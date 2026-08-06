"""Aggregation-table evaluation metrics.

Separates structure correctness (column/row alignment) from value
correctness (range-normalized error / string similarity on matched cells).

Numeric error is |pred - true| / (gold_col_max - gold_col_min), i.e.
fraction of the gold column's span (percentage points of the range), not
|pred-true|/|true|. That avoids blowing up on zero gold values.

Per-query rank score is the product of:
  structure_fbeta_score × cell_f1@tau

Pipeline order is mandatory:
  1. Column alignment
  2. Row alignment (Hungarian, three tiers)
  3. Value scoring (matched cells only)
  4. Grouping diagnostics (merge/split)
  5. Cell-F1@tau and query_score = structure × cell
  6. Optional budget curves
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

import numpy as np
from scipy.optimize import linear_sum_assignment

logger = logging.getLogger(__name__)

EmbeddingFn = Callable[[Sequence[str]], np.ndarray]


# ---------------------------------------------------------------------------
# Config / schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricConfig:
    tau: float = 0.05
    theta: float = 0.9
    epsilon: float = 1e-9
    tau_sweep: Tuple[float, ...] = (0.01, 0.05, 0.20)
    structure_beta: float = 2.0
    merge_value_tol: float = 0.05
    abbreviation_map: Mapping[str, str] = field(
        default_factory=lambda: {
            "usa": "united states",
            "us": "united states",
            "u.s.": "united states",
            "u.s.a.": "united states",
            "uk": "united kingdom",
            "u.k.": "united kingdom",
        }
    )

    def __post_init__(self) -> None:
        if not math.isfinite(self.structure_beta) or self.structure_beta <= 0:
            raise ValueError("structure_beta must be finite and positive")


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    role: str  # "key" | "measure"
    type: str  # "string" | "numeric" | "date"
    operator: Optional[str] = None  # COUNT/SUM/AVG/MIN/MAX for measures


@dataclass(frozen=True)
class AggregationTable:
    columns: Tuple[ColumnSpec, ...]
    rows: Tuple[Mapping[str, Any], ...]

    def column_names(self) -> Tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def by_role(self, role: str) -> Tuple[ColumnSpec, ...]:
        return tuple(column for column in self.columns if column.role == role)


# ---------------------------------------------------------------------------
# Canonicalization (logged stage — never bury inside comparisons)
# ---------------------------------------------------------------------------


def canonicalize(
    value: Any,
    *,
    value_type: str = "string",
    abbreviation_map: Optional[Mapping[str, str]] = None,
    log: bool = True,
) -> Any:
    """Deterministic value canonicalization.

    Always applied before exact comparisons and for the Normalized matching
    tier. Mutations are logged so callers can audit the stage.
    """
    abbrev = abbreviation_map or MetricConfig().abbreviation_map
    original = value
    if value is None:
        return None

    if value_type == "numeric":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            if isinstance(value, float) and value.is_integer():
                out = int(value)
            else:
                out = float(value) if isinstance(value, float) else int(value)
            if log and out != original:
                logger.debug("canonicalize numeric %r -> %r", original, out)
            return out
        text = str(value).strip().replace(",", "")
        try:
            number = float(text)
        except ValueError:
            return text.lower()
        out = int(number) if number.is_integer() else number
        if log:
            logger.debug("canonicalize numeric %r -> %r", original, out)
        return out

    if value_type == "date":
        text = str(value).strip()
        # Prefer ISO-ish YYYY-MM-DD; also accept YYYY/M/D and YYYY.M.D.
        match = re.match(
            r"^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$",
            text,
        )
        if match:
            year, month, day = match.groups()
            out = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            if log and out != text:
                logger.debug("canonicalize date %r -> %r", original, out)
            return out
        return text.lower()

    # string
    text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = abbrev.get(text, text)
    if log and text != str(original).strip().lower():
        logger.debug("canonicalize string %r -> %r", original, text)
    return text


def _normalize_column_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", str(name)).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


# ---------------------------------------------------------------------------
# Similarity helpers
# ---------------------------------------------------------------------------


def _token_set_ratio(a: str, b: str) -> float:
    ta = set(a.split())
    tb = set(b.split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    if not inter:
        return SequenceMatcher(None, a, b).ratio()
    sorted_inter = " ".join(sorted(inter))
    sorted_a = " ".join(sorted(ta))
    sorted_b = " ".join(sorted(tb))
    return max(
        SequenceMatcher(None, sorted_inter, sorted_a).ratio(),
        SequenceMatcher(None, sorted_inter, sorted_b).ratio(),
        SequenceMatcher(None, sorted_a, sorted_b).ratio(),
    )


def lexical_sim(a: Any, b: Any) -> float:
    sa = "" if a is None else str(a)
    sb = "" if b is None else str(b)
    if sa == sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return max(
        SequenceMatcher(None, sa, sb).ratio(),
        _token_set_ratio(sa, sb),
    )


def _embed_cosine(a: str, b: str, embed_fn: Optional[EmbeddingFn]) -> float:
    if embed_fn is None:
        return 0.0
    vectors = embed_fn([a, b])
    if vectors is None or len(vectors) < 2:
        return 0.0
    va = np.asarray(vectors[0], dtype=float)
    vb = np.asarray(vectors[1], dtype=float)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def string_sim(
    a: Any,
    b: Any,
    *,
    embed_fn: Optional[EmbeddingFn] = None,
    abbreviation_map: Optional[Mapping[str, str]] = None,
) -> float:
    ca = canonicalize(a, value_type="string", abbreviation_map=abbreviation_map)
    cb = canonicalize(b, value_type="string", abbreviation_map=abbreviation_map)
    if ca is None and cb is None:
        return 1.0
    if ca is None or cb is None:
        return 0.0
    return max(lexical_sim(ca, cb), _embed_cosine(str(ca), str(cb), embed_fn))


def key_component_sim(
    pred: Any,
    gold: Any,
    column: ColumnSpec,
    *,
    tier: str,
    config: MetricConfig,
    embed_fn: Optional[EmbeddingFn] = None,
) -> float:
    if tier == "exact":
        # Exact after light formatting only for numeric 2023 == 2023.0.
        if column.type == "numeric":
            try:
                return (
                    1.0
                    if float(pred) == float(gold)
                    else 0.0
                )
            except (TypeError, ValueError):
                return 1.0 if pred == gold else 0.0
        return 1.0 if pred == gold else 0.0

    # Normalized and semantic both canonicalize first.
    cp = canonicalize(
        pred,
        value_type=column.type,
        abbreviation_map=config.abbreviation_map,
    )
    cg = canonicalize(
        gold,
        value_type=column.type,
        abbreviation_map=config.abbreviation_map,
    )
    if column.type in {"numeric", "date"}:
        return 1.0 if cp == cg else 0.0

    if tier == "normalized":
        return 1.0 if cp == cg else 0.0

    # semantic
    return string_sim(
        cp,
        cg,
        embed_fn=embed_fn,
        abbreviation_map=config.abbreviation_map,
    )


def composite_key_sim(
    pred_row: Mapping[str, Any],
    gold_row: Mapping[str, Any],
    key_columns: Sequence[Tuple[str, ColumnSpec]],
    *,
    tier: str,
    config: MetricConfig,
    embed_fn: Optional[EmbeddingFn] = None,
) -> float:
    """All-or-nothing composite key similarity.

    Returns the minimum component similarity when every component clears
    ``theta`` under semantic tier, otherwise 0 when any component fails the
    tier's exact/normalized equality. For semantic tier we still require the
    full tuple: if any component sim < theta the edge is rejected later.
    """
    if not key_columns:
        return 1.0
    sims: List[float] = []
    for pred_name, column in key_columns:
        sims.append(
            key_component_sim(
                pred_row.get(pred_name),
                gold_row.get(column.name),
                column,
                tier=tier,
                config=config,
                embed_fn=embed_fn,
            )
        )
    if tier in {"exact", "normalized"}:
        return 1.0 if all(sim >= 1.0 - 1e-12 for sim in sims) else 0.0
    # semantic: all-or-nothing via min — later filtered by theta
    return float(min(sims)) if sims else 0.0


# ---------------------------------------------------------------------------
# Step 1 — Column alignment
# ---------------------------------------------------------------------------


def _prf(
    tp: int,
    pred_total: int,
    gold_total: int,
    *,
    beta: float = 1.0,
) -> Dict[str, float]:
    precision = tp / pred_total if pred_total else (1.0 if gold_total == 0 else 0.0)
    recall = tp / gold_total if gold_total else (1.0 if pred_total == 0 else 0.0)
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    beta_squared = beta * beta
    denominator = beta_squared * precision + recall
    fbeta = (
        (1.0 + beta_squared) * precision * recall / denominator
        if denominator
        else 0.0
    )
    return {
        "P": precision,
        "R": recall,
        "F1": f1,
        "F_beta": fbeta,
        "beta": beta,
    }


def align_columns(
    pred: AggregationTable,
    gold: AggregationTable,
    *,
    config: MetricConfig,
    embed_fn: Optional[EmbeddingFn] = None,
) -> Dict[str, Any]:
    """One-to-one predicted→GT column matching by name then semantic similarity."""
    gold_cols = list(gold.columns)
    pred_cols = list(pred.columns)
    unmatched_gold = set(range(len(gold_cols)))
    unmatched_pred = set(range(len(pred_cols)))
    matches: Dict[str, str] = {}  # pred_name -> gold_name
    gold_to_pred: Dict[str, str] = {}

    # Pass 1: normalized exact name.
    gold_by_norm = {
        _normalize_column_name(column.name): idx
        for idx, column in enumerate(gold_cols)
    }
    for p_idx in list(unmatched_pred):
        norm = _normalize_column_name(pred_cols[p_idx].name)
        g_idx = gold_by_norm.get(norm)
        if g_idx is not None and g_idx in unmatched_gold:
            matches[pred_cols[p_idx].name] = gold_cols[g_idx].name
            gold_to_pred[gold_cols[g_idx].name] = pred_cols[p_idx].name
            unmatched_pred.remove(p_idx)
            unmatched_gold.remove(g_idx)

    # Pass 2: semantic / lexical name similarity (Hungarian on remaining).
    if unmatched_pred and unmatched_gold:
        p_list = sorted(unmatched_pred)
        g_list = sorted(unmatched_gold)
        weight = np.zeros((len(p_list), len(g_list)), dtype=float)
        for i, p_idx in enumerate(p_list):
            for j, g_idx in enumerate(g_list):
                # Never align a grouping key to an aggregate measure merely
                # because their names happen to look similar.
                if pred_cols[p_idx].role != gold_cols[g_idx].role:
                    continue
                weight[i, j] = string_sim(
                    pred_cols[p_idx].name,
                    gold_cols[g_idx].name,
                    embed_fn=embed_fn,
                    abbreviation_map=config.abbreviation_map,
                )
        cost = -weight
        # Pad to square for unbalanced bipartite sets.
        n_r, n_c = cost.shape
        n = max(n_r, n_c)
        padded = np.zeros((n, n), dtype=float)
        padded[:n_r, :n_c] = cost
        ri, ci = linear_sum_assignment(padded)
        for r, c in zip(ri, ci):
            if r >= n_r or c >= n_c:
                continue
            if weight[r, c] < config.theta:
                continue
            p_idx = p_list[r]
            g_idx = g_list[c]
            matches[pred_cols[p_idx].name] = gold_cols[g_idx].name
            gold_to_pred[gold_cols[g_idx].name] = pred_cols[p_idx].name
            unmatched_pred.discard(p_idx)
            unmatched_gold.discard(g_idx)

    # Pass 3: schema-agnostic role fallback. When there is exactly one
    # unmatched predicted and gold column for a role, their structural
    # positions are unambiguous even if names differ completely (for example,
    # ``group_label`` vs ``nationality`` or ``metric`` vs ``avg_age``).
    # This is especially important for the one-key/one-measure aggregation
    # workload and uses no dataset names or ground-truth values.
    for role in ("key", "measure"):
        role_pred = [
            idx for idx in unmatched_pred if pred_cols[idx].role == role
        ]
        role_gold = [
            idx for idx in unmatched_gold if gold_cols[idx].role == role
        ]
        if len(role_pred) != 1 or len(role_gold) != 1:
            continue
        p_idx = role_pred[0]
        g_idx = role_gold[0]
        matches[pred_cols[p_idx].name] = gold_cols[g_idx].name
        gold_to_pred[gold_cols[g_idx].name] = pred_cols[p_idx].name
        unmatched_pred.remove(p_idx)
        unmatched_gold.remove(g_idx)

    key_gold = [c for c in gold_cols if c.role == "key"]
    measure_gold = [c for c in gold_cols if c.role == "measure"]
    key_pred = [c for c in pred_cols if c.role == "key"]
    measure_pred = [c for c in pred_cols if c.role == "measure"]
    # Roles for predicted columns come from the GT column they aligned to when
    # available; otherwise fall back to the predicted role declaration.
    matched_key = sum(
        1
        for c in key_gold
        if c.name in gold_to_pred
    )
    matched_measure = sum(
        1
        for c in measure_gold
        if c.name in gold_to_pred
    )
    # Predicted totals by role: prefer GT-aligned role, else declared role.
    pred_key_count = 0
    pred_measure_count = 0
    for column in pred_cols:
        gold_name = matches.get(column.name)
        if gold_name is not None:
            gold_col = next(c for c in gold_cols if c.name == gold_name)
            if gold_col.role == "key":
                pred_key_count += 1
            else:
                pred_measure_count += 1
        elif column.role == "key":
            pred_key_count += 1
        else:
            pred_measure_count += 1

    missing_key_columns = [
        c.name for c in key_gold if c.name not in gold_to_pred
    ]
    key_alignment_failed = bool(missing_key_columns)

    return {
        "matches": matches,
        "gold_to_pred": gold_to_pred,
        "missing_key_columns": missing_key_columns,
        "key_alignment_failed": key_alignment_failed,
        "metrics": {
            "key": _prf(
                matched_key,
                pred_key_count,
                len(key_gold),
                beta=config.structure_beta,
            ),
            "measure": _prf(
                matched_measure,
                pred_measure_count,
                len(measure_gold),
                beta=config.structure_beta,
            ),
            "all": _prf(
                len(matches),
                len(pred_cols),
                len(gold_cols),
                beta=config.structure_beta,
            ),
        },
    }


# ---------------------------------------------------------------------------
# Step 2 — Row alignment (Hungarian, three tiers)
# ---------------------------------------------------------------------------


def _hungarian_match(
    weights: np.ndarray,
    *,
    threshold: float,
) -> List[Tuple[int, int, float]]:
    """Max-weight one-to-one matching; keep pairs with weight >= threshold."""
    if weights.size == 0:
        return []
    n_pred, n_gold = weights.shape
    n = max(n_pred, n_gold)
    cost = np.zeros((n, n), dtype=float)
    # Convert max-weight → min-cost; unmatched padded cells get 0 weight.
    cost[:n_pred, :n_gold] = -weights
    row_ind, col_ind = linear_sum_assignment(cost)
    pairs: List[Tuple[int, int, float]] = []
    for r, c in zip(row_ind, col_ind):
        if r >= n_pred or c >= n_gold:
            continue
        w = float(weights[r, c])
        if w >= threshold:
            pairs.append((r, c, w))
    return pairs


def align_rows(
    pred: AggregationTable,
    gold: AggregationTable,
    column_alignment: Mapping[str, Any],
    *,
    config: MetricConfig,
    embed_fn: Optional[EmbeddingFn] = None,
    tier: str = "semantic",
) -> Dict[str, Any]:
    gold_to_pred = column_alignment["gold_to_pred"]
    key_columns: List[Tuple[str, ColumnSpec]] = []
    for column in gold.by_role("key"):
        pred_name = gold_to_pred.get(column.name)
        if pred_name is None:
            # Unaligned key column — cannot form a reliable key edge.
            continue
        key_columns.append((pred_name, column))

    n_pred = len(pred.rows)
    n_gold = len(gold.rows)
    if n_pred == 0 and n_gold == 0:
        return {
            "matched_pairs": [],
            "spurious_pred": [],
            "missing_gold": [],
            "metrics": _prf(0, 0, 0, beta=config.structure_beta),
            "key_columns_used": [c.name for _, c in key_columns],
        }

    # Threshold: exact/normalized require perfect key equality (weight 1);
    # semantic uses theta.
    edge_threshold = 1.0 if tier in {"exact", "normalized"} else config.theta

    if not key_columns:
        # No usable keys — only a trivial 1-1 if both sides have a single row.
        if n_pred == 1 and n_gold == 1:
            pairs = [(0, 0, 1.0)]
        else:
            pairs = []
    else:
        weights = np.zeros((n_pred, n_gold), dtype=float)
        for i, pred_row in enumerate(pred.rows):
            for j, gold_row in enumerate(gold.rows):
                weights[i, j] = composite_key_sim(
                    pred_row,
                    gold_row,
                    key_columns,
                    tier=tier,
                    config=config,
                    embed_fn=embed_fn,
                )
        pairs = _hungarian_match(weights, threshold=edge_threshold)

    matched_pred = {i for i, _, _ in pairs}
    matched_gold = {j for _, j, _ in pairs}
    spurious = [i for i in range(n_pred) if i not in matched_pred]
    missing = [j for j in range(n_gold) if j not in matched_gold]
    return {
        "matched_pairs": pairs,
        "spurious_pred": spurious,
        "missing_gold": missing,
        "metrics": _prf(
            len(pairs),
            n_pred,
            n_gold,
            beta=config.structure_beta,
        ),
        "key_columns_used": [c.name for _, c in key_columns],
    }


# ---------------------------------------------------------------------------
# Step 3 — Value scoring (matched cells only)
# ---------------------------------------------------------------------------


_REL_ERR_BUCKETS = (
    ("exact_or_le_1pct", 0.0, 0.01),
    ("1_to_5pct", 0.01, 0.05),
    ("5_to_20pct", 0.05, 0.20),
    ("20_to_100pct", 0.20, 1.0),
    ("gt_100pct", 1.0, math.inf),
)


def _gold_numeric_range(
    gold: AggregationTable,
    column_name: str,
) -> Tuple[Optional[float], Optional[float]]:
    """Min/max of a gold numeric measure column (ignoring non-numeric cells)."""
    values: List[float] = []
    for row in gold.rows:
        try:
            values.append(float(row.get(column_name)))
        except (TypeError, ValueError):
            continue
    if not values:
        return None, None
    return min(values), max(values)


def _numeric_range_err(
    pred: Any,
    true: Any,
    *,
    col_min: Optional[float],
    col_max: Optional[float],
    epsilon: float,
) -> Tuple[Optional[float], bool]:
    """Return (range_err, is_zero_true).

    range_err = |pred - true| / (col_max - col_min), i.e. absolute error as a
    fraction of the gold column's span (percentage points of the range).

    When the gold column is constant (span ≈ 0), require an exact match.
    is_zero_true is retained as a diagnostic when the gold cell itself is 0.
    """
    try:
        p = float(pred)
        t = float(true)
    except (TypeError, ValueError):
        return None, False
    is_zero_true = abs(t) <= epsilon
    if col_min is None or col_max is None:
        return None, is_zero_true
    span = float(col_max) - float(col_min)
    if span <= epsilon:
        return (0.0 if abs(p - t) <= epsilon else 1.0), is_zero_true
    return abs(p - t) / span, is_zero_true


def score_values(
    pred: AggregationTable,
    gold: AggregationTable,
    column_alignment: Mapping[str, Any],
    row_alignment: Mapping[str, Any],
    *,
    config: MetricConfig,
    embed_fn: Optional[EmbeddingFn] = None,
    merge_pred_indices: Optional[Iterable[int]] = None,
    split_pred_indices: Optional[Iterable[int]] = None,
) -> Dict[str, Any]:
    """Score values ONLY on cleanly matched row×measure cells.

    Missing, spurious, merge, and split rows never enter the value
    distribution. Numeric error is range-normalized against the gold column.
    """
    excluded_pred = set(merge_pred_indices or ()) | set(split_pred_indices or ())
    gold_to_pred = column_alignment["gold_to_pred"]
    measure_cols = [
        column
        for column in gold.by_role("measure")
        if column.name in gold_to_pred
    ]
    column_ranges = {
        column.name: _gold_numeric_range(gold, column.name)
        for column in measure_cols
        if column.type == "numeric"
    }

    range_errors: List[float] = []
    pass_hits: Dict[float, int] = {tau: 0 for tau in config.tau_sweep}
    pass_total = 0
    by_operator: Dict[str, Dict[str, Any]] = {}
    zero_true_count = 0
    catastrophic = 0
    string_scores: List[float] = []

    clean_pairs = [
        (pi, gi, w)
        for pi, gi, w in row_alignment["matched_pairs"]
        if pi not in excluded_pred
    ]

    for pred_idx, gold_idx, _weight in clean_pairs:
        pred_row = pred.rows[pred_idx]
        gold_row = gold.rows[gold_idx]
        for column in measure_cols:
            pred_name = gold_to_pred[column.name]
            pred_val = pred_row.get(pred_name)
            gold_val = gold_row.get(column.name)
            op = (column.operator or "UNKNOWN").upper()
            op_bucket = by_operator.setdefault(
                op,
                {
                    "pass_hits": {tau: 0 for tau in config.tau_sweep},
                    "total": 0,
                },
            )

            if column.type == "numeric":
                col_min, col_max = column_ranges[column.name]
                range_err, is_zero_true = _numeric_range_err(
                    pred_val,
                    gold_val,
                    col_min=col_min,
                    col_max=col_max,
                    epsilon=config.epsilon,
                )
                if is_zero_true:
                    zero_true_count += 1
                if range_err is None:
                    continue
                range_errors.append(range_err)
                pass_total += 1
                op_bucket["total"] += 1
                if range_err > 1.0:
                    catastrophic += 1
                for tau in config.tau_sweep:
                    if range_err <= tau:
                        pass_hits[tau] += 1
                        op_bucket["pass_hits"][tau] += 1
            else:
                sim = string_sim(
                    pred_val,
                    gold_val,
                    embed_fn=embed_fn,
                    abbreviation_map=config.abbreviation_map,
                )
                string_scores.append(sim)
                pass_total += 1
                op_bucket["total"] += 1
                # String measures use theta as the pass threshold for every
                # tau entry (tau is numeric); still report under pass_at_tau
                # for a uniform interface when mixed.
                for tau in config.tau_sweep:
                    if sim >= config.theta:
                        pass_hits[tau] += 1
                        op_bucket["pass_hits"][tau] += 1

    histogram = {name: 0.0 for name, _, _ in _REL_ERR_BUCKETS}
    if range_errors:
        for err in range_errors:
            if err <= 0.01:
                histogram["exact_or_le_1pct"] += 1
            elif err < 0.05:
                histogram["1_to_5pct"] += 1
            elif err < 0.20:
                histogram["5_to_20pct"] += 1
            elif err <= 1.0:
                histogram["20_to_100pct"] += 1
            else:
                histogram["gt_100pct"] += 1
        total = float(len(range_errors))
        histogram = {k: v / total for k, v in histogram.items()}

    pass_at_tau = {
        tau: (pass_hits[tau] / pass_total if pass_total else 1.0)
        for tau in config.tau_sweep
    }
    pass_by_operator = {
        op: {
            tau: (
                stats["pass_hits"][tau] / stats["total"]
                if stats["total"]
                else 1.0
            )
            for tau in config.tau_sweep
        }
        for op, stats in by_operator.items()
    }

    row_recall = float(row_alignment["metrics"]["R"])
    return {
        "row_recall_context": row_recall,
        "rel_err_histogram": histogram,
        "range_err_histogram": histogram,
        "pass_at_tau": pass_at_tau,
        "pass_by_operator": pass_by_operator,
        "frac_catastrophic": (
            catastrophic / len(range_errors) if range_errors else 0.0
        ),
        "zero_true_count": zero_true_count,
        "n_numeric_cells": len(range_errors),
        "n_string_cells": len(string_scores),
        "n_scored_cells": pass_total,
        "column_ranges": {
            name: {"min": lo, "max": hi}
            for name, (lo, hi) in column_ranges.items()
        },
    }


# ---------------------------------------------------------------------------
# Step 4 — Grouping diagnostics (merge / split)
# ---------------------------------------------------------------------------


def detect_grouping_errors(
    pred: AggregationTable,
    gold: AggregationTable,
    column_alignment: Mapping[str, Any],
    *,
    config: MetricConfig,
    embed_fn: Optional[EmbeddingFn] = None,
) -> Dict[str, Any]:
    """Aggregate-consistency (additivity) check for under/over-grouping."""
    gold_to_pred = column_alignment["gold_to_pred"]
    key_columns: List[Tuple[str, ColumnSpec]] = []
    for column in gold.by_role("key"):
        pred_name = gold_to_pred.get(column.name)
        if pred_name is not None:
            key_columns.append((pred_name, column))

    measure_cols = [
        column
        for column in gold.by_role("measure")
        if column.type == "numeric" and column.name in gold_to_pred
    ]
    if not key_columns or not measure_cols or not pred.rows or not gold.rows:
        return {
            "merge_rate": 0.0,
            "split_rate": 0.0,
            "merge_pred_indices": [],
            "split_pred_indices": [],
            "merge_events": [],
            "split_events": [],
        }

    # Soft key similarity matrix (semantic) without one-to-one constraint.
    soft = np.zeros((len(pred.rows), len(gold.rows)), dtype=float)
    for i, pred_row in enumerate(pred.rows):
        for j, gold_row in enumerate(gold.rows):
            soft[i, j] = composite_key_sim(
                pred_row,
                gold_row,
                key_columns,
                tier="semantic",
                config=config,
                embed_fn=embed_fn,
            )

    def _measure_sum(rows: Sequence[Mapping[str, Any]], name: str) -> float:
        total = 0.0
        for row in rows:
            try:
                total += float(row.get(name) or 0.0)
            except (TypeError, ValueError):
                continue
        return total

    merge_events = []
    merge_pred_indices: List[int] = []
    for i, pred_row in enumerate(pred.rows):
        close = [j for j in range(len(gold.rows)) if soft[i, j] >= config.theta]
        if len(close) < 2:
            continue
        # Check additivity on at least one numeric measure.
        additive = False
        for column in measure_cols:
            pred_name = gold_to_pred[column.name]
            try:
                pred_val = float(pred_row.get(pred_name))
            except (TypeError, ValueError):
                continue
            gold_sum = _measure_sum(
                [gold.rows[j] for j in close], column.name
            )
            denom = abs(gold_sum) + config.epsilon
            if abs(pred_val - gold_sum) / denom <= config.merge_value_tol:
                additive = True
                break
        if additive:
            merge_pred_indices.append(i)
            merge_events.append({"pred_idx": i, "gold_indices": close})

    split_events = []
    split_pred_indices: List[int] = []
    for j, gold_row in enumerate(gold.rows):
        close = [i for i in range(len(pred.rows)) if soft[i, j] >= config.theta]
        if len(close) < 2:
            continue
        additive = False
        for column in measure_cols:
            pred_name = gold_to_pred[column.name]
            try:
                gold_val = float(gold_row.get(column.name))
            except (TypeError, ValueError):
                continue
            pred_sum = _measure_sum(
                [pred.rows[i] for i in close], pred_name
            )
            denom = abs(gold_val) + config.epsilon
            if abs(pred_sum - gold_val) / denom <= config.merge_value_tol:
                additive = True
                break
        if additive:
            split_pred_indices.extend(close)
            split_events.append({"gold_idx": j, "pred_indices": close})

    split_pred_indices = sorted(set(split_pred_indices))
    return {
        "merge_rate": (
            len(merge_pred_indices) / len(pred.rows) if pred.rows else 0.0
        ),
        "split_rate": (
            len(split_events) / len(gold.rows) if gold.rows else 0.0
        ),
        "merge_pred_indices": merge_pred_indices,
        "split_pred_indices": split_pred_indices,
        "merge_events": merge_events,
        "split_events": split_events,
    }


# ---------------------------------------------------------------------------
# Step 5 — Cell-F1@tau
# ---------------------------------------------------------------------------


def cell_f1_at_tau(
    pred: AggregationTable,
    gold: AggregationTable,
    column_alignment: Mapping[str, Any],
    row_alignment: Mapping[str, Any],
    *,
    config: MetricConfig,
    tau: float,
    embed_fn: Optional[EmbeddingFn] = None,
    merge_pred_indices: Optional[Iterable[int]] = None,
    split_pred_indices: Optional[Iterable[int]] = None,
) -> Dict[str, float]:
    """Cell-level F1 where TP requires column + row + value pass."""
    excluded_pred = set(merge_pred_indices or ()) | set(split_pred_indices or ())
    gold_to_pred = column_alignment["gold_to_pred"]
    matches = column_alignment["matches"]

    # Build matched-row lookup.
    pair_map = {
        pi: gi
        for pi, gi, _ in row_alignment["matched_pairs"]
        if pi not in excluded_pred
    }

    measure_gold = list(gold.by_role("measure"))
    # If there are no measure columns, treat key cells as the ranked cells.
    ranked_gold_cols = measure_gold or list(gold.by_role("key"))
    ranked_pred_cols = []
    for column in pred.columns:
        gold_name = matches.get(column.name)
        if gold_name is None:
            ranked_pred_cols.append(column)
            continue
        gold_col = next(c for c in gold.columns if c.name == gold_name)
        if measure_gold:
            if gold_col.role == "measure":
                ranked_pred_cols.append(column)
        else:
            if gold_col.role == "key":
                ranked_pred_cols.append(column)
    # Also count unmatched predicted columns of measure/key role as FP sources.
    for column in pred.columns:
        if column in ranked_pred_cols:
            continue
        if measure_gold and column.role == "measure":
            ranked_pred_cols.append(column)
        elif not measure_gold and column.role == "key":
            ranked_pred_cols.append(column)

    column_ranges = {
        column.name: _gold_numeric_range(gold, column.name)
        for column in ranked_gold_cols
        if column.type == "numeric"
    }

    tp = 0
    # Every predicted ranked cell is a candidate FP unless proven TP.
    pred_cell_count = len(pred.rows) * len(ranked_pred_cols)
    gold_cell_count = len(gold.rows) * len(ranked_gold_cols)

    for pred_idx, gold_idx in pair_map.items():
        pred_row = pred.rows[pred_idx]
        gold_row = gold.rows[gold_idx]
        for gold_col in ranked_gold_cols:
            pred_name = gold_to_pred.get(gold_col.name)
            if pred_name is None:
                continue
            pred_val = pred_row.get(pred_name)
            gold_val = gold_row.get(gold_col.name)
            passes = False
            if gold_col.type == "numeric":
                col_min, col_max = column_ranges[gold_col.name]
                range_err, _is_zero_true = _numeric_range_err(
                    pred_val,
                    gold_val,
                    col_min=col_min,
                    col_max=col_max,
                    epsilon=config.epsilon,
                )
                if range_err is not None:
                    passes = range_err <= tau
            else:
                passes = (
                    string_sim(
                        pred_val,
                        gold_val,
                        embed_fn=embed_fn,
                        abbreviation_map=config.abbreviation_map,
                    )
                    >= config.theta
                )
            if passes:
                tp += 1

    fp = max(pred_cell_count - tp, 0)
    fn = max(gold_cell_count - tp, 0)
    return _prf(tp, tp + fp, tp + fn)


# ---------------------------------------------------------------------------
# Step 6 — Budget curves
# ---------------------------------------------------------------------------


def budget_curves(
    runs: Sequence[Mapping[str, Any]],
    *,
    target_tau: float = 0.05,
    target_score: float = 0.8,
) -> Dict[str, Any]:
    """Build score-vs-tokens series from per-run evaluation outputs.

    Each run mapping must contain ``tokens`` (int) and ``metrics`` (the output
    of ``evaluate_aggregation_tables``).
    """
    ordered = sorted(runs, key=lambda run: int(run["tokens"]))
    series = []
    for run in ordered:
        metrics = run["metrics"]
        cell_f1 = metrics["rank"]["cell_f1"]
        # Keys may be float or stringified float depending on JSON round-trip.
        score = None
        for key, value in cell_f1.items():
            if abs(float(key) - target_tau) < 1e-12:
                score = float(value)
                break
        if score is None and cell_f1:
            score = float(next(iter(cell_f1.values())))
        series.append(
            {
                "tokens": int(run["tokens"]),
                "cell_f1": score,
                "row_recall": metrics["value"]["row_recall_context"],
            }
        )

    auc = 0.0
    if len(series) >= 2:
        for left, right in zip(series, series[1:]):
            width = right["tokens"] - left["tokens"]
            height = 0.5 * (
                (left["cell_f1"] or 0.0) + (right["cell_f1"] or 0.0)
            )
            auc += width * height

    tokens_to_reach = None
    for point in series:
        if (point["cell_f1"] or 0.0) >= target_score:
            tokens_to_reach = point["tokens"]
            break

    return {
        "series": series,
        "auc": auc,
        "tokens_to_reach_tau": tokens_to_reach,
        "target_tau": target_tau,
        "target_score": target_score,
    }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def evaluate_aggregation_tables(
    pred: AggregationTable,
    gold: AggregationTable,
    *,
    config: Optional[MetricConfig] = None,
    embed_fn: Optional[EmbeddingFn] = None,
    budget_runs: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Full aggregation-table evaluation. Steps run in mandatory order."""
    config = config or MetricConfig()

    # Step 1
    column_alignment = align_columns(
        pred, gold, config=config, embed_fn=embed_fn
    )

    # Step 2 — three tiers
    row_by_tier = {
        tier: align_rows(
            pred,
            gold,
            column_alignment,
            config=config,
            embed_fn=embed_fn,
            tier=tier,
        )
        for tier in ("exact", "normalized", "semantic")
    }
    # Prefer semantic matches for downstream value scoring; fall back.
    primary_rows = row_by_tier["semantic"]
    if not primary_rows["matched_pairs"] and row_by_tier["normalized"][
        "matched_pairs"
    ]:
        primary_rows = row_by_tier["normalized"]
    if not primary_rows["matched_pairs"] and row_by_tier["exact"][
        "matched_pairs"
    ]:
        primary_rows = row_by_tier["exact"]

    # Step 4 before interpreting value metrics
    grouping = detect_grouping_errors(
        pred,
        gold,
        column_alignment,
        config=config,
        embed_fn=embed_fn,
    )

    # Step 3 — values only on clean matches (exclude merge/split)
    value = score_values(
        pred,
        gold,
        column_alignment,
        primary_rows,
        config=config,
        embed_fn=embed_fn,
        merge_pred_indices=grouping["merge_pred_indices"],
        split_pred_indices=grouping["split_pred_indices"],
    )

    # Step 5
    cell_f1 = {
        tau: cell_f1_at_tau(
            pred,
            gold,
            column_alignment,
            primary_rows,
            config=config,
            tau=tau,
            embed_fn=embed_fn,
            merge_pred_indices=grouping["merge_pred_indices"],
            split_pred_indices=grouping["split_pred_indices"],
        )["F1"]
        for tau in config.tau_sweep
    }

    # Structure score favors recall: row F-beta × mean column F-beta.
    # Keep the historical F1 score beside it for auditability.
    row_f1 = float(primary_rows["metrics"]["F1"])
    row_fbeta = float(primary_rows["metrics"]["F_beta"])
    col_metrics = column_alignment["metrics"]
    col_f1s = [
        float(col_metrics["key"]["F1"]),
        float(col_metrics["measure"]["F1"]),
    ]
    col_fbetas = [
        float(col_metrics["key"]["F_beta"]),
        float(col_metrics["measure"]["F_beta"]),
    ]
    structure_f1_score = row_f1 * (sum(col_f1s) / len(col_f1s))
    structure_score = row_fbeta * (
        sum(col_fbetas) / len(col_fbetas)
    )
    query_score = {
        tau: structure_score * cell_f1[tau] for tau in config.tau_sweep
    }

    result: Dict[str, Any] = {
        "rank": {
            "structure_score": structure_score,
            "structure_fbeta_score": structure_score,
            "structure_f1_score": structure_f1_score,
            "structure_beta": config.structure_beta,
            "cell_f1": cell_f1,
            "query_score": query_score,
        },
        "structure": {
            "column": column_alignment["metrics"],
            "row": {
                tier: row_by_tier[tier]["metrics"]
                for tier in ("exact", "normalized", "semantic")
            },
            "key_alignment_failed": column_alignment["key_alignment_failed"],
            "missing_key_columns": column_alignment["missing_key_columns"],
            "structure_score": structure_score,
            "structure_fbeta_score": structure_score,
            "structure_f1_score": structure_f1_score,
            "structure_beta": config.structure_beta,
        },
        "value": {
            "row_recall_context": value["row_recall_context"],
            "rel_err_histogram": value["rel_err_histogram"],
            "range_err_histogram": value["range_err_histogram"],
            "pass_at_tau": value["pass_at_tau"],
            "pass_by_operator": value["pass_by_operator"],
            "frac_catastrophic": value["frac_catastrophic"],
            "zero_true_count": value["zero_true_count"],
            "column_ranges": value["column_ranges"],
        },
        "grouping": {
            "merge_rate": grouping["merge_rate"],
            "split_rate": grouping["split_rate"],
        },
    }

    # Step 6
    if budget_runs is not None:
        # Allow callers to pass already-evaluated sibling runs, or raw tables.
        prepared = []
        for run in budget_runs:
            if "metrics" in run:
                prepared.append(run)
            else:
                prepared.append(
                    {
                        "tokens": run["tokens"],
                        "metrics": evaluate_aggregation_tables(
                            run["pred"],
                            gold,
                            config=config,
                            embed_fn=embed_fn,
                        ),
                    }
                )
        result["budget"] = budget_curves(prepared)
    else:
        result["budget"] = None

    return result


def table_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    key_columns: Sequence[str],
    measure_columns: Sequence[str],
    column_types: Optional[Mapping[str, str]] = None,
    operators: Optional[Mapping[str, str]] = None,
) -> AggregationTable:
    """Convenience builder for tests and callers without typed schemas."""
    column_types = column_types or {}
    operators = operators or {}
    columns: List[ColumnSpec] = []
    for name in key_columns:
        columns.append(
            ColumnSpec(
                name=name,
                role="key",
                type=column_types.get(name, "string"),
            )
        )
    for name in measure_columns:
        columns.append(
            ColumnSpec(
                name=name,
                role="measure",
                type=column_types.get(name, "numeric"),
                operator=operators.get(name),
            )
        )
    return AggregationTable(
        columns=tuple(columns),
        rows=tuple(dict(row) for row in rows),
    )


def schema_from_sql(sql: str) -> Dict[str, Any]:
    """Infer aggregation key/measure roles from reference SQL.

    Uses GROUP BY columns as keys and aggregate SELECT aliases as measures.
    Non-aggregation SQL returns ``is_aggregation=False``.
    """
    import sqlglot
    from sqlglot import exp

    expr = sqlglot.parse_one(sql, error_level="ignore")
    group_expr = expr.args.get("group") if expr is not None else None
    group_by: List[str] = []
    if group_expr is not None:
        for node in group_expr.expressions:
            if isinstance(node, exp.Column):
                group_by.append(node.name)
            else:
                text = node.sql()
                group_by.append(text.split(".")[-1] if "." in text else text)

    key_columns: List[str] = []
    measure_columns: List[str] = []
    operators: Dict[str, str] = {}
    column_types: Dict[str, str] = {}
    selects = list(expr.selects) if expr is not None else []
    for node in selects:
        if isinstance(node, exp.Alias):
            output_name = str(node.alias)
            value = node.this
        else:
            output_name = str(
                getattr(node, "alias_or_name", None)
                or getattr(node, "output_name", None)
                or node.sql()
            )
            value = node
        is_agg = isinstance(value, exp.AggFunc) or bool(
            getattr(value, "is_aggregate", False)
        )
        if is_agg:
            measure_columns.append(output_name)
            column_types[output_name] = "numeric"
            if hasattr(value, "sql_name"):
                operators[output_name] = value.sql_name().upper()
            elif hasattr(value, "key"):
                operators[output_name] = str(value.key).upper()
        else:
            # Prefer the bare column name that appears in result frames.
            if isinstance(value, exp.Column):
                output_name = value.name or output_name
            key_columns.append(output_name)
            column_types[output_name] = "string"

    # GROUP BY is authoritative for keys when present.
    if group_by:
        key_columns = list(dict.fromkeys(group_by))
        for name in key_columns:
            column_types.setdefault(name, "string")

    is_aggregation = bool(group_by) or bool(measure_columns)
    return {
        "key_columns": key_columns,
        "measure_columns": measure_columns,
        "column_types": column_types,
        "operators": operators,
        "is_aggregation": is_aggregation,
        "has_groupby": bool(group_by),
    }


def _resolve_result_column(
    declared: str, present: set[str]
) -> Optional[str]:
    if not present:
        return declared
    if declared in present:
        return declared
    target = _normalize_column_name(declared)
    for name in present:
        if _normalize_column_name(name) == target:
            return name
    return None


def gold_table_from_sql(
    rows: Sequence[Mapping[str, Any]], sql: str
) -> AggregationTable:
    """Build a typed gold aggregation table from reference SQL + result rows."""
    schema = schema_from_sql(sql)
    if not schema["is_aggregation"]:
        raise ValueError("reference SQL is not an aggregation query")
    present: set[str] = set()
    for row in rows:
        present.update(str(key) for key in row.keys())

    key_columns: List[str] = []
    for name in schema["key_columns"]:
        resolved = _resolve_result_column(name, present)
        if resolved is not None and resolved not in key_columns:
            key_columns.append(resolved)

    measure_columns: List[str] = []
    for name in schema["measure_columns"]:
        resolved = _resolve_result_column(name, present)
        if resolved is not None and resolved not in measure_columns:
            measure_columns.append(resolved)

    claimed = set(key_columns) | set(measure_columns)
    for name in present:
        if name in claimed:
            continue
        if _column_values_look_numeric(rows, name):
            measure_columns.append(name)
        else:
            key_columns.append(name)

    column_types = dict(schema["column_types"])
    for name in key_columns:
        column_types.setdefault(name, "string")
    for name in measure_columns:
        column_types.setdefault(name, "numeric")
    return table_from_rows(
        rows,
        key_columns=key_columns,
        measure_columns=measure_columns,
        column_types=column_types,
        operators=schema["operators"],
    )


def _column_values_look_numeric(
    rows: Sequence[Mapping[str, Any]], column: str
) -> bool:
    seen = False
    for row in rows:
        value = row.get(column)
        if value is None or value == "":
            continue
        seen = True
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            continue
        try:
            float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return False
    return seen


def predicted_table_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    gold: AggregationTable,
) -> AggregationTable:
    """Assign key/measure roles to predicted columns for alignment.

    Name matches against the gold schema win first. Remaining columns are
    filled into leftover key/measure slots using value-type heuristics so the
    one-key/one-measure role fallback can still fire when names differ.
    """
    if not rows:
        return AggregationTable(columns=(), rows=())

    colnames: List[str] = []
    seen: set[str] = set()
    for row in rows:
        for name in row.keys():
            if name not in seen:
                seen.add(name)
                colnames.append(name)

    gold_by_norm = {
        _normalize_column_name(column.name): column for column in gold.columns
    }
    assigned: Dict[str, ColumnSpec] = {}
    used_gold: set[str] = set()
    for name in colnames:
        gold_col = gold_by_norm.get(_normalize_column_name(name))
        if gold_col is None or gold_col.name in used_gold:
            continue
        assigned[name] = ColumnSpec(
            name=name,
            role=gold_col.role,
            type=gold_col.type,
            operator=gold_col.operator,
        )
        used_gold.add(gold_col.name)

    leftover = [name for name in colnames if name not in assigned]
    key_slots = max(0, len(gold.by_role("key")) - sum(
        1 for spec in assigned.values() if spec.role == "key"
    ))
    measure_slots = max(0, len(gold.by_role("measure")) - sum(
        1 for spec in assigned.values() if spec.role == "measure"
    ))

    numeric_left = [
        name for name in leftover if _column_values_look_numeric(rows, name)
    ]
    string_left = [name for name in leftover if name not in numeric_left]

    # Prefer string-like leftovers for keys and numeric leftovers for measures.
    for name in string_left:
        if key_slots > 0:
            assigned[name] = ColumnSpec(name=name, role="key", type="string")
            key_slots -= 1
        elif measure_slots > 0:
            assigned[name] = ColumnSpec(
                name=name, role="measure", type="numeric"
            )
            measure_slots -= 1
        else:
            assigned[name] = ColumnSpec(name=name, role="key", type="string")
    for name in numeric_left:
        if name in assigned:
            continue
        if measure_slots > 0:
            assigned[name] = ColumnSpec(
                name=name, role="measure", type="numeric"
            )
            measure_slots -= 1
        elif key_slots > 0:
            assigned[name] = ColumnSpec(name=name, role="key", type="string")
            key_slots -= 1
        else:
            assigned[name] = ColumnSpec(
                name=name, role="measure", type="numeric"
            )

    key_columns = [name for name in colnames if assigned[name].role == "key"]
    measure_columns = [
        name for name in colnames if assigned[name].role == "measure"
    ]
    column_types = {name: assigned[name].type for name in colnames}
    operators = {
        name: assigned[name].operator
        for name in measure_columns
        if assigned[name].operator
    }
    return table_from_rows(
        rows,
        key_columns=key_columns,
        measure_columns=measure_columns,
        column_types=column_types,
        operators=operators,
    )


def json_ready_metrics(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert float-keyed metric dicts into JSON-safe string keys."""

    def _convert(value: Any) -> Any:
        if isinstance(value, Mapping):
            out: Dict[str, Any] = {}
            for key, item in value.items():
                out[str(key) if isinstance(key, float) else key] = _convert(
                    item
                )
            return out
        if isinstance(value, list):
            return [_convert(item) for item in value]
        if isinstance(value, tuple):
            return [_convert(item) for item in value]
        return value

    return _convert(result)

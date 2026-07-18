"""Phase 1 — Population transformation logic.

`apply_population` takes already-extracted, already-schema-stabilized WDIRS
records (i.e. the output of extraction/sieve/schema-stabilization, which
this module never touches) and re-derives a populated table for a given
`PopulationConfig`. This lets one shared, expensive WDIRS extraction be
"replayed" through many cheap population configs.

Two operating modes:
  - "rich" mode: a real `entity_resolver.EntityResolver` (and optionally an
    LLM client) is supplied, so embedding-based blocking, cross-encoder
    matching, and LLM canonicalization/normalization behave exactly like
    WDIRS's production path, just parameterized by `config`.
  - "cheap" mode (no resolver/LLM supplied): deterministic, dependency-free
    heuristics stand in for embedding/LLM steps. This mode exists so the
    Phase 2 config-grid diagnostic can run quickly over many configs without
    paying for real embeddings/LLM calls on every candidate; it is NOT a
    substitute for evaluating final routed configs, which should use rich
    mode.
"""

from __future__ import annotations

import copy
import logging
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional

from spp.population_config import PopulationConfig

logger = logging.getLogger(__name__)


@dataclass
class PopulationDiagnostics:
    """Deployment-visible ("glass-box") signals from one population run.

    These feed Phase 4's routing layer -- no ground truth involved.
    """

    table_name: str = ""
    config_id: str = ""
    n_input_rows: int = 0
    n_output_rows: int = 0
    n_entity_merges: int = 0
    n_values_normalized: int = 0
    n_values_unit_parsed: int = 0
    n_unit_parse_failures: int = 0
    n_missing_cells_before: int = 0
    n_missing_cells_after: int = 0
    n_rows_dropped_for_missing: int = 0
    column_coverage: Dict[str, float] = field(default_factory=dict)

    @property
    def missing_value_rate(self) -> float:
        total_cells = self.n_output_rows * max(len(self.column_coverage), 1)
        if total_cells == 0:
            return 0.0
        return self.n_missing_cells_after / total_cells

    @property
    def schema_column_coverage(self) -> float:
        if not self.column_coverage:
            return 0.0
        return sum(self.column_coverage.values()) / len(self.column_coverage)

    def glass_box_composite(self) -> float:
        """Single [0,1] quality proxy, analogous to spp-agent's composite."""
        signals = [
            self.schema_column_coverage,
            1.0 - min(self.missing_value_rate, 1.0),
            1.0 - min(self.n_unit_parse_failures / max(self.n_values_unit_parsed, 1), 1.0)
            if self.n_values_unit_parsed
            else 1.0,
        ]
        return sum(signals) / len(signals)


_UNIT_PATTERN = re.compile(
    r"^\s*[\$€£]?\s*([\d,]+(?:\.\d+)?)\s*(k|m|b|thousand|million|billion)?\s*$",
    re.IGNORECASE,
)
_UNIT_MULTIPLIERS = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "million": 1e6,
    "b": 1e9,
    "billion": 1e9,
}


def _try_parse_unit_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _UNIT_PATTERN.match(str(value))
    if not match:
        return None
    number_str, suffix = match.groups()
    try:
        number = float(number_str.replace(",", ""))
    except ValueError:
        return None
    if suffix:
        number *= _UNIT_MULTIPLIERS.get(suffix.lower(), 1.0)
    return number


def _dictionary_normalize(value: Any) -> Any:
    """Rule-based normalization: whitespace/case cleanup only."""
    if not isinstance(value, str):
        return value
    cleaned = re.sub(r"\s+", " ", value.strip())
    return cleaned


def _cheap_cluster_values(
    values: List[str], threshold: float
) -> Dict[str, str]:
    """Dependency-free entity clustering via SequenceMatcher ratio.

    Stands in for embedding-based blocking in "cheap" mode. Returns a
    mention -> canonical map (canonical = most frequent member of cluster).
    """
    unique_values = list(dict.fromkeys(v for v in values if v))
    clusters: List[List[str]] = []
    for value in unique_values:
        placed = False
        for cluster in clusters:
            if SequenceMatcher(None, value.lower(), cluster[0].lower()).ratio() >= threshold:
                cluster.append(value)
                placed = True
                break
        if not placed:
            clusters.append([value])

    counts = Counter(values)
    canonical_map: Dict[str, str] = {}
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        canonical = max(cluster, key=lambda v: counts.get(v, 0))
        for member in cluster:
            if member != canonical:
                canonical_map[member] = canonical
    return canonical_map


def _resolve_entities_for_column(
    records: List[Dict[str, Any]],
    column: str,
    config: PopulationConfig,
    entity_resolver: Optional[Any],
    semantic_type: str,
) -> Dict[str, str]:
    """Returns mention -> canonical map for one column, respecting the
    configured er_strategy. Uses rich EntityResolver when supplied, else
    the cheap SequenceMatcher heuristic.
    """
    values = [str(r[column]) for r in records if r.get(column) not in (None, "")]
    if len(values) < 2:
        return {}

    if entity_resolver is not None:
        from entity_resolver import EntityMention  # WDIRS module

        mentions = [
            EntityMention(
                mention_id=f"{column}_{i}",
                value=v,
                table_name="",
                column_name=column,
                semantic_type=semantic_type,
            )
            for i, v in enumerate(values)
        ]
        original_threshold = getattr(entity_resolver, "bi_encoder_threshold", None)
        try:
            if config.er_strategy.startswith("embedding_"):
                entity_resolver.bi_encoder_threshold = config.er_threshold
                result = entity_resolver.resolve_entities(mentions, semantic_type=semantic_type)
            else:  # "llm" strategy: rely on resolver's LLM canonicalization phase
                result = entity_resolver.resolve_entities(mentions, semantic_type=semantic_type)
            return dict(result.canonical_map)
        finally:
            if original_threshold is not None:
                entity_resolver.bi_encoder_threshold = original_threshold

    # Cheap mode fallback.
    threshold = config.er_threshold if config.er_strategy.startswith("embedding_") else 0.6
    return _cheap_cluster_values(values, threshold)


def apply_population(
    records: List[Dict[str, Any]],
    config: PopulationConfig,
    *,
    table_name: str = "",
    column_semantic_types: Optional[Dict[str, str]] = None,
    identity_columns: Optional[List[str]] = None,
    numeric_columns: Optional[List[str]] = None,
    entity_resolver: Optional[Any] = None,
    llm_normalize_fn: Optional[Callable[[str], str]] = None,
    llm_fill_fn: Optional[Callable[[str, str], Any]] = None,
) -> "tuple[List[Dict[str, Any]], PopulationDiagnostics]":
    """Apply one PopulationConfig to already-extracted records.

    Order matches the problem statement's composition:
        pop = f_miss ∘ f_unit ∘ f_type ∘ f_norm ∘ f_er
    i.e. entity resolution first, then normalization, then unit parsing,
    then (implicit type coercion), then missing-value handling last.
    """
    column_semantic_types = column_semantic_types or {}
    identity_columns = identity_columns or [
        c for c, t in column_semantic_types.items() if t in ("PERSON", "ORG", "GPE")
    ]
    numeric_columns = numeric_columns or [
        c for c, t in column_semantic_types.items() if t in ("MONEY", "QUANTITY", "QUANTITY_COUNT")
    ]

    diag = PopulationDiagnostics(
        table_name=table_name,
        config_id=config.config_id,
        n_input_rows=len(records),
    )
    if not records:
        diag.n_output_rows = 0
        return [], diag

    working = [copy.deepcopy(r) for r in records]

    # --- 1. Entity resolution -------------------------------------------------
    for column in identity_columns:
        semantic_type = column_semantic_types.get(column, "OTHER")
        canonical_map = _resolve_entities_for_column(
            working, column, config, entity_resolver, semantic_type
        )
        if canonical_map:
            diag.n_entity_merges += len(canonical_map)
            for row in working:
                if column in row and row[column] in canonical_map:
                    row[column] = canonical_map[row[column]]

    # --- 2. Value normalization ----------------------------------------------
    all_columns = {k for r in working for k in r.keys()}
    for row in working:
        for column in all_columns:
            value = row.get(column)
            if not isinstance(value, str) or not value:
                continue
            if config.norm_strategy == "llm" and llm_normalize_fn is not None:
                normalized = llm_normalize_fn(value)
            else:
                normalized = _dictionary_normalize(value)
            if normalized != value:
                diag.n_values_normalized += 1
                row[column] = normalized

    # --- 3. Unit standardization -----------------------------------------------
    if config.unit_strategy == "unit":
        for row in working:
            for column in numeric_columns:
                raw = row.get(column)
                if raw is None:
                    continue
                parsed = _try_parse_unit_value(raw)
                if parsed is not None:
                    diag.n_values_unit_parsed += 1
                    row[column] = parsed
                else:
                    diag.n_unit_parse_failures += 1

    # --- 4. Missing-value handling ---------------------------------------------
    fill_columns = numeric_columns or list(all_columns)
    missing_before = sum(
        1 for row in working for c in fill_columns if row.get(c) in (None, "")
    )
    diag.n_missing_cells_before = missing_before

    if config.miss_strategy == "drop":
        working = [
            row for row in working
            if all(row.get(c) not in (None, "") for c in fill_columns)
        ]
        diag.n_rows_dropped_for_missing = diag.n_input_rows - len(working)
    else:
        for column in fill_columns:
            observed = [row[column] for row in working if row.get(column) not in (None, "")]
            numeric_observed = [v for v in observed if isinstance(v, (int, float))]
            fill_value: Any = None
            if config.miss_strategy == "mean" and numeric_observed:
                fill_value = statistics.mean(numeric_observed)
            elif config.miss_strategy == "median" and numeric_observed:
                fill_value = statistics.median(numeric_observed)
            elif config.miss_strategy == "mode" and observed:
                fill_value = Counter(observed).most_common(1)[0][0]
            elif config.miss_strategy == "constant":
                fill_value = config.missing_constant
            elif config.miss_strategy == "llm" and llm_fill_fn is not None:
                fill_value = None  # resolved per-row below
            for row in working:
                if row.get(column) in (None, ""):
                    if config.miss_strategy == "llm" and llm_fill_fn is not None:
                        row[column] = llm_fill_fn(table_name, column)
                    elif fill_value is not None:
                        row[column] = fill_value

    diag.n_output_rows = len(working)
    missing_after = sum(
        1 for row in working for c in fill_columns if row.get(c) in (None, "")
    )
    diag.n_missing_cells_after = missing_after

    for column in all_columns:
        non_null = sum(1 for row in working if row.get(column) not in (None, ""))
        diag.column_coverage[column] = non_null / len(working) if working else 0.0

    logger.info(
        "apply_population table=%s config=%s rows %d->%d merges=%d norm=%d units=%d",
        table_name,
        config.config_id,
        diag.n_input_rows,
        diag.n_output_rows,
        diag.n_entity_merges,
        diag.n_values_normalized,
        diag.n_values_unit_parsed,
    )
    return working, diag

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
import json
import hashlib
import logging
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional

from json_repair import repair_json

from spp.population_config import PopulationConfig
from token_counter import TokenBudgetExceeded

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
    n_values_type_coerced: int = 0
    n_type_coercion_failures: int = 0
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
            self.n_values_unit_parsed
            / (self.n_values_unit_parsed + self.n_unit_parse_failures)
            if self.n_values_unit_parsed + self.n_unit_parse_failures
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
_NULL_STRINGS = {"", "null", "none", "nan", "n/a", "na"}
_NUMERIC_TOKEN_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
_BOOKKEEPING_COLUMNS = {"row_id", "created_at", "updated_at"}


def repair_join_columns_from_overlap(
    left_rows: List[Dict[str, Any]],
    left_column: str,
    right_rows: List[Dict[str, Any]],
    right_column: str,
    *,
    left_table: str = "",
    right_table: str = "",
) -> Optional[tuple[str, str]]:
    """Repair a non-overlapping join using populated source columns.

    The query-facing column names stay stable; only their values are rebound
    to the strongest observed cross-table value overlap.
    """

    def values(rows: List[Dict[str, Any]], column: str) -> set[str]:
        return {
            re.sub(r"\s+", " ", str(row[column]).strip()).casefold()
            for row in rows
            if row.get(column) not in (None, "")
        }

    def columns(rows: List[Dict[str, Any]]) -> set[str]:
        return {
            column
            for row in rows
            for column in row
            if column not in _BOOKKEEPING_COLUMNS
        }

    def score(left: set[str], right: set[str]) -> tuple[float, int]:
        overlap = len(left & right)
        denominator = min(len(left), len(right))
        return (
            overlap / denominator if denominator else 0.0,
            overlap,
        )

    current_score, current_overlap = score(
        values(left_rows, left_column),
        values(right_rows, right_column),
    )
    if current_overlap and current_score >= 0.25:
        return None

    candidates = []
    for candidate_left in columns(left_rows):
        left_values = values(left_rows, candidate_left)
        if not left_values:
            continue
        for candidate_right in columns(right_rows):
            left_tokens = set(candidate_left.casefold().split("_"))
            right_tokens = set(candidate_right.casefold().split("_"))
            names_align = bool(
                left_tokens & right_tokens
                or right_table.casefold() in left_tokens
                or left_table.casefold() in right_tokens
            )
            if not names_align:
                continue
            right_values = values(right_rows, candidate_right)
            overlap_score, overlap_count = score(left_values, right_values)
            candidates.append(
                (
                    overlap_score,
                    overlap_count,
                    candidate_left == left_column,
                    candidate_right == right_column,
                    candidate_left,
                    candidate_right,
                )
            )
    best = max(candidates, default=None)
    if best is None or best[0] < 0.5 or best[1] < 2:
        return None
    _, _, _, _, source_left, source_right = best
    if (source_left, source_right) == (left_column, right_column):
        return None
    for row in left_rows:
        if row.get(source_left) not in (None, ""):
            row[left_column] = row[source_left]
    for row in right_rows:
        if row.get(source_right) not in (None, ""):
            row[right_column] = row[source_right]
    return source_left, source_right


def _parse_llm_json(response: str, expected_type: type) -> Any:
    """Parse the first expected JSON value, repairing malformed LLM syntax."""
    opener = "[" if expected_type is list else "{"
    decoder = json.JSONDecoder()
    for match in re.finditer(re.escape(opener), response):
        candidate = response[match.start() :]
        try:
            value, _end = decoder.raw_decode(candidate)
            if isinstance(value, expected_type):
                return value
        except json.JSONDecodeError:
            continue
    start = response.find(opener)
    if start < 0:
        raise ValueError(f"LLM response contains no {expected_type.__name__}")
    repaired = repair_json(response[start:], return_objects=True)
    if not isinstance(repaired, expected_type):
        raise ValueError(
            f"repaired LLM response is not a {expected_type.__name__}"
        )
    return repaired


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


def _strict_numeric(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip().replace(",", "")
    if text.lower() in _NULL_STRINGS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _permissive_numeric(value: Any) -> Optional[float]:
    strict = _strict_numeric(value)
    if strict is not None:
        return strict
    text = str(value).strip().replace(",", "")
    match = _NUMERIC_TOKEN_PATTERN.search(text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _llm_numeric_mapping(
    table_name: str,
    column: str,
    values: List[Any],
    llm_client: Any,
) -> Dict[str, Optional[float]]:
    unique = list(dict.fromkeys(str(v) for v in values))[:100]
    if not unique:
        return {}
    prompt = (
        f"Parse the following values from numeric column {table_name}.{column}. "
        "Return ONLY a JSON object mapping each exact original string to a "
        "number or null.\nValues: "
        f"{json.dumps(unique, ensure_ascii=False)}"
    )
    try:
        response = llm_client.generate(prompt, max_tokens=500, temperature=0.0)
        raw = _parse_llm_json(response, dict)
        result: Dict[str, Optional[float]] = {}
        for key, value in raw.items():
            result[str(key)] = _strict_numeric(value)
        return result
    except TokenBudgetExceeded:
        raise
    except Exception as exc:
        logger.warning(
            "LLM type coercion failed for %s.%s: %s", table_name, column, exc
        )
        return {}


def _cheap_cluster_values(
    values: List[str], threshold: float
) -> Dict[str, str]:
    """Dependency-free entity clustering via SequenceMatcher ratio.

    Stands in for embedding-based blocking in "cheap" mode. Returns a
    mention -> canonical map (canonical = most frequent member of cluster).
    """
    unique_values = sorted({v for v in values if v})
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


def _llm_cluster_values(
    values: List[str], llm_client: Any, *, batch_size: int = 40
) -> Dict[str, str]:
    """Genuinely LLM-driven entity clustering for er_strategy="llm": no
    embedding blocking / cross-encoder matching at all, matching the
    problem statement's `Cer = {embedding, llm}` dichotomy (these are meant
    to be two DIFFERENT resolution mechanisms, not the same embedding
    pipeline with the canonicalization step reused). The LLM is asked
    directly which of a batch of values are the same real-world entity.

    Batches to keep prompts bounded; unique values are batched by
    insertion order (batch_size at a time), so within-batch duplicates are
    still caught even though cross-batch duplicates may be missed -- an
    accepted approximation given no embedding pre-blocking is used here.
    """
    unique_values = sorted({v for v in values if v})
    if len(unique_values) < 2:
        return {}

    canonical_map: Dict[str, str] = {}
    counts = Counter(values)

    for start in range(0, len(unique_values), batch_size):
        batch = unique_values[start : start + batch_size]
        if len(batch) < 2:
            continue
        numbered = "\n".join(f"{i}: {v}" for i, v in enumerate(batch))
        prompt = (
            "Below is a numbered list of values. Group together any values "
            "that refer to the SAME real-world entity (e.g. spelling "
            "variants, abbreviations, alternate names). Respond with ONLY a "
            "JSON list of groups, where each group is a list of the integer "
            "indices that belong together. Only include groups with 2 or "
            "more indices (omit singletons).\n\n"
            f"{numbered}\n\nJSON:"
        )
        try:
            response = llm_client.generate(prompt, max_tokens=500, temperature=0.0)
            groups = _parse_llm_json(response, list)
        except TokenBudgetExceeded:
            raise
        except Exception as exc:
            logger.warning("LLM entity clustering batch failed, skipping merges: %s", exc)
            continue

        for group in groups:
            try:
                members = [batch[i] for i in group if isinstance(i, int) and 0 <= i < len(batch)]
            except (TypeError, IndexError):
                continue
            if len(members) < 2:
                continue
            canonical = max(members, key=lambda v: counts.get(v, 0))
            for member in members:
                if member != canonical:
                    canonical_map[member] = canonical

    return canonical_map


def _llm_normalize_values(
    values: List[str],
    llm_client: Any,
    *,
    table_name: str = "",
    column: str = "",
    allow_abstraction: bool = False,
    workload_hint: str = "",
    source_context: str = "",
    batch_size: int = 100,
) -> Dict[str, str]:
    """Normalize unique values in bounded JSON-mapping batches."""
    unique = sorted({v for v in values if v.strip()})
    mapping: Dict[str, str] = {}
    for start in range(0, len(unique), batch_size):
        batch = unique[start : start + batch_size]
        if allow_abstraction:
            context_section = (
                f"\nRelevant source excerpts:\n{source_context[:4000]}"
                if source_context
                else ""
            )
            workload_section = (
                f"\nNatural-language grouping requests:\n{workload_hint}"
                if workload_hint
                else ""
            )
            prompt = (
                "Induce a source-grounded categorical normalization for a "
                "workload GROUP BY column. Map spelling/case variants together. "
                "When the observed values are conventional fine-grained subtypes "
                "of parent labels that also occur in the observed values or source "
                "excerpts, map them to the smallest coherent source-supported parent "
                "set. If the values already match the semantic level named by the "
                "grouping request, preserve their granularity. Do not replace "
                "peer categories with an unrequested broader taxonomy. Never "
                "invent facts about individual "
                "rows and never "
                "use benchmark schemas or expected answers. Return ONLY a JSON "
                "object mapping every exact original string to one canonical "
                f"category.\nColumn: {table_name}.{column}\n"
                f"Source-observed values: {json.dumps(batch, ensure_ascii=False)}"
                f"{workload_section}"
                f"{context_section}"
            )
        else:
            prompt = (
                "Normalize each string to a canonical form (trimmed, collapsed "
                "whitespace, consistent casing and spelling). Return ONLY a JSON "
                "object mapping every exact original string to its normalized "
                f"form.\nValues: {json.dumps(batch, ensure_ascii=False)}"
            )
        try:
            response = llm_client.generate(prompt, max_tokens=1000, temperature=0.0)
            raw = _parse_llm_json(response, dict)
            for value in batch:
                normalized = str(
                    raw.get(value, _dictionary_normalize(value))
                ).strip()
                if allow_abstraction and normalized:
                    supported = (
                        normalized.casefold()
                        in {item.casefold() for item in unique}
                        or normalized.casefold()
                        in source_context.casefold()
                    )
                    if not supported:
                        normalized = _dictionary_normalize(value)
                mapping[value] = normalized or _dictionary_normalize(value)
        except TokenBudgetExceeded:
            raise
        except Exception as exc:
            logger.warning("LLM normalization batch failed: %s", exc)
            mapping.update({value: _dictionary_normalize(value) for value in batch})
    return mapping


def _llm_choose_fill_value(
    table_name: str, column: str, observed: List[Any], llm_client: Any
) -> Optional[Any]:
    """Ask the LLM to pick a single representative fill value for a column,
    given a sample of its observed non-null values. This is one LLM call
    per (table, column) per config -- not per row -- and is meant to be a
    more semantically-aware alternative to raw-frequency "mode" (e.g.
    preferring a sensible representative category over a noisy outlier
    that happens to repeat), matching the problem statement's Cmiss={llm}
    option. Falls back to raw mode on any LLM failure or empty response.
    """
    if not observed:
        return None
    sample = observed[:30]
    sample_str = "\n".join(f"- {v}" for v in sample)
    prompt = (
        f"Column '{column}' in table '{table_name}' has these observed "
        f"values:\n{sample_str}\n\n"
        "Some rows are missing a value for this column. Suggest the single "
        "most reasonable fill-in value for this column, based on the "
        "pattern above (e.g. the most common category, or a sensible "
        "default). Respond with ONLY the value, nothing else."
    )
    try:
        response = llm_client.generate(prompt, max_tokens=30, temperature=0.0)
        response = response.strip()
        if response:
            return response
    except TokenBudgetExceeded:
        raise
    except Exception as exc:
        logger.warning("LLM fill-value selection failed for %s.%s: %s", table_name, column, exc)
    return Counter(observed).most_common(1)[0][0]


def _resolve_entities_for_column(
    records: List[Dict[str, Any]],
    column: str,
    config: PopulationConfig,
    entity_resolver: Optional[Any],
    semantic_type: str,
    llm_client: Optional[Any] = None,
    llm_cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Returns mention -> canonical map for one column, respecting the
    configured er_strategy. Uses rich EntityResolver when supplied, else
    the cheap SequenceMatcher heuristic. `llm_client` is required for a
    genuine er_strategy="llm" path (see `_llm_cluster_values`); without it,
    "llm" falls back to the cheap heuristic at a permissive threshold.
    """
    values = [str(r[column]) for r in records if r.get(column) not in (None, "")]
    if len(values) < 2:
        return {}

    if config.er_strategy == "llm":
        if llm_client is not None:
            payload = json.dumps(
                sorted(set(values)), ensure_ascii=False, separators=(",", ":")
            )
            cache_key = f"{column}:{hashlib.sha256(payload.encode()).hexdigest()}"
            cache_root = llm_cache if llm_cache is not None else {}
            er_cache = cache_root.setdefault("entity_resolution", {})
            if cache_key not in er_cache:
                er_cache[cache_key] = _llm_cluster_values(values, llm_client)
            return dict(er_cache[cache_key])
        return _cheap_cluster_values(values, threshold=0.6)

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
        result = entity_resolver.resolve_entities(
            mentions,
            semantic_type=semantic_type,
            bi_encoder_threshold=config.er_threshold,
            use_llm_canonicalization=False,
        )
        return dict(result.canonical_map)

    # Cheap mode fallback (no real EntityResolver supplied).
    return _cheap_cluster_values(values, config.er_threshold)


def apply_population(
    records: List[Dict[str, Any]],
    config: PopulationConfig,
    *,
    table_name: str = "",
    column_semantic_types: Optional[Dict[str, str]] = None,
    identity_columns: Optional[List[str]] = None,
    numeric_columns: Optional[List[str]] = None,
    protected_columns: Optional[List[str]] = None,
    abstraction_columns: Optional[List[str]] = None,
    abstraction_hints: Optional[Dict[str, str]] = None,
    source_context: str = "",
    entity_resolver: Optional[Any] = None,
    llm_client: Optional[Any] = None,
    llm_normalize_fn: Optional[Callable[[str], str]] = None,
    llm_fill_fn: Optional[Callable[[str, str], Any]] = None,
    llm_cache: Optional[Dict[str, Any]] = None,
) -> "tuple[List[Dict[str, Any]], PopulationDiagnostics]":
    """Apply one PopulationConfig to already-extracted records.

    Order matches the problem statement's composition:
        pop = f_miss ∘ f_unit ∘ f_type ∘ f_norm ∘ f_er
    i.e. entity resolution first, then normalization, then unit parsing,
    then (implicit type coercion), then missing-value handling last.
    """
    column_semantic_types = column_semantic_types or {}
    protected_columns = protected_columns or []
    abstraction_columns = abstraction_columns or []
    abstraction_hints = abstraction_hints or {}
    if identity_columns is None:
        identity_columns = [
            c
            for c, t in column_semantic_types.items()
            if str(t).upper() in ("PERSON", "ORG", "GPE")
        ]
    if numeric_columns is None:
        numeric_columns = [
            c
            for c, t in column_semantic_types.items()
            if str(t).upper()
            in ("MONEY", "QUANTITY", "QUANTITY_COUNT", "INTEGER", "REAL")
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
            working,
            column,
            config,
            entity_resolver,
            semantic_type,
            llm_client=llm_client,
            llm_cache=llm_cache,
        )
        if canonical_map:
            diag.n_entity_merges += len(canonical_map)
            for row in working:
                if column not in row or row[column] in (None, ""):
                    continue
                raw_value = str(row[column])
                canonical = canonical_map.get(raw_value)
                if canonical is None:
                    canonical = canonical_map.get(raw_value.lower().strip())
                if canonical is not None:
                    row[column] = canonical

    # --- 2. Value normalization ----------------------------------------------
    all_columns = {k for r in working for k in r.keys()}
    data_columns = all_columns - _BOOKKEEPING_COLUMNS
    taxonomy_by_column: Dict[str, Dict[str, str]] = {}
    if llm_client is not None:
        cache_root = llm_cache if llm_cache is not None else {}
        taxonomy_cache = cache_root.setdefault("taxonomy", {})
        for column in set(abstraction_columns) & data_columns:
            values = [
                str(row[column])
                for row in working
                if isinstance(row.get(column), str) and row.get(column)
            ]
            unique = sorted(set(values))
            if len(unique) < 3:
                continue
            lowered_values = {
                value.casefold() for value in unique[:100]
            }
            context_lines = [
                line.strip()
                for line in source_context.splitlines()
                if any(
                    value in line.casefold()
                    for value in lowered_values
                )
            ]
            relevant_context = "\n".join(context_lines)[:4000]
            workload_hint = abstraction_hints.get(column, "")
            payload = json.dumps(
                unique, ensure_ascii=False, separators=(",", ":")
            )
            cache_key = (
                f"{table_name}.{column}:"
                f"{hashlib.sha256((payload + workload_hint + relevant_context).encode()).hexdigest()}"
            )
            if cache_key not in taxonomy_cache:
                taxonomy_cache[cache_key] = _llm_normalize_values(
                    values,
                    llm_client,
                    table_name=table_name,
                    column=column,
                    allow_abstraction=True,
                    workload_hint=workload_hint,
                    source_context=relevant_context,
                )
            candidate = dict(taxonomy_cache[cache_key])
            outputs = {
                str(candidate.get(value, value)).strip().casefold()
                for value in unique
            }
            if 2 <= len(outputs) <= math.floor(len(unique) * 0.7):
                taxonomy_by_column[column] = candidate

    normalized_by_column: Dict[str, Dict[str, str]] = {}
    if config.norm_strategy == "llm" and llm_normalize_fn is None and llm_client is not None:
        cache_root = llm_cache if llm_cache is not None else {}
        normalization_cache = cache_root.setdefault("normalization", {})
        for column in data_columns:
            values = [
                row[column]
                for row in working
                if isinstance(row.get(column), str) and row.get(column)
            ]
            payload = json.dumps(
                sorted(set(values)), ensure_ascii=False, separators=(",", ":")
            )
            cache_key = (
                f"{table_name}.{column}:"
                f"{hashlib.sha256(payload.encode()).hexdigest()}"
            )
            if cache_key not in normalization_cache:
                normalization_cache[cache_key] = _llm_normalize_values(
                    values,
                    llm_client,
                    table_name=table_name,
                    column=column,
                )
            normalized_by_column[column] = dict(normalization_cache[cache_key])
    for row in working:
        for column in data_columns:
            value = row.get(column)
            if not isinstance(value, str) or not value:
                continue
            taxonomy_value = taxonomy_by_column.get(column, {}).get(value)
            if taxonomy_value:
                normalized = taxonomy_value
            elif (
                column in protected_columns
                and column not in abstraction_columns
            ):
                normalized = _dictionary_normalize(value)
            elif config.norm_strategy == "llm" and llm_normalize_fn is not None:
                normalized = llm_normalize_fn(value)
            elif config.norm_strategy == "llm" and llm_client is not None:
                normalized = normalized_by_column.get(column, {}).get(
                    value, _dictionary_normalize(value)
                )
            else:
                normalized = _dictionary_normalize(value)
            # A normalizer may repair spelling, but case-only rewrites destroy
            # exact predicate and join keys without adding semantic evidence.
            cleaned_original = _dictionary_normalize(value)
            if (
                isinstance(normalized, str)
                and normalized.casefold() == cleaned_original.casefold()
            ):
                normalized = cleaned_original
            if normalized != value:
                diag.n_values_normalized += 1
                row[column] = normalized

    for column in set(abstraction_columns) & data_columns:
        observed = [
            _dictionary_normalize(row[column])
            for row in working
            if isinstance(row.get(column), str) and row.get(column)
        ]
        by_casefold: Dict[str, Counter[str]] = {}
        for value in observed:
            by_casefold.setdefault(value.casefold(), Counter())[value] += 1
        canonical_case = {
            key: max(
                counts,
                key=lambda value: (counts[value], -len(value), value),
            )
            for key, counts in by_casefold.items()
        }
        for row in working:
            value = row.get(column)
            if not isinstance(value, str) or not value:
                continue
            canonical = canonical_case.get(
                _dictionary_normalize(value).casefold()
            )
            if canonical is not None and canonical != value:
                row[column] = canonical
                diag.n_values_normalized += 1

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

    # --- 4. Type coercion ------------------------------------------------------
    for column in numeric_columns:
        unparseable: List[Any] = []
        for row in working:
            value = row.get(column)
            if value in (None, ""):
                continue
            parsed = _strict_numeric(value)
            if parsed is None:
                unparseable.append(value)

        llm_mapping: Dict[str, Optional[float]] = {}
        if config.type_coercion == "llm" and unparseable and llm_client is not None:
            payload = json.dumps(
                sorted({str(v) for v in unparseable}),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            cache_key = (
                f"{table_name}.{column}:"
                f"{hashlib.sha256(payload.encode()).hexdigest()}"
            )
            cache_root = llm_cache if llm_cache is not None else {}
            coercion_cache = cache_root.setdefault("type_coercion", {})
            if cache_key not in coercion_cache:
                coercion_cache[cache_key] = _llm_numeric_mapping(
                    table_name, column, unparseable, llm_client
                )
            llm_mapping = dict(coercion_cache[cache_key])

        for row in working:
            value = row.get(column)
            if value in (None, ""):
                continue
            if config.type_coercion == "strict":
                parsed = _strict_numeric(value)
            elif config.type_coercion == "permissive":
                parsed = _permissive_numeric(value)
            else:
                parsed = _strict_numeric(value)
                if parsed is None:
                    parsed = llm_mapping.get(str(value))
                if parsed is None:
                    parsed = _permissive_numeric(value)
            if parsed is None:
                row[column] = None
                diag.n_type_coercion_failures += 1
            else:
                if parsed != value or not isinstance(value, (int, float)):
                    diag.n_values_type_coerced += 1
                row[column] = parsed

    # --- 5. Missing-value handling ---------------------------------------------
    # Never treat bookkeeping columns as data. Match spp-agent's sparse-table
    # semantics: "drop" removes only wholly empty semantic rows, rather than
    # listwise-deleting a useful entity because one optional attribute is null.
    candidate_columns = list(data_columns)
    mutable_columns = [
        column
        for column in candidate_columns
        if column not in set(protected_columns) | set(identity_columns)
    ]
    if config.miss_strategy in {"mean", "median"}:
        fill_columns = [
            column for column in numeric_columns if column in mutable_columns
        ]
    else:
        fill_columns = mutable_columns
    missing_before = sum(
        1 for row in working for c in candidate_columns if row.get(c) in (None, "")
    )
    diag.n_missing_cells_before = missing_before

    if config.miss_strategy == "drop":
        working = [
            row for row in working
            if any(row.get(c) not in (None, "") for c in candidate_columns)
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
            elif config.miss_strategy == "llm":
                if llm_fill_fn is not None:
                    fill_value = llm_fill_fn(table_name, column)
                elif llm_client is not None:
                    payload = json.dumps(
                        observed[:30], ensure_ascii=False, default=str
                    )
                    cache_key = (
                        f"{table_name}.{column}:"
                        f"{hashlib.sha256(payload.encode()).hexdigest()}"
                    )
                    cache_root = llm_cache if llm_cache is not None else {}
                    fill_cache = cache_root.setdefault("missing_fill", {})
                    if cache_key not in fill_cache:
                        fill_cache[cache_key] = _llm_choose_fill_value(
                            table_name, column, observed, llm_client
                        )
                    fill_value = fill_cache[cache_key]
                elif observed:
                    # No LLM available: fall back to mode rather than
                    # silently leaving cells empty (previous behavior was a
                    # no-op that made miss_strategy="llm" indistinguishable
                    # from doing nothing).
                    fill_value = Counter(observed).most_common(1)[0][0]
            for row in working:
                if row.get(column) in (None, "") and fill_value is not None:
                    row[column] = fill_value

    diag.n_output_rows = len(working)
    missing_after = sum(
        1 for row in working for c in candidate_columns if row.get(c) in (None, "")
    )
    diag.n_missing_cells_after = missing_after

    for column in data_columns:
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

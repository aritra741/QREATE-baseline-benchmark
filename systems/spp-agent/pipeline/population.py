from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from optimizer.config_space import PopulationConfig
from pipeline.extraction import ExtractionResult
from pipeline.schema import Schema
from pipeline.type_coercion import apply_type_coercion
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.population")

_EMBEDDER = None


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        logger.info("Loading sentence-transformer embedder all-MiniLM-L6-v2")
        from sentence_transformers import SentenceTransformer

        _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedder loaded")
    return _EMBEDDER


@dataclass
class PopulationDiagnostics:
    er_merge_count: int
    er_ambiguous_pairs: int
    norm_changes: int
    norm_entropy: float
    unit_parse_successes: int
    unit_parse_failures: int
    missing_before: int
    missing_after: int
    duplicate_rate: float


def _is_entity_column(col: str, dtype: str) -> bool:
    if dtype != "str":
        return False
    name = col.lower()
    return any(k in name for k in ("name", "team", "city", "owner", "college", "nationality", "location"))


def _is_numeric_column_type(dtype: str) -> bool:
    return dtype in {"int", "float", "numeric"}


def _is_categorical_column_type(dtype: str) -> bool:
    return dtype in {"str", "bool", "string", "categorical"}


def _dictionary_normalize(value: object) -> object:
    if not isinstance(value, str):
        return value
    text = value.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _mode_value_key(value: object) -> object:
    if isinstance(value, (list, dict)):
        import json

        return json.dumps(value, sort_keys=True, default=str)
    return value


def _column_mode_value(series: pd.Series) -> object | None:
    non_null = series.dropna()
    if non_null.empty:
        return None
    if pd.api.types.is_numeric_dtype(non_null):
        mode_val = non_null.mode(dropna=True)
        return None if mode_val.empty else mode_val.iloc[0]

    counts: Counter[object] = Counter()
    key_to_value: dict[object, object] = {}
    for value in non_null:
        key = _mode_value_key(value)
        counts[key] += 1
        key_to_value.setdefault(key, value)
    if not counts:
        return None
    return key_to_value[counts.most_common(1)[0][0]]


def _llm_normalize_values(values: list[str], model_name: str) -> dict[str, str]:
    from pipeline.llm_steps import llm_json_call
    from pipeline.llm_output_cache import get_norm_mapping, put_norm_mapping

    unique = sorted({v for v in values if isinstance(v, str) and v.strip()})
    if not unique:
        return {}

    cached = get_norm_mapping(model_name, unique)
    if cached is not None:
        return cached

    prompt = (
        "Normalize each string to a canonical form (lowercase, trimmed, collapsed whitespace). "
        "Return JSON mapping original -> normalized.\n"
        f"Values: {json_dumps_safe(unique[:100])}"
    )
    mapping = llm_json_call(model_name, prompt)
    if mapping is not None:
        result = {str(k): str(v) for k, v in mapping.items()}
        put_norm_mapping(model_name, unique, result)
        return result
    fallback = {v: _dictionary_normalize(v) for v in unique}
    put_norm_mapping(model_name, unique, fallback)
    return fallback


def _llm_entity_mapping(values: list[str], model_name: str) -> dict[str, str]:
    from pipeline.llm_steps import llm_json_call
    from pipeline.llm_output_cache import cache_key, get_cached_json, put_cached_json

    unique = sorted({v for v in values if isinstance(v, str) and v.strip()})
    if not unique:
        return {}
    key = cache_key(model_name, "er", unique)
    cached = get_cached_json("er", key)
    if isinstance(cached, dict):
        return {str(k): str(v) for k, v in cached.items()}

    prompt = (
        "Cluster synonymous entity names. Return JSON mapping each original name "
        "to a canonical form.\n"
        f"Values: {json_dumps_safe(unique[:100])}"
    )
    mapping = llm_json_call(model_name, prompt)
    if mapping is not None:
        result = {str(k): str(v) for k, v in mapping.items()}
        put_cached_json("er", key, result)
        return result
    fallback = {v: v for v in unique}
    put_cached_json("er", key, fallback)
    return fallback


def _canonicalize_entities(
    values: list[str],
    *,
    er_strategy: str,
    threshold: float,
    model_name: str,
) -> tuple[list[str], int, int]:
    if er_strategy == "llm":
        mapping = _llm_entity_mapping(values, model_name)
        canonical = [mapping.get(v, v) if isinstance(v, str) else v for v in values]
        unique_in = len({v for v in values if isinstance(v, str) and v.strip()})
        unique_out = len({v for v in canonical if isinstance(v, str) and v.strip()})
        return canonical, max(0, unique_in - unique_out), 0
    return _merge_entities(values, threshold)


def _coerce_imputed_value(value: object, dtype: str) -> object:
    if value is None:
        return np.nan
    if isinstance(value, float) and math.isnan(value):
        return np.nan
    if dtype in {"int", "float", "numeric"}:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value if dtype == "int" else float(value)
        if isinstance(value, float):
            return int(value) if dtype == "int" and value == int(value) else value
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if not text:
                return np.nan
            try:
                num = float(text)
                return int(num) if dtype == "int" and num == int(num) else num
            except ValueError:
                return np.nan
        return np.nan
    if dtype == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.strip().lower()
            if low in {"true", "1", "yes"}:
                return True
            if low in {"false", "0", "no"}:
                return False
        return bool(value)
    if isinstance(value, str):
        return value
    return str(value)


def _apply_llm_imputation(
    df: pd.DataFrame,
    table: str,
    col_types: dict[str, str],
    model_name: str,
) -> None:
    import json

    from pipeline.llm_output_cache import cache_key, get_cached_json, put_cached_json
    from pipeline.llm_steps import llm_json_call

    if df.empty:
        return

    rows_payload = json.loads(df.replace({np.nan: None}).to_json(orient="records"))
    for col in df.columns:
        if col == "id":
            continue
        missing_idx = [
            i
            for i, v in enumerate(df[col].tolist())
            if v is None
            or (isinstance(v, float) and math.isnan(v))
            or (isinstance(v, str) and not str(v).strip())
        ]
        if not missing_idx:
            continue

        dtype = col_types.get(col, "str")
        key = cache_key(model_name, "miss", table, col, dtype, rows_payload)
        cached = get_cached_json("miss", key)
        if not isinstance(cached, dict):
            prompt = (
                f"Impute missing values for table {table}, column {col} (type {dtype}).\n"
                f"Rows: {json_dumps_safe(rows_payload[:80])}\n"
                f"Missing row indices: {missing_idx}\n"
                "Return JSON mapping row index (as string) -> imputed value."
            )
            cached = llm_json_call(model_name, prompt) or {}
            put_cached_json("miss", key, cached)

        for idx_s, value in cached.items():
            try:
                idx = int(idx_s)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(df):
                coerced = _coerce_imputed_value(value, dtype)
                if pd.api.types.is_string_dtype(df[col]) or (
                    not pd.api.types.is_numeric_dtype(df[col])
                    and dtype not in {"int", "float", "numeric"}
                ):
                    if coerced is None or (
                        isinstance(coerced, float) and math.isnan(coerced)
                    ):
                        df.at[idx, col] = np.nan
                    else:
                        df.at[idx, col] = str(coerced)
                else:
                    df.at[idx, col] = coerced


def json_dumps_safe(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


_UNIT_RE = re.compile(r"^[\s$]*(-?\d+(?:\.\d+)?)\s*([a-zA-Z%]+)?[\s]*$")


def _parse_unit(value: object) -> tuple[object, bool]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return value, False
    if isinstance(value, (int, float)):
        return value, True
    if not isinstance(value, str):
        return value, False
    text = value.strip().replace(",", "")
    match = _UNIT_RE.match(text)
    if match:
        num = float(match.group(1))
        if num.is_integer():
            return int(num), True
        return num, True
    try:
        return float(text), True
    except ValueError:
        return value, False


def _merge_entities(values: list[str], threshold: float) -> tuple[list[str], int, int]:
    if len(values) <= 1:
        return values, 0, 0

    embedder = _get_embedder()
    embeddings = embedder.encode(values, normalize_embeddings=True)
    parent = list(range(len(values)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    merges = 0
    ambiguous = 0
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            sim = float(np.dot(embeddings[i], embeddings[j]))
            if sim >= threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
                    merges += 1
                else:
                    ambiguous += 1

    clusters: dict[int, list[int]] = {}
    for idx in range(len(values)):
        root = find(idx)
        clusters.setdefault(root, []).append(idx)

    canonical = values[:]
    for members in clusters.values():
        rep = members[0]
        rep_val = values[rep]
        for m in members:
            canonical[m] = rep_val
    return canonical, merges, ambiguous


def _unique_nonempty_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if isinstance(v, str) and v.strip()))


def _shared_er_mapping(
    values: list[str],
    *,
    er_strategy: str,
    threshold: float,
    model_name: str,
) -> tuple[dict[str, str], int, int]:
    unique = _unique_nonempty_strings(values)
    if not unique:
        return {}, 0, 0
    if len(unique) == 1:
        return {unique[0]: unique[0]}, 0, 0
    canonical, merges, ambiguous = _canonicalize_entities(
        unique,
        er_strategy=er_strategy,
        threshold=threshold,
        model_name=model_name,
    )
    return dict(zip(unique, canonical)), merges, ambiguous


def _apply_cross_table_join_er(
    db: dict[str, pd.DataFrame],
    schema: Schema,
    *,
    er_strategy: str,
    threshold: float,
    model_name: str,
) -> tuple[set[tuple[str, str]], int, int]:
    """Run ER jointly on pooled join-key values; return handled (table, col) pairs."""
    handled: set[tuple[str, str]] = set()
    er_merges = 0
    er_ambiguous = 0

    for left_table, left_col, right_table, right_col in schema.join_keys:
        left_df = db.get(left_table)
        right_df = db.get(right_table)
        if left_df is None or right_df is None:
            continue
        if left_col not in left_df.columns or right_col not in right_df.columns:
            continue

        left_dtype = schema.column_types.get(left_table, {}).get(left_col, "str")
        right_dtype = schema.column_types.get(right_table, {}).get(right_col, "str")
        if not _is_entity_column(left_col, left_dtype) or not _is_entity_column(
            right_col, right_dtype
        ):
            continue

        left_vals = left_df[left_col].fillna("").astype(str).tolist()
        right_vals = right_df[right_col].fillna("").astype(str).tolist()
        mapping, merges, ambiguous = _shared_er_mapping(
            left_vals + right_vals,
            er_strategy=er_strategy,
            threshold=threshold,
            model_name=model_name,
        )
        if not mapping:
            continue

        for df, col in ((left_df, left_col), (right_df, right_col)):
            str_vals = df[col].fillna("").astype(str).tolist()
            df[col] = [mapping.get(v, v) for v in str_vals]
        handled.add((left_table, left_col))
        handled.add((right_table, right_col))
        er_merges += merges
        er_ambiguous += ambiguous

    return handled, er_merges, er_ambiguous


def join_key_exact_overlap(
    db: dict[str, pd.DataFrame],
    left_table: str,
    left_col: str,
    right_table: str,
    right_col: str,
) -> float:
    """Exact string intersection over the union of unique join-key values."""
    left_df = db.get(left_table)
    right_df = db.get(right_table)
    if left_df is None or right_df is None:
        return 0.0
    if left_col not in left_df.columns or right_col not in right_df.columns:
        return 0.0

    def _value_set(df: pd.DataFrame, col: str) -> set[str]:
        return {
            str(v).strip()
            for v in df[col].tolist()
            if v is not None and not (isinstance(v, float) and math.isnan(v)) and str(v).strip()
        }

    left_values = _value_set(left_df, left_col)
    right_values = _value_set(right_df, right_col)
    union = left_values | right_values
    if not union:
        return 0.0
    return len(left_values & right_values) / len(union)


def _flatten_unhashable_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Stringify any list/dict values left behind by the LLM so that all
    downstream pandas operations (drop_duplicates, mode, factorize …) work on
    hashable scalars only."""
    import json as _json

    for col in df.columns:
        if df[col].dtype == object:
            def _coerce(v):
                if isinstance(v, (list, dict)):
                    return _json.dumps(v, ensure_ascii=False)
                return v

            df[col] = df[col].map(_coerce)
    return df


def _tuples_to_dataframe(
    extraction: ExtractionResult,
    schema: Schema,
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for table, cols in schema.tables.items():
        rows = extraction.tuples_by_table.get(table, [])
        if not rows:
            frames[table] = pd.DataFrame(columns=cols)
            continue
        df = pd.DataFrame(rows)
        for col in cols:
            if col not in df.columns:
                df[col] = np.nan
        keep = [c for c in cols if c in df.columns]
        if "id" in df.columns and "id" not in keep:
            keep = ["id"] + keep
        df = _flatten_unhashable_cells(df[keep] if keep else df)
        frames[table] = df
    return frames


def apply_population(
    extraction: ExtractionResult,
    config: PopulationConfig,
    schema: Schema,
    *,
    extraction_model: str | None = None,
    cross_table_join_er: bool = True,
) -> tuple[dict[str, pd.DataFrame], PopulationDiagnostics]:
    cfg = load_config()
    model = extraction_model or cfg["llm"]["extraction_model"]

    logger.debug(
        "apply_population config=%s er=%s norm=%s unit=%s miss=%s",
        config.config_id,
        config.er_strategy,
        config.norm_strategy,
        config.unit_strategy,
        config.miss_strategy,
    )

    db = _tuples_to_dataframe(extraction, schema)
    er_merges = 0
    er_ambiguous = 0
    norm_changes = 0
    norm_values: list[str] = []
    unit_success = 0
    unit_fail = 0
    missing_before = 0
    missing_after = 0

    threshold = {
        "embedding_0.7": 0.7,
        "embedding_0.8": 0.8,
        "embedding_0.9": 0.9,
        "llm": 0.9,
    }.get(config.er_strategy, 0.9)

    cross_table_join_columns: set[tuple[str, str]] = set()
    if cross_table_join_er and schema.join_keys:
        cross_table_join_columns, cross_merges, cross_ambiguous = _apply_cross_table_join_er(
            db,
            schema,
            er_strategy=config.er_strategy,
            threshold=threshold,
            model_name=model,
        )
        er_merges += cross_merges
        er_ambiguous += cross_ambiguous

    for table, df in db.items():
        if df.empty:
            continue
        col_types = schema.column_types.get(table, {})

        for col in df.columns:
            if col == "id":
                continue
            series = df[col]
            missing_before += int(series.isna().sum()) + int((series.astype(str).str.strip() == "").sum())

            if (table, col) in cross_table_join_columns:
                pass
            elif _is_entity_column(col, col_types.get(col, "str")):
                str_vals = series.fillna("").astype(str).tolist()
                merged, m, a = _canonicalize_entities(
                    str_vals,
                    er_strategy=config.er_strategy,
                    threshold=threshold,
                    model_name=model,
                )
                er_merges += m
                er_ambiguous += a
                df[col] = merged

            if config.norm_strategy == "dictionary":
                new_vals = [_dictionary_normalize(v) for v in df[col].tolist()]
            else:
                mapping = _llm_normalize_values(df[col].astype(str).tolist(), model)
                new_vals = [mapping.get(str(v), _dictionary_normalize(v)) for v in df[col].tolist()]

            for old, new in zip(df[col].tolist(), new_vals):
                if str(old) != str(new):
                    norm_changes += 1
                if isinstance(new, str):
                    norm_values.append(new)
            df[col] = new_vals

            if config.unit_strategy == "unit" and col_types.get(col, "str") in {
                "int",
                "float",
                "numeric",
            }:
                parsed_col = []
                for v in df[col].tolist():
                    parsed, ok = _parse_unit(v)
                    parsed_col.append(parsed)
                    if ok:
                        unit_success += 1
                    else:
                        unit_fail += 1
                df[col] = parsed_col

        if config.miss_strategy == "drop":
            # Sparse extraction leaves many null optional columns; drop only fully empty rows.
            if not df.empty:
                df.dropna(how="all", inplace=True)
        elif config.miss_strategy == "mean":
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(df[col].mean())
        elif config.miss_strategy == "llm":
            _apply_llm_imputation(df, table, col_types, model)
        elif config.miss_strategy == "median":
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(df[col].median())
        elif config.miss_strategy == "mode":
            for col in df.columns:
                if df[col].empty:
                    continue
                mode_value = _column_mode_value(df[col])
                if mode_value is None or (
                    isinstance(mode_value, float) and math.isnan(mode_value)
                ):
                    continue
                df[col] = df[col].fillna(mode_value)
        elif config.miss_strategy == "constant":
            for col in df.columns:
                if col == "id":
                    continue
                dtype = col_types.get(col, "str")
                if _is_numeric_column_type(dtype) or pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(0)
                elif _is_categorical_column_type(dtype):
                    # Leave NULL — do not insert numeric sentinels into GROUP BY keys.
                    continue
                else:
                    df[col] = df[col].fillna(0)

        missing_after += int(df.isna().sum().sum())

    db = apply_type_coercion(
        db,
        schema,
        config.type_coercion,
        model_name=model,
    )

    # duplicate rate across all tables
    total_rows = sum(len(df) for df in db.values())
    dup_rows = 0
    for df in db.values():
        if len(df) > 1:
            dup_rows += len(df) - len(df.drop_duplicates())
    duplicate_rate = dup_rows / total_rows if total_rows else 0.0

    if norm_values:
        counts = Counter(norm_values)
        total = sum(counts.values())
        entropy = -sum((c / total) * math.log(c / total + 1e-12) for c in counts.values())
    else:
        entropy = 0.0

    diagnostics = PopulationDiagnostics(
        er_merge_count=er_merges,
        er_ambiguous_pairs=er_ambiguous,
        norm_changes=norm_changes,
        norm_entropy=float(entropy),
        unit_parse_successes=unit_success,
        unit_parse_failures=unit_fail,
        missing_before=missing_before,
        missing_after=missing_after,
        duplicate_rate=float(duplicate_rate),
    )
    return db, diagnostics

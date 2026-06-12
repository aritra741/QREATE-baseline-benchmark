"""Schema type coercion before DuckDB materialization."""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from pipeline.schema import Schema
from utils.logging import setup_logger

logger = setup_logger("spp.type_coercion")

_NULL_STRINGS = frozenset({"", "null", "none", "nan", "n/a", "na"})
_NUMERIC_TOKEN_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _is_null_like(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().lower() in _NULL_STRINGS:
        return True
    return False


def _cast_strict_int(value: object) -> object:
    if _is_null_like(value):
        return np.nan
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return np.nan
        if value == int(value):
            return int(value)
        return np.nan
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.lower() in _NULL_STRINGS:
            return np.nan
        try:
            num = float(text)
            if num == int(num):
                return int(num)
            return np.nan
        except ValueError:
            return np.nan
    return np.nan


def _cast_strict_float(value: object) -> object:
    if _is_null_like(value):
        return np.nan
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return np.nan
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.lower() in _NULL_STRINGS:
            return np.nan
        try:
            return float(text)
        except ValueError:
            return np.nan
    return np.nan


def _extract_numeric_token(text: str) -> str | None:
    """Pull the first numeric literal from a messy string (e.g. 'pick 12' -> '12')."""
    cleaned = text.strip().replace(",", "")
    if cleaned.lower() in _NULL_STRINGS:
        return None
    match = _NUMERIC_TOKEN_RE.search(cleaned)
    return match.group(0) if match else None


def _cast_permissive_int(value: object) -> object:
    if _is_null_like(value):
        return np.nan
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return np.nan
        return int(value)
    if isinstance(value, str):
        token = _extract_numeric_token(value)
        if token is None:
            return np.nan
        try:
            return int(float(token))
        except ValueError:
            return np.nan
    return np.nan


def _cast_permissive_float(value: object) -> object:
    if _is_null_like(value):
        return np.nan
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return np.nan
        return float(value)
    if isinstance(value, str):
        token = _extract_numeric_token(value)
        if token is None:
            return np.nan
        try:
            return float(token)
        except ValueError:
            return np.nan
    return np.nan


def _coerce_column_permissive(series: pd.Series, dtype: str) -> pd.Series:
    if dtype == "int":
        casted = [_cast_permissive_int(v) for v in series.tolist()]
        return pd.array(casted, dtype=pd.Int64Dtype())
    if dtype in {"float", "numeric"}:
        casted = [_cast_permissive_float(v) for v in series.tolist()]
        return pd.to_numeric(pd.Series(casted), errors="coerce")
    return series


def _coerce_column_strict(series: pd.Series, dtype: str) -> pd.Series:
    if dtype == "int":
        casted = [_cast_strict_int(v) for v in series.tolist()]
        return pd.array(casted, dtype=pd.Int64Dtype())
    if dtype in {"float", "numeric"}:
        casted = [_cast_strict_float(v) for v in series.tolist()]
        return pd.to_numeric(pd.Series(casted), errors="coerce")
    return series


def apply_strict_type_coercion(
    db: dict[str, pd.DataFrame],
    schema: Schema,
) -> dict[str, pd.DataFrame]:
    """
    Enforce declared schema types on populated DataFrames before DuckDB insertion.

    Numeric columns (int, float, numeric) are cast to proper Python/pandas types.
    Null-like strings and empty strings become SQL NULL (pandas NA), not zero.
    """
    for table, df in db.items():
        if df.empty:
            continue
        col_types = schema.column_types.get(table, {})
        for col in df.columns:
            if col not in col_types:
                continue
            dtype = col_types[col]
            if dtype not in {"int", "float", "numeric"}:
                continue
            before_non_null = int(df[col].notna().sum())
            df[col] = _coerce_column_strict(df[col], dtype)
            after_non_null = int(df[col].notna().sum())
            if after_non_null != before_non_null:
                logger.debug(
                    "strict coercion %s.%s: non-null %d -> %d",
                    table,
                    col,
                    before_non_null,
                    after_non_null,
                )
    return db


def apply_permissive_type_coercion(
    db: dict[str, pd.DataFrame],
    schema: Schema,
) -> dict[str, pd.DataFrame]:
    """
    Lenient numeric coercion: truncate floats to ints and extract embedded numbers
    from strings (e.g. 'draft pick 12' -> 12). Still maps null-like tokens to NULL.
    """
    for table, df in db.items():
        if df.empty:
            continue
        col_types = schema.column_types.get(table, {})
        for col in df.columns:
            if col not in col_types:
                continue
            dtype = col_types[col]
            if dtype not in {"int", "float", "numeric"}:
                continue
            before_non_null = int(df[col].notna().sum())
            df[col] = _coerce_column_permissive(df[col], dtype)
            after_non_null = int(df[col].notna().sum())
            if after_non_null != before_non_null:
                logger.debug(
                    "permissive coercion %s.%s: non-null %d -> %d",
                    table,
                    col,
                    before_non_null,
                    after_non_null,
                )
    return db


def _llm_parse_mapping(
    table: str,
    col: str,
    dtype: str,
    values: list[str],
    model_name: str,
) -> dict[str, object]:
    import json

    from pipeline.llm_output_cache import cache_key, get_cached_json, put_cached_json
    from pipeline.llm_steps import llm_json_call

    unique = sorted({v for v in values if v.strip()})
    if not unique:
        return {}
    key = cache_key(model_name, "coerce", table, col, dtype, unique)
    cached = get_cached_json("coerce", key)
    if isinstance(cached, dict):
        return cached

    prompt = (
        f"Parse values for {table}.{col} as SQL type {dtype}. "
        "Return JSON mapping each original string to a parsed number or null.\n"
        f"Values: {json.dumps(unique[:100], ensure_ascii=False)}"
    )
    mapping = llm_json_call(model_name, prompt) or {}
    put_cached_json("coerce", key, mapping)
    return mapping


def apply_llm_type_coercion(
    db: dict[str, pd.DataFrame],
    schema: Schema,
    model_name: str,
) -> dict[str, pd.DataFrame]:
    for table, df in db.items():
        if df.empty:
            continue
        col_types = schema.column_types.get(table, {})
        for col in df.columns:
            if col not in col_types:
                continue
            dtype = col_types[col]
            if dtype not in {"int", "float", "numeric"}:
                continue

            raw_values = df[col].tolist()
            unparseable = []
            for value in raw_values:
                if _is_null_like(value):
                    continue
                parsed = _cast_strict_int(value) if dtype == "int" else _cast_strict_float(value)
                if isinstance(parsed, float) and math.isnan(parsed):
                    unparseable.append(str(value))

            mapping = _llm_parse_mapping(table, col, dtype, unparseable, model_name)
            if mapping:
                coerced = []
                for value in raw_values:
                    key = str(value)
                    if key in mapping:
                        coerced.append(mapping[key])
                    elif _is_null_like(value):
                        coerced.append(np.nan)
                    else:
                        coerced.append(
                            _cast_permissive_int(value)
                            if dtype == "int"
                            else _cast_permissive_float(value)
                        )
                df[col] = coerced

            df[col] = _coerce_column_permissive(df[col], dtype)
    return db


def apply_type_coercion(
    db: dict[str, pd.DataFrame],
    schema: Schema,
    mode: str,
    *,
    model_name: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Apply type coercion for the configured population axis."""
    if mode == "llm":
        if not model_name:
            logger.warning("coerce=llm requested without model_name; falling back to strict")
            return apply_strict_type_coercion(db, schema)
        return apply_llm_type_coercion(db, schema, model_name)
    if mode == "permissive":
        return apply_permissive_type_coercion(db, schema)
    return apply_strict_type_coercion(db, schema)

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

from pipeline.schema import Schema

_NUMERIC_AGG_FUNCS = ("avg", "sum", "min", "max")
_NUMERIC_COMP_OPS = ("<", ">", "<=", ">=", "=", "!=")


def _default_table_from_sql(sql: str, schema: Schema) -> str | None:
    match = re.search(r"\bfrom\s+([a-zA-Z_]\w*)", sql, flags=re.IGNORECASE)
    if not match:
        return None
    table = match.group(1).lower()
    for name in schema.tables:
        if name.lower() == table:
            return name
    return None


def _resolve_table(table_ref: str | None, default_table: str | None, schema: Schema) -> str | None:
    if table_ref:
        for name in schema.tables:
            if name.lower() == table_ref.lower():
                return name
    return default_table


def extract_numeric_column_requirements(sql: str, schema: Schema) -> list[tuple[str, str]]:
    """Return (table, column) pairs that must be numeric for SQL to execute."""
    default_table = _default_table_from_sql(sql, schema)
    requirements: set[tuple[str, str]] = set()

    for func in _NUMERIC_AGG_FUNCS:
        pattern = rf"\b{func}\s*\(\s*(?:([a-zA-Z_]\w*)\.)?([a-zA-Z_]\w*)\s*\)"
        for match in re.finditer(pattern, sql, flags=re.IGNORECASE):
            table = _resolve_table(match.group(1), default_table, schema)
            column = match.group(2)
            if not table or not column or column == "*":
                continue
            requirements.add((table, column))

    for op in _NUMERIC_COMP_OPS:
        pattern = rf"\b(?:([a-zA-Z_]\w*)\.)?([a-zA-Z_]\w*)\s*{re.escape(op)}\s*[-+]?\d"
        for match in re.finditer(pattern, sql, flags=re.IGNORECASE):
            table = _resolve_table(match.group(1), default_table, schema)
            column = match.group(2)
            if not table or not column:
                continue
            col_type = schema.column_types.get(table, {}).get(column, "str")
            if col_type in {"int", "float"}:
                requirements.add((table, column))

    return sorted(requirements)


def column_numeric_castable_rate(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    values = series.dropna()
    if values.empty:
        return 0.0
    cleaned = values.astype(str).str.strip().str.replace(",", "", regex=False)
    coerced = pd.to_numeric(cleaned, errors="coerce")
    return float(coerced.notna().mean())


def query_column_type_validity(
    queries: list[dict],
    schema: Schema,
    db: dict[str, pd.DataFrame],
) -> dict:
    """
    Check whether columns referenced by numeric SQL operations are castable to numeric.
    """
    requirements: set[tuple[str, str]] = set()
    for query in queries:
        requirements.update(extract_numeric_column_requirements(query.get("sql_query", ""), schema))

    if not requirements:
        return {
            "numeric_type_success_rate": 1.0,
            "query_column_type_validity": 1.0,
            "numeric_column_checks": [],
        }

    checks: list[dict] = []
    rates: list[float] = []
    for table, column in sorted(requirements):
        df = db.get(table, pd.DataFrame())
        if column not in df.columns:
            rate = 0.0
        else:
            rate = column_numeric_castable_rate(df[column])
        checks.append({"table": table, "column": column, "castable_rate": rate})
        rates.append(rate)

    success = float(sum(rates) / len(rates)) if rates else 1.0
    return {
        "numeric_type_success_rate": success,
        "query_column_type_validity": success,
        "numeric_column_checks": checks,
    }


def required_table_row_count(required_tables: Iterable[str], db: dict[str, pd.DataFrame]) -> dict[str, int]:
    return {table: len(db.get(table, pd.DataFrame())) for table in required_tables}

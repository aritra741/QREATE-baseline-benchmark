from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from data.loader import load_ground_truth, load_queries
from utils.config import load_config

_JOIN_ON_RE = re.compile(
    r"\bjoin\s+(\w+)\s+on\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)",
    re.IGNORECASE,
)


@dataclass
class Schema:
    dataset_name: str
    tables: dict[str, list[str]]
    column_types: dict[str, dict[str, str]]
    description: str
    join_keys: list[tuple[str, str, str, str]] = field(default_factory=list)


def _canonical_join_pair(
    left_table: str,
    left_col: str,
    right_table: str,
    right_col: str,
) -> tuple[str, str, str, str]:
    left = (left_table.lower(), left_col.lower())
    right = (right_table.lower(), right_col.lower())
    if left <= right:
        return left_table, left_col, right_table, right_col
    return right_table, right_col, left_table, left_col


def infer_join_keys_from_queries(dataset_name: str) -> list[tuple[str, str, str, str]]:
    """Foreign-key-style join pairs from JOIN ... ON left.col = right.col in workload SQL."""
    pairs: set[tuple[str, str, str, str]] = set()
    for query in load_queries(dataset_name):
        sql = query.get("sql_query", "")
        for match in _JOIN_ON_RE.finditer(sql):
            left_table, left_col, right_table, right_col = (
                match.group(2),
                match.group(3),
                match.group(4),
                match.group(5),
            )
            pairs.add(_canonical_join_pair(left_table, left_col, right_table, right_col))
    return sorted(pairs)


def _dtype_to_str(series: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(series):
        return "int"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    return "str"


def load_fixed_schema(dataset_name: str) -> Schema:
    """
    Infer schema from ground-truth tables.
    """
    tables = load_ground_truth(dataset_name)
    table_columns: dict[str, list[str]] = {}
    column_types: dict[str, dict[str, str]] = {}
    descriptions: list[str] = []

    cfg = load_config()
    benchu_root = Path(cfg["paths"]["benchu_root"])

    import json

    attr_map: dict[str, dict[str, dict]] = {}
    for attr_path in sorted(benchu_root.joinpath("Query", dataset_name).glob("*_attributes.json")):
        with attr_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for table_name, cols in data.items():
            attr_map.setdefault(table_name, {}).update(cols)

    for table_name, df in tables.items():
        # Normalize column names to lowercase so they match SQL query identifiers,
        # which are always lowercase (e.g. "birth_continent" not "Birth_continent").
        df.columns = [c.lower() for c in df.columns]
        cols = [c for c in df.columns if c != "unnamed: 0"]
        table_columns[table_name] = cols
        column_types[table_name] = {col: _dtype_to_str(df[col]) for col in cols}
        for col in cols:
            desc = attr_map.get(table_name, {}).get(col.lower(), {}).get("description", "")
            if not desc:
                # also try original-case key from attr_map
                for orig_key in attr_map.get(table_name, {}):
                    if orig_key.lower() == col:
                        desc = attr_map[table_name][orig_key].get("description", "")
                        break
            if desc:
                descriptions.append(f"{table_name}.{col}: {desc}")

    description = (
        f"Dataset {dataset_name} relational schema inferred from ground-truth CSV tables. "
        + " ".join(descriptions[:50])
    )
    return Schema(
        dataset_name=dataset_name,
        tables=table_columns,
        column_types=column_types,
        description=description,
        join_keys=infer_join_keys_from_queries(dataset_name),
    )

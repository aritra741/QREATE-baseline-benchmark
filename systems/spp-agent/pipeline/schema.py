from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data.loader import load_ground_truth
from utils.config import load_config


@dataclass
class Schema:
    dataset_name: str
    tables: dict[str, list[str]]
    column_types: dict[str, dict[str, str]]
    description: str


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
        cols = [c for c in df.columns if c.lower() != "unnamed: 0"]
        table_columns[table_name] = cols
        column_types[table_name] = {col: _dtype_to_str(df[col]) for col in cols}
        for col in cols:
            desc = attr_map.get(table_name, {}).get(col, {}).get("description", "")
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
    )

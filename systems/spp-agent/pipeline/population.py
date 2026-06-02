from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from llm.client import chat_completion
from optimizer.config_space import PopulationConfig
from pipeline.extraction import ExtractionResult
from pipeline.schema import Schema
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


def _dictionary_normalize(value: object) -> object:
    if not isinstance(value, str):
        return value
    text = value.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _llm_normalize_values(values: list[str], model_name: str) -> dict[str, str]:
    cfg = load_config()
    base_url = cfg["llm"]["base_url"]
    unique = sorted({v for v in values if isinstance(v, str) and v.strip()})
    if not unique:
        return {}

    prompt = (
        "Normalize each string to a canonical form (lowercase, trimmed, collapsed whitespace). "
        "Return JSON mapping original -> normalized.\n"
        f"Values: {json_dumps_safe(unique[:100])}"
    )
    try:
        raw, _ = chat_completion(
            model_name,
            [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            base_url=base_url,
            temperature=0.0,
            llm_cfg=cfg["llm"],
        )
        import json

        mapping = json.loads(raw)
        if isinstance(mapping, dict):
            return {str(k): str(v) for k, v in mapping.items()}
    except Exception:
        pass
    return {v: _dictionary_normalize(v) for v in unique}


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
        frames[table] = df[keep] if keep else df
    return frames


def apply_population(
    extraction: ExtractionResult,
    config: PopulationConfig,
    schema: Schema,
    *,
    extraction_model: str | None = None,
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

    threshold = 0.7 if config.er_strategy == "embedding_0.7" else 0.9

    for table, df in db.items():
        if df.empty:
            continue
        col_types = schema.column_types.get(table, {})

        for col in df.columns:
            if col == "id":
                continue
            series = df[col]
            missing_before += int(series.isna().sum()) + int((series.astype(str).str.strip() == "").sum())

            if _is_entity_column(col, col_types.get(col, "str")):
                str_vals = series.fillna("").astype(str).tolist()
                merged, m, a = _merge_entities(str_vals, threshold)
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

            if config.unit_strategy == "unit":
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
            df.dropna(how="any", inplace=True)
        elif config.miss_strategy == "mean":
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(df[col].mean())

        missing_after += int(df.isna().sum().sum())

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

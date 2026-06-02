from __future__ import annotations

import numpy as np
from scipy.stats import spearmanr

from diagnostics.glass_box_composite import compute_glass_box_composite
from optimizer.probing import ProbeData
from pipeline.schema import Schema
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.1h")


def _numeric_columns(schema: Schema) -> set[str]:
    cols: set[str] = set()
    for table, type_map in schema.column_types.items():
        for col, dtype in type_map.items():
            if dtype in ("int", "float"):
                cols.add(f"{table}.{col}")
    return cols


def _entity_columns(schema: Schema) -> set[str]:
    cols: set[str] = set()
    for table, type_map in schema.column_types.items():
        for col, dtype in type_map.items():
            if dtype == "str":
                cols.add(f"{table}.{col}")
    return cols


def _reweight_signals(signals: dict, *, numeric_weight: float, entity_weight: float) -> dict:
    """Return a copy of *signals* with adjusted weights for variant scoring."""
    adj = dict(signals)
    if numeric_weight != 1.0:
        rate = signals.get("numeric_type_success_rate", 1.0)
        adj["numeric_type_success_rate"] = rate * numeric_weight + (1.0 - numeric_weight)
    if entity_weight != 1.0:
        score = signals.get("entity_ambiguity_score", 0.0)
        adj["entity_ambiguity_score"] = score * entity_weight
    return adj


def _rank_configs(probe_data: ProbeData, reweight_fn) -> dict[str, float]:
    """Score each config using a reweighted glass-box composite."""
    scores: dict[str, float] = {}
    for cid in probe_data.config_ids:
        signals = probe_data.tier1_signals.get(cid, {})
        adj = reweight_fn(signals)
        scores[cid] = compute_glass_box_composite(adj)
    return scores


def _spearman(a: dict[str, float], b: dict[str, float]) -> float:
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        return 1.0
    x = np.array([a[c] for c in common])
    y = np.array([b[c] for c in common])
    return float(spearmanr(x, y).correlation)


def analyze_schema_rank_stability(
    probe_data: ProbeData,
    schema: Schema,
    *,
    thresholds: ThresholdConfig,
) -> dict:
    """Check whether schema composition changes the config ranking."""
    numeric_cols = _numeric_columns(schema)
    entity_cols = _entity_columns(schema)
    all_cols = numeric_cols | entity_cols

    numeric_frac = len(numeric_cols) / max(len(all_cols), 1)
    entity_frac = len(entity_cols) / max(len(all_cols), 1)

    full_scores = _rank_configs(probe_data, lambda s: s)
    numeric_scores = _rank_configs(
        probe_data,
        lambda s: _reweight_signals(s, numeric_weight=1.0 + numeric_frac, entity_weight=1.0 - entity_frac),
    )
    entity_scores = _rank_configs(
        probe_data,
        lambda s: _reweight_signals(s, numeric_weight=1.0 - numeric_frac, entity_weight=1.0 + entity_frac),
    )

    full_vs_numeric = _spearman(full_scores, numeric_scores)
    full_vs_entity = _spearman(full_scores, entity_scores)
    min_rho = min(full_vs_numeric, full_vs_entity)

    schema_matters = min_rho < thresholds.schema_rank_rho
    recommendation = "schema_first_hierarchy" if schema_matters else "flat_or_weaker_hierarchy"

    logger.info(
        "Schema rank stability: full_vs_numeric=%.4f full_vs_entity=%.4f min_rho=%.4f rec=%s",
        full_vs_numeric, full_vs_entity, min_rho, recommendation,
    )
    return {
        "full_vs_numeric_rho": full_vs_numeric,
        "full_vs_entity_rho": full_vs_entity,
        "min_rho": min_rho,
        "schema_matters": schema_matters,
        "recommendation": recommendation,
    }

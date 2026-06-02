from __future__ import annotations

from collections import defaultdict

import numpy as np

from optimizer.probing import ProbeData
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.1c")

_AXES = ("er_strategy", "norm_strategy", "unit_strategy", "miss_strategy")


def analyze_module_ordering(
    probe_data: ProbeData,
    *,
    thresholds: ThresholdConfig,
) -> dict:
    """Measure whether config-axis choice strongly affects proxy scores."""
    scores = probe_data.glass_box_composites
    configs = probe_data.configs

    if not scores:
        return {
            "axis_effects": {},
            "variance_by_axis": {},
            "ordering_sensitive": False,
            "recommendation": "fix_order",
        }

    all_vals = np.array(list(scores.values()))
    total_var = float(np.var(all_vals))

    axis_effects: dict[str, dict[str, float]] = {}
    variance_by_axis: dict[str, float] = {}

    for axis in _AXES:
        groups: dict[str, list[float]] = defaultdict(list)
        for cid, score in scores.items():
            option = getattr(configs[cid], axis)
            groups[option].append(score)
        means = {opt: float(np.mean(vals)) for opt, vals in groups.items()}
        axis_effects[axis] = means
        mean_vals = np.array(list(means.values()))
        variance_by_axis[axis] = float(np.var(mean_vals))

    max_axis_var = max(variance_by_axis.values()) if variance_by_axis else 0.0
    ordering_sensitive = total_var > 0 and max_axis_var > 0.1 * total_var
    recommendation = "use_dag_or_optimize_order" if ordering_sensitive else "fix_order"

    logger.info(
        "Module ordering: total_var=%.6f max_axis_var=%.6f sensitive=%s rec=%s",
        total_var, max_axis_var, ordering_sensitive, recommendation,
    )
    return {
        "axis_effects": axis_effects,
        "variance_by_axis": variance_by_axis,
        "ordering_sensitive": ordering_sensitive,
        "recommendation": recommendation,
    }

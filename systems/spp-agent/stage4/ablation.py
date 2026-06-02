from __future__ import annotations

from dataclasses import dataclass

from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage4.ablation")


@dataclass
class AblationResult:
    component: str
    baseline_error: float
    ablated_error: float
    gain: float
    delta: float
    retained: bool


def run_ablation(
    *,
    full_system_error: float,
    component_errors: dict[str, float],
    thresholds: ThresholdConfig,
) -> list[AblationResult]:
    """Compare full-system error vs each ablated system.

    For each component, *component_errors[name]* is the error when that
    component is removed.

    * ``gain``  = baseline_error - ablated_error  (positive → component *hurts*)
    * ``delta`` = ablated_error - baseline_error   (positive → component *helps*)
    * ``retained`` = delta > thresholds.ablation_gain
    """
    results: list[AblationResult] = []
    for component, ablated_error in component_errors.items():
        gain = full_system_error - ablated_error
        delta = ablated_error - full_system_error
        retained = delta > thresholds.ablation_gain
        results.append(
            AblationResult(
                component=component,
                baseline_error=full_system_error,
                ablated_error=ablated_error,
                gain=gain,
                delta=delta,
                retained=retained,
            )
        )
        logger.info(
            "Ablation %-22s baseline=%.4f ablated=%.4f delta=%.4f retained=%s",
            component,
            full_system_error,
            ablated_error,
            delta,
            retained,
        )
    return results


def describe_ablation_components() -> list[str]:
    """Return the canonical list of ablatable components."""
    return [
        "surrogate",
        "extraction_reuse",
        "recalibration",
        "routing",
        "flat_vs_hier",
        "query_clustering",
        "schema_pruning",
        "cluster_refinement",
    ]

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from utils.logging import setup_logger

logger = setup_logger("spp.thresholds")

_DEFAULT_RESULTS_PATH = Path("results/optimal_thresholds.json")


@dataclass
class ThresholdConfig:
    rho_viable: float = 0.65
    rho_bakeoff: float = 0.40
    cluster_purity: float = 0.75
    routing_gap: float = 0.08
    schema_rank_rho: float = 0.65
    linear_tolerance: float = 0.08
    interaction_ratio: float = 0.25
    ablation_gain: float = 0.005
    diminishing_returns_k: int = 4


THRESHOLD_SEARCH_SPACES: dict[str, tuple] = {
    "rho_viable": ("float", 0.3, 0.95),
    "rho_bakeoff": ("float", 0.1, 0.75),
    "cluster_purity": ("float", 0.5, 0.99),
    "routing_gap": ("float", 0.01, 0.30),
    "schema_rank_rho": ("float", 0.3, 0.95),
    "linear_tolerance": ("float", 0.01, 0.25),
    "interaction_ratio": ("float", 0.05, 0.70),
    "ablation_gain": ("float", 0.001, 0.10),
    "diminishing_returns_k": ("int", 2, 12),
}


def default_thresholds() -> ThresholdConfig:
    return ThresholdConfig()


def save_thresholds(tc: ThresholdConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(tc), indent=2), encoding="utf-8")
    logger.info("Saved thresholds to %s", path)


def load_thresholds(path: Path | None = None) -> ThresholdConfig:
    target = path or _DEFAULT_RESULTS_PATH
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
        logger.info("Loaded thresholds from %s", target)
        return ThresholdConfig(**data)
    logger.info("No thresholds file at %s; returning defaults", target)
    return default_thresholds()

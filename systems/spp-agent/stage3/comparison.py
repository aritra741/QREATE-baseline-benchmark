from __future__ import annotations

import time
from dataclasses import dataclass

from optimizer.probing import ProbeData
from optimizer.ranking_select import ranking_guided_select
from stage3.bayesian_opt import bayesian_opt_select
from stage3.coord_descent import coord_descent_select
from stage3.hyperband import hyperband_select
from stage3.ilp_select import ilp_select
from surrogates.base import BaseSurrogate
from utils.logging import setup_logger

logger = setup_logger("spp.stage3.comparison")

ALL_ALGORITHMS = ["greedy", "bayesian_opt", "hyperband", "coord_descent", "ilp"]


@dataclass
class AlgorithmResult:
    algorithm: str
    selected_configs: list[str]
    total_predicted_score: float
    wall_time_seconds: float


def _run_greedy(
    surrogate: BaseSurrogate,
    candidate_ids: list[str],
    budget: int,
    seed: int,
) -> list[str]:
    return ranking_guided_select(
        instance=None,
        surrogate=surrogate,
        remaining_budget=float(budget),
        config_candidates=candidate_ids,
    )


def compare_algorithms(
    surrogate: BaseSurrogate,
    candidate_ids: list[str],
    probe_data: ProbeData,
    budget: int,
    *,
    algorithms: list[str] | None = None,
    seed: int = 42,
) -> list[AlgorithmResult]:
    """Run each algorithm with the same budget and return results sorted by
    total predicted score (descending)."""
    algo_list = algorithms if algorithms is not None else list(ALL_ALGORITHMS)

    dispatch: dict[str, object] = {
        "greedy": lambda: _run_greedy(surrogate, candidate_ids, budget, seed),
        "bayesian_opt": lambda: bayesian_opt_select(
            surrogate, candidate_ids, budget, seed=seed,
        ),
        "hyperband": lambda: hyperband_select(
            surrogate, candidate_ids, budget,
        ),
        "coord_descent": lambda: coord_descent_select(
            surrogate, candidate_ids, budget, seed=seed,
        ),
        "ilp": lambda: ilp_select(surrogate, candidate_ids, budget),
    }

    results: list[AlgorithmResult] = []
    for name in algo_list:
        if name not in dispatch:
            logger.warning("Unknown algorithm '%s'; skipping", name)
            continue
        t0 = time.perf_counter()
        selected = dispatch[name]()
        elapsed = time.perf_counter() - t0
        total_score = sum(surrogate.score(cid) for cid in selected)
        results.append(
            AlgorithmResult(
                algorithm=name,
                selected_configs=selected,
                total_predicted_score=total_score,
                wall_time_seconds=elapsed,
            )
        )
        logger.info(
            "Algorithm %-15s selected=%d score=%.4f time=%.3fs",
            name,
            len(selected),
            total_score,
            elapsed,
        )

    results.sort(key=lambda r: r.total_predicted_score, reverse=True)
    return results

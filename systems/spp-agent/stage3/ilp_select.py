from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

from surrogates.base import BaseSurrogate
from utils.logging import setup_logger

logger = setup_logger("spp.stage3.ilp_select")


def ilp_select(
    surrogate: BaseSurrogate,
    candidate_ids: list[str],
    budget: int,
) -> list[str]:
    """LP relaxation of 0-1 knapsack (uniform cost, count budget).

    Maximise ``c @ x`` subject to ``sum(x) <= budget`` and ``0 <= x <= 1``
    using ``scipy.optimize.linprog`` (which *minimises*).  After solving,
    round by taking the top *budget* configs by x_i value.  Falls back to
    greedy ranking on solver failure.
    """
    if len(candidate_ids) <= budget:
        return surrogate.rank(candidate_ids)[:budget]

    n = len(candidate_ids)
    scores = np.array([surrogate.score(cid) for cid in candidate_ids])

    # linprog minimises, so negate scores to maximise
    c = -scores

    # Inequality constraint: sum(x) <= budget  →  A_ub @ x <= b_ub
    A_ub = np.ones((1, n))
    b_ub = np.array([float(budget)])
    bounds = [(0.0, 1.0)] * n

    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

    if not result.success:
        logger.warning("linprog failed (%s); falling back to greedy ranking", result.message)
        return surrogate.rank(candidate_ids)[:budget]

    x = result.x
    # Pick top-budget indices by LP relaxation value
    top_indices = np.argsort(-x)[:budget]
    selected = [candidate_ids[i] for i in top_indices]

    lp_obj = -result.fun
    logger.info(
        "ILP-LP selected %d configs (lp_objective=%.4f)",
        len(selected),
        lp_obj,
    )
    return selected

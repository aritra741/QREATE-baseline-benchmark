from __future__ import annotations

import math

from surrogates.base import BaseSurrogate
from utils.logging import setup_logger

logger = setup_logger("spp.stage3.hyperband")


def hyperband_select(
    surrogate: BaseSurrogate,
    candidate_ids: list[str],
    budget: int,
    *,
    eta: int = 3,
) -> list[str]:
    """Successive Halving (Hyperband bracket 0) using surrogate scores.

    Start with all candidates, keep top-1/eta fraction each round until
    ``<= budget`` configs remain.
    """
    if len(candidate_ids) <= budget:
        return surrogate.rank(candidate_ids)[:budget]

    survivors = list(candidate_ids)
    rung = 0

    while len(survivors) > budget:
        scored = [(cid, surrogate.score(cid)) for cid in survivors]
        scored.sort(key=lambda t: t[1], reverse=True)
        keep = max(budget, math.ceil(len(scored) / eta))
        survivors = [cid for cid, _ in scored[:keep]]
        rung += 1
        logger.info(
            "Hyperband rung=%d survivors=%d (kept top-%d of %d)",
            rung,
            len(survivors),
            keep,
            len(scored),
        )

    # Final rank among survivors
    ranked = surrogate.rank(survivors)
    selected = ranked[:budget]
    logger.info("Hyperband selected %d configs after %d rungs", len(selected), rung)
    return selected

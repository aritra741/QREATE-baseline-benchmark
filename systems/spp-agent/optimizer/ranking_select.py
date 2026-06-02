from __future__ import annotations

from surrogates.base import BaseSurrogate


def ranking_guided_select(
    instance,
    surrogate: BaseSurrogate,
    remaining_budget: float,
    config_candidates: list[str],
    *,
    cost_per_config: float = 1.0,
) -> list[str]:
    ranked = surrogate.rank(config_candidates)
    selected: list[str] = []
    budget = remaining_budget
    for cid in ranked:
        if budget < cost_per_config:
            break
        selected.append(cid)
        budget -= cost_per_config
    return selected

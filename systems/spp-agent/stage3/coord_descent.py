from __future__ import annotations

import random
import re

from surrogates.base import BaseSurrogate
from utils.logging import setup_logger

logger = setup_logger("spp.stage3.coord_descent")

_AXES = ("er", "norm", "unit", "miss")
_CID_RE = re.compile(
    r"er=(?P<er>[^|]+)\|norm=(?P<norm>[^|]+)\|unit=(?P<unit>[^|]+)\|miss=(?P<miss>.+)"
)


def _parse_config_id(config_id: str) -> dict[str, str]:
    m = _CID_RE.match(config_id)
    if m is None:
        raise ValueError(f"Cannot parse config_id: {config_id}")
    return m.groupdict()


def _build_config_id(axes: dict[str, str]) -> str:
    return f"er={axes['er']}|norm={axes['norm']}|unit={axes['unit']}|miss={axes['miss']}"


def coord_descent_select(
    surrogate: BaseSurrogate,
    candidate_ids: list[str],
    budget: int,
    *,
    max_iter: int = 20,
    seed: int = 42,
) -> list[str]:
    """Coordinate descent over config axes (er, norm, unit, miss).

    Start from the probed config with the highest surrogate score.
    Iterate axes in round-robin; for each axis try all option values
    while keeping other axes fixed. Move to the best neighbour when it
    improves the score.  Return the top *budget* configs encountered
    during the search trajectory (deduplicated, sorted by score).
    """
    if len(candidate_ids) <= budget:
        return surrogate.rank(candidate_ids)[:budget]

    rng = random.Random(seed)

    # Index candidate options per axis
    candidate_set = set(candidate_ids)
    axis_options: dict[str, list[str]] = {ax: [] for ax in _AXES}
    for cid in candidate_ids:
        parsed = _parse_config_id(cid)
        for ax in _AXES:
            if parsed[ax] not in axis_options[ax]:
                axis_options[ax].append(parsed[ax])

    # Start from best-scored candidate
    scored = [(cid, surrogate.score(cid)) for cid in candidate_ids]
    scored.sort(key=lambda t: t[1], reverse=True)
    current_axes = _parse_config_id(scored[0][0])
    current_score = scored[0][1]

    trajectory: dict[str, float] = {scored[0][0]: current_score}

    for iteration in range(max_iter):
        improved = False
        for ax in _AXES:
            best_val = current_axes[ax]
            best_score = current_score
            options = list(axis_options[ax])
            rng.shuffle(options)
            for val in options:
                trial_axes = dict(current_axes)
                trial_axes[ax] = val
                trial_id = _build_config_id(trial_axes)
                if trial_id not in candidate_set:
                    continue
                s = surrogate.score(trial_id)
                trajectory[trial_id] = s
                if s > best_score:
                    best_score = s
                    best_val = val
            if best_val != current_axes[ax]:
                current_axes[ax] = best_val
                current_score = best_score
                improved = True
        if not improved:
            logger.info("Coord descent converged at iteration=%d", iteration)
            break

    ranked = sorted(trajectory.items(), key=lambda t: t[1], reverse=True)
    selected = [cid for cid, _ in ranked[:budget]]
    logger.info(
        "Coord descent selected %d configs (trajectory_size=%d iterations=%d)",
        len(selected),
        len(trajectory),
        min(iteration + 1, max_iter),
    )
    return selected

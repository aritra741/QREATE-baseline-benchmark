"""Stage 5 — baseline config-selection strategies for evaluation."""

from __future__ import annotations

import random as _random
from typing import Any

from optimizer.config_space import generate_config_space
from optimizer.ranking_select import ranking_guided_select
from surrogates.base import BaseSurrogate
from utils.logging import setup_logger

logger = setup_logger("spp.stage5.baselines")


def build_trivial_routing_table(
    selected_configs: list[str],
    query_clusters,
    probe_data,
) -> dict[int, str]:
    """Assign all clusters to the top glass-box config in selected_configs."""
    if not selected_configs:
        return {}
    if probe_data is not None and probe_data.glass_box_composites:
        best = max(
            (c for c in selected_configs if c in probe_data.glass_box_composites),
            key=lambda c: probe_data.glass_box_composites[c],
            default=selected_configs[0],
        )
    else:
        best = selected_configs[0]
    n_clusters = getattr(query_clusters, "n_clusters", 1)
    return {cid: best for cid in range(n_clusters)}


def default_config_select(candidate_ids: list[str], budget: int) -> list[str]:
    """Select first *budget* configs in canonical (generate_config_space) order."""
    canonical_order = [c.config_id for c in generate_config_space()]
    canonical_set = set(candidate_ids)
    ordered = [cid for cid in canonical_order if cid in canonical_set]
    # Append any candidate_ids not in canonical order at the end
    remaining = [cid for cid in candidate_ids if cid not in set(ordered)]
    return (ordered + remaining)[: max(1, budget)]


def single_best_select(
    surrogate: BaseSurrogate,
    candidate_ids: list[str],
    budget: int,
) -> list[str]:
    """Greedy ranking by the given surrogate."""
    return ranking_guided_select(
        None,
        surrogate,
        remaining_budget=float(budget),
        config_candidates=candidate_ids,
    )


def squid_select(
    candidate_ids: list[str],
    budget: int,
    *,
    historical_rows: list[dict],
    current_slice: str,
    current_btl_spread: float = 0.0,
    current_glass_spread: float = 0.0,
) -> list[str]:
    """SQUID-style: find most-similar historical row by (slice, btl_spread, glass_spread),
    reuse its selected_configs.  If selected_configs not in row, use its surrogate with
    lowest error."""
    best_row: dict[str, Any] | None = None
    best_dist = float("inf")

    for row in historical_rows:
        row_slice = str(row.get("slice", ""))
        slice_match = 0.0 if row_slice == current_slice else 1.0
        btl_diff = abs(float(row.get("btl_spread", 0.0)) - current_btl_spread)
        glass_diff = abs(float(row.get("glass_spread", 0.0)) - current_glass_spread)
        dist = slice_match + btl_diff + glass_diff
        if dist < best_dist:
            best_dist = dist
            best_row = row

    if best_row is not None:
        selected = best_row.get("selected_configs")
        if isinstance(selected, list) and selected:
            # Filter to valid candidates, truncate to budget
            valid = [c for c in selected if c in set(candidate_ids)]
            if valid:
                return valid[: max(1, budget)]

        # Fallback: use surrogate from the closest row
        surrogate_name = best_row.get("surrogate")
        if surrogate_name:
            try:
                from surrogates.registry import build_surrogate

                fallback = build_surrogate(surrogate_name)
                return single_best_select(fallback, candidate_ids, budget)
            except Exception:
                logger.warning(
                    "squid_select: could not build surrogate %s; falling back to default",
                    surrogate_name,
                )

    return default_config_select(candidate_ids, budget)


def random_select(
    candidate_ids: list[str],
    budget: int,
    *,
    seed: int = 42,
) -> list[str]:
    """Random selection."""
    rng = _random.Random(seed)
    pool = list(candidate_ids)
    rng.shuffle(pool)
    return pool[: max(1, budget)]


def ilp_baseline_select(
    surrogate: BaseSurrogate,
    candidate_ids: list[str],
    budget: int,
) -> list[str]:
    """Use stage3.ilp_select as a baseline."""
    from stage3.ilp_select import ilp_select

    return ilp_select(surrogate, candidate_ids, budget)

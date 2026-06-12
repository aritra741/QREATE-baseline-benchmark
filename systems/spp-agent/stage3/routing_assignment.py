from __future__ import annotations

"""Cluster-to-configuration assignment under token budget constraints.

Replaces the Stage 3 greedy/BO/ILP/coord_descent global ranking.
No ground-truth access.
"""

from dataclasses import dataclass

from surrogates.registry import build_surrogate
from utils.logging import setup_logger

logger = setup_logger("spp.stage3.routing_assignment")


@dataclass
class RoutingTable:
    cluster_to_config: dict[int, str]
    selected_configs: list[str]
    cluster_types: dict[int, str]
    assignment_scores: dict[int, float]
    assignment_uncertainty: dict[int, float]
    n_materializations: int
    risk_level: str
    token_cost_estimate: float


def _cluster_sizes(query_clusters) -> dict[int, int]:
    return {cid: len(queries) for cid, queries in query_clusters.cluster_to_queries.items()}


def assign_configs_to_clusters(
    query_clusters,
    probe_data,
    cluster_surrogates: dict[int, str],
    all_config_ids: list[str],
    token_budget,
    cost_model,
    n_docs: int,
    *,
    risk_level: str = "risk_neutral",
    risk_lambda: float = 0.5,
    seed: int = 42,
) -> RoutingTable:
    """Jointly select configurations and build routing table."""
    sizes = _cluster_sizes(query_clusters)
    sorted_clusters = sorted(
        range(query_clusters.n_clusters),
        key=lambda cid: sizes.get(cid, 0),
        reverse=True,
    )

    materialized: set[str] = set()
    routing: dict[int, str] = {}
    assignment_scores: dict[int, float] = {}
    assignment_uncertainty: dict[int, float] = {}
    token_cost = 0.0

    fitted_surrogates: dict[int, object] = {}
    cluster_rankings: dict[int, list[tuple[str, float, float]]] = {}

    for cluster_id in sorted_clusters:
        surrogate_name = cluster_surrogates.get(cluster_id, "direct_probe_ranking")
        surrogate = build_surrogate(surrogate_name, seed=seed)
        surrogate.fit_cluster(probe_data, cluster_id)
        fitted_surrogates[cluster_id] = surrogate

        ranked: list[tuple[str, float, float]] = []
        for config_id in all_config_ids:
            score, uncertainty = surrogate.score_with_uncertainty(config_id)
            if risk_level == "risk_averse":
                adjusted = score - risk_lambda * uncertainty
            else:
                adjusted = score
            ranked.append((config_id, adjusted, uncertainty))
        ranked.sort(key=lambda row: row[1], reverse=True)
        cluster_rankings[cluster_id] = ranked

    for cluster_id in sorted_clusters:
        ranked = cluster_rankings[cluster_id]
        surrogate = fitted_surrogates[cluster_id]
        assigned = False

        for config_id, adjusted_score, uncertainty in ranked:
            if config_id in materialized:
                routing[cluster_id] = config_id
                assignment_scores[cluster_id] = adjusted_score
                assignment_uncertainty[cluster_id] = uncertainty
                assigned = True
                break

            marginal = cost_model.config_marginal_cost(config_id, n_docs)
            if token_budget.remaining >= marginal:
                if marginal > 0:
                    token_budget.spend(marginal, label=f"materialize:{config_id}")
                    token_cost += marginal
                materialized.add(config_id)
                routing[cluster_id] = config_id
                assignment_scores[cluster_id] = adjusted_score
                assignment_uncertainty[cluster_id] = uncertainty
                assigned = True
                break

        if not assigned:
            if materialized:
                best = max(materialized, key=lambda c: surrogate.score(c))
                routing[cluster_id] = best
                assignment_scores[cluster_id] = surrogate.score(best)
                assignment_uncertainty[cluster_id] = surrogate.score_with_uncertainty(best)[1]
            elif ranked:
                routing[cluster_id] = ranked[0][0]
                assignment_scores[cluster_id] = ranked[0][1]
                assignment_uncertainty[cluster_id] = ranked[0][2]
                materialized.add(ranked[0][0])

    if not routing and all_config_ids:
        fallback = max(probe_data.glass_box_composites, key=probe_data.glass_box_composites.get)
        for cluster_id in range(query_clusters.n_clusters):
            routing[cluster_id] = fallback
            assignment_scores[cluster_id] = probe_data.glass_box_composites.get(fallback, 0.0)
            assignment_uncertainty[cluster_id] = 0.0
        materialized.add(fallback)

    selected_configs = sorted(set(routing.values()))
    logger.info(
        "Routing assignment: clusters=%d materializations=%d routing=%s risk=%s",
        len(routing),
        len(selected_configs),
        routing,
        risk_level,
    )

    return RoutingTable(
        cluster_to_config=routing,
        selected_configs=selected_configs,
        cluster_types=dict(query_clusters.cluster_types),
        assignment_scores=assignment_scores,
        assignment_uncertainty=assignment_uncertainty,
        n_materializations=len(selected_configs),
        risk_level=risk_level,
        token_cost_estimate=token_cost,
    )


def deterministic_routing_fallback(query_clusters, probe_data) -> RoutingTable:
    """Assign the highest global glass-box config to all clusters."""
    if not probe_data.glass_box_composites:
        best = probe_data.config_ids[0] if probe_data.config_ids else ""
    else:
        best = max(probe_data.glass_box_composites, key=probe_data.glass_box_composites.get)

    routing = {cid: best for cid in range(query_clusters.n_clusters)}
    score = probe_data.glass_box_composites.get(best, 0.0)

    return RoutingTable(
        cluster_to_config=routing,
        selected_configs=[best] if best else [],
        cluster_types=dict(query_clusters.cluster_types),
        assignment_scores={cid: score for cid in routing},
        assignment_uncertainty={cid: 0.0 for cid in routing},
        n_materializations=1 if best else 0,
        risk_level="risk_neutral",
        token_cost_estimate=0.0,
    )

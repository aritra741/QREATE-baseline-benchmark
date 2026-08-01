"""Progressive pilot search and conservative budgeted portfolio selection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from spp.budget_ledger import BudgetExhausted, GlobalBudgetLedger
from spp.population_config import encode_config_features
from spp.spec import (
    FrozenPortfolio,
    QualityEstimate,
    QueryRequirement,
    SynthesisConfig,
    conservative_portfolio_objective,
    route_by_conservative_quality,
)


@dataclass
class PilotResult:
    config_id: str
    estimates: Dict[str, QualityEstimate]
    output_signature: str
    full_cost_upper_bound: int
    sample_fraction: float
    metadata: dict = field(default_factory=dict)


@dataclass
class ProgressiveSearchResult:
    survivors: List[str]
    eliminated: Dict[str, str]
    pilots: Dict[str, PilotResult]
    rounds_completed: int
    tokens_spent: int


def diverse_candidate_order(
    configs: Sequence[SynthesisConfig],
) -> List[SynthesisConfig]:
    """Deterministic farthest-first order across all three SPP axes."""
    if not configs:
        return []

    def vector(config: SynthesisConfig) -> Tuple[float, ...]:
        schema_bits = tuple(
            1.0 if config.schema.pattern == pattern else 0.0
            for pattern in ("denormalized", "star", "snowflake")
        )
        preprocessing_bits = (
            1.0 if config.preprocessing.strategy == "whole_document" else 0.0,
            1.0 if config.preprocessing.strategy == "chunked" else 0.0,
            float(config.preprocessing.chunk_size or 0) / 4_000.0,
        )
        return schema_bits + preprocessing_bits + tuple(
            encode_config_features(config.population)
        )

    vectors = {config.config_id: vector(config) for config in configs}

    def distance(left: str, right: str) -> float:
        return sum(
            abs(a - b) for a, b in zip(vectors[left], vectors[right])
        )

    remaining = {config.config_id: config for config in configs}
    first_id = min(remaining)
    ordered = [remaining.pop(first_id)]
    while remaining:
        selected_ids = [config.config_id for config in ordered]
        next_id = max(
            remaining,
            key=lambda config_id: (
                min(distance(config_id, selected_id) for selected_id in selected_ids),
                config_id,
            ),
        )
        ordered.append(remaining.pop(next_id))
    return ordered


def canonical_output_signature(outputs_by_query: Mapping[str, Iterable[dict]]) -> str:
    """Hash materialized workload answers without consulting ground truth."""
    normalized = {}
    for query_id, rows in sorted(outputs_by_query.items()):
        canonical_rows = [
            {str(key): row[key] for key in sorted(row)}
            for row in rows
        ]
        canonical_rows.sort(
            key=lambda row: json.dumps(row, sort_keys=True, default=str)
        )
        normalized[query_id] = canonical_rows
    payload = json.dumps(normalized, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def collapse_output_equivalent(
    config_ids: Sequence[str],
    pilots: Mapping[str, PilotResult],
) -> Tuple[List[str], Dict[str, str]]:
    """Keep the cheapest representative for each output and coverage signature."""
    by_signature: Dict[Tuple[str, Tuple[str, ...]], List[str]] = {}
    for config_id in config_ids:
        pilot = pilots.get(config_id)
        if pilot is None:
            continue
        signature = (
            pilot.output_signature,
            tuple(sorted(pilot.estimates)),
        )
        by_signature.setdefault(signature, []).append(config_id)
    retained: List[str] = []
    eliminated: Dict[str, str] = {}
    for group in by_signature.values():
        representative = min(
            group,
            key=lambda cid: (pilots[cid].full_cost_upper_bound, cid),
        )
        retained.append(representative)
        for config_id in group:
            if config_id != representative:
                eliminated[config_id] = f"output-equivalent-to:{representative}"
    return sorted(retained), eliminated


def _confidence_dominated(
    candidate_id: str,
    challenger_id: str,
    requirements: Sequence[QueryRequirement],
    pilots: Mapping[str, PilotResult],
    *,
    beta: float,
) -> bool:
    candidate = pilots[candidate_id]
    challenger = pilots[challenger_id]
    if challenger.full_cost_upper_bound > candidate.full_cost_upper_bound:
        return False
    if not set(candidate.estimates) <= set(challenger.estimates):
        return False
    strict = False
    compared = False
    for requirement in requirements:
        left = candidate.estimates.get(requirement.query_id)
        right = challenger.estimates.get(requirement.query_id)
        if left is None or right is None:
            continue
        compared = True
        if right.lower_confidence_bound(beta) < left.upper_confidence_bound(beta):
            return False
        strict = strict or (
            right.lower_confidence_bound(beta) > left.upper_confidence_bound(beta)
        )
    return compared and strict


def progressive_pilot_search(
    configs: Sequence[SynthesisConfig],
    requirements: Sequence[QueryRequirement],
    evaluator: Callable[
        [SynthesisConfig, float, GlobalBudgetLedger], PilotResult
    ],
    ledger: GlobalBudgetLedger,
    *,
    sample_fractions: Sequence[float] = (0.05, 0.15, 0.4),
    completion_reserve: int,
    completion_costs: Optional[Mapping[str, int]] = None,
    completion_escrowed: bool = False,
    beta: float = 1.0,
) -> ProgressiveSearchResult:
    """Pilot candidates progressively and eliminate only safe dominations.

    ``evaluator`` is responsible for charging every LLM call to ``ledger``.
    The search verifies that reported token use appears in that ledger.
    """
    survivors = {config.config_id: config for config in configs}
    pilots: Dict[str, PilotResult] = {}
    eliminated: Dict[str, str] = {}
    started_spend = ledger.actual_spent
    rounds_completed = 0

    for sample_fraction in sample_fractions:
        if not completion_escrowed and not ledger.can_complete(completion_reserve):
            break
        round_results: Dict[str, PilotResult] = {}
        round_order = diverse_candidate_order(list(survivors.values()))
        if completion_costs and round_order:
            anchor = min(
                round_order,
                key=lambda config: (
                    int(completion_costs[config.config_id]),
                    config.config_id,
                ),
            )
            round_order = [
                anchor,
                *[config for config in round_order if config != anchor],
            ]
        pilot_budget_exhausted = False
        for config in round_order:
            if (
                not completion_escrowed
                and not ledger.can_complete(completion_reserve)
            ):
                break
            config_id = config.config_id
            before = ledger.actual_spent
            try:
                result = evaluator(config, float(sample_fraction), ledger)
            except BudgetExhausted:
                eliminated[config_id] = "not-admitted:pilot-budget"
                pilot_budget_exhausted = True
                break
            if result.config_id != config_id:
                raise ValueError("pilot evaluator returned the wrong config_id")
            if ledger.actual_spent < before:
                raise AssertionError("token ledger spend moved backwards")
            round_results[config_id] = result
            pilots[config_id] = result
        if not round_results and pilot_budget_exhausted:
            # The budget can still complete the escrowed cheapest full-cover
            # configuration. Preserve it for direct materialization instead of
            # incorrectly declaring the whole SPP problem infeasible.
            direct = round_order[0]
            eliminated.pop(direct.config_id, None)
            for config_id in set(survivors) - {direct.config_id}:
                eliminated[config_id] = "not-admitted:direct-completion"
            survivors = {direct.config_id: direct}
            break
        if not round_results:
            break
        rounds_completed += 1
        signature_counts: Dict[str, int] = {}
        for result in round_results.values():
            signature_counts[result.output_signature] = (
                signature_counts.get(result.output_signature, 0) + 1
            )
        for result in round_results.values():
            agreement = signature_counts[result.output_signature] / len(round_results)
            result.estimates = {
                query_id: replace(
                    estimate,
                    uncertainty=max(
                        estimate.uncertainty, 0.5 * (1.0 - agreement)
                    ),
                    components={
                        **dict(estimate.components),
                        "candidate_agreement": agreement,
                    },
                )
                for query_id, estimate in result.estimates.items()
            }
        for config_id in set(survivors) - set(round_results):
            eliminated[config_id] = "not-admitted:completion-reserve"

        retained, equivalents = collapse_output_equivalent(
            list(round_results), round_results
        )
        eliminated.update(equivalents)
        active = set(retained)
        for candidate_id in sorted(active):
            for challenger_id in sorted(active - {candidate_id}):
                if _confidence_dominated(
                    candidate_id,
                    challenger_id,
                    requirements,
                    round_results,
                    beta=beta,
                ):
                    eliminated[candidate_id] = (
                        f"confidence-dominated-by:{challenger_id}"
                    )
                    break
        active -= set(eliminated)
        survivors = {cid: survivors[cid] for cid in active}
        if completion_escrowed and completion_costs and survivors:
            survivor_reserve = min(
                int(completion_costs[config_id]) for config_id in survivors
            )
            if survivor_reserve > completion_reserve:
                raise AssertionError(
                    "pilot pruning discarded every completion-reserved candidate"
                )
        if len(survivors) <= 1:
            break

    return ProgressiveSearchResult(
        survivors=sorted(survivors),
        eliminated=eliminated,
        pilots=pilots,
        rounds_completed=rounds_completed,
        tokens_spent=ledger.actual_spent - started_spend,
    )


def select_budgeted_portfolio(
    configs: Sequence[SynthesisConfig],
    requirements: Sequence[QueryRequirement],
    estimates: Mapping[Tuple[str, str], QualityEstimate],
    construction_costs: Mapping[str, int],
    *,
    token_budget: int,
    tokens_already_spent: int = 0,
    beta: float = 1.0,
    quality_floor: float = 0.0,
    marginal_cost_fn: Optional[Callable[[str, Set[str]], int]] = None,
) -> FrozenPortfolio:
    """Two-pass full-cover then facility-location greedy selection."""
    by_id = {config.config_id: config for config in configs}
    remaining = int(token_budget) - int(tokens_already_spent)
    if remaining < 0:
        raise BudgetExhausted("search already exceeded total token budget")

    # With additive costs the conservative portfolio problem is a binary
    # facility-location ILP. Solving it exactly avoids a greedy cover choosing
    # a cheap low-quality config that blocks a better feasible config.
    if marginal_cost_fn is None:
        try:
            import numpy as np
            from scipy.optimize import Bounds, LinearConstraint, milp
            from scipy.sparse import lil_matrix

            config_list = list(configs)
            n_configs = len(config_list)
            n_queries = len(requirements)
            n_vars = n_configs + n_queries * n_configs
            objective = np.zeros(n_vars)
            cost_scale = max(
                sum(int(construction_costs[c.config_id]) for c in config_list),
                1,
            )
            for c_index, config in enumerate(config_list):
                objective[c_index] = (
                    int(construction_costs[config.config_id])
                    / cost_scale
                    * 1e-9
                )
            compatible: Dict[Tuple[int, int], float] = {}
            for q_index, requirement in enumerate(requirements):
                for c_index, config in enumerate(config_list):
                    estimate = estimates.get(
                        (requirement.query_id, config.config_id)
                    )
                    if not config.schema.covers(requirement) or estimate is None:
                        continue
                    lcb = estimate.lower_confidence_bound(beta)
                    if lcb < quality_floor:
                        continue
                    compatible[(q_index, c_index)] = lcb
                    objective[n_configs + q_index * n_configs + c_index] = -lcb
            incompatible_query_ids = [
                requirement.query_id
                for q_index, requirement in enumerate(requirements)
                if not any(
                    (q_index, c_index) in compatible
                    for c_index in range(n_configs)
                )
            ]
            if incompatible_query_ids:
                rendered_ids = ", ".join(incompatible_query_ids)
                raise BudgetExhausted(
                    "no full-cover portfolio satisfies the quality floor; "
                    f"incompatible queries: {rendered_ids}"
                )

            rows = 1 + n_queries + n_queries * n_configs
            matrix = lil_matrix((rows, n_vars), dtype=float)
            lower = np.full(rows, -np.inf)
            upper = np.full(rows, np.inf)
            row = 0
            for c_index, config in enumerate(config_list):
                matrix[row, c_index] = construction_costs[config.config_id]
            upper[row] = remaining
            row += 1
            for q_index in range(n_queries):
                for c_index in range(n_configs):
                    y_index = n_configs + q_index * n_configs + c_index
                    matrix[row, y_index] = 1.0
                lower[row] = upper[row] = 1.0
                row += 1
            for q_index in range(n_queries):
                for c_index in range(n_configs):
                    y_index = n_configs + q_index * n_configs + c_index
                    matrix[row, y_index] = 1.0
                    matrix[row, c_index] = -1.0
                    upper[row] = 0.0
                    row += 1
            variable_upper = np.ones(n_vars)
            for q_index in range(n_queries):
                for c_index in range(n_configs):
                    if (q_index, c_index) not in compatible:
                        variable_upper[
                            n_configs + q_index * n_configs + c_index
                        ] = 0.0
            solution = milp(
                c=objective,
                integrality=np.ones(n_vars),
                bounds=Bounds(np.zeros(n_vars), variable_upper),
                constraints=LinearConstraint(matrix.tocsr(), lower, upper),
            )
            if not solution.success or solution.x is None:
                raise BudgetExhausted(
                    f"no conservative portfolio fits budget: {solution.message}"
                )
            routing: Dict[str, str] = {}
            scores: Dict[str, float] = {}
            for q_index, requirement in enumerate(requirements):
                routed = max(
                    range(n_configs),
                    key=lambda c_index: solution.x[
                        n_configs + q_index * n_configs + c_index
                    ],
                )
                config_id = config_list[routed].config_id
                routing[requirement.query_id] = config_id
                scores[requirement.query_id] = compatible[(q_index, routed)]
            used = tuple(sorted(set(routing.values())))
            construction = sum(int(construction_costs[cid]) for cid in used)
            portfolio = FrozenPortfolio(
                selected_config_ids=used,
                query_to_config=routing,
                query_scores=scores,
                construction_tokens=tokens_already_spent + construction,
                objective_value=sum(scores.values()),
            )
            portfolio.validate(requirements, by_id, token_budget)
            return portfolio
        except ImportError:
            # Minimal installations retain the shared-cost greedy path below.
            pass

    def marginal(config_id: str, selected: Set[str]) -> int:
        if marginal_cost_fn is not None:
            return int(marginal_cost_fn(config_id, selected))
        return int(construction_costs[config_id])

    selected: Set[str] = set()
    uncovered = {requirement.query_id for requirement in requirements}
    req_by_id = {requirement.query_id: requirement for requirement in requirements}
    spent = 0

    # Pass 1: minimum-cost conservative set cover.
    while uncovered:
        best: Optional[Tuple[float, int, str, Set[str]]] = None
        for config in configs:
            if config.config_id in selected:
                continue
            covered = {
                query_id
                for query_id in uncovered
                if config.schema.covers(req_by_id[query_id])
                and (query_id, config.config_id) in estimates
                and estimates[
                    (query_id, config.config_id)
                ].lower_confidence_bound(beta)
                >= quality_floor
            }
            if not covered:
                continue
            cost = marginal(config.config_id, selected)
            if cost > remaining - spent:
                continue
            ratio = len(covered) / max(cost, 1)
            candidate = (ratio, -cost, config.config_id, covered)
            if best is None or candidate[:3] > best[:3]:
                best = candidate
        if best is None:
            raise BudgetExhausted(
                "no full-cover portfolio satisfies quality floor and budget"
            )
        _, neg_cost, config_id, covered = best
        selected.add(config_id)
        spent += -neg_cost
        uncovered -= covered

    # Pass 2: add candidates by conservative marginal utility per token.
    current_objective = conservative_portfolio_objective(
        requirements, selected, estimates, beta=beta
    )
    while True:
        best_addition: Optional[Tuple[float, float, int, str]] = None
        for config in configs:
            config_id = config.config_id
            if config_id in selected:
                continue
            cost = marginal(config_id, selected)
            if cost > remaining - spent:
                continue
            objective = conservative_portfolio_objective(
                requirements, selected | {config_id}, estimates, beta=beta
            )
            gain = objective - current_objective
            if gain <= 0:
                continue
            ratio = gain / max(cost, 1)
            candidate = (ratio, gain, -cost, config_id)
            if best_addition is None or candidate > best_addition:
                best_addition = candidate
        if best_addition is None:
            break
        _ratio, gain, neg_cost, config_id = best_addition
        selected.add(config_id)
        spent += -neg_cost
        current_objective += gain

    selected_configs = [by_id[config_id] for config_id in sorted(selected)]
    routing, scores = route_by_conservative_quality(
        requirements,
        selected_configs,
        estimates,
        beta=beta,
        quality_floor=quality_floor,
    )
    used = set(routing.values())
    # Drop selected candidates that never win a route; they provide no deployed
    # value even if the greedy intermediate objective briefly selected them.
    selected_configs = [config for config in selected_configs if config.config_id in used]
    actual_spent = 0
    costed: Set[str] = set()
    for config in selected_configs:
        actual_spent += marginal(config.config_id, costed)
        costed.add(config.config_id)
    portfolio = FrozenPortfolio(
        selected_config_ids=tuple(sorted(used)),
        query_to_config=routing,
        query_scores=scores,
        construction_tokens=tokens_already_spent + actual_spent,
        objective_value=sum(scores.values()),
    )
    portfolio.validate(requirements, by_id, token_budget)
    return portfolio

"""Query-conditioned, ground-truth-free quality and uncertainty estimation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from spp.spec import QualityEstimate


@dataclass(frozen=True)
class CellEvidence:
    row_identity: str
    column: str
    value: object
    source_span: Optional[str]
    span_restored: bool
    entailed: bool
    document_id: Optional[str] = None

    @property
    def supported(self) -> bool:
        return bool(self.source_span and self.span_restored and self.entailed)


@dataclass
class PilotObservation:
    query_id: str
    config_id: str
    cells: List[CellEvidence] = field(default_factory=list)
    relevant_evidence_atoms: Set[str] = field(default_factory=set)
    represented_evidence_atoms: Set[str] = field(default_factory=set)
    schema_validity: float = 1.0
    type_validity: float = 1.0
    key_validity: float = 1.0
    join_validity: float = 1.0
    entity_completeness: float = 1.0
    population_coverage: float = 1.0
    metamorphic_consistency: float = 1.0
    nl_sql_consistency: float = 1.0
    candidate_agreement: float = 1.0
    stochastic_scores: List[float] = field(default_factory=list)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _precision_proxy(cells: Sequence[CellEvidence]) -> float:
    if not cells:
        return 0.0
    return sum(cell.supported for cell in cells) / len(cells)


def _recall_proxy(observation: PilotObservation) -> float:
    relevant = observation.relevant_evidence_atoms
    if not relevant:
        # No relevant anchors found means completeness is unknown, not perfect.
        return 0.0
    return len(relevant & observation.represented_evidence_atoms) / len(relevant)


def _validity_product(observation: PilotObservation) -> Tuple[float, Dict[str, float]]:
    components = {
        "schema_validity": _clamp(observation.schema_validity),
        "type_validity": _clamp(observation.type_validity),
        "key_validity": _clamp(observation.key_validity),
        "join_validity": _clamp(observation.join_validity),
        "entity_completeness": _clamp(observation.entity_completeness),
        "population_coverage": _clamp(observation.population_coverage),
        "metamorphic_consistency": _clamp(observation.metamorphic_consistency),
        "nl_sql_consistency": _clamp(observation.nl_sql_consistency),
    }
    # Geometric mean prevents one failure from being hidden by unrelated high
    # signals while avoiding an excessively brittle raw product.
    if any(value <= 0 for value in components.values()):
        return 0.0, components
    validity = math.prod(components.values()) ** (1.0 / len(components))
    return validity, components


def _document_bootstrap_uncertainty(
    observation: PilotObservation,
    *,
    rounds: int,
    seed: int,
) -> float:
    by_document: Dict[str, List[CellEvidence]] = {}
    for cell in observation.cells:
        key = cell.document_id or f"row:{cell.row_identity}"
        by_document.setdefault(key, []).append(cell)
    documents = list(by_document)
    scores: List[float] = list(observation.stochastic_scores)
    if documents and rounds > 1:
        rng = random.Random(seed)
        for _ in range(rounds):
            sample = [rng.choice(documents) for _ in documents]
            sampled_cells = [
                cell for document_id in sample for cell in by_document[document_id]
            ]
            scores.append(_precision_proxy(sampled_cells))
    if documents:
        finite_sample_floor = min(
            1.0, 0.5 / math.sqrt(len(documents))
        )
    else:
        finite_sample_floor = 1.0
    bootstrap_spread = pstdev(scores) if len(scores) >= 2 else 0.0
    sampling_uncertainty = max(bootstrap_spread, finite_sample_floor)
    disagreement_uncertainty = 1.0 - _clamp(observation.candidate_agreement)
    return _clamp(max(sampling_uncertainty, disagreement_uncertainty))


def estimate_query_risk(
    observation: PilotObservation,
    *,
    bootstrap_rounds: int = 100,
    seed: int = 42,
) -> QualityEstimate:
    """Produce an interpretable F1-like proxy and conservative uncertainty."""
    precision = _precision_proxy(observation.cells)
    recall = _recall_proxy(observation)
    validity, validity_components = _validity_product(observation)
    uncertainty = _document_bootstrap_uncertainty(
        observation, rounds=bootstrap_rounds, seed=seed
    )
    components = {
        **validity_components,
        "candidate_agreement": _clamp(observation.candidate_agreement),
        "supported_cells": float(sum(cell.supported for cell in observation.cells)),
        "returned_cells": float(len(observation.cells)),
        "relevant_evidence_atoms": float(len(observation.relevant_evidence_atoms)),
        "represented_evidence_atoms": float(
            len(
                observation.relevant_evidence_atoms
                & observation.represented_evidence_atoms
            )
        ),
    }
    return QualityEstimate(
        query_id=observation.query_id,
        config_id=observation.config_id,
        precision_proxy=_clamp(precision),
        recall_proxy=_clamp(recall),
        validity=_clamp(validity),
        uncertainty=uncertainty,
        sample_size=len(
            {cell.document_id or cell.row_identity for cell in observation.cells}
        ),
        components=components,
    )


def aggregate_pilot_estimates(
    observations: Iterable[PilotObservation],
    *,
    bootstrap_rounds: int = 100,
    seed: int = 42,
) -> Dict[Tuple[str, str], QualityEstimate]:
    result: Dict[Tuple[str, str], QualityEstimate] = {}
    for offset, observation in enumerate(observations):
        key = (observation.query_id, observation.config_id)
        if key in result:
            raise ValueError(f"duplicate pilot observation: {key}")
        result[key] = estimate_query_risk(
            observation,
            bootstrap_rounds=bootstrap_rounds,
            seed=seed + offset,
        )
    return result


def workload_mean_lcb(
    estimates: Mapping[Tuple[str, str], QualityEstimate],
    config_id: str,
    *,
    beta: float = 1.0,
) -> float:
    values = [
        estimate.lower_confidence_bound(beta)
        for (_query_id, cid), estimate in estimates.items()
        if cid == config_id
    ]
    return mean(values) if values else 0.0

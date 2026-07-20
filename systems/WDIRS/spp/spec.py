"""Formal objects for offline workload-aware relational synthesis.

This module is intentionally ground-truth-free.  It represents candidate
``<schema, population, preprocessing>`` configurations, query requirements,
conservative quality estimates, and the portfolio objective used by the
deployable optimizer.  UDA-Bench ground truth belongs only in ``evaluation``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from spp.population_config import PopulationConfig


@dataclass(frozen=True)
class QueryRequirement:
    query_id: str
    text: str
    entities: Tuple[str, ...] = ()
    attributes: Tuple[str, ...] = ()
    attribute_bindings: Tuple[Tuple[str, str], ...] = ()
    relationships: Tuple[Tuple[str, str, str], ...] = ()
    operators: Tuple[str, ...] = ()
    units: Tuple[str, ...] = ()

    def required_symbols(self) -> Set[str]:
        symbols = set(self.entities) | set(self.attributes)
        for left, _relation, right in self.relationships:
            symbols.update((left, right))
        return symbols


@dataclass(frozen=True)
class RelationSpec:
    name: str
    attributes: Tuple[str, ...]
    primary_key: Optional[str] = None
    foreign_keys: Tuple[Tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class SchemaDesign:
    pattern: str
    relations: Tuple[RelationSpec, ...]
    covered_query_ids: Tuple[str, ...]
    description: str = ""

    @property
    def schema_id(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        return f"{self.pattern}:{digest}"

    def symbols(self) -> Set[str]:
        result: Set[str] = set()
        for relation in self.relations:
            result.add(relation.name)
            result.update(relation.attributes)
            for column, target_table, target_column in relation.foreign_keys:
                result.update((column, target_table, target_column))
        return result

    def covers(self, requirement: QueryRequirement) -> bool:
        return requirement.query_id in self.covered_query_ids and (
            requirement.required_symbols() <= self.symbols()
        )


@dataclass(frozen=True)
class PreprocessingPolicy:
    strategy: str
    chunk_size: Optional[int] = None
    chunk_overlap: int = 0
    preserve_document_metadata: bool = True

    def __post_init__(self) -> None:
        if self.strategy not in {"whole_document", "chunked"}:
            raise ValueError(f"Unsupported preprocessing strategy: {self.strategy}")
        if self.strategy == "whole_document" and self.chunk_size is not None:
            raise ValueError("whole_document cannot specify chunk_size")
        if self.strategy == "chunked" and (self.chunk_size is None or self.chunk_size <= 0):
            raise ValueError("chunked preprocessing requires positive chunk_size")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")
        if self.chunk_size is not None and self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

    @property
    def policy_id(self) -> str:
        if self.strategy == "whole_document":
            return "pre=whole_document"
        return f"pre=chunked:{self.chunk_size}:{self.chunk_overlap}"


@dataclass(frozen=True)
class SynthesisConfig:
    schema: SchemaDesign
    population: PopulationConfig
    preprocessing: PreprocessingPolicy

    @property
    def config_id(self) -> str:
        return (
            f"schema={self.schema.schema_id}|{self.preprocessing.policy_id}|"
            f"{self.population.config_id}"
        )


@dataclass(frozen=True)
class QualityEstimate:
    query_id: str
    config_id: str
    precision_proxy: float
    recall_proxy: float
    validity: float
    uncertainty: float
    sample_size: int
    components: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("precision_proxy", "recall_proxy", "validity", "uncertainty"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0,1], got {value}")
        if self.sample_size < 0:
            raise ValueError("sample_size cannot be negative")

    @property
    def f_proxy(self) -> float:
        denominator = self.precision_proxy + self.recall_proxy
        if denominator <= 0:
            return 0.0
        return (
            2.0 * self.precision_proxy * self.recall_proxy / denominator
        ) * self.validity

    def lower_confidence_bound(self, beta: float = 1.0) -> float:
        return max(0.0, self.f_proxy - beta * self.uncertainty)

    def upper_confidence_bound(self, beta: float = 1.0) -> float:
        return min(1.0, self.f_proxy + beta * self.uncertainty)


@dataclass(frozen=True)
class FrozenPortfolio:
    selected_config_ids: Tuple[str, ...]
    query_to_config: Mapping[str, str]
    query_scores: Mapping[str, float]
    construction_tokens: int
    objective_value: float

    def validate(
        self,
        requirements: Sequence[QueryRequirement],
        configs: Mapping[str, SynthesisConfig],
        token_budget: int,
    ) -> None:
        if self.construction_tokens > token_budget:
            raise ValueError("portfolio exceeds token budget")
        selected = set(self.selected_config_ids)
        if selected != set(self.query_to_config.values()):
            raise ValueError("selected configs and routing map disagree")
        for requirement in requirements:
            config_id = self.query_to_config.get(requirement.query_id)
            if not config_id:
                raise ValueError(f"query {requirement.query_id} has no route")
            config = configs.get(config_id)
            if config is None or not config.schema.covers(requirement):
                raise ValueError(
                    f"route for {requirement.query_id} is not schema-compatible"
                )


def conservative_portfolio_objective(
    requirements: Iterable[QueryRequirement],
    selected_config_ids: Iterable[str],
    estimates: Mapping[Tuple[str, str], QualityEstimate],
    *,
    beta: float = 1.0,
    query_weights: Optional[Mapping[str, float]] = None,
) -> float:
    """Facility-location objective using only conservative proxy scores."""
    selected = tuple(selected_config_ids)
    weights = query_weights or {}
    total = 0.0
    for requirement in requirements:
        candidates = [
            estimates[(requirement.query_id, config_id)].lower_confidence_bound(beta)
            for config_id in selected
            if (requirement.query_id, config_id) in estimates
        ]
        total += float(weights.get(requirement.query_id, 1.0)) * (
            max(candidates) if candidates else 0.0
        )
    return total


def route_by_conservative_quality(
    requirements: Sequence[QueryRequirement],
    selected_configs: Sequence[SynthesisConfig],
    estimates: Mapping[Tuple[str, str], QualityEstimate],
    *,
    beta: float = 1.0,
    quality_floor: float = 0.0,
) -> Tuple[Dict[str, str], Dict[str, float]]:
    """Choose a fixed, schema-compatible route for every workload query."""
    routing: Dict[str, str] = {}
    scores: Dict[str, float] = {}
    for requirement in requirements:
        ranked: List[Tuple[float, str]] = []
        for config in selected_configs:
            if not config.schema.covers(requirement):
                continue
            estimate = estimates.get((requirement.query_id, config.config_id))
            if estimate is None:
                continue
            ranked.append(
                (estimate.lower_confidence_bound(beta), config.config_id)
            )
        if not ranked:
            raise ValueError(f"no measured compatible route for {requirement.query_id}")
        score, config_id = max(ranked, key=lambda item: (item[0], item[1]))
        if score < quality_floor:
            raise ValueError(
                f"query {requirement.query_id} has LCB {score:.4f} below floor "
                f"{quality_floor:.4f}"
            )
        routing[requirement.query_id] = config_id
        scores[requirement.query_id] = score
    return routing, scores

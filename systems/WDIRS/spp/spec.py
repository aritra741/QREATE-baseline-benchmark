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
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from spp.population_config import PopulationConfig


@dataclass(frozen=True)
class AttributeRef:
    entity: str
    attribute: str
    semantic_type: str = "text"

    def __post_init__(self) -> None:
        if self.semantic_type not in {
            "text", "integer", "real", "date", "boolean"
        }:
            raise ValueError(
                f"unsupported semantic type: {self.semantic_type}"
            )


_SEMANTIC_TYPES = {"text", "integer", "real", "date", "boolean"}
_BINARY_EXPRESSION_OPERATORS = {
    "+", "-", "*", "/", "%",
    "=", "!=", "<", "<=", ">", ">=",
    "and", "or", "between", "in",
    "like", "ilike",
}
_UNARY_EXPRESSION_OPERATORS = {"not", "neg", "is_null", "is_not_null"}
_CAST_TYPES = {"integer", "real", "text", "numeric", "date", "boolean"}
_SCALAR_FUNCTIONS = {
    "trim", "lower", "upper", "coalesce", "nullif", "abs", "round",
}


@dataclass(frozen=True)
class ExpressionSpec:
    """Safe scalar-expression AST used by deterministic query plans.

    The AST is deliberately allowlisted and contains no raw SQL fragments.
    Physical columns remain explicit :class:`AttributeRef` leaves so schema
    coverage, contract extraction, and provenance can walk dependencies.
    """

    kind: str
    semantic_type: str = "text"
    attribute: Optional[AttributeRef] = None
    value: object = None
    operator: str = ""
    arguments: Tuple["ExpressionSpec", ...] = ()
    branches: Tuple[Tuple["ExpressionSpec", "ExpressionSpec"], ...] = ()
    default: Optional["ExpressionSpec"] = None
    alias: str = ""

    def __post_init__(self) -> None:
        if self.kind not in {
            "column", "literal", "binary", "unary", "cast", "case", "function",
        }:
            raise ValueError(f"unsupported expression kind: {self.kind}")
        if self.semantic_type not in _SEMANTIC_TYPES:
            raise ValueError(
                f"unsupported expression semantic type: {self.semantic_type}"
            )
        if self.kind == "column":
            if self.attribute is None:
                raise ValueError("column expression requires an attribute")
            if (
                self.arguments
                or self.branches
                or self.default is not None
                or self.operator
            ):
                raise ValueError("column expression cannot have child operations")
        elif self.kind == "literal":
            if self.attribute is not None or self.arguments or self.branches:
                raise ValueError("literal expression cannot have dependencies")
        elif self.kind == "binary":
            if self.operator not in _BINARY_EXPRESSION_OPERATORS:
                raise ValueError(
                    f"unsupported binary expression operator: {self.operator}"
                )
            if len(self.arguments) < 2:
                raise ValueError("binary expression requires at least two arguments")
        elif self.kind == "unary":
            if self.operator not in _UNARY_EXPRESSION_OPERATORS:
                raise ValueError(
                    f"unsupported unary expression operator: {self.operator}"
                )
            if len(self.arguments) != 1:
                raise ValueError("unary expression requires one argument")
        elif self.kind == "cast":
            if self.operator not in _CAST_TYPES:
                raise ValueError(f"unsupported cast target: {self.operator}")
            if len(self.arguments) != 1:
                raise ValueError("cast expression requires one argument")
        elif self.kind == "case":
            if not self.branches:
                raise ValueError("CASE expression requires at least one branch")
            if self.attribute is not None or self.arguments or self.operator:
                raise ValueError("CASE expression uses branches/default only")
        elif self.kind == "function":
            if self.operator not in _SCALAR_FUNCTIONS:
                raise ValueError(
                    f"unsupported scalar function: {self.operator}"
                )
            if not self.arguments:
                raise ValueError("scalar function requires arguments")

    def attributes(self) -> Tuple[AttributeRef, ...]:
        result: List[AttributeRef] = []

        def add(reference: AttributeRef) -> None:
            if reference not in result:
                result.append(reference)

        def visit(expression: Optional["ExpressionSpec"]) -> None:
            if expression is None:
                return
            if expression.attribute is not None:
                add(expression.attribute)
            for argument in expression.arguments:
                visit(argument)
            for condition, value in expression.branches:
                visit(condition)
                visit(value)
            visit(expression.default)

        visit(self)
        return tuple(result)


PlanExpression = Union[AttributeRef, ExpressionSpec]


def expression_attributes(value: PlanExpression) -> Tuple[AttributeRef, ...]:
    if isinstance(value, AttributeRef):
        return (value,)
    return value.attributes()


def map_expression_references(
    value: PlanExpression,
    mapper: Callable[[AttributeRef], AttributeRef],
) -> PlanExpression:
    """Return ``value`` with every physical-column leaf rewritten."""

    if isinstance(value, AttributeRef):
        return mapper(value)
    return ExpressionSpec(
        kind=value.kind,
        semantic_type=value.semantic_type,
        attribute=(
            mapper(value.attribute) if value.attribute is not None else None
        ),
        value=value.value,
        operator=value.operator,
        arguments=tuple(
            map_expression_references(argument, mapper)
            for argument in value.arguments
        ),
        branches=tuple(
            (
                map_expression_references(condition, mapper),
                map_expression_references(result, mapper),
            )
            for condition, result in value.branches
        ),
        default=(
            map_expression_references(value.default, mapper)
            if value.default is not None
            else None
        ),
        alias=value.alias,
    )


@dataclass(frozen=True)
class AggregateSpec:
    function: str
    attribute: Optional[AttributeRef] = None
    alias: str = ""
    distinct: bool = False
    expression: Optional[ExpressionSpec] = None

    def __post_init__(self) -> None:
        if self.function not in {"count", "sum", "avg", "min", "max"}:
            raise ValueError(f"unsupported aggregate: {self.function}")
        if (
            self.function != "count"
            and self.attribute is None
            and self.expression is None
        ):
            raise ValueError(f"{self.function} requires an attribute")


@dataclass(frozen=True)
class HavingSpec:
    aggregate: AggregateSpec
    operator: str
    value: object

    def __post_init__(self) -> None:
        if self.operator not in {"=", "!=", "<", "<=", ">", ">="}:
            raise ValueError(f"unsupported HAVING operator: {self.operator}")


@dataclass(frozen=True)
class PredicateSpec:
    kind: str = "predicate"
    attribute: Optional[AttributeRef] = None
    operator: str = "="
    value: object = None
    children: Tuple["PredicateSpec", ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"predicate", "and", "or"}:
            raise ValueError(f"unsupported predicate kind: {self.kind}")
        if self.kind == "predicate":
            if self.attribute is None:
                raise ValueError("leaf predicate requires an attribute")
            if self.operator not in {
                "=", "!=", "<", "<=", ">", ">=", "contains",
                "like", "ilike", "is_null", "is_not_null",
            }:
                raise ValueError(
                    f"unsupported predicate operator: {self.operator}"
                )
            if self.children:
                raise ValueError("leaf predicate cannot have children")
        elif not self.children:
            raise ValueError("boolean predicate requires children")


@dataclass(frozen=True)
class JoinSpec:
    left: AttributeRef
    right: AttributeRef
    join_type: str = "inner"
    left_expression: Optional[ExpressionSpec] = None
    right_expression: Optional[ExpressionSpec] = None
    match_mode: str = "equality"

    def __post_init__(self) -> None:
        if self.join_type not in {"inner", "left"}:
            raise ValueError(f"unsupported join type: {self.join_type}")
        if self.match_mode not in {"equality", "token_membership"}:
            raise ValueError(
                f"unsupported join match mode: {self.match_mode}"
            )


@dataclass(frozen=True)
class QueryPlan:
    projections: Tuple[PlanExpression, ...] = ()
    group_by: Tuple[PlanExpression, ...] = ()
    aggregates: Tuple[AggregateSpec, ...] = ()
    predicate: Optional[PredicateSpec] = None
    joins: Tuple[JoinSpec, ...] = ()
    having: Tuple[HavingSpec, ...] = ()

    def attributes(self) -> Tuple[AttributeRef, ...]:
        result: List[AttributeRef] = []

        def add(reference: Optional[AttributeRef]) -> None:
            if reference is not None and reference not in result:
                result.append(reference)

        def visit(predicate: Optional[PredicateSpec]) -> None:
            if predicate is None:
                return
            add(predicate.attribute)
            for child in predicate.children:
                visit(child)

        for expression in (*self.projections, *self.group_by):
            for reference in expression_attributes(expression):
                add(reference)
        for aggregate in self.aggregates:
            add(aggregate.attribute)
            if aggregate.expression is not None:
                for reference in aggregate.expression.attributes():
                    add(reference)
        for condition in self.having:
            add(condition.aggregate.attribute)
            if condition.aggregate.expression is not None:
                for reference in condition.aggregate.expression.attributes():
                    add(reference)
        visit(self.predicate)
        for join in self.joins:
            add(join.left)
            add(join.right)
            for expression in (
                join.left_expression,
                join.right_expression,
            ):
                if expression is not None:
                    for reference in expression.attributes():
                        add(reference)
        return tuple(result)


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
    plan: Optional[QueryPlan] = None

    def required_symbols(self) -> Set[str]:
        symbols = set(self.entities) | set(self.attributes)
        for left, _relation, right in self.relationships:
            symbols.update((left, right))
        if self.plan:
            for reference in self.plan.attributes():
                symbols.update((reference.entity, reference.attribute))
        return symbols


@dataclass(frozen=True)
class RelationSpec:
    name: str
    attributes: Tuple[str, ...]
    primary_key: Optional[str] = None
    foreign_keys: Tuple[Tuple[str, str, str], ...] = ()
    semantic_types: Tuple[Tuple[str, str], ...] = ()

    def semantic_type(self, attribute: str) -> str:
        return dict(self.semantic_types).get(attribute, "text")


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

    @property
    def route_eligible(self) -> bool:
        """Whether a hard workload contract permits serving this query."""

        return float(self.components.get("contract_route_eligible", 1.0)) > 0.0

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
            and estimates[
                (requirement.query_id, config_id)
            ].route_eligible
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
            if estimate is None or not estimate.route_eligible:
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

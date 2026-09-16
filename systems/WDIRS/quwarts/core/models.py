"""Pydantic data contracts. Each model carries ``schema_version``."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "1"


class VersionedModel(BaseModel):
    schema_version: str = SCHEMA_VERSION


class Role(str, Enum):
    KEY = "key"
    JOIN = "join"
    GROUP = "group"
    PREDICATE = "predicate"
    AGG_ADDITIVE = "agg_additive"
    AGG_DISTINCT = "agg_distinct"
    AGG_EXTREMAL = "agg_extremal"
    PROJECT = "project"


class TemplateShape(str, Enum):
    FILTERED_AGGREGATE = "filtered_aggregate"
    FILTERED_PROJECTION = "filtered_projection"
    UNFILTERED_AGGREGATE = "unfiltered_aggregate"
    BASE_CARDINALITY = "base_cardinality"
    ANTI_JOIN = "anti_join"
    CROSS_ATTRIBUTE_FILTER = "cross_attribute_filter"
    UNKNOWN = "unknown"


class LogicalAttribute(VersionedModel):
    name: str
    entity_type: str
    dtype: Literal["string", "numeric", "date", "categorical", "multivalued"]
    unit_domain: str | None = None
    nullable: bool = True


class DerivedExpression(VersionedModel):
    """Compiled view over base attributes. Never an evidence-layer attribute."""

    alias: str
    entity_type: str
    base_attributes: list[str]
    sql: str = ""


class LogicalRelationship(VersionedModel):
    name: str
    from_entity: str
    to_entity: str
    from_attribute: str
    to_attribute: str


class LogicalSchema(VersionedModel):
    id: str
    entity_types: list[str]
    attributes: list[LogicalAttribute]
    relationships: list[LogicalRelationship]
    identity_grain: dict[str, str]
    expressions: list[DerivedExpression] = Field(default_factory=list)


class PredicateRange(VersionedModel):
    attribute: str
    op: str
    values: list[Any] = Field(default_factory=list)


class SliceSpec(VersionedModel):
    kind: Literal["full", "ranges"] = "full"
    ranges: list[PredicateRange] = Field(default_factory=list)

    def union(self, other: "SliceSpec") -> "SliceSpec":
        if self.kind == "full" or other.kind == "full":
            return SliceSpec(kind="full")
        merged = list(self.ranges) + list(other.ranges)
        return SliceSpec(kind="ranges", ranges=merged)

    def contains_constants(self, constants: list[Any], op: str | None = None) -> bool:
        if self.kind == "full":
            return True
        if not constants:
            return True
        query = _interval(op, constants)
        if query is not None:
            covered: list[tuple[float, float]] = []
            for item in self.ranges:
                interval = _interval(item.op, item.values)
                if interval is not None:
                    covered.append(interval)
            if covered and _interval_subset(query, covered):
                return True
        observed: set[str] = set()
        for item in self.ranges:
            for value in item.values:
                observed.add(_norm_const(value))
        return all(_norm_const(value) in observed for value in constants)


def _norm_const(value: Any) -> str:
    return str(value).strip().lower()


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def _interval(op: str | None, values: list[Any]) -> tuple[float, float] | None:
    nums = [item for item in (_as_float(value) for value in values) if item is not None]
    if not nums or not op:
        return None
    token = op.strip().upper()
    lo, hi = float("-inf"), float("inf")
    if token in {"BETWEEN"}:
        if len(nums) < 2:
            return None
        return (min(nums[0], nums[1]), max(nums[0], nums[1]))
    if token in {">"}:
        return (nums[0], hi)
    if token in {">=", "GTE"}:
        return (nums[0], hi)
    if token in {"<"}:
        return (lo, nums[0])
    if token in {"<=", "LTE"}:
        return (lo, nums[0])
    if token in {"=", "EQ"}:
        return (nums[0], nums[0])
    return None


def _interval_subset(query: tuple[float, float], covered: list[tuple[float, float]]) -> bool:
    qlo, qhi = query
    return any(qlo >= clo and qhi <= chi for clo, chi in covered)


class ParamSlot(VersionedModel):
    slot_id: str
    attribute: str
    op: str
    dtype: str
    observed_constants: list[Any] = Field(default_factory=list)


class Template(VersionedModel):
    id: str
    canonical_sql: str
    param_slots: list[ParamSlot] = Field(default_factory=list)
    statement_ids: list[str] = Field(default_factory=list)
    freq: int = 1
    roles_by_attribute: dict[str, set[Role]] = Field(default_factory=dict)
    slice_safe: bool = False
    shape: TemplateShape = TemplateShape.UNKNOWN
    raw_sql: str = ""
    entity_types: set[str] = Field(default_factory=set)
    aggregated_attributes: set[str] = Field(default_factory=set)
    predicate_attributes: set[str] = Field(default_factory=set)
    join_pairs: list[tuple[str, str]] = Field(default_factory=list)
    group_attributes: list[str] = Field(default_factory=list)
    project_attributes: list[str] = Field(default_factory=list)
    has_count_star: bool = False
    binding_errors: list[str] = Field(default_factory=list)


class AttributeStats(VersionedModel):
    n_rows: int
    n_groups: int
    group_size: float
    n_distinct: int
    multiplicity: float
    rho: float
    n_scored_columns: int


class AttributeRequirement(VersionedModel):
    name: str
    entity_type: str
    dtype: str
    roles: set[Role] = Field(default_factory=set)
    templates: list[str] = Field(default_factory=list)
    freq_weight: float = 0.0
    finest_grain: str = "mention"
    required_forms: set[str] = Field(default_factory=set)
    slice: SliceSpec = Field(default_factory=SliceSpec)
    declared_domain: list[str] = Field(default_factory=list)
    stats: AttributeStats | None = None
    amp: float | None = None


class Workload(VersionedModel):
    templates: list[Template]
    requirements: dict[str, AttributeRequirement]
    binding_failures: list[str] = Field(default_factory=list)
    in_lists: dict[str, list[list[str]]] = Field(default_factory=dict)
    literal_aliases: dict[str, str] = Field(default_factory=dict)
    join_types: dict[str, str] = Field(default_factory=dict)


class Presupposition(VersionedModel):
    entity_type: str
    attribute: str | None
    module: Literal["er", "norm", "unit", "type", "miss", "grain"]
    demand: str
    destructive: bool


class ConflictEdge(VersionedModel):
    template_a: str
    template_b: str
    cell: tuple[str, str, str]
    demands: tuple[str, str]
    destructive: bool


class ConflictCluster(VersionedModel):
    id: str
    template_ids: list[str]
    resolved_demands: dict[str, str]


class ModuleConfig(VersionedModel):
    strategy: str
    params: dict[str, Any] = Field(default_factory=dict)


class PopulationPolicy(VersionedModel):
    er: dict[str, ModuleConfig] = Field(default_factory=dict)
    norm: dict[str, ModuleConfig] = Field(default_factory=dict)
    unit: dict[str, ModuleConfig] = Field(default_factory=dict)
    type: dict[str, ModuleConfig] = Field(default_factory=dict)
    miss: dict[str, ModuleConfig] = Field(default_factory=dict)
    grain: dict[str, str] = Field(default_factory=dict)


class PreprocessPolicy(VersionedModel):
    mode: Literal["whole_document", "fixed_chunk", "semantic_chunk"]
    chunk_tokens: int | None = None
    overlap_tokens: int | None = None
    carry_metadata: list[str] = Field(default_factory=list)


class Relation(VersionedModel):
    name: str
    attributes: list[str]
    entity_type: str | None = None


class ForeignKey(VersionedModel):
    from_relation: str
    from_attrs: list[str]
    to_relation: str
    to_attrs: list[str]


class FunctionalDependency(VersionedModel):
    relation: str
    determinant: list[str]
    dependent: list[str]


class DenialConstraint(VersionedModel):
    relation: str
    description: str
    columns: list[str]


class PhysicalSchema(VersionedModel):
    id: str
    pattern: Literal["denormalized", "star", "snowflake"]
    relations: list[Relation]
    primary_keys: dict[str, list[str]]
    foreign_keys: list[ForeignKey]
    declared_fds: list[FunctionalDependency]
    declared_dcs: list[DenialConstraint]
    covered_attributes: set[str]


class Configuration(VersionedModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())
    id: str
    schema_: PhysicalSchema = Field(alias="schema")
    pop: PopulationPolicy
    pre: PreprocessPolicy
    cluster_id: str


class CoverageSet(VersionedModel):
    attribute_ranges: dict[str, SliceSpec]
    attributes_present: set[str]
    grain: dict[str, str]
    forms: dict[str, set[str]]
    corpus_fingerprint: str


class SurrogateReport(VersionedModel):
    U_hat: float
    signals: dict[str, float]
    weighted: dict[str, float] = Field(default_factory=dict)


class MaterializedDB(VersionedModel):
    config_id: str
    sqlite_path: str
    sha256: str
    row_counts: dict[str, int]
    tokens_spent: int
    coverage: CoverageSet
    surrogate: SurrogateReport


class EvidenceRecord(VersionedModel):
    key: str
    segment_id: str
    doc_id: str
    template_cluster_id: str | None = None
    attribute: str
    surface_value: str | None = None
    parsed_value: Any | None = None
    original_unit: str | None = None
    null_reason: str | None = None
    candidate_keys: dict[str, str] = Field(default_factory=dict)
    span: tuple[int, int] | None = None
    confidence: float | None = None
    extractor_cfg_hash: str
    quality_tier: Literal["cheap", "expensive"]
    stage: Literal[1, 2, 3]
    tokens_spent: int = 0


class SourceDocument(VersionedModel):
    doc_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrozenPortfolio(VersionedModel):
    configurations: list[Configuration]
    route: dict[str, str]
    rewrites: dict[str, str]
    databases: list[MaterializedDB]
    tokens_spent: int
    cache_hit_rate: float
    seed: int
    logical_schema: LogicalSchema

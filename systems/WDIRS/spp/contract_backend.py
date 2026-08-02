"""Contract-driven, shared-evidence backend for offline relational synthesis.

The backend compiles one :class:`WorkloadContract`, creates its shared relation
graph, and instantiates :class:`ContractExtractor` with the run's budgeted LLM
client and evidence store during ``prepare``.  Validated evidence is extracted
once and reused by every non-equivalent raw or semantic candidate.  Candidate
portfolio construction remains the responsibility of :mod:`spp.optimizer`.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from spp.budget_ledger import BudgetExhausted, GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.contract_extractor import ContractExtractor
from spp.contract_validation import (
    AdaptiveRepairAdmission,
    ValidationIssue,
    targeted_repair_targets,
    validate_extraction,
)
from spp.evidence_store import (
    CellProvenance,
    ContractEvidence,
    ConflictRecord,
    DerivationLineage,
    EvidenceAnchor,
    EvidenceStore,
    ValidationOutcome as StoredValidationOutcome,
)
from spp.optimizer import PilotResult, canonical_output_signature
from spp.population_config import PopulationConfig
from spp.query_plan_compiler import compile_query_plan
from spp.query_quality import (
    QueryAssessment,
    QueryCompilationError,
    QueryExecution,
    QueryExecutionError,
    bootstrap_output_stability,
    compile_typed_plan,
    execute_readonly,
    assess_workload_quality,
)
from spp.schema_design import generate_schema_designs
from spp.schema_materializer import (
    reshape_tables,
    temporary_work_dir,
    write_sqlite_database,
)
from spp.spec import (
    PreprocessingPolicy,
    QualityEstimate,
    QueryRequirement,
    RelationSpec,
    SchemaDesign,
    SynthesisConfig,
)
from spp.workload_intent import WorkloadIntent
from spp.workload_contract import (
    WorkloadContract,
    compile_workload_contract as _default_contract_compiler,
)


BACKEND_VERSION = 3


class ContractIntegrationError(RuntimeError):
    """The external contract compiler or extractor has an incompatible API."""


@dataclass(frozen=True)
class ContractDocument:
    document_id: str
    text: str
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, order=True)
class RelationEdge:
    left_relation: str
    left_column: str
    right_relation: str
    right_column: str
    join_type: str = "inner"

    def __post_init__(self) -> None:
        if self.join_type not in {"inner", "left"}:
            raise ValueError(f"unsupported graph join type: {self.join_type}")

    @property
    def join_pair(self) -> Tuple[str, str, str, str]:
        return (
            self.left_relation,
            self.left_column,
            self.right_relation,
            self.right_column,
        )


@dataclass(frozen=True)
class WorkloadRelationGraph:
    relations: Tuple[RelationSpec, ...]
    edges: Tuple[RelationEdge, ...]
    covered_query_ids: Tuple[str, ...]
    pattern: str = "snowflake"

    @property
    def join_pairs(self) -> Tuple[Tuple[str, str, str, str], ...]:
        return tuple(edge.join_pair for edge in self.edges)

    @property
    def schema(self) -> SchemaDesign:
        return SchemaDesign(
            pattern=self.pattern,
            relations=self.relations,
            covered_query_ids=self.covered_query_ids,
            description=(
                "Shared relation graph compiled from the complete workload "
                "contract."
            ),
        )

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            _jsonable(asdict(self)),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SharedCellEvidence:
    relation: str
    row_identity: str
    column: str
    value: object
    anchor_id: str
    document_id: str
    anchor_text: str
    start: int
    end: int
    entailed: bool
    span_restored: bool

    @property
    def supported(self) -> bool:
        return self.entailed and self.span_restored


@dataclass(frozen=True)
class SharedExtraction:
    raw_tables: Mapping[str, Tuple[Mapping[str, object], ...]]
    evidence: Tuple[SharedCellEvidence, ...]
    semantic_tables: Optional[
        Mapping[str, Tuple[Mapping[str, object], ...]]
    ] = None
    metadata: Mapping[str, object] = field(default_factory=dict)


ContractCompiler = Callable[..., Any]


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest()}
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        public = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
        if public:
            return _jsonable(public)
    return str(value)


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _member(value: object, *names: str, default: object = None) -> object:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _normalize_documents(
    documents: Sequence[ContractDocument | Mapping[str, object] | str | object],
) -> Tuple[ContractDocument, ...]:
    normalized: Dict[str, ContractDocument] = {}
    for item in documents:
        if isinstance(item, ContractDocument):
            document = item
        elif isinstance(item, str):
            digest = hashlib.sha256(item.encode("utf-8")).hexdigest()
            document = ContractDocument(
                document_id=f"document:{digest[:16]}",
                text=item,
            )
        else:
            text = _member(item, "text", "content", "body", default="")
            document_id = _member(
                item,
                "document_id",
                "id",
                "name",
                "path",
                default="",
            )
            metadata = _member(item, "metadata", default={})
            rendered = str(text or "")
            if not document_id:
                digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
                document_id = f"document:{digest[:16]}"
            document = ContractDocument(
                document_id=str(document_id),
                text=rendered,
                metadata=(
                    dict(metadata)
                    if isinstance(metadata, Mapping)
                    else {"value": str(metadata)}
                ),
            )
        existing = normalized.get(document.document_id)
        if existing is not None and existing.text != document.text:
            raise ValueError(
                f"duplicate document id with different content: "
                f"{document.document_id!r}"
            )
        normalized[document.document_id] = document
    if not normalized:
        raise ValueError("ContractBackend requires at least one source document")
    return tuple(normalized[key] for key in sorted(normalized))


def _semantic_type(value: object) -> str:
    rendered = str(value or "text").strip().lower()
    aliases = {
        "int": "integer",
        "float": "real",
        "number": "real",
        "numeric": "real",
        "bool": "boolean",
        "datetime": "date",
    }
    rendered = aliases.get(rendered, rendered)
    return (
        rendered
        if rendered in {"text", "integer", "real", "date", "boolean"}
        else "text"
    )


def _foreign_keys(value: object) -> Tuple[Tuple[str, str, str], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    result = []
    for item in value:
        if isinstance(item, Mapping):
            column = _member(item, "column", "source_column", "left_column")
            table = _member(item, "target_table", "table", "right_relation")
            target = _member(
                item, "target_column", "reference_column", "right_column"
            )
            if column and table and target:
                result.append((str(column), str(table), str(target)))
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            result.append(tuple(str(part) for part in item[:3]))
    return tuple(result)


def _relation_from_value(
    value: object,
    *,
    fallback_name: str = "",
) -> Optional[RelationSpec]:
    if isinstance(value, RelationSpec):
        return value
    name = str(_member(value, "name", "relation", default=fallback_name) or "")
    raw_attributes = _member(value, "attributes", "columns", "fields", default=())
    types: Dict[str, str] = {}
    attributes: List[str] = []
    if isinstance(raw_attributes, Mapping):
        for column, declaration in raw_attributes.items():
            attributes.append(str(column))
            declared = (
                _member(declaration, "semantic_type", "type", default=declaration)
                if isinstance(declaration, Mapping)
                else declaration
            )
            types[str(column)] = _semantic_type(declared)
    elif isinstance(raw_attributes, (list, tuple, set)):
        for declaration in raw_attributes:
            if isinstance(declaration, str):
                attributes.append(declaration)
            else:
                column = _member(declaration, "name", "column")
                if column:
                    attributes.append(str(column))
                    types[str(column)] = _semantic_type(
                        _member(
                            declaration,
                            "semantic_type",
                            "type",
                            default="text",
                        )
                    )
    raw_types = _member(value, "semantic_types", "types", default={})
    if isinstance(raw_types, Mapping):
        types.update(
            {
                str(column): _semantic_type(declared)
                for column, declared in raw_types.items()
            }
        )
    elif isinstance(raw_types, (list, tuple)):
        for item in raw_types:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                types[str(item[0])] = _semantic_type(item[1])
    if not name or not attributes:
        return None
    primary_key = _member(value, "primary_key", "key", default=None)
    return RelationSpec(
        name=name,
        attributes=tuple(dict.fromkeys(attributes)),
        primary_key=str(primary_key) if primary_key else None,
        foreign_keys=_foreign_keys(
            _member(value, "foreign_keys", "references", default=())
        ),
        semantic_types=tuple(
            (column, types.get(column, "text"))
            for column in dict.fromkeys(attributes)
        ),
    )


def _contract_symbol_schema(contract: object) -> Optional[SchemaDesign]:
    """Translate the shipped WorkloadContract symbol graph to RelationSpec."""
    entities = _member(contract, "entities", default=())
    attributes = _member(contract, "attributes", default=())
    relationships = _member(contract, "relationships", default=())
    if not isinstance(entities, (list, tuple)) or not entities:
        return None
    entity_names = [
        str(_member(entity, "name", default="")).strip()
        for entity in entities
    ]
    entity_names = [name for name in entity_names if name]
    if not entity_names:
        return None
    attributes_by_entity: Dict[str, Dict[str, str]] = {
        name: {} for name in entity_names
    }
    identity_by_entity: Dict[str, List[str]] = {
        name: [] for name in entity_names
    }
    entity_lookup = {
        str(_member(entity, "name", default="")): entity for entity in entities
    }
    for name, entity in entity_lookup.items():
        identity_by_entity[name].extend(
            str(value)
            for value in (
                _member(entity, "identity_attributes", default=()) or ()
            )
            if str(value)
        )
    for attribute in attributes if isinstance(attributes, (list, tuple)) else ():
        name = str(_member(attribute, "name", default="")).strip()
        if not name:
            continue
        owners_value = _member(attribute, "owners", default=None)
        if callable(owners_value):
            owners_value = owners_value()
        if owners_value is None:
            owner = str(_member(attribute, "entity", default="")).strip()
            alternatives = _member(
                attribute, "entity_alternatives", default=()
            ) or ()
            owners = tuple(value for value in (owner, *alternatives) if value)
        else:
            owners = tuple(str(value) for value in (owners_value or ()))
        if not owners:
            owners = (entity_names[0],)
        semantic_types = tuple(
            str(value)
            for value in (
                _member(attribute, "semantic_types", default=("text",)) or ()
            )
        )
        declared = (
            semantic_types[0]
            if len(set(semantic_types)) == 1
            else (
                "real"
                if set(semantic_types) <= {"integer", "real"}
                else "text"
            )
        )
        for owner in owners:
            if owner in attributes_by_entity:
                attributes_by_entity[owner][name] = _semantic_type(declared)

    foreign_keys: Dict[str, List[Tuple[str, str, str]]] = {
        name: [] for name in entity_names
    }
    for relationship in (
        relationships if isinstance(relationships, (list, tuple)) else ()
    ):
        left = str(
            _member(relationship, "left_entity", default="")
        ).strip()
        right = str(
            _member(relationship, "right_entity", default="")
        ).strip()
        left_attributes = tuple(
            str(value)
            for value in (
                _member(relationship, "left_attributes", default=()) or ()
            )
        )
        right_attributes = tuple(
            str(value)
            for value in (
                _member(relationship, "right_attributes", default=()) or ()
            )
        )
        width = min(len(left_attributes), len(right_attributes))
        for index in range(width):
            left_column = left_attributes[index]
            right_column = right_attributes[index]
            if left not in attributes_by_entity or right not in attributes_by_entity:
                continue
            attributes_by_entity[left].setdefault(left_column, "text")
            attributes_by_entity[right].setdefault(right_column, "text")
            identity_by_entity[left].append(left_column)
            identity_by_entity[right].append(right_column)
            foreign_keys[left].append((left_column, right, right_column))

    relations = []
    for entity in entity_names:
        fields = attributes_by_entity[entity]
        identity_candidates = [
            value
            for value in dict.fromkeys(identity_by_entity[entity])
            if value
        ]
        if identity_candidates:
            primary_key = identity_candidates[0]
        else:
            primary_key = next(
                (
                    candidate
                    for candidate in (
                        f"{entity}_id",
                        "id",
                        f"{entity}_name",
                        "name",
                    )
                    if candidate in fields
                ),
                f"{entity}_identity",
            )
        fields.setdefault(primary_key, "text")
        relations.append(
            RelationSpec(
                name=entity,
                attributes=tuple(sorted(fields)),
                primary_key=primary_key,
                foreign_keys=tuple(dict.fromkeys(foreign_keys[entity])),
                semantic_types=tuple(
                    (column, fields[column]) for column in sorted(fields)
                ),
            )
        )
    return SchemaDesign(
        pattern="snowflake",
        relations=tuple(relations),
        covered_query_ids=(),
        description="Relations compiled from workload-contract symbols.",
    )


def _contract_schema(contract: object) -> Optional[SchemaDesign]:
    entities_value = _member(contract, "entities", default=())
    attributes_value = _member(contract, "attributes", default=())
    if isinstance(entities_value, (list, tuple)) and entities_value:
        entities = [
            str(_member(entity, "name", default="") or "")
            for entity in entities_value
        ]
        entities = [entity for entity in entities if entity]
        declared_attributes: Dict[str, List[object]] = {
            entity: [] for entity in entities
        }
        for attribute in (
            attributes_value
            if isinstance(attributes_value, (list, tuple))
            else ()
        ):
            owners = [
                str(value)
                for value in (
                    _member(attribute, "owners", default=())
                    or (
                        _member(attribute, "entity", default=""),
                        *_member(
                            attribute,
                            "entity_alternatives",
                            default=(),
                        ),
                    )
                )
                if str(value)
            ]
            for owner in owners:
                if owner in declared_attributes:
                    declared_attributes[owner].append(attribute)

        def physical_type(attribute: object) -> str:
            alternatives = {
                _semantic_type(value)
                for value in (
                    _member(
                        attribute,
                        "semantic_types",
                        default=("text",),
                    )
                    or ("text",)
                )
            }
            if alternatives <= {"integer", "real"}:
                return "real" if "real" in alternatives else "integer"
            return next(iter(alternatives)) if len(alternatives) == 1 else "text"

        base_relations: Dict[str, RelationSpec] = {}
        for entity in entities:
            fields = declared_attributes[entity]
            names = tuple(
                dict.fromkeys(
                    str(_member(field, "name", default=""))
                    for field in fields
                    if str(_member(field, "name", default=""))
                )
            )
            if not names:
                names = ("__identity__",)
            normalized_entity = re.sub(
                r"[^a-z0-9]+", "_", entity.lower()
            ).strip("_")
            priority = (
                f"{normalized_entity}_id",
                "id",
                f"{normalized_entity}_name",
                "name",
                normalized_entity,
            )
            primary_key = next(
                (candidate for candidate in priority if candidate in names),
                "__identity__" if names == ("__identity__",) else None,
            )
            types_by_name = {
                str(_member(field, "name", default="")): physical_type(field)
                for field in fields
            }
            base_relations[entity] = RelationSpec(
                name=entity,
                attributes=names,
                primary_key=primary_key,
                semantic_types=tuple(
                    (name, types_by_name.get(name, "text"))
                    for name in names
                ),
            )
        if base_relations:
            foreign_keys: Dict[str, set[Tuple[str, str, str]]] = {
                name: set() for name in base_relations
            }
            relationships = _member(
                contract, "relationships", default=()
            )
            for relationship in (
                relationships
                if isinstance(relationships, (list, tuple))
                else ()
            ):
                left_name = str(
                    _member(relationship, "left_entity", default="")
                )
                right_name = str(
                    _member(relationship, "right_entity", default="")
                )
                left = base_relations.get(left_name)
                right = base_relations.get(right_name)
                if left is None or right is None:
                    continue
                pairs = _member(
                    relationship, "endpoint_pairs", default=()
                ) or ()
                for pair in pairs:
                    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                        continue
                    left_column, right_column = map(str, pair[:2])
                    if (
                        left_column not in left.attributes
                        or right_column not in right.attributes
                    ):
                        continue
                    if right.primary_key == right_column:
                        foreign_keys[left_name].add(
                            (left_column, right_name, right_column)
                        )
                    elif left.primary_key == left_column:
                        foreign_keys[right_name].add(
                            (right_column, left_name, left_column)
                        )
            relations = tuple(
                replace(
                    relation,
                    foreign_keys=tuple(
                        sorted(foreign_keys[relation.name])
                    ),
                )
                for relation in base_relations.values()
            )
            return SchemaDesign(
                pattern="snowflake",
                relations=relations,
                covered_query_ids=(),
                description=(
                    "Relationship-preserving schema compiled directly from "
                    "the workload contract."
                ),
            )

    schema = _member(contract, "schema", "schema_design")
    if isinstance(schema, SchemaDesign):
        return schema
    symbol_schema = _contract_symbol_schema(contract)
    if symbol_schema is not None:
        return symbol_schema
    graph = _member(contract, "relation_graph", "graph", default=contract)
    relations_value = _member(graph, "relations", "tables", default=None)
    if relations_value is None and schema is not None:
        relations_value = _member(schema, "relations", "tables", default=None)
    relations: List[RelationSpec] = []
    if isinstance(relations_value, Mapping):
        for name, declaration in sorted(
            relations_value.items(), key=lambda pair: str(pair[0])
        ):
            relation = _relation_from_value(
                declaration, fallback_name=str(name)
            )
            if relation is not None:
                relations.append(relation)
    elif isinstance(relations_value, (list, tuple)):
        for declaration in relations_value:
            relation = _relation_from_value(declaration)
            if relation is not None:
                relations.append(relation)
    if not relations:
        return None
    pattern = str(
        _member(
            schema if schema is not None else graph,
            "pattern",
            default="snowflake",
        )
    )
    if pattern not in {"denormalized", "star", "snowflake"}:
        pattern = "snowflake"
    return SchemaDesign(
        pattern=pattern,
        relations=tuple(relations),
        covered_query_ids=(),
        description="Schema declared by the compiled workload contract.",
    )


def _intent_edges(intent: WorkloadIntent) -> Tuple[RelationEdge, ...]:
    edges: set[RelationEdge] = set()
    for requirement in intent.requirements:
        if requirement.plan:
            for join in requirement.plan.joins:
                edges.add(
                    RelationEdge(
                        join.left.entity,
                        join.left.attribute,
                        join.right.entity,
                        join.right.attribute,
                        join.join_type,
                    )
                )
        for left, relationship, right in requirement.relationships:
            if "=" not in relationship:
                continue
            left_column, right_column = relationship.split("=", 1)
            edges.add(
                RelationEdge(
                    left,
                    left_column.strip(),
                    right,
                    right_column.strip(),
                )
            )
    return tuple(sorted(edges))


def build_workload_relation_graph(
    intent: WorkloadIntent,
    contract: object = None,
) -> WorkloadRelationGraph:
    """Build one graph shared by extraction and every candidate."""
    declared = _contract_schema(contract) if contract is not None else None
    full_query_ids = tuple(intent.query_ids())
    full_set = set(full_query_ids)

    def rank(design: SchemaDesign) -> Tuple[int, int, str]:
        covered = sum(
            requirement.required_symbols() <= design.symbols()
            for requirement in intent.requirements
        )
        preference = {
            "snowflake": 2,
            "star": 1,
            "denormalized": 0,
        }.get(design.pattern, 0)
        return covered, preference, design.schema_id

    if declared is not None:
        selected = declared
    else:
        fallback_designs = generate_schema_designs(intent)
        selected = max(fallback_designs, key=rank)
    symbol_covered = tuple(
        requirement.query_id
        for requirement in intent.requirements
        if requirement.required_symbols() <= selected.symbols()
    )
    if set(symbol_covered) != full_set:
        if declared is not None:
            missing = sorted(full_set - set(symbol_covered))
            raise ValueError(
                "workload contract does not own all required symbols: "
                + ", ".join(missing)
            )
        selected = max(
            (
                design
                for design in fallback_designs
                if set(design.covered_query_ids) == full_set
            ),
            key=rank,
        )
        symbol_covered = full_query_ids

    edges = set(_intent_edges(intent))
    for relation in selected.relations:
        for column, target_table, target_column in relation.foreign_keys:
            edges.add(
                RelationEdge(
                    relation.name,
                    column,
                    target_table,
                    target_column,
                )
            )
    return WorkloadRelationGraph(
        relations=selected.relations,
        edges=tuple(sorted(edges)),
        covered_query_ids=tuple(symbol_covered),
        pattern=selected.pattern,
    )


def _call_contract_compiler(
    compiler: ContractCompiler,
    intent: WorkloadIntent,
) -> object:
    try:
        signature = inspect.signature(compiler)
    except (TypeError, ValueError):
        return compiler(intent)
    parameters = list(signature.parameters.values())
    if not parameters:
        return compiler()
    values = {
        "intent": intent,
        "workload_intent": intent,
        "requirements": intent.requirements,
        "queries": intent.requirements,
        "workload": intent,
    }
    args: List[object] = []
    kwargs: Dict[str, object] = {}
    assigned_fallback = False
    for parameter in parameters:
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        value = values.get(parameter.name)
        if value is None and parameter.default is inspect.Parameter.empty:
            if assigned_fallback:
                raise ContractIntegrationError(
                    "compile_workload_contract has an unsupported required "
                    f"parameter {parameter.name!r}"
                )
            value = intent
            assigned_fallback = True
        if value is None:
            continue
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[parameter.name] = value
    return compiler(*args, **kwargs)


def _rows_mapping(value: object) -> Dict[str, List[dict]]:
    if not isinstance(value, Mapping):
        return {}
    result: Dict[str, List[dict]] = {}
    for relation, rows in value.items():
        if isinstance(rows, Mapping):
            rows = [rows]
        if not isinstance(rows, (list, tuple)):
            continue
        result[str(relation)] = [
            {str(column): item for column, item in row.items()}
            for row in rows
            if isinstance(row, Mapping)
        ]
    return result


def _raw_extraction_parts(
    result: object,
) -> Tuple[Dict[str, List[dict]], Dict[str, List[dict]], object, object]:
    evidence: object = ()
    metadata: object = {}
    semantic: Dict[str, List[dict]] = {}
    if isinstance(result, tuple):
        if len(result) == 2:
            result, evidence = result
        elif len(result) >= 3:
            result, evidence, metadata = result[:3]
    if isinstance(result, Mapping):
        reserved = {
            "raw_tables",
            "tables",
            "relations",
            "semantic_tables",
            "semantic_candidates",
            "evidence",
            "cell_evidence",
            "provenance",
            "metadata",
            "diagnostics",
        }
        raw_value = _member(result, "raw_tables", "tables", "relations")
        if raw_value is None:
            raw_value = {
                key: value
                for key, value in result.items()
                if str(key) not in reserved
            }
        semantic_value = _member(
            result, "semantic_tables", "semantic_candidates", default={}
        )
        if isinstance(semantic_value, Mapping):
            direct = _rows_mapping(semantic_value)
            if direct:
                semantic = direct
            else:
                variants = [
                    _rows_mapping(value)
                    for _name, value in sorted(
                        semantic_value.items(), key=lambda pair: str(pair[0])
                    )
                ]
                semantic = next((value for value in variants if value), {})
        evidence = _member(
            result,
            "evidence",
            "cell_evidence",
            "provenance",
            default=evidence,
        )
        metadata = _member(
            result, "metadata", "diagnostics", default=metadata
        )
        return (
            _rows_mapping(raw_value),
            semantic,
            evidence,
            metadata,
        )
    raw_value = _member(result, "raw_tables", "tables", "relations")
    semantic_value = _member(
        result, "semantic_tables", "semantic_candidates", default={}
    )
    evidence = _member(
        result,
        "evidence",
        "cell_evidence",
        "provenance",
        default=evidence,
    )
    metadata = _member(result, "metadata", "diagnostics", default=metadata)
    return (
        _rows_mapping(raw_value),
        _rows_mapping(semantic_value),
        evidence,
        metadata,
    )


def _row_identity(
    relation: RelationSpec,
    row: Mapping[str, object],
    index: int,
) -> str:
    existing = row.get("row_id") or row.get("_row_identity")
    if existing not in (None, ""):
        return str(existing)
    key_value = (
        row.get(relation.primary_key) if relation.primary_key else None
    )
    payload = {
        "relation": relation.name,
        "key": _jsonable(key_value),
        "row": _jsonable(dict(row)),
        "ordinal": index,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _normalize_table_identities(
    tables: Mapping[str, Sequence[Mapping[str, object]]],
    graph: WorkloadRelationGraph,
    *,
    raw_tables: Optional[
        Mapping[str, Sequence[Mapping[str, object]]]
    ] = None,
) -> Dict[str, List[dict]]:
    relations = {relation.name: relation for relation in graph.relations}
    result: Dict[str, List[dict]] = {}
    for name, rows in tables.items():
        relation = relations.get(name)
        if relation is None:
            continue
        raw_rows = list((raw_tables or {}).get(name, ()))
        normalized = []
        for index, source in enumerate(rows):
            row = dict(source)
            identity = row.get("row_id") or row.get("_row_identity")
            if identity in (None, "") and index < len(raw_rows):
                identity = raw_rows[index].get("row_id")
            if identity in (None, "") and relation.primary_key:
                matching = next(
                    (
                        candidate.get("row_id")
                        for candidate in raw_rows
                        if candidate.get(relation.primary_key)
                        == row.get(relation.primary_key)
                    ),
                    None,
                )
                identity = matching
            row["row_id"] = str(
                identity
                if identity not in (None, "")
                else _row_identity(relation, row, index)
            )
            normalized.append(row)
        result[name] = normalized
    for relation in graph.relations:
        result.setdefault(relation.name, [])
    return result


def _flatten_evidence(value: object) -> List[object]:
    if isinstance(value, Mapping):
        evidence_keys = {
            "relation",
            "relation_name",
            "table",
            "column",
            "column_name",
            "attribute",
            "anchor_id",
            "document_id",
            "source_span",
            "exact_span",
            "quote",
        }
        if evidence_keys & set(value):
            return [value]
        return [
            item
            for nested in value.values()
            for item in _flatten_evidence(nested)
        ]
    if isinstance(value, (list, tuple, set)):
        return [item for nested in value for item in _flatten_evidence(nested)]
    if value is None:
        return []
    return [value]


def _find_span(
    rendered: str,
    documents: Mapping[str, ContractDocument],
    preferred_document: str = "",
) -> Tuple[str, int, int, str, bool]:
    ordered = []
    if preferred_document in documents:
        ordered.append(documents[preferred_document])
    ordered.extend(
        document
        for document_id, document in sorted(documents.items())
        if document_id != preferred_document
    )
    for document in ordered:
        start = document.text.find(rendered)
        if start < 0:
            start = document.text.casefold().find(rendered.casefold())
        if start >= 0:
            end = start + len(rendered)
            return (
                document.document_id,
                start,
                end,
                document.text[start:end],
                True,
            )
    fallback = ordered[0]
    return (
        fallback.document_id,
        0,
        len(fallback.text),
        fallback.text,
        False,
    )


def _explicit_evidence_index(
    value: object,
) -> Dict[Tuple[str, str, str], object]:
    result: Dict[Tuple[str, str, str], object] = {}
    for item in _flatten_evidence(value):
        relation = str(
            _member(item, "relation", "relation_name", "table", default="")
        )
        row_identity = str(
            _member(
                item,
                "row_identity",
                "row_id",
                "record_id",
                default="",
            )
        )
        column = str(
            _member(item, "column", "column_name", "attribute", default="")
        )
        if relation and column:
            result[(relation, row_identity, column)] = item
    return result


def _build_cell_evidence(
    raw_tables: Mapping[str, Sequence[Mapping[str, object]]],
    semantic_tables: Mapping[str, Sequence[Mapping[str, object]]],
    explicit: object,
    documents: Sequence[ContractDocument],
    graph: WorkloadRelationGraph,
) -> Tuple[SharedCellEvidence, ...]:
    document_map = {document.document_id: document for document in documents}
    explicit_index = _explicit_evidence_index(explicit)
    rows_to_visit = {
        name: [*raw_tables.get(name, ()), *semantic_tables.get(name, ())]
        for name in set(raw_tables) | set(semantic_tables)
    }
    evidence: Dict[Tuple[str, str, str, str], SharedCellEvidence] = {}
    relations = {relation.name: relation for relation in graph.relations}
    for relation_name, rows in sorted(rows_to_visit.items()):
        relation = relations.get(relation_name)
        if relation is None:
            continue
        for index, row in enumerate(rows):
            identity = str(
                row.get("row_id") or _row_identity(relation, row, index)
            )
            for column in relation.attributes:
                value = row.get(column)
                if value in (None, ""):
                    continue
                item = (
                    explicit_index.get((relation_name, identity, column))
                    or explicit_index.get((relation_name, "", column))
                )
                rendered = str(
                    _member(
                        item,
                        "source_span",
                        "exact_span",
                        "quote",
                        "text",
                        default=value,
                    )
                )
                preferred_document = str(
                    _member(item, "document_id", "source_id", default="")
                )
                document_id, start, end, anchor_text, restored = _find_span(
                    rendered, document_map, preferred_document
                )
                explicit_start = _member(
                    item, "start", "start_offset", "span_start", default=None
                )
                explicit_end = _member(
                    item, "end", "end_offset", "span_end", default=None
                )
                if (
                    document_id in document_map
                    and explicit_start is not None
                    and explicit_end is not None
                ):
                    try:
                        candidate_start = int(explicit_start)
                        candidate_end = int(explicit_end)
                    except (TypeError, ValueError):
                        candidate_start = candidate_end = -1
                    text = document_map[document_id].text
                    if 0 <= candidate_start <= candidate_end <= len(text):
                        start, end = candidate_start, candidate_end
                        anchor_text = text[start:end]
                        restored = bool(anchor_text)
                entailed = bool(
                    _member(item, "entailed", "supported", default=restored)
                )
                span_restored = bool(
                    _member(item, "span_restored", default=restored)
                )
                anchor = EvidenceAnchor.create(
                    document_id=document_id,
                    text=anchor_text,
                    start=start,
                    end=end,
                    anchor_type="contract_cell",
                    metadata={
                        "relation": relation_name,
                        "column": column,
                    },
                )
                cell = SharedCellEvidence(
                    relation=relation_name,
                    row_identity=identity,
                    column=column,
                    value=value,
                    anchor_id=anchor.anchor_id,
                    document_id=document_id,
                    anchor_text=anchor_text,
                    start=start,
                    end=end,
                    entailed=entailed,
                    span_restored=span_restored,
                )
                key = (
                    relation_name,
                    identity,
                    column,
                    json.dumps(_jsonable(value), sort_keys=True),
                )
                previous = evidence.get(key)
                if previous is None or cell.supported > previous.supported:
                    evidence[key] = cell
    return tuple(
        evidence[key]
        for key in sorted(evidence)
    )


def _symbol_key(value: object) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _contract_extraction_parts(
    result: object,
    graph: WorkloadRelationGraph,
    invalid_record_indexes: set[int],
    invalid_relationship_indexes: set[int],
) -> Tuple[Dict[str, List[dict]], List[dict]]:
    """Convert concrete ContractExtraction records to graph rows and evidence."""
    records = tuple(
        (
            *(_member(result, "entity_records", default=()) or ()),
            *(_member(result, "attribute_records", default=()) or ()),
        )
    )
    if not records:
        records = tuple(_member(result, "records", default=()) or ())
    relations = {relation.name: relation for relation in graph.relations}
    relation_names = {_symbol_key(name): name for name in relations}
    root_relation = graph.relations[0].name if graph.relations else ""
    rows: Dict[str, List[dict]] = {name: [] for name in relations}
    grouped: Dict[Tuple[str, str, str], List[dict]] = {}
    evidence: List[dict] = []

    def new_row(
        relation: RelationSpec,
        identity: str,
        document_id: str,
        variant: int,
    ) -> dict:
        row_identity = hashlib.sha256(
            (
                f"{relation.name}\0{identity}\0{document_id}\0{variant}"
            ).encode("utf-8")
        ).hexdigest()
        row = {"row_id": row_identity}
        if relation.primary_key:
            row[relation.primary_key] = identity
        rows[relation.name].append(row)
        return row

    for record_index, record in enumerate(records):
        if record_index in invalid_record_indexes:
            continue
        entity = str(_member(record, "entity", default="") or "")
        relation_name = relation_names.get(_symbol_key(entity), root_relation)
        relation = relations.get(relation_name)
        if relation is None:
            continue
        identity = str(_member(record, "identity", default="") or "").strip()
        document_id = str(
            _member(record, "document_id", default="") or ""
        )
        if not identity or not document_id:
            continue
        key = (relation.name, identity, document_id)
        alternatives = grouped.setdefault(key, [])
        if not alternatives:
            alternatives.append(new_row(relation, identity, document_id, 0))
        attribute_value = _member(record, "attribute", default=None)
        if attribute_value is None:
            column = relation.primary_key
            value = identity
            row = alternatives[0]
        else:
            column = str(attribute_value)
            if column not in relation.attributes:
                continue
            value = _member(record, "value")
            row = next(
                (
                    candidate
                    for candidate in alternatives
                    if candidate.get(column) in (None, "", value)
                ),
                None,
            )
            if row is None:
                row = new_row(
                    relation, identity, document_id, len(alternatives)
                )
                alternatives.append(row)
            row[column] = value
        if not column or value in (None, ""):
            continue
        evidence.append(
            {
                "relation": relation.name,
                "row_identity": row["row_id"],
                "column": column,
                "value": value,
                "document_id": document_id,
                "exact_span": str(
                    _member(record, "exact_span", default=value)
                ),
                "span_start": _member(record, "span_start", default=None),
                "span_end": _member(record, "span_end", default=None),
                "entailed": record_index not in invalid_record_indexes,
                "span_restored": record_index not in invalid_record_indexes,
            }
        )

    def rows_for_identity(
        relation: RelationSpec,
        identity: str,
        document_id: str,
    ) -> List[dict]:
        matches = [
            row
            for (name, known_identity, _document), alternatives
            in grouped.items()
            if name == relation.name and known_identity == identity
            for row in alternatives
        ]
        if matches:
            return matches
        key = (relation.name, identity, document_id)
        row = new_row(relation, identity, document_id, 0)
        grouped[key] = [row]
        return [row]

    for relationship_index, record in enumerate(
        tuple(
            _member(
                result, "relationship_records", default=()
            )
            or ()
        )
    ):
        if relationship_index in invalid_relationship_indexes:
            continue
        left_name = relation_names.get(
            _symbol_key(
                _member(record, "left_entity", default="")
            )
        )
        right_name = relation_names.get(
            _symbol_key(
                _member(record, "right_entity", default="")
            )
        )
        left_relation = relations.get(left_name or "")
        right_relation = relations.get(right_name or "")
        if left_relation is None or right_relation is None:
            continue
        matching_edges = [
            edge
            for edge in graph.edges
            if (
                edge.left_relation == left_relation.name
                and edge.right_relation == right_relation.name
            )
            or (
                edge.left_relation == right_relation.name
                and edge.right_relation == left_relation.name
            )
        ]
        if not matching_edges:
            continue
        left_identity = str(
            _member(record, "left_identity", default="")
        )
        right_identity = str(
            _member(record, "right_identity", default="")
        )
        document_id = str(
            _member(record, "document_id", default="")
        )
        if not left_identity or not right_identity or not document_id:
            continue
        left_rows = rows_for_identity(
            left_relation, left_identity, document_id
        )
        right_rows = rows_for_identity(
            right_relation, right_identity, document_id
        )
        for edge in matching_edges:
            reversed_edge = edge.left_relation != left_relation.name
            left_column = (
                edge.right_column if reversed_edge else edge.left_column
            )
            right_column = (
                edge.left_column if reversed_edge else edge.right_column
            )
            if (
                left_column not in left_relation.attributes
                or right_column not in right_relation.attributes
            ):
                continue
            if left_relation.primary_key == left_column:
                shared_value = left_rows[0].get(
                    left_column, left_identity
                )
            elif right_relation.primary_key == right_column:
                shared_value = right_rows[0].get(
                    right_column, right_identity
                )
            else:
                left_tokens = {
                    token
                    for token in re.split(r"[^a-z0-9]+", left_column.lower())
                    if token
                }
                right_tokens = {
                    token
                    for token in re.split(r"[^a-z0-9]+", right_column.lower())
                    if token
                }
                left_entity_tokens = {
                    token
                    for token in re.split(
                        r"[^a-z0-9]+", left_relation.name.lower()
                    )
                    if token
                }
                right_entity_tokens = {
                    token
                    for token in re.split(
                        r"[^a-z0-9]+", right_relation.name.lower()
                    )
                    if token
                }
                right_is_key = bool(
                    right_tokens
                    & (right_entity_tokens | {"id", "name"})
                )
                left_is_key = bool(
                    left_tokens
                    & (left_entity_tokens | {"id", "name"})
                )
                shared_value = (
                    right_identity
                    if right_is_key and not left_is_key
                    else left_identity
                )
            exact_span = str(
                _member(record, "exact_span", default="")
            )
            span_start = _member(
                record, "span_start", default=None
            )
            span_end = _member(record, "span_end", default=None)
            for relation, column, candidate_rows in (
                (left_relation, left_column, left_rows),
                (right_relation, right_column, right_rows),
            ):
                for row in candidate_rows:
                    existing = row.get(column)
                    if existing not in (None, "", shared_value):
                        continue
                    row[column] = shared_value
                    evidence.append(
                        {
                            "relation": relation.name,
                            "row_identity": row["row_id"],
                            "column": column,
                            "value": shared_value,
                            "document_id": document_id,
                            "exact_span": exact_span,
                            "span_start": span_start,
                            "span_end": span_end,
                            "entailed": True,
                            "span_restored": True,
                            "derivation": "relationship_edge",
                        }
                    )
    return rows, evidence


def _normalize_extraction(
    result: object,
    documents: Sequence[ContractDocument],
    graph: WorkloadRelationGraph,
    *,
    validation_issues: Sequence[object] = (),
) -> SharedExtraction:
    raw, semantic, explicit, metadata = _raw_extraction_parts(result)
    if not raw and (
        _member(result, "records", default=None) is not None
        or _member(result, "entity_records", default=None) is not None
    ):
        invalid_indexes = {
            int(index)
            for issue in validation_issues
            if str(_member(issue, "severity", default="error")) == "error"
            and _member(issue, "relationship", default=None) is None
            and isinstance(
                index := _member(issue, "record_index", default=None), int
            )
        }
        invalid_relationship_indexes = {
            int(index)
            for issue in validation_issues
            if str(_member(issue, "severity", default="error")) == "error"
            and _member(issue, "relationship", default=None) is not None
            and isinstance(
                index := _member(issue, "record_index", default=None), int
            )
        }
        raw, explicit_records = _contract_extraction_parts(
            result,
            graph,
            invalid_indexes,
            invalid_relationship_indexes,
        )
        explicit = explicit_records
        metadata = {
            "validation_issues": [
                _jsonable(issue) for issue in validation_issues
            ],
            "validation_error_count": sum(
                str(_member(issue, "severity", default="error")) == "error"
                for issue in validation_issues
            ),
            "derivation_mappings": [
                _jsonable(mapping)
                for mapping in (
                    _member(
                        result,
                        "derivation_mappings",
                        default=(),
                    )
                    or ()
                )
            ],
        }
    normalized_raw = _normalize_table_identities(raw, graph)
    normalized_semantic = (
        _normalize_table_identities(
            semantic, graph, raw_tables=normalized_raw
        )
        if semantic
        else {}
    )
    evidence = _build_cell_evidence(
        normalized_raw,
        normalized_semantic,
        explicit,
        documents,
        graph,
    )
    return SharedExtraction(
        raw_tables={
            name: tuple(dict(row) for row in rows)
            for name, rows in sorted(normalized_raw.items())
        },
        semantic_tables=(
            {
                name: tuple(dict(row) for row in rows)
                for name, rows in sorted(normalized_semantic.items())
            }
            if normalized_semantic
            else None
        ),
        evidence=evidence,
        metadata=(
            dict(metadata)
            if isinstance(metadata, Mapping)
            else {"extractor_metadata": str(metadata)}
        ),
    )


def _shared_payload(shared: SharedExtraction) -> dict:
    return {
        "version": 1,
        "raw_tables": _jsonable(shared.raw_tables),
        "semantic_tables": _jsonable(shared.semantic_tables),
        "evidence": [_jsonable(asdict(cell)) for cell in shared.evidence],
        "metadata": _jsonable(shared.metadata),
    }


def _shared_from_payload(payload: object) -> SharedExtraction:
    if not isinstance(payload, Mapping) or payload.get("version") != 1:
        raise ContractIntegrationError("unsupported shared extraction artifact")
    raw = _rows_mapping(payload.get("raw_tables"))
    semantic = _rows_mapping(payload.get("semantic_tables"))
    evidence = []
    for item in payload.get("evidence", ()):
        if not isinstance(item, Mapping):
            continue
        evidence.append(
            SharedCellEvidence(
                relation=str(item.get("relation", "")),
                row_identity=str(item.get("row_identity", "")),
                column=str(item.get("column", "")),
                value=item.get("value"),
                anchor_id=str(item.get("anchor_id", "")),
                document_id=str(item.get("document_id", "")),
                anchor_text=str(item.get("anchor_text", "")),
                start=int(item.get("start", 0)),
                end=int(item.get("end", 0)),
                entailed=bool(item.get("entailed", False)),
                span_restored=bool(item.get("span_restored", False)),
            )
        )
    metadata = payload.get("metadata", {})
    return SharedExtraction(
        raw_tables={
            name: tuple(rows) for name, rows in sorted(raw.items())
        },
        semantic_tables=(
            {name: tuple(rows) for name, rows in sorted(semantic.items())}
            if semantic
            else None
        ),
        evidence=tuple(evidence),
        metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
    )


class ContractBackend:
    """A ``SynthesisBackend`` implementation over one compiled contract."""

    def __init__(
        self,
        documents: Sequence[
            ContractDocument | Mapping[str, object] | str | object
        ],
        llm_client: object,
        *,
        scratch_dir: Optional[Path] = None,
        contract_compiler: Optional[ContractCompiler] = None,
        max_query_rows: int = 100_000,
        bootstrap_folds: int = 4,
    ):
        self.documents = _normalize_documents(documents)
        self.llm_client = llm_client
        self.scratch_dir = (
            Path(scratch_dir).expanduser().resolve()
            if scratch_dir is not None
            else None
        )
        self.extractor: object = None
        self.contract_compiler = contract_compiler
        self.max_query_rows = int(max_query_rows)
        self.bootstrap_folds = int(bootstrap_folds)
        if self.max_query_rows <= 0:
            raise ValueError("max_query_rows must be positive")
        if self.bootstrap_folds < 2:
            raise ValueError("bootstrap_folds must be at least two")
        self.intent: Optional[WorkloadIntent] = None
        self.contract: object = None
        self.relation_graph: Optional[WorkloadRelationGraph] = None
        self.preprocessing_policy = PreprocessingPolicy(
            strategy="whole_document"
        )
        self._intent_fingerprint: Optional[str] = None
        self._candidate_kind: Dict[str, str] = {}
        self._shared: Optional[SharedExtraction] = None
        self._shared_artifact_key: Optional[str] = None
        self._repair_summary: Dict[str, object] = {}

    def _compiler(self) -> ContractCompiler:
        compiler = self.contract_compiler or _default_contract_compiler
        if compiler is None:
            raise ContractIntegrationError(
                "spp.workload_contract.compile_workload_contract is not "
                "available; pass contract_compiler=... until that module lands"
            )
        return compiler

    def _extractor(
        self,
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
    ) -> object:
        if self.extractor is not None:
            return self.extractor
        budgeted_client = BudgetedLLMClient(
            self.llm_client,
            ledger,
            default_stage="contract_extraction",
        )
        self.extractor = ContractExtractor(
            self.documents,
            budgeted_client,
            evidence_store,
        )
        return self.extractor

    def _ensure_contract(self, intent: WorkloadIntent) -> None:
        fingerprint = _fingerprint(asdict(intent))
        if (
            self._intent_fingerprint == fingerprint
            and self.contract is not None
            and self.relation_graph is not None
        ):
            return
        self.contract = _call_contract_compiler(self._compiler(), intent)
        if self.contract is None:
            raise ContractIntegrationError(
                "compile_workload_contract returned None"
            )
        self.relation_graph = build_workload_relation_graph(
            intent, self.contract
        )
        self._intent_fingerprint = fingerprint
        self._shared = None
        self._shared_artifact_key = None

    def _validated_schema(self, intent: WorkloadIntent) -> SchemaDesign:
        assert self.relation_graph is not None
        schema = self.relation_graph.schema
        probe = SynthesisConfig(
            schema=schema,
            population=PopulationConfig(
                er_strategy="raw",
                norm_strategy="raw",
                unit_strategy="none",
                miss_strategy="drop",
                type_coercion="strict",
            ),
            preprocessing=self.preprocessing_policy,
        )
        covered = tuple(
            requirement.query_id
            for requirement in intent.requirements
            if requirement.required_symbols() <= schema.symbols()
            and (
                requirement.plan is None
                or compile_query_plan(requirement.plan, probe) is not None
            )
        )
        if set(covered) == set(intent.query_ids()):
            return replace(schema, covered_query_ids=covered)

        missing = sorted(set(intent.query_ids()) - set(covered))
        raise ValueError(
            "contract relation graph cannot bind the complete typed workload: "
            + ", ".join(missing)
        )

    def _semantic_candidate_relevant(
        self,
        intent: WorkloadIntent,
        schema: SchemaDesign,
    ) -> bool:
        contract_signals = any(
            _member(
                self.contract,
                name,
                default=None,
            )
            not in (None, (), [], {})
            for name in (
                "semantic_rules",
                "normalizations",
                "unit_rules",
                "type_rules",
                "semantic_candidates",
            )
        )
        typed = any(
            declared != "text"
            for relation in schema.relations
            for _column, declared in relation.semantic_types
        )
        grouped_categorical = any(
            "group_by"
            in {
                role
                for _query_id, roles in (
                    _member(
                        attribute, "contexts", default=()
                    )
                    or ()
                )
                for role in roles
            }
            and set(
                _member(
                    attribute,
                    "semantic_types",
                    default=("text",),
                )
                or ("text",)
            )
            == {"text"}
            for attribute in (
                _member(self.contract, "attributes", default=())
                or ()
            )
        )
        return bool(
            contract_signals
            or typed
            or intent.has_units
            or intent.has_numeric_operations
            or grouped_categorical
        )

    def generate_configs(
        self,
        intent: WorkloadIntent,
        observed_document_lengths: Optional[Sequence[int]] = None,
    ) -> Sequence[SynthesisConfig]:
        """Generate a minimal raw/semantic candidate set for the workload."""
        self._ensure_contract(intent)
        _ = observed_document_lengths
        # ContractExtractor currently validates absolute source offsets over
        # whole documents. Advertising a chunked policy would make cache and
        # reproducibility metadata false even if values happened to match.
        self.preprocessing_policy = PreprocessingPolicy(
            strategy="whole_document"
        )
        schema = self._validated_schema(intent)
        raw = SynthesisConfig(
            schema=schema,
            population=PopulationConfig(
                er_strategy="raw",
                norm_strategy="raw",
                unit_strategy="none",
                miss_strategy="drop",
                type_coercion="strict",
            ),
            preprocessing=self.preprocessing_policy,
        )
        candidates = [raw]
        kinds = {raw.config_id: "raw"}
        if self._semantic_candidate_relevant(intent, schema):
            semantic = SynthesisConfig(
                schema=schema,
                population=PopulationConfig(
                    er_strategy="evidence",
                    norm_strategy="contract_mapping",
                    unit_strategy=(
                        "contract_unit" if intent.has_units else "none"
                    ),
                    miss_strategy="drop",
                    type_coercion=(
                        "permissive"
                        if intent.has_numeric_operations
                        else "strict"
                    ),
                ),
                preprocessing=self.preprocessing_policy,
            )
            if semantic.config_id != raw.config_id:
                candidates.append(semantic)
                kinds[semantic.config_id] = "evidence_semantic"
        self._candidate_kind = kinds
        return tuple(sorted(candidates, key=lambda item: item.config_id))

    def _shared_key(self) -> str:
        assert self.relation_graph is not None
        payload = {
            "backend_version": BACKEND_VERSION,
            "contract": _fingerprint(self.contract),
            "graph": self.relation_graph.fingerprint,
            "preprocessing": asdict(self.preprocessing_policy),
            "extractor": {
                "module": ContractExtractor.__module__,
                "class": ContractExtractor.__qualname__,
                "version": str(getattr(ContractExtractor, "version", "")),
                "model": str(
                    getattr(
                        self.llm_client,
                        "model",
                        type(self.llm_client).__name__,
                    )
                ),
            },
            "documents": [
                {
                    "document_id": document.document_id,
                    "sha256": hashlib.sha256(
                        document.text.encode("utf-8")
                    ).hexdigest(),
                }
                for document in self.documents
            ],
        }
        return "contract-extraction:" + _fingerprint(payload)

    def _persist_shared_evidence(
        self,
        evidence_store: EvidenceStore,
    ) -> None:
        assert self._shared is not None
        assert self._shared_artifact_key is not None
        anchors = [
            EvidenceAnchor(
                anchor_id=cell.anchor_id,
                document_id=cell.document_id,
                text=cell.anchor_text,
                start=cell.start,
                end=cell.end,
                anchor_type="contract_cell",
                metadata={
                    "relation": cell.relation,
                    "column": cell.column,
                },
            )
            for cell in self._shared.evidence
        ]
        evidence_store.add_anchors(anchors)
        evidence_store.add_cell_provenance(
            CellProvenance(
                config_id=f"shared:{self._shared_artifact_key}",
                relation=cell.relation,
                row_identity=cell.row_identity,
                column=cell.column,
                value_json=json.dumps(
                    _jsonable(cell.value),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                anchor_id=cell.anchor_id,
                entailed=cell.entailed,
                span_restored=cell.span_restored,
            )
            for cell in self._shared.evidence
        )

    def _persist_contract_audit(
        self,
        extraction: object,
        issues: Sequence[ValidationIssue],
        evidence_store: EvidenceStore,
    ) -> None:
        """Persist raw surfaces, units, conflicts, and validation decisions."""
        assert self.contract is not None
        entity_records = tuple(
            _member(extraction, "entity_records", default=()) or ()
        )
        attribute_records = tuple(
            _member(extraction, "attribute_records", default=()) or ()
        )
        records = (*entity_records, *attribute_records)
        error_indexes = {
            issue.record_index
            for issue in issues
            if issue.severity == "error"
            and issue.relationship is None
            and issue.record_index is not None
        }

        def record_contract(record: object) -> object:
            attribute = _member(record, "attribute", default=None)
            entity = _symbol_key(_member(record, "entity", default=""))
            if attribute is None:
                return next(
                    (
                        item
                        for item in _member(
                            self.contract, "entities", default=()
                        )
                        if _symbol_key(
                            _member(item, "name", default="")
                        )
                        == entity
                    ),
                    None,
                )
            return next(
                (
                    item
                    for item in _member(
                        self.contract, "attributes", default=()
                    )
                    if _symbol_key(
                        _member(item, "name", default="")
                    )
                    == _symbol_key(attribute)
                    and entity
                    in {
                        _symbol_key(owner)
                        for owner in (
                            _member(item, "owners", default=()) or ()
                        )
                    }
                ),
                None,
            )

        contract_rows: List[ContractEvidence] = []
        outcomes: List[StoredValidationOutcome] = []
        for index, record in enumerate(records):
            declaration = record_contract(record)
            contract_id = str(
                _member(
                    declaration,
                    "contract_id",
                    default=(
                        "record:"
                        + _fingerprint(
                            {
                                "entity": _member(
                                    record, "entity", default=""
                                ),
                                "attribute": _member(
                                    record,
                                    "attribute",
                                    default=None,
                                ),
                            }
                        )
                    ),
                )
            )
            document_id = str(
                _member(record, "document_id", default="")
            )
            start = int(_member(record, "span_start", default=0) or 0)
            end = int(_member(record, "span_end", default=start) or start)
            anchor_row = evidence_store.conn.execute(
                """
                SELECT anchor_id FROM anchors
                WHERE document_id = ? AND start_offset = ? AND end_offset = ?
                ORDER BY anchor_type, anchor_id LIMIT 1
                """,
                (document_id, start, end),
            ).fetchone()
            if anchor_row is None:
                continue
            accepted = index not in error_indexes
            relation = str(_member(record, "entity", default=""))
            column = str(
                _member(record, "attribute", default="")
                or "__identity__"
            )
            identity = str(
                _member(record, "identity", default="")
            )
            contract_rows.append(
                ContractEvidence(
                    contract_id=contract_id,
                    relation=relation,
                    row_identity=identity,
                    column=column,
                    raw_value_json=json.dumps(
                        _jsonable(
                            _member(record, "value", default=identity)
                        ),
                        sort_keys=True,
                    ),
                    raw_surface=str(
                        _member(record, "exact_span", default="")
                    ),
                    source_unit=(
                        str(_member(record, "unit"))
                        if _member(record, "unit", default=None)
                        is not None
                        else None
                    ),
                    anchor_id=str(anchor_row[0]),
                    accepted=accepted,
                    validation_status=(
                        "accepted" if accepted else "rejected"
                    ),
                    metadata={
                        "document_id": document_id,
                        "record_index": index,
                    },
                )
            )
            outcomes.append(
                StoredValidationOutcome(
                    contract_id=contract_id,
                    scope="cell",
                    scope_key=f"{document_id}:{index}",
                    code="contract_acceptance",
                    passed=accepted,
                    severity="error",
                    details={"column": column},
                )
            )
        if contract_rows:
            evidence_store.add_contract_evidence(contract_rows)
        for ordinal, issue in enumerate(issues):
            declaration = next(
                (
                    record_contract(records[issue.record_index])
                    for _unused in (0,)
                    if issue.relationship is None
                    and issue.record_index is not None
                    and 0 <= issue.record_index < len(records)
                ),
                None,
            )
            contract_id = str(
                _member(
                    declaration,
                    "contract_id",
                    default="validation:" + issue.fingerprint,
                )
            )
            outcomes.append(
                StoredValidationOutcome(
                    contract_id=contract_id,
                    scope=(
                        "relationship"
                        if issue.relationship
                        else "cell"
                    ),
                    scope_key=(
                        f"{issue.document_id or 'contract'}:"
                        f"{issue.record_index if issue.record_index is not None else ordinal}"
                    ),
                    code=issue.code,
                    passed=False,
                    severity=issue.severity,
                    details={"message": issue.message},
                )
            )
        if outcomes:
            evidence_store.add_validation_outcomes(outcomes)

        conflicts: List[ConflictRecord] = []
        grouped: Dict[
            Tuple[str, str, str], List[ContractEvidence]
        ] = {}
        for row in contract_rows:
            if row.column == "__identity__":
                continue
            grouped.setdefault(
                (row.relation, row.row_identity, row.column), []
            ).append(row)
        for (relation, identity, column), group in grouped.items():
            values = sorted({row.raw_value_json for row in group})
            if len(values) < 2:
                continue
            declaration = next(
                (
                    record_contract(record)
                    for record in attribute_records
                    if str(
                        _member(record, "entity", default="")
                    )
                    == relation
                    and str(
                        _member(record, "identity", default="")
                    )
                    == identity
                    and str(
                        _member(record, "attribute", default="")
                    )
                    == column
                ),
                None,
            )
            conflicts.append(
                ConflictRecord(
                    contract_id=str(
                        _member(
                            declaration,
                            "contract_id",
                            default="conflict:"
                            + _fingerprint(
                                (relation, identity, column)
                            ),
                        )
                    ),
                    relation=relation,
                    row_identity=identity,
                    column=column,
                    values_json=json.dumps(values),
                    anchor_ids=tuple(
                        sorted({row.anchor_id for row in group})
                    ),
                )
            )
        if conflicts:
            evidence_store.add_conflicts(conflicts)

    def _adaptive_repair(
        self,
        extractor: object,
        extraction: object,
        ledger: GlobalBudgetLedger,
    ) -> Tuple[object, Tuple[ValidationIssue, ...]]:
        """Repair only novel, document-local contract violations."""
        assert self.contract is not None
        admission = AdaptiveRepairAdmission()
        current = extraction
        issues = validate_extraction(
            current, self.contract, self.documents
        )
        blocked_targets: set[Tuple[str, str, str, str, str]] = set()
        document_lengths = {
            document.document_id: len(document.text)
            for document in self.documents
        }

        def applies(issue: ValidationIssue, target: object) -> bool:
            return (
                issue.document_id == getattr(target, "document_id", None)
                and (
                    getattr(target, "attribute", None) is None
                    or issue.attribute == getattr(target, "attribute")
                )
                and (
                    getattr(target, "relationship", None) is None
                    or issue.relationship == getattr(target, "relationship")
                )
                and (
                    not getattr(target, "entity", "")
                    or _symbol_key(issue.entity)
                    == _symbol_key(getattr(target, "entity"))
                )
            )

        while True:
            selected = None
            for target in targeted_repair_targets(issues):
                target_key = (
                    target.phase,
                    target.document_id,
                    target.entity,
                    str(target.attribute or ""),
                    str(target.relationship or ""),
                )
                if target_key in blocked_targets:
                    continue
                target_issues = tuple(
                    issue for issue in issues if applies(issue, target)
                )
                conservative_cost = (
                    document_lengths.get(target.document_id, 0) + 1
                ) // 2 + int(
                    getattr(extractor, "max_attribute_tokens", 512)
                ) + 1_024
                if admission.admit(
                    target_issues,
                    evidence=current,
                    estimated_repair_tokens=conservative_cost,
                    completion_reserve=0,
                    ledger=ledger,
                ):
                    selected = (target, target_issues)
                    break
            if selected is None:
                break

            target, target_issues = selected
            target_key = (
                target.phase,
                target.document_id,
                target.entity,
                str(target.attribute or ""),
                str(target.relationship or ""),
            )
            rejected = next(
                (
                    record
                    for record in (
                        *(
                            _member(
                                current, "entity_records", default=()
                            )
                            or ()
                        ),
                        *(
                            _member(
                                current, "attribute_records", default=()
                            )
                            or ()
                        ),
                        *(
                            _member(
                                current,
                                "relationship_records",
                                default=(),
                            )
                            or ()
                        ),
                    )
                    if str(
                        _member(record, "document_id", default="")
                    )
                    == target.document_id
                    and (
                        target.attribute is None
                        or str(
                            _member(record, "attribute", default="")
                        )
                        == target.attribute
                    )
                    and (
                        target.relationship is None
                        or str(
                            _member(
                                record,
                                "relationship",
                                default="",
                            )
                        )
                        == target.relationship
                    )
                ),
                None,
            )
            repaired = tuple(
                extractor.repair_target(
                    self.contract,
                    target,
                    entity_records=tuple(
                        _member(
                            current, "entity_records", default=()
                        )
                        or ()
                    ),
                    rejected_record=rejected,
                )
            )
            if not repaired:
                continue

            entity_records = list(
                _member(current, "entity_records", default=()) or ()
            )
            attribute_records = list(
                _member(current, "attribute_records", default=()) or ()
            )
            relationship_records = list(
                _member(
                    current, "relationship_records", default=()
                )
                or ()
            )
            if target.phase == "entity":
                entity_records = [
                    record
                    for record in entity_records
                    if not (
                        str(
                            _member(
                                record, "document_id", default=""
                            )
                        )
                        == target.document_id
                        and _symbol_key(
                            _member(record, "entity", default="")
                        )
                        == _symbol_key(target.entity)
                    )
                ]
            elif target.phase == "attribute":
                attribute_records = [
                    record
                    for record in attribute_records
                    if not (
                        str(
                            _member(
                                record, "document_id", default=""
                            )
                        )
                        == target.document_id
                        and str(
                            _member(
                                record, "attribute", default=""
                            )
                        )
                        == str(target.attribute or "")
                        and (
                            not target.entity
                            or _symbol_key(
                                _member(
                                    record, "entity", default=""
                                )
                            )
                            == _symbol_key(target.entity)
                        )
                    )
                ]
            else:
                relationship_records = [
                    record
                    for record in relationship_records
                    if not (
                        str(
                            _member(
                                record, "document_id", default=""
                            )
                        )
                        == target.document_id
                        and str(
                            _member(
                                record,
                                "relationship",
                                default="",
                            )
                        )
                        == str(target.relationship or "")
                    )
                ]
            for record in repaired:
                if _member(record, "relationship", default=None) is not None:
                    relationship_records.append(record)
                elif _member(record, "attribute", default=None) is None:
                    entity_records.append(record)
                else:
                    attribute_records.append(record)
            updated = replace(
                current,
                entity_records=tuple(entity_records),
                attribute_records=tuple(attribute_records),
                relationship_records=tuple(relationship_records),
            )
            before = _fingerprint(current)
            after = _fingerprint(updated)
            if before == after:
                continue
            current = updated
            next_issues = validate_extraction(
                current, self.contract, self.documents
            )
            before_errors = sum(
                issue.severity == "error" for issue in issues
            )
            after_errors = sum(
                issue.severity == "error" for issue in next_issues
            )
            if after_errors >= before_errors:
                blocked_targets.add(target_key)
            issues = next_issues
        derive_mappings = getattr(extractor, "derive_mappings", None)
        if callable(derive_mappings) and hasattr(
            current, "derivation_mappings"
        ):
            current = replace(
                current,
                derivation_mappings=tuple(
                    derive_mappings(
                        self.contract,
                        tuple(
                            _member(
                                current,
                                "attribute_records",
                                default=(),
                            )
                            or ()
                        ),
                    )
                ),
            )
        self._repair_summary = {
            "admitted_actions": admission.admitted_attempts,
            "blocked_without_loss_reduction": len(blocked_targets),
            "remaining_errors": sum(
                issue.severity == "error" for issue in issues
            ),
            "remaining_warnings": sum(
                issue.severity == "warning" for issue in issues
            ),
        }
        return current, tuple(issues)

    def prepare(
        self,
        intent: WorkloadIntent,
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
    ) -> None:
        self.intent = intent
        self._ensure_contract(intent)
        for document in self.documents:
            evidence_store.add_document(
                document.document_id,
                document.text,
                metadata=dict(document.metadata),
            )
        key = self._shared_key()
        cached = evidence_store.get_shared_artifact(key)
        if cached is not None:
            self._shared = _shared_from_payload(cached)
        else:
            before = ledger.actual_spent
            extractor = self._extractor(evidence_store, ledger)
            result = extractor.extract(self.contract)
            result, validation_issues = self._adaptive_repair(
                extractor,
                result,
                ledger,
            )
            self._persist_contract_audit(
                result, validation_issues, evidence_store
            )
            self._shared = _normalize_extraction(
                result,
                self.documents,
                self.relation_graph,
                validation_issues=validation_issues,
            )
            if not any(self._shared.raw_tables.values()):
                if bool(
                    _member(
                        result,
                        "budget_exhausted",
                        default=False,
                    )
                ):
                    raise BudgetExhausted(
                        "budget ended before the contract entity registry "
                        "produced any materializable row"
                    )
                raise ContractIntegrationError(
                    "ContractExtractor.extract returned no raw relation rows"
                )
            evidence_store.put_shared_artifact(
                key,
                stage="contract_extraction",
                payload=_shared_payload(self._shared),
                producer_tokens=ledger.actual_spent - before,
            )
        self._shared_artifact_key = key
        self._persist_shared_evidence(evidence_store)

    @staticmethod
    def _coerce_value(value: object, semantic_type: str) -> object:
        if value in (None, ""):
            return value
        if semantic_type == "text":
            return value.strip() if isinstance(value, str) else value
        if semantic_type == "boolean":
            if isinstance(value, bool):
                return value
            rendered = str(value).strip().casefold()
            if rendered in {"true", "yes", "1"}:
                return True
            if rendered in {"false", "no", "0"}:
                return False
            return value
        if semantic_type not in {"integer", "real"}:
            return value
        if isinstance(value, bool):
            return value
        rendered = str(value).strip().replace(",", "")
        try:
            number = float(rendered)
        except ValueError:
            return value
        if not math.isfinite(number):
            return value
        if semantic_type == "integer" and number.is_integer():
            return int(number)
        return number if semantic_type == "real" else value

    def _derived_semantic_tables(
        self,
        raw_tables: Mapping[str, Sequence[Mapping[str, object]]],
    ) -> Dict[str, List[dict]]:
        assert self.relation_graph is not None
        assert self._shared is not None
        supported = {
            (cell.relation, cell.row_identity, cell.column)
            for cell in self._shared.evidence
            if cell.supported
        }
        relations = {
            relation.name: relation for relation in self.relation_graph.relations
        }
        mappings: Dict[Tuple[str, str, str], object] = {}
        for mapping in (
            self._shared.metadata.get("derivation_mappings", ())
            if isinstance(self._shared.metadata, Mapping)
            else ()
        ):
            entity = str(_member(mapping, "entity", default=""))
            column = str(
                _member(mapping, "attribute", default="")
            )
            source = json.dumps(
                _jsonable(
                    _member(mapping, "source_value", default=None)
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
            if entity and column:
                mappings[(entity, column, source)] = _member(
                    mapping, "target_value", default=None
                )
        result: Dict[str, List[dict]] = {}
        for name, rows in raw_tables.items():
            relation = relations[name]
            transformed = []
            for row in rows:
                output = dict(row)
                identity = str(row.get("row_id", ""))
                for column, semantic_type in relation.semantic_types:
                    if (name, identity, column) in supported:
                        coerced = self._coerce_value(
                            output.get(column), semantic_type
                        )
                        source_key = json.dumps(
                            _jsonable(output.get(column)),
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        output[column] = mappings.get(
                            (name, column, source_key),
                            coerced,
                        )
                transformed.append(output)
            result[name] = transformed
        return result

    def _sample_raw_tables(
        self,
        fraction: float,
    ) -> Dict[str, List[dict]]:
        assert self._shared is not None
        sampled: Dict[str, List[dict]] = {}
        for name, rows in self._shared.raw_tables.items():
            ordered = sorted(
                (dict(row) for row in rows),
                key=lambda row: _fingerprint(row),
            )
            if not ordered:
                sampled[name] = []
                continue
            count = min(
                len(ordered),
                max(1, math.ceil(len(ordered) * fraction)),
            )
            sampled[name] = ordered[:count]
        return sampled

    def _semantic_tables_for_sample(
        self,
        raw_tables: Mapping[str, Sequence[Mapping[str, object]]],
    ) -> Dict[str, List[dict]]:
        assert self._shared is not None
        if self._shared.semantic_tables is None:
            return self._derived_semantic_tables(raw_tables)
        selected_ids = {
            name: {str(row.get("row_id", "")) for row in rows}
            for name, rows in raw_tables.items()
        }
        filtered = {
            name: [
                dict(row)
                for row in rows
                if str(row.get("row_id", "")) in selected_ids.get(name, set())
            ]
            for name, rows in self._shared.semantic_tables.items()
        }
        return _normalize_table_identities(
            filtered,
            self.relation_graph,
            raw_tables=raw_tables,
        )

    def _reshape(
        self,
        tables: Mapping[str, Sequence[Mapping[str, object]]],
        schema: SchemaDesign,
    ) -> Dict[str, List[dict]]:
        table_names = set(tables)
        schema_names = {relation.name for relation in schema.relations}
        if schema.pattern == "denormalized" and table_names != schema_names:
            assert self.relation_graph is not None
            return reshape_tables(
                tables,
                schema,
                join_pairs=self.relation_graph.join_pairs,
            )
        return {
            relation.name: [
                dict(row) for row in tables.get(relation.name, ())
            ]
            for relation in schema.relations
        }

    def _candidate_tables(
        self,
        config: SynthesisConfig,
        *,
        sample_fraction: float,
    ) -> Dict[str, List[dict]]:
        if self._shared is None:
            raise RuntimeError("prepare must run before candidate materialization")
        raw = self._sample_raw_tables(sample_fraction)
        kind = self._candidate_kind.get(config.config_id, "raw")
        source = (
            self._semantic_tables_for_sample(raw)
            if kind == "evidence_semantic"
            else raw
        )
        return self._reshape(source, config.schema)

    @staticmethod
    def _physical_signature(
        tables: Mapping[str, Sequence[Mapping[str, object]]],
        schema: SchemaDesign,
    ) -> str:
        """Fingerprint values after SQLite's declared column affinities."""
        normalized: Dict[str, List[dict]] = {}
        for relation in schema.relations:
            rows = []
            for row in tables.get(relation.name, ()):
                output = {}
                for column in relation.attributes:
                    value = row.get(column)
                    if (
                        value not in (None, "")
                        and relation.semantic_type(column)
                        in {"integer", "real", "boolean"}
                        and not isinstance(value, bytes)
                    ):
                        try:
                            number = float(str(value).strip())
                        except ValueError:
                            pass
                        else:
                            if math.isfinite(number):
                                value = (
                                    int(number)
                                    if number.is_integer()
                                    else number
                                )
                    output[column] = value
                rows.append(output)
            normalized[relation.name] = rows
        return _fingerprint(normalized)

    def _semantic_changes_are_supported(
        self,
        tables: Mapping[str, Sequence[Mapping[str, object]]],
    ) -> bool:
        assert self._shared is not None
        supported = {
            (cell.relation, cell.row_identity, cell.column)
            for cell in self._shared.evidence
            if cell.supported
        }
        raw_index = {
            (relation, str(row.get("row_id", ""))): row
            for relation, rows in self._shared.raw_tables.items()
            for row in rows
        }
        changed = False
        for relation, rows in tables.items():
            for row in rows:
                identity = str(row.get("row_id", ""))
                original = raw_index.get((relation, identity))
                if original is None:
                    return False
                for column, value in row.items():
                    if column == "row_id" or value == original.get(column):
                        continue
                    changed = True
                    if (relation, identity, column) not in supported:
                        return False
        return changed

    def prune_configs(
        self,
        configs: Sequence[SynthesisConfig],
    ) -> Sequence[SynthesisConfig]:
        """Remove evidence-equivalent or unsupported semantic candidates."""
        if self._shared is None:
            return tuple(configs)
        retained: List[SynthesisConfig] = []
        signatures: set[str] = set()
        ordered = sorted(
            configs,
            key=lambda config: (
                self._candidate_kind.get(config.config_id) != "raw",
                config.config_id,
            ),
        )
        for config in ordered:
            tables = self._candidate_tables(config, sample_fraction=1.0)
            kind = self._candidate_kind.get(config.config_id, "raw")
            if (
                kind == "evidence_semantic"
                and not self._semantic_changes_are_supported(tables)
            ):
                continue
            signature = self._physical_signature(tables, config.schema)
            if signature in signatures:
                continue
            signatures.add(signature)
            retained.append(config)
        return tuple(sorted(retained, key=lambda item: item.config_id))

    def completion_reserve(
        self,
        _configs: Sequence[SynthesisConfig],
        _requirements: Sequence[QueryRequirement],
    ) -> int:
        # Shared extraction happens in prepare; candidate construction is local.
        return 0

    def estimate_full_cost(
        self,
        _config: SynthesisConfig,
        _requirements: Sequence[QueryRequirement],
    ) -> int:
        # Token cost after shared preparation is zero. Extractors that call an
        # LLM must use the ledger passed to extract(...).
        return 0

    def _persist_candidate_provenance(
        self,
        config: SynthesisConfig,
        tables: Mapping[str, Sequence[Mapping[str, object]]],
        evidence_store: EvidenceStore,
    ) -> None:
        assert self._shared is not None
        by_exact: Dict[Tuple[str, str, str, str], SharedCellEvidence] = {}
        by_value: Dict[Tuple[str, str, str], SharedCellEvidence] = {}
        for cell in self._shared.evidence:
            rendered = json.dumps(
                _jsonable(cell.value), sort_keys=True, separators=(",", ":")
            )
            by_exact[
                (cell.relation, cell.row_identity, cell.column, rendered)
            ] = cell
            by_value.setdefault((cell.relation, cell.column, rendered), cell)
        mapped_sources: Dict[
            Tuple[str, str, str], List[Tuple[str, object]]
        ] = {}
        for mapping in (
            self._shared.metadata.get("derivation_mappings", ())
            if isinstance(self._shared.metadata, Mapping)
            else ()
        ):
            relation = str(_member(mapping, "entity", default=""))
            column = str(
                _member(mapping, "attribute", default="")
            )
            source_rendered = json.dumps(
                _jsonable(
                    _member(mapping, "source_value", default=None)
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
            target_rendered = json.dumps(
                _jsonable(
                    _member(mapping, "target_value", default=None)
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
            mapped_sources.setdefault(
                (relation, column, target_rendered), []
            ).append((source_rendered, mapping))
        evidence_store.conn.execute(
            "DELETE FROM cell_provenance WHERE config_id = ?",
            (config.config_id,),
        )
        copied = []
        lineages: List[DerivationLineage] = []
        relations = {relation.name: relation for relation in config.schema.relations}
        for relation_name, rows in tables.items():
            relation = relations.get(relation_name)
            if relation is None:
                continue
            for index, row in enumerate(rows):
                identity = str(
                    row.get("row_id")
                    or _row_identity(relation, row, index)
                )
                for column in relation.attributes:
                    value = row.get(column)
                    if value in (None, ""):
                        continue
                    rendered = json.dumps(
                        _jsonable(value),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    source = (
                        by_exact.get(
                            (
                                relation_name,
                                identity,
                                column,
                                rendered,
                            )
                        )
                        or by_value.get(
                            (relation_name, column, rendered)
                        )
                    )
                    mapping_used = None
                    if source is None:
                        for source_rendered, mapping in mapped_sources.get(
                            (relation_name, column, rendered), ()
                        ):
                            source = (
                                by_exact.get(
                                    (
                                        relation_name,
                                        identity,
                                        column,
                                        source_rendered,
                                    )
                                )
                                or by_value.get(
                                    (
                                        relation_name,
                                        column,
                                        source_rendered,
                                    )
                                )
                            )
                            if source is not None:
                                mapping_used = (
                                    source_rendered,
                                    mapping,
                                )
                                break
                    if source is None:
                        continue
                    copied.append(
                        CellProvenance(
                            config_id=config.config_id,
                            relation=relation_name,
                            row_identity=identity,
                            column=column,
                            value_json=rendered,
                            anchor_id=source.anchor_id,
                            entailed=source.entailed,
                            span_restored=source.span_restored,
                        )
                    )
                    if mapping_used is not None:
                        source_rendered, mapping = mapping_used
                        lineages.append(
                            DerivationLineage(
                                config_id=config.config_id,
                                relation=relation_name,
                                column=column,
                                source_value_json=source_rendered,
                                derived_value_json=rendered,
                                mapping_kind=str(
                                    _member(
                                        mapping,
                                        "mapping_kind",
                                        default="mapping",
                                    )
                                ),
                                evidence_anchor_ids=(
                                    source.anchor_id,
                                ),
                            )
                        )
        evidence_store.add_cell_provenance(copied)
        if lineages:
            evidence_store.add_derivation_lineage(lineages)

    def _apply_mapping_contract(
        self,
        config: SynthesisConfig,
        assessments: Mapping[str, QueryAssessment],
    ) -> Dict[str, QueryAssessment]:
        """Treat an explicitly induced query mapping as a hard plan contract."""
        if self._shared is None or self.intent is None:
            return dict(assessments)
        mapped_fields = {
            (
                str(_member(mapping, "entity", default="")),
                str(_member(mapping, "attribute", default="")),
            )
            for mapping in (
                self._shared.metadata.get("derivation_mappings", ())
                if isinstance(self._shared.metadata, Mapping)
                else ()
            )
        }
        if not mapped_fields:
            return dict(assessments)
        requirement_by_id = {
            requirement.query_id: requirement
            for requirement in self.intent.requirements
        }
        semantic = (
            self._candidate_kind.get(config.config_id)
            == "evidence_semantic"
        )
        adjusted: Dict[str, QueryAssessment] = {}
        for query_id, assessment in assessments.items():
            requirement = requirement_by_id.get(query_id)
            references = (
                requirement.plan.attributes()
                if requirement is not None
                and requirement.plan is not None
                else ()
            )
            relevant = any(
                (reference.entity, reference.attribute) in mapped_fields
                for reference in references
            )
            if not relevant:
                adjusted[query_id] = assessment
                continue
            estimate = assessment.estimate
            components = dict(estimate.components)
            components["contract_mapping_alignment"] = float(semantic)
            if semantic:
                updated_estimate = replace(
                    estimate, components=components
                )
            else:
                updated_estimate = replace(
                    estimate,
                    validity=0.0,
                    uncertainty=1.0,
                    components=components,
                )
            adjusted[query_id] = replace(
                assessment, estimate=updated_estimate
            )
        return adjusted

    def _document_bootstrap_tables(
        self,
        tables: Mapping[str, Sequence[Mapping[str, object]]],
        fold: int,
    ) -> Dict[str, List[dict]]:
        """Return a deterministic document jackknife sample."""
        assert self._shared is not None
        documents_by_row: Dict[Tuple[str, str], set[str]] = {}
        for cell in self._shared.evidence:
            documents_by_row.setdefault(
                (cell.relation, cell.row_identity), set()
            ).add(cell.document_id)
        sampled: Dict[str, List[dict]] = {}
        for relation, rows in tables.items():
            retained = []
            for row in rows:
                identity = str(row.get("row_id", ""))
                documents = documents_by_row.get(
                    (relation, identity), set()
                )
                key = (
                    min(documents)
                    if documents
                    else "row:" + _fingerprint((relation, identity))
                )
                held_out = (
                    int.from_bytes(
                        hashlib.sha256(
                            f"bootstrap-v1\0{key}".encode("utf-8")
                        ).digest()[:8],
                        "big",
                    )
                    % self.bootstrap_folds
                    == fold
                )
                if not held_out:
                    retained.append(dict(row))
            sampled[relation] = retained
        return sampled

    def _apply_output_bootstraps(
        self,
        config: SynthesisConfig,
        tables: Mapping[str, Sequence[Mapping[str, object]]],
        assessments: Mapping[str, QueryAssessment],
        directory: Path,
    ) -> Dict[str, QueryAssessment]:
        """Execute typed plans over deterministic document jackknifes."""
        executions: Dict[str, List[QueryExecution]] = {
            query_id: [] for query_id in assessments
        }
        requirements = {
            requirement.query_id: requirement
            for requirement in (
                self.intent.requirements if self.intent is not None else ()
            )
        }
        for fold in range(self.bootstrap_folds):
            bootstrap_path = write_sqlite_database(
                directory / f"bootstrap-{fold}.sqlite",
                self._document_bootstrap_tables(tables, fold),
                config.schema,
            )
            for query_id in assessments:
                requirement = requirements.get(query_id)
                if requirement is None:
                    continue
                try:
                    execution = execute_readonly(
                        bootstrap_path,
                        compile_typed_plan(requirement, config),
                        max_rows=self.max_query_rows,
                    )
                except (
                    QueryCompilationError,
                    QueryExecutionError,
                    OSError,
                    sqlite3.Error,
                ):
                    continue
                executions[query_id].append(execution)
        adjusted: Dict[str, QueryAssessment] = {}
        for query_id, assessment in assessments.items():
            requirement = requirements.get(query_id)
            if requirement is None or assessment.execution is None:
                adjusted[query_id] = assessment
                continue
            stability = bootstrap_output_stability(
                requirement,
                assessment.execution,
                executions.get(query_id, ()),
            )
            components = dict(assessment.estimate.components)
            components[
                "document_bootstrap_output_stability"
            ] = stability
            estimate = replace(
                assessment.estimate,
                validity=assessment.estimate.validity * stability,
                uncertainty=max(
                    assessment.estimate.uncertainty,
                    1.0 - stability,
                ),
                components=components,
            )
            adjusted[query_id] = replace(
                assessment, estimate=estimate
            )
        return adjusted

    def pilot(
        self,
        config: SynthesisConfig,
        sample_fraction: float,
        evidence_store: EvidenceStore,
        _ledger: GlobalBudgetLedger,
    ) -> PilotResult:
        if not 0.0 < sample_fraction <= 1.0:
            raise ValueError("sample_fraction must lie in (0,1]")
        if self.intent is None:
            raise RuntimeError("prepare must run before pilot")
        tables = self._candidate_tables(
            config, sample_fraction=sample_fraction
        )
        self._persist_candidate_provenance(config, tables, evidence_store)
        with temporary_work_dir(
            "contract-spp-pilot-",
            parent=self.scratch_dir,
        ) as directory:
            path = write_sqlite_database(
                directory / "pilot.sqlite", tables, config.schema
            )
            assessments = assess_workload_quality(
                self.intent.requirements,
                config,
                path,
                evidence_store,
                max_rows=self.max_query_rows,
            )
            assessments = self._apply_output_bootstraps(
                config, tables, assessments, directory
            )
            assessments = self._apply_mapping_contract(
                config, assessments
            )
        outputs = {
            query_id: (
                assessment.execution.rows
                if assessment.execution is not None
                else ()
            )
            for query_id, assessment in assessments.items()
        }
        return PilotResult(
            config_id=config.config_id,
            estimates={
                query_id: assessment.estimate
                for query_id, assessment in assessments.items()
            },
            output_signature=canonical_output_signature(outputs),
            full_cost_upper_bound=0,
            sample_fraction=sample_fraction,
            metadata={
                "candidate_kind": self._candidate_kind.get(
                    config.config_id, "raw"
                ),
                "rows_by_relation": {
                    name: len(rows) for name, rows in sorted(tables.items())
                },
                "shared_extraction": self._shared_artifact_key,
            },
        )

    def materialize(
        self,
        config: SynthesisConfig,
        evidence_store: EvidenceStore,
        _ledger: GlobalBudgetLedger,
        output_path: Path,
    ) -> Path:
        tables = self._candidate_tables(config, sample_fraction=1.0)
        self._persist_candidate_provenance(config, tables, evidence_store)
        return write_sqlite_database(output_path, tables, config.schema)

    def validate_materialization(
        self,
        config: SynthesisConfig,
        database_path: Path,
        requirements: Sequence[QueryRequirement],
        evidence_store: EvidenceStore,
        _ledger: GlobalBudgetLedger,
    ) -> Mapping[str, QualityEstimate]:
        uri = Path(database_path).expanduser().resolve().as_uri()
        with sqlite3.connect(uri + "?mode=ro&immutable=1", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or str(integrity[0]).lower() != "ok":
                raise RuntimeError(
                    f"materialized SQLite integrity check failed: {integrity}"
                )
        assessments = assess_workload_quality(
            requirements,
            config,
            database_path,
            evidence_store,
            max_rows=self.max_query_rows,
        )
        tables = self._candidate_tables(
            config, sample_fraction=1.0
        )
        with temporary_work_dir(
            "contract-spp-validation-",
            parent=self.scratch_dir,
        ) as directory:
            assessments = self._apply_output_bootstraps(
                config, tables, assessments, directory
            )
        assessments = self._apply_mapping_contract(
            config, assessments
        )
        return {
            query_id: assessment.estimate
            for query_id, assessment in assessments.items()
        }

    def reproducibility_manifest(self) -> dict:
        extractor = self.extractor
        extractor_manifest = {
            "module": (
                type(extractor).__module__ if extractor is not None else None
            ),
            "class": (
                type(extractor).__qualname__ if extractor is not None else None
            ),
            "version": (
                str(getattr(extractor, "version", ""))
                if extractor is not None
                else None
            ),
            "model": (
                str(
                    getattr(
                        self.llm_client,
                        "model",
                        type(self.llm_client).__name__,
                    )
                )
            ),
            "max_workers": (
                int(getattr(extractor, "max_workers", 1))
                if extractor is not None
                else None
            ),
            "max_context_characters": (
                int(getattr(extractor, "max_context_characters", 0))
                if extractor is not None
                else None
            ),
        }
        return {
            "backend": type(self).__name__,
            "backend_version": BACKEND_VERSION,
            "external_labels_used": False,
            "contract_sha256": (
                _fingerprint(self.contract)
                if self.contract is not None
                else None
            ),
            "relation_graph_sha256": (
                self.relation_graph.fingerprint
                if self.relation_graph is not None
                else None
            ),
            "shared_extraction_key": self._shared_artifact_key,
            "shared_extraction_sha256": (
                _fingerprint(_shared_payload(self._shared))
                if self._shared is not None
                else None
            ),
            "preprocessing_policy": asdict(self.preprocessing_policy),
            "candidate_semantics": dict(sorted(self._candidate_kind.items())),
            "repair": dict(self._repair_summary),
            "derivation_mapping_count": (
                len(
                    self._shared.metadata.get(
                        "derivation_mappings", ()
                    )
                )
                if self._shared is not None
                and isinstance(self._shared.metadata, Mapping)
                else 0
            ),
            "extractor": extractor_manifest,
            "quality_estimator": {
                "module": "spp.query_quality",
                "max_query_rows": self.max_query_rows,
                "document_bootstrap_folds": self.bootstrap_folds,
                "sqlite_read_only": True,
            },
            "documents": [
                {
                    "document_id": document.document_id,
                    "sha256": hashlib.sha256(
                        document.text.encode("utf-8")
                    ).hexdigest(),
                    "metadata_sha256": _fingerprint(document.metadata),
                }
                for document in self.documents
            ],
        }


__all__ = [
    "BACKEND_VERSION",
    "ContractBackend",
    "ContractDocument",
    "ContractIntegrationError",
    "RelationEdge",
    "SharedCellEvidence",
    "SharedExtraction",
    "WorkloadRelationGraph",
    "build_workload_relation_graph",
]

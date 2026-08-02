"""Ground-truth-free quality checks for typed workload queries.

The functions in this module compile the existing typed query-plan IR, execute
the resulting SQL against an immutable SQLite database, and combine provenance,
relational, stability, metamorphic, aggregate, and join signals.  Nothing in
this module imports benchmark evaluation data or an oracle.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from spp.evidence_store import EvidenceStore
from spp.query_plan_compiler import compile_query_plan
from spp.quality_signals import profile_relational_database
from spp.spec import (
    AttributeRef,
    QualityEstimate,
    QueryRequirement,
    SynthesisConfig,
)


_READ_PREFIX = re.compile(r"^\s*(?:SELECT|WITH)\b", re.IGNORECASE)
_DENIED_SQLITE_ACTIONS = {
    value
    for name in (
        "SQLITE_ALTER_TABLE",
        "SQLITE_ANALYZE",
        "SQLITE_ATTACH",
        "SQLITE_CREATE_INDEX",
        "SQLITE_CREATE_TABLE",
        "SQLITE_CREATE_TEMP_INDEX",
        "SQLITE_CREATE_TEMP_TABLE",
        "SQLITE_CREATE_TEMP_TRIGGER",
        "SQLITE_CREATE_TEMP_VIEW",
        "SQLITE_CREATE_TRIGGER",
        "SQLITE_CREATE_VIEW",
        "SQLITE_DELETE",
        "SQLITE_DETACH",
        "SQLITE_DROP_INDEX",
        "SQLITE_DROP_TABLE",
        "SQLITE_DROP_TEMP_INDEX",
        "SQLITE_DROP_TEMP_TABLE",
        "SQLITE_DROP_TEMP_TRIGGER",
        "SQLITE_DROP_TEMP_VIEW",
        "SQLITE_DROP_TRIGGER",
        "SQLITE_DROP_VIEW",
        "SQLITE_INSERT",
        "SQLITE_PRAGMA",
        "SQLITE_REINDEX",
        "SQLITE_TRANSACTION",
        "SQLITE_UPDATE",
    )
    if (value := getattr(sqlite3, name, None)) is not None
}


class QueryCompilationError(ValueError):
    """A typed workload plan cannot bind unambiguously to a candidate."""


class QueryExecutionError(RuntimeError):
    """A read-only query could not be executed safely."""


@dataclass(frozen=True)
class QueryExecution:
    sql: str
    columns: Tuple[str, ...]
    rows: Tuple[Mapping[str, object], ...]
    canonical_digest: str
    value_digest: str
    truncated: bool = False

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class EvidenceCoverage:
    precision: float
    recall: float
    output_support: float
    supported_cells: int
    provenance_cells: int
    materialized_cells: int
    required_attributes: int
    covered_attributes: int
    sample_size: int


@dataclass(frozen=True)
class QueryAssessment:
    estimate: QualityEstimate
    execution: Optional[QueryExecution]
    sql: Optional[str]
    error: Optional[str] = None


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return str(value)


def _canonical_payload(
    columns: Sequence[str], rows: Iterable[Sequence[object]]
) -> Tuple[str, str]:
    normalized_rows = [
        [_jsonable(value) for value in row]
        for row in rows
    ]
    normalized_rows.sort(
        key=lambda row: json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    )
    value_payload = json.dumps(
        normalized_rows,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    payload = json.dumps(
        {"columns": list(columns), "rows": normalized_rows},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return (
        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        hashlib.sha256(value_payload.encode("utf-8")).hexdigest(),
    )


def compile_typed_plan(
    requirement: QueryRequirement,
    config: SynthesisConfig,
) -> str:
    """Compile one complete typed plan or raise a diagnostic exception."""
    if requirement.plan is None:
        raise QueryCompilationError(
            f"query {requirement.query_id!r} has no typed query plan"
        )
    sql = compile_query_plan(requirement.plan, config)
    if not sql:
        raise QueryCompilationError(
            f"query {requirement.query_id!r} cannot bind to "
            f"candidate {config.config_id!r}"
        )
    return sql


def compile_typed_plans(
    requirements: Sequence[QueryRequirement],
    config: SynthesisConfig,
) -> Dict[str, str]:
    """Compile all schema-covered typed plans for one candidate."""
    return {
        requirement.query_id: compile_typed_plan(requirement, config)
        for requirement in requirements
        if config.schema.covers(requirement)
    }


def _readonly_uri(database_path: Path) -> str:
    resolved = Path(database_path).expanduser().resolve()
    if not resolved.is_file():
        raise QueryExecutionError(f"SQLite database does not exist: {resolved}")
    return resolved.as_uri() + "?mode=ro&immutable=1"


def _readonly_authorizer(
    action: int,
    _arg1: Optional[str],
    _arg2: Optional[str],
    _database: Optional[str],
    _trigger: Optional[str],
) -> int:
    if action in _DENIED_SQLITE_ACTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def execute_readonly(
    database_path: Path,
    sql: str,
    *,
    max_rows: int = 100_000,
    max_vm_steps: int = 10_000_000,
    reverse_unordered_selects: bool = False,
) -> QueryExecution:
    """Execute one SELECT in immutable mode with bounded rows and VM steps."""
    if not isinstance(sql, str) or not _READ_PREFIX.match(sql):
        raise QueryExecutionError("only SELECT/WITH statements are allowed")
    if max_rows <= 0 or max_vm_steps <= 0:
        raise ValueError("execution limits must be positive")

    steps = 0

    def progress() -> int:
        nonlocal steps
        steps += 1_000
        return int(steps > max_vm_steps)

    try:
        with sqlite3.connect(
            _readonly_uri(database_path), uri=True
        ) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.execute(
                "PRAGMA reverse_unordered_selects="
                + ("ON" if reverse_unordered_selects else "OFF")
            )
            connection.set_authorizer(_readonly_authorizer)
            connection.set_progress_handler(progress, 1_000)
            cursor = connection.execute(sql)
            columns = tuple(
                str(description[0]) for description in (cursor.description or ())
            )
            raw_rows = cursor.fetchmany(max_rows + 1)
    except sqlite3.Error as exc:
        raise QueryExecutionError(str(exc)) from exc

    truncated = len(raw_rows) > max_rows
    raw_rows = raw_rows[:max_rows]
    digest, value_digest = _canonical_payload(columns, raw_rows)
    mapped_rows = tuple(
        {
            columns[index]: row[index]
            for index in range(min(len(columns), len(row)))
        }
        for row in raw_rows
    )
    return QueryExecution(
        sql=sql,
        columns=columns,
        rows=mapped_rows,
        canonical_digest=digest,
        value_digest=value_digest,
        truncated=truncated,
    )


execute_sqlite_readonly = execute_readonly


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _locate_attribute(
    reference: AttributeRef,
    config: SynthesisConfig,
) -> Optional[Tuple[str, str]]:
    direct = [
        relation
        for relation in config.schema.relations
        if relation.name == reference.entity
        and reference.attribute in relation.attributes
    ]
    if len(direct) == 1:
        return direct[0].name, reference.attribute
    candidates = [
        relation
        for relation in config.schema.relations
        if reference.attribute in relation.attributes
    ]
    if len(candidates) == 1:
        return candidates[0].name, reference.attribute
    if (
        config.schema.pattern == "denormalized"
        and config.schema.relations
        and reference.attribute in config.schema.relations[0].attributes
    ):
        return config.schema.relations[0].name, reference.attribute
    return None


def _required_locations(
    requirement: QueryRequirement,
    config: SynthesisConfig,
) -> Tuple[Tuple[str, str], ...]:
    references = list(requirement.plan.attributes()) if requirement.plan else []
    if not references:
        references.extend(
            AttributeRef(entity, attribute)
            for entity, attribute in requirement.attribute_bindings
        )
    locations = [
        location
        for reference in references
        if (location := _locate_attribute(reference, config)) is not None
    ]
    if not locations and requirement.plan and requirement.plan.aggregates:
        for relation in config.schema.relations:
            column = relation.primary_key or (
                relation.attributes[0] if relation.attributes else None
            )
            if column:
                locations.append((relation.name, column))
                break
    return tuple(dict.fromkeys(locations))


def _materialized_counts(
    database_path: Path,
    locations: Sequence[Tuple[str, str]],
) -> Dict[Tuple[str, str], int]:
    counts: Dict[Tuple[str, str], int] = {}
    with sqlite3.connect(_readonly_uri(database_path), uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        for table, column in locations:
            try:
                counts[(table, column)] = int(
                    connection.execute(
                        f"SELECT COUNT({_quote(column)}) "
                        f"FROM {_quote(table)}"
                    ).fetchone()[0]
                )
            except sqlite3.Error:
                counts[(table, column)] = 0
    return counts


def _relation_row_counts(
    database_path: Path,
    locations: Sequence[Tuple[str, str]],
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    with sqlite3.connect(_readonly_uri(database_path), uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        for table in dict.fromkeys(table for table, _column in locations):
            try:
                counts[table] = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {_quote(table)}"
                    ).fetchone()[0]
                )
            except sqlite3.Error:
                counts[table] = 0
    return counts


def _provenance_rows(
    evidence_store: Optional[EvidenceStore],
    config_ids: Sequence[str],
    locations: Sequence[Tuple[str, str]],
) -> Sequence[sqlite3.Row]:
    if evidence_store is None or not config_ids:
        return ()
    unique_config_ids = tuple(dict.fromkeys(config_ids))
    placeholders = ",".join("?" for _ in unique_config_ids)
    clauses = []
    params: list[object] = list(unique_config_ids)
    for table, column in locations:
        clauses.append("(cp.relation_name = ? AND cp.column_name = ?)")
        params.extend((table, column))
    location_sql = " AND (" + " OR ".join(clauses) + ")" if clauses else ""
    sql = (
        "SELECT cp.*, a.document_id "
        "FROM cell_provenance cp "
        "LEFT JOIN anchors a ON a.anchor_id = cp.anchor_id "
        f"WHERE cp.config_id IN ({placeholders})"
        f"{location_sql}"
    )
    try:
        return evidence_store.conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return ()


def _decode_json(value: object) -> object:
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return str(value)


def compute_evidence_coverage(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
    evidence_store: Optional[EvidenceStore],
    *,
    execution: Optional[QueryExecution] = None,
    evidence_config_ids: Sequence[str] = (),
) -> EvidenceCoverage:
    """Measure query-conditioned cell and output support from provenance."""
    locations = _required_locations(requirement, config)
    counts = _materialized_counts(database_path, locations)
    relation_counts = _relation_row_counts(database_path, locations)
    config_ids = tuple(
        dict.fromkeys((config.config_id, *evidence_config_ids))
    )
    provenance = _provenance_rows(
        evidence_store, config_ids, locations
    )
    unique = {
        (
            str(row["relation_name"]),
            str(row["row_identity"]),
            str(row["column_name"]),
            str(row["anchor_id"]),
        ): row
        for row in provenance
    }
    supported = {
        key: row
        for key, row in unique.items()
        if bool(row["entailed"]) and bool(row["span_restored"])
    }
    materialized_cells = sum(counts.values())
    precision = (
        len(supported)
        / max(materialized_cells, len(unique), 1)
        if locations
        else 0.0
    )

    supported_by_location: Dict[Tuple[str, str], set[str]] = {}
    for row in supported.values():
        location = (str(row["relation_name"]), str(row["column_name"]))
        supported_by_location.setdefault(location, set()).add(
            str(row["row_identity"])
        )
    per_attribute = [
        min(
            len(supported_by_location.get(location, set()))
            / max(relation_counts.get(location[0], 0), 1),
            1.0,
        )
        if relation_counts.get(location[0], 0) > 0
        else 0.0
        for location in locations
    ]
    recall = sum(per_attribute) / len(per_attribute) if per_attribute else 0.0

    aggregate_columns = {
        aggregate.alias
        or (
            f"{aggregate.function}_{aggregate.attribute.attribute}"
            if aggregate.attribute is not None
            else "count_all"
        )
        for aggregate in (
            requirement.plan.aggregates if requirement.plan else ()
        )
    }
    output_values = []
    if execution is not None:
        for row in execution.rows:
            for column, value in row.items():
                if column not in aggregate_columns and value is not None:
                    output_values.append(_jsonable(value))
    supported_values = {
        json.dumps(
            _jsonable(_decode_json(row["value_json"])),
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in supported.values()
    }
    if not output_values:
        output_support = precision if aggregate_columns else 0.0
    else:
        output_support = sum(
            json.dumps(
                value, sort_keys=True, separators=(",", ":")
            )
            in supported_values
            for value in output_values
        ) / len(output_values)

    sample_keys = {
        str(row["document_id"] or row["row_identity"])
        for row in supported.values()
    }
    covered_attributes = sum(
        bool(supported_by_location.get(location)) for location in locations
    )
    return EvidenceCoverage(
        precision=_clamp(precision),
        recall=_clamp(recall),
        output_support=_clamp(output_support),
        supported_cells=len(supported),
        provenance_cells=len(unique),
        materialized_cells=materialized_cells,
        required_attributes=len(locations),
        covered_attributes=covered_attributes,
        sample_size=len(sample_keys),
    )


def _aggregate_grouping_signals(
    requirement: QueryRequirement,
    execution: QueryExecution,
) -> Tuple[float, float]:
    if requirement.plan is None or not requirement.plan.aggregates:
        return 1.0, 1.0
    checks: list[float] = []
    for aggregate in requirement.plan.aggregates:
        alias = aggregate.alias or (
            f"{aggregate.function}_{aggregate.attribute.attribute}"
            if aggregate.attribute is not None
            else "count_all"
        )
        if alias not in execution.columns:
            checks.append(0.0)
            continue
        values = [row.get(alias) for row in execution.rows]
        valid = all(
            value is None
            or (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and (aggregate.function != "count" or float(value) >= 0)
            )
            for value in values
        )
        checks.append(float(valid))
    grouping = 1.0
    if requirement.plan.group_by:
        group_columns = [
            reference.attribute for reference in requirement.plan.group_by
        ]
        groups = [
            tuple(row.get(column) for column in group_columns)
            for row in execution.rows
        ]
        grouping = float(len(groups) == len(set(groups)))
    elif len(execution.rows) != 1:
        grouping = 0.0
    aggregate = sum(checks) / len(checks) if checks else 1.0
    return aggregate, grouping


def _aggregate_additivity(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
    execution: QueryExecution,
    *,
    max_rows: int,
) -> float:
    """Check grouped aggregates against the corresponding global aggregate."""
    plan = requirement.plan
    if (
        plan is None
        or not plan.aggregates
        or not plan.group_by
        or plan.having
    ):
        return 1.0
    comparable = [
        aggregate
        for aggregate in plan.aggregates
        if aggregate.function in {"count", "sum", "min", "max"}
    ]
    if not comparable:
        return 1.0
    global_requirement = replace(
        requirement,
        plan=replace(
            plan,
            projections=(),
            group_by=(),
            having=(),
        ),
    )
    try:
        global_execution = execute_readonly(
            database_path,
            compile_typed_plan(global_requirement, config),
            max_rows=max_rows,
        )
    except (QueryCompilationError, QueryExecutionError):
        return 0.0
    if len(global_execution.rows) != 1:
        return 0.0
    global_row = global_execution.rows[0]
    checks: list[float] = []
    for aggregate in comparable:
        alias = aggregate.alias or (
            f"{aggregate.function}_{aggregate.attribute.attribute}"
            if aggregate.attribute is not None
            else "count_all"
        )
        grouped_values = [
            row.get(alias)
            for row in execution.rows
            if row.get(alias) is not None
        ]
        global_value = global_row.get(alias)
        if global_value is None:
            checks.append(float(not grouped_values))
            continue
        numeric_values = (global_value, *grouped_values)
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in numeric_values
        ):
            checks.append(0.0)
            continue
        if aggregate.function in {"count", "sum"}:
            observed = sum(float(value) for value in grouped_values)
        elif aggregate.function == "min":
            observed = (
                min(float(value) for value in grouped_values)
                if grouped_values
                else float(global_value)
            )
        else:
            observed = (
                max(float(value) for value in grouped_values)
                if grouped_values
                else float(global_value)
            )
        checks.append(
            float(
                math.isclose(
                    observed,
                    float(global_value),
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                )
            )
        )
    return sum(checks) / len(checks) if checks else 1.0


def _row_signature(row: Mapping[str, object]) -> str:
    return json.dumps(
        _jsonable(dict(row)),
        sort_keys=True,
        separators=(",", ":"),
    )


def _predicate_monotonicity(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
    execution: QueryExecution,
    *,
    max_rows: int,
) -> float:
    plan = requirement.plan
    if plan is None or plan.predicate is None:
        return 1.0
    relaxed_requirement = replace(
        requirement,
        plan=replace(plan, predicate=None),
    )
    try:
        relaxed = execute_readonly(
            database_path,
            compile_typed_plan(relaxed_requirement, config),
            max_rows=max_rows,
        )
    except (QueryCompilationError, QueryExecutionError):
        return 0.0
    if execution.truncated or relaxed.truncated:
        return 0.0
    if not plan.aggregates:
        filtered_counts = Counter(
            _row_signature(row) for row in execution.rows
        )
        relaxed_counts = Counter(
            _row_signature(row) for row in relaxed.rows
        )
        return float(
            all(
                count <= relaxed_counts[signature]
                for signature, count in filtered_counts.items()
            )
        )

    group_columns = tuple(
        reference.attribute for reference in plan.group_by
    )
    filtered_groups = {
        tuple(row.get(column) for column in group_columns)
        for row in execution.rows
    }
    relaxed_groups = {
        tuple(row.get(column) for column in group_columns)
        for row in relaxed.rows
    }
    if not filtered_groups <= relaxed_groups:
        return 0.0
    count_aliases = [
        aggregate.alias
        or (
            f"count_{aggregate.attribute.attribute}"
            if aggregate.attribute is not None
            else "count_all"
        )
        for aggregate in plan.aggregates
        if aggregate.function == "count"
    ]
    if not count_aliases:
        return 1.0
    relaxed_by_group = {
        tuple(row.get(column) for column in group_columns): row
        for row in relaxed.rows
    }
    return float(
        all(
            float(row.get(alias, 0) or 0)
            <= float(
                relaxed_by_group.get(
                    tuple(row.get(column) for column in group_columns),
                    {},
                ).get(alias, 0)
                or 0
            )
            for row in execution.rows
            for alias in count_aliases
        )
    )


def _provenance_bootstrap_stability(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    evidence_store: Optional[EvidenceStore],
    evidence_config_ids: Sequence[str],
    *,
    rounds: int = 64,
) -> float:
    locations = _required_locations(requirement, config)
    config_ids = tuple(
        dict.fromkeys((config.config_id, *evidence_config_ids))
    )
    rows = _provenance_rows(evidence_store, config_ids, locations)
    atoms = {
        (
            str(row["relation_name"]),
            str(row["row_identity"]),
            str(row["column_name"]),
            str(row["anchor_id"]),
        ): (
            str(row["document_id"] or row["row_identity"]),
            bool(row["entailed"]) and bool(row["span_restored"]),
        )
        for row in rows
    }
    by_document: Dict[str, List[bool]] = {}
    for document_id, supported in atoms.values():
        by_document.setdefault(document_id, []).append(supported)
    documents = tuple(sorted(by_document))
    if not documents:
        return 0.0
    scores = []
    seed = (
        f"{requirement.query_id}\0{config.config_id}\0"
        "provenance-bootstrap-v1"
    )
    for round_index in range(rounds):
        sample = []
        for slot in range(len(documents)):
            digest = hashlib.sha256(
                f"{seed}\0{round_index}\0{slot}".encode("utf-8")
            ).digest()
            document = documents[
                int.from_bytes(digest[:8], "big") % len(documents)
            ]
            sample.extend(by_document[document])
        scores.append(sum(sample) / len(sample) if sample else 0.0)
    average = sum(scores) / len(scores)
    variance = sum((score - average) ** 2 for score in scores) / len(scores)
    return _clamp(1.0 - 2.0 * math.sqrt(variance))


def bootstrap_output_stability(
    requirement: QueryRequirement,
    baseline: QueryExecution,
    bootstraps: Sequence[QueryExecution],
) -> float:
    """Validate query-output invariants across deterministic document samples."""
    if not bootstraps:
        return 0.0
    plan = requirement.plan
    scores: list[float] = []
    for sample in bootstraps:
        if sample.columns != baseline.columns or sample.truncated:
            scores.append(0.0)
            continue
        checks = [1.0]
        if plan is None or not plan.aggregates:
            baseline_counts = Counter(
                _row_signature(row) for row in baseline.rows
            )
            sample_counts = Counter(
                _row_signature(row) for row in sample.rows
            )
            checks.append(
                float(
                    all(
                        count <= baseline_counts[signature]
                        for signature, count in sample_counts.items()
                    )
                )
            )
        else:
            group_columns = tuple(
                reference.attribute for reference in plan.group_by
            )
            baseline_by_group = {
                tuple(row.get(column) for column in group_columns): row
                for row in baseline.rows
            }
            sample_by_group = {
                tuple(row.get(column) for column in group_columns): row
                for row in sample.rows
            }
            checks.append(
                float(
                    set(sample_by_group) <= set(baseline_by_group)
                    if group_columns
                    else len(sample.rows) <= 1
                )
            )
            for aggregate in plan.aggregates:
                alias = aggregate.alias or (
                    f"{aggregate.function}_{aggregate.attribute.attribute}"
                    if aggregate.attribute is not None
                    else "count_all"
                )
                for group, row in sample_by_group.items():
                    value = row.get(alias)
                    if value is not None and (
                        not isinstance(value, (int, float))
                        or isinstance(value, bool)
                        or not math.isfinite(float(value))
                    ):
                        checks.append(0.0)
                        continue
                    if aggregate.function == "count":
                        baseline_value = baseline_by_group.get(
                            group, {}
                        ).get(alias)
                        checks.append(
                            float(
                                baseline_value is not None
                                and float(value or 0)
                                <= float(baseline_value or 0)
                            )
                        )
        scores.append(sum(checks) / len(checks))
    return sum(scores) / len(scores)


def _join_signal(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
) -> float:
    if requirement.plan is None or not requirement.plan.joins:
        return 1.0
    scores: list[float] = []
    with sqlite3.connect(_readonly_uri(database_path), uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        for join in requirement.plan.joins:
            left = _locate_attribute(join.left, config)
            right = _locate_attribute(join.right, config)
            if left is None or right is None:
                scores.append(0.0)
                continue
            if left[0] == right[0]:
                scores.append(1.0)
                continue
            try:
                left_values = {
                    row[0]
                    for row in connection.execute(
                        f"SELECT DISTINCT {_quote(left[1])} "
                        f"FROM {_quote(left[0])} "
                        f"WHERE {_quote(left[1])} IS NOT NULL"
                    )
                }
                right_values = {
                    row[0]
                    for row in connection.execute(
                        f"SELECT DISTINCT {_quote(right[1])} "
                        f"FROM {_quote(right[0])} "
                        f"WHERE {_quote(right[1])} IS NOT NULL"
                    )
                }
            except sqlite3.Error:
                scores.append(0.0)
                continue
            if not left_values and not right_values:
                scores.append(0.5)
            elif not left_values or not right_values:
                scores.append(0.0)
            else:
                scores.append(
                    len(left_values & right_values)
                    / min(len(left_values), len(right_values))
                )
    return sum(scores) / len(scores) if scores else 1.0


def _failed_estimate(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    *,
    component: str,
) -> QualityEstimate:
    return QualityEstimate(
        query_id=requirement.query_id,
        config_id=config.config_id,
        precision_proxy=0.0,
        recall_proxy=0.0,
        validity=0.0,
        uncertainty=1.0,
        sample_size=0,
        components={component: 0.0},
    )


def assess_query_quality(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
    evidence_store: Optional[EvidenceStore],
    *,
    evidence_config_ids: Sequence[str] = (),
    max_rows: int = 100_000,
) -> QueryAssessment:
    """Return an auditable, gold-free assessment for one workload query."""
    try:
        sql = compile_typed_plan(requirement, config)
    except QueryCompilationError as exc:
        return QueryAssessment(
            estimate=_failed_estimate(
                requirement, config, component="plan_compiles"
            ),
            execution=None,
            sql=None,
            error=str(exc),
        )
    try:
        execution = execute_readonly(
            database_path, sql, max_rows=max_rows
        )
        repeated = execute_readonly(
            database_path,
            sql,
            max_rows=max_rows,
            reverse_unordered_selects=True,
        )
        wrapped = execute_readonly(
            database_path,
            f'SELECT * FROM ({sql.rstrip().rstrip(";")}) '
            'AS "__spp_metamorphic" WHERE 1 = 1',
            max_rows=max_rows,
        )
    except QueryExecutionError as exc:
        return QueryAssessment(
            estimate=_failed_estimate(
                requirement, config, component="query_executes"
            ),
            execution=None,
            sql=sql,
            error=str(exc),
        )

    stability = float(
        execution.value_digest == repeated.value_digest
        and not execution.truncated
        and not repeated.truncated
    )
    metamorphic = float(
        execution.value_digest == wrapped.value_digest
        and not wrapped.truncated
    )
    aggregate, grouping = _aggregate_grouping_signals(
        requirement, execution
    )
    aggregate_additivity = _aggregate_additivity(
        requirement,
        config,
        database_path,
        execution,
        max_rows=max_rows,
    )
    predicate_monotonicity = _predicate_monotonicity(
        requirement,
        config,
        database_path,
        execution,
        max_rows=max_rows,
    )
    join = _join_signal(requirement, config, database_path)
    try:
        relational = profile_relational_database(
            database_path, config.schema
        )
        relational_components = {
            "schema_validity": relational.schema_validity,
            "type_validity": relational.type_validity,
            "key_validity": relational.key_validity,
            "foreign_key_validity": relational.join_validity,
        }
    except (OSError, sqlite3.Error):
        relational_components = {
            "schema_validity": 0.0,
            "type_validity": 0.0,
            "key_validity": 0.0,
            "foreign_key_validity": 0.0,
        }
    evidence = compute_evidence_coverage(
        requirement,
        config,
        database_path,
        evidence_store,
        execution=execution,
        evidence_config_ids=evidence_config_ids,
    )
    provenance_bootstrap = _provenance_bootstrap_stability(
        requirement,
        config,
        evidence_store,
        evidence_config_ids,
    )
    precision = (
        0.75 * evidence.precision + 0.25 * evidence.output_support
        if execution.rows
        else evidence.precision
    )
    contract_coverage = (
        1.0
        if evidence.required_attributes == evidence.covered_attributes
        else 0.0
    )
    validity_components = {
        **relational_components,
        "required_attribute_coverage": contract_coverage,
        "query_executes": 1.0,
        "output_stability": stability,
        "metamorphic_consistency": metamorphic,
        "predicate_monotonicity": predicate_monotonicity,
        "aggregate_validity": aggregate,
        "aggregate_additivity": aggregate_additivity,
        "grouping_consistency": grouping,
        "join_signal": join,
        "provenance_bootstrap_stability": provenance_bootstrap,
    }
    validity_values = [_clamp(value) for value in validity_components.values()]
    validity = (
        math.prod(validity_values) ** (1.0 / len(validity_values))
        if validity_values and all(value > 0 for value in validity_values)
        else 0.0
    )
    finite_sample = (
        min(1.0, 0.5 / math.sqrt(evidence.sample_size))
        if evidence.sample_size
        else 1.0
    )
    signal_uncertainty = max(
        1.0 - stability,
        1.0 - metamorphic,
        1.0 - predicate_monotonicity,
        1.0 - aggregate,
        1.0 - aggregate_additivity,
        1.0 - grouping,
        1.0 - join,
        1.0 - provenance_bootstrap,
    )
    uncertainty = _clamp(max(finite_sample, signal_uncertainty))
    components = {
        **{key: float(value) for key, value in validity_components.items()},
        "aggregate_bounds": float(aggregate),
        "bootstrap_stability": float(provenance_bootstrap),
        "evidence_precision": evidence.precision,
        "evidence_recall": evidence.recall,
        "output_evidence_support": evidence.output_support,
        "supported_cells": float(evidence.supported_cells),
        "provenance_cells": float(evidence.provenance_cells),
        "materialized_required_cells": float(evidence.materialized_cells),
        "required_attributes": float(evidence.required_attributes),
        "covered_attributes": float(evidence.covered_attributes),
        "output_rows": float(execution.row_count),
        "output_truncated": float(execution.truncated),
    }
    estimate = QualityEstimate(
        query_id=requirement.query_id,
        config_id=config.config_id,
        precision_proxy=_clamp(precision),
        recall_proxy=evidence.recall,
        validity=_clamp(validity),
        uncertainty=uncertainty,
        sample_size=evidence.sample_size,
        components=components,
    )
    return QueryAssessment(
        estimate=estimate,
        execution=execution,
        sql=sql,
    )


def estimate_query_quality(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
    evidence_store: Optional[EvidenceStore],
    *,
    evidence_config_ids: Sequence[str] = (),
    max_rows: int = 100_000,
) -> QualityEstimate:
    return assess_query_quality(
        requirement,
        config,
        database_path,
        evidence_store,
        evidence_config_ids=evidence_config_ids,
        max_rows=max_rows,
    ).estimate


def assess_workload_quality(
    requirements: Sequence[QueryRequirement],
    config: SynthesisConfig,
    database_path: Path,
    evidence_store: Optional[EvidenceStore],
    *,
    evidence_config_ids: Sequence[str] = (),
    max_rows: int = 100_000,
) -> Dict[str, QueryAssessment]:
    return {
        requirement.query_id: assess_query_quality(
            requirement,
            config,
            database_path,
            evidence_store,
            evidence_config_ids=evidence_config_ids,
            max_rows=max_rows,
        )
        for requirement in requirements
        if config.schema.covers(requirement)
    }


def estimate_workload_quality(
    requirements: Sequence[QueryRequirement],
    config: SynthesisConfig,
    database_path: Path,
    evidence_store: Optional[EvidenceStore],
    *,
    evidence_config_ids: Sequence[str] = (),
    max_rows: int = 100_000,
) -> Dict[str, QualityEstimate]:
    return {
        query_id: assessment.estimate
        for query_id, assessment in assess_workload_quality(
            requirements,
            config,
            database_path,
            evidence_store,
            evidence_config_ids=evidence_config_ids,
            max_rows=max_rows,
        ).items()
    }


__all__ = [
    "EvidenceCoverage",
    "QueryAssessment",
    "QueryCompilationError",
    "QueryExecution",
    "QueryExecutionError",
    "assess_query_quality",
    "assess_workload_quality",
    "bootstrap_output_stability",
    "compile_typed_plan",
    "compile_typed_plans",
    "compute_evidence_coverage",
    "estimate_query_quality",
    "estimate_workload_quality",
    "execute_readonly",
    "execute_sqlite_readonly",
]

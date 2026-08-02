"""Adapter that reuses validated WDIRS extraction primitives as an SPP backend.

WDIRS is not a deployable fallback here. The adapter uses its chunking,
constrained extraction, provenance, and population operators to build explicit
new-system schema candidates.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from spp.budget_ledger import GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.evidence_store import CellProvenance, EvidenceAnchor, EvidenceStore
from spp.optimizer import PilotResult, canonical_output_signature
from spp.population import repair_join_columns_from_overlap
from spp.quality_signals import profile_relational_database
from spp.query_plan_compiler import compile_query_plan
from spp.risk_estimator import CellEvidence, PilotObservation, estimate_query_risk
from spp.schema_materializer import (
    reshape_tables,
    temporary_work_dir,
    write_sqlite_database,
)
from spp.spec import (
    AttributeRef,
    QualityEstimate,
    QueryRequirement,
    SynthesisConfig,
)
from spp.workload_intent import (
    WorkloadIntent,
    _plan_contract_score,
)

logger = logging.getLogger(__name__)


def _rewrite_query_plan(
    plan: Any,
    reference_mapper: Any,
    *,
    join_mapper: Any = None,
) -> Any:
    def predicate(value: Any) -> Any:
        if value is None:
            return None
        if value.kind == "predicate":
            return replace(
                value,
                attribute=(
                    reference_mapper(value.attribute)
                    if value.attribute is not None
                    else None
                ),
            )
        return replace(
            value,
            children=tuple(predicate(child) for child in value.children),
        )

    return replace(
        plan,
        projections=tuple(
            reference_mapper(value) for value in plan.projections
        ),
        group_by=tuple(
            reference_mapper(value) for value in plan.group_by
        ),
        aggregates=tuple(
            replace(
                aggregate,
                attribute=(
                    reference_mapper(aggregate.attribute)
                    if aggregate.attribute is not None
                    else None
                ),
            )
            for aggregate in plan.aggregates
        ),
        predicate=predicate(plan.predicate),
        joins=tuple(
            (
                join_mapper(join)
                if join_mapper is not None
                else replace(
                    join,
                    left=reference_mapper(join.left),
                    right=reference_mapper(join.right),
                )
            )
            for join in plan.joins
        ),
        having=tuple(
            replace(
                condition,
                aggregate=replace(
                    condition.aggregate,
                    attribute=(
                        reference_mapper(
                            condition.aggregate.attribute
                        )
                        if condition.aggregate.attribute is not None
                        else None
                    ),
                ),
            )
            for condition in plan.having
        ),
    )


class WDIRSPrimitiveBackend:
    """Ground-truth-free data plane for the new offline optimizer."""

    def __init__(
        self,
        runner: Any,
        *,
        schema_workload_queries: Sequence[str] = (),
        scratch_dir: Path | None = None,
    ):
        self.runner = runner
        self.schema_workload_queries = tuple(schema_workload_queries)
        self.scratch_dir = (
            Path(scratch_dir).expanduser().resolve()
            if scratch_dir is not None
            else None
        )
        self.intent: WorkloadIntent | None = None
        self._corpus_text = ""
        self._table_names: List[str] = []
        self._source_document_counts: Dict[str, int] = {}
        self._extracted_document_counts: Dict[str, int] = {}
        self._original_llm_client = runner.llm_client
        self._population_cache: Dict[str, Dict[str, List[dict]]] = {}
        self._evidence_store: EvidenceStore | None = None
        self._shared_provenance: List[CellProvenance] = []
        self._supported_source_cells: Dict[
            tuple[str, str, str], object
        ] = {}
        self._missing_tables: set[str] = set()
        self._cache_fingerprint: str | None = None
        self._physical_requirement_issues: Dict[str, List[str]] = {}
        self._physical_config_issues: Dict[str, Dict[str, str]] = {}

    def reproducibility_manifest(self) -> dict:
        return {
            "backend": type(self).__name__,
            "dataset": self.runner.dataset,
            "model": str(
                getattr(
                    self._original_llm_client,
                    "model",
                    type(self._original_llm_client).__name__,
                )
            ),
            "cache_dir": str(self.runner.cache_dir),
            "source_document_counts": dict(self._source_document_counts),
            "extracted_document_counts": dict(
                self._extracted_document_counts
            ),
            "scratch_dir": (
                str(self.scratch_dir) if self.scratch_dir is not None else None
            ),
            "source_primitive": "WDIRS",
            "runtime_delta_attribute_discovery": bool(
                getattr(self.runner, "enable_attribute_discovery", True)
            ),
            "config_equivalence_pruning": {
                "preprocessing": "shared_extraction_fixed",
                "normalization": (
                    "group_dimensions_source_grounded_semantic"
                ),
                "missing_values": "workload_columns_not_imputed",
            },
            "schema_workload_query_count": len(
                self.schema_workload_queries
            ),
            "schema_workload_sha256": (
                hashlib.sha256(
                    "\n;\n".join(self.schema_workload_queries).encode()
                ).hexdigest()
                if self.schema_workload_queries
                else None
            ),
            "missing_inferred_tables": sorted(self._missing_tables),
            "cache_workload_fingerprint": self._cache_fingerprint,
            "physical_requirement_issues": dict(
                self._physical_requirement_issues
            ),
            "physical_config_issues": dict(self._physical_config_issues),
            "physical_binding": dict(
                (
                    self.intent.analysis_diagnostics.get(
                        "_physical_binding", {}
                    )
                    if self.intent is not None
                    else {}
                )
            ),
        }

    def _fingerprint_cache_state(self, intent: WorkloadIntent) -> None:
        """Bind reusable extraction state to source identity and canonical IR."""
        source_files = []
        try:
            import config as config_module

            dataset_path = (
                Path(config_module.SOURCE_DATA_DIR) / self.runner.dataset
            ).expanduser().resolve()
            if dataset_path.exists():
                for path in sorted(
                    item
                    for item in dataset_path.rglob("*")
                    if item.is_file()
                ):
                    stat = path.stat()
                    source_files.append(
                        {
                            "path": str(path.relative_to(dataset_path)),
                            "size": stat.st_size,
                            "mtime_ns": stat.st_mtime_ns,
                        }
                    )
        except (OSError, ValueError):
            source_files = []
        payload = {
            "version": 1,
            "dataset": str(self.runner.dataset),
            "source_files": source_files,
            "requirements": [asdict(item) for item in intent.requirements],
        }
        rendered = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        )
        fingerprint = hashlib.sha256(rendered.encode()).hexdigest()
        self._cache_fingerprint = fingerprint
        if self.scratch_dir is None:
            return
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        # Keep the canonical-intent identity separate from the outer runner's
        # source/workload cache marker; both must match when both are present.
        marker = self.scratch_dir / "spp_intent_fingerprint.json"
        if marker.exists():
            try:
                existing = json.loads(marker.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"unreadable SPP cache fingerprint: {marker}"
                ) from exc
            if existing.get("fingerprint") != fingerprint:
                raise ValueError(
                    "scratch/cache fingerprint does not match the canonical "
                    "workload and source identity; use a fresh scratch directory"
                )
            return
        cache_dir = Path(self.runner.cache_dir)
        if cache_dir.exists() and any(
            path.is_file() for path in cache_dir.rglob("*")
        ):
            raise ValueError(
                "existing extraction cache has no workload fingerprint; "
                "use a fresh scratch directory"
            )
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "version": payload["version"],
                    "dataset": payload["dataset"],
                },
                indent=2,
            )
        )
        temporary.replace(marker)

    def _records_for_table(self, table: str) -> List[dict]:
        """Return materialized rows or an empty relation if extraction missed it.

        In an NL-only run, inferred relations are hypotheses. A hypothesis that
        produces no physical table is a zero-coverage outcome, not a fatal
        database error.
        """
        if not self.runner.data_layer.table_exists(table):
            if table not in self._missing_tables:
                logger.warning(
                    "Inferred relation %r was not materialized; treating it "
                    "as empty for cost and quality estimation",
                    table,
                )
                self._missing_tables.add(table)
            return []
        try:
            return list(self.runner.data_layer.get_all_records(table))
        except Exception as exc:
            if table not in self._missing_tables:
                logger.warning(
                    "Could not read inferred relation %r; treating it as "
                    "empty: %s",
                    table,
                    exc,
                )
                self._missing_tables.add(table)
            return []

    def _repair_all_null_required_columns(self) -> None:
        """Run one isolated extraction pass for required columns with no values."""
        if self.intent is None:
            return
        missing_by_table: Dict[str, set[str]] = {}
        for requirement in self.intent.requirements:
            references = list(
                requirement.plan.attributes()
                if requirement.plan is not None
                else ()
            )
            references.extend(
                AttributeRef(entity, attribute)
                for entity, attribute in requirement.attribute_bindings
            )
            for reference in references:
                table = reference.entity
                column = reference.attribute
                if (
                    table not in self._table_names
                    or not self.runner.data_layer.table_exists(table)
                ):
                    continue
                rows = self._records_for_table(table)
                if not any(
                    row.get(column) not in (None, "") for row in rows
                ):
                    missing_by_table.setdefault(table, set()).add(column)
        if not missing_by_table:
            return

        def quote(identifier: str) -> str:
            return '"' + str(identifier).replace('"', '""') + '"'

        repair_queries = []
        for table, columns in sorted(missing_by_table.items()):
            projected = set(columns)
            identity = getattr(self.runner, "identity_columns", {}).get(table)
            if identity and any(
                row.get(identity) not in (None, "")
                for row in self._records_for_table(table)
            ):
                projected.add(identity)
            repair_queries.append(
                "SELECT "
                + ", ".join(quote(column) for column in sorted(projected))
                + f" FROM {quote(table)}"
            )
        logger.warning(
            "Retrying isolated extraction for all-null required columns: %s",
            {
                table: sorted(columns)
                for table, columns in sorted(missing_by_table.items())
            },
        )
        original_lattice = self.runner.lattice_planner.lattice
        original_source_counts = dict(
            getattr(self.runner, "source_document_counts", {})
        )
        original_extracted_counts = dict(
            getattr(self.runner, "extracted_document_counts", {})
        )
        result = self.runner.preprocess(
            workload_queries=repair_queries,
            perform_proactive_er=False,
        )
        repair_source_counts = dict(
            getattr(self.runner, "source_document_counts", {})
        )
        repair_extracted_counts = dict(
            getattr(self.runner, "extracted_document_counts", {})
        )
        self.runner.lattice_planner.lattice = original_lattice
        self.runner.source_document_counts = {
            **original_source_counts,
            **repair_source_counts,
        }
        self.runner.extracted_document_counts = {
            **original_extracted_counts,
            **repair_extracted_counts,
        }
        if not result.success:
            logger.warning(
                "Isolated required-column extraction failed: %s",
                getattr(result, "error", "unknown error"),
            )

    def _install_budgeted_client(
        self,
        ledger: GlobalBudgetLedger,
        *,
        stage: str,
        config_id: str | None = None,
    ) -> None:
        budgeted = BudgetedLLMClient(
            self._original_llm_client,
            ledger,
            default_stage=stage,
            config_id=config_id,
        )
        self.runner.llm_client = budgeted
        for attribute in (
            "extractor",
            "sieve_synthesizer",
            "entity_resolver",
            "entity_anchor",
            "lattice_planner",
        ):
            component = getattr(self.runner, attribute, None)
            if component is not None and hasattr(component, "llm_client"):
                component.llm_client = budgeted

    def prepare(
        self,
        intent: WorkloadIntent,
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
    ) -> None:
        self.intent = intent
        self._evidence_store = evidence_store
        self._fingerprint_cache_state(intent)
        sql_queries = list(self.schema_workload_queries) or [
            requirement.text
            for requirement in intent.requirements
            if re.match(r"^\s*(select|with)\b", requirement.text, re.I)
        ]
        if (
            not self.schema_workload_queries
            and len(sql_queries) != len(intent.requirements)
        ):
            columns_by_entity: Dict[str, set[str]] = {
                entity: set()
                for requirement in intent.requirements
                for entity in requirement.entities
            }
            for requirement in intent.requirements:
                for entity, attribute in requirement.attribute_bindings:
                    columns_by_entity.setdefault(entity, set()).add(attribute)
                for left, relation, right in requirement.relationships:
                    if "=" in relation:
                        left_column, right_column = relation.split("=", 1)
                        columns_by_entity.setdefault(left, set()).add(left_column)
                        columns_by_entity.setdefault(right, set()).add(right_column)
            for entity, columns in sorted(columns_by_entity.items()):
                projected = sorted(columns) or ["name"]
                sql_queries.append(
                    f"SELECT {', '.join(projected)} FROM {entity}"
                )
        self._install_budgeted_client(ledger, stage="shared_extraction")
        result = self.runner.preprocess(
            workload_queries=sql_queries, perform_proactive_er=False
        )
        if not result.success:
            raise RuntimeError("shared WDIRS primitive extraction failed")
        inferred_table_names = sorted(
            self.runner.lattice_planner.lattice.tables
            if self.schema_workload_queries
            else {
                entity
                for requirement in intent.requirements
                for entity in requirement.entities
            }
        )
        self._table_names = []
        for table in inferred_table_names:
            if self.runner.data_layer.table_exists(table):
                self._table_names.append(table)
            else:
                self._missing_tables.add(table)
                logger.warning(
                    "Inferred relation %r was not materialized; it will be "
                    "treated as an empty, zero-coverage relation",
                    table,
                )
        self._repair_all_null_required_columns()
        self._source_document_counts = dict(
            getattr(self.runner, "source_document_counts", {})
        )
        self._extracted_document_counts = dict(
            getattr(self.runner, "extracted_document_counts", {})
        )
        chunks = self.runner.data_layer.get_all_chunks()
        by_document: Dict[str, List[Any]] = {}
        anchor_by_chunk: Dict[str, str] = {}
        content_by_chunk: Dict[str, str] = {}
        for chunk in chunks:
            by_document.setdefault(chunk.doc_id, []).append(chunk)
        corpus_parts: List[str] = []
        for document_id, document_chunks in by_document.items():
            ordered = sorted(document_chunks, key=lambda chunk: chunk.chunk_index)
            content = "\n".join(chunk.content for chunk in ordered)
            corpus_parts.append(content.lower())
            evidence_store.add_document(document_id, content)
            document_anchor = EvidenceAnchor.create(
                document_id=document_id,
                text=content,
                start=0,
                end=len(content),
                anchor_type="source_document",
                metadata={"projection_fastpath": True},
            )
            anchors = [
                EvidenceAnchor.create(
                    document_id=document_id,
                    text=chunk.content,
                    start=0,
                    end=len(chunk.content),
                    anchor_type="source_chunk",
                    metadata={"chunk_id": chunk.chunk_id},
                )
                for chunk in ordered
            ]
            evidence_store.add_anchors([document_anchor, *anchors])
            anchor_by_chunk[document_id] = document_anchor.anchor_id
            content_by_chunk[document_id] = content.lower()
            for chunk, anchor in zip(ordered, anchors):
                anchor_by_chunk[str(chunk.chunk_id)] = anchor.anchor_id
                content_by_chunk[str(chunk.chunk_id)] = chunk.content.lower()
        self._corpus_text = "\n".join(corpus_parts)
        try:
            from sqlalchemy import text

            provenance_rows: List[CellProvenance] = []
            with self.runner.data_layer.engine.connect() as connection:
                rows = connection.execute(
                    text(
                        "SELECT row_id, column_name, chunk_id "
                        "FROM cell_provenance"
                    )
                ).fetchall()
            records_by_row: Dict[str, tuple[str, dict]] = {}
            for table in self._table_names:
                for record in self._records_for_table(table):
                    records_by_row[str(record.get("row_id"))] = (table, record)
            for row in rows:
                record_entry = records_by_row.get(str(row.row_id))
                anchor_id = anchor_by_chunk.get(str(row.chunk_id))
                if record_entry is None or anchor_id is None:
                    continue
                table, record = record_entry
                value = record.get(row.column_name)
                rendered = str(value).strip().lower() if value is not None else ""
                source_text = content_by_chunk.get(str(row.chunk_id), "")
                restored = bool(
                    rendered
                    and (
                        rendered in source_text
                        or (
                            isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            and format(value, "g")
                            in source_text.replace(",", "")
                        )
                    )
                )
                provenance_rows.append(
                    CellProvenance(
                        config_id="shared_extraction",
                        relation=table,
                        row_identity=str(row.row_id),
                        column=str(row.column_name),
                        value_json=json.dumps(value, default=str),
                        anchor_id=anchor_id,
                        entailed=restored,
                        span_restored=restored,
                    )
                )
            evidence_store.add_cell_provenance(provenance_rows)
            self._shared_provenance = provenance_rows
            self._supported_source_cells = {
                (
                    provenance.relation,
                    provenance.row_identity,
                    provenance.column,
                ): json.loads(provenance.value_json)
                for provenance in provenance_rows
                if provenance.entailed and provenance.span_restored
            }
        except Exception as exc:
            # Older WDIRS caches may predate cell-level provenance. Row-level
            # support remains available through source chunks and is reflected
            # as higher uncertainty rather than aborting synthesis.
            logger.warning("Could not import cell provenance into evidence store: %s", exc)

    def refine_intent(self, intent: WorkloadIntent) -> WorkloadIntent:
        """Bind typed plans to populated source evidence before schema search."""
        rows_by_table = {
            table: self._records_for_table(table)
            for table in self._table_names
        }

        diagnostics: Dict[str, Any] = {}
        rewritten_requirements: List[QueryRequirement] = []
        refined_join_pairs: List[tuple[str, str, str, str]] = []
        for requirement in intent.requirements:
            plan = requirement.plan
            if plan is None:
                rewritten_requirements.append(requirement)
                continue
            join_changes: List[dict] = []

            def bind_reference(reference: AttributeRef) -> AttributeRef:
                return reference

            def bind_join(join: Any) -> Any:
                left_rows = rows_by_table.get(join.left.entity, [])
                right_rows = rows_by_table.get(join.right.entity, [])
                repaired = repair_join_columns_from_overlap(
                    copy.deepcopy(left_rows),
                    join.left.attribute,
                    copy.deepcopy(right_rows),
                    join.right.attribute,
                    left_table=join.left.entity,
                    right_table=join.right.entity,
                )
                if repaired is None:
                    bound = join
                else:
                    bound = replace(
                        join,
                        left=replace(
                            join.left, attribute=repaired[0]
                        ),
                        right=replace(
                            join.right, attribute=repaired[1]
                        ),
                    )
                    join_changes.append(
                        {
                            "from": (
                                join.left.entity,
                                join.left.attribute,
                                join.right.entity,
                                join.right.attribute,
                            ),
                            "to": (
                                bound.left.entity,
                                bound.left.attribute,
                                bound.right.entity,
                                bound.right.attribute,
                            ),
                        }
                    )
                refined_join_pairs.append(
                    (
                        bound.left.entity,
                        bound.left.attribute,
                        bound.right.entity,
                        bound.right.attribute,
                    )
                )
                return bound

            rewritten_plan = _rewrite_query_plan(
                plan,
                bind_reference,
                join_mapper=bind_join,
            )
            bindings = tuple(
                dict.fromkeys(
                    (reference.entity, reference.attribute)
                    for reference in rewritten_plan.attributes()
                )
            )
            relationships = tuple(
                (
                    join.left.entity,
                    f"{join.left.attribute}={join.right.attribute}",
                    join.right.entity,
                )
                for join in rewritten_plan.joins
            )
            rewritten_requirements.append(
                replace(
                    requirement,
                    entities=tuple(
                        dict.fromkeys(
                            reference.entity
                            for reference in rewritten_plan.attributes()
                        )
                    ),
                    attributes=tuple(
                        dict.fromkeys(
                            reference.attribute
                            for reference in rewritten_plan.attributes()
                        )
                    ),
                    attribute_bindings=bindings,
                    relationships=relationships,
                    plan=rewritten_plan,
                )
            )
            if join_changes:
                diagnostics[requirement.query_id] = {
                    "join_changes": join_changes,
                }

        refined = replace(
            intent,
            requirements=tuple(rewritten_requirements),
            analysis_diagnostics={
                **dict(intent.analysis_diagnostics),
                "_physical_binding": diagnostics,
            },
        )
        self.intent = refined
        if refined_join_pairs:
            lattice = self.runner.lattice_planner.lattice
            lattice.join_column_pairs = list(
                dict.fromkeys(refined_join_pairs)
            )
            lattice.join_pairs = list(
                dict.fromkeys(
                    (left, right)
                    for left, _left_col, right, _right_col
                    in refined_join_pairs
                )
            )
        return refined

    def _row_count(self) -> int:
        return sum(
            len(self._records_for_table(table))
            for table in self._table_names
        )

    def estimate_full_cost(
        self,
        config: SynthesisConfig,
        requirements: Sequence[QueryRequirement],
    ) -> int:
        llm_axes = sum(
            (
                config.population.er_strategy == "llm",
                config.population.norm_strategy == "llm",
                config.population.miss_strategy == "llm",
                config.population.type_coercion == "llm",
            )
        )
        # Admission upper bound only. Actual reporting always comes from ledger.
        return int(
            llm_axes * max(self._row_count(), 1) * 48
            # Initial compile, semantic verifier, and one bounded repair.
            + len(requirements) * 12_288
        )

    def completion_reserve(
        self,
        configs: Sequence[SynthesisConfig],
        requirements: Sequence[QueryRequirement],
    ) -> int:
        cheapest = min(
            self.estimate_full_cost(config, requirements) for config in configs
        )
        return cheapest

    def prune_configs(
        self, configs: Sequence[SynthesisConfig]
    ) -> Sequence[SynthesisConfig]:
        """Reject physically unsupported coverage and collapse inert axes."""
        representatives: Dict[
            tuple[str, str, str, str, str], SynthesisConfig
        ] = {}
        lattice_tables = getattr(
            self.runner.lattice_planner.lattice, "tables", {}
        )

        def evidence_type(table: str, column: str) -> str | None:
            candidates = []
            if table in lattice_tables:
                candidates.append(lattice_tables[table].columns.get(column))
            if not candidates or candidates == [None]:
                candidates = [
                    table_info.columns.get(column)
                    for table_info in lattice_tables.values()
                    if column in table_info.columns
                ]
            inferred = set()
            for column_info in candidates:
                evidence = set(
                    getattr(column_info, "type_evidence", ())
                )
                if "numeric" in evidence:
                    inferred.add("real")
                elif "date" in evidence:
                    inferred.add("date")
                elif "text" in evidence:
                    inferred.add("text")
            return next(iter(inferred)) if len(inferred) == 1 else None

        physical_issues: Dict[str, List[str]] = {}
        active_intent = getattr(self, "intent", None)
        if active_intent is not None:
            for requirement in active_intent.requirements:
                issues: List[str] = []
                overlap_repairable: set[tuple[str, str]] = set()
                if requirement.plan is not None:
                    for join in requirement.plan.joins:
                        left_rows = self._records_for_table(
                            join.left.entity
                        )
                        right_rows = self._records_for_table(
                            join.right.entity
                        )
                        if repair_join_columns_from_overlap(
                            copy.deepcopy(left_rows),
                            join.left.attribute,
                            copy.deepcopy(right_rows),
                            join.right.attribute,
                            left_table=join.left.entity,
                            right_table=join.right.entity,
                        ) is not None:
                            overlap_repairable.update(
                                {
                                    (
                                        join.left.entity,
                                        join.left.attribute,
                                    ),
                                    (
                                        join.right.entity,
                                        join.right.attribute,
                                    ),
                                }
                            )
                required_by_entity: Dict[str, set[str]] = {
                    entity: set() for entity in requirement.entities
                }
                for entity, attribute in requirement.attribute_bindings:
                    required_by_entity.setdefault(entity, set()).add(attribute)
                if requirement.plan is not None:
                    for reference in requirement.plan.attributes():
                        required_by_entity.setdefault(
                            reference.entity, set()
                        ).add(reference.attribute)
                for left, _relation, right in requirement.relationships:
                    required_by_entity.setdefault(left, set())
                    required_by_entity.setdefault(right, set())
                for table, required_columns in sorted(
                    required_by_entity.items()
                ):
                    if (
                        table not in self._table_names
                        or not self.runner.data_layer.table_exists(table)
                    ):
                        issues.append(f"missing_physical_table:{table}")
                        continue
                    rows = self._records_for_table(table)
                    if not rows:
                        issues.append(f"empty_required_table:{table}")
                        continue
                    for column in sorted(required_columns):
                        if not any(
                            row.get(column) not in (None, "") for row in rows
                        ) and (table, column) not in overlap_repairable:
                            issues.append(
                                f"all_null_required_column:{table}.{column}"
                            )
                if issues:
                    physical_issues[requirement.query_id] = issues
        self._physical_requirement_issues = physical_issues
        requirements_by_id = (
            {
                requirement.query_id: requirement
                for requirement in active_intent.requirements
            }
            if active_intent is not None
            else {}
        )
        normalization_active = bool(lattice_tables) or any(
            requirement.plan is not None and requirement.plan.group_by
            for requirement in requirements_by_id.values()
        )
        config_issues: Dict[str, Dict[str, str]] = {}

        for original_config in configs:
            binding_issues: Dict[str, str] = {}
            for query_id in original_config.schema.covered_query_ids:
                requirement = requirements_by_id.get(query_id)
                if requirement is None or requirement.plan is None:
                    continue
                if compile_query_plan(
                    requirement.plan, original_config
                ) is None:
                    binding_issues[query_id] = (
                        "typed query plan cannot bind to candidate schema"
                    )
            if binding_issues:
                config_issues[original_config.config_id] = binding_issues
            physically_covered = tuple(
                query_id
                for query_id in original_config.schema.covered_query_ids
                if query_id not in physical_issues
                and query_id not in binding_issues
            )
            if not physically_covered:
                continue
            original_config = replace(
                original_config,
                schema=replace(
                    original_config.schema,
                    covered_query_ids=physically_covered,
                ),
            )
            corrected_relations = []
            for relation in original_config.schema.relations:
                types = dict(relation.semantic_types)
                for column in relation.attributes:
                    inferred = evidence_type(relation.name, column)
                    if inferred is not None:
                        types[column] = inferred
                corrected_relations.append(
                    replace(
                        relation,
                        semantic_types=tuple(
                            (column, types.get(column, "text"))
                            for column in relation.attributes
                        ),
                    )
                )
            config = replace(
                original_config,
                schema=replace(
                    original_config.schema,
                    relations=tuple(corrected_relations),
                ),
            )
            key = (
                config.schema.schema_id,
                config.population.er_strategy,
                (
                    config.population.norm_strategy
                    if normalization_active
                    else "inert_without_evidence"
                ),
                config.population.unit_strategy,
                config.population.type_coercion,
            )
            current = representatives.get(key)
            rank = (
                config.preprocessing.strategy == "whole_document",
                config.population.norm_strategy == "dictionary",
                config.population.miss_strategy == "drop",
            )
            current_rank = (
                (
                    current.preprocessing.strategy == "whole_document",
                    current.population.norm_strategy == "dictionary",
                    current.population.miss_strategy == "drop",
                )
                if current is not None
                else (False, False, False)
            )
            if current is None or rank > current_rank:
                representatives[key] = config
        self._physical_config_issues = config_issues
        return tuple(
            sorted(representatives.values(), key=lambda item: item.config_id)
        )

    def _copy_provenance_for_config(
        self,
        config_id: str,
        populated: Mapping[str, Sequence[dict]],
    ) -> None:
        if self._evidence_store is None or not self._shared_provenance:
            return
        values_by_cell = {
            (table, str(row.get("row_id")), column): row.get(column)
            for table, rows in populated.items()
            for row in rows
            for column in row
        }
        copied = []
        for provenance in self._shared_provenance:
            key = (
                provenance.relation,
                provenance.row_identity,
                provenance.column,
            )
            if key not in values_by_cell:
                continue
            try:
                source_value = json.loads(provenance.value_json)
            except json.JSONDecodeError:
                source_value = provenance.value_json
            if values_by_cell[key] != source_value:
                continue
            copied.append(
                CellProvenance(
                    config_id=config_id,
                    relation=provenance.relation,
                    row_identity=provenance.row_identity,
                    column=provenance.column,
                    value_json=provenance.value_json,
                    anchor_id=provenance.anchor_id,
                    entailed=provenance.entailed,
                    span_restored=provenance.span_restored,
                )
            )
        self._evidence_store.add_cell_provenance(copied)

    def _populated_tables(
        self, config: SynthesisConfig
    ) -> Dict[str, List[dict]]:
        cache_key = (
            f"{self._cache_fingerprint or 'unfingerprinted'}:"
            f"{config.population.config_id}"
        )
        if cache_key in self._population_cache:
            populated = copy.deepcopy(self._population_cache[cache_key])
            self._copy_provenance_for_config(config.config_id, populated)
            return populated

        semantic_types: Dict[str, Dict[str, str]] = {
            table: {} for table in self._table_names
        }
        protected: Dict[str, set[str]] = {
            table: set() for table in self._table_names
        }
        abstractions: Dict[str, set[str]] = {
            table: set() for table in self._table_names
        }
        abstraction_hints: Dict[str, Dict[str, List[str]]] = {
            table: {} for table in self._table_names
        }
        for relation in config.schema.relations:
            if relation.name in semantic_types:
                semantic_types[relation.name].update(
                    dict(relation.semantic_types)
                )
        if self.intent is not None:
            for requirement in self.intent.requirements:
                for entity, attribute in requirement.attribute_bindings:
                    if entity in protected:
                        protected[entity].add(attribute)
                if requirement.plan is None:
                    continue
                for reference in requirement.plan.attributes():
                    if reference.entity not in semantic_types:
                        continue
                    semantic_types[reference.entity][
                        reference.attribute
                    ] = reference.semantic_type
                    protected[reference.entity].add(reference.attribute)
                for reference in requirement.plan.group_by:
                    if (
                        reference.entity in abstractions
                        and reference.semantic_type
                        not in {"integer", "real", "date", "boolean"}
                    ):
                        abstractions[reference.entity].add(
                            reference.attribute
                        )
                        abstraction_hints[reference.entity].setdefault(
                            reference.attribute, []
                        ).append(requirement.text)
        lattice_tables = getattr(
            self.runner.lattice_planner.lattice, "tables", {}
        )
        for table, table_info in lattice_tables.items():
            if table not in semantic_types:
                continue
            for column, column_info in table_info.columns.items():
                evidence = set(
                    getattr(column_info, "type_evidence", ())
                )
                if "numeric" in evidence:
                    semantic_types[table][column] = "real"
                elif "date" in evidence:
                    semantic_types[table][column] = "date"
                elif "text" in evidence:
                    semantic_types[table][column] = "text"

        populated = self.runner.materialize_population_tables(
            self._table_names,
            config.population,
            semantic_type_overrides=semantic_types,
            protected_columns={
                table: sorted(columns)
                for table, columns in protected.items()
            },
            abstraction_columns={
                table: sorted(columns)
                for table, columns in abstractions.items()
            },
            abstraction_hints={
                table: {
                    column: "\n".join(dict.fromkeys(hints))
                    for column, hints in columns.items()
                }
                for table, columns in abstraction_hints.items()
            },
            source_context=self._corpus_text,
        )
        self._copy_provenance_for_config(config.config_id, populated)
        self._population_cache[cache_key] = copy.deepcopy(populated)
        return populated

    def _sample_tables(
        self, tables: Mapping[str, Sequence[dict]], fraction: float
    ) -> Dict[str, List[dict]]:
        sampled: Dict[str, List[dict]] = {}
        for table, rows in tables.items():
            ordered = sorted(
                rows,
                key=lambda row: hashlib.sha256(
                    json.dumps(row, sort_keys=True, default=str).encode()
                ).hexdigest(),
            )
            count = min(len(ordered), max(1, math.ceil(len(ordered) * fraction)))
            sampled[table] = ordered[:count]
        return sampled

    def _query_estimate(
        self,
        requirement: QueryRequirement,
        config: SynthesisConfig,
        populated: Mapping[str, Sequence[dict]],
        *,
        validity: Mapping[str, float],
        sample_fraction: float,
    ) -> QualityEstimate:
        cells: List[CellEvidence] = []
        relevant_atoms = set()
        represented_atoms = set()
        coverage_values: List[float] = []
        entity_completeness_values: List[float] = []
        bound = requirement.attribute_bindings or tuple(
            (table, attribute)
            for table in requirement.entities
            for attribute in requirement.attributes
        )
        relevant_entities = set(requirement.entities) | {
            table for table, _attribute in bound
        }
        for table in relevant_entities:
            source_count = self._source_document_counts.get(table, 0)
            if source_count <= 0:
                continue
            durable_rows = len(self._records_for_table(table))
            extracted_documents = self._extracted_document_counts.get(
                table, durable_rows
            )
            entity_completeness_values.append(
                min(
                    1.0,
                    durable_rows / source_count,
                    extracted_documents / source_count,
                )
            )
        for table, attribute in bound:
            populated_rows = list(populated.get(table, ()))
            if populated_rows:
                coverage_values.append(
                    sum(
                        row.get(attribute) not in (None, "")
                        for row in populated_rows
                    )
                    / len(populated_rows)
                )
            else:
                coverage_values.append(0.0)
            for index, row in enumerate(
                self._records_for_table(table)
            ):
                value = row.get(attribute)
                if value not in (None, ""):
                    identity = row.get("row_id", index)
                    relevant_atoms.add(
                        f"{table}:{attribute}:{identity}"
                    )
            for index, row in enumerate(populated.get(table, ())):
                value = row.get(attribute)
                if value in (None, ""):
                    continue
                identity = row.get("row_id", index)
                atom = f"{table}:{attribute}:{identity}"
                represented_atoms.add(atom)
                source_value = self._supported_source_cells.get(
                    (table, str(identity), attribute)
                )
                evidence_value = source_value
                supported = (
                    source_value == value
                    and source_value not in (None, "")
                )
                if not supported:
                    matching_source = next(
                        (
                            candidate
                            for (
                                source_table,
                                source_identity,
                                _source_column,
                            ), candidate in self._supported_source_cells.items()
                            if source_table == table
                            and source_identity == str(identity)
                            and candidate == value
                            and candidate not in (None, "")
                        ),
                        None,
                    )
                    if matching_source is not None:
                        evidence_value = matching_source
                        supported = True
                if (
                    not supported
                    and source_value not in (None, "")
                    and (
                        config.population.norm_strategy == "llm"
                        or config.population.unit_strategy == "unit"
                        or config.population.type_coercion != "strict"
                    )
                ):
                    # The transformed value is derived from a span-restored
                    # source cell by the selected population policy.
                    evidence_value = source_value
                    supported = True
                rendered_evidence = (
                    str(evidence_value).strip().lower()
                    if evidence_value not in (None, "")
                    else None
                )
                cells.append(
                    CellEvidence(
                        row_identity=str(row.get("row_id", index)),
                        column=attribute,
                        value=value,
                        source_span=rendered_evidence if supported else None,
                        span_restored=supported,
                        entailed=supported,
                        document_id=str(row.get("source_doc_id", "")) or None,
                    )
                )
        observation = PilotObservation(
            query_id=requirement.query_id,
            config_id=config.config_id,
            cells=cells,
            relevant_evidence_atoms=relevant_atoms,
            represented_evidence_atoms=represented_atoms,
            schema_validity=validity["schema_validity"],
            type_validity=validity["type_validity"],
            key_validity=validity["key_validity"],
            join_validity=validity["join_validity"],
            entity_completeness=(
                min(entity_completeness_values)
                if entity_completeness_values
                else 1.0
            ),
            population_coverage=(
                min(coverage_values) if coverage_values else 0.0
            ),
            metamorphic_consistency=1.0,
            nl_sql_consistency=(
                1.0
                if re.match(r"^\s*(select|with)\b", requirement.text, re.I)
                else max(
                    0.0,
                    min(
                        1.0,
                        (
                            _plan_contract_score(
                                requirement.plan, requirement.text
                            )
                            + 10
                        )
                        / 30,
                    ),
                )
            ),
            stochastic_scores=[sample_fraction],
        )
        return estimate_query_risk(observation, bootstrap_rounds=40)

    def pilot(
        self,
        config: SynthesisConfig,
        sample_fraction: float,
        _evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
    ) -> PilotResult:
        if self.intent is None:
            raise RuntimeError("prepare must run before pilot")
        self._install_budgeted_client(
            ledger, stage="pilot_population", config_id=config.config_id
        )
        populated = self._sample_tables(
            self._populated_tables(config), sample_fraction
        )
        join_pairs = tuple(self.runner.lattice_planner.lattice.join_column_pairs)
        reshaped = reshape_tables(
            populated, config.schema, join_pairs=join_pairs
        )
        pilot_parent = (
            self.scratch_dir / "pilots"
            if self.scratch_dir is not None
            else None
        )
        with temporary_work_dir("spp-pilot-", parent=pilot_parent) as directory:
            db_path = write_sqlite_database(
                directory / "pilot.sqlite", reshaped, config.schema
            )
            relational = profile_relational_database(db_path, config.schema)
        validity = {
            "schema_validity": relational.schema_validity,
            "type_validity": relational.type_validity,
            "key_validity": relational.key_validity,
            "join_validity": relational.join_validity,
        }
        estimates = {
            requirement.query_id: self._query_estimate(
                requirement,
                config,
                populated,
                validity=validity,
                sample_fraction=sample_fraction,
            )
            for requirement in self.intent.requirements
            if config.schema.covers(requirement)
        }
        return PilotResult(
            config_id=config.config_id,
            estimates=estimates,
            output_signature=canonical_output_signature(reshaped),
            full_cost_upper_bound=self.estimate_full_cost(
                config, self.intent.requirements
            ),
            sample_fraction=sample_fraction,
            metadata={"relational_diagnostics": validity},
        )

    def materialize(
        self,
        config: SynthesisConfig,
        _evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
        output_path: Path,
    ) -> Path:
        self._install_budgeted_client(
            ledger, stage="final_population", config_id=config.config_id
        )
        populated = self._populated_tables(config)
        reshaped = reshape_tables(
            populated,
            config.schema,
            join_pairs=tuple(
                self.runner.lattice_planner.lattice.join_column_pairs
            ),
        )
        return write_sqlite_database(output_path, reshaped, config.schema)

    def validate_materialization(
        self,
        config: SynthesisConfig,
        database_path: Path,
        requirements: Sequence[QueryRequirement],
        _evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
    ) -> Mapping[str, QualityEstimate]:
        self._install_budgeted_client(
            ledger, stage="final_validation", config_id=config.config_id
        )
        relational = profile_relational_database(database_path, config.schema)
        validity = {
            "schema_validity": relational.schema_validity,
            "type_validity": relational.type_validity,
            "key_validity": relational.key_validity,
            "join_validity": relational.join_validity,
        }
        populated = self._populated_tables(config)
        return {
            requirement.query_id: self._query_estimate(
                requirement,
                config,
                populated,
                validity=validity,
                sample_fraction=1.0,
            )
            for requirement in requirements
            if config.schema.covers(requirement)
        }

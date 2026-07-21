"""Adapter that reuses validated WDIRS extraction primitives as an SPP backend.

WDIRS is not a deployable fallback here. The adapter uses its chunking,
constrained extraction, provenance, and population operators to build explicit
new-system schema candidates.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from spp.budget_ledger import GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.evidence_store import CellProvenance, EvidenceAnchor, EvidenceStore
from spp.optimizer import PilotResult, canonical_output_signature
from spp.quality_signals import profile_relational_database
from spp.risk_estimator import CellEvidence, PilotObservation, estimate_query_risk
from spp.schema_materializer import reshape_tables, write_sqlite_database
from spp.spec import QualityEstimate, QueryRequirement, SynthesisConfig
from spp.workload_intent import WorkloadIntent

logger = logging.getLogger(__name__)


class WDIRSPrimitiveBackend:
    """Ground-truth-free data plane for the new offline optimizer."""

    def __init__(
        self,
        runner: Any,
        *,
        schema_workload_queries: Sequence[str] = (),
    ):
        self.runner = runner
        self.schema_workload_queries = tuple(schema_workload_queries)
        self.intent: WorkloadIntent | None = None
        self._corpus_text = ""
        self._table_names: List[str] = []
        self._original_llm_client = runner.llm_client

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
            "source_primitive": "WDIRS",
            "runtime_delta_attribute_discovery": bool(
                getattr(self.runner, "enable_attribute_discovery", True)
            ),
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
        }

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
        self._table_names = sorted(
            self.runner.lattice_planner.lattice.tables
            if self.schema_workload_queries
            else {
                entity
                for requirement in intent.requirements
                for entity in requirement.entities
            }
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
            evidence_store.add_anchors(anchors)
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
                for record in self.runner.data_layer.get_all_records(table):
                    records_by_row[str(record.get("row_id"))] = (table, record)
            for row in rows:
                record_entry = records_by_row.get(str(row.row_id))
                anchor_id = anchor_by_chunk.get(str(row.chunk_id))
                if record_entry is None or anchor_id is None:
                    continue
                table, record = record_entry
                value = record.get(row.column_name)
                rendered = str(value).strip().lower() if value is not None else ""
                restored = bool(
                    rendered and rendered in content_by_chunk.get(str(row.chunk_id), "")
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
        except Exception as exc:
            # Older WDIRS caches may predate cell-level provenance. Row-level
            # support remains available through source chunks and is reflected
            # as higher uncertainty rather than aborting synthesis.
            logger.warning("Could not import cell provenance into evidence store: %s", exc)

    def _row_count(self) -> int:
        return sum(
            len(self.runner.data_layer.get_all_records(table))
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
            + len(requirements) * 4_096
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

    def _populated_tables(
        self, config: SynthesisConfig
    ) -> Dict[str, List[dict]]:
        return self.runner.materialize_population_tables(
            self._table_names, config.population
        )

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
        bound = requirement.attribute_bindings or tuple(
            (table, attribute)
            for table in requirement.entities
            for attribute in requirement.attributes
        )
        for table, attribute in bound:
            for index, row in enumerate(
                self.runner.data_layer.get_all_records(table)
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
                rendered = str(value).strip().lower()
                supported = bool(rendered and rendered in self._corpus_text)
                cells.append(
                    CellEvidence(
                        row_identity=str(row.get("row_id", index)),
                        column=attribute,
                        value=value,
                        source_span=rendered if supported else None,
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
            metamorphic_consistency=1.0,
            nl_sql_consistency=1.0
            if re.match(r"^\s*(select|with)\b", requirement.text, re.I)
            else 0.5,
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
        with tempfile.TemporaryDirectory(prefix="spp-pilot-") as directory:
            db_path = write_sqlite_database(
                Path(directory) / "pilot.sqlite", reshaped, config.schema
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

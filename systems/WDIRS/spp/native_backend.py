"""Native schema/preprocessing/population backend for the new SPP system."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from spp.budget_ledger import GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.evidence_store import CellProvenance, EvidenceAnchor, EvidenceStore
from spp.optimizer import PilotResult, canonical_output_signature
from spp.population import apply_population
from spp.quality_signals import profile_relational_database
from spp.risk_estimator import CellEvidence, PilotObservation, estimate_query_risk
from spp.schema_materializer import write_sqlite_database
from spp.spec import (
    PreprocessingPolicy,
    QualityEstimate,
    QueryRequirement,
    RelationSpec,
    SynthesisConfig,
)
from spp.workload_intent import WorkloadIntent
from token_counter import count_tokens


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    text: str
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class DocumentUnit:
    unit_id: str
    document_id: str
    text: str
    start: int
    end: int


def preprocess_documents(
    documents: Sequence[SourceDocument],
    policy: PreprocessingPolicy,
) -> List[DocumentUnit]:
    units: List[DocumentUnit] = []
    for document in documents:
        if policy.strategy == "whole_document":
            slices = [(0, len(document.text))]
        else:
            assert policy.chunk_size is not None
            step = policy.chunk_size - policy.chunk_overlap
            slices = [
                (start, min(start + policy.chunk_size, len(document.text)))
                for start in range(0, max(len(document.text), 1), step)
            ]
        for index, (start, end) in enumerate(slices):
            text = document.text[start:end]
            digest = hashlib.sha256(
                f"{policy.policy_id}\0{document.document_id}\0{index}\0{text}".encode()
            ).hexdigest()
            units.append(
                DocumentUnit(
                    unit_id=digest,
                    document_id=document.document_id,
                    text=text,
                    start=start,
                    end=end,
                )
            )
    return units


class NativeSPPBackend:
    """LLM-backed backend where every formal SPP axis changes execution."""

    def __init__(
        self,
        documents: Sequence[SourceDocument],
        llm_client: Any,
        *,
        max_extraction_tokens: int = 2_048,
    ):
        if not documents:
            raise ValueError("native SPP backend requires source documents")
        self.documents = tuple(documents)
        self.llm_client = llm_client
        self.max_extraction_tokens = int(max_extraction_tokens)
        self.intent: WorkloadIntent | None = None
        self._population_cache: Dict[str, Any] = {}
        self._extraction_cost_cache: Dict[Tuple[str, str], int] = {}
        self._final_estimates: Dict[
            str, Dict[str, QualityEstimate]
        ] = {}

    def reproducibility_manifest(self) -> dict:
        return {
            "backend": type(self).__name__,
            "model": str(
                getattr(self.llm_client, "model", type(self.llm_client).__name__)
            ),
            "max_extraction_tokens": self.max_extraction_tokens,
            "extraction_prompt_version": 1,
            "documents": [
                {
                    "document_id": document.document_id,
                    "sha256": hashlib.sha256(document.text.encode()).hexdigest(),
                    "metadata": dict(document.metadata),
                }
                for document in self.documents
            ],
        }

    def prepare(
        self,
        intent: WorkloadIntent,
        evidence_store: EvidenceStore,
        _ledger: GlobalBudgetLedger,
    ) -> None:
        self.intent = intent
        for document in self.documents:
            evidence_store.add_document(
                document.document_id,
                document.text,
                metadata=dict(document.metadata),
            )

    def _prompt(self, relation: RelationSpec, unit: DocumentUnit) -> str:
        return (
            "Extract zero or more rows for the requested relation from the source "
            "text. Do not infer unsupported values. Return only a JSON array of "
            "objects; use null for absent optional values.\n\n"
            f"Relation: {relation.name}\n"
            f"Columns: {json.dumps(list(relation.attributes))}\n"
            f"Primary key: {relation.primary_key}\n\n"
            f"Source text:\n{unit.text}"
        )

    def _estimated_unit_cost(
        self, relation: RelationSpec, unit: DocumentUnit
    ) -> int:
        prompt = self._prompt(relation, unit)
        conservative = (len(prompt.encode("utf-8")) + 1) // 2
        try:
            prompt_tokens = max(count_tokens(prompt), conservative)
        except RuntimeError:
            prompt_tokens = conservative
        # Include a worst-case syntax-repair call. Its prompt contains the
        # original completion, so budget for the initial output as repair input
        # as well as a replacement completion.
        return prompt_tokens + 3 * self.max_extraction_tokens + 512

    def estimate_full_cost(
        self,
        config: SynthesisConfig,
        requirements: Sequence[QueryRequirement],
    ) -> int:
        units = preprocess_documents(self.documents, config.preprocessing)
        cost_key = (config.schema.schema_id, config.preprocessing.policy_id)
        extraction = self._extraction_cost_cache.get(cost_key)
        if extraction is None:
            extraction = sum(
                self._estimated_unit_cost(relation, unit)
                for relation in config.schema.relations
                for unit in units
            )
            self._extraction_cost_cache[cost_key] = extraction
        population_llm_axes = sum(
            (
                config.population.er_strategy == "llm",
                config.population.norm_strategy == "llm",
                config.population.miss_strategy == "llm",
                config.population.type_coercion == "llm",
            )
        )
        population = population_llm_axes * max(len(units), 1) * 512
        # Reserve compile + semantic verification/repair for every query.
        return extraction + population + len(requirements) * 4_096

    def completion_reserve(
        self,
        configs: Sequence[SynthesisConfig],
        requirements: Sequence[QueryRequirement],
    ) -> int:
        return min(
            self.estimate_full_cost(config, requirements) for config in configs
        )

    @staticmethod
    def _extract_json_array(response: str) -> List[dict]:
        start, end = response.find("["), response.rfind("]")
        if start < 0 or end < start:
            raise ValueError("extraction response contains no JSON array")
        candidate = response[start : end + 1]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            # Repair JSON-invalid escapes and literal control characters
            # deterministically. Structural errors such as missing commas are
            # handled by the explicit, budgeted repair call below.
            repaired: List[str] = []
            in_string = False
            index = 0
            while index < len(candidate):
                character = candidate[index]
                preceding_backslashes = 0
                cursor = index - 1
                while cursor >= 0 and candidate[cursor] == "\\":
                    preceding_backslashes += 1
                    cursor -= 1
                if character == '"' and preceding_backslashes % 2 == 0:
                    in_string = not in_string
                    repaired.append(character)
                elif in_string and character == "\\":
                    following = (
                        candidate[index + 1]
                        if index + 1 < len(candidate)
                        else ""
                    )
                    if following not in '"\\/bfnrtu':
                        repaired.append("\\\\")
                    else:
                        repaired.append(character)
                elif in_string and character == "\n":
                    repaired.append("\\n")
                elif in_string and character == "\r":
                    repaired.append("\\r")
                elif in_string and character == "\t":
                    repaired.append("\\t")
                else:
                    repaired.append(character)
                index += 1
            try:
                payload = json.loads("".join(repaired))
            except json.JSONDecodeError as exc:
                raise ValueError("extraction response contains malformed JSON") from exc
        if not isinstance(payload, list):
            raise ValueError("extraction response must be a JSON list")
        return [row for row in payload if isinstance(row, dict)]

    def _extract_relation(
        self,
        config: SynthesisConfig,
        relation: RelationSpec,
        units: Sequence[DocumentUnit],
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
        *,
        stage: str,
    ) -> Tuple[List[dict], List[CellEvidence]]:
        budgeted = BudgetedLLMClient(
            self.llm_client,
            ledger,
            default_stage=stage,
            config_id=config.config_id,
        )
        records: List[dict] = []
        cells: List[CellEvidence] = []
        for unit in units:
            prompt = self._prompt(relation, unit)
            model_id = str(
                getattr(self.llm_client, "model", type(self.llm_client).__name__)
            )
            artifact_key = hashlib.sha256(
                f"extract\0{model_id}\0{relation}\0{unit.unit_id}\0{prompt}".encode()
            ).hexdigest()
            cached = evidence_store.get_shared_artifact(artifact_key)
            artifact_created = cached is None
            if cached is None:
                before = ledger.actual_spent
                response = budgeted.generate(
                    prompt,
                    max_tokens=self.max_extraction_tokens,
                    temperature=0.0,
                    operation="constrained_extraction",
                )
                try:
                    rows = self._extract_json_array(response)
                except ValueError:
                    repair_prompt = (
                        "Repair the JSON syntax in the extraction response below. "
                        "Do not add, remove, infer, or change any row or value. "
                        "Return only one valid JSON array of objects. The allowed "
                        f"object keys are {json.dumps(list(relation.attributes))}."
                        "\n\nMalformed extraction response:\n"
                        f"{response}"
                    )
                    repaired_response = budgeted.generate(
                        repair_prompt,
                        max_tokens=self.max_extraction_tokens,
                        temperature=0.0,
                        operation="repair_extraction_json",
                    )
                    try:
                        rows = self._extract_json_array(repaired_response)
                    except ValueError as repair_error:
                        digest = hashlib.sha256(response.encode()).hexdigest()[:16]
                        raise ValueError(
                            "extraction JSON remained malformed after one "
                            f"budgeted repair (response_sha256={digest})"
                        ) from repair_error
                produced_tokens = ledger.actual_spent - before
                evidence_store.put_shared_artifact(
                    artifact_key,
                    stage=stage,
                    payload=rows,
                    producer_tokens=produced_tokens,
                )
            else:
                rows = [dict(row) for row in cached]

            anchor = EvidenceAnchor.create(
                document_id=unit.document_id,
                text=unit.text,
                start=unit.start,
                end=unit.end,
                anchor_type="preprocessed_unit",
                metadata={
                    "unit_id": unit.unit_id,
                    "policy": config.preprocessing.policy_id,
                },
            )
            evidence_store.add_anchors([anchor])
            for local_index, raw_row in enumerate(rows):
                row = {
                    column: raw_row.get(column)
                    for column in relation.attributes
                }
                row_identity = str(
                    row.get(relation.primary_key)
                    if relation.primary_key
                    else f"{unit.unit_id}:{local_index}"
                )
                row["row_id"] = hashlib.sha256(
                    f"{relation.name}\0{row_identity}".encode()
                ).hexdigest()
                records.append(row)
                provenance_rows: List[CellProvenance] = []
                for column in relation.attributes:
                    value = row.get(column)
                    if value in (None, ""):
                        continue
                    rendered = str(value).strip()
                    restored = rendered.lower() in unit.text.lower()
                    cells.append(
                        CellEvidence(
                            row_identity=row["row_id"],
                            column=column,
                            value=value,
                            source_span=rendered if restored else None,
                            span_restored=restored,
                            entailed=restored,
                            document_id=unit.document_id,
                        )
                    )
                    provenance_rows.append(
                        CellProvenance(
                            config_id=config.config_id,
                            relation=relation.name,
                            row_identity=row["row_id"],
                            column=column,
                            value_json=json.dumps(value, default=str),
                            anchor_id=anchor.anchor_id,
                            entailed=restored,
                            span_restored=restored,
                        )
                    )
                if stage.startswith("final_"):
                    evidence_store.add_cell_provenance(provenance_rows)
                elif artifact_created:
                    evidence_store.add_cell_provenance(
                        [
                            CellProvenance(
                                config_id=f"shared:{artifact_key}",
                                relation=row.relation,
                                row_identity=row.row_identity,
                                column=row.column,
                                value_json=row.value_json,
                                anchor_id=row.anchor_id,
                                entailed=row.entailed,
                                span_restored=row.span_restored,
                            )
                            for row in provenance_rows
                        ]
                    )
        return records, cells

    def _materialize_records(
        self,
        config: SynthesisConfig,
        units: Sequence[DocumentUnit],
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
        *,
        stage: str,
    ) -> Tuple[Dict[str, List[dict]], Dict[str, List[CellEvidence]]]:
        tables: Dict[str, List[dict]] = {}
        cells_by_table: Dict[str, List[CellEvidence]] = {}
        population_client = BudgetedLLMClient(
            self.llm_client,
            ledger,
            default_stage=f"{stage}_population",
            config_id=config.config_id,
        )
        for relation in config.schema.relations:
            extracted, cells = self._extract_relation(
                config,
                relation,
                units,
                evidence_store,
                ledger,
                stage=stage,
            )
            numeric_columns: List[str] = []
            for column in relation.attributes:
                observed = [
                    row.get(column)
                    for row in extracted
                    if row.get(column) not in (None, "")
                ]
                numeric = 0
                for value in observed:
                    try:
                        float(str(value).replace(",", "").strip())
                        numeric += 1
                    except ValueError:
                        continue
                name_hint = any(
                    token in column.lower()
                    for token in (
                        "age", "year", "count", "amount", "price", "area",
                        "population", "gdp", "score", "number", "total",
                    )
                )
                if name_hint or (observed and numeric / len(observed) >= 0.5):
                    numeric_columns.append(column)
            semantic_types = {
                column: "QUANTITY" if column in numeric_columns else "OTHER"
                for column in relation.attributes
            }
            populated, _diagnostics = apply_population(
                extracted,
                config.population,
                table_name=relation.name,
                column_semantic_types=semantic_types,
                identity_columns=(
                    [relation.primary_key] if relation.primary_key else []
                ),
                numeric_columns=numeric_columns,
                llm_client=population_client,
                llm_cache=self._population_cache,
            )
            tables[relation.name] = populated
            cells_by_table[relation.name] = cells
        return tables, cells_by_table

    def _estimates(
        self,
        config: SynthesisConfig,
        requirements: Sequence[QueryRequirement],
        cells_by_table: Mapping[str, Sequence[CellEvidence]],
        relational: Any,
        *,
        documents: Sequence[SourceDocument],
    ) -> Dict[str, QualityEstimate]:
        estimates: Dict[str, QualityEstimate] = {}
        for requirement in requirements:
            relevant_columns = set(requirement.attributes)
            cells = [
                cell
                for table_cells in cells_by_table.values()
                for cell in table_cells
                if cell.column in relevant_columns
            ]
            represented = {
                f"{cell.document_id}:{cell.column}"
                for cell in cells
            }
            # Every sampled document/required column is a potential evidence
            # opportunity; failure to extract it lowers the coverage proxy.
            relevant = set(represented)
            for document in documents:
                for column in relevant_columns:
                    if column.lower() in document.text.lower():
                        relevant.add(f"{document.document_id}:{column}:mentioned")
            observation = PilotObservation(
                query_id=requirement.query_id,
                config_id=config.config_id,
                cells=list(cells),
                relevant_evidence_atoms=relevant,
                represented_evidence_atoms=represented,
                schema_validity=relational.schema_validity,
                type_validity=relational.type_validity,
                key_validity=relational.key_validity,
                join_validity=relational.join_validity,
                metamorphic_consistency=1.0,
                nl_sql_consistency=0.5
                if not re.match(r"^\s*(select|with)\b", requirement.text, re.I)
                else 1.0,
            )
            estimates[requirement.query_id] = estimate_query_risk(observation)
        return estimates

    def _run_materialization(
        self,
        config: SynthesisConfig,
        documents: Sequence[SourceDocument],
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
        database_path: Path,
        *,
        stage: str,
    ) -> Tuple[Dict[str, List[dict]], Dict[str, QualityEstimate]]:
        if self.intent is None:
            raise RuntimeError("prepare must run before materialization")
        units = preprocess_documents(documents, config.preprocessing)
        tables, cells = self._materialize_records(
            config, units, evidence_store, ledger, stage=stage
        )
        write_sqlite_database(database_path, tables, config.schema)
        relational = profile_relational_database(database_path, config.schema)
        estimates = self._estimates(
            config,
            self.intent.requirements,
            cells,
            relational,
            documents=documents,
        )
        return tables, estimates

    def pilot(
        self,
        config: SynthesisConfig,
        sample_fraction: float,
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
    ) -> PilotResult:
        count = min(
            len(self.documents),
            max(1, math.ceil(len(self.documents) * sample_fraction)),
        )
        sampled = sorted(
            self.documents,
            key=lambda document: hashlib.sha256(
                document.document_id.encode()
            ).hexdigest(),
        )[:count]
        with tempfile.TemporaryDirectory(prefix="native-spp-pilot-") as directory:
            tables, estimates = self._run_materialization(
                config,
                sampled,
                evidence_store,
                ledger,
                Path(directory) / "pilot.sqlite",
                stage="pilot_extraction",
            )
        return PilotResult(
            config_id=config.config_id,
            estimates=estimates,
            output_signature=canonical_output_signature(tables),
            full_cost_upper_bound=self.estimate_full_cost(
                config, self.intent.requirements if self.intent else ()
            ),
            sample_fraction=sample_fraction,
            metadata={
                "documents": count,
                "preprocessing_policy": config.preprocessing.policy_id,
            },
        )

    def materialize(
        self,
        config: SynthesisConfig,
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
        output_path: Path,
    ) -> Path:
        _tables, estimates = self._run_materialization(
            config,
            self.documents,
            evidence_store,
            ledger,
            output_path,
            stage="final_extraction",
        )
        self._final_estimates[config.config_id] = estimates
        return output_path

    def validate_materialization(
        self,
        config: SynthesisConfig,
        database_path: Path,
        requirements: Sequence[QueryRequirement],
        _evidence_store: EvidenceStore,
        _ledger: GlobalBudgetLedger,
    ) -> Mapping[str, QualityEstimate]:
        # Materialization already produced query-conditioned provenance
        # estimates. Validation confirms the DB is readable and immutable-safe.
        uri = f"file:{Path(database_path).resolve()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA integrity_check").fetchone()
        estimates = self._final_estimates.get(config.config_id)
        if estimates is None:
            raise RuntimeError("missing final materialization estimates")
        return {
            requirement.query_id: estimates[requirement.query_id]
            for requirement in requirements
            if requirement.query_id in estimates
        }

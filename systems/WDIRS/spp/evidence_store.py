"""Shared, configuration-independent evidence and provenance store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class EvidenceAnchor:
    anchor_id: str
    document_id: str
    text: str
    start: int
    end: int
    anchor_type: str
    metadata: dict

    @staticmethod
    def create(
        *,
        document_id: str,
        text: str,
        start: int,
        end: int,
        anchor_type: str,
        metadata: Optional[dict] = None,
    ) -> "EvidenceAnchor":
        payload = f"{document_id}\0{start}\0{end}\0{anchor_type}\0{text}"
        anchor_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return EvidenceAnchor(
            anchor_id=anchor_id,
            document_id=document_id,
            text=text,
            start=int(start),
            end=int(end),
            anchor_type=anchor_type,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class CellProvenance:
    config_id: str
    relation: str
    row_identity: str
    column: str
    value_json: str
    anchor_id: str
    entailed: bool
    span_restored: bool


@dataclass(frozen=True)
class ContractEvidence:
    """A raw, configuration-independent value admitted by a contract."""

    contract_id: str
    relation: str
    row_identity: str
    column: str
    raw_value_json: str
    raw_surface: str
    source_unit: Optional[str]
    anchor_id: str
    accepted: bool
    validation_status: str
    metadata: dict


@dataclass(frozen=True)
class ConflictRecord:
    """Competing source-backed values retained without silent resolution."""

    contract_id: str
    relation: str
    row_identity: str
    column: str
    values_json: str
    anchor_ids: Tuple[str, ...]
    resolution: Optional[str] = None


@dataclass(frozen=True)
class ValidationOutcome:
    """Auditable result of a hard contract check."""

    contract_id: str
    scope: str
    scope_key: str
    code: str
    passed: bool
    severity: str
    details: dict


@dataclass(frozen=True)
class DerivationLineage:
    """A reversible candidate-specific unit or taxonomy mapping."""

    config_id: str
    relation: str
    column: str
    source_value_json: str
    derived_value_json: str
    mapping_kind: str
    evidence_anchor_ids: Tuple[str, ...]


class EvidenceStore:
    """SQLite store shared by all candidate materializations in one run."""

    def __init__(self, path: Path, *, readonly: bool = False):
        self.path = Path(path).expanduser().resolve()
        self._lock = threading.RLock()
        if readonly:
            uri = f"file:{self.path}?mode=ro"
            self.conn = sqlite3.connect(
                uri, uri=True, check_same_thread=False
            )
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(
                self.path, check_same_thread=False
            )
            self._initialize()
        self.conn.row_factory = sqlite3.Row

    def _initialize(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                content_sha256 TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS anchors (
                anchor_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                text TEXT NOT NULL,
                start_offset INTEGER NOT NULL,
                end_offset INTEGER NOT NULL,
                anchor_type TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(document_id)
            );
            CREATE TABLE IF NOT EXISTS cell_provenance (
                config_id TEXT NOT NULL,
                relation_name TEXT NOT NULL,
                row_identity TEXT NOT NULL,
                column_name TEXT NOT NULL,
                value_json TEXT NOT NULL,
                anchor_id TEXT NOT NULL,
                entailed INTEGER NOT NULL,
                span_restored INTEGER NOT NULL,
                PRIMARY KEY (
                    config_id, relation_name, row_identity, column_name, anchor_id
                ),
                FOREIGN KEY(anchor_id) REFERENCES anchors(anchor_id)
            );
            CREATE TABLE IF NOT EXISTS shared_artifacts (
                artifact_key TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                producer_tokens INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS contract_evidence (
                contract_id TEXT NOT NULL,
                relation_name TEXT NOT NULL,
                row_identity TEXT NOT NULL,
                column_name TEXT NOT NULL,
                raw_value_json TEXT NOT NULL,
                raw_surface TEXT NOT NULL,
                source_unit TEXT,
                anchor_id TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                validation_status TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                PRIMARY KEY (
                    contract_id, relation_name, row_identity, column_name,
                    anchor_id, raw_value_json
                ),
                FOREIGN KEY(anchor_id) REFERENCES anchors(anchor_id)
            );
            CREATE TABLE IF NOT EXISTS conflict_sets (
                contract_id TEXT NOT NULL,
                relation_name TEXT NOT NULL,
                row_identity TEXT NOT NULL,
                column_name TEXT NOT NULL,
                values_json TEXT NOT NULL,
                anchor_ids_json TEXT NOT NULL,
                resolution TEXT,
                PRIMARY KEY (
                    contract_id, relation_name, row_identity, column_name
                )
            );
            CREATE TABLE IF NOT EXISTS validation_outcomes (
                contract_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                code TEXT NOT NULL,
                passed INTEGER NOT NULL,
                severity TEXT NOT NULL,
                details_json TEXT NOT NULL,
                PRIMARY KEY (contract_id, scope, scope_key, code)
            );
            CREATE TABLE IF NOT EXISTS derivation_lineage (
                config_id TEXT NOT NULL,
                relation_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                source_value_json TEXT NOT NULL,
                derived_value_json TEXT NOT NULL,
                mapping_kind TEXT NOT NULL,
                evidence_anchor_ids_json TEXT NOT NULL,
                PRIMARY KEY (
                    config_id, relation_name, column_name,
                    source_value_json, derived_value_json, mapping_kind
                )
            );
            CREATE TABLE IF NOT EXISTS count_memory_facts (
                fact_id TEXT PRIMARY KEY,
                memory_key TEXT NOT NULL,
                operation TEXT NOT NULL,
                fact_key TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                quantity_surface TEXT,
                unit TEXT,
                anchor_ids_json TEXT NOT NULL,
                conflicted INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS count_memory_scope_idx
                ON count_memory_facts(memory_key);
            """
        )
        self.conn.commit()

    def add_document(
        self, document_id: str, content: str, *, metadata: Optional[dict] = None
    ) -> None:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.conn.execute(
            "INSERT OR REPLACE INTO documents VALUES (?, ?, ?)",
            (document_id, digest, json.dumps(metadata or {}, sort_keys=True)),
        )
        self.conn.commit()

    def add_anchors(self, anchors: Iterable[EvidenceAnchor]) -> None:
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO anchors
            (anchor_id, document_id, text, start_offset, end_offset, anchor_type, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    anchor.anchor_id,
                    anchor.document_id,
                    anchor.text,
                    anchor.start,
                    anchor.end,
                    anchor.anchor_type,
                    json.dumps(anchor.metadata, sort_keys=True),
                )
                for anchor in anchors
            ],
        )
        self.conn.commit()

    def add_cell_provenance(self, rows: Iterable[CellProvenance]) -> None:
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO cell_provenance
            (config_id, relation_name, row_identity, column_name, value_json,
             anchor_id, entailed, span_restored)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.config_id,
                    row.relation,
                    row.row_identity,
                    row.column,
                    row.value_json,
                    row.anchor_id,
                    int(row.entailed),
                    int(row.span_restored),
                )
                for row in rows
            ],
        )
        self.conn.commit()

    def supported_cells(
        self, *, config_id: str, relation: Optional[str] = None
    ) -> List[CellProvenance]:
        sql = (
            "SELECT * FROM cell_provenance "
            "WHERE config_id = ? AND entailed = 1 AND span_restored = 1"
        )
        params: List[object] = [config_id]
        if relation:
            sql += " AND relation_name = ?"
            params.append(relation)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            CellProvenance(
                config_id=row["config_id"],
                relation=row["relation_name"],
                row_identity=row["row_identity"],
                column=row["column_name"],
                value_json=row["value_json"],
                anchor_id=row["anchor_id"],
                entailed=bool(row["entailed"]),
                span_restored=bool(row["span_restored"]),
            )
            for row in rows
        ]

    def add_contract_evidence(
        self, rows: Iterable[ContractEvidence]
    ) -> None:
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO contract_evidence
            (contract_id, relation_name, row_identity, column_name,
             raw_value_json, raw_surface, source_unit, anchor_id, accepted,
             validation_status, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.contract_id,
                    row.relation,
                    row.row_identity,
                    row.column,
                    row.raw_value_json,
                    row.raw_surface,
                    row.source_unit,
                    row.anchor_id,
                    int(row.accepted),
                    row.validation_status,
                    json.dumps(row.metadata, sort_keys=True),
                )
                for row in rows
            ],
        )
        self.conn.commit()

    def accepted_contract_evidence(
        self,
        *,
        contract_id: Optional[str] = None,
        relation: Optional[str] = None,
    ) -> List[ContractEvidence]:
        sql = "SELECT * FROM contract_evidence WHERE accepted = 1"
        params: List[object] = []
        if contract_id is not None:
            sql += " AND contract_id = ?"
            params.append(contract_id)
        if relation is not None:
            sql += " AND relation_name = ?"
            params.append(relation)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            ContractEvidence(
                contract_id=row["contract_id"],
                relation=row["relation_name"],
                row_identity=row["row_identity"],
                column=row["column_name"],
                raw_value_json=row["raw_value_json"],
                raw_surface=row["raw_surface"],
                source_unit=row["source_unit"],
                anchor_id=row["anchor_id"],
                accepted=bool(row["accepted"]),
                validation_status=row["validation_status"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def add_conflicts(self, rows: Iterable[ConflictRecord]) -> None:
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO conflict_sets
            (contract_id, relation_name, row_identity, column_name,
             values_json, anchor_ids_json, resolution)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.contract_id,
                    row.relation,
                    row.row_identity,
                    row.column,
                    row.values_json,
                    json.dumps(row.anchor_ids),
                    row.resolution,
                )
                for row in rows
            ],
        )
        self.conn.commit()

    def add_validation_outcomes(
        self, rows: Iterable[ValidationOutcome]
    ) -> None:
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO validation_outcomes
            (contract_id, scope, scope_key, code, passed, severity,
             details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.contract_id,
                    row.scope,
                    row.scope_key,
                    row.code,
                    int(row.passed),
                    row.severity,
                    json.dumps(row.details, sort_keys=True),
                )
                for row in rows
            ],
        )
        self.conn.commit()

    def add_derivation_lineage(
        self, rows: Iterable[DerivationLineage]
    ) -> None:
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO derivation_lineage
            (config_id, relation_name, column_name, source_value_json,
             derived_value_json, mapping_kind, evidence_anchor_ids_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.config_id,
                    row.relation,
                    row.column,
                    row.source_value_json,
                    row.derived_value_json,
                    row.mapping_kind,
                    json.dumps(row.evidence_anchor_ids),
                )
                for row in rows
            ],
        )
        self.conn.commit()

    def remember_count_fact(
        self,
        *,
        fact_id: str,
        memory_key: str,
        operation: str,
        fact_key: str,
        quantity: int,
        quantity_surface: Optional[str],
        unit: Optional[str],
        anchor_id: str,
    ) -> None:
        """Persist one idempotent count-memory operation and its evidence."""

        with self._lock:
            row = self.conn.execute(
                """
                SELECT quantity, quantity_surface, unit, anchor_ids_json,
                       conflicted
                FROM count_memory_facts
                WHERE fact_id = ?
                """,
                (fact_id,),
            ).fetchone()
            if row is None:
                self.conn.execute(
                    """
                    INSERT INTO count_memory_facts
                    (fact_id, memory_key, operation, fact_key, quantity,
                     quantity_surface, unit, anchor_ids_json, conflicted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        fact_id,
                        memory_key,
                        operation,
                        fact_key,
                        int(quantity),
                        quantity_surface,
                        unit,
                        json.dumps((anchor_id,)),
                    ),
                )
            else:
                anchors = list(json.loads(row["anchor_ids_json"]))
                if anchor_id not in anchors:
                    anchors.append(anchor_id)
                conflicted = bool(row["conflicted"]) or (
                    int(row["quantity"]) != int(quantity)
                    or row["unit"] != unit
                )
                self.conn.execute(
                    """
                    UPDATE count_memory_facts
                    SET anchor_ids_json = ?, conflicted = ?
                    WHERE fact_id = ?
                    """,
                    (
                        json.dumps(tuple(sorted(anchors))),
                        int(conflicted),
                        fact_id,
                    ),
                )
            self.conn.commit()

    def count_facts(self, *, memory_key: str) -> List[dict]:
        """Return deterministic count-memory state for one entity field."""

        with self._lock:
            rows = self.conn.execute(
                """
                SELECT fact_id, memory_key, operation, fact_key, quantity,
                       quantity_surface, unit, anchor_ids_json, conflicted
                FROM count_memory_facts
                WHERE memory_key = ?
                ORDER BY operation, fact_key, fact_id
                """,
                (memory_key,),
            ).fetchall()
        result = []
        for row in rows:
            anchor_ids = tuple(json.loads(row["anchor_ids_json"]))
            anchors = []
            for anchor_id in anchor_ids:
                anchor = self.conn.execute(
                    """
                    SELECT anchor_id, document_id, text, start_offset,
                           end_offset
                    FROM anchors
                    WHERE anchor_id = ?
                    """,
                    (anchor_id,),
                ).fetchone()
                if anchor is not None:
                    anchors.append(
                        {
                            "anchor_id": anchor["anchor_id"],
                            "document_id": anchor["document_id"],
                            "exact_span": anchor["text"],
                            "start": int(anchor["start_offset"]),
                            "end": int(anchor["end_offset"]),
                        }
                    )
            result.append(
                {
                    "fact_id": row["fact_id"],
                    "memory_key": row["memory_key"],
                    "operation": row["operation"],
                    "fact_key": row["fact_key"],
                    "quantity": int(row["quantity"]),
                    "quantity_surface": row["quantity_surface"],
                    "unit": row["unit"],
                    "anchor_ids": anchor_ids,
                    "evidence": tuple(anchors),
                    "conflicted": bool(row["conflicted"]),
                }
            )
        return result

    def put_shared_artifact(
        self, key: str, *, stage: str, payload: object, producer_tokens: int
    ) -> bool:
        with self._lock:
            cursor = self.conn.execute(
                "INSERT OR IGNORE INTO shared_artifacts VALUES (?, ?, ?, ?)",
                (
                    key,
                    stage,
                    json.dumps(payload, sort_keys=True),
                    int(producer_tokens),
                ),
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def get_shared_artifact(self, key: str) -> Optional[object]:
        with self._lock:
            row = self.conn.execute(
                "SELECT payload_json FROM shared_artifacts "
                "WHERE artifact_key = ?",
                (key,),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def manifest(self) -> dict:
        self.conn.commit()
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        counts = {}
        for table in (
            "documents",
            "anchors",
            "cell_provenance",
            "shared_artifacts",
            "contract_evidence",
            "conflict_sets",
            "validation_outcomes",
            "derivation_lineage",
            "count_memory_facts",
        ):
            counts[table] = self.conn.execute(
                f"SELECT COUNT(*) FROM {table}"  # table is fixed above
            ).fetchone()[0]
        return {
            "path": str(self.path),
            "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest()
            if self.path.exists()
            else None,
            "counts": counts,
        }

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "EvidenceStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

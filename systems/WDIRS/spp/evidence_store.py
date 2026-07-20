"""Shared, configuration-independent evidence and provenance store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


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


class EvidenceStore:
    """SQLite store shared by all candidate materializations in one run."""

    def __init__(self, path: Path, *, readonly: bool = False):
        self.path = Path(path).expanduser().resolve()
        if readonly:
            uri = f"file:{self.path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.path)
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

    def put_shared_artifact(
        self, key: str, *, stage: str, payload: object, producer_tokens: int
    ) -> bool:
        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO shared_artifacts VALUES (?, ?, ?, ?)",
            (key, stage, json.dumps(payload, sort_keys=True), int(producer_tokens)),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_shared_artifact(self, key: str) -> Optional[object]:
        row = self.conn.execute(
            "SELECT payload_json FROM shared_artifacts WHERE artifact_key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def manifest(self) -> dict:
        self.conn.commit()
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        counts = {}
        for table in ("documents", "anchors", "cell_provenance", "shared_artifacts"):
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

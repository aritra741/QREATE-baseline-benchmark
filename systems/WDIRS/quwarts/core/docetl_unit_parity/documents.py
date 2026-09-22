"""Derive the seven-document parity set from DocETL pipeline_output IDs only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pipeline_ids(path: Path) -> list[str]:
    """Read only ``doc_id``. Do not touch extracted values, text, or answers."""

    payload = json.loads(path.read_text())
    if not isinstance(payload, list) or not payload:
        raise SystemExit(f"{path}: pipeline_output is not a non-empty list")
    ids: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(payload):
        if not isinstance(row, dict) or "doc_id" not in row:
            raise SystemExit(f"{path}: row {index} missing doc_id")
        doc_id = str(row["doc_id"]).strip()
        if not doc_id:
            raise SystemExit(f"{path}: row {index} has empty doc_id")
        if doc_id in seen:
            raise SystemExit(f"{path}: duplicated doc_id {doc_id}")
        seen.add(doc_id)
        ids.append(doc_id)
    return ids


def load_parity_documents(
    pipeline_root: Path,
    source_dir: Path,
    query_ids: list[str],
) -> dict[str, Any]:
    artifacts = []
    per_query: dict[str, list[str]] = {}
    for query_id in query_ids:
        path = pipeline_root / query_id / "table_finance" / "pipeline_output.json"
        if not path.is_file():
            raise SystemExit(f"missing pipeline_output for {query_id}")
        ids = extract_pipeline_ids(path)
        per_query[query_id] = ids
        artifacts.append(str(path))

    ordered_sets = [tuple(sorted(ids, key=_id_sort)) for ids in per_query.values()]
    if len(set(ordered_sets)) != 1:
        raise SystemExit(f"DocETL pipeline_output ID sets differ: {per_query}")
    document_ids = list(ordered_sets[0])
    if len(document_ids) != 7:
        raise SystemExit(f"expected 7 unique document IDs, got {document_ids}")

    sources = {path.stem: path for path in sorted(source_dir.glob("*.txt"))}
    mapping: dict[str, str] = {}
    contents_hash = hashlib.sha256()
    source_hashes: dict[str, str] = {}
    for doc_id in document_ids:
        matches = [path for stem, path in sources.items() if stem == doc_id or path.name == doc_id]
        if not matches:
            raise SystemExit(f"document ID {doc_id} maps to no current source")
        if len(matches) != 1:
            raise SystemExit(f"document ID {doc_id} is ambiguous: {matches}")
        path = matches[0]
        if path.name in mapping.values():
            raise SystemExit(f"source {path.name} mapped from multiple IDs")
        mapping[doc_id] = path.name
        digest = _file_hash(path)
        source_hashes[doc_id] = digest
        contents_hash.update(doc_id.encode())
        contents_hash.update(path.read_bytes())

    payload = {
        "query_ids": list(query_ids),
        "document_ids": document_ids,
        "mapping": mapping,
        "source_hashes": source_hashes,
        "same_set_in_every_artifact": True,
        "n_artifacts": len(artifacts),
        "historical_ingest_reconstructed": False,
        "note": "IDs come from current DocETL pipeline_output artifacts; source text is the live Finance snapshot.",
        "hashes": {
            "ordered_query_ids": _hash(list(query_ids)),
            "ordered_document_ids": _hash(document_ids),
            "source_document_contents": contents_hash.hexdigest(),
            "id_to_document_mapping": _hash(mapping),
        },
    }
    payload["execution_parity_input_set_sha256"] = _hash(
        {
            "queries": payload["hashes"]["ordered_query_ids"],
            "documents": payload["hashes"]["ordered_document_ids"],
            "contents": payload["hashes"]["source_document_contents"],
            "mapping": payload["hashes"]["id_to_document_mapping"],
        }
    )
    return payload


def _id_sort(doc_id: str) -> tuple[int, str]:
    return (int(doc_id) if str(doc_id).isdigit() else 10**18, str(doc_id))

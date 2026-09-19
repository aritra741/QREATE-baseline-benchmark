"""Internal entity identity. Semantic attributes are never merge keys."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from quwarts.core.models import SourceDocument

PROVENANCE_COL = "__entity_id"
PROVENANCE_LABEL = "__provenance_label"
_COLLISIONS: list[dict[str, Any]] = []
_DROPPED: list[dict[str, Any]] = []


def document_stem(doc_id: str) -> str:
    name = Path(str(doc_id or "")).name
    return Path(name).stem if name else ""


def source_document_hash(doc_id: str, text: str = "") -> str:
    payload = f"{doc_id}\n{text or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def entity_id(corpus_id: str, document_hash: str, local_entity_index: int = 0) -> str:
    payload = f"{corpus_id}|{document_hash}|{int(local_entity_index)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clear_identity_audit() -> None:
    _COLLISIONS.clear()
    _DROPPED.clear()


def identity_collisions() -> list[dict[str, Any]]:
    return list(_COLLISIONS)


def dropped_rows() -> list[dict[str, Any]]:
    return list(_DROPPED)


def texts_by_stem(documents: Iterable[SourceDocument] | None) -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    for doc in documents or []:
        doc_id = str(getattr(doc, "doc_id", "") or "")
        text = str(getattr(doc, "text", "") or "")
        found[document_stem(doc_id) or doc_id] = (doc_id, text)
        found[doc_id] = (doc_id, text)
    return found


def stamp_row(
    row: dict[str, Any],
    *,
    corpus_id: str,
    documents: Iterable[SourceDocument] | None = None,
    local_entity_index: int = 0,
) -> dict[str, Any]:
    out = dict(row)
    doc_id = str(out.get("doc_id") or "")
    catalog = texts_by_stem(documents)
    stem = document_stem(doc_id) or doc_id
    source_id, text = catalog.get(doc_id) or catalog.get(stem) or (doc_id, "")
    digest = source_document_hash(source_id, text)
    out[PROVENANCE_COL] = entity_id(corpus_id, digest, local_entity_index)
    out[PROVENANCE_LABEL] = stem or source_id
    if not out.get("doc_id"):
        out["doc_id"] = source_id
    return out


def ensure_document_rows(
    rows: list[dict[str, Any]],
    documents: Iterable[SourceDocument],
    corpus_id: str,
) -> list[dict[str, Any]]:
    """One provenance row per source document, including all-NULL entities."""

    have = {document_stem(str(row.get("doc_id") or "")) for row in rows}
    have.discard("")
    out = list(rows)
    for doc in documents:
        stem = document_stem(doc.doc_id)
        if stem in have:
            continue
        out.append(
            stamp_row(
                {"doc_id": doc.doc_id},
                corpus_id=corpus_id,
                documents=documents,
            )
        )
        have.add(stem)
    return out


def dedup_provenance(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse only identical provenance keys. Log every collision."""

    clear_identity_audit()
    kept: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        key = str(row.get(PROVENANCE_COL) or "")
        if not key:
            _DROPPED.append({"reason": "missing_provenance", "doc_id": row.get("doc_id")})
            continue
        if key not in kept:
            kept[key] = dict(row)
            order.append(key)
            continue
        current = kept[key]
        _COLLISIONS.append(
            {
                "entity_id": key,
                "docs": [current.get("doc_id"), row.get("doc_id")],
                "reason": "identical_provenance",
            }
        )
        for field, value in row.items():
            if current.get(field) in (None, "") and value not in (None, ""):
                current[field] = value
    return [kept[key] for key in order]

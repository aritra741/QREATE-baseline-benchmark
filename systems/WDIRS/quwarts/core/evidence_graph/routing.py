"""Gold-free sample freeze, section index, and context packs."""

from __future__ import annotations

import hashlib
import random
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from quwarts.core.evidence_graph.config import (
    CALL1_ATTRIBUTES,
    CALL1_TERMS,
    CALL2_ATTRIBUTES,
    CALL2_TERMS,
    EFFECTIVE_INPUT_LIMIT,
    PACK_BUDGET,
    PLUMBING,
    SAFETY_MARGIN,
    SAMPLE_N,
    SEED,
    SOURCE,
    WRAPPER_RESERVE,
    COMPLETION_SPACE,
    load_attribute_descriptions,
    load_observables,
    sha256_text,
)
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.shared_bundle.context_blocks import pack_c1, parse_layout
from quwarts.experiments.extract_util import field_terms

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_CITATION = re.compile(r"\[[12]\d{3}\]\s+[A-Z]{2,}\s+\d+")
_ACT = re.compile(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+Act\s+\d{4}\b")
_JUDGE = re.compile(r"\b(?:Justice|Judge|[A-Z][a-z]+ J\.|[A-Z][a-z]+ JJ\.)\b")
_STATUS = re.compile(r"\b(?:company|organisation|organization|government|pty ltd|limited)\b", re.I)
_VERDICT = re.compile(r"\b(?:dismissed|approved|guilty|not guilty|orders that|I would dismiss)\b", re.I)
_TYPE = re.compile(r"\b(?:civil|criminal|commercial|administrative)\s+case\b", re.I)


def document_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def whole_document_budget() -> int:
    return EFFECTIVE_INPUT_LIMIT - COMPLETION_SPACE - SAFETY_MARGIN - WRAPPER_RESERVE


def load_entities() -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    try:
        rows = list(conn.execute('SELECT doc_id, "__entity_id" FROM legal ORDER BY doc_id'))
    finally:
        conn.close()
    items = []
    for doc_id, entity_id in rows:
        stem = str(doc_id).replace(".txt", "")
        path = SOURCE / f"{stem}.txt"
        if not path.exists():
            continue
        items.append({"entity_id": entity_id, "doc_id": str(doc_id), "stem": stem, "path": str(path)})
    if len(items) != 570:
        raise SystemExit(f"expected 570 legal documents, found {len(items)}")
    return items


def read_document(stem: str) -> str:
    return (SOURCE / f"{stem}.txt").read_text(encoding="utf-8", errors="replace")


def candidate_offsets(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for name, pattern in (
        ("year", _YEAR),
        ("citation", _CITATION),
        ("act", _ACT),
        ("judge", _JUDGE),
        ("status", _STATUS),
        ("verdict", _VERDICT),
        ("case_type", _TYPE),
    ):
        for match in pattern.finditer(text):
            hits.append({"kind": name, "start": match.start(), "end": match.end(), "value": match.group()})
    return hits


def layout_stats(doc_id: str, text: str) -> dict[str, Any]:
    blocks = parse_layout(doc_id, text)
    kinds: dict[str, int] = defaultdict(int)
    headings = []
    for block in blocks:
        kinds[block.kind] += 1
        if block.kind == "section_heading":
            headings.append(block.heading)
    return {
        "n_blocks": len(blocks),
        "n_headings": kinds.get("section_heading", 0),
        "n_paragraphs": kinds.get("paragraph", 0),
        "n_tables": sum(v for k, v in kinds.items() if k.startswith("table")),
        "n_lists": kinds.get("list", 0),
        "heading_preview": headings[:8],
        "kinds": dict(kinds),
    }


def retrieval_keys() -> dict[str, list[str]]:
    descriptions = load_attribute_descriptions()
    keys: dict[str, list[str]] = {name: list(field_terms(name)) for name in descriptions}
    for name, desc in descriptions.items():
        keys[name].extend(field_terms(desc))
        keys[name].extend(re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", desc))
    for item in load_observables():
        name = item["attribute"]
        keys.setdefault(name, [])
        keys[name].extend(field_terms(name))
        keys[name].extend(re.findall(r"'([^']+)'", item.get("expression") or ""))
        keys[name].extend(re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", item.get("expression") or ""))
    keys["__call1"] = list(CALL1_TERMS)
    keys["__call2"] = list(CALL2_TERMS)
    for name in keys:
        keys[name] = list(dict.fromkeys(part.lower() for part in keys[name] if part and len(str(part)) > 1))
    return keys


def pack_for_call(doc_id: str, text: str, call: str, keys: dict[str, list[str]]) -> dict[str, Any]:
    blocks = parse_layout(doc_id, text)
    if call == "call1":
        wanted = {name: keys.get(name, []) for name in CALL1_ATTRIBUTES}
        wanted["bundle"] = keys.get("__call1", [])
    else:
        wanted = {name: keys.get(name, []) for name in CALL2_ATTRIBUTES}
        wanted["bundle"] = keys.get("__call2", [])
    packed = pack_c1(blocks, wanted, PACK_BUDGET)
    selected_ids = {row["block_id"] for row in packed["blocks"]}
    dropped = [
        {"block_id": block.block_id, "kind": block.kind, "start": block.start, "end": block.end, "tokens": block.tokens}
        for block in blocks
        if block.block_id not in selected_ids
    ]
    rendered = render_pack(packed["blocks"])
    return {
        "call": call,
        "selected_sections": [
            {
                "block_id": row["block_id"],
                "kind": row["kind"],
                "heading": row.get("heading") or "",
                "start": row["start"],
                "end": row["end"],
                "tokens": row["tokens"],
            }
            for row in packed["blocks"]
        ],
        "dropped_sections": dropped,
        "coverage_tokens": packed["used_tokens"],
        "source_tokens": count_tokens(text),
        "rendered_text": rendered,
        "rendered_input_tokens": count_tokens(rendered),
        "kinds": packed.get("kinds") or {},
    }


def render_pack(blocks: list[dict[str, Any]]) -> str:
    parts = []
    for row in blocks:
        heading = row.get("heading") or ""
        parts.append(
            f"[section id={row['block_id']} kind={row['kind']} heading={heading} "
            f"source_start={row['start']} source_end={row['end']}]\n{row.get('text') or ''}"
        )
    return "\n\n".join(parts)


def route_document(doc_id: str, text: str, keys: dict[str, list[str]]) -> dict[str, Any]:
    tokens = count_tokens(text)
    mode = "whole_document" if tokens <= whole_document_budget() else "packed_sections"
    stats = layout_stats(doc_id, text)
    hits = candidate_offsets(text)
    if mode == "whole_document":
        call1 = {
            "call": "call1",
            "selected_sections": [{"block_id": f"{doc_id}:full", "kind": "document", "heading": "document", "start": 0, "end": len(text), "tokens": tokens}],
            "dropped_sections": [],
            "coverage_tokens": tokens,
            "source_tokens": tokens,
            "rendered_text": text,
            "rendered_input_tokens": tokens,
            "kinds": {"document": 1},
        }
        call2 = dict(call1)
        call2["call"] = "call2"
    else:
        call1 = pack_for_call(doc_id, text, "call1", keys)
        call2 = pack_for_call(doc_id, text, "call2", keys)
    return {
        "doc_id": doc_id,
        "mode": mode,
        "document_tokens": tokens,
        "document_chars": len(text),
        "document_hash": document_hash(text),
        "candidate_count": len(hits),
        "layout": stats,
        "call1": {k: v for k, v in call1.items() if k != "rendered_text"},
        "call2": {k: v for k, v in call2.items() if k != "rendered_text"},
        "call1_text": call1["rendered_text"],
        "call2_text": call2["rendered_text"],
        "has_route": True,
    }


def _tercile(values: list[int], value: int) -> str:
    ordered = sorted(values)
    if not ordered:
        return "medium"
    lo = ordered[len(ordered) // 3]
    hi = ordered[(2 * len(ordered)) // 3]
    if value <= lo:
        return "low"
    if value >= hi:
        return "high"
    return "medium"


def freeze_sample(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(records, key=lambda row: (row["document_tokens"], row["doc_id"]))
    longest = ordered[-1]
    quartiles: list[list[dict[str, Any]]] = [[], [], [], []]
    for index, row in enumerate(ordered):
        quartiles[min(3, index * 4 // len(ordered))].append(row)
    counts = [row["candidate_count"] for row in ordered]
    rng = random.Random(SEED)
    picked: list[dict[str, Any]] = []
    picked_ids: set[str] = set()

    def stratum(row: dict[str, Any]) -> tuple[str, str, str]:
        heading = "none" if row["layout"]["n_headings"] == 0 else ("few" if row["layout"]["n_headings"] <= 5 else "many")
        table = "low_table" if row["layout"]["n_tables"] <= 8 else "high_table"
        return (_tercile(counts, row["candidate_count"]), heading, table)

    for qi, bucket in enumerate(quartiles):
        need = 8
        if qi == 3 and longest["doc_id"] not in picked_ids:
            picked.append(longest)
            picked_ids.add(longest["doc_id"])
            need = 7
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in bucket:
            if row["doc_id"] in picked_ids:
                continue
            groups[stratum(row)].append(row)
        keys = list(groups)
        rng.shuffle(keys)
        for key in keys:
            rng.shuffle(groups[key])
        while need > 0:
            progressed = False
            for key in keys:
                if need <= 0:
                    break
                if groups[key]:
                    row = groups[key].pop()
                    picked.append(row)
                    picked_ids.add(row["doc_id"])
                    need -= 1
                    progressed = True
            if not progressed:
                break
        leftover = [row for row in bucket if row["doc_id"] not in picked_ids]
        rng.shuffle(leftover)
        while need > 0 and leftover:
            row = leftover.pop()
            picked.append(row)
            picked_ids.add(row["doc_id"])
            need -= 1

    if longest["doc_id"] not in picked_ids:
        picked.append(longest)
    picked = sorted(picked, key=lambda row: (row["document_tokens"], row["doc_id"]))
    if len(picked) != SAMPLE_N:
        raise SystemExit(f"sample freeze produced {len(picked)} documents")
    return picked


def routing_rules() -> dict[str, Any]:
    return {
        "effective_input_limit": EFFECTIVE_INPUT_LIMIT,
        "completion_space": COMPLETION_SPACE,
        "safety_margin": SAFETY_MARGIN,
        "wrapper_reserve": WRAPPER_RESERVE,
        "pack_budget": PACK_BUDGET,
        "whole_document_budget": whole_document_budget(),
        "fit_rule": "document_tokens <= whole_document_budget -> complete document in calls 1 and 2",
        "overflow_rule": "deterministic section index + BM25 packs; absence from a pack stays unresolved",
        "call3_rule": "compact facts only, never the document",
        "call4_rule": "local windows of conflicting nodes only",
    }


def index_fingerprint(keys: dict[str, list[str]]) -> str:
    return sha256_text(json_ready(routing_rules()) + json_ready(keys))


def json_ready(payload: Any) -> str:
    import json

    return json.dumps(payload, sort_keys=True, default=str)

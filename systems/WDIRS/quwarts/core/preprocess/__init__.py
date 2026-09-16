"""Preprocessing policies and document segmentation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from quwarts.core.models import PreprocessPolicy, SourceDocument


@dataclass(frozen=True)
class Segment:
    segment_id: str
    doc_id: str
    text: str
    start: int
    end: int


def default_policies() -> list[PreprocessPolicy]:
    return [
        PreprocessPolicy(mode="whole_document"),
        PreprocessPolicy(mode="fixed_chunk", chunk_tokens=128, overlap_tokens=16),
    ]


def segment_documents(documents: list[SourceDocument], policy: PreprocessPolicy) -> list[Segment]:
    if policy.mode == "whole_document":
        return [
            Segment(
                segment_id=_sid(doc.doc_id, 0, len(doc.text), policy),
                doc_id=doc.doc_id,
                text=doc.text,
                start=0,
                end=len(doc.text),
            )
            for doc in documents
        ]
    width = max(int((policy.chunk_tokens or 128) * 4), 32)
    overlap = int((policy.overlap_tokens or 0) * 4)
    segments: list[Segment] = []
    for doc in documents:
        start = 0
        index = 0
        while start < len(doc.text):
            end = min(len(doc.text), start + width)
            segments.append(
                Segment(
                    segment_id=_sid(doc.doc_id, start, end, policy),
                    doc_id=doc.doc_id,
                    text=doc.text[start:end],
                    start=start,
                    end=end,
                )
            )
            if end == len(doc.text):
                break
            start = max(end - overlap, start + 1)
            index += 1
    return segments


def policy_hash(policy: PreprocessPolicy) -> str:
    return hashlib.sha256(
        f"{policy.mode}|{policy.chunk_tokens}|{policy.overlap_tokens}".encode()
    ).hexdigest()[:12]


def _sid(doc_id: str, start: int, end: int, policy: PreprocessPolicy) -> str:
    return hashlib.sha256(
        f"{doc_id}|{start}|{end}|{policy_hash(policy)}".encode()
    ).hexdigest()[:16]

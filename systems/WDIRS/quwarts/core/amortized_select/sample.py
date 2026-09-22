"""Deterministic diversity sampling of unlabeled candidate sets."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _bucket(row: dict[str, Any], feats: list[dict[str, Any]]) -> frozenset[str]:
    n = len(feats)
    if n <= 1:
        size = "n1"
    elif n <= 4:
        size = "n2_4"
    else:
        size = "n5_8"
    sources = {item["source_type"] for item in feats} or {"empty"}
    if sources <= {"table"}:
        src = "table"
    elif sources.isdisjoint({"table"}):
        src = "prose"
    else:
        src = "mixed"
    periods = tuple(sorted({item["period"] for item in feats if item.get("period")}) or {"none"})
    units = tuple(sorted({item["unit"] for item in feats if item.get("unit")}) or {"none"})
    shapes = tuple(sorted({item["value_shape"] for item in feats}) or {"none"})
    headings = tuple(sorted({(item["row_label"] or "")[:24] for item in feats[:3]}))
    pos = tuple(sorted({item["document_position"] for item in feats}) or {"unknown"})
    return frozenset(
        {
            f"size:{size}",
            f"src:{src}",
            *[f"p:{item}" for item in periods],
            *[f"u:{item}" for item in units],
            *[f"s:{item}" for item in shapes],
            *[f"h:{item}" for item in headings],
            *[f"pos:{item}" for item in pos],
        }
    )


def sample_attribute(
    rows: list[dict[str, Any]],
    feats_by_key: dict[tuple[str, str], list[dict[str, Any]]],
    k: int,
) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: (row["entity_id"], row["document_id"]))
    if not ranked:
        return []
    chosen: list[dict[str, Any]] = []
    covered: set[str] = set()
    first = ranked[0]
    chosen.append(first)
    covered.update(_bucket(first, feats_by_key.get((first["entity_id"], first["attribute"]), [])))
    while len(chosen) < min(k, len(ranked)):
        best = None
        for row in ranked:
            if row in chosen:
                continue
            bucket = _bucket(row, feats_by_key.get((row["entity_id"], row["attribute"]), []))
            gain = len(bucket - covered)
            cand = (-gain, row["entity_id"], row["document_id"])
            if best is None or cand < best[0]:
                best = (cand, row, bucket)
        if best is None:
            break
        _cand, row, bucket = best
        if _cand[0] == 0 and len(chosen) >= 1:
            # still fill remaining slots deterministically
            for extra in ranked:
                if extra not in chosen:
                    chosen.append(extra)
                    if len(chosen) >= k:
                        break
            break
        chosen.append(row)
        covered.update(bucket)
    return chosen[:k]


def samples_hash(samples: dict[str, list[dict[str, Any]]]) -> str:
    payload = {
        name: [{"entity_id": row["entity_id"], "document_id": row["document_id"], "attribute": row["attribute"]} for row in rows]
        for name, rows in sorted(samples.items())
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

"""Deterministic join blocking. Cartesian products are never sent to the model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlglot import exp

from quwarts.core.query_witness import JoinSpec, WitnessSpec
from quwarts.core.workload import parse_sql

PER_LEFT_CAP = 8
PER_QUERY_CAP = 48
_SPLIT = re.compile(r"\|\||\||,|;")


@dataclass
class BlockStats:
    query_id: str
    cartesian: int
    blocked: int
    skip_reason: str = ""
    per_left_cap: int = PER_LEFT_CAP
    per_query_cap: int = PER_QUERY_CAP
    signal: str = ""


@dataclass
class CandidateSet:
    rows: list[dict[str, Any]] = field(default_factory=list)
    stats: BlockStats | None = None


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _tokens(value: Any) -> list[str]:
    text = _norm(value)
    if not text:
        return []
    parts = [part.strip() for part in _SPLIT.split(text) if part.strip()]
    if text not in parts:
        parts.append(text)
    return list(dict.fromkeys(parts))


def _cell(row: dict[str, Any], column: str) -> Any:
    cells = row.get("cells") or {}
    if column in cells:
        return cells.get(column)
    for key, value in cells.items():
        if str(key).split(".")[-1].lower() == column:
            return value
    return None


def join_field_refs(join: JoinSpec) -> tuple[list[str], list[str], set[str]]:
    try:
        tree = parse_sql(join.on_sql)
    except Exception:
        return [], [], set()
    left_alias = join.left_alias.lower()
    right_alias = join.right_alias.lower()
    left_cols: list[str] = []
    right_cols: list[str] = []
    signals: set[str] = set()
    for col in tree.find_all(exp.Column):
        raw = (col.table or "").lower()
        name = (col.name or "").lower()
        if not name:
            continue
        if raw == left_alias or raw == join.left_table:
            left_cols.append(name)
        elif raw == right_alias or raw == join.right_table:
            right_cols.append(name)
    if tree.find(exp.EQ):
        signals.add("exact")
    if tree.find(exp.Like) or "||" in join.on_sql.lower() or " like " in f" {join.on_sql.lower()} ":
        signals.add("token")
    if tree.find(exp.Lower) or tree.find(exp.Trim) or tree.find(exp.Replace):
        signals.add("transform")
    return list(dict.fromkeys(left_cols)), list(dict.fromkeys(right_cols)), signals


def _row_keys(row: dict[str, Any], columns: Iterable[str]) -> list[str]:
    keys: list[str] = []
    for column in columns:
        value = _cell(row, column)
        if value in (None, ""):
            continue
        keys.extend(_tokens(value))
    return list(dict.fromkeys(keys))


def _retrieval_keys(row: dict[str, Any]) -> list[str]:
    blob = " ".join(
        [
            str(row.get("label") or ""),
            str(row.get("document") or ""),
            " ".join(str(value) for value in (row.get("cells") or {}).values() if value not in (None, "")),
        ]
    )
    return [tok for tok in _tokens(blob) if len(tok) > 2][:24]


def _index_rows(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for key in _row_keys(row, columns):
            index.setdefault(key, []).append(row)
    return index


def block_join_pairs(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    join: JoinSpec,
    *,
    per_left: int = PER_LEFT_CAP,
    per_query: int = PER_QUERY_CAP,
) -> tuple[list[tuple[dict[str, Any], dict[str, Any], str]], str, str]:
    left_cols, right_cols, signals = join_field_refs(join)
    if not left_cols or not right_cols or not signals:
        return [], "no useful blocking signal", ""
    index = _index_rows(right_rows, right_cols)
    if not index:
        return [], "no useful blocking signal", "empty_right_index"
    paired: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    seen: set[tuple[int, int]] = set()
    signal = "+".join(sorted(signals))
    for left in left_rows:
        if len(paired) >= per_query:
            break
        keys = _row_keys(left, left_cols)
        source = "index"
        if not keys:
            keys = _retrieval_keys(left)
            source = "retrieval"
            if not keys:
                continue
        ranked: dict[int, tuple[int, dict[str, Any]]] = {}
        for key in keys:
            for right in index.get(key, []):
                rid = int(right["rowid"])
                if rid == int(left["rowid"]) and left.get("table") == right.get("table"):
                    continue
                prev = ranked.get(rid)
                score = (prev[0] + 1) if prev else 1
                ranked[rid] = (score, right)
        chosen = sorted(ranked.values(), key=lambda item: (-item[0], item[1]["rowid"]))[:per_left]
        for _score, right in chosen:
            pair = (int(left["rowid"]), int(right["rowid"]))
            if pair in seen:
                continue
            seen.add(pair)
            paired.append((left, right, source))
            if len(paired) >= per_query:
                break
    if not paired:
        return [], "no useful blocking signal", signal
    return paired, "", signal


def pair_candidate(
    spec: WitnessSpec,
    join: JoinSpec,
    left: dict[str, Any],
    right: dict[str, Any],
    kept: set[Any],
    incumbent_primary: set[int],
) -> dict[str, Any] | None:
    from quwarts.core.query_witness import make_witness_key, occupancy_key

    rowids = {join.left_table: left["rowid"], join.right_table: right["rowid"]}
    primary = left if spec.primary == join.left_table else right
    other = right if primary is left else left
    if occupancy_key(rowids, primary.get("entity_id")) in kept:
        return None
    key = make_witness_key(spec, rowids, distinct_value=primary.get("entity_id"), group_key={})
    cells = dict(primary.get("cells") or {})
    cells.update({f"{other.get('table')}.{k}": v for k, v in (other.get("cells") or {}).items()})
    return {
        "witness_id": f"{primary['entity_id']}|{other['entity_id']}|{left['rowid']}|{right['rowid']}",
        "witness_key": key,
        "entity_id": primary["entity_id"],
        "rowid": primary["rowid"],
        "rowids": rowids,
        "label": f"{primary.get('label') or ''} / {other.get('label') or ''}",
        "table": spec.primary,
        "cells": cells,
        "document": (primary.get("document") or "") + "\n" + (other.get("document") or ""),
        "priority": 0 if primary["rowid"] not in incumbent_primary else 1,
    }

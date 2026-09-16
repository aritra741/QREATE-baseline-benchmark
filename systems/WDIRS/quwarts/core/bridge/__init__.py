"""Equijoin bridges: linkage without mutating either surface column."""

from __future__ import annotations

import json
import sqlite3
from typing import Iterable

from quwarts.core.domain import _atomic, _surfaces
from quwarts.core.extract import _parse_llm_object
from quwarts.core.models import EvidenceRecord, Workload

KEEP_RELATIONS = frozenset({"rename", "alias", "abbreviation", "historical_name"})


def bridge_table_name(left: str, right: str) -> str:
    return f"bridge_{left.replace('.', '_')}__{right.replace('.', '_')}"


def pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def build_bridges(
    pairs: list[tuple[str, str]],
    records: list[EvidenceRecord],
    workload: Workload,
    caller=None,
    linkage: dict[str, str] | None = None,
    documents=None,
) -> dict[tuple[str, str], list[dict[str, str]]]:
    """One bridge per equijoin pair. Corroboration is not applied."""

    surfaces = _surfaces(records)
    aliases = dict(workload.literal_aliases)
    aliases.update(linkage or {})
    texts = None
    if documents is not None:
        texts = [str(getattr(doc, "text", "") or "").lower() for doc in documents]
    built: dict[tuple[str, str], list[dict[str, str]]] = {}
    for left, right in pairs:
        key = (left, right)
        if key in built or (right, left) in built:
            continue
        left_vals = set(surfaces.get(left) or surfaces.get(left.split(".")[-1]) or ())
        right_vals = set(surfaces.get(right) or surfaces.get(right.split(".")[-1]) or ())
        if not left_vals or not right_vals:
            continue
        rows = _exact_rows(left_vals, right_vals)
        matched = {(row["left_value"].lower(), row["right_value"].lower()) for row in rows}
        rows.extend(_alias_rows(left_vals, right_vals, aliases, matched))
        matched = {(row["left_value"].lower(), row["right_value"].lower()) for row in rows}
        covered_left = {row["left_value"].lower() for row in rows}
        unknown = [
            value
            for value in sorted(_atomic(left_vals))
            if value.lower() not in covered_left
        ]
        targets = sorted(_atomic(right_vals) or right_vals)
        if unknown and targets and caller is not None:
            mapped = _typed_links(unknown, targets, caller, left, right)
            for source, dest, relation in mapped:
                pair = (source.lower(), dest.lower())
                if pair in matched:
                    continue
                if (
                    texts is not None
                    and relation in {"rename", "historical_name"}
                    and not _co_mentioned(source, dest, texts)
                ):
                    continue
                rows.append(
                    {
                        "left_value": source,
                        "right_value": dest,
                        "evidence": f"{relation}:{left}={right}",
                        "confidence": "0.7",
                        "relation": relation,
                    }
                )
                matched.add(pair)
        rows = _enforce_left_function(rows)
        if rows:
            built[key] = rows
    return built


def write_bridges(sqlite_path: str, bridges: dict[tuple[str, str], list[dict[str, str]]]) -> None:
    if not bridges:
        return
    conn = sqlite3.connect(sqlite_path)
    try:
        for (left, right), rows in bridges.items():
            name = bridge_table_name(left, right)
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{name}" ('
                "left_value TEXT, right_value TEXT, evidence TEXT, confidence TEXT, "
                "left_attr TEXT, right_attr TEXT)"
            )
            conn.execute(f'DELETE FROM "{name}"')
            conn.executemany(
                f'INSERT INTO "{name}" VALUES (?, ?, ?, ?, ?, ?)',
                [
                    (
                        row["left_value"],
                        row["right_value"],
                        row.get("evidence") or "",
                        row.get("confidence") or "",
                        left,
                        right,
                    )
                    for row in rows
                ],
            )
        conn.commit()
    finally:
        conn.close()


def list_bridges(sqlite_path: str) -> list[dict[str, str]]:
    conn = sqlite3.connect(sqlite_path)
    try:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bridge_%'"
            )
        ]
        found: list[dict[str, str]] = []
        for name in names:
            try:
                row = conn.execute(
                    f'SELECT left_attr, right_attr FROM "{name}" LIMIT 1'
                ).fetchone()
            except sqlite3.Error:
                continue
            if not row:
                continue
            found.append({"table": name, "left": str(row[0]), "right": str(row[1])})
        return found
    finally:
        conn.close()


def _exact_rows(left_vals: Iterable[str], right_vals: Iterable[str]) -> list[dict[str, str]]:
    right_fold = {item.lower(): item for item in right_vals}
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in left_vals:
        hit = right_fold.get(value.lower())
        if hit is None:
            continue
        key = (value.lower(), hit.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "left_value": value,
                "right_value": hit,
                "evidence": "exact",
                "confidence": "1",
            }
        )
    return rows


def _alias_rows(
    left_vals: set[str],
    right_vals: set[str],
    aliases: dict[str, str],
    matched: set[tuple[str, str]],
) -> list[dict[str, str]]:
    left_fold = {item.lower(): item for item in left_vals}
    right_fold = {item.lower(): item for item in right_vals}
    rows: list[dict[str, str]] = []
    for source, dest in aliases.items():
        if not source or not dest:
            continue
        orientations = (
            (left_fold.get(source.lower()), right_fold.get(dest.lower())),
            (left_fold.get(dest.lower()), right_fold.get(source.lower())),
        )
        for left_hit, right_hit in orientations:
            if not left_hit or not right_hit:
                continue
            key = (left_hit.lower(), right_hit.lower())
            if key in matched:
                continue
            matched.add(key)
            rows.append(
                {
                    "left_value": left_hit,
                    "right_value": right_hit,
                    "evidence": "sql_alias",
                    "confidence": "1",
                }
            )
    return rows


def _co_mentioned(left: str, right: str, texts: list[str]) -> bool:
    a, b = left.strip().lower(), right.strip().lower()
    if not a or not b:
        return False
    return any(a in text and b in text for text in texts)


def _typed_links(
    values: list[str],
    targets: list[str],
    caller,
    left: str,
    right: str,
) -> list[tuple[str, str, str]]:
    """Keep a single-model link when its relation is an identity type."""

    mapped = _llm_link(values, targets, caller, left, right)
    kept: list[tuple[str, str, str]] = []
    for source, (dest, relation) in mapped.items():
        if relation not in KEEP_RELATIONS:
            continue
        kept.append((source, dest, relation))
    return kept


def _llm_link(
    values: list[str],
    targets: list[str],
    caller,
    left: str,
    right: str,
) -> dict[str, tuple[str, str]]:
    prompt = (
        "SQL equijoins these columns, so a LEFT value may co-denote a RIGHT "
        "value even when the strings differ. This is identity, not association: "
        "renames, aliases, abbreviations, and historical names only. "
        "Do not link affiliates, locations, owners, or parents.\n"
        f"LEFT COLUMN: {left}\n"
        f"RIGHT COLUMN: {right}\n"
        f"LEFT: {json.dumps(values)}\n"
        f"RIGHT: {json.dumps(targets)}\n"
        "Return a JSON object mapping each LEFT value to "
        '{"right": <RIGHT value or null>, "relation": '
        '"rename"|"alias"|"abbreviation"|"historical_name"|"affiliate"'
        '|"located_in"|"owned_by"|"parent_of"|"none"}. No commentary.'
    )
    text = caller.complete(
        prompt, purpose="join_bridge", attribute=f"{left}={right}",
    )
    payload = _parse_llm_object(text)
    allowed = {item.lower(): item for item in targets}
    mapped: dict[str, tuple[str, str]] = {}
    for value in values:
        raw = payload.get(value)
        if raw is None:
            raw = payload.get(value.lower())
        dest, relation = _split_link(raw)
        if dest in (None, "", "null"):
            continue
        hit = allowed.get(str(dest).strip().lower())
        if hit is None:
            continue
        mapped[value] = (hit, relation)
    return mapped


def _split_link(raw) -> tuple[str | None, str]:
    if raw in (None, "", "null"):
        return None, "none"
    if isinstance(raw, dict):
        dest = raw.get("right") or raw.get("value") or raw.get("target")
        relation = str(raw.get("relation") or "none").strip().lower()
        return (None if dest in (None, "", "null") else str(dest).strip()), relation
    return str(raw).strip(), "none"


def _enforce_left_function(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Drop left values that map to more than one right value."""

    rights: dict[str, set[str]] = {}
    for row in rows:
        left = row["left_value"].strip().lower()
        rights.setdefault(left, set()).add(row["right_value"].strip().lower())
    banned = {left for left, dests in rights.items() if len(dests) > 1}
    return [row for row in rows if row["left_value"].strip().lower() not in banned]

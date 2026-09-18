"""Per-equijoin-edge profile. Zero tokens. No gold."""

from __future__ import annotations

import sqlite3
from difflib import SequenceMatcher
from typing import Any

from sqlglot import exp

from quwarts.core.models import Workload
from quwarts.core.workload import parse_sql


def blocking_admission(
    left_values: list[str],
    right_values: list[str],
    *,
    prefix: int = 3,
    threshold: float = 0.92,
) -> dict[str, Any]:
    """How many left×right pairs share a prefix block, vs all pairs."""

    possible = max(len(left_values) * len(right_values), 1)

    def key(value: str) -> str:
        text = " ".join(str(value).replace("_", " ").casefold().split())
        return text[:prefix] if text else ""

    admitted = 0
    high = 0
    high_admitted = 0
    high_blocked = 0
    for left in left_values:
        lk = key(left)
        lf = " ".join(str(left).replace("_", " ").casefold().split())
        for right in right_values:
            rk = key(right)
            rf = " ".join(str(right).replace("_", " ").casefold().split())
            ratio = SequenceMatcher(None, lf, rf).ratio()
            same = bool(lk) and lk == rk
            if same:
                admitted += 1
            if ratio >= threshold:
                high += 1
                if same:
                    high_admitted += 1
                else:
                    high_blocked += 1
    return {
        "n_left": len(left_values),
        "n_right": len(right_values),
        "possible_pairs": possible,
        "admitted_pairs": admitted,
        "admission_rate": admitted / possible,
        "pairs_above_threshold": high,
        "high_admitted": high_admitted,
        "high_blocked": high_blocked,
        "prefix": prefix,
        "threshold": threshold,
    }


def profile_join_edges(
    workload: Workload,
    sqlite_path: str,
    statements: dict[str, str],
    empty_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    empty = set(empty_ids or [])
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for template in workload.templates:
        sql = template.raw_sql or template.canonical_sql
        preds = _join_predicates(sql)
        for left, right in template.join_pairs:
            key = tuple(sorted((left, right)))
            row = edges.setdefault(
                key,
                {
                    "left": left,
                    "right": right,
                    "predicates": [],
                    "functions": set(),
                    "query_ids": [],
                    "empty_query_ids": [],
                },
            )
            row["query_ids"].extend(template.statement_ids)
            row["empty_query_ids"].extend(qid for qid in template.statement_ids if qid in empty)
            for pred in preds:
                if pred["text"] not in row["predicates"]:
                    row["predicates"].append(pred["text"])
                row["functions"].update(pred["functions"])

    conn = sqlite3.connect(sqlite_path)
    try:
        for row in edges.values():
            left_vals = _distinct_col(conn, row["left"])
            right_vals = _distinct_col(conn, row["right"])
            left_canon = _distinct_col(conn, f"{row['left']}__canonical") or left_vals
            right_canon = _distinct_col(conn, f"{row['right']}__canonical") or right_vals
            row["n_left"] = len(left_vals)
            row["n_right"] = len(right_vals)
            row["exact_yield"] = _yield(left_vals, right_vals, fold=False)
            row["canonical_yield"] = _yield(left_canon, right_canon, fold=True)
            row["functions"] = sorted(row["functions"])
            row["query_ids"] = sorted(set(row["query_ids"]))
            row["empty_query_ids"] = sorted(set(row["empty_query_ids"]))
            row["n_empty"] = len(row["empty_query_ids"])
            unmatched = [item for item in left_vals if item.casefold() not in {v.casefold() for v in right_vals}]
            row["unmatched_sample"] = [
                {"left": item, "nearest": _nearest(item, right_vals)}
                for item in unmatched[:20]
            ]
    finally:
        conn.close()
    return sorted(edges.values(), key=lambda item: (-item["n_empty"], -item["n_left"]))


def _join_predicates(sql: str | None) -> list[dict[str, Any]]:
    if not sql:
        return []
    try:
        tree = parse_sql(sql)
    except Exception:
        return []
    found: list[dict[str, Any]] = []
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            continue
        funcs = {
            node.__class__.__name__.upper()
            for node in on.walk()
            if isinstance(node, (exp.Trim, exp.Lower, exp.Upper, exp.Cast))
        }
        found.append({"text": on.sql(dialect="sqlite"), "functions": sorted(funcs)})
    return found


def _distinct_col(conn, attribute: str) -> list[str]:
    if "." in attribute:
        entity, bare = attribute.split(".", 1)
    else:
        entity, bare = "", attribute
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    candidates = []
    if entity and entity in tables:
        candidates.append((entity, bare))
    for table in tables:
        cols = [col[1] for col in conn.execute(f'PRAGMA table_info("{table}")')]
        if bare in cols:
            candidates.append((table, bare))
            break
    if not candidates:
        return []
    table, col = candidates[0]
    try:
        rows = conn.execute(
            f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL AND "{col}" <> \'\''
        ).fetchall()
    except sqlite3.Error:
        return []
    return [str(row[0]).strip() for row in rows if row[0] not in (None, "")]


def _yield(left: list[str], right: list[str], *, fold: bool) -> float:
    if not left:
        return 0.0
    if fold:
        have = {" ".join(item.replace("_", " ").casefold().split()) for item in right}
        hits = sum(1 for item in left if " ".join(item.replace("_", " ").casefold().split()) in have)
    else:
        have = {item.casefold() for item in right}
        hits = sum(1 for item in left if item.casefold() in have)
    return hits / len(left)


def _nearest(value: str, candidates: list[str], k: int = 3) -> list[dict[str, Any]]:
    scored = []
    for item in candidates:
        ratio = SequenceMatcher(None, value.casefold(), item.casefold()).ratio()
        scored.append((ratio, item))
    scored.sort(reverse=True)
    return [{"value": item, "ratio": round(ratio, 3)} for ratio, item in scored[:k]]

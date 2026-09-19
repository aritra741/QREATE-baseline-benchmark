"""Zero-token selective replay of stored group votes. Does not call a model."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from quwarts.core.component_oracle import base_checksums
from quwarts.core.pipeline import official_sql
from quwarts.core.query_group import (
    _fetch,
    _join_pairs,
    _norm_bag,
    _support_keys,
    apply_official_group,
    ensure_group_table,
    group_bags,
)
from quwarts.core.query_witness import normalize_group

RULES = (
    "empty_only",
    "empty_direct_branch",
    "empty_nonnull",
    "empty_direct_branch_nonnull",
    "direct_branch_all",
    "fill_null_only",
    "full_original",
)
OFFICIAL_RULE = "empty_only"


def is_sql_null(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in {"", "null", "none"}


def strategy_ran(vote: dict[str, Any], name: str) -> bool:
    raw = vote.get("raw")
    if not isinstance(raw, dict):
        return False
    if name == "direct":
        return isinstance(raw.get("direct"), dict)
    if name == "branch":
        return isinstance(raw.get("branch"), list) and len(raw.get("branch")) > 0
    if name == "adjudicator":
        return isinstance(raw.get("adjudicator"), dict)
    return False


def direct_branch_agree(vote: dict[str, Any]) -> bool:
    if not strategy_ran(vote, "direct") or not strategy_ran(vote, "branch"):
        return False
    return normalize_group(vote.get("direct_decision")) == normalize_group(vote.get("branch_decision"))


def vote_resolved(vote: dict[str, Any]) -> bool:
    return bool(vote.get("resolved")) and vote.get("agreement") != "fallback"


def load_group_votes(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def official_row_bags(
    sqlite_path: str | Path,
    statements: dict[str, str],
    predicates: list[Any],
) -> dict[str, dict[str, Any]]:
    out = {}
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        for qid, sql in statements.items():
            rewritten = official_sql(sql, sqlite_path, predicates)
            try:
                rows = _fetch(conn, rewritten)
                error = None
            except Exception as exc:
                rows = []
                error = str(exc)
            out[qid] = {
                "query_id": qid,
                "n_rows": len(rows),
                "empty": len(rows) == 0,
                "error": error,
                "count_mass": count_mass(rows),
                "bag": _norm_bag(rows),
            }
    finally:
        conn.close()
    return out


def count_mass(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in rows:
        for value in row.values():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                total += float(value)
    return total


def rule_accepts(
    vote: dict[str, Any],
    rule: str,
    empty_queries: set[str],
) -> bool:
    if not vote_resolved(vote):
        return False
    qid = str(vote.get("query_id") or "")
    empty = qid in empty_queries
    proposed = vote.get("group_value")
    old = vote.get("old_label")
    if rule == "empty_only":
        return empty
    if rule == "empty_direct_branch":
        return empty and direct_branch_agree(vote)
    if rule == "empty_nonnull":
        return empty and not is_sql_null(proposed)
    if rule == "empty_direct_branch_nonnull":
        return empty and direct_branch_agree(vote) and not is_sql_null(proposed)
    if rule == "direct_branch_all":
        return direct_branch_agree(vote)
    if rule == "fill_null_only":
        return is_sql_null(old) and not is_sql_null(proposed)
    if rule == "full_original":
        return True
    raise ValueError(f"unknown group replay rule: {rule}")


def _upsert(conn: sqlite3.Connection, vote: dict[str, Any]) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO group_labels("
        "expr_id, witness_key, group_value, resolved, direct_decision, branch_decision, "
        "adjudicator_decision, raw, evidence, context_hash, token_cost, provenance) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            vote.get("expr_id"),
            str(vote.get("witness_key")),
            None if is_sql_null(vote.get("group_value")) else str(vote.get("group_value")),
            1,
            None if vote.get("direct_decision") is None else str(vote.get("direct_decision")),
            None if vote.get("branch_decision") is None else str(vote.get("branch_decision")),
            None if vote.get("adjudicator_decision") is None else str(vote.get("adjudicator_decision")),
            json.dumps(vote.get("raw"), default=str),
            vote.get("evidence"),
            vote.get("context_hash"),
            int(vote.get("token_cost") or 0),
            str(vote.get("query_id") or vote.get("provenance") or ""),
        ],
    )


def replay_group_rule(
    dest: Path,
    statements: dict[str, str],
    predicates: list[Any],
    votes: list[dict[str, Any]],
    rule: str,
    empty_queries: set[str],
    uses_expr: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    site_local = rule != "full_original"
    conn = sqlite3.connect(str(dest))
    ensure_group_table(conn, site_local=site_local)
    conn.commit()
    checksums = base_checksums(conn)
    bags = group_bags(dest, statements, predicates, conn=conn, site_local=site_local)
    before_bags = dict(bags)
    support = {qid: _support_keys(conn, dest, qid, sql, predicates) for qid, sql in statements.items()}
    joins = {qid: _join_pairs(conn, dest, sql, predicates) for qid, sql in statements.items()}
    attempted = materialized = visible = rolled = 0
    isolation_fail = 0
    accepted: list[dict[str, Any]] = []
    expr_users = uses_expr or {}
    try:
        for vote in votes:
            if not rule_accepts(vote, rule, empty_queries):
                continue
            attempted += 1
            qid = str(vote.get("query_id") or "")
            if normalize_group(vote.get("group_value")) == normalize_group(vote.get("old_label")):
                rolled += 1
                continue
            conn.execute("SAVEPOINT group_replay")
            _upsert(conn, vote)
            target_sql = statements.get(qid)
            if not target_sql:
                conn.execute("ROLLBACK TO group_replay")
                conn.execute("RELEASE group_replay")
                rolled += 1
                continue
            target_rewritten, _ = apply_official_group(
                target_sql, dest, predicates, site_id=qid if site_local else None
            )
            target_bag = _norm_bag(_fetch(conn, target_rewritten))
            if target_bag == bags.get(qid) and site_local:
                conn.execute("ROLLBACK TO group_replay")
                conn.execute("RELEASE group_replay")
                rolled += 1
                continue
            after = group_bags(dest, statements, predicates, conn=conn, site_local=site_local)
            changed = [item for item, bag in after.items() if bag != bags.get(item)]
            allowed = {qid} if site_local else set(expr_users.get(str(vote.get("expr_id") or ""), set()) | {qid})
            leak = [item for item in changed if item not in allowed]
            support_broken = any(
                _support_keys(conn, dest, item, statements[item], predicates) != support[item]
                for item in changed or [qid]
            )
            join_broken = any(
                _join_pairs(conn, dest, statements[item], predicates) != joins[item]
                for item in changed or [qid]
            )
            checksum_broken = base_checksums(conn) != checksums
            if leak or support_broken or join_broken or checksum_broken or not changed:
                conn.execute("ROLLBACK TO group_replay")
                conn.execute("RELEASE group_replay")
                rolled += 1
                if leak:
                    isolation_fail += 1
                continue
            conn.execute("RELEASE group_replay")
            bags = after
            materialized += 1
            visible += 1
            accepted.append(vote)
        conn.commit()
    finally:
        conn.close()
    after_bags = group_bags(dest, statements, predicates, site_local=site_local)
    frozen = sqlite3.connect(str(dest))
    try:
        checksums_after = base_checksums(frozen)
        n_sidecar = int(frozen.execute("SELECT COUNT(*) FROM group_labels WHERE resolved = 1").fetchone()[0])
    finally:
        frozen.close()
    return {
        "rule": rule,
        "site_local": site_local,
        "n_attempted": attempted,
        "n_materialized": materialized,
        "n_sql_visible": visible,
        "n_sidecar_rows": n_sidecar,
        "n_rolled_back": rolled,
        "n_isolation_fail": isolation_fail,
        "accepted": accepted,
        "before_bags": before_bags,
        "bags": after_bags,
        "checksums": checksums_after,
    }

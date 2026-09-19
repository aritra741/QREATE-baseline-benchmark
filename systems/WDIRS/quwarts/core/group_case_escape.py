"""SQLite CASE-fallback inspection of stored group votes. No model calls."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlglot import exp

from quwarts.core.group_consensus import query_expr_map
from quwarts.core.group_replay import is_sql_null, vote_resolved
from quwarts.core.query_filter import alias_order, decode_witness_key, outer_alias_tables
from quwarts.core.query_group import _fetch, parse_allowed, parse_sql, same_label
from quwarts.core.signature import table_aliases

_AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def case_branches(expr_sql: str) -> tuple[list[tuple[str, Any]], Any]:
    tree = parse_sql(expr_sql)
    case = tree if isinstance(tree, exp.Case) else tree.find(exp.Case)
    if case is None:
        raise ValueError("not a CASE expression")
    scrutinee = case.this
    branches = []
    for pair in case.args.get("ifs") or []:
        cond = pair.this
        result = pair.args.get("true")
        if scrutinee is not None:
            cond_sql = f"({scrutinee.sql(dialect='sqlite')}) = ({cond.sql(dialect='sqlite') if cond is not None else 'NULL'})"
        else:
            cond_sql = cond.sql(dialect="sqlite") if cond is not None else "1"
        value = None
        if result is None or isinstance(result, exp.Null):
            value = None
        elif isinstance(result, exp.Literal):
            value = result.this
            if result.is_number:
                try:
                    value = int(value) if "." not in str(value) else float(value)
                except (TypeError, ValueError):
                    pass
            else:
                value = str(value)
        else:
            value = result.sql(dialect="sqlite")
        branches.append((cond_sql, value))
    default = case.args.get("default")
    if default is None or isinstance(default, exp.Null):
        else_value = None
    elif isinstance(default, exp.Literal):
        else_value = default.this
        if default.is_number:
            try:
                else_value = int(else_value) if "." not in str(else_value) else float(else_value)
            except (TypeError, ValueError):
                pass
        else:
            else_value = str(else_value)
    else:
        else_value = default.sql(dialect="sqlite")
    return branches, else_value


def _truth_sql(cond: str) -> str:
    return (
        f"CASE WHEN ({cond}) THEN 'TRUE' "
        f"WHEN NOT ({cond}) THEN 'FALSE' "
        f"ELSE 'NULL' END"
    )


def _bind_rowids(original_sql: str, official_sql_text: str, witness_key: str) -> list[str]:
    off = parse_sql(official_sql_text)
    order = alias_order(off)
    tables = outer_alias_tables(off) or table_aliases(off)
    rids = decode_witness_key(witness_key)
    table_rid = {}
    for alias, rid in zip(order, rids):
        table_rid[(tables.get(alias) or alias).lower()] = rid
    orig = parse_sql(original_sql)
    orig_tables = outer_alias_tables(orig) or table_aliases(orig)
    preds = []
    for alias in alias_order(orig):
        table = (orig_tables.get(alias) or alias).lower()
        rid = table_rid.get(table)
        if rid is None:
            continue
        preds.append(f"{_quote(alias)}.rowid = {int(rid)}")
    if not preds and rids:
        rid = rids[0]
        if rid is not None:
            alias = alias_order(orig)[0] if alias_order(orig) else None
            if alias:
                preds.append(f"{_quote(alias)}.rowid = {int(rid)}")
    return preds


def _eval_select(original_sql: str, projections: list[tuple[str, str]], binds: list[str]) -> str:
    tree = parse_sql(original_sql)
    if not isinstance(tree, exp.Select):
        raise ValueError("expected SELECT")
    tree.set("group", None)
    tree.set("having", None)
    tree.set("order", None)
    tree.set("distinct", None)
    tree.set("limit", None)
    exprs = []
    for alias, sql in projections:
        node = parse_sql(sql)
        if node.find(_AGGS):
            continue
        exprs.append(exp.alias_(node, alias))
    if not exprs:
        exprs.append(exp.alias_(exp.Literal.number(1), "ok"))
    tree.set("expressions", exprs)
    where = tree.args.get("where")
    extra = " AND ".join(binds) if binds else "1"
    extra_node = parse_sql(extra)
    if where is None:
        tree.set("where", exp.Where(this=extra_node))
    else:
        tree.set("where", exp.Where(this=exp.and_(where.this, extra_node)))
    return tree.sql(dialect="sqlite")


def eval_case_state(
    conn: sqlite3.Connection,
    original_sql: str,
    official_sql_text: str,
    expr_sql: str,
    witness_key: str,
) -> dict[str, Any]:
    branches, else_value = case_branches(expr_sql)
    binds = _bind_rowids(original_sql, official_sql_text, witness_key)
    projections = [(f"w{i}", _truth_sql(cond)) for i, (cond, _) in enumerate(branches)]
    fired_sql = "CASE " + " ".join(f"WHEN ({cond}) THEN {i + 1}" for i, (cond, _) in enumerate(branches)) + " ELSE 0 END"
    projections.append(("fired", fired_sql))
    projections.append(("result", f"({expr_sql})"))
    sql = _eval_select(original_sql, projections, binds)
    rows = _fetch(conn, sql)
    if not rows:
        sql = _eval_select(original_sql, projections, binds)
        # retry without original WHERE: rowid only
        tree = parse_sql(original_sql)
        tree.set("where", None)
        sql = _eval_select(tree.sql(dialect="sqlite"), projections, binds)
        rows = _fetch(conn, sql)
    row = rows[0] if rows else {}
    truths = []
    for i, _ in enumerate(branches):
        raw = str(row.get(f"w{i}") or "NULL").upper()
        if raw not in {"TRUE", "FALSE", "NULL"}:
            raw = "NULL"
        truths.append(raw)
    fired = int(row.get("fired") or 0)
    result = row.get("result")
    if fired > 0:
        selected = "branch"
        selected_index = fired
        selected_label = branches[fired - 1][1]
    else:
        selected = "ELSE"
        selected_index = 0
        selected_label = else_value
    return {
        "truths": truths,
        "n_true": sum(1 for item in truths if item == "TRUE"),
        "n_false": sum(1 for item in truths if item == "FALSE"),
        "n_null": sum(1 for item in truths if item == "NULL"),
        "fired": fired,
        "selected": selected,
        "selected_index": selected_index,
        "selected_label": selected_label,
        "original_result": result,
        "else_value": else_value,
        "branch_results": [value for _, value in branches],
        "rows": len(rows),
    }


def unknown_else_escape(state: dict[str, Any], vote: dict[str, Any]) -> bool:
    if not vote_resolved(vote) or is_sql_null(vote.get("group_value")):
        return False
    if state["n_true"] != 0 or state["selected"] != "ELSE":
        return False
    if state["n_null"] < 1:
        return False
    proposed = vote.get("group_value")
    legal = [value for value in state["branch_results"] if not is_sql_null(value)]
    if parse_allowed(proposed, legal) is None:
        return False
    if same_label(proposed, state["else_value"]):
        return False
    return True


def all_else_escape(state: dict[str, Any], vote: dict[str, Any]) -> bool:
    if not vote_resolved(vote) or is_sql_null(vote.get("group_value")):
        return False
    if state["n_true"] != 0 or state["selected"] != "ELSE":
        return False
    proposed = vote.get("group_value")
    legal = [value for value in state["branch_results"] if not is_sql_null(value)]
    if parse_allowed(proposed, legal) is None:
        return False
    if same_label(proposed, state["else_value"]):
        return False
    return True


def assignment_kind(state: dict[str, Any], vote: dict[str, Any]) -> str:
    proposed = vote.get("group_value")
    if state["selected"] == "ELSE" and state["n_null"] >= 1 and state["n_true"] == 0:
        return "unknown_to_branch"
    if state["selected"] == "ELSE" and state["n_null"] == 0 and state["n_true"] == 0:
        return "all_false_else_to_branch"
    if state["selected"] == "branch" and same_label(proposed, state["else_value"]):
        return "branch_to_else"
    if state["selected"] == "branch" and not same_label(proposed, state["selected_label"]):
        return "branch_to_different_branch"
    return "other"


def inspect_votes(
    sqlite_path: str | Path,
    queries: list[dict[str, str]],
    predicates: list[Any],
    votes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    statements = {row["query_id"]: row["sql"] for row in queries}
    maps: dict[str, dict[str, Any]] = {}
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    out = []
    try:
        for vote in votes:
            qid = str(vote.get("query_id") or "")
            sql = statements.get(qid)
            if sql is None:
                continue
            if qid not in maps:
                maps[qid] = query_expr_map(qid, sql, sqlite_path, predicates)
            meta = maps[qid].get(str(vote.get("expr_id")))
            if meta is None:
                continue
            state = eval_case_state(
                conn,
                sql,
                meta["official_sql"],
                meta["original"].sql,
                str(vote.get("witness_key")),
            )
            out.append(
                {
                    "vote": vote,
                    "state": state,
                    "unknown_else_escape": unknown_else_escape(state, vote),
                    "all_else_escape": all_else_escape(state, vote),
                    "kind": assignment_kind(state, vote),
                    "query_id": qid,
                    "expr_id": str(vote.get("expr_id")),
                    "witness_key": str(vote.get("witness_key")),
                    "proposed": vote.get("group_value"),
                    "old_label": vote.get("old_label"),
                    "alias": meta["alias"],
                }
            )
    finally:
        conn.close()
    return out

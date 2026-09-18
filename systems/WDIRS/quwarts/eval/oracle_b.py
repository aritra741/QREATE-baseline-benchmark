"""Step 2. Oracle B: gold signatures and rewrite validation. Diagnostic only."""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from sqlglot import exp

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.signature import (
    audit_workload,
    enumerate_predicates,
    gold_signature_sql,
    materialize_signatures,
    rewrite_sql,
)
from quwarts.core.workload import parse_sql
from quwarts.experiments.synthesize_case80 import gold_name, queries_for

OUT = ROOT / "results" / "quwarts_med_signatures"


def gold_conn():
    from diagnostics.run_config_grid import load_ground_truth
    from spp.config_grid import _build_in_memory_db

    return _build_in_memory_db(load_ground_truth(gold_name("Med")))


def _same(left, right) -> bool:
    if left is None and right is None:
        return True
    return left == right


def predicate_expression_check(conn: sqlite3.Connection, predicates) -> list[dict]:
    mismatches = []
    for pred in predicates:
        sql = (
            f'SELECT "{pred.sig_name}" AS sig, {gold_signature_sql(pred)} AS orig '
            f'FROM "{pred.table}"'
        )
        try:
            rows = conn.execute(sql).fetchall()
        except sqlite3.Error as exc:
            mismatches.append({"pred_id": pred.pred_id, "error": str(exc), "n": None})
            continue
        bad = [(sig, orig) for sig, orig in rows if not _same(sig, orig)]
        if bad:
            mismatches.append({
                "pred_id": pred.pred_id,
                "attribute": pred.attribute,
                "n": len(bad),
                "sample": bad[:5],
            })
    return mismatches


def _scalar_exprs(tree: exp.Expression) -> list[exp.Expression]:
    found: list[exp.Expression] = []
    if not isinstance(tree, exp.Select):
        return found
    for projection in tree.expressions:
        inner = projection.this if isinstance(projection, exp.Alias) else projection
        if isinstance(inner, exp.Case):
            found.append(inner)
        for case in inner.find_all(exp.Case):
            if case is not inner:
                found.append(case)
    where = tree.args.get("where")
    if where is not None:
        found.append(where.this if isinstance(where, exp.Where) else where)
    return found


def _strip_to_from(tree: exp.Expression) -> exp.Expression:
    clone = tree.copy()
    if isinstance(clone, exp.Select):
        clone.set("group", None)
        clone.set("order", None)
        clone.set("having", None)
        clone.set("limit", None)
        clone.set("where", None)
    return clone


def query_expression_check(conn: sqlite3.Connection, queries, predicates) -> list[dict]:
    mismatches = []
    for row in queries:
        orig_tree = parse_sql(row["sql"])
        rew_sql = rewrite_sql(row["sql"], predicates)
        rew_tree = parse_sql(rew_sql)
        orig_exprs = _scalar_exprs(orig_tree)
        rew_exprs = _scalar_exprs(rew_tree)
        if len(orig_exprs) != len(rew_exprs):
            mismatches.append({
                "query_id": row["query_id"],
                "error": f"expr count {len(orig_exprs)} vs {len(rew_exprs)}",
            })
            continue
        base = _strip_to_from(orig_tree)
        for index, (left, right) in enumerate(zip(orig_exprs, rew_exprs)):
            probe = base.copy()
            probe.set(
                "expressions",
                [
                    exp.alias_(left.copy(), "o"),
                    exp.alias_(right.copy(), "r"),
                ],
            )
            sql = probe.sql(dialect="sqlite")
            try:
                pairs = conn.execute(sql).fetchall()
            except sqlite3.Error as exc:
                mismatches.append({
                    "query_id": row["query_id"],
                    "expr": index,
                    "error": str(exc),
                    "sql": sql,
                })
                continue
            bad = [(o, r) for o, r in pairs if not _same(o, r)]
            if bad:
                mismatches.append({
                    "query_id": row["query_id"],
                    "expr": index,
                    "n": len(bad),
                    "sample": bad[:5],
                    "left": left.sql(dialect="sqlite"),
                    "right": right.sql(dialect="sqlite"),
                })
    return mismatches


def query_bag_check(conn: sqlite3.Connection, queries, predicates) -> list[dict]:
    results = []
    for row in queries:
        rewritten = rewrite_sql(row["sql"], predicates)
        ordered = parse_sql(row["sql"]).args.get("order") is not None
        try:
            orig = conn.execute(row["sql"]).fetchall()
        except sqlite3.Error as exc:
            results.append({
                "query_id": row["query_id"],
                "pass": False,
                "error": f"orig: {exc}",
            })
            continue
        try:
            pred = conn.execute(rewritten).fetchall()
        except sqlite3.Error as exc:
            results.append({
                "query_id": row["query_id"],
                "pass": False,
                "error": f"rewritten: {exc}",
                "rewritten": rewritten,
            })
            continue
        if ordered:
            ok = orig == pred
        else:
            ok = Counter(orig) == Counter(pred)
        results.append({
            "query_id": row["query_id"],
            "pass": ok,
            "orig_n": len(orig),
            "rewritten_n": len(pred),
            "rewritten": rewritten if not ok else None,
        })
    return results


def main() -> int:
    queries = queries_for("Med")
    report = audit_workload(queries)
    predicates = enumerate_predicates(report.occurrences, report.signature_eligible)
    conn = gold_conn()
    materialize_signatures(conn, predicates)
    pred_mismatch = predicate_expression_check(conn, predicates)
    expr_mismatch = query_expression_check(conn, queries, predicates)
    bags = query_bag_check(conn, queries, predicates)
    bag_fail = [item for item in bags if not item["pass"]]
    payload = {
        "step": 2,
        "label": "oracle_diagnostic",
        "n_predicates": len(predicates),
        "expression_equivalence": {
            "predicate_mismatches": pred_mismatch,
            "query_expr_mismatches": expr_mismatch,
            "pass": not pred_mismatch and not expr_mismatch,
        },
        "query_equivalence": {
            "n": len(bags),
            "n_pass": sum(1 for item in bags if item["pass"]),
            "failures": bag_fail,
            "pass": not bag_fail,
        },
    }
    payload["pass"] = (
        payload["expression_equivalence"]["pass"]
        and payload["query_equivalence"]["pass"]
    )
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "step2_oracle_b.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({
        "wrote": str(path),
        "label": "oracle_diagnostic",
        "expression_pass": payload["expression_equivalence"]["pass"],
        "n_predicate_mismatches": len(pred_mismatch),
        "n_query_expr_mismatches": len(expr_mismatch),
        "query_pass": payload["query_equivalence"]["pass"],
        "query_n_pass": payload["query_equivalence"]["n_pass"],
        "query_n": payload["query_equivalence"]["n"],
        "pass": payload["pass"],
        "expr_sample": expr_mismatch[:3],
        "bag_sample": bag_fail[:3],
        "pred_sample": pred_mismatch[:3],
    }, indent=2, default=str))
    return 0 if payload["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

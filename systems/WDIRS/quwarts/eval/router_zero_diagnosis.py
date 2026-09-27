"""AUDIT ONLY (reads gold): why do some held-out queries score 0 for every system?

For each held-out query whose product is 0 for QuWARTS (per-attribute run), fair DocETL (sentinels
as NULL) and recorded DocETL, this puts the gold result next to each system's result, and measures
per-document agreement with gold for every column the query uses, split into gold-null and
gold-non-null documents. Nothing here feeds the system; it runs after the freeze.

    python -m quwarts.eval.router_zero_diagnosis --corpus legal
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from quwarts.core.pipeline import official_sql
from quwarts.core.router.comparator import is_null, value_score
from quwarts.core.router.registry import RESULTS, get_corpus
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.docetl_rescore import recorded_tables

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def execute(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error as exc:
        return [{"__error__": str(exc)}]
    cols = [c[0] for c in cur.description or []]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def columns_used(sql: str, columns: set[str]) -> list[str]:
    return sorted({t for t in IDENT.findall(sql) if t in columns})


def doc_key(doc_id: Any) -> str:
    return str(doc_id).removesuffix(".txt").strip()


def agreement(pred: dict[str, dict], gold: dict[str, dict], column: str, value_type: str) -> dict[str, Any]:
    both = [d for d in gold if d in pred]
    nonnull = [d for d in both if not is_null(gold[d].get(column))]
    null = [d for d in both if is_null(gold[d].get(column))]
    acc = lambda ds: round(sum(value_score(pred[d].get(column), gold[d].get(column), value_type) for d in ds) / len(ds), 3) if ds else None
    wrong = Counter((str(pred[d].get(column)), str(gold[d].get(column))) for d in nonnull
                    if value_score(pred[d].get(column), gold[d].get(column), value_type) < 1)
    return {"docs": len(both), "gold_nonnull": len(nonnull), "acc_on_gold_nonnull": acc(nonnull),
            "gold_null": len(null), "acc_on_gold_null": acc(null),
            "pred_null_rate": round(sum(is_null(pred[d].get(column)) for d in both) / len(both), 3) if both else None,
            "top_confusions_pred_vs_gold": wrong.most_common(6)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    args = parser.parse_args(argv)
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.synthesize_case80 import gold_name
    from spp.config_grid import _build_in_memory_db

    spec = get_corpus(args.corpus)
    diag = RESULTS / "docetl_diagnostics" / spec.name
    cmp = json.loads((diag / "fair_comparison.json").read_text())["per_query"]
    zero = sorted(q for q, v in cmp.items()
                  if v["quwarts_per_attribute"] == 0 and v["fair_nullfix"] == 0 and v["recorded"] == 0)
    manifest, _ = recorded_tables(spec.name)
    gold_tables = load_ground_truth(gold_name({"legal": "Legal"}.get(spec.name, spec.name)))
    gold_conn = _build_in_memory_db(gold_tables)
    types = spec.benchmark_attribute_descriptions(purpose="audit")
    table = spec.tables[0]
    vtype = {a: str(r.get("value_type", "str")) for a, r in types.get(table.attributes_key, {}).items()}
    gold_docs = {doc_key(r["id"]): r for r in gold_tables[table.sql_name]}

    qw_db = RESULTS / "quwarts_router_v3" / spec.name / "shared_read_per_attribute" / "read_first.db"
    audit = audit_workload([{"query_id": q, "sql": s} for q, s in manifest.items()])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    qw_conn = sqlite3.connect(qw_db)
    qw_docs = {doc_key(r["doc_id"]): r for r in execute(qw_conn, f"SELECT * FROM {table.sql_name}")}
    report = {"audit_only": True, "zero_queries": zero, "queries": {}}
    for qid in zero:
        sql = manifest[qid]
        cols = columns_used(sql, set(vtype))
        dl_db = diag / "fair_nullfix" / f"{qid.replace(':', '_')}.db"
        dl_conn = sqlite3.connect(dl_db)
        dl_docs = {doc_key(r["doc_id"]): r for r in execute(dl_conn, f"SELECT * FROM {table.sql_name}")}
        entry = {
            "sql": sql,
            "gold": execute(gold_conn, sql)[:12],
            "quwarts": execute(qw_conn, official_sql(sql, qw_db, predicates, query_id=qid))[:12],
            "docetl_fair": execute(dl_conn, official_sql(sql, dl_db, predicates, query_id=qid))[:12],
            "columns": {c: {"type": vtype.get(c),
                            "quwarts": agreement(qw_docs, gold_docs, c, vtype.get(c, "str")),
                            "docetl_fair": agreement(dl_docs, gold_docs, c, vtype.get(c, "str")),
                            "gold_top_values": Counter(str(g.get(c)) for g in gold_docs.values()).most_common(8)}
                        for c in cols},
        }
        dl_conn.close()
        report["queries"][qid] = entry
    out = RESULTS / "quwarts_router_v3" / spec.name / "zero_diagnosis.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

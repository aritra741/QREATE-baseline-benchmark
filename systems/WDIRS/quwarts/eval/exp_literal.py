"""Does a reader that sees the query's constant report that constant?  A natural experiment in DocETL's saved reads.

DocETL's prompt carries the query's SQL. It reads the same (document, column) once per query that needs it, so a
column is read both by queries whose WHERE clause names a constant for it (``manufacturer LIKE '%Pfizer%'``,
``verdict = 'Dismissed'``) and by queries that do not name that constant. Per (column, constant): among documents
whose correct value does NOT satisfy the condition, the share of reads that satisfy it (false match), when the
constant is shown and when it is not; among documents whose correct value satisfies it, the share that do (hit).
Our system's read of the same column (realistic v1 views) is given for reference. No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_literal
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import sqlglot
from sqlglot import exp

from quwarts.core.router.comparator import is_null
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_docetl_variation import ROOTS, blank, catalogs, safe
from quwarts.eval.exp_tau import EXP

CORPORA = ["cspaper", "player", "art", "med", "legal"]
QV = Path("/scratch/general/vast/u1592362/quwarts_exp/RW-qviews/RW-norereads-V3")


def conditions(sql: str) -> list[tuple[str, str, str]]:
    """(table.column, operator, constant) for = / LIKE / IN with a string constant in the WHERE clause."""
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:  # noqa: BLE001
        return []
    alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    single = next(iter(alias.values())) if len(set(alias.values())) == 1 else None
    w = tree.find(exp.Where)
    out = []
    if w is None:
        return out
    for node in w.find_all(exp.EQ, exp.Like, exp.In):
        col = node.find(exp.Column)
        if col is None:
            continue
        t = alias.get(col.table, col.table) if col.table else single
        lits = [x.this for x in node.find_all(exp.Literal) if x.is_string]
        op = "like" if isinstance(node, exp.Like) else "eq"
        for lit in lits:
            if t and lit.strip("%"):
                out.append((f"{t}.{col.name}", op, lit))
    return out


def satisfies(v, op: str, lit: str) -> bool:
    if blank(v):
        return False
    s = str(v).casefold()
    if op == "like":
        pat = "^" + ".*".join(re.escape(p) for p in lit.casefold().split("%")) + "$"
        return re.search(pat, s, re.S) is not None
    return s.strip() == lit.casefold().strip()


def main() -> int:
    out = {}
    tot = defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0, 0])  # corpus -> shown fm n, shown fm k, not-shown n, k, shown hit n,k, not hit n,k
    for c in CORPORA:
        cat = catalogs(c)
        by_safe = {safe(q): q for q in cat}
        gdoc = gold_by_doc(c)
        reads = defaultdict(lambda: defaultdict(list))  # column -> doc -> [(qid, value)]
        conds = {}
        for root in ROOTS:
            base = EXP.parent / root / c
            if not base.exists():
                continue
            for qdir in base.iterdir():
                q = by_safe.get(qdir.name)
                if q is None or not qdir.is_dir():
                    continue
                conds[q] = conditions(cat[q])
                for tdir in qdir.glob("table_*"):
                    t = tdir.name[len("table_"):]
                    f = tdir / "pipeline_output.json"
                    if f.exists():
                        for row in json.loads(f.read_text()):
                            d = str(row.get("doc_id")).rsplit(".", 1)[0]
                            for a, v in row.items():
                                if a != "doc_id":
                                    reads[f"{t}.{a.lower()}"][d].append((q, v))
        pairs = {(col.lower(), op, lit) for cs in conds.values() for col, op, lit in cs}
        res = []
        for col, op, lit in sorted(pairs):
            t, a = col.split(".", 1)
            g = {str(d).rsplit(".", 1)[0]: r for d, r in gdoc.get(t, {}).items()}
            s = {"shown": [0, 0, 0, 0], "not shown": [0, 0, 0, 0]}  # non-sat docs, false matches, sat docs, hits
            for d, rs in reads.get(col, {}).items():
                gr = g.get(d) or {}
                gv = next((v for k, v in gr.items() if k.lower() == a), None)
                if is_null(gv):
                    continue
                truth = satisfies(gv, op, lit)
                for q, v in rs:
                    shown = any(cc.lower() == col and cl == lit for cc, _o, cl in conds.get(q, []))
                    k = s["shown" if shown else "not shown"]
                    m = satisfies(v, op, lit)
                    if truth:
                        k[2] += 1
                        k[3] += m
                    else:
                        k[0] += 1
                        k[1] += m
            if s["shown"][0] + s["shown"][2] == 0 or s["not shown"][0] + s["not shown"][2] == 0:
                continue
            for i, w in enumerate(("shown", "not shown")):
                for j in range(4):
                    tot[c][4 * (j // 2) + 2 * i + j % 2] += s[w][j]
            res.append({"column": col, "op": op, "constant": lit,
                        "false_match_shown": round(s["shown"][1] / s["shown"][0], 3) if s["shown"][0] else None,
                        "false_match_not_shown": round(s["not shown"][1] / s["not shown"][0], 3) if s["not shown"][0] else None,
                        "hit_shown": round(s["shown"][3] / s["shown"][2], 3) if s["shown"][2] else None,
                        "hit_not_shown": round(s["not shown"][3] / s["not shown"][2], 3) if s["not shown"][2] else None,
                        "reads": s})
        out[c] = res
    summary = {}
    for c, (sn, sk, nn, nk, hsn, hsk, hnn, hnk) in tot.items():
        summary[c] = {"false_match_shown": round(sk / sn, 3) if sn else None, "false_match_not_shown": round(nk / nn, 3) if nn else None,
                      "hit_shown": round(hsk / hsn, 3) if hsn else None, "hit_not_shown": round(hnk / hnn, 3) if hnn else None,
                      "reads_non_matching_shown": sn, "reads_non_matching_not_shown": nn, "conditions": len(out[c])}
    dest = EXP / "WHY" / "literal"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps({"summary": summary, "conditions": out}, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

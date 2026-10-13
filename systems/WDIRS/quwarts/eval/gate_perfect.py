"""Gate 3: a perfect extraction must score 1.0 through each system's own path, for every realistic test question.

  docetl  the correct values of exactly the columns DocETL extracts for a question (C.design of that question), put
          through run_docetl_drift.build_db (its table building, numeric typing and physical-schema completion) and
          scored by the drift scorer, as DocETL's answers are.
  ours    the correct values of every column, written into the initial build's database layout, represented by
          core.represent.build with the field specs and the test workload (as the stream builds its views),
          completed, and scored as our system's answers are.
A question below 1.0 means the path itself, not the extraction, loses points. No model calls.

    QUWARTS_REALISTIC=v3 QUWARTS_W0_REALISTIC=1 PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama \
        QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.gate_perfect docetl|ours [corpus ...]
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from quwarts.core.router.comparator import is_null
from quwarts.eval import drift_live as D
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_tau import EXP, score_multi
from quwarts.eval.realistic_queries import register

CORPORA = ["cspaper", "art", "legal", "player", "med"]
REPO = EXP.parents[1]


def gold_value(gdoc: dict, t: str, d: str, a: str):
    g = gdoc.get(t, {}).get(d) or gdoc.get(t, {}).get(str(d).rsplit(".", 1)[0]) or gdoc.get(t, {}).get(f"{d}.txt") or {}
    v = g.get(a)
    return None if is_null(v) else v


def docetl_path(c: str, tmp: Path) -> dict:
    sys.path.insert(0, str(REPO / "systems" / "DocETL"))
    import run_docetl_drift as RD

    ctx = D.R.context(c)
    ids = register(ctx, c)
    gdoc = gold_by_doc(c)
    items = []
    for q in ids:
        sql = ctx.catalog[q]
        fields, reads = D.C.design(ctx.spec, {q: sql})
        tables, numeric = {}, {}
        for r in reads:
            if r.table not in ctx.names or not r.attributes:
                continue
            attrs = list(r.attributes)
            tables[r.table] = [{"doc_id": d, **{a.lower(): gold_value(gdoc, r.table, d, a) for a in attrs}} for d in ctx.names[r.table]]
            numeric[r.table] = {a.lower() for a in attrs if getattr(fields.get(f"{r.table}.{a}"), "value_type", "str") in ("int", "float")}
        db = RD.build_db(c, sql, tables, numeric, tmp / f"{RD.safe(q)}.db")
        items.append((q, db))
    return score_multi(c, items)


def ours_path(c: str, tmp: Path) -> dict:
    from quwarts.core.represent import Config, build
    from quwarts.eval.exp_cause import base_db, write_column
    from quwarts.eval.exp_context import fields_of

    ctx = D.R.context(c)
    ids = register(ctx, c)
    gdoc = gold_by_doc(c)
    fields = fields_of(c)
    master = tmp / "master.db"
    src = base_db(c, 100)
    con = sqlite3.connect(src)
    tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    con.close()
    import shutil

    shutil.copy2(src, master)
    mcon = sqlite3.connect(master)  # tables the initial build never read (e.g. owner): the stream creates them on demand
    for t in ctx.names:
        if t not in tabs:
            mcon.execute(f'CREATE TABLE "{t}" (doc_id TEXT)')
            mcon.executemany(f'INSERT INTO "{t}" (doc_id) VALUES (?)', [(str(d),) for d in ctx.names[t]])
            tabs.append(t)
    mcon.commit()
    mcon.close()
    cols = set(fields) | {f"{t}.{a}" for t, rows in gdoc.items() for r in rows.values() for a in r if a not in ("id", "pdf_filename")}
    for col in sorted(cols):  # every column of the correct rows (owner's are not in the field list but are read on demand)
        t, a = col.split(".", 1)
        if t not in tabs or t not in ctx.names:
            continue
        vals = {str(d): gold_value(gdoc, t, d, a) for d in ctx.names[t]}
        write_column(master, t, a, vals)
    view = tmp / "view.db"
    build(master, view, ctx.spec, fields, {q: ctx.catalog[q] for q in ids}, Config(t0=os.environ.get("GATE_RAWVIEW") != "1"))
    D.R.complete(c, view)
    return score_multi(c, [(q, view) for q in ids])


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    which, corpora = args[0], args[1:] or CORPORA
    out = {}
    for c in corpora:
        tmp = Path(tempfile.mkdtemp(dir="/scratch/general/vast/u1592362"))
        s = (docetl_path if which == "docetl" else ours_path)(c, tmp)
        below = {q: {"0%": v[0.0], "20%": v[0.2], "error": v.get("error")} for q, v in s.items() if min(v[0.0], v[0.2]) < 0.999}
        out[c] = {"questions": len(s), "below_1": below}
        print(c, which, "questions", len(s), "below 1.0:", len(below), json.dumps(below)[:1500], flush=True)
    dest = EXP / "WHY" / "realistic3"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"gate_perfect_{which}.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

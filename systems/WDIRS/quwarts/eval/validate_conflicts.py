"""Check a file of representation-conflict query groups against the correct data.

The correct database stores each value as the document states it, and each query does its own post-processing in SQL,
so the stored raw value answers every query. A conflict appears when a system stores a processed form of a column
instead (one item of a list, a merged spelling, a parsed number): the form one query wants can destroy what another
query needs. Each group declares, for one or more of its queries, that query's form of the shared column as an SQL
UPDATE (ALT). The check, on a copy of the correct data with the ALT applied (before the physical-schema completion):
the query the form is for still scores 1.0, and at least one other query of the group scores below 1.0.

File format (Query/Realistic/conflict/<corpus>.sql):
    -- GROUP G1: <one line: the shared column and what each query needs from it>
    -- TYPE: list-vs-one | fine-vs-coarse | join-spelling | number-vs-text
    -- COLUMN: table.column
    -- ALT G1a: UPDATE <table> SET <column> = ... ;   (one line: the form query G1a wants, stored in place of the raw value)
    -- G1a: <question>
    SELECT ...;
    -- G1b: <question>
    SELECT ...;
Every query is also put through validate_queries (runs, non-empty, no empty group keys or cells, realism rules,
scores 1.0 against itself).

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.validate_conflicts <corpus> <file.sql> [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tempfile
from pathlib import Path


def parse(path: Path) -> list[dict]:
    groups, cur, pending_q = [], None, None
    lines = path.read_text().splitlines()
    i = 0
    sql_buf: list[str] = []
    for line in lines + ["-- END"]:
        s = line.strip()
        if s.startswith("--"):
            if pending_q is not None and sql_buf:
                cur["queries"].append({**pending_q, "sql": " ".join(sql_buf).strip().rstrip(";").strip() + ";"})
                pending_q, sql_buf = None, []
            m = re.match(r"--\s*GROUP\s+(G\w+):\s*(.*)", s)
            if m:
                cur = {"id": m.group(1), "about": m.group(2), "type": None, "column": None, "alts": {}, "queries": []}
                groups.append(cur)
                continue
            if cur is None:
                continue
            m = re.match(r"--\s*TYPE:\s*(.*)", s)
            if m:
                cur["type"] = m.group(1).strip()
                continue
            m = re.match(r"--\s*COLUMN:\s*(\S+)", s)
            if m:
                cur["column"] = m.group(1).strip()
                continue
            m = re.match(r"--\s*ALT\s+(G\w+):\s*(.*)", s)
            if m:
                cur["alts"][m.group(1)] = m.group(2).strip().rstrip(";")
                continue
            m = re.match(r"--\s*(G\d+[a-z]):\s*(.*)", s)
            if m:
                pending_q = {"id": m.group(1), "question": m.group(2).strip()}
                continue
        elif s and pending_q is not None:
            sql_buf.append(s)
        i += 1
    return groups


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("file")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    from quwarts.eval import drift_live as D
    from quwarts.eval import validate_queries as V
    from quwarts.eval.exp_tau import score_multi
    from spp.config_grid import _build_in_memory_db

    c = a.corpus
    groups = parse(Path(a.file))
    tmp = Path(tempfile.mkdtemp(dir="/scratch/general/vast/u1592362"))
    # 1. each query through the standard checker
    flat = tmp / "queries.sql"
    alias = {f"QC{i + 1}": q["id"] for i, q in enumerate(q for g in groups for q in g["queries"])}  # the checker's id format
    back = {v: k for k, v in alias.items()}
    flat.write_text("\n\n".join(f"-- {back[q['id']]}: {q['question']}\n{q['sql']}" for g in groups for q in g["queries"]))
    vrep = tmp / "v.json"
    V.main([c, str(flat), "--role", "test", "--out", str(vrep)])
    vq = {alias[r["id"]]: r for r in json.loads(vrep.read_text())["queries"]}
    # 2. the forms: each ALT on a copy of the correct data
    ctx = D.R.context(c)
    gold, _ = D.R.Scorer(c).gold()
    g_mem = _build_in_memory_db(gold)
    report, bad = [], 0
    for g in groups:
        for q in g["queries"]:
            ctx.catalog[f"conflict:{c}#{q['id']}"] = q["sql"]
        res = {"group": g["id"], "about": g["about"], "type": g["type"], "column": g["column"], "problems": [],
               "queries": {q["id"]: {"question": q["question"], "checker_ok": vq.get(q["id"], {}).get("ok"),
                                     "checker_problems": vq.get(q["id"], {}).get("problems"),
                                     "result_rows": vq.get(q["id"], {}).get("result_rows")} for q in g["queries"]},
               "forms": {}}
        if len(g["queries"]) < 2:
            res["problems"].append("a group needs at least two queries")
        if g["type"] not in ("list-vs-one", "fine-vs-coarse", "join-spelling", "number-vs-text"):
            res["problems"].append(f"unknown TYPE {g['type']!r}")
        if not g["alts"]:
            res["problems"].append("no ALT form declared")
        t, col = (g["column"] or ".").split(".", 1)
        for owner, upd in g["alts"].items():
            m = re.match(r"UPDATE\s+\"?(\w+)\"?\s+SET\s+\"?(\w+)\"?\s*=", upd, re.I)
            if not m or m.group(1).lower() != t.lower() or m.group(2).lower() != col.lower():
                res["problems"].append(f"ALT {owner} must be one UPDATE of the group's COLUMN {g['column']}")
                continue
            db = tmp / f"{g['id']}_{owner}.db"
            if db.exists():
                db.unlink()
            dst = sqlite3.connect(db)
            g_mem.backup(dst)
            try:
                dst.execute(upd)
                dst.commit()
                changed = dst.total_changes
            except sqlite3.Error as exc:
                res["problems"].append(f"ALT {owner} fails: {exc}")
                dst.close()
                continue
            dst.close()
            D.R.complete(c, db)
            sc = score_multi(c, [(f"conflict:{c}#{q['id']}", db) for q in g["queries"]])
            scores = {q["id"]: {"0%": sc[f"conflict:{c}#{q['id']}"].get(0.0), "20%": sc[f"conflict:{c}#{q['id']}"].get(0.2)} for q in g["queries"]}
            res["forms"][owner] = {"update": upd, "rows_changed": changed, "scores": scores}
            if owner not in scores:
                res["problems"].append(f"ALT {owner} names no query of the group")
                continue
            if (scores[owner]["0%"] or 0) < 0.999:
                res["problems"].append(f"the form for {owner} breaks {owner} itself (scores {scores[owner]['0%']} at 0%)")
            if not any((v["0%"] or 0) < 0.999 for k, v in scores.items() if k != owner):
                res["problems"].append(f"the form for {owner} breaks no other query of the group (no conflict)")
            if changed == 0:
                res["problems"].append(f"ALT {owner} changes no row")
        for qid, r in res["queries"].items():
            if not r["checker_ok"]:
                res["problems"].append(f"{qid} fails the query checker: {r['checker_problems']}")
        bad += bool(res["problems"])
        report.append(res)
    summary = {"corpus": c, "groups": len(groups), "queries": sum(len(g["queries"]) for g in groups), "groups_with_problems": bad,
               "by_type": {t: sum(g["type"] == t for g in groups) for t in {g["type"] for g in groups}}}
    text = json.dumps({"summary": summary, "groups": report}, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text)
        print("REPORT", json.dumps(summary))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

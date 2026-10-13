"""Results of the decisive tests (DocETL arms, our reader arms), per query: answer vs correct, dropped documents,
false/true matches of each WHERE constant, scores at 0/5/10/20%. Reads results/docetl_arms and results/reader_arms.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_arms_report
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from quwarts.core.router.comparator import is_null
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_docetl_variation import catalogs, safe
from quwarts.eval.exp_literal import conditions, satisfies
from quwarts.eval.exp_tau import EXP

REPO = EXP.parents[1]
ASRUN = {"docetl": REPO / "results" / "docetl_realistic_ollama", "docetl-drift": REPO / "results" / "docetl_drift_ollama"}


def arm_dirs():
    for sysname, base in (("docetl", REPO / "results" / "docetl_arms"), ("ours", REPO / "results" / "reader_arms")):
        if base.exists():
            for d in sorted(base.iterdir()):
                if d.is_dir():
                    yield sysname, d.name, d


def answer(db: Path, sql: str):
    try:
        con = sqlite3.connect(db)
        rows = con.execute(sql).fetchall()
        con.close()
        return rows[0][0] if len(rows) == 1 and len(rows[0]) == 1 else f"{len(rows)} rows"
    except Exception as exc:  # noqa: BLE001
        return f"error {exc}"[:60]


def matches(db: Path, sql: str, c: str, gdoc: dict):
    out = {}
    con = sqlite3.connect(db)
    for col, op, lit in conditions(sql):
        t, a = col.split(".", 1)
        try:
            rows = con.execute(f'SELECT doc_id, "{a.lower()}" FROM "{t}"').fetchall()
        except sqlite3.Error:
            continue
        g = {str(d).rsplit(".", 1)[0]: r for d, r in gdoc.get(t, {}).items()}
        fm = nm = tm = pm = 0
        for d, v in rows:
            gv = next((x for k, x in (g.get(str(d).rsplit(".", 1)[0]) or {}).items() if k.lower() == a.lower()), None)
            if is_null(gv):
                continue
            if satisfies(gv, op, lit):
                pm += 1
                tm += satisfies(v, op, lit)
            else:
                nm += 1
                fm += satisfies(v, op, lit)
        out[f"{col} {op} {lit}"] = {"false_match": f"{fm}/{nm}", "true_match": f"{tm}/{pm}"}
    con.close()
    return out


def main() -> int:
    rows = []
    gold_cache, cat_cache = {}, {}
    from quwarts.eval import drift_live as D

    for sysname, arm, d in arm_dirs():
        for cdir in sorted(x for x in d.iterdir() if x.is_dir()):
            c = cdir.name
            per = cdir / "per_query.json"
            if not per.exists():
                continue
            if c not in gold_cache:
                gold_cache[c], cat_cache[c] = gold_by_doc(c), catalogs(c)
                gs, _ = D.R.Scorer(c).gold()
                from spp.config_grid import _build_in_memory_db

                gold_cache[c + ":db"] = _build_in_memory_db(gs)
            for q, v in json.loads(per.read_text()).items():
                sql = cat_cache[c][q]
                db = cdir / "db" / f"{safe(q)}.db"
                try:
                    correct = gold_cache[c + ":db"].execute(sql).fetchall()
                    correct = correct[0][0] if len(correct) == 1 and len(correct[0]) == 1 else f"{len(correct)} rows"
                except Exception:  # noqa: BLE001
                    correct = None
                rows.append({"system": sysname, "arm": arm, "corpus": c, "query": q, "score": v["score"],
                             "dropped": v.get("failed_docs"), "answer": answer(db, sql), "correct": correct,
                             "constants": matches(db, sql, c, gold_cache[c]),
                             "tokens": v.get("prompt_tokens", v.get("input_tokens", 0)) + v.get("completion_tokens", v.get("output_tokens", 0))})
    dest = EXP / "WHY" / "arms"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "results.json").write_text(json.dumps(rows, indent=1, default=str))
    for r in sorted(rows, key=lambda r: (r["corpus"], r["query"], r["system"], r["arm"])):
        print(f"{r['corpus']:6s} {r['query'][:34]:34s} {r['system']:6s} {r['arm']:24s} @20 {r['score']['20%']:.3f} @0 {r['score']['0%']:.3f} "
              f"drop {str(r['dropped']):4s} ans {str(r['answer'])[:10]:10s} correct {str(r['correct'])[:10]:10s} {json.dumps(r['constants'])[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

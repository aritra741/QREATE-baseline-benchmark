"""Per-document filter matches for every setup of the shared-read ladder (a measure that exact single-number scoring
does not hide): for each distinct (column, operator, constant) in the realistic queries' WHERE clauses, the share of
documents a setup counts wrongly (correct value fails the filter) and rightly (correct value passes).

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_ingredients_filters med player
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_docetl_variation import catalogs, safe
from quwarts.eval.exp_literal import conditions, satisfies
from quwarts.eval.exp_tau import EXP

REPO = EXP.parents[1]
QV = Path("/scratch/general/vast/u1592362/quwarts_exp/RW-qviews/RW-norereads-V3")


def setups(c: str) -> dict[str, callable]:
    recs = [json.loads(x) for x in (EXP / "RW-norereads-V3" / "live" / c / "streams" / "fixed4-realistic_100.jsonl").read_text().splitlines() if x.strip()]
    pos = {r["qid"]: r["pos"] for r in recs}
    return {
        "DocETL per query, as run": lambda q: REPO / "results" / "docetl_realistic_ollama" / c / "db" / f"{safe(q)}.db",
        "L0 DocETL shared, harness wording": lambda q: REPO / "results" / "docetl_arms" / "shared" / c / "db" / f"{safe(q)}.db",
        "L1 + our wording": lambda q: REPO / "results" / "docetl_arms" / "shared_ourwords" / c / "db" / f"{safe(q)}.db",
        "L2 + split documents": lambda q: REPO / "results" / "docetl_arms" / "shared_ourwords_chunked" / c / "db" / f"{safe(q)}.db",
        "L3 our reader, as read": lambda q: REPO / "results" / "shared_reader" / "base" / c / "asread" / "db" / f"{safe(q)}.db",
        "L4 + commit": lambda q: REPO / "results" / "shared_reader" / "base" / c / "committed" / "db" / f"{safe(q)}.db",
        "W1 no use lines (committed)": lambda q: REPO / "results" / "shared_reader" / "nousage" / c / "committed" / "db" / f"{safe(q)}.db",
        "W2 every column (committed)": lambda q: REPO / "results" / "shared_reader" / "allcols" / c / "committed" / "db" / f"{safe(q)}.db",
        "our full system, as run": lambda q: QV / c / "fixed4-realistic_100" / f"{pos[q]:04d}.db" if q in pos else Path("/nonexistent"),
    }


def main(argv=None) -> int:
    out = {}
    for c in (argv or sys.argv[1:]):
        cat = catalogs(c)
        qs = sorted(json.loads((EXP / "WHY" / "swap" / f"realistic_{c}.json").read_text())[c]["per_query"])
        gold = gold_by_doc(c)
        conds = {}
        for q in qs:
            for col, op, lit in conditions(cat[q]):
                conds.setdefault((col, op, lit), q)
        res = {}
        for name, path in setups(c).items():
            wrong = wrong_n = right = right_n = 0
            done = True
            for (col, op, lit), q in conds.items():
                p = path(q)
                if not p.exists():
                    done = False
                    break
                t, x = col.split(".", 1)
                try:
                    got = {str(d).rsplit(".", 1)[0]: v for d, v in sqlite3.connect(p).execute(f'SELECT doc_id, "{x}" FROM "{t}"')}
                except sqlite3.Error:
                    continue
                for d, row in gold.get(t, {}).items():
                    key = str(d).rsplit(".", 1)[0]
                    truth = satisfies(row.get(x), op, lit)
                    said = satisfies(got.get(key), op, lit)
                    if truth:
                        right_n += 1
                        right += said
                    else:
                        wrong_n += 1
                        wrong += said
            res[name] = None if not done else {"wrongly counted": f"{wrong}/{wrong_n}", "rightly counted": f"{right}/{right_n}",
                                               "wrong_rate": round(wrong / wrong_n, 3) if wrong_n else None,
                                               "right_rate": round(right / right_n, 3) if right_n else None}
        out[c] = {"filters": len(conds), "setups": res}
        print(f"\n{c}: {len(conds)} distinct filters")
        for k, v in res.items():
            print(f"  {k:36s} " + ("(not finished)" if v is None else f"wrong {v['wrongly counted']:>9s} ({v['wrong_rate']:.3f})   right {v['rightly counted']:>8s} ({v['right_rate']:.3f})"))
    dest = EXP / "WHY" / "ingredients"
    dest.mkdir(parents=True, exist_ok=True)
    prev = json.loads((dest / "filters.json").read_text()) if (dest / "filters.json").exists() else {}
    prev.update(out)
    (dest / "filters.json").write_text(json.dumps(prev, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

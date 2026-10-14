"""Counterfactual: DocETL's "unknown" read as an absence. DocETL's prompt asks for -1 (numbers) or "" (text) when a
field is unknown, and its tables store those as NULL. For a count or a yes/no question the true answer is often an
absence (0, "No"), which the model reports as unknown. Here, in the columns DocETL extracted for a query, a NULL
number becomes 0 and a NULL yes/no becomes "No"; nothing else changes. Measured: per-answer accuracy of those columns
(exact, against the correct data) and the query score at 0/5/10/20% tolerance, before and after. No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_docetl_impute <docetl root name> [corpus ...]
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import statistics as S
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from quwarts.core.router.comparator import is_null
from quwarts.eval import drift_live as D
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_context import fields_of
from quwarts.eval.exp_docetl_variation import catalogs, safe
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_tau import EXP, TAUS, score_multi
from quwarts.eval.exp_transfer import kind_of

CORPORA = ["cspaper", "player", "art", "med", "legal"]
ABSENCE = {"number": 0, "yes/no": "No"}


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    root_name, corpora = args[0], args[1:] or CORPORA
    out = {}
    for c in corpora:
        base = EXP.parent / root_name / c
        per = json.loads((base / "per_query.json").read_text()) if (base / "per_query.json").exists() else {}
        if not per:
            continue
        ctx = D.R.context(c)
        cat = catalogs(c)
        for q in per:
            if cat.get(q):
                ctx.catalog.setdefault(q, cat[q])
        fields = fields_of(c)
        gdoc = gold_by_doc(c)
        tmp = Path(tempfile.mkdtemp(dir="/scratch/general/vast/u1592362"))
        before, after, cells = [], [], defaultdict(lambda: [0, 0, 0])  # kind -> [answers, right before, right after]
        for q in per:
            db = base / "db" / f"{safe(q)}.db"
            if not db.exists() or not cat.get(q):
                continue
            imp = tmp / db.name
            shutil.copy2(db, imp)
            con = sqlite3.connect(imp)
            for tdir in (base / safe(q)).glob("table_*"):
                t = tdir.name[len("table_"):]
                stats = json.loads((tdir / "stats.json").read_text()) if (tdir / "stats.json").exists() else {}
                for a in (stats.get("fields") or []):
                    k = kind_of(fields[f"{t}.{a}"]) if f"{t}.{a}" in fields else None
                    if k not in ABSENCE:
                        continue
                    rows = con.execute(f'SELECT doc_id, "{a.lower()}" FROM "{t}"').fetchall()
                    for d, v in rows:
                        g = (gdoc.get(t, {}).get(str(d)) or gdoc.get(t, {}).get(str(d).rsplit(".", 1)[0]) or {}).get(a)
                        if is_null(g):
                            continue
                        new = ABSENCE[k] if v is None else v
                        cells[k][0] += 1
                        cells[k][1] += (v is not None) and correct(v, g, 0.0)
                        cells[k][2] += correct(new, g, 0.0)
                    con.execute(f'UPDATE "{t}" SET "{a.lower()}" = ? WHERE "{a.lower()}" IS NULL', (ABSENCE[k],))
            con.commit()
            con.close()
            before.append((q, db))
            after.append((q, imp))
        sb, sa = score_multi(c, before), score_multi(c, after)
        qs = [q for q, _ in before]
        changed = [q for q in qs if abs(sa[q][0.2] - sb[q][0.2]) > 1e-9]
        out[c] = {"queries": len(qs), "queries_whose_score_changed_at_20": len(changed), "changed_queries": {q: [round(sb[q][0.2], 3), round(sa[q][0.2], 3)] for q in changed},
                  "score_before": {f"{t:.0%}": round(S.mean(sb[q][t] for q in qs), 4) for t in TAUS},
                  "score_after": {f"{t:.0%}": round(S.mean(sa[q][t] for q in qs), 4) for t in TAUS},
                  "answer_accuracy": {k: {"answers": n, "before": round(b / n, 3), "after": round(a / n, 3)} for k, (n, b, a) in cells.items() if n}}
        print(c, json.dumps(out[c]), flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
    dest = EXP / "WHY" / "docetl_impute"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{root_name}.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""One representation per query vs one shared representation (no model calls).

Our system stores one raw extraction (master.db) and, after each query, rebuilds ONE view for every query seen so far:
the representation layer gives each column a single target from all those queries' uses (represent.build). A column
that two queries need in different forms (a list vs one value, a label vs the stated text, one spelling per join
partner) gets one compromise. Here, from the same raw table (the realistic v3 run kept each query's table, built
without representation, so it is the raw extraction at that point), each query is scored on: raw (no representation),
shared (the view for all queries seen so far, as the system would build it with the layer on), and own (a view built
for that query alone). Also per column: whether the shared target differs from the query's own target.

    QUWARTS_REALISTIC=v3 PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_perquery_view [corpus ...]
"""

from __future__ import annotations

import json
import shutil
import statistics as S
import sys
import tempfile
from pathlib import Path

from quwarts.core.represent import Config, build
from quwarts.eval import drift_live as D
from quwarts.eval.exp_context import fields_of
from quwarts.eval.exp_tau import EXP, TAUS, score_multi
from quwarts.eval.realistic_queries import register

QV = Path("/scratch/general/vast/u1592362/quwarts_exp/RW-qviews/RW3-V3")


def main(argv=None) -> int:
    corpora = (argv or sys.argv[1:]) or ["player", "art", "cspaper"]
    out = {}
    for c in corpora:
        ctx = D.R.context(c)
        register(ctx, c)
        fields = fields_of(c)
        recs = [json.loads(x) for x in (EXP / "RW3-V3" / "live" / c / "streams" / "fixed4-realistic_100.jsonl").read_text().splitlines() if x.strip()]
        order = [r["qid"] for r in sorted(recs, key=lambda r: r["pos"])]
        tmp = Path(tempfile.mkdtemp(dir="/scratch/general/vast/u1592362"))
        items = {"raw": [], "shared": [], "own": []}
        changed = {}
        for r in recs:
            q, pos = r["qid"], r["pos"]
            src = QV / c / "fixed4-realistic_100" / f"{pos:04d}.db"
            if not src.exists():
                continue
            seen = {x: ctx.catalog[x] for x in order[: pos + 1]}
            raw = tmp / f"raw_{pos}.db"
            shutil.copy2(src, raw)
            m_shared = build(raw, tmp / f"shared_{pos}.db", ctx.spec, fields, seen, Config())
            m_own = build(raw, tmp / f"own_{pos}.db", ctx.spec, fields, {q: ctx.catalog[q]}, Config())
            for k in ("raw", "shared", "own"):
                p = tmp / f"{k}_{pos}.db"
                D.R.complete(c, p)
                items[k].append((q, p))
            changed[q] = sorted(set(m_own["columns"]) ^ set(m_shared["columns"])) if isinstance(m_own.get("columns"), dict) else None
        sc = {k: score_multi(c, v) for k, v in items.items()}
        qs = [q for q, _ in items["raw"]]
        res = {"queries": len(qs), "mean": {k: {f"{t:.0%}": round(S.mean(sc[k][q][t] for q in qs), 4) for t in TAUS} for k in sc},
               "own_vs_shared_at_20": {"better": sum(sc["own"][q][0.2] > sc["shared"][q][0.2] + 1e-9 for q in qs),
                                       "worse": sum(sc["own"][q][0.2] < sc["shared"][q][0.2] - 1e-9 for q in qs)},
               "per_query": {q: {k: round(sc[k][q][0.2], 3) for k in sc} for q in qs}}
        out[c] = res
        print(c, json.dumps({k: v for k, v in res.items() if k != "per_query"}), flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
    dest = EXP / "WHY" / "perquery_view"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{'_'.join(corpora)}.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

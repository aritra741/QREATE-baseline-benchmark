"""Our full system's answers on the representation-conflict queries (the live stream run with QUWARTS_REALISTIC=conflict),
rescored against the answer keys: each query's kept view, completed, scored by score_multi with REFERENCE. Tokens: the
initial build plus the stream. Output: results/conflict_full/<run>/<corpus>/per_query.json (read by exp_conflict_report).

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_conflict_full RW-haiku-conflict [corpus ...]
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from quwarts.eval import drift_live as D
from quwarts.eval.exp_tau import EXP, TAUS, score_multi
from quwarts.eval.validate_conflicts import load

QV = Path("/scratch/general/vast/u1592362/quwarts_exp/RW-qviews")


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    run, corpora = args[0], args[1:] or ["art", "med", "player", "cspaper"]
    for c in corpora:
        ctx = D.R.context(c)
        for q, s in load(c).items():
            ctx.catalog[q] = s
        live = EXP / run / "live" / c
        recs = [json.loads(x) for x in (live / "streams" / "fixed4-realistic_100.jsonl").read_text().splitlines() if x.strip()]
        tmp = Path(tempfile.mkdtemp(dir="/scratch/general/vast/u1592362"))
        items = []
        for r in recs:
            src = QV / run / c / "fixed4-realistic_100" / f"{r['pos']:04d}.db"
            if src.exists():
                dst = tmp / src.name
                shutil.copy2(src, dst)
                D.R.complete(c, dst)
                items.append((r["qid"], dst))
        sc = score_multi(c, items)
        b = json.loads((live / "build.json").read_text())
        out = {"per_query": {q: {f"{t:.0%}": sc[q].get(t) for t in TAUS} for q in sc},
               "tokens": b.get("tokens", 0) + sum(r.get("input_tokens", 0) + r.get("output_tokens", 0) for r in recs),
               "stream_calls": sum(r.get("calls", 0) for r in recs), "build_calls": b.get("calls")}
        dest = EXP.parents[1] / "results" / "conflict_full" / run / c
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "per_query.json").write_text(json.dumps(out, indent=1))
        print(c, f"mean@20 {sum(v['20%'] for v in out['per_query'].values()) / len(out['per_query']):.3f}", f"tokens {out['tokens'] / 1e6:.2f}M", flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

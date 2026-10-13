"""What the large model's second looks change in query results, paired within a run: each run's final served table
scored with its second looks and with the small model's answers left in those cells, at 0/5/10/20% tolerance.
Lists, per corpus, the second-look columns, how many cells changed, and which test queries moved.  No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_ITEMFILTER_EMPTY=1 \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_reread_effect <scratch dir> [corpus ...]
"""

from __future__ import annotations

import json
import statistics as S
import sys
from collections import Counter
from pathlib import Path

from quwarts.eval.exp_tau import EXP, TAUS, score_multi, served_view

RUNS = ["V3", "V3-rep1", "V3-rep2"]


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    sp = Path(args[0])
    out = {}
    for c in args[1:] or ["cspaper", "player", "art", "med", "legal"]:
        tests = list(dict.fromkeys(json.loads((EXP.parent / "drift_live_ollama" / c / "fixed4_attribute_pool_design.json").read_text())["test"]))
        res = {"runs": []}
        for run in RUNS:
            rep = EXP / run / "live" / c / "repair_reads.jsonl"
            if not rep.exists():
                continue
            looks = Counter(f"{r['table']}.{r['attribute']}" for r in map(json.loads, rep.read_text().splitlines()) if r.get("purpose") == "second_look")
            with_ = score_multi(c, [(q, served_view(c, run, sp / "fv" / f"{c}_{run}")) for q in tests])
            without = score_multi(c, [(q, served_view(c, run, sp / "fv" / f"{c}_{run}_nolook", second_looks=False)) for q in tests])
            moved = {q: round(with_[q][0.2] - without[q][0.2], 4) for q in tests if abs(with_[q][0.2] - without[q][0.2]) > 1e-9}
            res["runs"].append({"run": run, "second_looks": dict(looks),
                                "with": {f"{t:.0%}": round(S.mean(with_[q][t] for q in tests), 4) for t in TAUS},
                                "without": {f"{t:.0%}": round(S.mean(without[q][t] for q in tests), 4) for t in TAUS},
                                "queries_moved_at_20": moved})
            print(c, run, json.dumps({k: v for k, v in res["runs"][-1].items() if k != "queries_moved_at_20"}), "moved", len(moved), flush=True)
        out[c] = res
        dest = EXP / "WHY" / "reread_effect"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{c}.json").write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

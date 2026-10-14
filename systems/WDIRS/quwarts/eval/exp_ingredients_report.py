"""What helps with a small model, and does knowing the workload help: the shared-read ladder on Qwen.

Every rung reads each table once with the union of the realistic queries' columns and answers all of them from that
table (no representation layer):
  L0  DocETL, harness wording (tool call, whole document)            results/docetl_arms/shared/<c>
  L1  + our wording                                                   results/docetl_arms/shared_ourwords/<c>
  L2  + documents split into our pieces                               results/docetl_arms/shared_ourwords_chunked/<c>
  L3  our reader (plain JSON, a row kept whatever the reply), as read results/shared_reader/base/<c> (asread)
  L4  + our commit step                                               results/shared_reader/base/<c> (committed)
Workload: W1 = L4 without use lines (shared_reader/nousage), W2 = L4 reading every schema column (shared_reader/allcols).
Ends: DocETL per query as run and our full system as run (WHY/swap/realistic_<c>.json, by_tau).

    PYTHONPATH=systems/WDIRS ~/venvs/quwarts/bin/python -m quwarts.eval.exp_ingredients_report
"""

from __future__ import annotations

import json
import statistics as S
from pathlib import Path

from quwarts.eval.exp_tau import EXP

REPO = EXP.parents[1]
T = ["0%", "5%", "10%", "20%"]
CORPORA = ["player", "med", "art", "cspaper"]  # court cases dropped for time (2026-10-14)


def docetl(arm: str, c: str) -> dict | None:
    p = REPO / "results" / "docetl_arms" / arm / c / "per_query.json"
    if not p.exists():
        return None
    per = json.loads(p.read_text())
    qs = sorted(json.loads((EXP / "WHY" / "swap" / f"realistic_{c}.json").read_text())[c]["per_query"])
    if not all(q in per for q in qs):
        return None
    tok = 0
    for f in (REPO / "results" / "docetl_arms" / arm / c / "_shared").glob("table_*/stats.json"):
        s = json.loads(f.read_text())
        tok += s["prompt_tokens"] + s["completion_tokens"]
    failed = sum(len(json.loads(f.read_text())["failed"]) for f in (REPO / "results" / "docetl_arms" / arm / c / "_shared").glob("table_*/stats.json"))
    return {"mean": {t: round(S.mean(per[q]["score"][t] for q in qs), 4) for t in T}, "tokens_M": round(tok / 1e6, 2), "lost_documents": failed}


def ours(variant: str, store: str, c: str) -> dict | None:
    p = REPO / "results" / "shared_reader" / variant / c / "per_query.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return {"mean": d["mean"][store], "tokens_M": round((d["input_tokens"] + d["output_tokens"]) / 1e6, 2)}


def main() -> int:
    out = {}
    for c in CORPORA:
        sw = json.loads((EXP / "WHY" / "swap" / f"realistic_{c}.json").read_text())[c]["by_tau"]
        r = {"DocETL per query, as run": {"mean": {t: sw[t]["docetl"] for t in T}},
             "L0 DocETL shared read, harness wording": docetl("shared", c),
             "L1 + our wording": docetl("shared_ourwords", c),
             "L2 + split documents": docetl("shared_ourwords_chunked", c),
             "L3 our reader, values as read": ours("base", "asread", c),
             "L4 + our commit step": ours("base", "committed", c),
             "W1 L4 without workload use lines": ours("nousage", "committed", c),
             "W2 L4 reading every schema column": ours("allcols", "committed", c),
             "W1 as read": ours("nousage", "asread", c),
             "W2 as read": ours("allcols", "asread", c),
             "our full system, as run": {"mean": {t: sw[t]["ours"] for t in T}}}
        out[c] = r
    dest = EXP / "WHY" / "ingredients"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    for c, r in out.items():
        print(f"\n{c}")
        for k, v in r.items():
            if v is None:
                print(f"  {k:40s} (not finished)")
                continue
            extra = f"  {v['tokens_M']}M tok" if "tokens_M" in v else ""
            extra += f"  lost {v['lost_documents']}" if "lost_documents" in v else ""
            print(f"  {k:40s} " + " ".join(f"{t}:{v['mean'][t]:.3f}" for t in T) + extra)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

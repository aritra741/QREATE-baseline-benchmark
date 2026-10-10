"""The catalogue planner's evaluation (SYSTEM_PLAN.md).

    python -m quwarts.eval.exp_v2 labels      # ten labelled cells per new column per corpus (the repair component's input)
    python -m quwarts.eval.exp_v2 analyze     # v2 against the recorded system: scores, tokens, the catalogue, ablations
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as S
from pathlib import Path

from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPO, gold_by_doc, is_null

CORPORA = ["cspaper", "player", "art", "med", "legal"]
LIVE = REPO / "results" / "drift_live_ollama"
OUT = EXP / "V2"
LABELLED = 10


def labels() -> None:
    """For every new column of the drift design, ten documents with a gold value, drawn with a fixed seed: the
    labelled sample the repair component estimates a column's repair rate from (a validation set a user would label)."""
    (OUT / "labels").mkdir(parents=True, exist_ok=True)
    for c in CORPORA:
        ctx = R.context(c)
        gold = gold_by_doc(c)
        design = json.loads((LIVE / c / "fixed4_attribute_pool_design.json").read_text())
        out = {}
        for col in design["new_columns"]:
            t, a = col.split(".", 1)
            docs = [d for d in sorted(ctx.names[t]) if a in gold.get(t, {}).get(d, {}) or a in gold.get(t, {}).get(d.rsplit(".", 1)[0], {})]
            rng = random.Random(f"{c}:{col}:labels")
            rng.shuffle(docs)
            chosen = docs[:LABELLED]
            out[col] = {d: (gold[t].get(d) or gold[t].get(d.rsplit(".", 1)[0]))[a] for d in chosen}
        (OUT / "labels" / f"{c}.json").write_text(json.dumps(out, indent=1, default=str))
        print(f"{c}: {len(out)} columns, {sum(len(v) for v in out.values())} labelled cells")


def stream_stats(f: Path) -> dict | None:
    if not f.exists():
        return None
    rs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    rep = [r.get("planner", {}) for r in rs]
    repair_tokens = 0
    for p in rep:
        for t, ti in p.items():
            for k, v in (ti.get("repair") or {}).items():
                repair_tokens += v.get("tokens", 0) or 0
    return {"score": round(S.mean(r["benchmark"] for r in rs), 4), "queries": len(rs),
            "tokens": sum(r["input_tokens"] + r["output_tokens"] for r in rs), "repair_tokens": repair_tokens,
            "patches": sum(r["action"] == "patch" for r in rs)}


def analyze() -> dict:
    out = {"runs": {}}
    variants = {"recorded": LIVE, "v2": OUT / "live"}
    for p in sorted(OUT.glob("ablate-*")) + sorted(OUT.glob("rep*")):
        variants[p.name] = p / "live"
    for c in CORPORA:
        row = {}
        for name, root in variants.items():
            for key in ("fixed4-attribute_pool_100", "fixed4-attribute_pool_0", "fixed4-attribute_pool_50",
                        "fixed4b025-attribute_pool_100", "fixed4b050-attribute_pool_100"):
                st = stream_stats(root / c / "streams" / f"{key}.jsonl")
                if st:
                    row.setdefault(name, {})[key] = st
        out["runs"][c] = row
        plan = OUT / "live" / c / "state" / "fixed4-attribute_pool_100.json"
        if plan.exists():
            st = json.loads(plan.read_text()).get("frozen", {})
            out.setdefault("catalogue", {})[c] = {t: {"groups": v["groups"], "probe_calls": v["probe"]["calls"],
                                                      "columns": {k: {kk: vv for kk, vv in x.items() if kk != "column"} for k, x in v["stats"].items()}}
                                                  for t, v in st.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["labels", "analyze"])
    a = ap.parse_args(argv)
    if a.what == "labels":
        labels()
    else:
        o = analyze()
        for c, row in o["runs"].items():
            for name, keys in row.items():
                for k, st in keys.items():
                    print(f"{c:8s} {name:18s} {k:32s} score={st['score']} tokens={st['tokens'] / 1e6:.2f}M repair={st['repair_tokens'] / 1e6:.2f}M queries={st['queries']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

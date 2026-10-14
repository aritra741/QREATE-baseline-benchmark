"""The representation-conflict benchmark: every arm side by side (no model calls).

Arms: DocETL per query (re-reads with the query's SQL in the prompt), DocETL shared (one read per table, no SQL,
every query answered from it), ours as committed today (raw / one shared view / one view per query), ours with
values stored as read (same three), and the same paths on perfect values (the ceiling of each path).
Per collection: mean score at 0/5/10/20%, how many groups have BOTH questions right at 20% (the conflict resolved),
and tokens. Output: results/experiments/WHY/conflict/summary.json

    PYTHONPATH=systems/WDIRS ~/venvs/quwarts/bin/python -m quwarts.eval.exp_conflict_report
"""

from __future__ import annotations

import glob
import json
import statistics as S
from collections import defaultdict
from pathlib import Path

from quwarts.eval.exp_tau import EXP
from quwarts.eval.validate_conflicts import parse

REPO = EXP.parents[1]
C = ["art", "med", "player", "cspaper"]
T = ["0%", "5%", "10%", "20%"]


def main() -> int:
    out = {}
    for c in C:
        groups = parse(REPO / "Query" / "Realistic" / "conflict" / f"{c}.sql")
        qids = [f"conflict:{c}#{q['id']}" for g in groups for q in g["queries"]]
        arms, tokens = {}, {}
        for arm in ("strfix", "shared"):
            p = REPO / "results" / "docetl_arms" / f"{arm}-claude-haiku-5-5" / c / "per_query.json"
            if p.exists():
                d = json.loads(p.read_text())
                name = "DocETL per query" if arm == "strfix" else "DocETL shared read"
                arms[name] = {q: d[q]["score"] for q in qids if q in d}
                if arm == "strfix":
                    tokens[name] = sum(d[q]["prompt_tokens"] + d[q]["completion_tokens"] for q in qids if q in d)
                else:
                    tokens[name] = sum(json.loads(Path(f).read_text())["prompt_tokens"] + json.loads(Path(f).read_text())["completion_tokens"]
                                       for f in glob.glob(str(p.parent / "_shared" / "table_*" / "stats.json")))
        p = REPO / "results" / "conflict_full" / "RW-haiku-conflict" / c / "per_query.json"
        if p.exists():  # our full system (build, planner, representation layer, reuse) on the conflict stream, Haiku reading
            d = json.loads(p.read_text())
            arms["ours, full system (one shared view, as run)"] = {q: d["per_query"][q] for q in qids if q in d["per_query"]}
            tokens["ours, full system (build + stream)"] = d["tokens"]
        for src, label in (("claude-haiku-5-5-claude-haiku-5-5", "ours, stored as read, view agent per query"),
                           ("gold-claude-haiku-5-5", "ours on perfect values, stored as read, view agent per query")):
            p = REPO / "results" / "conflict_agent" / src / c / "per_query.json"
            if p.exists():
                d = json.loads(p.read_text())
                arms[label] = {q: d["per_query"][q]["score"] for q in qids if q in d["per_query"]}
                tokens[label + " (agent only)"] = d["agent_tokens"]["input"] + d["agent_tokens"]["output"]
        for src, label in (("claude-haiku-5-5", "ours"), ("gold", "ours on perfect values")):
            for store, sl in (("", "as committed"), ("asread", "stored as read")):
                p = REPO / "results" / "conflict_ours" / src / c / store / "per_query.json"
                if not p.exists():
                    continue
                d = json.loads(p.read_text())
                for k, kl in (("raw", "no view"), ("shared", "one shared view"), ("perquery", "one view per query")):
                    arms[f"{label}, {sl}, {kl}"] = {q: d["per_query"][q][k] for q in qids if q in d["per_query"]}
                if src != "gold" and store == "":
                    tokens[f"{label} (one read, all views)"] = d["input_tokens"] + d["output_tokens"]
        res = {}
        for name, sc in arms.items():
            if len(sc) < len(qids):
                res[name] = {"incomplete": f"{len(sc)}/{len(qids)}"}
                continue
            both = sum(all((sc[f"conflict:{c}#{q['id']}"].get("20%") or 0) >= 0.999 for q in g["queries"]) for g in groups)
            res[name] = {"mean": {t: round(S.mean(sc[q].get(t) or 0 for q in qids), 3) for t in T}, "groups_resolved_at_20": f"{both}/{len(groups)}"}
        out[c] = {"queries": len(qids), "arms": res, "tokens": tokens}
    dest = EXP / "WHY" / "conflict"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    for c, r in out.items():
        print(f"\n{c} ({r['queries']} queries)  tokens: " + ", ".join(f"{k} {v / 1e6:.2f}M" for k, v in r["tokens"].items()))
        for name, v in r["arms"].items():
            if "mean" in v:
                print(f"   {name:58s} " + " ".join(f"{t}:{v['mean'][t]:.3f}" for t in T) + f"  both right {v['groups_resolved_at_20']}")
            else:
                print(f"   {name:58s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

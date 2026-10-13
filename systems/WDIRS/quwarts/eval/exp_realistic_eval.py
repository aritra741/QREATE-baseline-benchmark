"""Scores on the realistic workload (Query/Realistic) at 0, 5, 10 and 20% tolerance, per query and per collection.

Our system: each query is scored on the view it was answered from (kept by QUWARTS_KEEP_QUERY_VIEWS, one database per
stream position), so the scores are exact, not reconstructed. DocETL: the database it built for each query. Tokens:
ours = the initial build plus every on-demand read of the stream; DocETL = every map call. No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_realistic_eval [corpus ...]
"""

from __future__ import annotations

import json
import shutil
import statistics as S
import sys
from pathlib import Path

from quwarts.eval import drift_live as D
from quwarts.eval.exp_tau import EXP, TAUS, safe, score_multi
from quwarts.eval.realistic_queries import load, register

CORPORA = ["cspaper", "player", "art", "med", "legal"]
QVIEWS = Path("/scratch/general/vast/u1592362/quwarts_exp/RW-qviews")
DOCETL = EXP.parent / "docetl_realistic_ollama"
KEY = "fixed4-realistic_100"
TMP = Path("/scratch/general/vast/u1592362/quwarts_exp/RW-score-tmp")
SYSTEMS = {"our system (no re-reads)": ["RW-norereads-V3", "RW-norereads-V3-rep1", "RW-norereads-V3-rep2"],
           "our system": ["RW-V3", "RW-V3-rep1", "RW-V3-rep2"]}


def main(argv=None) -> int:
    corpora = (argv or sys.argv[1:]) or CORPORA
    dest = EXP / "WHY" / "realistic"
    dest.mkdir(parents=True, exist_ok=True)
    for c in corpora:
        ctx = D.R.context(c)
        ids = register(ctx, c)
        questions = {qid: q for qid, q, _ in load(c)}
        out = {"corpus": c, "queries": len(ids), "systems": {}, "per_query": {}}
        per_doc = json.loads((DOCETL / c / "per_query.json").read_text()) if (DOCETL / c / "per_query.json").exists() else {}
        doc_items = [(q, DOCETL / c / "db" / f"{safe(q)}.db") for q in ids if q in per_doc and (DOCETL / c / "db" / f"{safe(q)}.db").exists()]
        if doc_items:
            d = score_multi(c, doc_items)
            out["per_query"]["DocETL"] = {"DocETL": d}
            out["systems"]["DocETL"] = {"queries_answered": len(d), "tokens_m": round(sum(per_doc[q]["prompt_tokens"] + per_doc[q]["completion_tokens"] for q, _ in doc_items) / 1e6, 2)}
        for name, runs in SYSTEMS.items():
            for run in runs:
                stream = EXP / run / "live" / c / "streams" / f"{KEY}.jsonl"
                views = QVIEWS / run / c / KEY
                if not stream.exists() or not views.exists():
                    continue
                recs = [json.loads(x) for x in stream.read_text().splitlines() if x.strip()]
                # a copy of each kept view completed to the physical schema (the predicate signature columns of
                # queries registered after the catalogue was first read; unresolved, they fall back to the SQL predicate)
                tmp = TMP / run / c
                tmp.mkdir(parents=True, exist_ok=True)
                items = []
                for r in recs:
                    v = views / f"{r['pos']:04d}.db"
                    if v.exists():
                        dst = tmp / v.name
                        shutil.copy2(v, dst)
                        D.R.complete(c, dst)
                        items.append((r["qid"], dst))
                o = score_multi(c, items)
                for r in recs:
                    if r["qid"] in o:
                        o[r["qid"]]["recorded_20"] = r.get("benchmark")
                out["per_query"].setdefault(name, {})[run] = o
                build = json.loads((EXP.parent / "drift_live_ollama" / c / "build.json").read_text())  # the shared W0 build
                out["systems"].setdefault(name, {}).setdefault("runs", []).append(
                    {"run": run, "queries": len(o), "stream_tokens_m": round(sum(r["input_tokens"] + r["output_tokens"] for r in recs) / 1e6, 3),
                     "build_tokens_m": round(build["tokens"] / 1e6, 3)})
        # means over the queries every system answered (DocETL may skip some)
        common = set(ids)
        for name, runs in out["per_query"].items():
            for o in runs.values():
                common &= set(o)
        out["common_queries"] = len(common)
        for name, runs in out["per_query"].items():
            out["systems"].setdefault(name, {})["score"] = {
                f"{t:.0%}": round(S.mean(S.mean(o[q][t] for q in common) for o in runs.values()), 4) for t in TAUS} if common else None
        out["questions"] = questions
        (dest / f"{c}.json").write_text(json.dumps(out, indent=1, default=str))
        print(c, "common", len(common), json.dumps({k: v.get("score") for k, v in out["systems"].items()}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

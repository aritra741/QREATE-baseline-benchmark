"""DocETL with and without its optimizers, next to our system, on the queries where our edge was largest.

Haiku executing: plain DocETL (docetl_arms/strfix-claude-haiku-5-5), DocETL + MOAR (labeled sample; salvaged where MOAR's
search looped), DocETL + v1 (no labels), ours (reader_arms/chunk-claude-haiku-5-5). Qwen executing, for context: plain
DocETL as run, with the type fix, with split documents, ours. Scores at 0/5/10/20%; tokens of the executing model
(the optimizers' agent calls are reported separately as cost where DocETL records it).

    PYTHONPATH=systems/WDIRS ~/venvs/quwarts/bin/python systems/DocETL/exp_optimizer_comparison.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUERIES = [("player", q) for q in ("QJ14", "QJ15", "QJ17", "QJ19", "QJ20")] + [("med", q) for q in ("Q8", "Q12", "QJ4")]


def load(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


def main() -> int:
    R = REPO / "results"
    rows = []
    for c, q in QUERIES:
        qid = f"real:{c}#{q}"
        r = {"query": qid}
        d = load(R / "docetl_arms" / "strfix-claude-haiku-5-5" / c / "per_query.json").get(qid)
        r["DocETL (Haiku)"] = d and {"score": d["score"], "tokens_M": round((d["prompt_tokens"] + d["completion_tokens"]) / 1e6, 2)}
        for opt in ("moar", "v1"):
            d = load(R / "docetl_optimized" / f"{opt}-claude-haiku-5-5" / c / "per_query.json").get(qid)
            if d:
                tok = sum(sum(t.get(k, {}).get(x, 0) for x in ("prompt", "completion")) for t in d["tables"] for k in ("optimization_tokens", "run_tokens"))
                r[f"DocETL + {opt.upper() if opt == 'moar' else 'v1'} (Haiku)"] = {
                    "score": d["score"], "tokens_M": round(tok / 1e6, 2),
                    "plans": {t["table"]: t["plan_ops"] for t in d["tables"]},
                    "salvage": {t["table"]: t.get("salvage") for t in d["tables"] if t.get("salvage")}}
        d = load(R / "reader_arms" / "chunk-claude-haiku-5-5" / c / "per_query.json").get(qid)
        r["ours (Haiku)"] = d and {"score": d["score"], "tokens_M": round((d["input_tokens"] + d["output_tokens"]) / 1e6, 2)}
        swap = load(R / "experiments" / "WHY" / "swap" / f"realistic_{c}.json").get(c, {}).get("per_query", {}).get(qid, {})
        r["DocETL as run (Qwen)"] = {"20%": swap.get("docetl")}
        for arm, label in (("strfix", "DocETL type fix (Qwen)"), ("chunked", "DocETL split documents (Qwen)")):
            d = load(R / "docetl_arms" / arm / c / "per_query.json").get(qid)
            r[label] = d and {"score": d["score"], "tokens_M": round((d["prompt_tokens"] + d["completion_tokens"]) / 1e6, 2)}
        r["ours (Qwen)"] = {"20%": swap.get("ours")}
        rows.append(r)
    dest = REPO / "results" / "experiments" / "WHY" / "docetl_optimizer"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "comparison.json").write_text(json.dumps(rows, indent=1, default=str))
    cols = ["DocETL (Haiku)", "DocETL + MOAR (Haiku)", "DocETL + v1 (Haiku)", "ours (Haiku)", "DocETL as run (Qwen)", "DocETL type fix (Qwen)",
            "DocETL split documents (Qwen)", "ours (Qwen)"]

    def cell(x):
        if not x:
            return "-"
        s = (x.get("score") or x).get("20%")
        t = x.get("tokens_M")
        return (f"{s:.3f}" if isinstance(s, (int, float)) else "-") + (f" ({t}M)" if t is not None else "")

    print("query        | " + " | ".join(cols))
    for r in rows:
        print(f"{r['query']:12s} | " + " | ".join(cell(r.get(k)) for k in cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

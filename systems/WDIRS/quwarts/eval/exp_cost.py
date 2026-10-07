"""Cost in tokens, and a representative price at OpenRouter list rates (results/experiments/COST/).

    python -m quwarts.eval.exp_cost

Tokens are input + output as charged by the local server (journal and usage logs). Prices are OpenRouter list rates
fetched on 2026-10-07 (https://openrouter.ai/api/v1/models), per million tokens:
    qwen/qwen-2.5-7b-instruct            $0.10 in, $0.20 out   (the model of every main result)
    meta-llama/llama-3.1-8b-instruct     $0.05 in, $0.08 out
    Qwen 2.5 32B Instruct is not listed; a range from the closest listed models:
    qwen/qwen3-32b                       $0.08 in, $0.28 out   (low)
    qwen/qwen-2.5-coder-32b-instruct     $0.66 in, $1.00 out   (high; same generation and size)
The fixed levels' builds (0-75% drift) are costed as one shared read of W0's and the kept columns (E1.3: within about
2%); their input/output split follows the corpus's measured W0 build.
"""

from __future__ import annotations

import json
import statistics as S
from pathlib import Path

from quwarts.eval.exp_analysis import EXP, REPO

RES = REPO / "results"
OUT = EXP / "COST"
CORPORA = ["cspaper", "player", "art", "med", "legal"]
RATES = {"qwen2.5-7b": (0.10, 0.20), "llama3.1-8b": (0.05, 0.08), "qwen2.5-32b (low: qwen3-32b)": (0.08, 0.28),
         "qwen2.5-32b (high: qwen-2.5-coder-32b)": (0.66, 1.00)}


def usd(inp: float, out: float, rate=RATES["qwen2.5-7b"]) -> float:
    return inp / 1e6 * rate[0] + out / 1e6 * rate[1]


def stream(root: Path, c: str, key: str) -> list[dict]:
    return [json.loads(l) for l in (root / c / "streams" / f"{key}.jsonl").read_text().splitlines()]


def io(rows) -> tuple[int, int]:
    return sum(r["input_tokens"] for r in rows), sum(r["output_tokens"] for r in rows)


def levels(c: str) -> dict[int, dict]:
    import csv

    return {int(r["level"]): r for r in csv.DictReader(open(RES / "drift_live_ollama" / "fixed_levels.csv"))
            if r["corpus"] == c and r["axis"] == "attribute_pool" and r["backend"] == "ollama"}


def main() -> dict:
    out: dict = {"rates_usd_per_million": RATES, "corpora": {}}
    live = RES / "drift_live_ollama"
    for c in CORPORA:
        b = json.loads((live / c / "build.json").read_text())
        w0_in, w0_out = b["input"], b["output"]
        out_share = w0_out / (w0_in + w0_out)
        lv = levels(c)
        per = {}
        for p in (0, 25, 50, 75, 100):
            rows = stream(live, c, f"fixed4-attribute_pool_{p}")
            bt = int(lv[p]["build_tokens"]) if p != 100 else w0_in + w0_out
            b_in, b_out = (w0_in, w0_out) if p == 100 else (bt * (1 - out_share), bt * out_share)
            p_in, p_out = io(rows)
            patching = [r for r in rows if r["action"] == "patch"]
            per[p] = {"queries": len(rows), "score": round(sum(r["benchmark"] for r in rows) / len(rows), 4),
                      "build_tokens": round(b_in + b_out), "patch_tokens": p_in + p_out,
                      "total_tokens": round(b_in + b_out + p_in + p_out),
                      "build_usd": round(usd(b_in, b_out), 4), "patch_usd": round(usd(p_in, p_out), 4),
                      "total_usd": round(usd(b_in + p_in, b_out + p_out), 4),
                      "patching_queries": len(patching),
                      "patch_tokens_per_patching_query": {
                          "median": round(S.median([r["input_tokens"] + r["output_tokens"] for r in patching])) if patching else 0,
                          "max": max([r["input_tokens"] + r["output_tokens"] for r in patching], default=0)},
                      "usd_per_test_query": round(usd(b_in + p_in, b_out + p_out) / len(rows), 5)}
        # DocETL on the same test queries (100% drift)
        dd = json.loads((RES / "docetl_drift_ollama" / c / "per_query.json").read_text())
        q = [r["qid"] for r in stream(live, c, "fixed4-attribute_pool_100") if r["qid"] in dd]
        q_all = len(stream(live, c, "fixed4-attribute_pool_100"))
        d_in = sum(dd[k]["prompt_tokens"] for k in q)
        d_out = sum(dd[k]["completion_tokens"] for k in q)
        docetl = {"queries": len(q), "of": q_all, "tokens": d_in + d_out, "usd": round(usd(d_in, d_out), 4),
                  "usd_per_query": round(usd(d_in, d_out) / len(q), 5)}
        # Smaller build workloads (E12), 100% drift
        shares = {}
        stale = c in ("med", "legal")  # their E12 and other-model runs predate the regenerated queries
        for d, share in (() if stale else (("E12-w0f010", 10), ("E12-w0f025", 25), ("E12-w0f050", 50))):
            f = EXP / d / "live" / c / "build.json"
            if not f.exists():
                continue
            bb = json.loads(f.read_text())
            pi, po = io(stream(EXP / d / "live", c, "fixed4-attribute_pool_100"))
            shares[share] = {"build_tokens": bb["tokens"], "patch_tokens": pi + po,
                             "total_usd": round(usd(bb.get("input", bb["tokens"]) + pi, bb.get("output", 0) + po), 4)}
        # Component ablations (E13): patch tokens at 100% drift
        abl = {}
        for n in ("noreuse", "noscope", "nobatch", "head"):
            if not (EXP / f"E13-{n}" / "live" / c / "streams" / "fixed4-attribute_pool_100.jsonl").exists():
                continue  # not yet run on this corpus
            pi, po = io(stream(EXP / f"E13-{n}" / "live", c, "fixed4-attribute_pool_100"))
            abl[n] = {"patch_tokens": pi + po, "patch_usd": round(usd(pi, po), 4)}
        # Other models (100% drift; their own builds)
        models = {}
        for name, root, rates in (("llama3.1-8b", "E6.2-stream-llama8b", ["llama3.1-8b"]), ("llama3.1-8b", "E6.3-llama8b", ["llama3.1-8b"]),
                                  ("qwen2.5-32b", "E6.2-stream-qwen32b", ["qwen2.5-32b (low: qwen3-32b)", "qwen2.5-32b (high: qwen-2.5-coder-32b)"]),
                                  ("qwen2.5-32b", "E6.3-qwen32b", ["qwen2.5-32b (low: qwen3-32b)", "qwen2.5-32b (high: qwen-2.5-coder-32b)"])):
            r = EXP / f"{root}-{c}" / "live"
            if stale or name in models or not (r / c / "streams" / "fixed4-attribute_pool_100.jsonl").exists():
                continue
            bb = json.loads((r / c / "build.json").read_text())
            pi, po = io(stream(r, c, "fixed4-attribute_pool_100"))
            models[name] = {"build_tokens": bb["tokens"], "patch_tokens": pi + po,
                            "usd": {k: round(usd(bb["input"] + pi, bb["output"] + po, RATES[k]), 4) for k in rates}}
        models["qwen2.5-7b"] = {"build_tokens": per[100]["build_tokens"], "patch_tokens": per[100]["patch_tokens"],
                                "usd": {"qwen2.5-7b": per[100]["total_usd"]}}
        out["corpora"][c] = {"levels": per, "docetl_100": docetl, "train_shares_100": shares, "ablations_100": abl,
                             "models_100": models}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1)[:5000])

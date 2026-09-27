"""Paired comparison of QuWARTS and the fair DocETL run under the benchmark protocol (AUDIT: reads scores).

Held-out queries of each corpus (the 16 or 20 DocETL evaluation queries). QuWARTS: the shared read with
benchmark descriptions on a blank base (``shared_read_protocol/score_blank.json``), from the head run
or, with ``--long chain``, from the chained run where the corpus has documents longer than the window
(a corpus without long documents has identical reads in both). DocETL: ``docetl_protocol_score``.
Differences are paired per query; the 95% interval is a paired bootstrap over queries.

    python -m quwarts.eval.protocol_comparison --long chain
"""

from __future__ import annotations

import argparse
import json
import random
import sys

from quwarts.core.router.registry import RESULTS

CORPORA = ["med", "finan", "legal", "art", "cspaper", "player"]


def paired_ci(diffs: list[float], reps: int = 10_000, seed: int = 20260927) -> list[float]:
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(reps))
    return [round(means[int(0.025 * reps)], 3), round(means[int(0.975 * reps) - 1], 3)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--long", choices=["head", "chain"], default="head")
    args = parser.parse_args(argv)
    rows, qt, dt = [], 0.0, 0.0
    for corpus in CORPORA:
        folder = RESULTS / "quwarts_router_v3" / corpus
        chained = RESULTS / "quwarts_router_v3" / f"{corpus}_chain"
        if args.long == "chain" and (chained / "shared_read_protocol" / "score_blank.json").exists():
            folder = chained
        q = json.loads((folder / "shared_read_protocol" / "score_blank.json").read_text())
        d = json.loads((RESULTS / "docetl_diagnostics" / corpus / "protocol_score.json").read_text())
        held = d["per_query"]
        ours = {p["query_id"]: float(p["product"]) for p in q["read_first"]["per_query"] if p["query_id"] in held}
        diffs = [ours[k] - held[k]["fair_raw"] for k in sorted(held)]
        rows.append({
            "corpus": corpus, "run": folder.name, "n": len(diffs),
            "quwarts": round(sum(ours.values()) / len(ours), 3),
            "docetl_fair": round(sum(h["fair_raw"] for h in held.values()) / len(held), 3),
            "diff": round(sum(diffs) / len(diffs), 3), "ci95": paired_ci(diffs),
            "wlt": [sum(x > 1e-9 for x in diffs), sum(x < -1e-9 for x in diffs), sum(abs(x) <= 1e-9 for x in diffs)],
            "quwarts_tokens_M": round(q["read_tokens"] / 1e6, 2), "docetl_tokens_M": round(d["tokens"] / 1e6, 1),
            "token_fraction": round(q["read_tokens"] / d["tokens"], 3),
        })
        qt, dt = qt + q["read_tokens"], dt + d["tokens"]
    out = {"long_documents": args.long, "per_corpus": rows,
           "macro_quwarts": round(sum(r["quwarts"] for r in rows) / len(rows), 4),
           "macro_docetl_fair": round(sum(r["docetl_fair"] for r in rows) / len(rows), 4),
           "tokens_quwarts_M": round(qt / 1e6, 2), "tokens_docetl_M": round(dt / 1e6, 1), "token_fraction": round(qt / dt, 3)}
    name = "protocol_comparison.json" if args.long == "head" else f"protocol_comparison_{args.long}.json"
    (RESULTS / "docetl_diagnostics" / name).write_text(json.dumps(out, indent=2))
    for r in rows:
        print(f"{r['corpus']:8s} {r['run']:14s} QuWARTS {r['quwarts']:.3f}  DocETL {r['docetl_fair']:.3f}  diff {r['diff']:+.3f} "
              f"CI {r['ci95']}  W/L/T {r['wlt']}  tokens {r['quwarts_tokens_M']}M vs {r['docetl_tokens_M']}M ({r['token_fraction']:.1%})")
    print({k: v for k, v in out.items() if k != "per_corpus"})
    return 0


if __name__ == "__main__":
    sys.exit(main())

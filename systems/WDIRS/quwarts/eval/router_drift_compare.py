"""Drift comparison (AUDIT: reads scores). Both systems use a blank base and the same pipeline.

S_drift is built from the drift split's 64 input queries; S_random from the random split's 64. On the
drift split's 16 held-out queries, S_random saw some of them as input and S_drift saw none, so the
paired difference on the queries S_random saw is the drift penalty: same queries, same pipeline,
only whether the query (and its roles and constants) was in the input differs.

    python -m quwarts.eval.router_drift_compare --corpus legal
"""

from __future__ import annotations

import argparse
import json
import random
import sys

from quwarts.core.router.registry import RESULTS, get_corpus
from quwarts.core.router.templates import drift_split, exposure
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.single_table_case80 import load_queries
from quwarts.eval.router_execute_v3 import DATASET


def paired(a: dict[str, float], b: dict[str, float], ids: list[str], n: int = 10_000) -> dict:
    if not ids:
        return {"n": 0}
    d = [a[q] - b[q] for q in ids]
    rng = random.Random(0)
    boots = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(n))
    return {"n": len(ids), "a": sum(a[q] for q in ids) / len(ids), "b": sum(b[q] for q in ids) / len(ids),
            "a_minus_b": sum(d) / len(d), "ci95": [boots[int(0.025 * n)], boots[int(0.975 * n)]],
            "a_better": sum(x > 1e-12 for x in d), "b_better": sum(x < -1e-12 for x in d),
            "same": sum(abs(x) <= 1e-12 for x in d)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    spec = get_corpus(args.corpus)
    rows = load_queries(DATASET[spec.name])
    r_train, r_test = split_80_20(rows, args.seed)
    d_train, d_test, hidden = drift_split(rows, args.seed, include_constants=True)  # the drift_v0 run
    root = RESULTS / "quwarts_router_v3"
    load = lambda p: {r["query_id"]: float(r["product"]) for r in json.loads(p.read_text())["read_first"]["per_query"]}  # noqa: E731
    s_drift = load(root / f"{spec.name}_drift" / "shared_read_per_attribute" / "score_blank.json")
    s_random = load(root / spec.name / "shared_read_per_attribute" / "score_blank.json")
    d_held = sorted(r["query_id"] for r in d_test)
    r_input = {r["query_id"] for r in r_train}
    seen_by_random = [q for q in d_held if q in r_input]
    unseen_by_both = [q for q in d_held if q not in r_input]
    mean = lambda s, ids: sum(s[q] for q in ids) / len(ids)  # noqa: E731
    ex = exposure(d_train, d_test)
    report = {
        "hidden_items": hidden,
        "exposure": {k: v for k, v in ex.items() if k != "per_query"},
        "S_drift": {"input_64": mean(s_drift, [r["query_id"] for r in d_train]), "held_out_16": mean(s_drift, d_held)},
        "S_random": {"input_64": mean(s_random, sorted(r_input)), "held_out_16": mean(s_random, [r["query_id"] for r in r_test]),
                     "on_drift_held_out_16": mean(s_random, d_held)},
        "drift_penalty_on_queries_S_random_saw": paired(s_random, s_drift, seen_by_random),
        "both_unseen": paired(s_random, s_drift, unseen_by_both),
        "all_16_drift_held_out": paired(s_random, s_drift, d_held),
        "per_query": {q: {"S_random": round(s_random[q], 4), "S_drift": round(s_drift[q], 4),
                          "seen_by_S_random": q in r_input,
                          "drift": ex["per_query"][q]["unseen_roles"] + ex["per_query"][q]["unseen_literals"]}
                      for q in d_held},
    }
    out = root / f"{spec.name}_drift" / "drift_compare.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "per_query"}, indent=2))
    for q, v in report["per_query"].items():
        print(f"  {q:24s} seen_by_random={str(v['seen_by_S_random']):5s} S_random={v['S_random']:.3f} S_drift={v['S_drift']:.3f}  {v['drift'][:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

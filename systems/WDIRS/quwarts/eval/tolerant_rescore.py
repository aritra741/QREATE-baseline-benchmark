"""Rescore the frozen protocol runs of QuWARTS and fair DocETL under the benchmark metric and the tolerant
metric (``tolerant_score``), both on every query and on the held-out queries (AUDIT: reads gold).

QuWARTS: ``shared_read_protocol/read_first_blank.db`` (chained run where it exists), all train and test
queries. DocETL: the fair protocol run's per-query databases (``docetl_diagnostics/<corpus>/protocol_raw``),
its 16 or 20 evaluation queries. Databases are copied to a scratch folder before scoring. The benchmark
metric must reproduce the stored scores exactly (checked).

    python -m quwarts.eval.tolerant_rescore --corpus med
    python -m quwarts.eval.tolerant_rescore --report
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path
from typing import Any

from quwarts.core.router.registry import RESULTS
from quwarts.eval.tolerant_score import score_tolerant

CORPORA = ["med", "finan", "legal", "art", "cspaper", "player"]
ROOT = RESULTS / "representation" / "tolerant_rescore"
SCRATCH = Path.home() / "quwarts_scratch" / "tolerant_rescore"


def quwarts_run(corpus: str) -> Path:
    chained = RESULTS / "quwarts_router_v3" / f"{corpus}_chain" / "shared_read_protocol"
    return chained if (chained / "read_first_blank.db").exists() else RESULTS / "quwarts_router_v3" / corpus / "shared_read_protocol"


def all_queries(corpus: str) -> dict[str, str]:
    from quwarts.eval import router_shared_read_run as rs

    train, test = rs.workload(corpus)
    return {r["query_id"]: r["sql"] for r in list(train) + list(test)}


def per_query(report: dict[str, Any]) -> dict[str, float]:
    return {p["query_id"]: round(float(p["product"]), 4) for p in report["per_query"]}


def score_both(dataset: str, queries: dict[str, str], dbs: dict[str, str], base: Path, scratch: Path) -> dict[str, dict[str, float]]:
    from quwarts.eval.router_execute_v3 import score

    benchmark = per_query(score(dataset, queries, dbs, base))
    tolerant_ = per_query(score_tolerant(dataset, queries, dbs, base, scratch))
    return {"benchmark": benchmark, "tolerant": tolerant_}


def rescore(corpus: str) -> dict[str, Any]:
    from quwarts.core.router.registry import get_corpus
    from quwarts.eval.docetl_rescore import recorded_tables
    from quwarts.eval.router_execute_v3 import DATASET

    spec = get_corpus(corpus)
    out: dict[str, Any] = {"corpus": corpus}
    run = quwarts_run(corpus)
    scratch = SCRATCH / corpus
    scratch.mkdir(parents=True, exist_ok=True)
    db = scratch / "quwarts_read_first_blank.db"
    shutil.copy2(run / "read_first_blank.db", db)
    queries = all_queries(corpus)
    q = score_both(DATASET[spec.name], queries, {k: str(db) for k in queries}, db, scratch / "tolerant_quwarts")
    stored = {p["query_id"]: round(float(p["product"]), 4)
              for p in json.loads((run / "score_blank.json").read_text())["read_first"]["per_query"]}
    out["quwarts"] = {"run": str(run.relative_to(RESULTS)), **q,
                      "reproduces_stored": all(abs(q["benchmark"].get(k, 0) - v) < 1e-3 for k, v in stored.items())}
    manifest, _ = recorded_tables(spec.name)
    folder = RESULTS / "docetl_diagnostics" / spec.name / "protocol_raw"
    dbs = {}
    for qid in manifest:
        src = folder / f"{qid.replace(':', '_')}.db"
        dst = scratch / "docetl" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        dbs[qid] = str(dst)
    d = score_both(DATASET[spec.name], manifest, dbs, Path(next(iter(dbs.values()))), scratch / "tolerant_docetl")
    stored_d = json.loads((RESULTS / "docetl_diagnostics" / spec.name / "protocol_score.json").read_text())["per_query"]
    out["docetl"] = {**d, "reproduces_stored": all(abs(d["benchmark"][k] - v["fair_raw"]) < 1e-3 for k, v in stored_d.items())}
    out["held_out"] = sorted(manifest)
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / f"{corpus}.json").write_text(json.dumps(out, indent=1))
    return out


def paired_ci(diffs: list[float], reps: int = 10_000, seed: int = 20260927) -> list[float]:
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(reps))
    return [round(means[int(0.025 * reps)], 3), round(means[int(0.975 * reps) - 1], 3)]


def report() -> str:
    lines = ["| Corpus | Metric | QuWARTS, held-out | DocETL, held-out | Δ (CI95) | QuWARTS, all queries | reproduces stored |",
             "|---|---|---:|---:|---|---:|---|"]
    macro = {"benchmark": [[], []], "tolerant": [[], []]}
    for corpus in CORPORA:
        path = ROOT / f"{corpus}.json"
        if not path.exists():
            continue
        r = json.loads(path.read_text())
        held = r["held_out"]
        for metric in ("benchmark", "tolerant"):
            qs = [r["quwarts"][metric].get(k, 0.0) for k in held]
            ds = [r["docetl"][metric].get(k, 0.0) for k in held]
            allq = list(r["quwarts"][metric].values())
            diffs = [a - b for a, b in zip(qs, ds)]
            macro[metric][0].append(sum(qs) / len(qs))
            macro[metric][1].append(sum(ds) / len(ds))
            ok = f"{r['quwarts']['reproduces_stored']}/{r['docetl']['reproduces_stored']}" if metric == "benchmark" else ""
            lines.append(f"| {corpus} | {metric} | {sum(qs) / len(qs):.3f} | {sum(ds) / len(ds):.3f} | "
                         f"{sum(diffs) / len(diffs):+.3f} {paired_ci(diffs)} | {sum(allq) / len(allq):.3f} | {ok} |")
    for metric, (qs, ds) in macro.items():
        if qs:
            lines.append(f"| **macro** | {metric} | {sum(qs) / len(qs):.3f} | {sum(ds) / len(ds):.3f} | {sum(qs) / len(qs) - sum(ds) / len(ds):+.3f} | | |")
    text = "\n".join(lines)
    (ROOT / "REPORT.md").write_text(text + "\n")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", choices=CORPORA)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)
    if args.corpus:
        r = rescore(args.corpus)
        print(json.dumps({k: (v if not isinstance(v, dict) else {m: (round(sum(x.values()) / max(1, len(x)), 4) if isinstance(x, dict) else x)
                                                                   for m, x in v.items()}) for k, v in r.items() if k != "held_out"}))
    if args.report:
        print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())

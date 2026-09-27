"""Score the fair DocETL Legal run and compare it paired with recorded DocETL and QuWARTS.

The fair run (``systems/DocETL/run_fair_docetl.py``) gives DocETL the same workload-generated
descriptions QuWARTS used, SQL-derived numeric types, a tokenizer-correct context cut, and logs
failures. Its tables are scored here through the same path as ``docetl_rescore`` (which reproduces
the recorded 0.12350932750098194 exactly), once raw and once with -1 / empty sentinels as NULL.
Only queries whose run completed (``stats.json`` with rows > 0) are scored; the comparison is paired
on exactly those queries.

    python -m quwarts.eval.docetl_fair_score --corpus legal
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from typing import Any

from quwarts.core.router.registry import RESULTS, get_corpus
from quwarts.eval.docetl_rescore import recorded_tables, rescore

def fair_tables(corpus: str) -> tuple[dict[str, dict[str, list]], dict[str, dict], set[str]]:
    run = RESULTS / f"docetl_fair_{corpus}"
    numeric = set(json.loads((run / "numeric_fields.json").read_text()))
    tables: dict[str, dict[str, list]] = {}
    stats: dict[str, dict] = {}
    for stat_path in sorted(run.glob("*/table_*/stats.json")):
        s = json.loads(stat_path.read_text())
        if not s.get("rows"):
            continue  # a run that made no successful calls is not a DocETL result
        qid = s["query_id"]
        stats[qid] = s
        tables.setdefault(qid, {})[stat_path.parent.name[len("table_"):]] = json.loads(
            (stat_path.parent / "pipeline_output.json").read_text())
    return tables, stats, numeric


def per_query(report: dict[str, Any]) -> dict[str, float]:
    rows = report["per_query"]
    return {r["query_id"]: float(r["product"]) for r in rows}


def paired(a: dict[str, float], b: dict[str, float], qids: list[str], seed: int = 0, n: int = 10_000) -> dict:
    diffs = [a[q] - b[q] for q in qids]
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n))
    return {"mean_a": sum(a[q] for q in qids) / len(qids), "mean_b": sum(b[q] for q in qids) / len(qids),
            "mean_diff": sum(diffs) / len(diffs), "ci95": [boots[int(0.025 * n)], boots[int(0.975 * n)]],
            "wins": sum(d > 1e-12 for d in diffs), "losses": sum(d < -1e-12 for d in diffs),
            "ties": sum(abs(d) <= 1e-12 for d in diffs)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    args = parser.parse_args(argv)
    spec = get_corpus(args.corpus)
    manifest, _ = recorded_tables(spec.name)
    tables, stats, numeric = fair_tables(spec.name)
    queries = {q: manifest[q] for q in tables}
    table_names = {t for per in tables.values() for t in per}
    numeric_by_table = {t: numeric for t in table_names}
    out = RESULTS / "docetl_diagnostics" / spec.name
    reports = {}
    for tag, null in (("fair_raw", False), ("fair_nullfix", True)):
        reports[tag] = rescore(spec.name, tables, numeric_by_table, queries, out / tag, null)
        (out / f"{tag}_score.json").write_text(json.dumps(reports[tag], indent=2))

    recorded = per_query(json.loads((out / "recorded_score.json").read_text()))
    recorded_null = per_query(json.loads((out / "recorded_nullfix_score.json").read_text()))
    quwarts_path = RESULTS / "quwarts_router_v3" / spec.name / "shared_read_per_attribute" / "score.json"
    quwarts = per_query(json.loads(quwarts_path.read_text())["read_first"])
    qids = sorted(queries)
    fair_raw, fair_null = per_query(reports["fair_raw"]), per_query(reports["fair_nullfix"])
    tokens = {q: stats[q]["prompt_tokens"] + stats[q]["completion_tokens"] for q in qids}
    summary = {
        "queries": qids,
        "n": len(qids),
        "missing_from_16": "runs stopped when OpenRouter credits ran out (HTTP 402); see stats",
        "per_query": {q: {"fair_raw": fair_raw[q], "fair_nullfix": fair_null[q], "recorded": recorded[q],
                          "recorded_nullfix": recorded_null[q], "quwarts_per_attribute": quwarts[q],
                          "fair_tokens": tokens[q]} for q in qids},
        "fair_docetl_tokens_mean_per_query": sum(tokens.values()) / len(qids),
        "quwarts_vs_fair_nullfix": paired(quwarts, fair_null, qids),
        "quwarts_vs_fair_raw": paired(quwarts, fair_raw, qids),
        "quwarts_vs_recorded": paired(quwarts, recorded, qids),
        "fair_nullfix_vs_recorded": paired(fair_null, recorded, qids),
    }
    (out / "fair_comparison.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "per_query"}, indent=2))
    for q in qids:
        print(q, {k: round(v, 4) if isinstance(v, float) else v for k, v in summary["per_query"][q].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())

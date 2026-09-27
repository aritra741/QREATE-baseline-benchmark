"""Score a fair DocETL run under the benchmark protocol (AUDIT: reads gold).

The run lives in results/docetl_fair_<corpus>_<tag> (``systems/DocETL/run_fair_docetl.py --protocol``):
attribute descriptions and value types from the benchmark, Qwen-tokenizer cuts with endpoint-driven
retries, failures logged. Scored through the same path as ``docetl_rescore`` (which reproduces the
recorded DocETL numbers exactly), raw and with -1 / empty sentinels as NULL, and compared per query
with the recorded DocETL run on the same queries.

    python -m quwarts.eval.docetl_protocol_score --corpus finan --tag protocol
"""

from __future__ import annotations

import argparse
import json
import sys

from quwarts.core.router.registry import RESULTS, get_corpus
from quwarts.eval.docetl_rescore import recorded_tables, rescore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--tag", default="protocol")
    args = parser.parse_args(argv)
    spec = get_corpus(args.corpus)
    run = RESULTS / f"docetl_fair_{spec.name}_{args.tag}"
    manifest, recorded = recorded_tables(spec.name)
    numeric = set(json.loads((run / "numeric_fields.json").read_text()))
    tables, stats = {}, {}
    for stat_path in sorted(run.glob("*/table_*/stats.json")):
        s = json.loads(stat_path.read_text())
        tables.setdefault(s["query_id"], {})[stat_path.parent.name[len("table_"):]] = json.loads(
            (stat_path.parent / "pipeline_output.json").read_text())
        stats[s["query_id"]] = s
    missing = sorted(set(manifest) - set(tables))
    if missing:
        raise SystemExit(f"incomplete run: {missing}")
    numeric_by_table = {t.sql_name: numeric for t in spec.tables}
    out = RESULTS / "docetl_diagnostics" / spec.name
    reports = {}
    for tag, null in (("raw", False), ("nullfix", True)):
        reports[tag] = rescore(spec.name, tables, numeric_by_table, manifest, out / f"{args.tag}_{tag}", null)
    rec = rescore(spec.name, {q: recorded[q] for q in manifest}, numeric_by_table, manifest, out / f"{args.tag}_recorded_same_types", False)
    per = lambda r: {p["query_id"]: float(p["product"]) for p in r["per_query"]}  # noqa: E731
    raw, null, old = per(reports["raw"]), per(reports["nullfix"]), per(rec)
    summary = {
        "corpus": spec.name, "run": run.name, "queries": len(manifest),
        "product_raw": reports["raw"]["mean_per_query_product"],
        "product_nullfix": reports["nullfix"]["mean_per_query_product"],
        "recorded_docetl_product": json.loads((RESULTS / f"docetl_{spec.name}_case80" / "evaluation.json").read_text())["mean_query_score"]["0.2"],
        "tokens": sum(s["prompt_tokens"] + s["completion_tokens"] for s in stats.values()),
        "rows_per_query": sorted({s["rows"] for s in stats.values()}),
        "docs_at_reduced_context": sum(s.get("docs_at_reduced_context", 0) for s in stats.values()),
        "per_query": {q: {"fair_raw": round(raw[q], 4), "fair_nullfix": round(null[q], 4), "recorded": round(old[q], 4)} for q in sorted(manifest)},
    }
    (out / f"{args.tag}_score.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "per_query"}, indent=2))
    for q, v in summary["per_query"].items():
        print(f"  {q:24s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

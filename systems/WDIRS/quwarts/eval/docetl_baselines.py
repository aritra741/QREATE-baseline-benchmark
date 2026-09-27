"""Zero-token audit of the recorded DocETL case80 runs (AUDIT: the rescore reads gold).

Per corpus: the recorded product (evaluation.json mean_query_score@0.20, the handoff's number), the
two recorded token totals (summary.json and session_token_cost.json, which disagree for some runs),
coverage per query and table (rows, distinct documents, documents missing from the output, duplicate
rows), the share of sentinel cells (-1 for numbers, empty strings for text), whether the recorded
query set equals the held-out split QuWARTS is scored on, and a rescore through the QuWARTS scorer
(raw and with sentinels as NULL) for single-table queries, which must reproduce the recorded number.

    python -m quwarts.eval.docetl_baselines
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from quwarts.core.router.corpus_features import list_documents
from quwarts.core.router.registry import REGISTRY, RESULTS

CORPORA = ["med", "finan", "legal", "art", "cspaper", "player"]


def doc_key(value: Any) -> str:
    """Document id without a trailing .txt (ids such as '2401.01511v1_Title' contain dots)."""
    text = Path(str(value)).name.strip()
    return text[:-4] if text.endswith(".txt") else text


def main(argv: list[str] | None = None) -> int:
    from quwarts.eval import router_shared_read_run as rs
    from quwarts.eval.docetl_rescore import recorded_tables, rescore

    report: dict[str, Any] = {"audit_only": True, "corpora": {}}
    for name in CORPORA:
        spec = REGISTRY[name]
        run = RESULTS / f"docetl_{name}_case80"
        ev = json.loads((run / "evaluation.json").read_text())
        summary = json.loads((run / "summary.json").read_text())
        session = json.loads((run / "session_token_cost.json").read_text())
        manifest, tables = recorded_tables(name)
        docs = {t.sql_name: {doc_key(p.name) for p in list_documents(t)} for t in spec.tables}
        source_len = {t.sql_name: {doc_key(p.name): len(p.read_text(errors="replace")) for p in list_documents(t)}
                      for t in spec.tables}
        seen_share: list[float] = []

        coverage = {}
        sentinel = Counter()
        for qid, per_table in tables.items():
            for table, records in per_table.items():
                ids = [doc_key(r.get("doc_id", "")) for r in records]
                lengths = source_len.get(table, {})
                seen_share += [min(1.0, len(str(r.get("text", ""))) / lengths[i]) for r, i in zip(records, ids)
                               if lengths.get(i) and "text" in r]
                corpus = docs.get(table, set())
                coverage[f"{qid}/{table}"] = {"rows": len(ids), "distinct_docs": len(set(ids)), "corpus_docs": len(corpus),
                                              "missing_docs": len(corpus - set(ids)), "duplicate_rows": len(ids) - len(set(ids))}
                for r in records:
                    for k, v in r.items():
                        if k in ("doc_id", "text"):
                            continue
                        sentinel["cells"] += 1
                        if v == -1 or v == -1.0 or (isinstance(v, str) and not v.strip()):
                            sentinel["sentinel"] += 1
        missing_share = [c["missing_docs"] / c["corpus_docs"] for c in coverage.values() if c["corpus_docs"]]

        try:
            _train, test = rs.workload(name)
            test_ids = {r["query_id"] for r in test}
            same_split = set(manifest) == test_ids
        except Exception as exc:  # noqa: BLE001
            same_split = f"workload unavailable: {exc}"

        single = {q: t for q, t in tables.items() if len(t) == 1}
        rescored = {}
        if single:
            types = spec.benchmark_attribute_descriptions(purpose="scoring")
            numeric = {t.sql_name: {a for a, r in types.get(t.attributes_key, {}).items()
                                    if str(r.get("value_type")) in ("int", "float")} for t in spec.tables}
            for tag, null in (("raw", False), ("nullfix", True)):
                try:
                    rep = rescore(name, single, numeric, {q: manifest[q] for q in single},
                                  RESULTS / "docetl_diagnostics" / name / f"baseline_{tag}", null)
                    rescored[tag] = rep["mean_per_query_product"]
                except Exception as exc:  # noqa: BLE001
                    rescored[tag] = f"error: {type(exc).__name__}: {exc}"[:200]

        report["corpora"][name] = {
            "queries": len(manifest),
            "multi_table_queries": len(tables) - len(single),
            "recorded_product": ev["mean_query_score"]["0.2"],
            "rescored_single_table_product": rescored,
            "tokens_summary_json": summary.get("total_tokens"),
            "tokens_session_json": session.get("total_tokens"),
            "llm_calls": [summary.get("llm_calls"), session.get("llm_calls")],
            "query_set_equals_quwarts_held_out": same_split,
            "docs_per_table": {t: len(v) for t, v in docs.items()},
            "mean_missing_doc_share": sum(missing_share) / len(missing_share) if missing_share else None,
            "max_missing_doc_share": max(missing_share) if missing_share else None,
            "total_duplicate_rows": sum(c["duplicate_rows"] for c in coverage.values()),
            "sentinel_cell_share": sentinel["sentinel"] / sentinel["cells"] if sentinel["cells"] else None,
            "mean_share_of_document_seen": sum(seen_share) / len(seen_share) if seen_share else None,
            "rows_seeing_under_half_the_document": (sum(x < 0.5 for x in seen_share) / len(seen_share)) if seen_share else None,
            "coverage": coverage,
        }
    out = RESULTS / "docetl_diagnostics" / "baselines_audit.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    for name, c in report["corpora"].items():
        print(f"{name:8s} q={c['queries']:2d} multi={c['multi_table_queries']:2d} recorded={c['recorded_product']:.4f} "
              f"rescored={c['rescored_single_table_product']} tokens={c['tokens_summary_json']}/{c['tokens_session_json']} "
              f"same_split={c['query_set_equals_quwarts_held_out']} missing={c['mean_missing_doc_share']:.3f}"
              f"(max {c['max_missing_doc_share']:.3f}) dupes={c['total_duplicate_rows']} sentinel={c['sentinel_cell_share']:.3f} "
              f"seen={c['mean_share_of_document_seen']} under_half={c['rows_seeing_under_half_the_document']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

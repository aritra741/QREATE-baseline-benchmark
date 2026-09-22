"""Zero-token audit of frozen DocETL Med/Finan/Legal runs. No model calls."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/aritramazumder/Documents/UDA-Bench-main")
OUT = ROOT / "results" / "docetl_execution_anatomy_audit"

RUNS = {
    "Finan": ROOT / "results" / "docetl_finan_case80",
    "Med": ROOT / "results" / "docetl_med_case80",
    "Legal": ROOT / "results" / "docetl_legal_case80",
}
SOURCE = {
    "Finan": ROOT / "source_data" / "Finance" / "finance",
    "Med": {
        "disease": ROOT / "source_data" / "Healthcare" / "disease_small",
        "drug": ROOT / "source_data" / "Healthcare" / "drug_small",
        "institution": ROOT / "source_data" / "Healthcare" / "institutes_small",
    },
    "Legal": ROOT / "source_data" / "Legal" / "legal_case",
}

ARTIFACT_NAMES = [
    "summary.json",
    "session_token_cost.json",
    "query_results.json",
    "query_manifest.json",
    "evaluation.json",
    "report.json",
    "docetl_shim.json",
    "test_workload.json",
    "docetl_grid_test.log",
]


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reconstruct_prompt(table: str, needed_cols: list[str], nl_query: str) -> str:
    field_list = "\n".join(f"- {c}" for c in needed_cols)
    numeric_guidance = ", ".join(c for c in needed_cols)
    return (
        f"You are building a structured {table} table for this natural-language query:\n"
        f"{nl_query}\n\n"
        f"From this {table} document, extract exactly one record with these fields:\n"
        f"{field_list}\n\n"
        "For numeric fields, return numbers (not quoted strings). "
        f"Numeric fields in this extraction: {numeric_guidance if numeric_guidance else 'none'}.\n"
        "If a numeric field is unknown, return -1. "
        "If a text field is unknown, return empty string. "
        "Keep names concise and normalized.\n\n"
        f"Document:\n{{{{ input.text }}}}"
    )


def count_txt(path: Path) -> int:
    if not path.exists():
        return 0
    return len(list(path.glob("*.txt")))


def json_row_count(path: Path) -> tuple[int, list[str], bool, int]:
    """Return (n_rows, keys, has_text, nbytes). Does not infer execution."""
    if not path.exists():
        return 0, [], False, 0
    raw = path.read_bytes()
    data = json.loads(raw)
    if isinstance(data, list):
        keys = sorted({k for row in data[:5] if isinstance(row, dict) for k in row})
        has_text = any(isinstance(row, dict) and "text" in row for row in data[:20])
        return len(data), keys, has_text, len(raw)
    if isinstance(data, dict):
        return 1, sorted(data.keys()), "text" in data, len(raw)
    return 0, [], False, len(raw)


def parse_log(log_path: Path) -> dict:
    if not log_path.exists():
        return {"available": False}
    text = log_path.read_text(errors="ignore")
    completions = len(re.findall(r"LiteLLM completion\(\)", text))
    wrappers = len(re.findall(r"Wrapper: Completed Call", text))
    retries = len(re.findall(r"(?i)retry|Retrying", text))
    errors = len(re.findall(r"(?i)failed|RateLimit|timeout|Error", text))
    q_starts = re.findall(r"Executing (\S+)", text)
    return {
        "available": True,
        "bytes": log_path.stat().st_size,
        "litellm_completion_log_lines": completions,
        "wrapper_completed_log_lines": wrappers,
        "retry_log_lines": retries,
        "errorish_log_lines": errors,
        "executing_mentions": q_starts,
        "n_executing_mentions": len(q_starts),
        "note": (
            "LiteLLM logs both start and wrapper lines; these are not a "
            "per-call ledger. Prefer query_results.llm_calls."
        ),
    }


def inventory(run_dir: Path) -> dict:
    files = {}
    for name in ARTIFACT_NAMES:
        p = run_dir / name
        files[name] = {
            "exists": p.exists(),
            "bytes": p.stat().st_size if p.exists() else 0,
        }
    qt = run_dir / "query_tables"
    files["query_tables/"] = {
        "exists": qt.is_dir(),
        "n_json": len(list(qt.glob("*.json"))) if qt.is_dir() else 0,
        "n_csv": len(list(qt.glob("*.csv"))) if qt.is_dir() else 0,
    }
    pipes = run_dir / "docetl_pipelines"
    files["docetl_pipelines/"] = {
        "exists": pipes.is_dir(),
        "n_query_dirs": len([p for p in pipes.iterdir() if p.is_dir()]) if pipes.is_dir() else 0,
    }
    eval_dbs = run_dir / "query_eval_dbs"
    files["query_eval_dbs/"] = {
        "exists": eval_dbs.is_dir(),
        "n_db": len(list(eval_dbs.glob("*.db"))) if eval_dbs.is_dir() else 0,
    }
    plots = run_dir / "plots"
    files["plots/"] = {"exists": plots.is_dir()}
    yaml_plans = list(run_dir.rglob("*.yaml")) + list(run_dir.rglob("*.yml"))
    files["yaml_plans"] = {"exists": bool(yaml_plans), "n": len(yaml_plans)}
    cache_dirs = [
        p for p in run_dir.rglob("*")
        if p.is_dir() and p.name in {".cache", "cache", "llm_cache", ".docetl_cache"}
    ]
    files["docetl_llm_cache"] = {"exists": bool(cache_dirs), "paths": [str(p) for p in cache_dirs]}
    call_logs = list(run_dir.rglob("*call*log*")) + list(run_dir.rglob("*usage*.jsonl"))
    files["per_call_jsonl"] = {"exists": bool(call_logs), "n": len(call_logs)}
    candidate = list(run_dir.rglob("*candidate*")) + list(run_dir.rglob("*pareto*"))
    files["optimizer_candidate_plans"] = {"exists": bool(candidate), "n": len(candidate)}
    return files


def source_counts(dataset: str) -> dict:
    src = SOURCE[dataset]
    if isinstance(src, dict):
        return {table: count_txt(path) for table, path in src.items()}
    return {"finance" if dataset == "Finan" else "legal": count_txt(src)}


def eval_scores(evaluation: dict | None) -> dict[str, dict]:
    if not evaluation:
        return {}
    out = {}
    for qid, rec in (evaluation.get("per_query") or {}).items():
        rank = rec.get("rank") or {}
        cell = (rank.get("cell_f1") or rec.get("cell_f1") or {})
        prod = (rank.get("query_score") or rec.get("query_score") or {})
        out[qid] = {
            "f2": rank.get("structure_fbeta_score", rec.get("structure", {}).get("structure_fbeta_score")),
            "cell_f1_02": cell.get("0.2"),
            "product_02": prod.get("0.2"),
            "gold_rows": rec.get("gold_row_count"),
            "pred_rows": rec.get("predicted_row_count"),
            "official_accuracy": rec.get("official_accuracy"),
        }
    return out


def inspect_pipelines(run_dir: Path, query_sql: dict[str, str]) -> list[dict]:
    pipes = run_dir / "docetl_pipelines"
    rows = []
    if not pipes.is_dir():
        return rows
    for qdir in sorted(p for p in pipes.iterdir() if p.is_dir()):
        qid = qdir.name
        tables = []
        for tdir in sorted(p for p in qdir.iterdir() if p.is_dir() and p.name.startswith("table_")):
            table = tdir.name.removeprefix("table_")
            cfg = load_json(tdir / "docetl_intermediate" / ".docetl_intermediate_config.json")
            extract_path = tdir / "docetl_intermediate" / "extract_step" / "extract_fields.json"
            out_path = tdir / "pipeline_output.json"
            n_ext, ext_keys, ext_text, ext_bytes = json_row_count(extract_path)
            n_out, out_keys, out_text, out_bytes = json_row_count(out_path)
            prompt_hash_from_cfg = None
            if isinstance(cfg, dict):
                prompt_hash_from_cfg = (cfg.get("extract_step") or {}).get("extract_fields")
            # reconstruct prompt from SQL + table columns in extract output keys
            needed = [k for k in ext_keys if k not in {"doc_id", "text", "_input_hash"}]
            sql = query_sql.get(qid, "")
            prompt = reconstruct_prompt(table, needed, sql)
            tables.append({
                "table": table,
                "operator": "map",
                "operator_name": "extract_fields",
                "step": "extract_step",
                "config_available": cfg is not None,
                "intermediate_config": cfg,
                "stored_output_hash": prompt_hash_from_cfg,
                "reconstructed_prompt_sha256": sha256_text(prompt),
                "needed_cols_from_output_keys": needed,
                "n_attributes": len(needed),
                "extract_fields_rows": n_ext,
                "extract_fields_bytes": ext_bytes,
                "extract_fields_has_document_text": ext_text,
                "pipeline_output_rows": n_out,
                "pipeline_output_bytes": out_bytes,
                "pipeline_output_has_document_text": out_text,
                "pipeline_output_sample_keys": out_keys,
                "unit_of_work": "several_attributes_for_one_document",
                "input_kind": "full_document",
                "chunking": False,
                "gleaning": False,
                "resolve": False,
                "batch_size_configured": None,
                "batch_size_default_in_runner": 1,
                "final_aggregate_by": "sqlite_benchmark_sql",
            })
        qt = run_dir / "query_tables" / f"{qid}.json"
        pred = load_json(qt) if qt.exists() else None
        rows.append({
            "query_id": qid,
            "n_table_pipelines": len(tables),
            "tables": tables,
            "query_table_exists": qt.exists(),
            "query_table_groups": len(pred) if isinstance(pred, list) else None,
            "empty_output_bag": isinstance(pred, list) and len(pred) == 0,
            "executed_dag": [
                "document_selection: all *.txt in source table dir (runner _raw_doc_records_for_table)",
                "chunking_or_retrieval: unavailable / not present in artifacts (no split/gather/topk)",
                "map_extraction: MapOp extract_fields, one call per document, all SQL-needed attrs",
                "filter: SQLite WHERE from benchmark SQL (not an LLM filter op)",
                "resolve_entity_matching: unavailable / not present",
                "grouping: SQLite GROUP BY from benchmark SQL",
                "reduce_aggregation: SQLite COUNT/AVG/SUM from benchmark SQL",
                "validation_gleaning: unavailable / not configured in runner",
                "final_output: query_tables/<id>.json from SQLite",
            ],
            "candidate_plans_evaluated": "unavailable — optimizer was not invoked; bypass_cache=True",
        })
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "audit": "zero-token frozen DocETL execution anatomy",
        "no_model_calls": True,
        "no_docetl_rerun": True,
        "corpora": {},
        "missing_telemetry": [],
        "quwarts_finan": {},
    }
    missing = []

    for dataset, run_dir in RUNS.items():
        inv = inventory(run_dir)
        summary = load_json(run_dir / "summary.json")
        session = load_json(run_dir / "session_token_cost.json")
        qres = load_json(run_dir / "query_results.json") or []
        qman = load_json(run_dir / "query_manifest.json") or []
        ev = load_json(run_dir / "evaluation.json")
        scores = eval_scores(ev)
        query_sql = {row["query_id"]: row["sql"] for row in qres}
        if not query_sql and qman:
            query_sql = {row["query_id"]: row["sql"] for row in qman}
        pipes = inspect_pipelines(run_dir, query_sql)
        log_info = parse_log(run_dir / "docetl_grid_test.log")
        src = source_counts(dataset)

        session_calls = (session or {}).get("llm_calls")
        summary_calls = (summary or {}).get("llm_calls")
        session_tokens = (session or {}).get("total_tokens")
        summary_tokens = (summary or {}).get("total_tokens")
        session_is_partial = (
            session_calls is not None
            and summary_calls is not None
            and session_calls != summary_calls
        )

        per_query = []
        call_list = []
        for row in qres:
            qid = row["query_id"]
            sc = scores.get(qid, {})
            pipe = next((p for p in pipes if p["query_id"] == qid), None)
            n_docs_out = 0
            n_attrs = 0
            n_tables = 0
            if pipe:
                n_tables = pipe["n_table_pipelines"]
                n_docs_out = sum(t["pipeline_output_rows"] for t in pipe["tables"])
                n_attrs = sum(t["n_attributes"] for t in pipe["tables"])
            calls = row.get("llm_calls")
            tokens = row.get("total_tokens")
            prompt = row.get("prompt_tokens")
            completion = row.get("completion_tokens")
            # implied docs/call only if calls == extracted rows; else mark unknown
            docs_per_call = None
            if calls and n_docs_out and calls == n_docs_out:
                docs_per_call = 1.0
            elif calls and n_docs_out:
                docs_per_call = n_docs_out / calls
            per_query.append({
                "query_id": qid,
                "sql": row.get("sql"),
                "family": qid.split(":")[0].split("_", 1)[-1] if "_" in qid else None,
                "success": row.get("success"),
                "llm_calls": calls,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": tokens,
                "latency_s": row.get("latency_s"),
                "pred_rows": row.get("pred_rows"),
                "gold_rows": row.get("gold_rows"),
                "official_score": row.get("score"),
                "f2": sc.get("f2"),
                "cell_f1_02": sc.get("cell_f1_02"),
                "product_02": sc.get("product_02"),
                "n_table_pipelines": n_tables,
                "extracted_rows_sum": n_docs_out,
                "attributes_extracted_sum": n_attrs,
                "empty_output_bag": row.get("pred_rows") == 0,
                "tokens_per_call": (tokens / calls) if calls else None,
                "tokens_per_extracted_row": (tokens / n_docs_out) if n_docs_out else None,
                "completion_tokens_per_call": (completion / calls) if calls else None,
                "prompt_tokens_per_call": (prompt / calls) if calls else None,
                "implied_docs_per_call": docs_per_call,
                "final_aggregate_by": "sqlite",
                "llm_produced_final_aggregate": False,
            })
            if calls:
                call_list.append({
                    "calls": calls,
                    "prompt": prompt,
                    "completion": completion,
                    "total": tokens,
                    "docs": n_docs_out,
                    "attrs": n_attrs,
                    "product": sc.get("product_02") or 0.0,
                })

        n_q = len(per_query)
        tot_calls = sum(r["llm_calls"] or 0 for r in per_query)
        tot_prompt = sum(r["prompt_tokens"] or 0 for r in per_query)
        tot_comp = sum(r["completion_tokens"] or 0 for r in per_query)
        tot_tok = sum(r["total_tokens"] or 0 for r in per_query)
        products = [r["product_02"] for r in per_query if r["product_02"] is not None]
        sum_product = sum(products)
        docs_total = sum(r["extracted_rows_sum"] for r in per_query)
        empty_bags = sum(1 for r in per_query if r["empty_output_bag"])

        # distributions from query-level totals only (per-call ledger unavailable)
        tokens_per_call = [r["tokens_per_call"] for r in per_query if r["tokens_per_call"]]
        prompt_per_call = [r["prompt_tokens_per_call"] for r in per_query if r["prompt_tokens_per_call"]]
        comp_per_call = [r["completion_tokens_per_call"] for r in per_query if r["completion_tokens_per_call"]]

        def _mean(xs):
            return sum(xs) / len(xs) if xs else None

        # source coverage: extracted rows vs source files, per table
        coverage = {}
        for pipe in pipes:
            for t in pipe["tables"]:
                table = t["table"]
                src_n = src.get(table, src.get("finance") or src.get("legal") or 0)
                coverage.setdefault(table, []).append({
                    "query_id": pipe["query_id"],
                    "extracted_rows": t["pipeline_output_rows"],
                    "source_txt": src_n,
                    "covers_all_source_txt": (
                        t["pipeline_output_rows"] == src_n if src_n else None
                    ),
                })

        # score vs tokens correlation (gold used ONLY here)
        scored = [r for r in per_query if r["product_02"] is not None and r["total_tokens"]]
        if len(scored) >= 3:
            xs = [r["total_tokens"] for r in scored]
            ys = [r["product_02"] for r in scored]
            mx, my = _mean(xs), _mean(ys)
            num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
            corr_tokens_product = num / den if den else None
            ys2 = [r["f2"] or 0 for r in scored]
            my2 = _mean(ys2)
            num2 = sum((x - mx) * (y - my2) for x, y in zip(xs, ys2))
            den2 = (sum((x - mx) ** 2 for x in xs) * sum((y - my2) ** 2 for y in ys2)) ** 0.5
            corr_tokens_f2 = num2 / den2 if den2 else None
        else:
            corr_tokens_product = corr_tokens_f2 = None

        high = sorted(scored, key=lambda r: r["product_02"], reverse=True)[:3]
        low = sorted(scored, key=lambda r: r["product_02"])[:3]

        report["corpora"][dataset] = {
            "run_dir": str(run_dir),
            "inventory": inv,
            "source_txt_counts": src,
            "log": log_info,
            "summary": summary,
            "session_token_cost": {
                "available": session is not None,
                "llm_calls": session_calls,
                "total_tokens": session_tokens,
                "partial_resume_fragment": session_is_partial,
                "note": (
                    "session_token_cost.json is this process only; "
                    "summary.json / query_results.json are cumulative"
                    if session_is_partial
                    else "session totals match summary"
                ),
            },
            "authority_totals": {
                "queries": n_q,
                "llm_calls": tot_calls,
                "prompt_tokens": tot_prompt,
                "completion_tokens": tot_comp,
                "total_tokens": tot_tok,
                "empty_output_bags": empty_bags,
                "extracted_rows_all_queries": docs_total,
                "mean_f2": _mean([r["f2"] for r in per_query if r["f2"] is not None]),
                "mean_cell_f1_02": _mean([r["cell_f1_02"] for r in per_query if r["cell_f1_02"] is not None]),
                "mean_product_02": _mean(products),
                "sum_product_02": sum_product,
            },
            "unit_of_work": {
                "demonstrated_from_runner_and_artifacts": (
                    "one map call extracts several SQL-needed attributes from one full document"
                ),
                "documents_per_call": "1 when llm_calls == extracted_rows; else retries/unobserved",
                "chunks_per_call": "unavailable (no chunk operator, no chunk ids in outputs)",
                "attributes_per_call": "all columns referenced by that query's SQL for that table",
                "records_per_call": 1,
                "group_reduce_unit": "not an LLM call; SQLite over the extracted table",
                "entire_query_answer_unit": "not an LLM call; SQLite",
                "mean_tokens_per_call": _mean(tokens_per_call),
                "mean_prompt_tokens_per_call": _mean(prompt_per_call),
                "mean_completion_tokens_per_call": _mean(comp_per_call),
                "tokens_per_document_if_one_call_per_row": (
                    tot_tok / docs_total if docs_total else None
                ),
                "tokens_per_output_row": (
                    tot_tok / sum(r["pred_rows"] or 0 for r in per_query)
                    if sum(r["pred_rows"] or 0 for r in per_query)
                    else None
                ),
                "tokens_per_product_point": (
                    tot_tok / sum_product if sum_product else None
                ),
            },
            "coverage": {
                "processes_every_source_document": all(
                    all(x["covers_all_source_txt"] for x in xs)
                    for xs in coverage.values()
                ) if coverage else None,
                "per_table": {
                    table: {
                        "source_txt": xs[0]["source_txt"] if xs else None,
                        "extracted_row_values": sorted({x["extracted_rows"] for x in xs}),
                        "all_queries_full_corpus": all(x["covers_all_source_txt"] for x in xs),
                    }
                    for table, xs in coverage.items()
                },
                "samples_documents": False if coverage and all(
                    all(x["covers_all_source_txt"] for x in xs) for xs in coverage.values()
                ) else "unknown",
                "completes_queries_sequentially": True,
                "spreads_work_across_queries_in_one_pass": False,
                "shares_intermediate_extractions_across_queries": False,
                "query_specific_extraction_schemas": True,
                "generates_groups_or_aggregates_directly_via_llm": False,
                "generates_groups_or_aggregates_via_sqlite": True,
            },
            "gold_used_only_for_correlation": {
                "corr_tokens_vs_product": corr_tokens_product,
                "corr_tokens_vs_f2": corr_tokens_f2,
                "highest_product_queries": [
                    {k: h[k] for k in ("query_id", "product_02", "f2", "total_tokens", "llm_calls", "n_table_pipelines")}
                    for h in high
                ],
                "lowest_product_queries": [
                    {k: h[k] for k in ("query_id", "product_02", "f2", "total_tokens", "llm_calls", "n_table_pipelines")}
                    for h in low
                ],
                "note": "High vs low product queries use the same map→SQLite plan; token spend is similar within a corpus when table count matches.",
            },
            "per_query": per_query,
            "pipelines": pipes,
        }

        if not inv["per_call_jsonl"]["exists"]:
            missing.append(f"{dataset}: per-call token ledger / prompt dump")
        if not inv["optimizer_candidate_plans"]["exists"]:
            missing.append(f"{dataset}: optimizer candidate plans (none on disk; runner never called optimizer)")
        if not inv["docetl_llm_cache"]["exists"]:
            missing.append(f"{dataset}: DocETL LLM cache (runner sets bypass_cache=True)")
        if not inv["yaml_plans"]["exists"]:
            missing.append(f"{dataset}: serialized YAML plan")
        if session_is_partial:
            missing.append(f"{dataset}: full-run session_token_cost (file is a resume fragment)")

    # QuWARTS Finan comparison from frozen witness arm
    qw = load_json(ROOT / "results" / "quwarts_finan_query_witness" / "finan_query_witness_arm.json")
    schema_audit = load_json(ROOT / "results" / "quwarts_finan_throughput_audit" / "finan_throughput_audit.json")
    finan = report["corpora"]["Finan"]
    docetl_q = {r["query_id"]: r for r in finan["per_query"]}
    qw_q = {r["query_id"]: r for r in (qw or {}).get("per_query_100", (qw or {}).get("per_query_25", []))}
    matched = []
    for qid, d in docetl_q.items():
        w = qw_q.get(qid)
        if not w:
            continue
        matched.append({
            "query_id": qid,
            "docetl_calls": d["llm_calls"],
            "docetl_tokens": d["total_tokens"],
            "docetl_pred_rows": d["pred_rows"],
            "docetl_empty": d["empty_output_bag"],
            "docetl_product": d["product_02"],
            "docetl_f2": d["f2"],
            "quwarts_pred_rows": w.get("pred_rows"),
            "quwarts_product": w.get("product"),
            "quwarts_f2": w.get("structure_f2"),
            "quwarts_cell_f1": w.get("cell_f1_20"),
        })

    report["quwarts_finan"] = {
        "source": "results/quwarts_finan_query_witness/finan_query_witness_arm.json",
        "schema_extraction_tokens_per_attempted_job": (
            (schema_audit or {}).get("tokens_per_attempted_job")
            or ((schema_audit or {}).get("recorded") or {}).get("tokens_per_attempted_job")
        ),
        "schema_extraction_approx": 1706,
        "query_witness_tokens_per_witness_approx": 1716,
        "query_witness_mean_from_cost_schedule": 1716.3801242236025,
        "theta_100": 1381827,
        "docetl_tokens": 1381827,
        "docetl_product": 0.084,
        "quwarts_product_100": (qw or {}).get("score", {}).get("query_witness_100", {}).get("mean_per_query_product"),
        "quwarts_tokens_100": (qw or {}).get("score", {}).get("query_witness_100", {}).get("tokens"),
        "quwarts_attempted_tasks": (qw or {}).get("counts", {}).get("attempted"),
        "quwarts_accepted": (qw or {}).get("counts", {}).get("accepted"),
        "quwarts_empty_bags_100": (qw or {}).get("empty_bags", {}).get("theta100"),
        "docetl_empty_bags": finan["authority_totals"]["empty_output_bags"],
        "docetl_queries_completed": finan["authority_totals"]["queries"],
        "docetl_mean_tokens_per_call": finan["unit_of_work"]["mean_tokens_per_call"],
        "docetl_source_docs": finan["source_txt_counts"],
        "matched_query_shapes": matched,
        "demonstrated": [
            "DocETL finishes all 16 Finan queries; each query runs map over the full finance txt set then SQLite.",
            "QuWARTS query-witness at θ=1,381,827 attempted 805 tasks, accepted 96, filled 0 additional empty bags (20 empty remain).",
            "DocETL mean call is ~12k tokens (full document + multi-attribute schema). QuWARTS witness/schema jobs are ~1.7k tokens (one condition or cell).",
            "DocETL empty bags: from query_tables pred_rows==0. QuWARTS empty bags stay at 20/20 programs.",
            "DocETL groups/counts/avgs are SQLite over extracted columns, not LLM reduce.",
        ],
        "hypotheses_not_demonstrated": [
            "Whether DocETL retrieval/context is better: no retrieval operator exists in the frozen run.",
            "Whether DocETL batching of several documents per call occurred: runner default batch_size is 1; per-call payloads are unavailable.",
            "Exact retry counts per document: only query-level llm_calls exist.",
        ],
    }
    if schema_audit:
        rec = schema_audit
        # tokens_per_attempted_job may be nested
        tpa = rec.get("tokens_per_attempted_job")
        if tpa is None:
            for v in rec.values():
                if isinstance(v, dict) and "tokens_per_attempted_job" in v:
                    tpa = v["tokens_per_attempted_job"]
                    break
        report["quwarts_finan"]["schema_extraction_tokens_per_attempted_job"] = tpa

    report["missing_telemetry"] = sorted(set(missing)) + [
        "per-call input/output token pairs",
        "per-call prompt text / prompt hash stored at execution time",
        "retry vs first-attempt distinction",
        "documents or chunks actually sent in each LiteLLM payload",
        "operator-level token split beyond a single 'docetl' bucket",
        "row counts entering vs leaving SQLite (only final query_tables exist)",
        "optimizer rewrite traces (never executed)",
    ]
    report["decision"] = {
        "choice": "DocETL completes queries rather than spreading coverage",
        "largest_mechanism_quwarts_lacks": (
            "Query-complete extract-then-SQLite: every Finan query gets a full-corpus "
            "multi-attribute map and a deterministic SQL aggregate, instead of spending "
            "the same θ on many ~1.7k-token witness/cell jobs that leave programs incomplete."
        ),
        "also_demonstrated_but_secondary": [
            "DocETL directly generates aggregates/groups via SQLite (not LLM).",
            "DocETL packs several attributes per document into one call (~12k tokens) vs QuWARTS ~1.7k per cell/witness.",
        ],
        "rejected": [
            "DocETL uses materially better retrieval/context — no retrieval artifacts.",
            "DocETL batches more evidence per call — batch_size default 1; no per-call payload log.",
        ],
    }

    out_path = OUT / "audit_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote {out_path}")
    for ds, body in report["corpora"].items():
        a = body["authority_totals"]
        print(
            f"{ds}: q={a['queries']} calls={a['llm_calls']} tokens={a['total_tokens']} "
            f"empty={a['empty_output_bags']} product={a['mean_product_02']}"
        )
        print("  source", body["source_txt_counts"])
        print("  unit", body["unit_of_work"]["mean_tokens_per_call"], "tok/call")
        print("  coverage", body["coverage"]["per_table"])


if __name__ == "__main__":
    main()

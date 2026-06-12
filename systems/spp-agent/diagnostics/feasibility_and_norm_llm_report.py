#!/usr/bin/env python3
"""Part 1: corpus-infeasible exclusion in five-slice benchmark.
Part 2: best norm=llm probe config on three agg_filter normalization failures.
"""

from __future__ import annotations

import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.tools import load_agent_cache, lock_toolkit_corpus_to_probe
from data.aggregation_slices import AGGREGATION_SLICE_ORDER
from data.instance_builder import Instance, build_instance
from data.query_alignment import prepare_aggregation_slice_instance
from diagnostics.five_slice_benchmark import (
    _evaluate_slice,
    _macro_f1_for_query,
    _stable_slice_seed,
)
from optimizer.config_space import parse_config_id
from optimizer.materialize import materialize_database
from pipeline.evaluation import _eval_context
from pipeline.extraction import extract_documents
from pipeline.population import apply_population
from utils.config import load_config

TARGET_QUERIES = [
    "mixed_queries_filter_agg_5",
    "mixed_queries_filter_agg_3",
    "mixed_queries_filter_agg_player_3",
]


def _best_norm_llm_config(toolkit, instance, queries) -> tuple[str, float]:
    """Pick probe config with norm=llm having highest mean macro-F1 on agg_only."""
    settings, parser, attributes, _ = _eval_context(instance)
    candidates = [cid for cid in toolkit.probe_data.config_ids if "|norm=llm|" in cid]
    best_id = ""
    best_mean = -1.0
    for cid in candidates:
        db = materialize_database(toolkit.probe_data, cid, instance.schema)
        scores = []
        for q in queries:
            try:
                row = _macro_f1_for_query(instance, db, q, parser, attributes, settings)
                scores.append(row["macro_f1"])
            except Exception:
                scores.append(0.0)
        mean = sum(scores) / len(scores) if scores else 0.0
        if mean > best_mean:
            best_mean = mean
            best_id = cid
    return best_id, best_mean


def main() -> None:
    cfg = load_config()
    cache_path = Path(cfg["paths"]["results_dir"]) / cfg.get("phase1", {}).get(
        "probe_context_cache", "phase1_agg_only_probe_context.json"
    )

    print("## Part 1 — Corpus-infeasible exclusion (five-slice benchmark)\n")
    slice_results = []
    for slice_name in AGGREGATION_SLICE_ORDER:
        print(f"Evaluating {slice_name}...", flush=True)
        slice_results.append(_evaluate_slice(slice_name, cache_path=cache_path, cfg=cfg))

    print()
    print("| Slice | # queries | Excluded (infeasible) | Mean F1 (feasible only) |")
    print("|-------|-----------|----------------------|-------------------------|")
    for r in slice_results:
        print(
            f"| {r['slice']} | {r['n_queries']} | {r.get('n_corpus_infeasible', 0)} | "
            f"{r.get('mean_f1_feasible', 0.0):.4f} |"
        )

    infeasible_detail = [
        (r["slice"], row["query_id"], row.get("missing_corpus_literals", []))
        for r in slice_results
        for row in r.get("per_query", [])
        if row.get("corpus_infeasible")
    ]
    if infeasible_detail:
        print("\nExcluded queries:")
        for slice_name, qid, missing in infeasible_detail:
            print(f"- {slice_name} / {qid}: missing literals {missing}")

    print("\n## Part 2 — Best norm=llm probe config on three normalization failures\n")
    toolkit = load_agent_cache(cache_path)
    lock_toolkit_corpus_to_probe(toolkit)
    base = build_instance("Player", include_ground_truth=False)
    agg_only_pool, _ = prepare_aggregation_slice_instance(
        base,
        slice_name="agg_only",
        num_docs=int(cfg.get("phase0", {}).get("num_docs", 20)),
        num_eval_queries=9999,
        seed=_stable_slice_seed(int(cfg["experiment"]["seed"]), "agg_only"),
        query_table_filter=set(cfg.get("phase0", {}).get("table_filter", ["player"])),
    )
    probe_instance = Instance(
        dataset_name="Player",
        corpus=list(toolkit.corpus),
        queries=list(agg_only_pool.queries),
        schema=agg_only_pool.schema,
    )
    best_config, agg_only_mean = _best_norm_llm_config(
        toolkit, probe_instance, agg_only_pool.queries
    )
    print(f"Best norm=llm config (agg_only mean F1={agg_only_mean:.4f}):\n`{best_config}`\n")

    phase0 = cfg.get("phase0", {})
    agg_filter_instance, _ = prepare_aggregation_slice_instance(
        base,
        slice_name="agg_filter",
        num_docs=int(phase0.get("num_docs", 20)),
        num_eval_queries=9999,
        seed=_stable_slice_seed(int(cfg["experiment"]["seed"]), "agg_filter"),
        query_table_filter=set(phase0.get("table_filter", ["player"])),
    )
    extraction = extract_documents(
        agg_filter_instance.corpus,
        agg_filter_instance.schema,
        cfg["llm"]["extraction_model"],
    )
    db, _ = apply_population(
        extraction, parse_config_id(best_config), agg_filter_instance.schema
    )
    settings, parser, attributes, _ = _eval_context(agg_filter_instance)
    query_by_id = {q.get("query_id"): q for q in agg_filter_instance.queries}

    print("| Query | F1 (norm=llm) |")
    print("|-------|---------------|")
    for qid in TARGET_QUERIES:
        q = query_by_id.get(qid)
        if q is None:
            print(f"| {qid} | N/A |")
            continue
        try:
            row = _macro_f1_for_query(
                agg_filter_instance, db, q, parser, attributes, settings
            )
            f1 = row["macro_f1"]
        except Exception:
            f1 = 0.0
        print(f"| {qid} | {f1:.4f} |")


if __name__ == "__main__":
    main()

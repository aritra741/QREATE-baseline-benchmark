#!/usr/bin/env python3
"""Evaluate budgeted SPP agent on agg_only and agg_filter slices."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.tools import load_agent_cache, lock_toolkit_corpus_to_probe
from data.instance_builder import Instance, build_instance
from data.query_alignment import corpus_alignment_metadata, prepare_aggregation_slice_instance
from pipeline.budgeted_pipeline import run_budgeted_spp_pipeline
from stage5.per_query_eval import best_single_config_mean_f1, spp_routing_mean_f1
from utils.config import load_config
from utils.logging import setup_logger


def _stable_slice_seed(base_seed: int, slice_name: str) -> int:
    return base_seed + sum(ord(c) for c in slice_name) % 1000


def _evaluate_slice(
    slice_name: str,
    *,
    cfg: dict,
    offline: bool,
    token_budget: int,
    max_rounds: int,
) -> dict:
    phase0 = cfg.get("phase0", {})
    seed = int(cfg["experiment"]["seed"])
    num_docs = int(phase0.get("num_docs", 20))
    table_filter = set(phase0.get("table_filter", ["player"]))

    base = build_instance("Player", include_ground_truth=False)
    slice_instance, _ = prepare_aggregation_slice_instance(
        base,
        slice_name=slice_name,
        num_docs=num_docs,
        num_eval_queries=9999,
        seed=_stable_slice_seed(seed, slice_name),
        query_table_filter=table_filter,
    )

    shared_extraction = None
    instance = slice_instance
    if offline and slice_name == "agg_only":
        cache_path = SPP_ROOT / "results" / "phase1_agg_only_probe_context.json"
        if cache_path.exists():
            toolkit = load_agent_cache(cache_path)
            lock_toolkit_corpus_to_probe(toolkit)
            shared_extraction = toolkit.probe_data.extraction
            instance = Instance(
                dataset_name="Player",
                corpus=list(toolkit.corpus),
                queries=list(slice_instance.queries),
                schema=slice_instance.schema,
                metadata={
                    **corpus_alignment_metadata(toolkit.corpus),
                    "aggregation_slice": slice_name,
                },
            )

    result = run_budgeted_spp_pipeline(
        instance,
        token_budget=token_budget,
        max_rounds=max_rounds,
        use_heuristic_agent=offline,
        use_heuristic_demand=offline,
        shared_extraction=shared_extraction,
    )

    query_ids = [str(q.get("query_id", i)) for i, q in enumerate(instance.queries, start=1)]
    per_query_by_config = {
        p["config_id"]: p.get("per_query_f1", {}) for p in result.probed_configs
    }
    best_cid, best_single = best_single_config_mean_f1(per_query_by_config)
    routing = result.routing_table.query_to_config
    spp_mean = spp_routing_mean_f1(per_query_by_config, routing, query_ids)

    return {
        "slice": slice_name,
        "n_queries": len(query_ids),
        "best_single_config_id": best_cid,
        "best_single_config_mean_f1": round(best_single, 4),
        "spp_routing_mean_f1": round(spp_mean, 4),
        "configs_materialized": len(result.probed_configs),
        "budget_spent": result.token_budget_spent,
        "budget_total": result.token_budget_total,
        "final_routing": routing,
        "probed_configs": [
            {
                "config_id": p["config_id"],
                "settings": p["settings"],
                "mean_f1": p.get("mean_f1"),
                "per_query_f1": p.get("per_query_f1"),
            }
            for p in result.probed_configs
        ],
        "demand_profile": result.demand_profile,
        "supply_profile": result.supply_profile,
    }


def _print_table(rows: list[dict]) -> None:
    headers = [
        "Slice",
        "# queries",
        "Best single config mean F1",
        "SPP routing mean F1",
        "Configs materialized",
        "Budget spent",
    ]
    print("\n" + " | ".join(headers))
    print("-" * 90)
    for r in rows:
        print(
            f"{r['slice']} | {r['n_queries']} | "
            f"{r['best_single_config_mean_f1']:.4f} | "
            f"{r['spp_routing_mean_f1']:.4f} | "
            f"{r['configs_materialized']} | {r['budget_spent']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Budgeted SPP agent evaluation.")
    parser.add_argument(
        "--slices",
        nargs="+",
        default=["agg_only", "agg_filter"],
        help="Aggregation slices to evaluate.",
    )
    parser.add_argument("--offline", action="store_true", help="Heuristic demand + agent (no LLM).")
    parser.add_argument("--token-budget", type=int, default=None)
    parser.add_argument("--max-rounds", type=int, default=8)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    logger = setup_logger("spp.budgeted_eval")
    cfg = load_config()
    token_budget = int(args.token_budget or cfg.get("token_budget", 50_000))

    rows: list[dict] = []
    for slice_name in args.slices:
        logger.info("Evaluating slice=%s offline=%s budget=%d", slice_name, args.offline, token_budget)
        row = _evaluate_slice(
            slice_name,
            cfg=cfg,
            offline=args.offline,
            token_budget=token_budget,
            max_rounds=args.max_rounds,
        )
        rows.append(row)

    _print_table(rows)

    out_path = args.output or (SPP_ROOT / "results" / "budgeted_agent_eval.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"slices": rows}, indent=2), encoding="utf-8")
    logger.info("Wrote %s", out_path)


if __name__ == "__main__":
    main()

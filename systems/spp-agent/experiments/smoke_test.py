#!/usr/bin/env python3
"""Fast end-to-end smoke test for the SPP pipeline (minutes, not hours)."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from data.instance_builder import Instance, build_instance
from data.query_alignment import prepare_aligned_instance
from optimizer.config_space import generate_config_space
from optimizer.probing import run_probes
from pipeline.evaluation import evaluate_config
from pipeline.full_pipeline import run_spp_pipeline
from stage4.query_clustering import cluster_workload
from thresholds.schema import load_thresholds
from utils.config import load_config
from utils.logging import log_step, setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SPP agent smoke test (minimal docs/configs/queries).")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING (overrides config/env)")
    parser.add_argument("--num-docs", type=int, default=None)
    parser.add_argument("--num-configs", type=int, default=None)
    parser.add_argument("--num-pairs", type=int, default=None)
    parser.add_argument("--num-eval-queries", type=int, default=None)
    return parser.parse_args()


def _prepare_smoke_instance(
    instance: Instance,
    *,
    num_docs: int,
    num_eval_queries: int,
    seed: int,
) -> tuple[Instance, set[str]]:
    return prepare_aligned_instance(
        instance,
        num_docs=num_docs,
        num_eval_queries=num_eval_queries,
        seed=seed,
    )


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.smoke")
    cfg = load_config()
    smoke = cfg.get("smoke_test", {})

    num_docs = args.num_docs or int(smoke.get("num_docs", 10))
    num_configs = args.num_configs or int(smoke.get("num_configs", 4))
    num_pairs = args.num_pairs or int(smoke.get("num_judge_pairs", 5))
    num_eval_queries = args.num_eval_queries or int(smoke.get("num_eval_queries", 3))

    llm = cfg["llm"]
    logger.info("=" * 60)
    logger.info("SPP SMOKE TEST")
    logger.info("=" * 60)
    logger.info(
        "Limits: docs=%d configs=%d judge_pairs=%d eval_queries=%d",
        num_docs,
        num_configs,
        num_pairs,
        num_eval_queries,
    )
    logger.info(
        "LLM profile=%s provider=%s extraction=%s judge=%s base_url=%s",
        llm.get("profile"),
        llm.get("provider"),
        llm.get("extraction_model"),
        llm.get("judge_model"),
        llm.get("base_url"),
    )

    seed = int(cfg["experiment"]["seed"])
    rng = random.Random(seed)

    with log_step(logger, "load_instance", dataset="Player"):
        instance = build_instance("Player", include_ground_truth=False)
        instance, required_tables = _prepare_smoke_instance(
            instance,
            num_docs=num_docs,
            num_eval_queries=num_eval_queries,
            seed=seed,
        )
        logger.info(
            "Aligned instance corpus=%d queries=%d required_tables=%s",
            len(instance.corpus),
            len(instance.queries),
            sorted(required_tables),
        )
        for doc in instance.corpus:
            logger.info("  doc id=%s chars=%d", doc["doc_id"], len(doc["text"]))
        for q in instance.queries:
            logger.info("  query id=%s sql=%s", q["query_id"], q["sql_query"][:80])

    all_configs = generate_config_space()
    rng.shuffle(all_configs)
    # Run a row-retaining config first (coverage assert runs on config 1).
    probe_configs = sorted(
        all_configs[: num_configs * 4],
        key=lambda c: (c.miss_strategy == "drop", c.norm_strategy == "llm"),
    )[:num_configs]
    logger.info("Selected probe configs: %s", [c.config_id for c in probe_configs])

    with log_step(logger, "run_probes"):
        probe_data = run_probes(
            instance,
            instance.schema,
            probe_configs,
            judge_pair_budget=num_pairs,
            seed=seed,
            corpus_docs=instance.corpus,
            required_tables=required_tables,
            eval_queries=instance.queries,
        )

    pipeline_result = None
    with log_step(logger, "run_pipeline"):
        query_clusters = cluster_workload(instance.queries, seed=seed)
        thresholds = load_thresholds()
        pipeline_result = run_spp_pipeline(
            probe_data,
            queries=instance.queries,
            schema=instance.schema,
            thresholds=thresholds,
            token_budget=int(cfg.get("token_budget", 500_000)),
            seed=seed,
            instance=instance,
            query_clusters=query_clusters,
        )
        logger.info(
            "Pipeline: surrogate=%s algorithm=%s selected=%s routing=%s",
            pipeline_result.best_surrogate,
            pipeline_result.best_algorithm,
            pipeline_result.selected_configs,
            dict(pipeline_result.routing_table.cluster_to_config)
            if pipeline_result.routing_table
            else {},
        )

    true_errors: dict[str, float] = {}
    with log_step(logger, "post_hoc_eval", configs=len(probe_data.config_ids)):
        for cid in probe_data.config_ids:
            true_errors[cid] = evaluate_config(
                instance,
                cid,
                probe_data.databases[cid],
                max_queries=num_eval_queries,
            )

    first_db_rows = {t: len(df) for t, df in next(iter(probe_data.databases.values())).items()}

    report = {
        "mode": "smoke_test",
        "dataset": "Player",
        "required_tables": sorted(required_tables),
        "rows_by_table": first_db_rows,
        "num_docs": len(instance.corpus),
        "num_configs": len(probe_data.config_ids),
        "num_pairs": len(probe_data.pairwise_comparisons),
        "num_eval_queries": num_eval_queries,
        "llm_profile": llm.get("profile"),
        "total_token_cost": probe_data.total_cost,
        "config_table": [
            {
                "config_id": cid,
                "glass_box_score": probe_data.glass_box_composites.get(cid),
                "btl_score": probe_data.btl_scores.get(cid),
                "true_error": true_errors.get(cid),
                "numeric_type_success_rate": probe_data.tier1_signals[cid].get("numeric_type_success_rate"),
                "required_table_row_count": probe_data.tier1_signals[cid].get("required_table_row_count"),
            }
            for cid in probe_data.config_ids
        ],
        "judge_comparisons": probe_data.pairwise_comparisons,
        "btl_report": probe_data.btl_report,
        "pipeline": {
            "best_surrogate": pipeline_result.best_surrogate if pipeline_result else None,
            "best_algorithm": pipeline_result.best_algorithm if pipeline_result else None,
            "selected_configs": pipeline_result.selected_configs if pipeline_result else [],
            "routing_table": (
                dict(pipeline_result.routing_table.cluster_to_config)
                if pipeline_result and pipeline_result.routing_table
                else {}
            ),
            "cluster_surrogates": (
                {str(k): v for k, v in pipeline_result.cluster_surrogates.items()}
                if pipeline_result
                else {}
            ),
        },
    }

    out_path = Path(cfg["paths"]["results_dir"]) / "smoke_test_Player.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    logger.info("=" * 60)
    logger.info("SMOKE TEST COMPLETE")
    logger.info("Saved report: %s", out_path)
    logger.info("Rows by table (first config): %s", first_db_rows)
    logger.info("Required table player rows: %s", first_db_rows.get("player", 0))
    logger.info("Total LLM token cost (probe phase): %.0f", probe_data.total_cost)
    for row in report["config_table"]:
        logger.info(
            "  %s glass_box=%.4f btl=%s true_error=%.4f",
            row["config_id"],
            row["glass_box_score"] or 0.0,
            row["btl_score"],
            row["true_error"] or 0.0,
        )
    logger.info("=" * 60)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

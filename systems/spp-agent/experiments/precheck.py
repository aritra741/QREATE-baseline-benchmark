#!/usr/bin/env python3
"""Precheck: validate glass-box and BTL signals against post-hoc true error."""

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

from data.dataset_registry import normalize_dataset_name, precheck_path, results_dir_for_dataset
from data.instance_builder import build_instance
from data.query_alignment import prepare_aligned_instance
from experiments.ranking_metrics import proxy_vs_true_correlation
from optimizer.config_space import generate_config_space
from optimizer.probing import run_probes
from pipeline.evaluation import evaluate_config
from utils.config import load_config
from utils.logging import log_step, setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SPP precheck experiment.")
    parser.add_argument("--dataset", default="Player", help="Bench-U dataset (Player, Med, ...)")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING")
    parser.add_argument("--num-docs", type=int, default=None)
    parser.add_argument("--num-configs", type=int, default=None)
    parser.add_argument("--num-pairs", type=int, default=None)
    parser.add_argument("--num-eval-queries", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.precheck")
    cfg = load_config()
    dataset = normalize_dataset_name(args.dataset)
    seed = int(cfg["experiment"]["seed"])
    rng = random.Random(seed)

    precheck_cfg = cfg.get("precheck", {})
    probing_cfg = cfg["probing"]

    num_docs = args.num_docs or int(precheck_cfg.get("num_docs", probing_cfg.get("min_probe_docs", 20)))
    num_configs = args.num_configs or int(precheck_cfg.get("num_configs", probing_cfg["num_probe_configs"]))
    num_pairs = args.num_pairs or int(precheck_cfg.get("num_judge_pairs", probing_cfg["judge_pair_budget"]))
    num_eval_queries = args.num_eval_queries or int(precheck_cfg.get("num_eval_queries", 3))
    llm = cfg["llm"]

    logger.info("=" * 60)
    logger.info("SPP PRECHECK")
    logger.info("=" * 60)
    logger.info(
        "docs=%d configs=%d judge_pairs=%d eval_queries=%d seed=%d",
        num_docs,
        num_configs,
        num_pairs,
        num_eval_queries,
        seed,
    )
    logger.info(
        "LLM profile=%s extraction=%s judge=%s",
        llm.get("profile"),
        llm.get("extraction_model"),
        llm.get("judge_model"),
    )

    with log_step(logger, "load_instance", dataset=dataset):
        instance = build_instance(dataset, include_ground_truth=False)
        instance, required_tables = prepare_aligned_instance(
            instance,
            num_docs=num_docs,
            num_eval_queries=num_eval_queries,
            seed=seed,
            dataset=dataset,
        )
        logger.info(
            "Aligned corpus=%d queries=%d required_tables=%s",
            len(instance.corpus),
            len(instance.queries),
            sorted(required_tables),
        )

    all_configs = generate_config_space()
    if len(all_configs) < num_configs:
        raise RuntimeError(f"Config space has only {len(all_configs)} configs, need {num_configs}.")

    rng.shuffle(all_configs)
    probe_configs = all_configs[:num_configs]
    logger.info("Probe configs: %s", [c.config_id for c in probe_configs])

    with log_step(logger, "run_probes", configs=num_configs, pairs=num_pairs):
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

    true_errors: dict[str, float] = {}
    with log_step(logger, "post_hoc_eval", configs=len(probe_data.config_ids)):
        for idx, cid in enumerate(probe_data.config_ids, start=1):
            logger.info("Evaluating config %d/%d: %s", idx, len(probe_data.config_ids), cid)
            true_errors[cid] = evaluate_config(
                instance,
                cid,
                probe_data.databases[cid],
                max_queries=num_eval_queries,
            )
    probe_data.true_errors = true_errors

    glass_corr = proxy_vs_true_correlation(probe_data.glass_box_composites, true_errors)
    btl_corr = proxy_vs_true_correlation(probe_data.btl_scores, true_errors)
    logger.info("Glass-box vs true: %s", glass_corr)
    logger.info("BTL vs true: %s", btl_corr)

    config_table = [
        {
            "config_id": cid,
            "glass_box_score": probe_data.glass_box_composites.get(cid),
            "btl_score": probe_data.btl_scores.get(cid),
            "true_error": true_errors.get(cid),
            "numeric_type_success_rate": probe_data.tier1_signals[cid].get("numeric_type_success_rate"),
            "required_table_row_count": probe_data.tier1_signals[cid].get("required_table_row_count"),
            "numeric_column_checks": probe_data.tier1_signals[cid].get("numeric_column_checks"),
        }
        for cid in probe_data.config_ids
    ]

    report = {
        "dataset": dataset,
        "required_tables": sorted(required_tables),
        "num_docs": len(instance.corpus),
        "num_configs": len(probe_data.config_ids),
        "num_pairs": len(probe_data.pairwise_comparisons),
        "num_eval_queries": num_eval_queries,
        "glass_box_vs_true": glass_corr,
        "btl_vs_true": btl_corr,
        "btl_report": probe_data.btl_report,
        "config_table": config_table,
    }

    out_path = precheck_path(results_dir_for_dataset(dataset), dataset)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    logger.info("Saved precheck report to %s", out_path)
    logger.info("Precheck complete. Review results before Phase 0.")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Phase 0 — build instance × surrogate reward table (Player only, aggregation slices)."""

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

from data.aggregation_slices import group_queries_by_aggregation_slice
from data.instance_builder import build_instance
from data.query_alignment import (
    corpus_entity_types,
    filter_queries_by_corpus_coverage,
    prepare_aggregation_slice_instance,
)
from experiments.checkpoint import config_fingerprint, load_checkpoint, save_checkpoint
from optimizer.config_space import generate_config_space
from optimizer.materialize import all_config_ids, materialize_database
from optimizer.probing import run_probes
from pipeline.evaluation import evaluate_spp_set
from surrogates.registry import MAIN_SURROGATES, build_surrogate
from utils.config import load_config
from utils.logging import log_step, setup_logger

CHECKPOINT_VERSION = 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 0 Player reward table (aggregation slices).")
    parser.add_argument("--log-level", default=None)
    parser.add_argument(
        "--slices",
        nargs="*",
        default=None,
        help="Aggregation slice names, e.g. agg_only agg_filter agg_join",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore checkpoint and restart from scratch.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not load an existing checkpoint (same as --fresh).",
    )
    return parser.parse_args()


def _select_configs(surrogate, candidates: list[str], budget: int) -> list[str]:
    ranked = surrogate.rank(candidates)
    return ranked[: max(1, budget)]


def _feasible_slice_counts(base_instance) -> dict[str, int]:
    corpus_types = corpus_entity_types(base_instance.corpus)
    counts: dict[str, int] = {}
    for name, queries in group_queries_by_aggregation_slice(base_instance.queries).items():
        kept = filter_queries_by_corpus_coverage(queries, base_instance.schema, corpus_types)
        counts[name] = len(kept)
    return counts


def _resolve_slice_names(base_instance, phase0: dict, cli_slices: list[str] | None) -> list[str]:
    min_queries = int(phase0.get("min_queries_per_slice", 3))
    feasible_counts = _feasible_slice_counts(base_instance)

    configured = phase0.get("workload_slices")
    if isinstance(configured, list) and configured and isinstance(configured[0], str):
        candidate_names = configured
    elif isinstance(configured, list) and configured and isinstance(configured[0], dict):
        candidate_names = [s["name"] for s in configured]
    else:
        candidate_names = [
            name for name, count in feasible_counts.items() if count >= min_queries
        ]

    if cli_slices:
        allowed = {s.lower() for s in cli_slices}
        candidate_names = [s for s in candidate_names if s.lower() in allowed]

    resolved = [s for s in candidate_names if feasible_counts.get(s, 0) >= min_queries]
    if not resolved:
        raise RuntimeError(
            f"No eligible aggregation slices with >= {min_queries} corpus-feasible queries. "
            f"Counts: {feasible_counts}"
        )
    return resolved


def _build_report_meta(
    *,
    slice_names: list[str],
    slice_counts: dict[str, int],
    corpus_types: set[str],
    budget_levels: list[int],
    surrogates: list[str],
    num_configs: int,
    fingerprint: dict,
) -> dict:
    return {
        "dataset": "Player",
        "phase": 0,
        "workload_type": "aggregation_only",
        "slice_query_counts": slice_counts,
        "slice_query_counts_note": (
            "Counts after excluding queries referencing tables without text corpus (e.g. owner)."
        ),
        "corpus_entity_types": sorted(corpus_types),
        "slices_planned": slice_names,
        "budget_levels": budget_levels,
        "surrogates": surrogates,
        "num_probe_configs": num_configs,
        "config_fingerprint": fingerprint,
    }


def _write_outputs(
    out_path: Path,
    checkpoint_path: Path,
    report_meta: dict,
    rows: list[dict],
    *,
    completed_slices: list[str],
    status: str,
    logger,
) -> None:
    slices_evaluated = list(dict.fromkeys(row["slice"] for row in rows))
    report = {
        **report_meta,
        "status": status,
        "slices_evaluated": slices_evaluated,
        "completed_slices": completed_slices,
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    checkpoint = {
        "version": CHECKPOINT_VERSION,
        "status": status,
        **report_meta,
        "completed_slices": completed_slices,
        "rows": rows,
    }
    save_checkpoint(checkpoint_path, checkpoint)
    logger.info("Checkpoint saved (%s). rows=%d completed_slices=%s", status, len(rows), completed_slices)


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.phase0")
    cfg = load_config()
    phase0 = cfg.get("phase0", {})
    precheck = cfg.get("precheck", {})
    seed = int(cfg["experiment"]["seed"])
    rng = random.Random(seed)

    num_docs = int(phase0.get("num_docs", precheck.get("num_docs", 20)))
    num_configs = int(phase0.get("num_probe_configs", precheck.get("num_configs", 8)))
    num_pairs = int(phase0.get("num_judge_pairs", precheck.get("num_judge_pairs", 14)))
    num_eval_queries = int(phase0.get("num_eval_queries", precheck.get("num_eval_queries", 3)))
    budget_levels = [int(b) for b in phase0.get("budget_levels", [1, 2])]
    surrogates = phase0.get("surrogates", list(MAIN_SURROGATES.keys()))
    table_filter = set(phase0.get("table_filter", ["player"]))

    results_dir = Path(cfg["paths"]["results_dir"])
    out_path = results_dir / "phase0_reward_table_Player.json"
    checkpoint_path = results_dir / "phase0_reward_table_Player.checkpoint.json"

    base_instance = build_instance("Player", include_ground_truth=False)
    slice_names = _resolve_slice_names(base_instance, phase0, args.slices)
    slice_counts = _feasible_slice_counts(base_instance)
    corpus_types = corpus_entity_types(base_instance.corpus)

    all_configs = generate_config_space()
    rng.shuffle(all_configs)
    probe_config_list = all_configs[:num_configs]
    candidate_ids = all_config_ids()

    fingerprint = config_fingerprint(
        seed=seed,
        num_docs=num_docs,
        num_probe_configs=num_configs,
        num_judge_pairs=num_pairs,
        num_eval_queries=num_eval_queries,
        budget_levels=budget_levels,
        surrogates=surrogates,
        slice_names=slice_names,
        probe_config_ids=[c.config_id for c in probe_config_list],
        table_filter=sorted(table_filter),
    )

    report_meta = _build_report_meta(
        slice_names=slice_names,
        slice_counts=slice_counts,
        corpus_types=corpus_types,
        budget_levels=budget_levels,
        surrogates=surrogates,
        num_configs=num_configs,
        fingerprint=fingerprint,
    )

    rows: list[dict] = []
    completed_slices: list[str] = []

    resume = not (args.fresh or args.no_resume)
    if resume:
        checkpoint = load_checkpoint(checkpoint_path)
        if checkpoint:
            saved_fp = checkpoint.get("config_fingerprint")
            if saved_fp != fingerprint:
                raise RuntimeError(
                    "Checkpoint config fingerprint mismatch. "
                    "Use --fresh to restart, or align config with the checkpoint run. "
                    f"checkpoint={saved_fp} current={fingerprint}"
                )
            rows = list(checkpoint.get("rows", []))
            completed_slices = list(checkpoint.get("completed_slices", []))
            logger.info(
                "Resuming from checkpoint: completed_slices=%s rows=%d",
                completed_slices,
                len(rows),
            )

    pending_slices = [s for s in slice_names if s not in completed_slices]

    logger.info("Phase 0 Player reward table (aggregation-only)")
    logger.info("planned=%s pending=%s", slice_names, pending_slices)
    logger.info("slice_query_counts=%s", slice_counts)
    logger.info("budgets=%s surrogates=%s", budget_levels, surrogates)

    if not pending_slices:
        logger.info("All slices already complete.")
        _write_outputs(
            out_path,
            checkpoint_path,
            report_meta,
            rows,
            completed_slices=completed_slices,
            status="complete",
            logger=logger,
        )
        print(json.dumps(json.loads(out_path.read_text()), indent=2))
        return

    for slice_name in pending_slices:
        logger.info("=" * 60)
        logger.info("Aggregation slice: %s (pool=%d queries)", slice_name, slice_counts.get(slice_name, 0))

        slice_rows: list[dict] = []
        try:
            with log_step(logger, f"slice_{slice_name}_setup"):
                instance, required_tables = prepare_aggregation_slice_instance(
                    base_instance,
                    slice_name=slice_name,
                    num_docs=num_docs,
                    num_eval_queries=num_eval_queries,
                    seed=seed + hash(slice_name) % 1000,
                    query_table_filter=table_filter,
                )
                logger.info(
                    "Slice %s docs=%d eval_queries=%d required_tables=%s",
                    slice_name,
                    len(instance.corpus),
                    len(instance.queries),
                    sorted(required_tables),
                )

            with log_step(logger, f"slice_{slice_name}_probes"):
                probe_data = run_probes(
                    instance,
                    instance.schema,
                    probe_config_list,
                    judge_pair_budget=num_pairs,
                    seed=seed,
                    corpus_docs=instance.corpus,
                    required_tables=required_tables,
                    eval_queries=instance.queries,
                )

            for surrogate_name in surrogates:
                surrogate = build_surrogate(surrogate_name, seed=seed)
                surrogate.fit(probe_data)

                for budget in budget_levels:
                    selected = _select_configs(surrogate, candidate_ids, budget)
                    dbs = {
                        cid: materialize_database(probe_data, cid, instance.schema)
                        for cid in selected
                    }
                    true_spp_error = evaluate_spp_set(instance, selected, dbs)

                    row = {
                        "dataset": "Player",
                        "slice": slice_name,
                        "num_queries": len(instance.queries),
                        "num_queries_in_slice_pool": slice_counts.get(slice_name, 0),
                        "corpus_entity_types": instance.metadata.get("corpus_entity_types"),
                        "required_tables": instance.metadata.get("required_tables"),
                        "budget": budget,
                        "surrogate": surrogate_name,
                        "num_probe_configs": len(probe_data.config_ids),
                        "selected_configs": selected,
                        "true_spp_error": true_spp_error,
                    }
                    slice_rows.append(row)
                    logger.info(
                        "slice=%s surrogate=%s budget=%d true_spp_error=%.4f",
                        slice_name,
                        surrogate_name,
                        budget,
                        true_spp_error,
                    )
        except Exception:
            logger.exception("Slice %s failed; checkpoint preserved through last completed slice.", slice_name)
            raise

        rows.extend(slice_rows)
        completed_slices.append(slice_name)
        status = "complete" if set(completed_slices) >= set(slice_names) else "in_progress"
        _write_outputs(
            out_path,
            checkpoint_path,
            report_meta,
            rows,
            completed_slices=completed_slices,
            status=status,
            logger=logger,
        )
        logger.info("Finished slice %s (%d/%d)", slice_name, len(completed_slices), len(slice_names))

    logger.info("Phase 0 complete. Saved to %s", out_path)
    print(json.dumps(json.loads(out_path.read_text()), indent=2))


if __name__ == "__main__":
    main()

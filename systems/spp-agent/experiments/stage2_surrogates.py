#!/usr/bin/env python3
"""Stage 2 — compare surrogates and select the best one."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.tools import load_agent_cache, lock_toolkit_corpus_to_probe
from data.instance_builder import Instance
from data.query_alignment import corpus_alignment_metadata
from optimizer.materialize import materialize_database
from pipeline.evaluation import evaluate_config
from stage2.surrogate_comparison import SurrogateComparisonResult, compare_surrogates, select_best_surrogate
from surrogates.registry import ALL_SURROGATES
from thresholds.schema import default_thresholds, load_thresholds
from utils.config import load_config
from utils.logging import setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 2 surrogate comparison.")
    parser.add_argument("--log-level", default=None)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use placeholder data if probe cache is missing.",
    )
    parser.add_argument("--results-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.stage2_surrogates")
    cfg = load_config()

    results_dir = Path(args.results_dir) if args.results_dir else Path(cfg["paths"]["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)

    # Load thresholds
    thresholds_path = results_dir / "optimal_thresholds.json"
    if thresholds_path.exists():
        tc = load_thresholds(thresholds_path)
        logger.info("Loaded optimized thresholds from %s", thresholds_path)
    else:
        tc = default_thresholds()
        logger.info("Using default thresholds")

    # Load probe data
    cache_name = cfg.get("phase1", {}).get("probe_context_cache", "phase1_agg_only_probe_context.json")
    cache_path = results_dir / cache_name
    probe_data = None
    toolkit = None
    if cache_path.exists():
        try:
            toolkit = load_agent_cache(cache_path)
            probe_data = toolkit.probe_data if toolkit else None
            logger.info("Loaded probe data from %s", cache_path)
        except Exception:
            logger.warning("Failed to load agent cache from %s", cache_path)

    if probe_data is None and not args.offline:
        raise RuntimeError(
            f"No probe data at {cache_path}. Run phase1_comparison.py first, or use --offline."
        )

    true_errors: dict[str, float] | None = None
    if probe_data is not None and toolkit is not None and not args.offline:
        has_dbs = any(
            cid in probe_data.databases
            and sum(len(df) for df in probe_data.databases[cid].values()) > 0
            for cid in probe_data.config_ids
        )
        if probe_data.extraction is not None or has_dbs:
            phase0_cfg = cfg.get("phase0", {})
            seed = int(cfg["experiment"]["seed"])
            lock_toolkit_corpus_to_probe(toolkit)
            if not toolkit.corpus or not toolkit.queries:
                raise RuntimeError(
                    "Probe cache missing corpus/queries after corpus lock; "
                    "re-run phase1_comparison.py --force-probe"
                )
            eval_instance = Instance(
                dataset_name="Player",
                corpus=toolkit.corpus,
                queries=toolkit.queries,
                schema=toolkit.schema,
                metadata=corpus_alignment_metadata(toolkit.corpus),
            )
            logger.info(
                "Computing per-config true errors for %d probed configs (corpus-restricted GT)",
                len(probe_data.config_ids),
            )
            true_errors = {}
            for cid in probe_data.config_ids:
                db = probe_data.databases.get(cid)
                if not db:
                    db = materialize_database(probe_data, cid, toolkit.schema)
                true_errors[cid] = evaluate_config(eval_instance, cid, db)
        else:
            logger.warning(
                "Probe cache has no extraction/databases; Stage 2 LOO will use glass-box proxy. "
                "Re-run: python experiments/phase1_comparison.py --force-probe"
            )

    surrogate_names = list(ALL_SURROGATES.keys())
    logger.info("Comparing %d surrogates: %s", len(surrogate_names), surrogate_names)

    result = compare_surrogates(
        probe_data,
        surrogate_names,
        thresholds=tc,
        true_errors=true_errors,
    )

    out_path = results_dir / "stage2_report.json"
    out_path.write_text(
        json.dumps(dataclasses.asdict(result), indent=2),
        encoding="utf-8",
    )
    logger.info("Saved Stage 2 report to %s", out_path)

    best = select_best_surrogate(result)
    print()
    print("Stage 2 Surrogate Comparison:")
    print(f"  Best surrogate: {best}")
    print()
    print("Ranking (Spearman ρ, top-3 recall, mean regret):")
    rho_by_name = {m.name: m.spearman_rho for m in result.metrics}
    recall_by_name = {m.name: m.top_k_recall for m in result.metrics}
    regret_by_name = {m.name: m.mean_regret for m in result.metrics}
    for i, name in enumerate(result.ranking, 1):
        print(
            f"  {i}. {name}: ρ={rho_by_name.get(name, 0):.3f}, "
            f"top3={recall_by_name.get(name, 0):.2f}, "
            f"regret={regret_by_name.get(name, 0):.4f}"
        )


if __name__ == "__main__":
    main()

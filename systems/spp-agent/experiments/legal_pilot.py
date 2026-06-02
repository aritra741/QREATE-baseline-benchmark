#!/usr/bin/env python3
"""
Legal dataset pilot: Phase 0 reward table + Phase 1 agent comparison on agg_only.

Reuses Player module implementations; Legal-specific loading/SQL normalization only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import pandas as pd

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.react_agent import select_surrogate
from agent.tools import AgentToolkit, load_agent_cache, rule_based_select, save_agent_cache
from data.aggregation_slices import filter_aggregation_queries, group_queries_by_aggregation_slice
from data.legal_support import (
    LEGAL_DATASET,
    LEGAL_TABLE,
    analyze_unit_relevance,
    build_legal_instance,
    build_tier0_summary,
    config_feature_vector,
    prepare_legal_agg_only_instance,
)
from experiments.ranking_metrics import proxy_vs_true_correlation
from optimizer.config_space import generate_config_space
from optimizer.materialize import all_config_ids, materialize_database
from optimizer.probing import run_probes
from pipeline.legal_evaluation import build_error_matrix, evaluate_spp_set_legal
from surrogates.registry import MAIN_SURROGATES, build_surrogate
from surrogates.linear_error import LinearErrorSurrogate, RFErrorSurrogate
from utils.config import load_config
from utils.logging import log_step, setup_logger

MAIN_SURROGATES_LIST = list(MAIN_SURROGATES.keys())
AGENT_SURROGATES = [
    "direct_probe_ranking",
    "glass_box_proxy",
    "llm_judge_btl",
    "linear_proxy_glass",
    "rf_proxy_glass",
]

SURROGATE_LABELS = {
    "random_ranking": "Random",
    "direct_probe_ranking": "ProbeRank",
    "glass_box_proxy": "HeuristicDiag",
    "llm_judge_btl": "JudgeBTL",
    "linear_proxy_glass": "LinearDiag",
    "rf_proxy_glass": "RFDiag",
    "linear_error": "linear_error",
    "rf_error": "rf_error",
}

PHASE1_METHODS = [
    "always_random_ranking",
    "always_direct_probe_ranking",
    "always_glass_box_proxy",
    "always_llm_judge_btl",
    "always_linear_proxy_glass",
    "always_rf_proxy_glass",
    "best_fixed",
    "rule_based",
    "react_agent",
    "oracle",
]

ALWAYS_METHOD_SURROGATE = {
    "always_random_ranking": "random_ranking",
    "always_direct_probe_ranking": "direct_probe_ranking",
    "always_glass_box_proxy": "glass_box_proxy",
    "always_llm_judge_btl": "llm_judge_btl",
    "always_linear_proxy_glass": "linear_proxy_glass",
    "always_rf_proxy_glass": "rf_proxy_glass",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Legal agg_only pilot (Phase 0 + Phase 1).")
    parser.add_argument("--log-level", default=None)
    parser.add_argument("--offline", action="store_true", help="Skip react_agent LLM; use rule-based fallback.")
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Validate Legal data loading and agg_only query pool, then exit.",
    )
    parser.add_argument(
        "--phase1-only",
        action="store_true",
        help="Run Phase 1 only from saved Phase 0 + probe context (skip probes).",
    )
    return parser.parse_args()


def _legal_cfg(cfg: dict) -> dict:
    return cfg.get("legal", {})


def _probe_settings(cfg: dict) -> dict:
    legal = _legal_cfg(cfg)
    phase0 = cfg.get("phase0", {})
    precheck = cfg.get("precheck", {})
    return {
        "num_docs": int(legal.get("num_docs", phase0.get("num_docs", 20))),
        "num_configs": int(legal.get("num_probe_configs", phase0.get("num_probe_configs", 8))),
        "num_pairs": int(legal.get("num_judge_pairs", phase0.get("num_judge_pairs", 14))),
        "num_eval_queries": int(legal.get("num_eval_queries", phase0.get("num_eval_queries", 3))),
        "budget_levels": [int(b) for b in legal.get("budget_levels", phase0.get("budget_levels", [1, 2]))],
        "seed": int(cfg["experiment"]["seed"]),
    }


def _error_matrix_has_variation(matrix: pd.DataFrame) -> bool:
    values = matrix.to_numpy().astype(float)
    if values.size == 0:
        return False
    return float(values.max() - values.min()) > 1e-12


def _surrogate_correlations(probe_data, true_errors: dict[str, float]) -> list[dict]:
    rows = []
    specs = [
        ("direct_probe_ranking", probe_data.glass_box_composites, "ProbeRank uses glass-box probe scores"),
        ("glass_box_proxy", probe_data.glass_box_composites, "HeuristicDiag"),
        ("llm_judge_btl", probe_data.btl_scores, "JudgeBTL"),
        ("linear_proxy_glass", None, "LinearDiag"),
        ("rf_proxy_glass", None, "RFDiag"),
        ("linear_error", None, "ablation"),
        ("rf_error", None, "ablation"),
    ]

    linear_glass = build_surrogate("linear_proxy_glass")
    rf_glass = build_surrogate("rf_proxy_glass")
    linear_glass.fit(probe_data)
    rf_glass.fit(probe_data)

    linear_err = LinearErrorSurrogate()
    rf_err = RFErrorSurrogate()
    linear_err.fit(probe_data, true_errors=true_errors)
    rf_err.fit(probe_data, true_errors=true_errors)

    score_maps = {
        "direct_probe_ranking": probe_data.glass_box_composites,
        "glass_box_proxy": probe_data.glass_box_composites,
        "llm_judge_btl": probe_data.btl_scores,
        "linear_proxy_glass": {cid: linear_glass.score(cid) for cid in probe_data.config_ids},
        "rf_proxy_glass": {cid: rf_glass.score(cid) for cid in probe_data.config_ids},
        "linear_error": {cid: linear_err.score(cid) for cid in probe_data.config_ids},
        "rf_error": {cid: rf_err.score(cid) for cid in probe_data.config_ids},
    }

    for name, _scores, note in specs:
        proxy = score_maps[name]
        corr = proxy_vs_true_correlation(proxy, true_errors)
        rows.append(
            {
                "surrogate": name,
                "label": SURROGATE_LABELS.get(name, name),
                "spearman": corr.get("spearman"),
                "kendall": corr.get("kendall"),
                "top3_overlap": corr.get("top3_overlap"),
                "note": note,
            }
        )
    return rows


def _build_phase0_rows(
    instance,
    probe_data,
    true_errors: dict[str, float],
    budget_levels: list[int],
    slice_counts: dict[str, int],
) -> list[dict]:
    rows: list[dict] = []
    candidate_ids = all_config_ids()

    for surrogate_name in MAIN_SURROGATES_LIST:
        surrogate = build_surrogate(surrogate_name, seed=int(load_config()["experiment"]["seed"]))
        surrogate.fit(probe_data)

        for budget in budget_levels:
            ranked = surrogate.rank(candidate_ids)
            selected = ranked[: max(1, budget)]
            dbs = {cid: materialize_database(probe_data, cid, instance.schema) for cid in selected}
            spp_error = evaluate_spp_set_legal(instance, selected, dbs)
            rows.append(
                {
                    "dataset": LEGAL_DATASET,
                    "slice": "agg_only",
                    "num_queries": len(instance.queries),
                    "num_queries_in_slice_pool": slice_counts.get("agg_only", 0),
                    "budget": budget,
                    "surrogate": surrogate_name,
                    "surrogate_label": SURROGATE_LABELS.get(surrogate_name, surrogate_name),
                    "selected_configs": selected,
                    "true_spp_error": spp_error,
                    "num_probe_configs": len(probe_data.config_ids),
                }
            )
    return rows


def _reward_table_distinct(rows: list[dict], surrogates: list[str], budgets: list[int]) -> bool:
    seen = {(r["surrogate"], r["budget"]): r["true_spp_error"] for r in rows}
    errors = [seen[(s, b)] for s in surrogates for b in budgets if (s, b) in seen]
    return len(set(round(e, 6) for e in errors)) > 1


def _compute_best_fixed(rows: list[dict], surrogates: list[str]) -> tuple[str, float]:
    avg: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["surrogate"] in surrogates:
            avg[row["surrogate"]].append(float(row["true_spp_error"]))
    means = {s: mean(v) for s, v in avg.items()}
    best = min(means.values())
    tied = sorted(s for s, val in means.items() if abs(val - best) < 1e-12)
    return tied[0], float(best)


def _oracle_for_budget(budget: int, rows: list[dict], surrogates: list[str]) -> tuple[str, float]:
    subset = {r["surrogate"]: float(r["true_spp_error"]) for r in rows if r["budget"] == budget and r["surrogate"] in surrogates}
    best = min(subset.values())
    tied = sorted(s for s, val in subset.items() if abs(val - best) < 1e-12)
    return tied[0], float(best)


def _run_phase1(
    phase0_rows: list[dict],
    agent_toolkit: AgentToolkit | None,
    budget_levels: list[int],
    best_fixed: str,
    *,
    offline: bool,
    logger,
) -> tuple[list[dict], list[dict]]:
    cfg = load_config()
    phase1_cfg = cfg.get("phase1", {})
    main_surrogates = MAIN_SURROGATES_LIST
    lookup = {(int(r["budget"]), r["surrogate"]): float(r["true_spp_error"]) for r in phase0_rows}
    probe_context = agent_toolkit.decision_context() if agent_toolkit else None

    per_instance: list[dict] = []
    for budget in budget_levels:
        oracle_surrogate, oracle_error = _oracle_for_budget(budget, phase0_rows, main_surrogates)

        for method in PHASE1_METHODS:
            note = None
            if method == "oracle":
                selected = oracle_surrogate
                note = "oracle"
            elif method in ALWAYS_METHOD_SURROGATE:
                selected = ALWAYS_METHOD_SURROGATE[method]
            elif method == "best_fixed":
                selected = best_fixed
                note = "best_fixed_on_legal_agg_only"
            elif method == "rule_based":
                threshold = float(phase1_cfg.get("glass_box_spread_threshold", 0.01))
                selected, note = rule_based_select(
                    probe_context,
                    glass_box_spread_threshold=threshold,
                    logger=logger,
                )
            elif method == "react_agent":
                if offline or agent_toolkit is None:
                    selected, note = rule_based_select(None, logger=logger)
                    note = f"react_fallback_{note}"
                else:
                    selected, raw = select_surrogate(toolkit=agent_toolkit)
                    note = raw if str(raw).startswith("react_") else f"react_{raw}"
            else:
                raise ValueError(method)

            error = lookup[(budget, selected)]
            regret = error - oracle_error
            per_instance.append(
                {
                    "budget": budget,
                    "method": method,
                    "selected_surrogate": selected,
                    "error": error,
                    "oracle_surrogate": oracle_surrogate,
                    "oracle_error": oracle_error,
                    "regret": regret,
                    "oracle_match": selected == oracle_surrogate,
                    "note": note,
                }
            )

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in per_instance:
        grouped[row["method"]].append(row)

    summaries = []
    for method in PHASE1_METHODS:
        items = grouped.get(method, [])
        if not items:
            continue
        counts = Counter(r["selected_surrogate"] for r in items)
        summaries.append(
            {
                "method": method,
                "avg_error": float(mean(r["error"] for r in items)),
                "avg_regret": float(mean(r["regret"] for r in items)),
                "oracle_match_rate": float(mean(1.0 if r["oracle_match"] else 0.0 for r in items)),
                "worst_regret": float(max(r["regret"] for r in items)),
                "selected_surrogates": dict(sorted(counts.items())),
            }
        )
    return summaries, per_instance


def _print_final_summary(
    *,
    num_configs: int,
    num_queries: int,
    error_variation: bool,
    btl_corr: dict,
    surrogates_differ: bool,
    best_fixed: str,
    phase0_rows: list[dict],
    phase1_summaries: list[dict],
    unit_analysis: dict,
) -> None:
    by_method = {m["method"]: m for m in phase1_summaries}
    react = by_method.get("react_agent", {})
    oracle_rows = [r for r in phase0_rows if r["surrogate"] in MAIN_SURROGATES_LIST]
    oracle_avg = mean(
        min(float(r["true_spp_error"]) for r in oracle_rows if r["budget"] == b)
        for b in sorted({int(r["budget"]) for r in phase0_rows})
    )

    print()
    print("=" * 72)
    print("LEGAL PILOT SUMMARY (agg_only)")
    print("=" * 72)
    print(f"Configs probed: {num_configs} | Eval queries: {num_queries} | Schema: single-table ({LEGAL_TABLE})")
    print(f"1. Error matrix variation: {'YES' if error_variation else 'NO — experiment uninformative'}")
    print(
        f"2. JudgeBTL vs true error: Spearman={btl_corr.get('spearman')} "
        f"Kendall={btl_corr.get('kendall')} "
        f"(strong if Spearman >= 0.8)"
    )
    print(f"3. Surrogate differentiation in Phase 0: {'YES' if surrogates_differ else 'NO (degenerate)'}")
    print(f"4. Best fixed surrogate: {best_fixed} ({SURROGATE_LABELS.get(best_fixed, best_fixed)})")
    print(f"   Oracle avg error: {oracle_avg:.4f}")
    if react:
        print(
            f"   React agent avg error={react.get('avg_error', float('nan')):.4f} "
            f"regret={react.get('avg_regret', float('nan')):.4f} "
            f"oracle_match={react.get('oracle_match_rate', float('nan')):.4f}"
        )
    print(f"5. Unit standardization: none_avg={unit_analysis.get('unit_none_avg_error')} "
          f"unit_avg={unit_analysis.get('unit_unit_avg_error')} "
          f"effect={unit_analysis.get('unit_effect')}")
    print()
    print("Phase 0 reward table (true SPP error):")
    print(f"{'surrogate':<22} {'b=1':>8} {'b=2':>8}")
    for surrogate in MAIN_SURROGATES_LIST:
        b1 = next((r["true_spp_error"] for r in phase0_rows if r["surrogate"] == surrogate and r["budget"] == 1), None)
        b2 = next((r["true_spp_error"] for r in phase0_rows if r["surrogate"] == surrogate and r["budget"] == 2), None)
        label = SURROGATE_LABELS.get(surrogate, surrogate)
        print(f"{label:<22} {b1 if b1 is not None else 'NA':>8.4f} {b2 if b2 is not None else 'NA':>8.4f}")
    print("=" * 72)


def _save_phase1_outputs(
    *,
    results_dir: Path,
    legal_cfg: dict,
    phase0_json_path: Path,
    phase0_rows: list[dict],
    best_fixed: str,
    phase1_summaries: list[dict],
    phase1_rows: list[dict],
) -> None:
    phase1_json_path = results_dir / legal_cfg.get("phase1_json_file", "legal_phase1_comparison_agg_only.json")
    phase1_json_path.write_text(
        json.dumps(
            {
                "dataset": LEGAL_DATASET,
                "slice": "agg_only",
                "source_phase0": str(phase0_json_path),
                "best_fixed_surrogate": best_fixed,
                "methods": phase1_summaries,
                "per_instance": phase1_rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    phase1_csv_path = results_dir / legal_cfg.get("phase1_csv_file", "legal_phase1_agent_results.csv")
    agent_rows = [r for r in phase1_rows if r["method"] == "react_agent"]
    with phase1_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["budget", "agent_choice", "agent_error", "oracle_error", "regret", "oracle_surrogate"],
        )
        writer.writeheader()
        for row in agent_rows:
            writer.writerow(
                {
                    "budget": row["budget"],
                    "agent_choice": row["selected_surrogate"],
                    "agent_error": row["error"],
                    "oracle_error": row["oracle_error"],
                    "regret": row["regret"],
                    "oracle_surrogate": row["oracle_surrogate"],
                }
            )


def _run_phase1_only(args: argparse.Namespace, logger) -> None:
    cfg = load_config()
    legal_cfg = _legal_cfg(cfg)
    results_dir = Path(cfg["paths"]["results_dir"])
    settings = _probe_settings(cfg)

    phase0_json_path = results_dir / legal_cfg.get("phase0_json_file", "legal_phase0_reward_table.json")
    context_path = results_dir / legal_cfg.get("probe_context_cache", "legal_phase1_probe_context.json")
    btl_path = results_dir / legal_cfg.get("btl_precheck_file", "legal_btl_precheck.json")

    if not phase0_json_path.exists():
        raise FileNotFoundError(f"Missing {phase0_json_path}. Run full legal_pilot first.")
    if not context_path.exists():
        raise FileNotFoundError(f"Missing {context_path}. Run full legal_pilot first.")

    phase0_payload = json.loads(phase0_json_path.read_text(encoding="utf-8"))
    phase0_rows = phase0_payload.get("rows", [])
    agent_toolkit = load_agent_cache(context_path)
    btl_corr = {}
    if btl_path.exists():
        btl_corr = json.loads(btl_path.read_text(encoding="utf-8")).get("btl_vs_true", {})

    best_fixed, _ = _compute_best_fixed(phase0_rows, MAIN_SURROGATES_LIST)
    logger.info("Phase 1 only: loaded %d Phase 0 rows from %s", len(phase0_rows), phase0_json_path)

    phase1_summaries, phase1_rows = _run_phase1(
        phase0_rows,
        agent_toolkit,
        settings["budget_levels"],
        best_fixed,
        offline=args.offline,
        logger=logger,
    )
    _save_phase1_outputs(
        results_dir=results_dir,
        legal_cfg=legal_cfg,
        phase0_json_path=phase0_json_path,
        phase0_rows=phase0_rows,
        best_fixed=best_fixed,
        phase1_summaries=phase1_summaries,
        phase1_rows=phase1_rows,
    )

    diagnostics_path = results_dir / legal_cfg.get("diagnostics_file", "legal_diagnostics.json")
    num_configs = 8
    num_queries = 3
    if diagnostics_path.exists():
        diag = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        num_configs = len(diag.get("configs", [])) or num_configs
        num_queries = int((diag.get("tier0") or {}).get("num_queries", num_queries))

    surrogates_differ = _reward_table_distinct(
        phase0_rows, MAIN_SURROGATES_LIST, settings["budget_levels"]
    )
    _print_final_summary(
        num_configs=num_configs,
        num_queries=num_queries,
        error_variation=True,
        btl_corr=btl_corr,
        surrogates_differ=surrogates_differ,
        best_fixed=best_fixed,
        phase0_rows=phase0_rows,
        phase1_summaries=phase1_summaries,
        unit_analysis={},
    )


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.legal_pilot")
    cfg = load_config()
    legal_cfg = _legal_cfg(cfg)
    results_dir = Path(cfg["paths"]["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)

    if args.phase1_only:
        _run_phase1_only(args, logger)
        return

    settings = _probe_settings(cfg)
    seed = settings["seed"]
    rng = random.Random(seed)

    logger.info("=" * 72)
    logger.info("LEGAL PILOT — agg_only surrogate selection")
    logger.info("=" * 72)

    base_instance = build_legal_instance()
    agg_counts = (base_instance.metadata or {}).get("aggregation_slice_counts", {})
    agg_only_count = agg_counts.get("agg_only", 0)
    logger.info("Legal corpus docs=%d total_queries=%d agg_only_pool=%d", len(base_instance.corpus), len(base_instance.queries), agg_only_count)

    if agg_only_count < int(legal_cfg.get("min_queries_per_slice", 3)):
        logger.error(
            "Insufficient agg_only queries (%d). Cannot replicate Player pilot on Legal.",
            agg_only_count,
        )
        raise SystemExit(1)

    if args.data_only:
        print(
            json.dumps(
                {
                    "dataset": LEGAL_DATASET,
                    "corpus_docs": len(base_instance.corpus),
                    "total_queries": len(base_instance.queries),
                    "aggregation_slice_counts": agg_counts,
                    "schema_mode": "denormalized_single_table",
                    "config_space_size": len(generate_config_space()),
                    "status": "ok",
                },
                indent=2,
            )
        )
        return

    all_configs = generate_config_space()
    logger.info("Configuration space size=%d (single-table; pop x pre only)", len(all_configs))

    rng.shuffle(all_configs)

    instance, required_tables = prepare_legal_agg_only_instance(
        base_instance,
        num_docs=settings["num_docs"],
        num_eval_queries=settings["num_eval_queries"],
        seed=seed + hash("agg_only") % 1000,
    )
    logger.info(
        "agg_only instance docs=%d eval_queries=%d required_tables=%s",
        len(instance.corpus),
        len(instance.queries),
        sorted(required_tables),
    )

    probe_config_list = all_configs[: settings["num_configs"]]
    logger.info("Probe configs: %s", [c.config_id for c in probe_config_list])

    with log_step(logger, "legal_probes"):
        probe_data = run_probes(
            instance,
            instance.schema,
            probe_config_list,
            judge_pair_budget=settings["num_pairs"],
            seed=seed,
            corpus_docs=instance.corpus,
            required_tables=required_tables,
            eval_queries=instance.queries,
        )

    with log_step(logger, "legal_error_matrix"):
        error_matrix, avg_errors = build_error_matrix(instance, probe_data)
    probe_data.true_errors = avg_errors

    print("\nLegal error matrix (config x query):")
    print(error_matrix.to_string(float_format=lambda x: f"{x:.4f}"))

    error_matrix_path = results_dir / legal_cfg.get("error_matrix_file", "legal_error_matrix.csv")
    error_matrix.to_csv(error_matrix_path)
    logger.info("Saved %s", error_matrix_path)

    if not _error_matrix_has_variation(error_matrix):
        logger.error("All config errors identical on Legal — config space has no effect. Halting.")
        raise SystemExit(1)

    tier0 = build_tier0_summary(instance)
    diagnostics = {
        "dataset": LEGAL_DATASET,
        "slice": "agg_only",
        "tier0": tier0,
        "configs": [],
    }
    for cid in probe_data.config_ids:
        cfg_obj = probe_data.configs[cid]
        diagnostics["configs"].append(
            {
                "config_id": cid,
                "tier0_features": tier0,
                "config_features": config_feature_vector(cfg_obj),
                "tier1": probe_data.tier1_signals.get(cid, {}),
                "glass_box_score": probe_data.glass_box_composites.get(cid),
                "btl_score": probe_data.btl_scores.get(cid),
                "true_avg_error": avg_errors.get(cid),
            }
        )
    diagnostics_path = results_dir / legal_cfg.get("diagnostics_file", "legal_diagnostics.json")
    diagnostics_path.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")

    corr_rows = _surrogate_correlations(probe_data, avg_errors)
    corr_path = results_dir / legal_cfg.get("surrogate_correlations_file", "legal_surrogate_correlations.csv")
    with corr_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["surrogate", "label", "spearman", "kendall", "top3_overlap", "note"])
        writer.writeheader()
        writer.writerows(corr_rows)

    btl_corr = next(r for r in corr_rows if r["surrogate"] == "llm_judge_btl")
    btl_precheck = {
        "dataset": LEGAL_DATASET,
        "slice": "agg_only",
        "btl_vs_true": proxy_vs_true_correlation(probe_data.btl_scores, avg_errors),
        "glass_box_vs_true": proxy_vs_true_correlation(probe_data.glass_box_composites, avg_errors),
        "btl_report": probe_data.btl_report,
    }
    btl_path = results_dir / legal_cfg.get("btl_precheck_file", "legal_btl_precheck.json")
    btl_path.write_text(json.dumps(btl_precheck, indent=2), encoding="utf-8")

    phase0_rows = _build_phase0_rows(
        instance,
        probe_data,
        avg_errors,
        settings["budget_levels"],
        agg_counts,
    )
    phase0_json_path = results_dir / legal_cfg.get("phase0_json_file", "legal_phase0_reward_table.json")
    phase0_json_path.write_text(
        json.dumps(
            {
                "dataset": LEGAL_DATASET,
                "slice": "agg_only",
                "schema_mode": "denormalized_single_table",
                "rows": phase0_rows,
                "budget_levels": settings["budget_levels"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    phase0_csv_path = results_dir / legal_cfg.get("phase0_csv_file", "legal_phase0_reward_table.csv")
    with phase0_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["surrogate", "label", "budget_1_error", "budget_2_error"])
        for surrogate in MAIN_SURROGATES_LIST:
            b1 = next((r["true_spp_error"] for r in phase0_rows if r["surrogate"] == surrogate and r["budget"] == 1), "")
            b2 = next((r["true_spp_error"] for r in phase0_rows if r["surrogate"] == surrogate and r["budget"] == 2), "")
            writer.writerow([surrogate, SURROGATE_LABELS.get(surrogate, surrogate), b1, b2])

    surrogates_differ = _reward_table_distinct(phase0_rows, MAIN_SURROGATES_LIST, settings["budget_levels"])
    best_fixed, _best_err = _compute_best_fixed(phase0_rows, MAIN_SURROGATES_LIST)

    agent_toolkit = AgentToolkit.from_probe_run(
        probe_data,
        corpus=instance.corpus,
        queries=instance.queries,
        schema=instance.schema,
        slice_name="agg_only",
    )
    context_path = results_dir / legal_cfg.get("probe_context_cache", "legal_phase1_probe_context.json")
    save_agent_cache(agent_toolkit, context_path)

    phase1_summaries, phase1_rows = _run_phase1(
        phase0_rows,
        agent_toolkit,
        settings["budget_levels"],
        best_fixed,
        offline=args.offline,
        logger=logger,
    )

    _save_phase1_outputs(
        results_dir=results_dir,
        legal_cfg=legal_cfg,
        phase0_json_path=phase0_json_path,
        phase0_rows=phase0_rows,
        best_fixed=best_fixed,
        phase1_summaries=phase1_summaries,
        phase1_rows=phase1_rows,
    )

    unit_analysis = analyze_unit_relevance(probe_data.config_ids, avg_errors)

    _print_final_summary(
        num_configs=len(probe_data.config_ids),
        num_queries=len(instance.queries),
        error_variation=True,
        btl_corr=btl_corr,
        surrogates_differ=surrogates_differ,
        best_fixed=best_fixed,
        phase0_rows=phase0_rows,
        phase1_summaries=phase1_summaries,
        unit_analysis=unit_analysis,
    )


if __name__ == "__main__":
    main()

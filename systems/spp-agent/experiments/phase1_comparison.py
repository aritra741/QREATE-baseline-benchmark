#!/usr/bin/env python3
"""Phase 1 — surrogate-selection comparison on agg_only using Phase 0 reward table."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.react_agent import select_surrogate
from agent.tools import AgentToolkit, load_agent_cache, rule_based_select, save_agent_cache
from data.dataset_registry import (
    dataset_phase0_settings,
    dataset_phase1_settings,
    normalize_dataset_name,
    phase0_reward_table_path,
    phase1_comparison_path,
    phase1_probe_cache_path,
    results_dir_for_dataset,
)
from data.instance_builder import Instance, build_instance
from data.query_alignment import corpus_alignment_metadata, prepare_aggregation_slice_instance
from optimizer.config_space import generate_config_space
from optimizer.materialize import all_config_ids, materialize_database
from optimizer.probing import run_probes
from pipeline.evaluation import evaluate_spp_set
from surrogates.registry import build_surrogate
from utils.config import load_config
from utils.logging import setup_logger

MAIN_SURROGATES = [
    "random_ranking",
    "direct_probe_ranking",
    "glass_box_proxy",
    "llm_judge_btl",
    "linear_proxy_glass",
    "rf_proxy_glass",
]

METHODS = [
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
    parser = argparse.ArgumentParser(description="Phase 1 agg_only surrogate comparison.")
    parser.add_argument("--dataset", default="Player", help="Bench-U dataset (Player, Med, ...)")
    parser.add_argument("--log-level", default=None)
    parser.add_argument(
        "--phase0",
        type=Path,
        default=None,
        help="Path to Phase 0 reward table JSON.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip probe rerun; rule_based uses placeholder, react_agent skipped unless cache exists.",
    )
    parser.add_argument(
        "--force-probe",
        action="store_true",
        help="Re-run agg_only probes and refresh decision-context cache.",
    )
    return parser.parse_args()


def normalize_slice_name(slice_name: str) -> str:
    if slice_name == "agg":
        return "agg_only"
    return slice_name


def load_phase0_agg_only_rows(path: Path, *, dataset: str) -> tuple[list[dict], dict]:
    report = json.loads(path.read_text(encoding="utf-8"))
    dataset_key = normalize_dataset_name(dataset)
    rows = []
    for row in report.get("rows", []):
        if normalize_dataset_name(str(row.get("dataset", dataset_key))) != dataset_key:
            continue
        slice_name = normalize_slice_name(str(row.get("slice", "")))
        if slice_name != "agg_only":
            continue
        normalized = dict(row)
        normalized["slice"] = slice_name
        rows.append(normalized)
    if not rows:
        raise RuntimeError(f"No {dataset_key} agg_only rows found in {path}")
    meta = {
        "budget_levels": report.get("budget_levels", sorted({int(r["budget"]) for r in rows})),
        "surrogates": report.get("surrogates", MAIN_SURROGATES),
        "config_fingerprint": report.get("config_fingerprint", {}),
    }
    return rows, meta


def build_error_lookup(rows: list[dict]) -> dict[tuple[int, str], float]:
    lookup: dict[tuple[int, str], float] = {}
    for row in rows:
        key = (int(row["budget"]), str(row["surrogate"]))
        lookup[key] = float(row["true_spp_error"])
    return lookup


def compute_best_fixed(rows: list[dict], surrogates: list[str]) -> tuple[str, float]:
    avg_by_surrogate: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        avg_by_surrogate[str(row["surrogate"])].append(float(row["true_spp_error"]))
    candidates = {s: mean(v) for s, v in avg_by_surrogate.items() if s in surrogates}
    if not candidates:
        raise RuntimeError("Cannot compute best_fixed surrogate from Phase 0 rows.")
    best_error = min(candidates.values())
    tied = sorted(s for s, err in candidates.items() if abs(err - best_error) < 1e-12)
    return tied[0], float(best_error)


def _instance_from_toolkit(toolkit: AgentToolkit) -> Instance:
    meta = {
        **corpus_alignment_metadata(toolkit.corpus),
    }
    return Instance(
        dataset_name=getattr(toolkit.schema, "dataset_name", "Player"),
        corpus=toolkit.corpus,
        queries=toolkit.queries,
        schema=toolkit.schema,
        metadata=meta,
    )


def evaluate_surrogate_spp_error(
    toolkit: AgentToolkit,
    surrogate_name: str,
    budget: int,
    *,
    seed: int = 42,
) -> float:
    """Phase-0-style true SPP error for a surrogate not present in the reward table."""
    surrogate = build_surrogate(surrogate_name, seed=seed)
    surrogate.fit(toolkit.probe_data)
    selected = surrogate.rank(all_config_ids())[: max(1, budget)]
    dbs = {
        cid: materialize_database(toolkit.probe_data, cid, toolkit.schema)
        for cid in selected
    }
    return evaluate_spp_set(_instance_from_toolkit(toolkit), selected, dbs)


def resolve_phase0_error(
    budget: int,
    selected: str,
    lookup: dict[tuple[int, str], float],
    *,
    agent_toolkit: AgentToolkit | None,
    seed: int,
    logger,
) -> float:
    key = (budget, selected)
    if key in lookup:
        return lookup[key]
    if agent_toolkit is None:
        raise KeyError(
            f"No Phase 0 error for budget={budget} surrogate={selected!r} "
            "(no probe cache to evaluate)."
        )
    logger.warning(
        "No Phase 0 row for budget=%d surrogate=%s; evaluating from probe cache",
        budget,
        selected,
    )
    return evaluate_surrogate_spp_error(agent_toolkit, selected, budget, seed=seed)


def oracle_for_budget(
    budget: int,
    lookup: dict[tuple[int, str], float],
    surrogates: list[str],
) -> tuple[str, float]:
    errors = {s: lookup[(budget, s)] for s in surrogates if (budget, s) in lookup}
    if not errors:
        raise RuntimeError(f"No Phase 0 errors for budget={budget}")
    best = min(errors.values())
    tied = sorted(s for s, err in errors.items() if abs(err - best) < 1e-12)
    return tied[0], float(best)


def _load_or_build_agent_toolkit(
    *,
    dataset: str,
    cache_path: Path,
    cfg: dict,
    logger,
    offline: bool,
    force_probe: bool,
) -> AgentToolkit | None:
    if cache_path.exists() and not force_probe:
        logger.info("Loading cached agent toolkit from %s", cache_path)
        return load_agent_cache(cache_path)

    if offline:
        logger.warning(
            "Agent cache missing and --offline set; rule_based/react_agent will use fallbacks."
        )
        return None

    dataset_key = normalize_dataset_name(dataset)
    phase0 = dataset_phase0_settings(dataset_key)
    precheck = cfg.get("precheck", {})
    seed = int(cfg["experiment"]["seed"])
    num_docs = int(phase0.get("num_docs", precheck.get("num_docs", 20)))
    num_configs = int(phase0.get("num_probe_configs", precheck.get("num_configs", 8)))
    num_pairs = int(phase0.get("num_judge_pairs", precheck.get("num_judge_pairs", 14)))
    num_eval_queries = int(phase0.get("num_eval_queries", precheck.get("num_eval_queries", 3)))
    table_filter = set(phase0.get("table_filter", ["player"]))

    logger.info(
        "Running agg_only probes for agent/rule diagnostics (%s docs=%d configs=%d pairs=%d)",
        dataset_key,
        num_docs,
        num_configs,
        num_pairs,
    )

    base_instance = build_instance(dataset_key, include_ground_truth=False)
    instance, required_tables = prepare_aggregation_slice_instance(
        base_instance,
        slice_name="agg_only",
        num_docs=num_docs,
        num_eval_queries=num_eval_queries,
        seed=seed + hash("agg_only") % 1000,
        query_table_filter=table_filter,
        dataset=dataset_key,
    )

    all_configs = generate_config_space()
    rng = random.Random(seed)
    rng.shuffle(all_configs)
    probe_config_list = all_configs[:num_configs]

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
    toolkit = AgentToolkit.from_probe_run(
        probe_data,
        corpus=instance.corpus,
        queries=instance.queries,
        schema=instance.schema,
        slice_name="agg_only",
    )
    save_agent_cache(toolkit, cache_path)
    logger.info("Saved agent toolkit cache to %s", cache_path)
    return toolkit


def _method_selected_surrogate(
    method: str,
    *,
    budget: int,
    best_fixed_surrogate: str,
    agent_toolkit: AgentToolkit | None,
    phase1_cfg: dict,
    offline: bool,
    logger,
) -> tuple[str, str | None]:
    """Return (surrogate, note)."""
    probe_context = agent_toolkit.decision_context() if agent_toolkit else None
    if method in ALWAYS_METHOD_SURROGATE:
        return ALWAYS_METHOD_SURROGATE[method], None
    if method == "best_fixed":
        return best_fixed_surrogate, "best_fixed_on_player_agg_only"
    if method == "rule_based":
        threshold = float(phase1_cfg.get("glass_box_spread_threshold", 0.01))
        surrogate, reason = rule_based_select(
            probe_context,
            glass_box_spread_threshold=threshold,
            logger=logger,
        )
        return surrogate, reason
    if method == "react_agent":
        if offline or agent_toolkit is None:
            surrogate, reason = rule_based_select(probe_context, logger=logger)
            return surrogate, f"react_fallback_{reason}"
        surrogate, raw = select_surrogate(toolkit=agent_toolkit)
        note = raw if str(raw).startswith("react_") else f"react_{raw}"
        return surrogate, note
    if method == "oracle":
        raise ValueError("oracle selection handled separately")
    raise ValueError(f"Unknown method: {method}")


def _aggregate_method_results(per_instance: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in per_instance:
        grouped[row["method"]].append(row)

    summaries = []
    for method in METHODS:
        rows = grouped.get(method, [])
        if not rows:
            continue
        surrogate_counts = Counter(r["selected_surrogate"] for r in rows)
        summaries.append(
            {
                "method": method,
                "avg_error": float(mean(r["error"] for r in rows)),
                "avg_regret": float(mean(r["regret"] for r in rows)),
                "oracle_match_rate": float(mean(1.0 if r["oracle_match"] else 0.0 for r in rows)),
                "worst_regret": float(max(r["regret"] for r in rows)),
                "selected_surrogates": dict(sorted(surrogate_counts.items())),
            }
        )
    return summaries


def _print_advisor_summary(
    *,
    dataset: str,
    best_fixed_surrogate: str,
    best_fixed_avg_error: float,
    method_summaries: list[dict],
    oracle_avg_error: float,
) -> None:
    by_method = {m["method"]: m for m in method_summaries}
    react = by_method.get("react_agent", {})
    best_fixed = by_method.get("best_fixed", {})

    print()
    print(f"PHASE 1: {dataset} agg_only surrogate-selection comparison")
    print()
    print(f"Best fixed surrogate: {best_fixed_surrogate} (avg error {best_fixed_avg_error:.4f})")
    print(f"Oracle avg error: {oracle_avg_error:.4f}")
    if react:
        print(f"React agent avg error: {react.get('avg_error', float('nan')):.4f}")
        print(f"React agent avg regret: {react.get('avg_regret', float('nan')):.4f}")
        print(f"React agent oracle match rate: {react.get('oracle_match_rate', float('nan')):.4f}")
    if best_fixed:
        print(f"Best fixed avg error: {best_fixed.get('avg_error', float('nan')):.4f}")
    print()
    print("Conclusion:")
    react_regret = react.get("avg_regret", float("nan"))
    react_error = react.get("avg_error", float("nan"))
    best_fixed_error = best_fixed.get("avg_error", float("nan"))
    react_oracle_match = react.get("oracle_match_rate", 0.0)

    matches_oracle_error = react_regret < 1e-9
    matches_best_fixed = react_error <= best_fixed_error + 1e-9

    if react_oracle_match >= 1.0 - 1e-12 or matches_oracle_error:
        print("- React matches oracle/best_fixed: agent can identify the right surrogate on this slice.")
    elif matches_best_fixed:
        print("- React matches best_fixed error but not oracle surrogate identity on all budgets.")
    else:
        print("- React underperforms best_fixed: agent reasoning is not adding value yet.")
    print(f"- Scope: {dataset} agg_only only; do not generalize beyond this pilot slice.")


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.phase1")
    cfg = load_config()
    dataset = normalize_dataset_name(args.dataset)
    phase1_cfg = dataset_phase1_settings(dataset)
    results_dir = results_dir_for_dataset(dataset)

    phase0_path = args.phase0 or phase0_reward_table_path(results_dir, dataset)
    if not phase0_path.exists():
        raise FileNotFoundError(
            f"Phase 0 reward table not found at {phase0_path}. "
            f"Run: python experiments/phase0_reward_table.py --dataset {dataset}"
        )

    rows, meta = load_phase0_agg_only_rows(phase0_path, dataset=dataset)
    lookup = build_error_lookup(rows)
    budget_levels = [int(b) for b in meta["budget_levels"]]
    surrogates = [s for s in MAIN_SURROGATES if any((b, s) in lookup for b in budget_levels)]

    best_fixed_surrogate, best_fixed_avg_error = compute_best_fixed(rows, surrogates)
    logger.info(
        "Loaded %d agg_only Phase 0 rows; best_fixed=%s (avg error %.4f)",
        len(rows),
        best_fixed_surrogate,
        best_fixed_avg_error,
    )

    cache_path = phase1_probe_cache_path(results_dir, dataset)
    agent_toolkit = _load_or_build_agent_toolkit(
        dataset=dataset,
        cache_path=cache_path,
        cfg=cfg,
        logger=logger,
        offline=args.offline,
        force_probe=args.force_probe,
    )

    per_instance: list[dict] = []
    oracle_errors: list[float] = []

    for budget in budget_levels:
        oracle_surrogate, oracle_error = oracle_for_budget(budget, lookup, surrogates)
        oracle_errors.append(oracle_error)

        for method in METHODS:
            if method == "oracle":
                selected = oracle_surrogate
                note = "oracle"
            else:
                selected, note = _method_selected_surrogate(
                    method,
                    budget=budget,
                    best_fixed_surrogate=best_fixed_surrogate,
                    agent_toolkit=agent_toolkit,
                    phase1_cfg=phase1_cfg,
                    offline=args.offline,
                    logger=logger,
                )

            error = resolve_phase0_error(
                budget,
                selected,
                lookup,
                agent_toolkit=agent_toolkit,
                seed=int(cfg["experiment"]["seed"]),
                logger=logger,
            )
            regret = error - oracle_error
            oracle_match = selected == oracle_surrogate

            entry = {
                "budget": budget,
                "method": method,
                "selected_surrogate": selected,
                "error": error,
                "oracle_surrogate": oracle_surrogate,
                "oracle_error": oracle_error,
                "regret": regret,
                "oracle_match": oracle_match,
            }
            if note:
                entry["note"] = note
            per_instance.append(entry)
            logger.info(
                "budget=%d method=%s selected=%s error=%.4f regret=%.4f oracle_match=%s",
                budget,
                method,
                selected,
                error,
                regret,
                oracle_match,
            )

    method_summaries = _aggregate_method_results(per_instance)
    oracle_avg_error = float(mean(oracle_errors)) if oracle_errors else 0.0

    report = {
        "dataset": dataset,
        "slice": "agg_only",
        "scope_note": f"{dataset} agg_only only; not a cross-dataset or cross-slice generalization claim.",
        "source_phase0": str(phase0_path),
        "best_fixed_surrogate": best_fixed_surrogate,
        "best_fixed_label": f"best_fixed_on_{dataset.lower()}_agg_only",
        "best_fixed_avg_error": best_fixed_avg_error,
        "main_surrogates": surrogates,
        "budget_levels": budget_levels,
        "probe_context_cache": str(cache_path) if agent_toolkit else None,
        "methods": method_summaries,
        "per_instance": per_instance,
    }

    out_path = phase1_comparison_path(results_dir, dataset)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Saved Phase 1 comparison to %s", out_path)

    _print_advisor_summary(
        dataset=dataset,
        best_fixed_surrogate=best_fixed_surrogate,
        best_fixed_avg_error=best_fixed_avg_error,
        method_summaries=method_summaries,
        oracle_avg_error=oracle_avg_error,
    )


if __name__ == "__main__":
    main()

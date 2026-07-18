#!/usr/bin/env python3
"""
Phase 2 driver: run the SPP config grid against WDIRS-quality extraction.

Intended to run on a machine with Postgres + Ollama (e.g. HPC with
qwen2.5:7b-instruct). Steps:

  1. Preprocess the dataset ONCE with WDIRS (expensive: extraction, sieve
     synthesis, schema stabilization, entity resolution) using a train split
     of queries -- exactly like `evaluate_player.py` already does.
  2. Load ground truth CSVs and a test split of queries.
  3. Run `spp.config_grid.run_config_grid` across the full (or a sampled)
     PopulationConfig space, replaying population (cheap) per config against
     the single shared extraction.
  4. Write out per-config grid results + a `viable_config_search_space.json`
     report shaped like spp-agent's, for direct comparison against
     systems/spp-agent/results/<Dataset>/config_grid_test_<Dataset>/viable_config_search_space.json

Usage:
    OLLAMA_MODEL=qwen2.5:7b-instruct python diagnostics/run_config_grid.py \\
        --dataset Player \\
        --query-subdirs Filter Agg Join \\
        --train-fraction 0.8 \\
        --max-test-queries 60 \\
        --out results/spp_config_grid_Player

Requires Postgres running and reachable via WDIRS's config.py DB settings,
and Ollama serving `OLLAMA_MODEL` (default qwen2.5:7b-instruct).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, List

WDIRS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WDIRS_ROOT))

PROJECT_ROOT = WDIRS_ROOT.parent.parent
DATA_DIR = PROJECT_ROOT / "Data"
QUERY_DIR = PROJECT_ROOT / "Query"


def load_ground_truth(dataset: str) -> Dict[str, List[dict]]:
    """Load every CSV under Data/<dataset>/ as one ground-truth table."""
    gt_dir = DATA_DIR / dataset
    ground_truth: Dict[str, List[dict]] = {}
    for csv_file in gt_dir.glob("*.csv"):
        table_name = csv_file.stem.lower()
        with open(csv_file, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        ground_truth[table_name] = rows
        print(f"  loaded {len(rows)} ground-truth rows for table '{table_name}'")
    if not ground_truth:
        raise FileNotFoundError(f"No ground-truth CSVs found under {gt_dir}")
    return ground_truth


def load_queries_from_sql_file(path: Path) -> List[str]:
    """Parses WDIRS/UDA-Bench's "-- Query N: ..." delimited .sql files."""
    queries: List[str] = []
    current = None
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("-- Query"):
                if line.startswith("-- Query"):
                    current = None
                continue
            if line.startswith("--"):
                continue
            current = line if current is None else current + " " + line
            if line.endswith(";"):
                queries.append(current.rstrip(";").strip())
                current = None
    return queries


def load_dataset_queries(dataset: str, subdirs: List[str]) -> List[str]:
    base = QUERY_DIR / dataset
    all_queries: List[str] = []
    for subdir in subdirs:
        sql_dir = base / subdir
        if not sql_dir.is_dir():
            print(f"  [warn] {sql_dir} does not exist; skipping")
            continue
        for sql_file in sorted(sql_dir.glob("*.sql")):
            file_queries = load_queries_from_sql_file(sql_file)
            print(f"  loaded {len(file_queries)} queries from {sql_file.relative_to(QUERY_DIR)}")
            all_queries.extend(file_queries)
    if not all_queries:
        raise FileNotFoundError(f"No queries found under {base} for subdirs={subdirs}")
    return all_queries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="Dataset name, e.g. Player, Art")
    parser.add_argument(
        "--query-subdirs",
        nargs="+",
        default=["Filter", "Agg", "Select", "Join", "Mixed"],
        help="Query/<dataset>/<subdir>/*.sql folders to pull queries from",
    )
    parser.add_argument("--train-fraction", type=float, default=0.8)
    parser.add_argument(
        "--max-test-queries",
        type=int,
        default=60,
        help="Cap on number of test queries scored per config (grid cost is O(n_configs * n_queries))",
    )
    parser.add_argument(
        "--configs-sample",
        type=int,
        default=None,
        help="If set, randomly sample this many configs from the full space instead of all of it",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--test-on-full-workload",
        action="store_true",
        default=True,
        help=(
            "Score the config grid against ALL queries (matching "
            "evaluate_player.py's own 80%%-train/100%%-test convention), not "
            "just the held-out test split. WDIRS's schema is discovered "
            "entirely from the TRAIN split, so any workload column referenced "
            "only by a held-out query is never extracted -- causing "
            "'no such column' failures that are IDENTICAL across every "
            "PopulationConfig and get misread as config-insensitivity. "
            "Testing on the full workload maximizes schema coverage. "
            "Use --no-test-on-full-workload to fall back to strict held-out "
            "scoring (smaller, cleaner generalization test, but with schema "
            "coverage gaps on any train-fraction < 1.0)."
        ),
    )
    parser.add_argument(
        "--no-test-on-full-workload",
        dest="test_on_full_workload",
        action="store_false",
    )
    parser.add_argument(
        "--token-budget",
        type=float,
        default=172400,
        help=(
            "Total materialization token budget (WDIRS's own units from "
            "spp.routing.estimate_config_marginal_cost). Only LLM-backed axes "
            "(er=llm, norm=llm, miss=llm) cost anything; embedding/dictionary/"
            "rule-based configs are free CPU-only replays. Configs whose "
            "marginal cost would exceed the remaining budget are skipped and "
            "reported separately, not silently dropped."
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory (default: results/spp_config_grid_<dataset> under project root)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Override WDIRS_DB_PATH env var (sqlite/duckdb cache path used by WDIRS's data layer)",
    )
    args = parser.parse_args()

    if args.db_path:
        os.environ["WDIRS_DB_PATH"] = args.db_path
    os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b-instruct")

    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "results" / f"spp_config_grid_{args.dataset}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"SPP CONFIG GRID — dataset={args.dataset} model={os.environ['OLLAMA_MODEL']}")
    print("=" * 80)

    print("\n[1/5] Loading ground truth...")
    ground_truth = load_ground_truth(args.dataset)

    print("\n[2/5] Loading queries...")
    all_query_strings = load_dataset_queries(args.dataset, args.query_subdirs)
    random.seed(args.seed)
    random.shuffle(all_query_strings)

    if args.test_on_full_workload:
        # This diagnostic measures config sensitivity given best-effort
        # extraction, not extraction generalization (Phase 5's evaluation
        # harness is where held-out generalization matters and is properly
        # ground-truth-firewalled). So maximize schema coverage by feeding
        # every query to preprocess() -- otherwise any column referenced
        # only outside the train split is never extracted, producing
        # config-INDEPENDENT "no such column" failures that get misread as
        # config-insensitivity.
        train_queries = all_query_strings
    else:
        n_train = int(len(all_query_strings) * args.train_fraction)
        train_queries = all_query_strings[:n_train]
    test_queries = all_query_strings if args.test_on_full_workload else all_query_strings[len(train_queries):]
    if args.max_test_queries and len(test_queries) > args.max_test_queries:
        # Sample rather than truncate so the scored set isn't biased toward
        # whatever happened to sort first after the shuffle.
        test_queries = random.sample(test_queries, args.max_test_queries)

    print(
        f"  total={len(all_query_strings)} train={len(train_queries)} "
        f"test(scored)={len(test_queries)} "
        f"(full-workload-test={args.test_on_full_workload})"
    )

    print("\n[3/5] Running WDIRS preprocessing (shared extraction; this is the expensive step)...")
    from wdirs_runner import WDIRSRunner

    t0 = time.time()
    runner = WDIRSRunner(args.dataset)
    preprocess_result = runner.preprocess(workload_queries=train_queries)
    preprocess_time = time.time() - t0

    if not preprocess_result.success:
        print(f"PREPROCESSING FAILED: {preprocess_result.error}")
        sys.exit(1)

    print(
        f"  preprocessing done in {preprocess_time:.1f}s: "
        f"{preprocess_result.tables_processed} tables, {preprocess_result.total_records} records"
    )

    print("\n[4/5] Running config grid over Pop(T,s) space (token-budget-gated)...")
    from spp.population_config import generate_config_space
    from spp.config_grid import (
        run_config_grid,
        build_viable_config_search_space,
        summarize_query_sensitivity,
    )
    from spp.routing import TokenBudget, estimate_config_marginal_cost

    full_config_space = generate_config_space()
    if args.configs_sample and args.configs_sample < len(full_config_space):
        full_config_space = random.sample(full_config_space, args.configs_sample)

    # Estimate row volume once (shared extraction is already materialized),
    # used to price each config's marginal materialization cost.
    n_rows_total = sum(len(rows) for rows in ground_truth.values())
    n_rows_total = n_rows_total or 1

    budget = TokenBudget(total=args.token_budget)
    config_space: list = []
    skipped_over_budget: list = []
    for config in full_config_space:
        marginal = estimate_config_marginal_cost(config, n_rows_total)
        if budget.remaining >= marginal:
            if marginal > 0:
                budget.spend(marginal, label=f"grid:{config.config_id}")
            config_space.append(config)
        else:
            skipped_over_budget.append({"config_id": config.config_id, "estimated_cost": marginal})

    print(
        f"  token budget={args.token_budget:.0f} spent={budget.spent:.0f} "
        f"remaining={budget.remaining:.0f}"
    )
    print(
        f"  configs within budget: {len(config_space)}/{len(full_config_space)} "
        f"(skipped {len(skipped_over_budget)} over-budget configs)"
    )
    print(f"  evaluating {len(config_space)} configs x {len(test_queries)} queries "
          f"= {len(config_space) * len(test_queries)} query executions")

    queries_payload = [{"query_id": f"q{i}", "sql": sql} for i, sql in enumerate(test_queries)]

    t0 = time.time()
    grid = run_config_grid(runner, queries_payload, ground_truth, config_space=config_space)
    grid_time = time.time() - t0
    print(f"  grid complete in {grid_time:.1f}s")

    viable = build_viable_config_search_space(grid)
    sensitivity = summarize_query_sensitivity(grid)

    print("\n[5/5] Writing results...")
    grid_json = {
        "dataset": args.dataset,
        "model": os.environ["OLLAMA_MODEL"],
        "n_train_queries": len(train_queries),
        "n_test_queries": len(test_queries),
        "full_config_space_size": len(full_config_space),
        "config_space_size": len(config_space),
        "token_budget": args.token_budget,
        "token_spent": budget.spent,
        "token_remaining": budget.remaining,
        "n_skipped_over_budget": len(skipped_over_budget),
        "skipped_over_budget": skipped_over_budget,
        "preprocess_seconds": preprocess_time,
        "grid_seconds": grid_time,
        "per_config": grid.per_config,
    }
    (out_dir / "config_grid_results.json").write_text(json.dumps(grid_json, indent=2))
    viable["token_budget"] = args.token_budget
    viable["token_spent"] = budget.spent
    viable["unbudgeted_full_config_space_size"] = len(full_config_space)
    (out_dir / "viable_config_search_space.json").write_text(json.dumps(viable, indent=2))
    (out_dir / "query_sensitivity.json").write_text(json.dumps(sensitivity, indent=2))

    print(f"\nWrote {out_dir / 'config_grid_results.json'}")
    print(f"Wrote {out_dir / 'viable_config_search_space.json'}")
    print(f"Wrote {out_dir / 'query_sensitivity.json'}")
    print(
        f"\never_optimal={viable['n_ever_optimal']}/{viable['n_evaluated_configs']} "
        f"({viable['ever_optimal_fraction_of_evaluated']:.1%})"
    )
    print(
        f"config-sensitive queries: {sensitivity['n_config_sensitive']}/{sensitivity['n_queries']} "
        f"(the rest are flat across ALL evaluated configs -- almost always an "
        f"extraction-quality ceiling/floor, not a real config-irrelevance finding)"
    )
    if sensitivity["n_config_insensitive"]:
        print("\nConfig-insensitive queries (identical error for every config):")
        for q in sensitivity["config_insensitive_queries"][:10]:
            print(
                f"  {q['query_id']} err={q['min_error']:.3f} gold_rows={q['gold_rows']} "
                f"pred_rows_range={q['pred_rows_range']} tables={q['tables_used']}"
            )
            print(f"    sql: {q['sql']}")
    print(
        "\nCompare against spp-agent's own report at:\n"
        f"  systems/spp-agent/results/{args.dataset}/config_grid_test_{args.dataset}/viable_config_search_space.json"
    )

    runner.close()


if __name__ == "__main__":
    main()

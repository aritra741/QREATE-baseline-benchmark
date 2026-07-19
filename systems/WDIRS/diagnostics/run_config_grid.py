#!/usr/bin/env python3
"""
Phase 2 driver: run the SPP config grid against WDIRS-quality extraction.

Intended to run on a machine with SQLite + Ollama (e.g. HPC with
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

Requires Ollama serving `OLLAMA_MODEL` (default qwen2.5:7b-instruct).
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
sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "Data"
QUERY_DIR = PROJECT_ROOT / "Query"


def _canonical_gt_table(dataset: str, stem: str) -> str:
    key = dataset.strip().lower()
    aliases = {
        "finan": "finance",
        "finance": "finance",
        "art": "art",
        "cspaper": "cspaper",
        "legal": "legal",
    }
    if key in aliases:
        return aliases[key]
    med_aliases = {
        "disease_small": "disease",
        "drug_small": "drug",
        "institutes_small": "institution",
    }
    if key in {"med", "medical", "healthcare"}:
        return med_aliases.get(stem.lower(), stem.lower())
    return stem.lower()


def load_ground_truth(dataset: str) -> Dict[str, List[dict]]:
    """Load and relationally normalize ground-truth CSV tables.

    UDA-Bench CSVs contain padding whitespace and, for Player, owner aliases
    across the declared team-owner relationship. Executing workload SQL on the
    raw strings makes valid semantic joins return zero rows, so normalize the
    evaluation database before any gold query is run.
    """
    gt_dir = DATA_DIR / dataset
    ground_truth: Dict[str, List[dict]] = {}
    for csv_file in gt_dir.glob("*.csv"):
        table_name = _canonical_gt_table(dataset, csv_file.stem)
        with open(csv_file, "r", encoding="utf-8") as f:
            rows = [
                {
                    str(key).strip(): (
                        value.strip() if isinstance(value, str) else value
                    )
                    for key, value in row.items()
                }
                for row in csv.DictReader(f, skipinitialspace=True)
            ]
        ground_truth[table_name] = rows
        print(f"  loaded {len(rows)} ground-truth rows for table '{table_name}'")
    if not ground_truth:
        raise FileNotFoundError(f"No ground-truth CSVs found under {gt_dir}")

    if dataset.strip().lower() == "player":
        # owner.nba_team is the declared clean relationship to team.team_name.
        # Use it to canonicalize team.ownership to owner.name, which is the
        # semantic join key used by the generated workload.
        owner_by_team = {
            row.get("nba_team"): row.get("name")
            for row in ground_truth.get("owner", [])
            if row.get("nba_team") and row.get("name")
        }
        n_aligned = 0
        for team_row in ground_truth.get("team", []):
            canonical_owner = owner_by_team.get(team_row.get("team_name"))
            if canonical_owner and team_row.get("ownership") != canonical_owner:
                team_row["ownership"] = canonical_owner
                n_aligned += 1
        print(f"  aligned {n_aligned} Player team-owner ground-truth keys")

    return ground_truth


def load_attributes(dataset: str) -> Dict[str, dict]:
    attributes: Dict[str, dict] = {}
    for path in sorted((QUERY_DIR / dataset).glob("*_attributes.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for table, columns in payload.items():
            attributes.setdefault(table, {}).update(columns)
    if not attributes:
        raise FileNotFoundError(
            f"No *_attributes.json files found under {QUERY_DIR / dataset}"
        )
    return attributes


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
            "Hard token budget for grid materialization. The precise Qwen "
            "token counter rejects an LLM call before dispatch if its prompt "
            "plus maximum output could exceed the remaining budget. A cheap "
            "row-based estimate is also used to avoid starting configs that "
            "obviously cannot fit."
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
        help="Override the dataset-specific SQLite path used by WDIRS",
    )
    parser.add_argument(
        "--reuse-db",
        action="store_true",
        help=(
            "Reuse an existing diagnostic SQLite DB. By default the diagnostic "
            "starts with a fresh DB while retaining schema-aware extraction "
            "caches, preventing duplicate/stale materialized rows."
        ),
    )
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "results" / f"spp_config_grid_{args.dataset}"
    out_dir.mkdir(parents=True, exist_ok=True)
    using_default_db = args.db_path is None
    db_path = Path(args.db_path) if args.db_path else out_dir / "wdirs_grid.db"
    db_path = db_path.expanduser().resolve()
    if db_path.exists() and not args.reuse_db:
        if using_default_db:
            db_path.unlink()
        else:
            parser.error(
                f"--db-path already exists: {db_path}. Pass --reuse-db to "
                "reuse it, or provide a fresh path."
            )
    os.environ["WDIRS_DB_PATH"] = str(db_path)
    os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b-instruct")

    print("=" * 80)
    print(f"SPP CONFIG GRID — dataset={args.dataset} model={os.environ['OLLAMA_MODEL']}")
    print(f"SQLite DB: {db_path} ({'reused' if args.reuse_db else 'fresh'})")
    print("=" * 80)

    print("\n[1/5] Loading ground truth...")
    ground_truth = load_ground_truth(args.dataset)
    attributes = load_attributes(args.dataset)

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

    # Fail before the expensive extraction if any workload SQL is invalid for
    # the ground-truth SQLite representation. Previously these errors were
    # swallowed as empty result sets after hours of preprocessing.
    from spp.config_grid import _build_in_memory_db, _execute_sql, SQLExecutionError

    gt_validation_conn = _build_in_memory_db(ground_truth)
    invalid_queries = []
    for sql in all_query_strings:
        try:
            _execute_sql(gt_validation_conn, sql)
        except SQLExecutionError as exc:
            invalid_queries.append(str(exc))
    gt_validation_conn.close()
    if invalid_queries:
        preview = "\n".join(f"  - {error}" for error in invalid_queries[:10])
        raise RuntimeError(
            f"{len(invalid_queries)} workload queries failed ground-truth SQL "
            f"validation before extraction:\n{preview}"
        )
    print("  all workload queries passed ground-truth SQL validation")

    print("\n[3/5] Running WDIRS preprocessing (shared extraction; this is the expensive step)...")
    from wdirs_runner import WDIRSRunner

    t0 = time.time()
    runner = WDIRSRunner(args.dataset)
    preprocess_result = runner.preprocess(
        workload_queries=train_queries,
        perform_proactive_er=False,
    )
    preprocess_time = time.time() - t0

    if not preprocess_result.success:
        print(f"PREPROCESSING FAILED: {preprocess_result.error}")
        sys.exit(1)

    materialized_sql_errors = []
    for sql in all_query_strings:
        try:
            runner.data_layer.execute_sql(sql)
        except RuntimeError as exc:
            materialized_sql_errors.append(str(exc))
    if materialized_sql_errors:
        preview = "\n".join(
            f"  - {error}" for error in materialized_sql_errors[:10]
        )
        raise RuntimeError(
            f"{len(materialized_sql_errors)} workload queries failed against "
            f"the freshly materialized schema; config scoring was not started:\n"
            f"{preview}"
        )

    print(
        f"  preprocessing done in {preprocess_time:.1f}s: "
        f"{preprocess_result.tables_processed} tables, {preprocess_result.total_records} records"
    )

    print("\n[4/5] Running config grid over Pop(T,s) space (token-budget-gated)...")
    from spp.population_config import generate_config_space
    from spp.config_grid import (
        run_config_grid,
        build_viable_config_search_space,
        official_query_error,
        summarize_query_sensitivity,
    )
    from spp.routing import TokenBudget, estimate_config_marginal_cost
    from token_counter import GLOBAL_COUNTER

    cartesian_config_space = generate_config_space()
    full_cartesian_size = len(cartesian_config_space)
    full_config_space = cartesian_config_space
    if args.configs_sample and args.configs_sample < len(cartesian_config_space):
        full_config_space = sorted(
            random.sample(cartesian_config_space, args.configs_sample),
            key=lambda config: config.config_id,
        )

    # Estimate row volume once (shared extraction is already materialized),
    # used to price each config's marginal materialization cost.
    workload_tables = set(runner.lattice_planner.lattice.tables)
    n_rows_total = sum(
        len(rows)
        for table, rows in ground_truth.items()
        if table in workload_tables
    )
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
        f"  token budget={args.token_budget:.0f} row-cost estimate="
        f"{budget.spent:.0f} estimated remaining={budget.remaining:.0f}"
    )
    print(
        f"  configs within budget: {len(config_space)}/{len(full_config_space)} "
        f"(skipped {len(skipped_over_budget)} over-budget configs)"
    )
    print(f"  evaluating {len(config_space)} configs x {len(test_queries)} queries "
          f"= {len(config_space) * len(test_queries)} query executions")

    queries_payload = [{"query_id": f"q{i}", "sql": sql} for i, sql in enumerate(test_queries)]

    t0 = time.time()
    GLOBAL_COUNTER.reset()
    GLOBAL_COUNTER.set_budget(int(args.token_budget))
    grid = run_config_grid(
        runner,
        queries_payload,
        ground_truth,
        config_space=config_space,
        query_error_fn=lambda sql, gt, pred: official_query_error(
            sql, gt, pred, attributes
        ),
    )
    grid_time = time.time() - t0
    actual_tokens = GLOBAL_COUNTER.total_tokens
    print(
        f"  grid complete in {grid_time:.1f}s; actual materialization "
        f"tokens={actual_tokens:.0f}/{args.token_budget:.0f}"
    )
    if grid.stopped_early:
        print(f"  grid stopped at hard token limit: {grid.stop_reason}")

    viable = build_viable_config_search_space(grid)
    sensitivity = summarize_query_sensitivity(grid)

    print("\n[5/5] Writing results...")
    grid_json = {
        "dataset": args.dataset,
        "model": os.environ["OLLAMA_MODEL"],
        "n_train_queries": len(train_queries),
        "n_test_queries": len(test_queries),
        "full_config_space_size": full_cartesian_size,
        "planned_config_space_size": len(full_config_space),
        "config_space_size": len(config_space),
        "token_budget": args.token_budget,
        "token_spent_estimate": budget.spent,
        "token_spent_actual": actual_tokens,
        "token_remaining_actual": max(args.token_budget - actual_tokens, 0),
        "grid_stopped_early": grid.stopped_early,
        "grid_stop_reason": grid.stop_reason,
        "n_skipped_over_budget": len(skipped_over_budget),
        "skipped_over_budget": skipped_over_budget,
        "preprocess_seconds": preprocess_time,
        "grid_seconds": grid_time,
        "per_config": grid.per_config,
    }
    (out_dir / "config_grid_results.json").write_text(json.dumps(grid_json, indent=2))
    viable["token_budget"] = args.token_budget
    viable["token_spent_estimate"] = budget.spent
    viable["token_spent_actual"] = actual_tokens
    viable["full_cartesian_config_space_size"] = full_cartesian_size
    viable["planned_config_space_size"] = len(full_config_space)
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
        f"behaviorally distinct error profiles="
        f"{viable['n_behaviorally_distinct_error_profiles']}; "
        f"ever-optimal profiles={viable['n_ever_optimal_error_profiles']}; "
        f"strictly-optimal configs={viable['n_strictly_optimal']}"
    )
    print(
        f"config-sensitive queries: {sensitivity['n_config_sensitive']}/{sensitivity['n_queries']} "
        f"(flat queries may be stably correct, extraction-limited, or genuinely "
        f"unaffected; they do not count toward config viability)"
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

"""Train/dev/test splits for balanced aggregation workloads (Player, Med, ...)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from data.aggregation_slices import AGGREGATION_SLICE_ORDER
from data.balanced_workload import build_feasible_slice_pool
from data.dataset_registry import (
    default_table_filter,
    normalize_dataset_name,
    results_dir_for_dataset,
    workload_slices_for_dataset,
    workload_split_targets,
)
from data.instance_builder import Instance, build_instance
from data.loader import _benchu_root, load_corpus
from data.player_workload_generator import generate_all_candidates, mine_corpus_literals
from data.loader import load_ground_truth
from data.workload_selection import select_balanced_queries, stable_slice_seed
from utils.config import load_config

DEFAULT_SPLIT_TARGETS = {
    "train": 20,
    "dev": 5,
    "test": 5,
}

HOLDOUT_POLICY = (
    "The test split is assigned first from a shuffled per-slice pool and is never "
    "included in train or dev. Use train for agent design, prompt tuning, threshold "
    "optimization, and algorithm selection. Use dev only for validation during "
    "development. The test split must not be used for any tuning or selection."
)


def build_expanded_query_pool(
    instance: Instance,
    *,
    corpus: list[dict],
    dataset: str = "",
) -> tuple[list[dict], list[dict]]:
    """Legacy + on-disk queries plus freshly generated candidates (Player and Med)."""
    dataset_key = normalize_dataset_name(dataset or instance.dataset_name)

    if dataset_key == "Player":
        gt = load_ground_truth("Player")
        literals = mine_corpus_literals(corpus, gt)
        generated_by_slice = generate_all_candidates(literals)
        new_queries: list[dict] = []
        for slice_name, candidates in generated_by_slice.items():
            for i, query in enumerate(candidates, start=1):
                q = dict(query)
                q["query_id"] = f"{slice_name}_gen_{i}"
                meta = dict(q.get("metadata") or {})
                meta["generated"] = True
                q["metadata"] = meta
                new_queries.append(q)
        return list(instance.queries) + new_queries, new_queries

    if dataset_key == "Med":
        from data.med_workload_generator import generate_all_candidates_med

        generated_by_slice = generate_all_candidates_med()
        new_queries = []
        for slice_name, candidates in generated_by_slice.items():
            for query in candidates:
                q = dict(query)
                meta = dict(q.get("metadata") or {})
                meta["generated"] = True
                q["metadata"] = meta
                new_queries.append(q)
        return list(instance.queries) + new_queries, new_queries

    if dataset_key == "Finan":
        from data.finan_workload_generator import generate_all_candidates_finan

        new_queries = []
        for query in generate_all_candidates_finan():
            q = dict(query)
            meta = dict(q.get("metadata") or {})
            meta["generated"] = True
            q["metadata"] = meta
            new_queries.append(q)
        return list(instance.queries) + new_queries, new_queries

    if dataset_key == "Art":
        from data.art_workload_generator import generate_all_candidates_art

        new_queries = []
        for query in generate_all_candidates_art():
            q = dict(query)
            meta = dict(q.get("metadata") or {})
            meta["generated"] = True
            q["metadata"] = meta
            new_queries.append(q)
        return list(instance.queries) + new_queries, new_queries

    return list(instance.queries), []


def _adjust_split_targets(
    max_feasible: int,
    targets: dict[str, int],
) -> dict[str, int]:
    total_target = sum(targets.values())
    if max_feasible >= total_target:
        return dict(targets)
    if max_feasible <= 0:
        return {"train": 0, "dev": 0, "test": 0}
    ratio = max_feasible / total_target
    adjusted = {
        split: max(0, int(round(targets[split] * ratio)))
        for split in ("train", "dev", "test")
    }
    while sum(adjusted.values()) > max_feasible:
        for split in ("test", "dev", "train"):
            if adjusted[split] > 0 and sum(adjusted.values()) > max_feasible:
                adjusted[split] -= 1
    while sum(adjusted.values()) < max_feasible:
        for split in ("train", "dev", "test"):
            if sum(adjusted.values()) < max_feasible:
                adjusted[split] += 1
            if sum(adjusted.values()) >= max_feasible:
                break
    return adjusted


def assign_slice_split(
    pool: list[dict],
    *,
    slice_name: str,
    targets: dict[str, int],
    seed: int,
) -> dict[str, Any]:
    total_needed = sum(targets.values())
    if len(pool) < total_needed:
        targets = _adjust_split_targets(len(pool), targets)

    selected = select_balanced_queries(
        pool,
        slice_name=slice_name,
        target_count=sum(targets.values()),
        seed=stable_slice_seed(seed, slice_name),
    )
    rng = random.Random(stable_slice_seed(seed, f"{slice_name}__split"))
    shuffled = list(selected)
    rng.shuffle(shuffled)

    test_n = targets["test"]
    dev_n = targets["dev"]
    train_n = targets["train"]

    test_queries = shuffled[:test_n]
    dev_queries = shuffled[test_n : test_n + dev_n]
    train_queries = shuffled[test_n + dev_n : test_n + dev_n + train_n]

    def tag(queries: list[dict], split: str) -> list[dict]:
        tagged = []
        for q in queries:
            meta = dict(q.get("metadata") or {})
            meta["split"] = split
            meta["aggregation_slice"] = slice_name
            meta["held_out"] = split == "test"
            tagged.append({**q, "metadata": meta})
        return tagged

    return {
        "slice": slice_name,
        "targets": targets,
        "max_feasible": len(pool),
        "reached_target": len(selected) >= sum(DEFAULT_SPLIT_TARGETS.values()),
        "train": tag(train_queries, "train"),
        "dev": tag(dev_queries, "dev"),
        "test": tag(test_queries, "test"),
    }


def create_train_dev_test_split(
    *,
    dataset: str = "",
    train_per_slice: int | None = None,
    dev_per_slice: int | None = None,
    test_per_slice: int | None = None,
    min_train_total: int | None = None,
    seed: int | None = None,
    table_filter: set[str] | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    dataset_key = normalize_dataset_name(dataset)
    seed = seed if seed is not None else int(cfg["experiment"]["seed"])
    split_targets = workload_split_targets(dataset_key)
    targets = {
        "train": train_per_slice if train_per_slice is not None else split_targets["train"],
        "dev": dev_per_slice if dev_per_slice is not None else split_targets["dev"],
        "test": test_per_slice if test_per_slice is not None else split_targets["test"],
    }
    min_train = (
        min_train_total if min_train_total is not None else split_targets["min_train_total"]
    )
    table_filter = table_filter or default_table_filter(dataset_key)

    corpus = load_corpus(dataset_key)
    instance = build_instance(dataset_key, include_ground_truth=False)
    combined_queries, generated_queries = build_expanded_query_pool(
        instance,
        corpus=corpus,
        dataset=dataset_key,
    )

    slice_order = workload_slices_for_dataset(dataset_key)
    slice_reports: list[dict[str, Any]] = []
    removed_infeasible: list[dict] = []
    removed_duplicates: list[dict] = []
    splits: dict[str, list[dict]] = {"train": [], "dev": [], "test": []}

    for slice_name in slice_order:
        pool_report = build_feasible_slice_pool(
            combined_queries,
            slice_name=slice_name,
            schema=instance.schema,
            corpus=corpus,
            table_filter=table_filter,
        )
        removed_infeasible.extend(pool_report["removed_infeasible"])
        removed_duplicates.extend(pool_report["removed_duplicates"])
        assignment = assign_slice_split(
            pool_report["queries"],
            slice_name=slice_name,
            targets=dict(targets),
            seed=seed,
        )
        slice_reports.append(
            {
                "slice": slice_name,
                "targets": assignment["targets"],
                "counts": {
                    "train": len(assignment["train"]),
                    "dev": len(assignment["dev"]),
                    "test": len(assignment["test"]),
                },
                "max_feasible": assignment["max_feasible"],
                "reached_target": assignment["reached_target"],
                "shortfall_reason": (
                    None
                    if assignment["reached_target"]
                    else "insufficient unique corpus-feasible queries after deduplication"
                ),
            }
        )
        splits["train"].extend(assignment["train"])
        splits["dev"].extend(assignment["dev"])
        splits["test"].extend(assignment["test"])

    counts_per_slice = {r["slice"]: r["counts"] for r in slice_reports}
    totals = {split: len(splits[split]) for split in splits}
    train_met_minimum = totals["train"] >= min_train

    return {
        "dataset": dataset_key,
        "split_targets_per_slice": targets,
        "counts_per_slice": counts_per_slice,
        "totals": totals,
        "train_met_minimum": train_met_minimum,
        "min_train_total": min_train,
        "removed_infeasible_count": len(removed_infeasible),
        "removed_duplicates_count": len(removed_duplicates),
        "removed_infeasible_sample": removed_infeasible[:40],
        "removed_duplicates_sample": removed_duplicates[:40],
        "generated_candidate_count": len(generated_queries),
        "holdout_policy": HOLDOUT_POLICY,
        "test_held_out": True,
        "splits": splits,
        "slice_reports": slice_reports,
    }


def _write_split_sql(path: Path, queries: list[dict], split_name: str) -> None:
    lines: list[str] = []
    for idx, query in enumerate(queries, start=1):
        sql = query["sql_query"].rstrip(";")
        slice_type = (query.get("metadata") or {}).get("aggregation_slice", "unknown")
        lines.append(f"-- Query {idx}: {split_name} ({slice_type}) id={query['query_id']}")
        lines.append(sql + ";")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_split_artifacts(
    report: dict[str, Any],
    *,
    results_dir: Path,
    write_sql: bool = True,
    dataset: str | None = None,
) -> dict[str, str]:
    dataset_key = normalize_dataset_name(dataset or report.get("dataset") or "Player")
    results_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = results_dir / "workload_split_manifest.json"
    payload = {
        k: v
        for k, v in report.items()
        if k != "splits"
    }
    payload["query_ids"] = {
        split: [q["query_id"] for q in report["splits"][split]]
        for split in ("train", "dev", "test")
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    paths: dict[str, str] = {"manifest": str(manifest_path)}
    for split in ("train", "dev", "test"):
        split_path = results_dir / f"workload_{split}.json"
        split_path.write_text(
            json.dumps(report["splits"][split], indent=2),
            encoding="utf-8",
        )
        paths[split] = str(split_path)

    if write_sql:
        sql_root = _benchu_root() / "Query" / dataset_key / "Splits"
        for split in ("train", "dev", "test"):
            sql_path = sql_root / f"{split}.sql"
            _write_split_sql(sql_path, report["splits"][split], split)
            paths[f"{split}_sql"] = str(sql_path)

    return paths


def load_split_manifest(
    manifest_path: Path | None = None,
    *,
    dataset: str = "",
) -> dict[str, Any]:
    cfg = load_config()
    if manifest_path is None:
        path = results_dir_for_dataset(dataset) / "workload_split_manifest.json"
    else:
        path = manifest_path
    return json.loads(path.read_text(encoding="utf-8"))


def load_split_queries(
    split: str,
    *,
    results_dir: Path | None = None,
    dataset: str = "",
) -> list[dict]:
    root = results_dir or results_dir_for_dataset(dataset)
    path = root / f"workload_{split}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def filter_queries_to_split(queries: list[dict], split: str, *, dataset: str = "") -> list[dict]:
    allowed = {q["query_id"] for q in load_split_queries(split, dataset=dataset)}
    return [q for q in queries if q.get("query_id") in allowed]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Create train/dev/test workload split")
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--train-per-slice", type=int, default=None)
    parser.add_argument("--dev-per-slice", type=int, default=None)
    parser.add_argument("--test-per-slice", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--no-write-sql", action="store_true")
    args = parser.parse_args()

    dataset_key = normalize_dataset_name(args.dataset)
    results_dir = results_dir_for_dataset(dataset_key)
    report = create_train_dev_test_split(
        dataset=dataset_key,
        train_per_slice=args.train_per_slice,
        dev_per_slice=args.dev_per_slice,
        test_per_slice=args.test_per_slice,
        seed=args.seed,
    )
    paths = write_split_artifacts(
        report,
        results_dir=results_dir,
        write_sql=not args.no_write_sql,
        dataset=dataset_key,
    )

    summary = {
        "counts_per_slice": report["counts_per_slice"],
        "totals": report["totals"],
        "train_met_minimum": report["train_met_minimum"],
        "removed_infeasible_count": report["removed_infeasible_count"],
        "removed_duplicates_count": report["removed_duplicates_count"],
        "test_held_out": report["test_held_out"],
        "holdout_policy": report["holdout_policy"],
        "artifact_paths": paths,
    }
    print(json.dumps(summary, indent=2))
    print(f"\nManifest: {paths['manifest']}")


if __name__ == "__main__":
    main()

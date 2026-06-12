#!/usr/bin/env python3
"""Compare join-key overlap and slice F1 before vs after cross-table join-key ER."""

from __future__ import annotations

import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.tools import load_agent_cache, lock_toolkit_corpus_to_probe
from data.instance_builder import Instance, build_instance
from data.query_alignment import corpus_alignment_metadata, prepare_aggregation_slice_instance
from diagnostics.five_slice_benchmark import (
    CONFIG_ID,
    _eval_context,
    _macro_f1_for_query,
    _stable_slice_seed,
)
from optimizer.config_space import parse_config_id
from pipeline.extraction import extract_documents
from pipeline.population import apply_population, join_key_exact_overlap
from utils.config import load_config

SLICES = ("agg_join", "agg_filter_join")
PRIMARY_JOIN = ("player", "team", "team", "team_name")


def _load_slice_instance(slice_name: str, cfg: dict):
    phase0 = cfg.get("phase0", {})
    seed = int(cfg["experiment"]["seed"])
    num_docs = int(phase0.get("num_docs", 20))
    table_filter = set(phase0.get("table_filter", ["player"]))

    base = build_instance("Player", include_ground_truth=False)
    slice_pool, _ = prepare_aggregation_slice_instance(
        base,
        slice_name=slice_name,
        num_docs=num_docs,
        num_eval_queries=9999,
        seed=_stable_slice_seed(seed, slice_name),
        query_table_filter=table_filter,
    )
    return slice_pool


def _load_extraction(instance, cache_path: Path, *, fresh_extraction: bool):
    if not fresh_extraction and cache_path.exists():
        toolkit = load_agent_cache(cache_path)
        lock_toolkit_corpus_to_probe(toolkit)
        locked = Instance(
            dataset_name=instance.dataset_name,
            corpus=list(toolkit.corpus),
            queries=list(instance.queries),
            schema=instance.schema,
            metadata={
                **corpus_alignment_metadata(toolkit.corpus),
                "aggregation_slice": instance.metadata.get("aggregation_slice", ""),
            },
        )
        return locked, toolkit.probe_data.extraction

    cfg = load_config()
    extraction = extract_documents(
        instance.corpus,
        instance.schema,
        cfg["llm"]["extraction_model"],
        queries=instance.queries,
    )
    return instance, extraction


def _mean_f1(instance, db, parser, attributes, settings) -> float:
    scores: list[float] = []
    for query in instance.queries:
        try:
            row = _macro_f1_for_query(instance, db, query, parser, attributes, settings)
            scores.append(float(row["macro_f1"]))
        except Exception:
            scores.append(0.0)
    return sum(scores) / len(scores) if scores else 0.0


def _evaluate_mode(instance, extraction, *, cross_table_join_er: bool) -> dict:
    config = parse_config_id(CONFIG_ID)
    db, _ = apply_population(
        extraction,
        config,
        instance.schema,
        cross_table_join_er=cross_table_join_er,
    )
    settings, parser, attributes, _ = _eval_context(instance)
    lt, lc, rt, rc = PRIMARY_JOIN
    return {
        "join_overlap": join_key_exact_overlap(db, lt, lc, rt, rc),
        "mean_f1": _mean_f1(instance, db, parser, attributes, settings),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fresh-extraction",
        action="store_true",
        help="Run fresh LLM extraction per slice instead of cached probe extraction",
    )
    args = parser.parse_args()

    cfg = load_config()
    cache_path = Path(cfg["paths"]["results_dir"]) / cfg.get("phase1", {}).get(
        "probe_context_cache", "phase1_agg_only_probe_context.json"
    )

    print("Cross-table join-key ER evaluation (fixed config)")
    print(f"Config: {CONFIG_ID}")
    print(f"Primary join pair: {'.'.join(PRIMARY_JOIN[:2])} <-> {'.'.join(PRIMARY_JOIN[2:])}")
    print(f"Schema join keys ({len(build_instance('Player').schema.join_keys)}):")
    for pair in build_instance("Player").schema.join_keys:
        print(f"  {pair[0]}.{pair[1]} = {pair[2]}.{pair[3]}")
    print()

    rows: list[dict] = []
    for slice_name in SLICES:
        instance = _load_slice_instance(slice_name, cfg)
        eval_instance, extraction = _load_extraction(
            instance, cache_path, fresh_extraction=args.fresh_extraction
        )
        before = _evaluate_mode(eval_instance, extraction, cross_table_join_er=False)
        after = _evaluate_mode(eval_instance, extraction, cross_table_join_er=True)
        rows.append(
            {
                "slice": slice_name,
                "before_overlap": before["join_overlap"],
                "after_overlap": after["join_overlap"],
                "before_f1": before["mean_f1"],
                "after_f1": after["mean_f1"],
            }
        )

    print("| Slice | Join overlap (before) | Join overlap (after) | Mean F1 (before) | Mean F1 (after) |")
    print("|-------|----------------------|----------------------|------------------|-----------------|")
    for row in rows:
        print(
            f"| {row['slice']} | {row['before_overlap']:.4f} | {row['after_overlap']:.4f} | "
            f"{row['before_f1']:.4f} | {row['after_f1']:.4f} |"
        )

    mean_before_f1 = sum(r["before_f1"] for r in rows) / len(rows)
    mean_after_f1 = sum(r["after_f1"] for r in rows) / len(rows)
    print()
    print(f"Mean F1 across slices (before): {mean_before_f1:.4f}")
    print(f"Mean F1 across slices (after):  {mean_after_f1:.4f}")


if __name__ == "__main__":
    main()

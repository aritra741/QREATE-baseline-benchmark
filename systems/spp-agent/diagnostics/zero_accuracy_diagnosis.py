#!/usr/bin/env python3
"""Diagnose zero-accuracy failures in the full SPP pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.tools import load_agent_cache
from data.instance_builder import Instance
from data.query_alignment import corpus_alignment_metadata
from optimizer.materialize import materialize_database
from pipeline.evaluation import _eval_context, _run_gold_sql
from pipeline.execution import execute_sql_on_db
from pipeline.full_pipeline import run_spp_pipeline
from stage4.query_clustering import cluster_workload
from thresholds.schema import load_thresholds
from utils.config import load_config


def _df_preview(df: pd.DataFrame, n: int = 2) -> str:
    if df is None or df.empty:
        return "(empty)"
    return df.head(n).to_string(index=False)


def main() -> None:
    cfg = load_config()
    benchu = Path(cfg["paths"]["benchu_root"])
    results = SPP_ROOT / "results"
    cache_path = results / cfg.get("phase1", {}).get(
        "probe_context_cache", "phase1_agg_only_probe_context.json"
    )

    phase0 = cfg.get("phase0", {})
    seed = int(cfg["experiment"]["seed"])
    num_docs = int(phase0.get("num_docs", 20))
    num_q = int(phase0.get("num_eval_queries", 3))
    table_filter = set(phase0.get("table_filter", ["player"]))

    toolkit = load_agent_cache(cache_path)
    if not toolkit.corpus or not toolkit.queries:
        raise RuntimeError(
            "Probe cache missing corpus/queries; re-run phase1_comparison.py --force-probe"
        )
    instance = Instance(
        dataset_name="Player",
        corpus=list(toolkit.corpus),
        queries=list(toolkit.queries),
        schema=toolkit.schema,
        metadata={
            **corpus_alignment_metadata(toolkit.corpus),
            "aggregation_slice": "agg_only",
            "num_docs": len(toolkit.corpus),
            "num_eval_queries": len(toolkit.queries),
        },
    )
    toolkit.instance = instance

    query_clusters = cluster_workload(instance.queries, seed=seed)
    toolkit.query_clusters = query_clusters

    tc = load_thresholds()
    token_budget = int(cfg.get("token_budget", 500_000))

    print("=" * 72)
    print("WORKLOAD: Player agg_only, queries:", [q.get("query_id") for q in instance.queries])
    print("=" * 72)

    pipeline_result = run_spp_pipeline(
        toolkit.probe_data,
        queries=instance.queries,
        schema=toolkit.schema,
        thresholds=tc,
        token_budget=token_budget,
        instance=instance,
        agent_risk_level="risk_neutral",
        query_clusters=query_clusters,
        seed=seed,
    )

    routing = dict(pipeline_result.routing_table.cluster_to_config)
    labels = query_clusters.labels
    probe = toolkit.probe_data
    schema = toolkit.schema

    print("\n## Q1: Routing table → valid non-empty materialized databases?\n")
    print("Routing table (cluster_id -> config_id):")
    for cid, cfg_id in sorted(routing.items()):
        print(f"  cluster {cid} -> {cfg_id}")

    print("\nPer-query routing:")
    dbs_by_config: dict[str, dict[str, pd.DataFrame]] = {}
    for idx, query in enumerate(instance.queries):
        qid = query.get("query_id", idx)
        cluster_id = labels[idx] if idx < len(labels) else None
        cfg_id = routing.get(cluster_id, "MISSING")
        print(f"  {qid} -> cluster {cluster_id} -> config {cfg_id[:60]}...")

    print("\nMaterialized database schema + row counts per assigned config:")
    assigned_configs = sorted(set(routing.values()))
    q1_ok = True
    for cfg_id in assigned_configs:
        if cfg_id not in dbs_by_config:
            dbs_by_config[cfg_id] = materialize_database(probe, cfg_id, schema)
        db = dbs_by_config[cfg_id]
        total_rows = sum(len(df) for df in db.values())
        print(f"\n  Config: {cfg_id}")
        if not db or total_rows == 0:
            q1_ok = False
            print("    STATUS: EMPTY OR MISSING")
        else:
            print(f"    STATUS: non-empty (total_rows={total_rows})")
        for table, df in db.items():
            print(f"    table={table!r} rows={len(df)} cols={list(df.columns)}")

    print(f"\nQ1 VERDICT: {'PASS' if q1_ok else 'FAIL'} — all routed configs materialize to non-empty DBs")

    print("\n## Q2: SQL execution on assigned database?\n")
    print("(Workload uses benchmark SQL from query['sql_query'], not NL2SQL generation.)\n")

    settings, parser, attributes, _ = _eval_context(instance)
    q2_results = []
    for idx, query in enumerate(instance.queries):
        qid = query.get("query_id", idx)
        sql = query["sql_query"].strip()
        cluster_id = labels[idx]
        cfg_id = routing[cluster_id]
        db = dbs_by_config[cfg_id]

        print(f"--- {qid} (cluster {cluster_id}, config ...{cfg_id[-40:]}) ---")
        print(f"SQL: {sql}")
        try:
            pred_df = execute_sql_on_db(db, sql)
            ok = True
            err = None
        except Exception as exc:
            pred_df = pd.DataFrame()
            ok = False
            err = str(exc)

        if ok:
            print(f"EXEC: SUCCESS  returned_rows={len(pred_df)}")
            print(f"FIRST 2 ROWS:\n{_df_preview(pred_df, 2)}")
        else:
            print(f"EXEC: FAILED  error={err}")
        q2_results.append((qid, ok, len(pred_df) if ok else 0))

    q2_all_ok = all(r[1] for r in q2_results)
    print(f"\nQ2 VERDICT: {'PASS' if q2_all_ok else 'FAIL'} — SQL execution on assigned DBs")

    print("\n## Q3: Error metric inputs (gold vs pred) before F1?\n")

    from evaluation.metrics import MetricCalculator
    from evaluation.query_manifest import QueryManifest
    from evaluation.row_matcher import RowMatcher

    for idx, query in enumerate(instance.queries[:2]):
        qid = query.get("query_id", idx)
        sql = query["sql_query"]
        cluster_id = labels[idx]
        cfg_id = routing[cluster_id]
        db = dbs_by_config[cfg_id]

        print(f"--- {qid} ---")
        try:
            pred_df = execute_sql_on_db(db, sql)
            gold_df = _run_gold_sql(instance, sql)
            pred_ok = True
            gold_ok = True
        except Exception as exc:
            print(f"EXECUTION ERROR: {exc}")
            continue

        print(f"PRED: rows={len(pred_df)} cols={list(pred_df.columns)}")
        print(_df_preview(pred_df, 5))
        print(f"\nGOLD (corpus-restricted): rows={len(gold_df)} cols={list(gold_df.columns)}")
        print(_df_preview(gold_df, 5))

        manifest = QueryManifest(sql, parser.parse(sql), attributes)
        matcher = RowMatcher(settings=settings)
        match_result = matcher.match(
            gold_df=gold_df,
            pred_df=pred_df,
            primary_keys=manifest.primary_keys,
            secondary_key=None,
            attr_descriptions=attributes,
            query_type=manifest.parsed.query_type,
        )
        metrics = MetricCalculator(manifest, settings).compute(match_result)
        print(f"\nMATCH: aligned_rows={match_result.len_pred} pred_total={len(pred_df)} gold_total={len(gold_df)}")
        print(f"       primary_keys={manifest.primary_keys}")
        print(f"METRIC: macro_f1={metrics['macro_f1']:.4f}  error(1-F1)={1-metrics['macro_f1']:.4f}")
        print()

    out = {
        "routing_table": {str(k): v for k, v in routing.items()},
        "q1_all_nonempty": q1_ok,
        "q2_sql_results": {q: {"ok": ok, "rows": n} for q, ok, n in q2_results},
        "selected_configs": pipeline_result.selected_configs,
        "best_surrogate": pipeline_result.best_surrogate,
    }
    out_path = results / "zero_accuracy_diagnosis.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

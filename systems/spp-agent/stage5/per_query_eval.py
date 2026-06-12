"""Ground-truth per-query F1 evaluation (stage5 firewall only)."""

from __future__ import annotations

from typing import Any

from pipeline.evaluation import (
    _alignment_keys_for_match,
    _eval_context,
    _normalize_join_keys_case_insensitive,
    _run_gold_sql,
)
from pipeline.execution import execute_sql_on_db
from utils.logging import setup_logger

logger = setup_logger("spp.stage5.per_query")


def evaluate_per_query_f1(instance, db: dict) -> dict[str, float]:
    """
    Compute macro-F1 per query_id for one materialized database.
    Must only be called from stage5 / post-hoc evaluation paths.
    """
    from evaluation.metrics import MetricCalculator
    from evaluation.query_manifest import QueryManifest
    from evaluation.row_matcher import RowMatcher

    settings, parser, attributes, _ = _eval_context(instance)
    scores: dict[str, float] = {}

    for q_idx, query in enumerate(instance.queries, start=1):
        qid = str(query.get("query_id", q_idx))
        sql = query["sql_query"]
        try:
            pred_df = execute_sql_on_db(db, sql)
            gold_df = _run_gold_sql(instance, sql)
            manifest = QueryManifest(sql, parser.parse(sql), attributes)
            join_keys = _alignment_keys_for_match(manifest, pred_df, gold_df)
            pred_aligned, gold_aligned = _normalize_join_keys_case_insensitive(
                pred_df, gold_df, join_keys
            )
            matcher = RowMatcher(settings=settings)
            match_result = matcher.match(
                gold_df=gold_aligned,
                pred_df=pred_aligned,
                primary_keys=join_keys,
                secondary_key=None,
                attr_descriptions=attributes,
                query_type=manifest.parsed.query_type,
            )
            metrics = MetricCalculator(manifest, settings).compute(match_result)
            scores[qid] = float(metrics["macro_f1"])
        except Exception as exc:
            logger.warning("per_query_eval failed qid=%s: %s", qid, exc)
            scores[qid] = 0.0

    return scores


def mean_f1(per_query: dict[str, float]) -> float:
    if not per_query:
        return 0.0
    return float(sum(per_query.values()) / len(per_query))


def spp_routing_mean_f1(
    per_query_by_config: dict[str, dict[str, float]],
    routing: dict[str, str],
    query_ids: list[str],
) -> float:
    """Mean F1 under per-query routing (best probed config per query)."""
    if not query_ids:
        return 0.0
    total = 0.0
    for qid in query_ids:
        cid = routing.get(qid)
        if cid is None or cid not in per_query_by_config:
            total += 0.0
            continue
        total += per_query_by_config[cid].get(qid, 0.0)
    return total / len(query_ids)


def best_single_config_mean_f1(per_query_by_config: dict[str, dict[str, float]]) -> tuple[str, float]:
    best_id = ""
    best_score = -1.0
    for cid, pq in per_query_by_config.items():
        m = mean_f1(pq)
        if m > best_score:
            best_score = m
            best_id = cid
    return best_id, best_score if best_score >= 0 else 0.0

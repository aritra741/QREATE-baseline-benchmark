from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

from data.loader import load_ground_truth
from data.query_alignment import restrict_ground_truth_tables
from pipeline.execution import execute_sql_on_db
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.evaluation")


def _ensure_eval_imports(benchu_root: Path) -> None:
    root = str(benchu_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def _query_error(pred_df: pd.DataFrame, gold_df: pd.DataFrame, macro_f1: float) -> float:
    return 1.0 - float(macro_f1)


def _resolve_alignment_keys(
    keys: list[str],
    pred_df: pd.DataFrame,
    gold_df: pd.DataFrame,
) -> list[str]:
    """Map parser keys (e.g. player.position) to names present in SQL result frames."""
    resolved: list[str] = []
    for key in keys:
        candidates = [key]
        if "." in key:
            candidates.append(key.split(".", 1)[1])
        chosen = next(
            (c for c in candidates if c in pred_df.columns and c in gold_df.columns),
            None,
        )
        if chosen is None:
            chosen = next((c for c in candidates if c in pred_df.columns or c in gold_df.columns), key)
        if chosen not in resolved:
            resolved.append(chosen)
    return resolved if resolved else list(keys)


def _normalize_join_keys_case_insensitive(
    pred_df: pd.DataFrame,
    gold_df: pd.DataFrame,
    join_keys: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resolve alignment keys and lowercase string join-key values before row alignment."""
    keys = _resolve_alignment_keys(join_keys, pred_df, gold_df)
    pred = pred_df.copy()
    gold = gold_df.copy()
    for key in keys:
        for df in (pred, gold):
            if key not in df.columns:
                continue
            col = df[key]
            if pd.api.types.is_string_dtype(col) or col.dtype == object:
                df[key] = col.map(lambda v: v.lower() if isinstance(v, str) else v)
    return pred, gold


def _alignment_keys_for_match(
    manifest,
    pred_df: pd.DataFrame,
    gold_df: pd.DataFrame,
) -> list[str]:
    """Resolved primary keys used by RowMatcher after frame normalization."""
    return _resolve_alignment_keys(list(manifest.primary_keys), pred_df, gold_df)


def _should_restrict_gt_to_corpus(instance) -> bool:
    meta = instance.metadata or {}
    if "restrict_gt_to_corpus" in meta:
        return bool(meta["restrict_gt_to_corpus"])
    if meta.get("sampled_player_ids"):
        return True
    return bool(load_config().get("phase0", {}).get("restrict_gt_to_corpus", False))


def _post_process_gold_df(df: pd.DataFrame, benchu_root: Path | None = None) -> pd.DataFrame:
    if benchu_root is None:
        benchu_root = Path(load_config()["paths"]["benchu_root"])
    _ensure_eval_imports(benchu_root)
    from evaluation.utils import clean_string_columns, standardize_column_name

    renamed = {col: standardize_column_name(col) for col in df.columns}
    df = df.rename(columns=renamed)
    return clean_string_columns(df)


def _eval_context(instance) -> tuple[Any, ...]:
    from evaluation.config import EvalSettings, load_json
    from evaluation.sql_parser import SqlParser

    cfg = load_config()
    benchu_root = Path(cfg["paths"]["benchu_root"])
    _ensure_eval_imports(benchu_root)

    settings = EvalSettings(llm_provider="none")
    parser = SqlParser()
    gt_dir = benchu_root / "Query" / instance.dataset_name
    attr_files = sorted(gt_dir.glob("*_attributes.json"))
    if not attr_files:
        raise FileNotFoundError("Attributes JSON not found for evaluation.")
    attributes = load_json(attr_files[0])
    return settings, parser, attributes, gt_dir


def _run_gold_sql(instance, sql: str) -> pd.DataFrame:
    if _should_restrict_gt_to_corpus(instance):
        cfg = load_config()
        benchu_root = Path(cfg["paths"]["benchu_root"])
        gt = load_ground_truth(instance.dataset_name)
        restricted = restrict_ground_truth_tables(gt, instance.corpus)
        logger.debug(
            "Gold SQL on corpus-restricted GT (n_player_rows=%d, sampled_ids=%d)",
            len(restricted.get("player", [])),
            len((instance.metadata or {}).get("sampled_player_ids", [])),
        )
        return _post_process_gold_df(execute_sql_on_db(restricted, sql), benchu_root)

    from evaluation.gt_runner import GtRunner

    _, _, attributes, gt_dir = _eval_context(instance)
    gt_runner = GtRunner(gt_dir=gt_dir, attributes=attributes)
    return gt_runner.run(sql)


def evaluate_config(
    instance,
    config_id: str,
    db: dict[str, pd.DataFrame],
    *,
    max_queries: int | None = None,
) -> float:
    """
    Post-hoc oracle evaluation for a single populated database.
    Returns average query error (1 - macro_f1).
    """
    from evaluation.metrics import MetricCalculator
    from evaluation.query_manifest import QueryManifest
    from evaluation.row_matcher import RowMatcher

    settings, parser, attributes, _ = _eval_context(instance)

    queries = instance.queries
    if max_queries is not None:
        queries = queries[:max_queries]

    logger.info(
        "Evaluating config=%s queries=%d/%d",
        config_id,
        len(queries),
        len(instance.queries),
    )

    errors: list[float] = []
    for q_idx, query in enumerate(queries, start=1):
        sql = query["sql_query"]
        qid = query.get("query_id", q_idx)
        try:
            pred_df = execute_sql_on_db(db, sql)
            gold_df = _run_gold_sql(instance, sql)
        except Exception as exc:
            logger.warning("Query %s failed execution: %s", qid, exc)
            errors.append(1.0)
            continue

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
        err = _query_error(pred_df, gold_df, metrics["macro_f1"])
        errors.append(err)
        logger.info(
            "Query %s error=%.4f macro_f1=%.4f pred_rows=%d gold_rows=%d",
            qid,
            err,
            metrics["macro_f1"],
            match_result.len_pred,
            match_result.len_gold,
        )

    avg_error = float(sum(errors) / len(errors)) if errors else 1.0
    logger.info("Config %s average_error=%.4f over %d queries", config_id, avg_error, len(errors))
    return avg_error


def evaluate_spp_set(instance, selected_config_ids: list[str], dbs: dict[str, dict[str, pd.DataFrame]]) -> float:
    """
    Err(SPP) = (1/|Q|) sum_q min_{c in SPP} Err(q,c)
    """
    if not instance.queries or not selected_config_ids:
        return 1.0

    from evaluation.metrics import MetricCalculator
    from evaluation.query_manifest import QueryManifest
    from evaluation.row_matcher import RowMatcher

    settings, parser, attributes, _ = _eval_context(instance)

    total = 0.0
    for query in instance.queries:
        sql = query["sql_query"]
        q_errors: list[float] = []
        for cid in selected_config_ids:
            db = dbs[cid]
            try:
                pred_df = execute_sql_on_db(db, sql)
            except Exception:
                q_errors.append(1.0)
                continue

            try:
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
                q_errors.append(1.0 - metrics["macro_f1"])
            except Exception:
                q_errors.append(1.0)

        total += min(q_errors) if q_errors else 1.0

    return total / len(instance.queries)

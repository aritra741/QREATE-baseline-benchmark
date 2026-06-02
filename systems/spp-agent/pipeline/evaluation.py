from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from pipeline.execution import execute_sql_on_db
from utils.logging import setup_logger

logger = setup_logger("spp.evaluation")


def _ensure_eval_imports(benchu_root: Path) -> None:
    root = str(benchu_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def _query_error(pred_df: pd.DataFrame, gold_df: pd.DataFrame, macro_f1: float) -> float:
    return 1.0 - float(macro_f1)


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
    from evaluation.config import EvalSettings
    from evaluation.gt_runner import GtRunner
    from evaluation.metrics import MetricCalculator
    from evaluation.query_manifest import QueryManifest
    from evaluation.row_matcher import RowMatcher
    from evaluation.sql_parser import SqlParser
    from utils.config import load_config

    cfg = load_config()
    benchu_root = Path(cfg["paths"]["benchu_root"])
    _ensure_eval_imports(benchu_root)

    settings = EvalSettings(llm_provider="none")
    parser = SqlParser()
    gt_dir = benchu_root / "Query" / instance.dataset_name
    attr_files = sorted((benchu_root / "Query" / instance.dataset_name).glob("*_attributes.json"))
    if not attr_files:
        raise FileNotFoundError("Attributes JSON not found for evaluation.")
    attributes = __import__("evaluation.config", fromlist=["load_json"]).load_json(attr_files[0])
    gt_runner = GtRunner(gt_dir=gt_dir, attributes=attributes)

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
            gold_df = gt_runner.run(sql)
        except Exception as exc:
            logger.warning("Query %s failed execution: %s", qid, exc)
            errors.append(1.0)
            continue

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

            from evaluation.config import EvalSettings
            from evaluation.gt_runner import GtRunner
            from evaluation.metrics import MetricCalculator
            from evaluation.query_manifest import QueryManifest
            from evaluation.row_matcher import RowMatcher
            from evaluation.sql_parser import SqlParser
            from utils.config import load_config

            cfg = load_config()
            benchu_root = Path(cfg["paths"]["benchu_root"])
            _ensure_eval_imports(benchu_root)
            settings = EvalSettings(llm_provider="none")
            parser = SqlParser()
            gt_dir = benchu_root / "Query" / instance.dataset_name
            attr_files = sorted(gt_dir.glob("*_attributes.json"))
            attributes = __import__("evaluation.config", fromlist=["load_json"]).load_json(attr_files[0])
            gt_runner = GtRunner(gt_dir=gt_dir, attributes=attributes)

            try:
                gold_df = gt_runner.run(sql)
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
                q_errors.append(1.0 - metrics["macro_f1"])
            except Exception:
                q_errors.append(1.0)

        total += min(q_errors) if q_errors else 1.0

    return total / len(instance.queries)

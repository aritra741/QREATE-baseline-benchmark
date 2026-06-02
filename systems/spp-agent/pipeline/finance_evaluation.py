from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data.finance_support import FINANCE_QUERY_DATASET, execute_finance_sql, normalize_finance_sql
from pipeline.evaluation import _ensure_eval_imports, _query_error
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.finance_evaluation")


def evaluate_query_errors(instance, db: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Return query_id -> error for one populated database."""
    from evaluation.config import EvalSettings
    from evaluation.gt_runner import GtRunner
    from evaluation.metrics import MetricCalculator
    from evaluation.query_manifest import QueryManifest
    from evaluation.row_matcher import RowMatcher
    from evaluation.sql_parser import SqlParser

    cfg = load_config()
    benchu_root = Path(cfg["paths"]["benchu_root"])
    _ensure_eval_imports(benchu_root)

    settings = EvalSettings(llm_provider="none")
    parser = SqlParser()
    gt_dir = benchu_root / "Query" / FINANCE_QUERY_DATASET
    attr_files = sorted(gt_dir.glob("*_attributes.json"))
    if not attr_files:
        raise FileNotFoundError("Finance attributes JSON not found.")
    attributes = __import__("evaluation.config", fromlist=["load_json"]).load_json(attr_files[0])
    gt_runner = GtRunner(gt_dir=gt_dir, attributes=attributes)

    errors: dict[str, float] = {}
    for query in instance.queries:
        qid = query["query_id"]
        sql = normalize_finance_sql(query["sql_query"])
        try:
            pred_df = execute_finance_sql(db, sql)
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
            errors[qid] = _query_error(pred_df, gold_df, metrics["macro_f1"])
        except Exception as exc:
            logger.warning("Query %s failed: %s", qid, exc)
            errors[qid] = 1.0
    return errors


def evaluate_spp_set_finance(instance, selected_config_ids: list[str], dbs: dict[str, dict[str, pd.DataFrame]]) -> float:
    if not instance.queries or not selected_config_ids:
        return 1.0

    total = 0.0
    for query in instance.queries:
        sql = normalize_finance_sql(query["sql_query"])
        q_errors: list[float] = []
        for cid in selected_config_ids:
            db = dbs[cid]
            try:
                pred_df = execute_finance_sql(db, sql)
            except Exception:
                q_errors.append(1.0)
                continue

            from evaluation.config import EvalSettings
            from evaluation.gt_runner import GtRunner
            from evaluation.metrics import MetricCalculator
            from evaluation.query_manifest import QueryManifest
            from evaluation.row_matcher import RowMatcher
            from evaluation.sql_parser import SqlParser

            cfg = load_config()
            benchu_root = Path(cfg["paths"]["benchu_root"])
            _ensure_eval_imports(benchu_root)
            settings = EvalSettings(llm_provider="none")
            parser = SqlParser()
            gt_dir = benchu_root / "Query" / FINANCE_QUERY_DATASET
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


def build_error_matrix(instance, probe_data) -> tuple[pd.DataFrame, dict[str, float]]:
    query_ids = [q["query_id"] for q in instance.queries]
    rows: list[dict[str, float | str]] = []
    avg_errors: dict[str, float] = {}

    for cid in probe_data.config_ids:
        db = probe_data.databases[cid]
        q_errors = evaluate_query_errors(instance, db)
        row: dict[str, float | str] = {"config_id": cid}
        for qid in query_ids:
            row[qid] = q_errors.get(qid, 1.0)
        rows.append(row)
        avg_errors[cid] = sum(q_errors.values()) / len(q_errors) if q_errors else 1.0

    matrix = pd.DataFrame(rows).set_index("config_id")
    return matrix, avg_errors

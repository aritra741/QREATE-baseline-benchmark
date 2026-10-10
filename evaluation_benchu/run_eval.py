"""
评测脚本使用说明
---------------
用途：对单条 SQL 的预测结果与 GT 执行对齐和准确率评估，生成 gold/matched CSV 及 acc.json。

最小示例：
# Player Select
python3 -m evaluation.run_eval \
  --dataset Player \
  --task Select \
  --sql-file evaluation/demo_acc_result/Player/Select/select_queries_player/1/sql.json \
  --result-csv evaluation/demo_acc_result/Player/Select/select_queries_player/1/result.csv

# Player Filter
python3 -m evaluation.run_eval \
  --dataset Player \
  --task Filter \
  --sql-file evaluation/demo_acc_result/Player/Filter/filter_queries_player/1/sql.json \
  --result-csv evaluation/demo_acc_result/Player/Filter/filter_queries_player/1/result.csv

# Player Agg 
python3 -m evaluation.run_eval \
  --dataset Player \
  --task Agg \
  --sql-file evaluation/demo_acc_result/Player/Agg/agg_queries/2/sql.json \
  --result-csv evaluation/demo_acc_result/Player/Agg/agg_queries/2/result.csv

# Player Join
python3 -m evaluation.run_eval \
  --dataset Player \
  --task Join \
  --sql-file evaluation/demo_acc_result/Player/Join/join_queries/2/sql.json \
  --result-csv evaluation/demo_acc_result/Player/Join/join_queries/2/join_player_2.csv

# Player Mixed filter_join
python3 -m evaluation.run_eval \
  --dataset Player \
  --task Mixed \
  --sql-file  evaluation/demo_acc_result/Player/Mixed/mixed_queries_filter_join/2/sql.json \
  --result-csv  evaluation/demo_acc_result/Player/Mixed/mixed_queries_filter_join/2/filter_join_player_2.csv

常用参数：
- --dataset：数据集名称，对应 Query/{dataset} 下的 GT CSV 和 attributes。
- --task：任务名（Select/Filter/Agg/Join/Mixed），仅用于默认路径推断。
- --sql-file：SQL 文件或包含 {"sql": "..."} 的 sql.json。
- --result-csv：预测结果 CSV，若省略则按 demo 路径推断。
- --query-id：当 sql-file 是多 SQL 原文件时用于推断默认 result 路径的编号。
- --attributes-file：可显式指定 *_attributes.json，默认 Query/{dataset}/*_attributes.json。
- --gt-dir：GT CSV 目录，默认 Query/{dataset}。
- --output-dir：输出目录，默认 result.csv 同级的 acc_result。
- --primary-key：多实体场景的二级主键；未指定时使用解析得到的主键。
- --float-tolerance：浮点数比较的绝对容忍度。
- --multi-value-sep：多值字符串的分隔符（默认 "||"）。
- --llm-provider/--llm-model：可选的 LLM 语义比对配置；默认为 aihubmix（用 LLM）。
- --log-level：日志级别，默认 INFO。
- --semantic-join：开启 GT 执行阶段的语义 Join 补齐；可选调节 topK/threshold/max-query/vector-prefilter/LLM provider。

输出：
{output_dir}/gold_result.csv           # duckdb 执行 GT SQL 的结果
{output_dir}/matched_result.csv        # 预测结果对齐后
{output_dir}/matched_gold_result.csv   # GT 对齐后
{output_dir}/acc.json                  # 列级与宏平均指标
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlglot import exp, parse_one

from .tools.config import EvalSettings, Paths
from .tools.gt_runner import GtRunner
from .tools.logging_utils import setup_logger
from .tools.metrics import MetricCalculator
from .tools.query_manifest import QueryManifest
from .tools.result_loader import ResultLoader
from .tools.result_writer import ResultWriter
from .tools.row_matcher import RowMatcher
from .tools.sql_parser import SqlParser
from .tools.utils import normalize_empty_cells, standardize_column_name


def infer_result_path(dataset: str, task: str, sql_file: Path, query_id: int) -> Path:
    return Path("evaluation") / "demo_acc_result" / dataset / task / sql_file.stem / str(query_id) / "result.csv"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run evaluation for a single SQL query.")
    parser.add_argument("--dataset", required=True, help="Dataset name, e.g., Player")
    parser.add_argument("--sql-file", required=True, type=Path, help="Path to sql or sql.json")
    parser.add_argument("--result-csv", type=Path, help="Path to system output CSV")
    parser.add_argument("--task", default="Select", help="Task folder name used for default path inference")
    parser.add_argument("--query-id", type=int, default=1, help="Query index inside the SQL file when inferring paths")
    parser.add_argument("--attributes-file", type=Path, help="Path to *_attributes.json; defaults to Query/{dataset}/*_attributes.json")
    parser.add_argument("--gt-dir", type=Path, help="Directory containing GT CSV tables; defaults to Query/{dataset}")
    parser.add_argument("--output-dir", type=Path, help="Directory to store acc_result outputs; defaults to sibling of result.csv")
    parser.add_argument("--primary-key", help="Optional secondary key for multi-entity alignment")
    parser.add_argument("--float-tolerance", type=float, default=0.0, help="Absolute tolerance for float comparison")
    parser.add_argument("--multi-value-sep", default="||", help="Separator for multi_str attributes")
    parser.add_argument("--llm-provider", default="aihubmix", help="LLM provider name, set to 'none' to disable")
    parser.add_argument("--llm-model", default="openai/gpt-4.1-mini",help="LLM model name")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument("--semantic-join", action="store_true", help="Enable semantic join augmentation for GT execution")
    parser.add_argument("--semantic-join-topk", type=int, default=5, help="Vector prefilter topK for semantic join")
    parser.add_argument(
        "--semantic-join-threshold",
        type=float,
        default=0.0,
        help="Similarity threshold for semantic join vector prefilter",
    )
    parser.add_argument(
        "--semantic-join-max-query",
        type=int,
        default=200,
        help="Max query rows to send into semantic matching (protects from explosion)",
    )
    parser.add_argument(
        "--semantic-join-llm-provider",
        help="Optional override LLM provider for semantic join; also syncs eval LLM config",
    )
    parser.add_argument(
        "--semantic-join-llm-model",
        help="Optional override LLM model for semantic join; also syncs eval LLM config",
    )
    parser.add_argument(
        "--semantic-join-vector-prefilter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Toggle vector prefilter for semantic join (default on)",
    )
    parser.add_argument(
        "--semantic-join-debug-dir",
        type=Path,
        help="Optional directory to dump semantic join debug artifacts (candidates/hits)",
    )
    return parser


def _inject_id_columns(manifest: QueryManifest, logger) -> str:
    """
    Ensure non-aggregation GT SQL always returns id columns for alignment.
    For joins we add {table}.id for each participating table; for single-table
    non-aggregation queries we add bare id. Aggregations are left untouched.
    """
    parsed = manifest.parsed
    if parsed.query_type == "aggregation":
        return manifest.sql

    existing: set[str] = set()
    for item in parsed.select_items:
        if item.output_name:
            existing.add(standardize_column_name(item.output_name).lower())
        if item.source_name:
            existing.add(standardize_column_name(item.source_name).lower())

    if parsed.query_type == "join":
        candidates = [f"{table}.id" for table in parsed.tables]
    else:
        candidates = ["id"]

    required = []
    for col in candidates:
        normalized = standardize_column_name(col).lower()
        if normalized not in existing:
            required.append(col)

    if not required:
        return manifest.sql

    try:
        expr = parse_one(manifest.sql, error_level="ignore")
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to parse SQL for id injection: %s", exc)
        return manifest.sql
    if expr is None:  # pragma: no cover - defensive fallback
        logger.warning("Failed to parse SQL for id injection: empty expression")
        return manifest.sql

    for col in required:
        if "." in col:
            table, column = col.split(".", 1)
            expr = expr.select(exp.alias_(exp.column(column, table=table), col, quoted=True))
        else:
            expr = expr.select(exp.alias_(exp.column(col), col))

    patched_sql = expr.sql(dialect="duckdb")
    logger.debug("Injected id columns into GT SQL: %s", required)
    return patched_sql


def main():
    arg_parser = build_arg_parser()
    args = arg_parser.parse_args()

    sql_file: Path = args.sql_file
    result_csv = args.result_csv or infer_result_path(args.dataset, args.task, sql_file, args.query_id)

    llm_provider = args.llm_provider
    llm_model = args.llm_model
    if args.semantic_join_llm_provider:
        llm_provider = args.semantic_join_llm_provider
    if args.semantic_join_llm_model:
        llm_model = args.semantic_join_llm_model

    settings = EvalSettings(
        float_tolerance=args.float_tolerance,
        multi_value_sep=args.multi_value_sep,
        llm_provider=llm_provider,
        llm_model=llm_model,
        log_level=args.log_level,
        semantic_join_enabled=bool(args.semantic_join),
        semantic_join_topk=args.semantic_join_topk,
        semantic_join_score_threshold=args.semantic_join_threshold,
        semantic_join_max_query=args.semantic_join_max_query,
        semantic_join_debug_dir=args.semantic_join_debug_dir,
        semantic_join_vector_prefilter_enabled=bool(args.semantic_join_vector_prefilter),
    )

    paths = Paths(
        dataset=args.dataset,
        sql_file=sql_file,
        result_csv=result_csv,
        attributes_file=args.attributes_file,
        output_dir=args.output_dir,
        gt_dir=args.gt_dir,
    )

    logger = setup_logger("run_eval", level=settings.log_level)
    logger.info("Starting evaluation for dataset=%s sql=%s", args.dataset, sql_file)

    parser = SqlParser()
    manifest = QueryManifest.from_files(sql_file=sql_file, attributes_file=paths.resolve_attributes(), parser=parser)

    if manifest.added_aliases:
        logger.info("Added default aliases for join columns: %s", ", ".join(manifest.added_aliases))
    if manifest.original_sql != manifest.sql:
        logger.debug("Canonicalized SQL for execution: %s", manifest.sql)

    gt_runner = GtRunner(gt_dir=paths.resolve_gt_dir(), attributes=manifest.attributes)
    gt_sql = _inject_id_columns(manifest, logger)
    gold_df = gt_runner.run(gt_sql, parsed_query=manifest.parsed, settings=settings)

    loader = ResultLoader(
        expected_columns=manifest.parsed.output_columns,
        stop_columns=manifest.stop_columns,
        attributes=manifest.attributes,
    )
    pred_df = loader.load(result_csv)

    matcher = RowMatcher(settings=settings)
    match_result = matcher.match(
        gold_df=gold_df,
        pred_df=pred_df,
        primary_keys=manifest.primary_keys,
        secondary_key=args.primary_key,
        attr_descriptions=manifest.attributes,
        query_type=manifest.parsed.query_type,
    )

    numeric_columns: set[str] = set()
    for item in manifest.parsed.select_items:
        col_name = item.output_name
        meta = manifest.get_column_meta(col_name)
        if item.is_agg or (meta and meta.value_type in {"int", "float"}):
            numeric_columns.add(col_name)

    empty_tokens = ["none", "nan", "null", "n/a"]
    match_result.gold_aligned = normalize_empty_cells(
        match_result.gold_aligned, numeric_columns=sorted(numeric_columns), empty_tokens=empty_tokens
    )
    match_result.pred_aligned = normalize_empty_cells(
        match_result.pred_aligned, numeric_columns=sorted(numeric_columns), empty_tokens=empty_tokens
    )

    metric_calculator = MetricCalculator(manifest, settings)
    metrics = metric_calculator.compute(match_result)

    writer = ResultWriter(output_dir=paths.resolve_output_dir())
    writer.write(gold_df, match_result.gold_aligned, match_result.pred_aligned, metrics)

    logger.info("Evaluation finished. Macro F1=%.4f", metrics["macro_f1"])


if __name__ == "__main__":
    main()

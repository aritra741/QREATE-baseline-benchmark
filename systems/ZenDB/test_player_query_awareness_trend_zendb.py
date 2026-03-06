"""
Run Q1..Q10 query-awareness trend benchmarking with ZenDB on Player.

This script reuses existing QUEST/ZenDB components only:
- SQL parser + logical planner from QUEST
- ZenDB physical planner (ZendbTextPhysicalPlanner)
- official UDA-Bench evaluator wiring from WDIRS reference

Strict mode:
- no silent fallbacks
- any query failure aborts the run
"""

import csv
import json
import logging
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
SYSTEMS_DIR = PROJECT_ROOT / "systems"
WDIRS_DIR = PROJECT_ROOT / "systems" / "WDIRS"

sys.path.insert(0, str(SYSTEMS_DIR))
sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from config import QUERY_DIR, RESULTS_DIR  # type: ignore
from token_counter import GLOBAL_COUNTER, ensure_precise_tokenizer_ready

from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.row_matcher import RowMatcher as _RowMatcher
from evaluation.sql_parser import SqlParser as _SqlParser
from test_player_query_awareness_trend import (  # type: ignore
    _infer_identity_col_for_query,
    evaluate_with_official_framework,
    parse_trend_queries,
)


DATASET = "Player"
DATASET_QUERY = "Player"
TREND_SQL_FILE = QUERY_DIR / DATASET_QUERY / "query_aware_trend_queries.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_zendb"
ZENDB_MODEL = "ollama/qwen2.5:7b-instruct"
ZENDB_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
ZENDB_INDEX_TYPE = os.getenv("ZENDB_INDEX_TYPE", "ZenDBDoc")

IDENTITY_COLUMNS: Dict[str, str] = {
    "city": "city_name",
    "player": "name",
    "team": "team_name",
    "owner": "name",
}


@dataclass
class TrendQueryMetrics:
    query_id: str
    query_text: str
    success: bool
    delta_type: str
    latency_s: float
    result_rows: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    macro_f1: float
    macro_precision: float
    macro_recall: float
    gt_result_count: int
    matched_rows: int
    is_agg: bool
    error: str | None = None


def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fh = logging.FileHandler(log_file)
    ch = logging.StreamHandler(sys.stdout)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(fh)
    root.addHandler(ch)


def _zendb_imports() -> Dict[str, Any]:
    from quest.sql.parser import sqlparser
    from quest.sql.planner.logical import LogicalPlanner
    from quest.sql.planner.joinlogical_quest_paper import JoinLogicalPlanner
    from quest.sql.processer.processer import Processer
    from quest.db.indexer.indexer import load_all_indexer
    from quest.core.llm.sampler import AttrSampler
    from quest.core.llm.llm_query import TextLLMQuerier, LLMInfo
    import quest.conf.settings as qsettings

    from systems.ZenDB.zendb_physical import ZendbTextPhysicalPlanner

    return {
        "sqlparser": sqlparser,
        "LogicalPlanner": LogicalPlanner,
        "JoinLogicalPlanner": JoinLogicalPlanner,
        "Processer": Processer,
        "load_all_indexer": load_all_indexer,
        "AttrSampler": AttrSampler,
        "TextLLMQuerier": TextLLMQuerier,
        "LLMInfo": LLMInfo,
        "qsettings": qsettings,
        "ZendbTextPhysicalPlanner": ZendbTextPhysicalPlanner,
    }


def _set_model_settings(qsettings: Any) -> None:
    qsettings.OLLAMA_BASE = ZENDB_API_BASE
    qsettings.LLM_MODEL = ZENDB_MODEL
    qsettings.API_BASE = ZENDB_API_BASE
    qsettings.GPT_MODEL = ZENDB_MODEL
    qsettings.GPT_API_BASE = ZENDB_API_BASE
    os.environ["OPENAI_API_KEY"] = "ollama"
    os.environ["OPENAI_BASE"] = ZENDB_API_BASE


def _extract_tables_from_sql(sql: str) -> List[str]:
    tables: List[str] = []
    pattern = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)|\bJOIN\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
    for m in pattern.finditer(sql):
        tbl = (m.group(1) or m.group(2) or "").strip().lower()
        if tbl and tbl not in tables:
            tables.append(tbl)
    if not tables:
        raise ValueError(f"Could not parse tables from SQL: {sql}")
    return tables


def _build_prompt_schema(attributes: Dict[str, Any], tables: List[str]) -> str:
    lines: List[str] = []
    for table in tables:
        if table not in attributes:
            raise ValueError(f"Missing attribute schema for table '{table}'")
        attr_def = attributes[table]
        if not isinstance(attr_def, dict):
            raise ValueError(f"Invalid attribute schema format for table '{table}'")
        for attr_name, attr_info in attr_def.items():
            if not isinstance(attr_info, dict):
                raise ValueError(f"Invalid attribute schema for {table}.{attr_name}")
            desc = str(attr_info.get("description", "")).strip()
            lines.append(f"{attr_name}: {desc}")
    if not lines:
        raise RuntimeError("Built empty ZenDB prompt schema.")
    return "\n".join(lines)


def _llm_snapshot(llm_info_cls: Any) -> Tuple[int, int]:
    p = int(llm_info_cls.tot_input_tokens)
    c = int(llm_info_cls.tot_output_tokens)
    if p < 0 or c < 0:
        raise RuntimeError(f"Invalid LLM counters: input={p}, output={c}")
    return p, c


def _llm_delta(llm_info_cls: Any, before: Tuple[int, int]) -> Tuple[int, int]:
    now = _llm_snapshot(llm_info_cls)
    dp = now[0] - before[0]
    dc = now[1] - before[1]
    if dp < 0 or dc < 0:
        raise RuntimeError(f"LLM counters moved backwards: before={before}, now={now}")
    return dp, dc


def _result_to_dataframe(result: Any) -> pd.DataFrame:
    if result is None:
        raise RuntimeError("ZenDB execution returned None.")
    if isinstance(result, pd.DataFrame):
        return result
    if isinstance(result, list):
        return pd.DataFrame(result)
    if hasattr(result, "to_dataframe"):
        df = result.to_dataframe()
        if not isinstance(df, pd.DataFrame):
            raise RuntimeError("ZenDB result.to_dataframe() did not return DataFrame.")
        return df
    raise RuntimeError(f"Unsupported ZenDB result type: {type(result)}")


def _save_rows_csv(rows: List[Dict[str, Any]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with out_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["_empty"])
        return
    cols: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def _load_indexer_for_tables(load_all_indexer: Any, tables: List[str]) -> Any:
    table_to_type = {table: ZENDB_INDEX_TYPE for table in tables}
    indexer = load_all_indexer(table_to_type=table_to_type)
    if not hasattr(indexer, "table_to_indexer") or not indexer.table_to_indexer:
        raise RuntimeError("ZenDB indexer loaded with no tables.")

    for table in tables:
        idx, idx_type = indexer.get_indexer(table)
        if idx is None:
            raise RuntimeError(f"No index loaded for table '{table}'")
        if idx_type != ZENDB_INDEX_TYPE:
            raise RuntimeError(
                f"Index type mismatch for '{table}': expected '{ZENDB_INDEX_TYPE}', got '{idx_type}'"
            )
    return indexer


def execute_query_via_zendb(
    zendb_mod: Dict[str, Any],
    sql: str,
    prompt_schema: str,
    indexer: Any,
) -> pd.DataFrame:
    sqlparser = zendb_mod["sqlparser"]
    logical_planner_cls = zendb_mod["LogicalPlanner"]
    join_logical_planner_cls = zendb_mod["JoinLogicalPlanner"]
    physical_planner_cls = zendb_mod["ZendbTextPhysicalPlanner"]
    processer_cls = zendb_mod["Processer"]
    attr_sampler_cls = zendb_mod["AttrSampler"]
    text_querier_cls = zendb_mod["TextLLMQuerier"]

    ast = sqlparser.parse_sql(sql)
    tables = _extract_tables_from_sql(sql)
    use_join_planner = len(tables) > 1
    logical_planner = join_logical_planner_cls() if use_join_planner else logical_planner_cls()
    logical_plan = logical_planner.build_logical_plan(ast)

    sampler = attr_sampler_cls(schema=prompt_schema)
    querier = text_querier_cls(prompt=prompt_schema, llm=ZENDB_MODEL, api_base=ZENDB_API_BASE)

    for table in tables:
        idx_obj, _ = indexer.get_indexer(table)
        sampler.try_sample(idx_obj, prompt_schema)

    physical_planner = physical_planner_cls(indexer, querier, sampler=sampler)
    physical_plan = physical_planner.build(logical_plan)

    processer = processer_cls()
    result = processer.process(physical_plan)
    return _result_to_dataframe(result)


def run_trend_queries_zendb(run_dir: Path) -> List[TrendQueryMetrics]:
    zendb_mod = _zendb_imports()
    qsettings = zendb_mod["qsettings"]
    _set_model_settings(qsettings)

    load_all_indexer = zendb_mod["load_all_indexer"]
    llm_info_cls = zendb_mod["LLMInfo"]

    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    plots_dir = run_dir / "plots"
    query_eval_db_dir = run_dir / "query_eval_dbs"

    run_dir.mkdir(parents=True, exist_ok=True)
    query_results_dir.mkdir(parents=True, exist_ok=True)
    query_tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    query_eval_db_dir.mkdir(parents=True, exist_ok=True)

    attributes: Dict[str, Any] = _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    if not attributes:
        raise RuntimeError(f"Missing or empty attributes JSON: {ATTRIBUTES_FILE}")

    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")

    all_tables: List[str] = []
    for _, qtext in trend_queries:
        for t in _extract_tables_from_sql(qtext):
            if t not in all_tables:
                all_tables.append(t)
    if not all_tables:
        raise RuntimeError("No tables parsed from trend queries.")

    indexer = _load_indexer_for_tables(load_all_indexer, all_tables)

    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info(f"Executing {query_id} with ZenDB")
        t0 = time.time()
        before = _llm_snapshot(llm_info_cls)

        tables = _extract_tables_from_sql(query_text)
        prompt_schema = _build_prompt_schema(attributes, tables)
        result_df = execute_query_via_zendb(
            zendb_mod=zendb_mod,
            sql=query_text,
            prompt_schema=prompt_schema,
            indexer=indexer,
        )

        rows = result_df.to_dict("records")
        latency = time.time() - t0
        d_prompt, d_completion = _llm_delta(llm_info_cls, before)
        d_total = d_prompt + d_completion
        GLOBAL_COUNTER.record(input_tokens=d_prompt, output_tokens=d_completion, operation="zendb")

        out_csv = query_tables_dir / f"{query_id}.csv"
        out_json = query_tables_dir / f"{query_id}.json"
        _save_rows_csv(rows, out_csv)
        out_json.write_text(json.dumps(rows, indent=2, default=str))

        query_eval_db = query_eval_db_dir / f"{query_id}.db"
        eval_out = evaluate_with_official_framework(
            query_text,
            rows,
            gt_runner=eval_gt_runner,
            sql_parser=eval_sql_parser,
            row_matcher=eval_row_matcher,
            settings=eval_settings,
            attributes=attributes,
            identity_col=_infer_identity_col_for_query(query_text, IDENTITY_COLUMNS),
            phase2_db=query_eval_db,
            output_dir=query_results_dir / query_id,
        )

        item = TrendQueryMetrics(
            query_id=query_id,
            query_text=query_text,
            success=True,
            delta_type="ZenDB",
            latency_s=latency,
            result_rows=len(rows),
            prompt_tokens=d_prompt,
            completion_tokens=d_completion,
            total_tokens=d_total,
            macro_f1=eval_out.get("macro_f1", 0.0),
            macro_precision=eval_out.get("macro_precision", 0.0),
            macro_recall=eval_out.get("macro_recall", 0.0),
            gt_result_count=eval_out.get("gt_result_count", 0),
            matched_rows=eval_out.get("matched_rows", 0),
            is_agg=eval_out.get("is_agg", False),
        )
        metrics.append(item)

        acc_path = query_results_dir / query_id / "acc.json"
        acc_path.parent.mkdir(parents=True, exist_ok=True)
        acc_data = {}
        if acc_path.exists():
            acc_data = json.loads(acc_path.read_text())
        acc_data["query_id"] = query_id
        acc_data["latency_s"] = round(latency, 4)
        acc_data["prompt_tokens"] = d_prompt
        acc_data["completion_tokens"] = d_completion
        acc_data["total_tokens"] = d_total
        acc_data["result_rows"] = len(rows)
        acc_data["success"] = True
        acc_data["macro_f1"] = eval_out.get("macro_f1", 0.0)
        acc_data["macro_precision"] = eval_out.get("macro_precision", 0.0)
        acc_data["macro_recall"] = eval_out.get("macro_recall", 0.0)
        acc_path.write_text(json.dumps(acc_data, indent=2))

        logger.info(
            f"{query_id}: rows={item.result_rows} latency={item.latency_s:.3f}s "
            f"tokens={item.total_tokens} F1={item.macro_f1:.3f}"
        )

    return metrics


def save_metrics(metrics: List[TrendQueryMetrics], run_dir: Path) -> None:
    rows = [asdict(m) for m in metrics]
    out_json = run_dir / "trend_metrics.json"
    out_csv = run_dir / "trend_metrics.csv"
    out_json.write_text(json.dumps(rows, indent=2))
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    logger.info(f"Saved metrics JSON: {out_json}")
    logger.info(f"Saved metrics CSV:  {out_csv}")


def plot_metrics(metrics: List[TrendQueryMetrics], run_dir: Path) -> None:
    if not metrics:
        raise RuntimeError("No metrics to plot.")

    ordered = sorted(metrics, key=lambda m: int(m.query_id[1:]))
    x_labels = [m.query_id for m in ordered]
    x = list(range(len(x_labels)))

    result_rows = [m.result_rows for m in ordered]
    token_cost = [m.total_tokens for m in ordered]
    latency = [m.latency_s for m in ordered]
    f1 = [m.macro_f1 for m in ordered]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "Player Query-Awareness Trend with ZenDB (Q1..Q10)",
        fontsize=16,
        fontweight="bold",
    )

    axes[0, 0].plot(x, result_rows, marker="o", color="#7f8c8d")
    axes[0, 0].set_title("Result Table Size (rows)")
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels(x_labels)
    axes[0, 0].set_ylabel("rows")
    axes[0, 0].grid(alpha=0.3)

    axes[0, 1].plot(x, token_cost, marker="o", color="#8e44ad")
    axes[0, 1].set_title("Token Cost")
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels(x_labels)
    axes[0, 1].set_ylabel("tokens")
    axes[0, 1].grid(alpha=0.3)

    axes[1, 0].plot(x, latency, marker="o", color="#2980b9")
    axes[1, 0].set_title("Latency")
    axes[1, 0].set_xticks(x)
    axes[1, 0].set_xticklabels(x_labels)
    axes[1, 0].set_ylabel("seconds")
    axes[1, 0].grid(alpha=0.3)

    axes[1, 1].plot(x, f1, marker="o", color="#27ae60")
    axes[1, 1].set_title("Macro F1 (official evaluator)")
    axes[1, 1].set_xticks(x)
    axes[1, 1].set_xticklabels(x_labels)
    axes[1, 1].set_ylim(0.0, 1.0)
    axes[1, 1].set_ylabel("F1")
    axes[1, 1].grid(alpha=0.3)

    plt.tight_layout()
    plots_dir = run_dir / "plots"
    summary_plot = plots_dir / "query_awareness_trend_summary.png"
    plt.savefig(summary_plot, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved trend summary plot: {summary_plot}")


def main() -> int:
    ensure_precise_tokenizer_ready()

    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    run_tag = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_BASE_DIR / f"run_{run_tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(run_dir / "query_awareness_trend_zendb.log")

    logger.info("Starting Player query-awareness trend test (ZenDB)...")
    logger.info(f"Run directory: {run_dir}")
    logger.info(f"Trend query source: {TREND_SQL_FILE}")
    logger.info(f"Model: {ZENDB_MODEL} @ {ZENDB_API_BASE}")
    logger.info(f"Index type: {ZENDB_INDEX_TYPE}")
    logger.info(f"Identity columns (for eval): {IDENTITY_COLUMNS}")

    try:
        metrics = run_trend_queries_zendb(run_dir)
        save_metrics(metrics, run_dir)
        plot_metrics(metrics, run_dir)

        success_count = sum(1 for m in metrics if m.success)
        avg_f1 = sum(m.macro_f1 for m in metrics) / len(metrics) if metrics else 0.0
        if not math.isfinite(avg_f1):
            raise RuntimeError(f"Average F1 is non-finite: {avg_f1}")
        logger.info("=" * 80)
        logger.info(
            f"Completed: {success_count}/{len(metrics)} queries succeeded, "
            f"avg macro F1={avg_f1:.3f}"
        )
        token_summary = GLOBAL_COUNTER.summary_str()
        logger.info(token_summary)
        token_json_path = run_dir / "token_cost.json"
        GLOBAL_COUNTER.save_json(token_json_path)
        logger.info(f"Token cost JSON saved to: {token_json_path}")
        logger.info(f"Outputs under: {run_dir}")
        logger.info("=" * 80)
        return 0
    except Exception as exc:
        logger.exception(f"ZenDB trend test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

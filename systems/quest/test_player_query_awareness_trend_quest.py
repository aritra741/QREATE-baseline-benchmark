"""
Run Q1..Q10 query-awareness trend benchmarking with QUEST on Player.

This script wires QUEST's SQL parser/planner/executor into the same official
evaluation contract used by other baseline runners.

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

# Needed for `import quest...` namespace package imports.
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

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_quest"
QUEST_MODEL = "ollama/qwen2.5:7b-instruct"
QUEST_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

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


def _quest_imports() -> Dict[str, Any]:
    # Import lazily to avoid import-time side effects unless script runs.
    from quest.sql.parser import sqlparser
    from quest.sql.planner.logical import LogicalPlanner
    from quest.sql.planner.physical import TextPhysicalPlanner
    from quest.sql.processer.processer import Processer
    from quest.db.indexer.indexer import load_all_indexer
    from quest.core.llm.sampler import AttrSampler
    from quest.core.llm.llm_query import TextLLMQuerier, LLMInfo
    from quest.sql.planner.joinlogical_quest_paper import JoinLogicalPlanner
    import quest.conf.settings as qsettings

    return {
        "sqlparser": sqlparser,
        "LogicalPlanner": LogicalPlanner,
        "TextPhysicalPlanner": TextPhysicalPlanner,
        "Processer": Processer,
        "load_all_indexer": load_all_indexer,
        "AttrSampler": AttrSampler,
        "TextLLMQuerier": TextLLMQuerier,
        "LLMInfo": LLMInfo,
        "JoinLogicalPlanner": JoinLogicalPlanner,
        "qsettings": qsettings,
    }


def _set_quest_model_settings(qsettings: Any) -> None:
    # AttrSampler pulls model/api from quest.conf.settings globals.
    qsettings.OLLAMA_BASE = QUEST_API_BASE
    qsettings.LLM_MODEL = QUEST_MODEL
    qsettings.API_BASE = QUEST_API_BASE
    qsettings.GPT_MODEL = QUEST_MODEL
    qsettings.GPT_API_BASE = QUEST_API_BASE
    os.environ["OPENAI_API_KEY"] = "ollama"
    os.environ["OPENAI_BASE"] = QUEST_API_BASE


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


def _sanitize_sql_for_quest(sql: str) -> str:
    """
    QUEST's custom SQL parser rejects standard statement terminators like `;`.
    The shared benchmark query file keeps trailing semicolons for other systems,
    so strip them only at the handoff boundary to QUEST.
    """
    cleaned = sql.strip()
    while cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if not cleaned:
        raise ValueError("Empty SQL after QUEST sanitization.")
    return cleaned


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
        raise RuntimeError("Built empty QUEST prompt schema.")
    return "\n".join(lines)


def _llm_snapshot(llm_info_cls: Any) -> Tuple[int, int]:
    p = int(llm_info_cls.tot_input_tokens)
    c = int(llm_info_cls.tot_output_tokens)
    if p < 0 or c < 0:
        raise RuntimeError(f"Invalid QUEST LLM counters: input={p}, output={c}")
    return p, c


def _llm_delta(llm_info_cls: Any, before: Tuple[int, int]) -> Tuple[int, int]:
    now = _llm_snapshot(llm_info_cls)
    dp = now[0] - before[0]
    dc = now[1] - before[1]
    if dp < 0 or dc < 0:
        raise RuntimeError(f"QUEST LLM counters moved backwards: before={before}, now={now}")
    return dp, dc


def _result_to_dataframe(result: Any) -> pd.DataFrame:
    if result is None:
        raise RuntimeError("QUEST execution returned None.")
    if isinstance(result, pd.DataFrame):
        return result
    if isinstance(result, list):
        return pd.DataFrame(result)
    if hasattr(result, "to_dataframe"):
        df = result.to_dataframe()
        if not isinstance(df, pd.DataFrame):
            raise RuntimeError("QUEST result.to_dataframe() did not return DataFrame.")
        return df
    raise RuntimeError(f"Unsupported QUEST result type: {type(result)}")


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


def execute_query_via_quest(
    quest_mod: Dict[str, Any],
    sql: str,
    prompt_schema: str,
    use_join_planner: bool,
    indexer: Any,
) -> pd.DataFrame:
    sqlparser = quest_mod["sqlparser"]
    logical_planner_cls = quest_mod["LogicalPlanner"]
    join_logical_planner_cls = quest_mod["JoinLogicalPlanner"]
    text_physical_planner_cls = quest_mod["TextPhysicalPlanner"]
    processer_cls = quest_mod["Processer"]
    attr_sampler_cls = quest_mod["AttrSampler"]
    text_querier_cls = quest_mod["TextLLMQuerier"]

    quest_sql = _sanitize_sql_for_quest(sql)
    ast = sqlparser.parse_sql(quest_sql)
    logical_planner = join_logical_planner_cls() if use_join_planner else logical_planner_cls()
    logical_plan = logical_planner.build_logical_plan(ast)

    sampler = attr_sampler_cls(schema=prompt_schema)
    querier = text_querier_cls(prompt=prompt_schema, llm=QUEST_MODEL, api_base=QUEST_API_BASE)

    # Initialize evidence sampling for all indexed tables participating in this query.
    for table in _extract_tables_from_sql(quest_sql):
        idx_obj, _ = indexer.get_indexer(table)
        sampler.try_sample(idx_obj, prompt_schema)

    physical_planner = text_physical_planner_cls(indexer, querier, sampler=sampler)
    physical_plan = physical_planner.build(logical_plan)

    processer = processer_cls()
    result = processer.process(physical_plan)
    return _result_to_dataframe(result)


def run_trend_queries_quest(run_dir: Path) -> List[TrendQueryMetrics]:
    quest_mod = _quest_imports()
    qsettings = quest_mod["qsettings"]
    _set_quest_model_settings(qsettings)

    load_all_indexer = quest_mod["load_all_indexer"]
    llm_info_cls = quest_mod["LLMInfo"]

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

    # Load all pre-built indexes from QUEST config path.
    indexer = load_all_indexer(table_to_type=None)
    if not hasattr(indexer, "table_to_indexer") or not indexer.table_to_indexer:
        raise RuntimeError("QUEST indexer loaded with no tables.")

    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info(f"Executing {query_id} with QUEST")
        t0 = time.time()
        before = _llm_snapshot(llm_info_cls)

        tables = _extract_tables_from_sql(query_text)
        prompt_schema = _build_prompt_schema(attributes, tables)
        use_join_planner = len(tables) > 1

        result_df = execute_query_via_quest(
            quest_mod=quest_mod,
            sql=query_text,
            prompt_schema=prompt_schema,
            use_join_planner=use_join_planner,
            indexer=indexer,
        )

        rows = result_df.to_dict("records")
        latency = time.time() - t0
        d_prompt, d_completion = _llm_delta(llm_info_cls, before)
        d_total = d_prompt + d_completion
        GLOBAL_COUNTER.record(input_tokens=d_prompt, output_tokens=d_completion, operation="quest")

        out_csv = query_tables_dir / f"{query_id}.csv"
        out_json = query_tables_dir / f"{query_id}.json"
        _save_rows_csv(rows, out_csv)
        out_json.write_text(json.dumps(rows, indent=2, default=str))

        # Keep path for compatibility with evaluator signature; not required unless
        # augmented fallback query execution is triggered.
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
            delta_type="QUEST",
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
        "Player Query-Awareness Trend with QUEST (Q1..Q10)",
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
    setup_logging(run_dir / "query_awareness_trend_quest.log")

    logger.info("Starting Player query-awareness trend test (QUEST)...")
    logger.info(f"Run directory: {run_dir}")
    logger.info(f"Trend query source: {TREND_SQL_FILE}")
    logger.info(f"Model: {QUEST_MODEL} @ {QUEST_API_BASE}")
    logger.info(f"Identity columns (for eval): {IDENTITY_COLUMNS}")

    try:
        metrics = run_trend_queries_quest(run_dir)
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
        logger.exception(f"QUEST trend test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

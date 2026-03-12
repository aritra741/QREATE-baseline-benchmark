"""
Run Q1..Q10 single-table query-awareness trend benchmarking with UQE on Player.

Queries span SELECT extraction, structured WHERE filters, semantic WHERE
filters, COUNT aggregation, and GROUP BY aggregation — the full range of
operations UQE was designed for (excluding JOINs, which the paper scopes out).

Each query is executed through UQE's standard pipeline:
    parse → plan → optimize → execute

Metrics collected per query: latency, token cost, macro F1/precision/recall
evaluated against the official UDA-Bench ground truth.
"""

import csv
import argparse
import json
import logging
import math
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
WDIRS_DIR = PROJECT_ROOT / "systems" / "WDIRS"

sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from config import QUERY_DIR, RESULTS_DIR  # type: ignore  # WDIRS config
from token_counter import GLOBAL_COUNTER, ensure_precise_tokenizer_ready

from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.metrics import MetricCalculator as _MetricCalculator
from evaluation.query_manifest import QueryManifest as _QueryManifest
from evaluation.row_matcher import RowMatcher as _RowMatcher
from evaluation.sql_parser import SqlParser as _SqlParser
from evaluation.utils import (
    add_missing_columns as _add_missing_cols,
    clean_string_columns as _clean_string_cols,
    drop_unnamed_columns as _drop_unnamed,
    normalize_file_name_columns as _norm_file_cols,
    normalize_types as _norm_types,
    standardize_column_name as _std_col,
)

DATASET = "Player"
DATASET_QUERY = "Player"
TREND_SQL_FILE = SCRIPT_DIR / "query" / "player" / "trend_queries_sf_agg.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_uqe"

IDENTITY_COLUMNS: Dict[str, str] = {
    "player": "name",
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
    error: Optional[str] = None


class TokenTracker:
    """Tracks UQE LLM token usage via monkey-patched chat_stream."""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def snapshot(self) -> Tuple[int, int]:
        return self.prompt_tokens, self.completion_tokens

    def delta(self, before: Tuple[int, int]) -> Tuple[int, int]:
        return self.prompt_tokens - before[0], self.completion_tokens - before[1]

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += max(0, int(prompt_tokens))
        self.completion_tokens += max(0, int(completion_tokens))


class _PreflightPatcher:
    """
    Monkey-patches UQE hot paths so we can quickly execute all queries and catch
    structural/operator errors without expensive LLM calls.
    """

    def __init__(self) -> None:
        self._saved: Dict[str, Any] = {}

    def __enter__(self):
        import oper as uqe_oper
        import expression as uqe_expr

        self._saved["oper.llm_extractor"] = uqe_oper.llm_extractor
        self._saved["oper.llm_filter"] = getattr(uqe_oper, "llm_filter", None)
        self._saved["expr.sample_merged_rows"] = uqe_expr.sample_merged_rows

        def _fake_llm_extractor(df, col, attrs, sys_prompt, data_schema, df_id=None, model=None, retries=1):
            out = pd.DataFrame(index=range(len(df)))
            for attr in attrs:
                out[f"{col}.{attr}"] = pd.NA
            return out

        def _fake_llm_filter(*args, **kwargs):
            return 0

        def _fake_sample_merged_rows(df, col_to_add, data_schema):
            # Keep all rows so predicate wiring is exercised.
            return list(range(len(df)))

        uqe_oper.llm_extractor = _fake_llm_extractor
        if self._saved["oper.llm_filter"] is not None:
            uqe_oper.llm_filter = _fake_llm_filter
        uqe_expr.sample_merged_rows = _fake_sample_merged_rows
        return self

    def __exit__(self, exc_type, exc, tb):
        import oper as uqe_oper
        import expression as uqe_expr

        uqe_oper.llm_extractor = self._saved["oper.llm_extractor"]
        if self._saved["oper.llm_filter"] is not None:
            uqe_oper.llm_filter = self._saved["oper.llm_filter"]
        uqe_expr.sample_merged_rows = self._saved["expr.sample_merged_rows"]
        return False


def _approx_tokens(text: Optional[str]) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def _approx_tokens_messages(messages: list) -> Tuple[int, int]:
    """Estimate prompt tokens from a list of chat messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _approx_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += _approx_tokens(part.get("text", ""))
    return total


def patch_uqe_for_token_tracking(token_tracker: TokenTracker) -> None:
    """
    Monkey-patch UQE's f.chat_stream to count every LLM call.
    """
    import f as uqe_f

    original_chat_stream = uqe_f.chat_stream

    def wrapped_chat_stream(messages, model=None, temperature=0.1, max_tokens=100, attempts=5):
        if model is None:
            model = uqe_f.MODEL
        result = original_chat_stream(
            messages, model=model, temperature=temperature,
            max_tokens=max_tokens, attempts=attempts,
        )
        p_tok = _approx_tokens_messages(messages)
        c_tok = _approx_tokens(result)
        token_tracker.add(p_tok, c_tok)
        GLOBAL_COUNTER.record(
            input_tokens=p_tok, output_tokens=c_tok, operation="uqe",
        )
        return result

    uqe_f.chat_stream = wrapped_chat_stream


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


def parse_trend_queries(sql_file: Path) -> List[Tuple[str, str]]:
    """Parse Q1..Q10 from a comment-delimited SQL file."""
    if not sql_file.exists():
        raise FileNotFoundError(f"Trend SQL file not found: {sql_file}")
    lines = sql_file.read_text().splitlines()
    queries: List[Tuple[str, str]] = []

    i = 0
    while i < len(lines):
        m = re.match(r"\s*--\s*Q(\d+)\s*:", lines[i], flags=re.IGNORECASE)
        if not m:
            i += 1
            continue
        qid = f"Q{int(m.group(1))}"
        i += 1
        sql_lines: List[str] = []
        while i < len(lines):
            raw = lines[i]
            s = raw.strip()
            if re.match(r"\s*--\s*Q\d+\s*:", raw, flags=re.IGNORECASE):
                break
            if s.startswith("--") or s == "":
                i += 1
                continue
            sql_lines.append(raw)
            if ";" in raw:
                i += 1
                break
            i += 1

        sql = "\n".join(sql_lines).strip().rstrip(";").strip()
        if sql:
            queries.append((qid, sql))

    queries.sort(key=lambda x: int(x[0][1:]))
    expected = [f"Q{i}" for i in range(1, 11)]
    got = [qid for qid, _ in queries]
    if got != expected:
        raise RuntimeError(
            f"Expected exactly Q1..Q10 in order. Got: {got}"
        )
    return queries


def _strip_description_prefix(df: pd.DataFrame) -> pd.DataFrame:
    """
    UQE returns columns like 'description.name', 'description.age'.
    Strip the 'description.' prefix so they match ground truth column names.
    """
    rename_map = {}
    for col in df.columns:
        if col.startswith("description."):
            new_name = col[len("description."):]
            rename_map[col] = new_name
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def _build_pred_df(
    rows: List[Dict[str, Any]],
    expected_columns: List[str],
    attributes: Dict[str, Any],
) -> pd.DataFrame:
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=expected_columns)
    df = _drop_unnamed(df)
    df = df.rename(columns={c: _std_col(c) for c in df.columns})
    df = _norm_file_cols(df)
    df = _add_missing_cols(df, expected_columns)
    df = _clean_string_cols(df)
    df = _norm_types(df, attributes)
    return df


def _looks_like_aggregate_column(col_name: str) -> bool:
    c = str(col_name).strip().lower()
    # Covers names like: count(*), count_star(), sum(age), avg(age), ...
    return (
        c.startswith("count(")
        or c.startswith("sum(")
        or c.startswith("avg(")
        or c.startswith("min(")
        or c.startswith("max(")
        or c.startswith("count_")
        or c.endswith("_star()")
    )


def _resolve_primary_keys(
    primary_keys: List[str],
    gold_df: pd.DataFrame,
    pred_df: pd.DataFrame,
) -> List[str]:
    gold_cols = {str(c) for c in gold_df.columns}
    pred_cols = {str(c) for c in pred_df.columns}

    resolved: List[str] = []
    for key in primary_keys:
        candidates = [
            key,
            key.split(".")[-1],
            _std_col(key),
            _std_col(key.split(".")[-1]),
        ]
        chosen = next((c for c in candidates if c in gold_cols and c in pred_cols), None)
        if chosen and chosen not in resolved:
            resolved.append(chosen)

    if not resolved:
        raise RuntimeError(
            f"Could not resolve primary keys {primary_keys} "
            f"against gold columns={list(gold_df.columns)} "
            f"and pred columns={list(pred_df.columns)}"
        )
    return resolved


def evaluate_with_official_framework(
    sql: str,
    result_rows: List[Dict[str, Any]],
    *,
    gt_runner: _GtRunner,
    sql_parser: _SqlParser,
    row_matcher: _RowMatcher,
    settings: _EvalSettings,
    attributes: Dict[str, Any],
    identity_col: Optional[str],
    output_dir: Path,
) -> Dict[str, Any]:
    parsed = sql_parser.parse(sql)
    is_agg = parsed.query_type == "aggregation"
    if not identity_col:
        raise RuntimeError("Strict mode requires explicit identity_col.")
    entity = identity_col

    if is_agg:
        gt_sql = sql
        primary_keys = parsed.primary_keys
    else:
        primary_keys = [entity]
        import sqlglot
        import sqlglot.expressions as _sqlglot_exp

        parsed_ast = sqlglot.parse_one(sql)
        if not parsed_ast.find(_sqlglot_exp.Star) and not parsed_ast.args.get("group"):
            existing = {
                c.name.lower()
                for c in parsed_ast.find_all(_sqlglot_exp.Column)
                if isinstance(c.parent, _sqlglot_exp.Select)
            }
            if entity.lower() not in existing:
                parsed_ast = parsed_ast.select(_sqlglot_exp.column(entity))
            gt_sql = parsed_ast.sql(dialect="duckdb")
        else:
            gt_sql = sql

    gold_df = gt_runner.run(gt_sql)
    if not is_agg and entity not in gold_df.columns:
        raise RuntimeError(
            f"Identity column '{entity}' missing from GT result columns {list(gold_df.columns)}"
        )

    manifest = _QueryManifest(gt_sql, sql_parser.parse(gt_sql), attributes)
    pred_df = _build_pred_df(
        result_rows,
        expected_columns=list(gold_df.columns),
        attributes=attributes,
    )

    if is_agg:
        # For aggregation queries, SQL parser may provide synthetic keys (e.g., id)
        # that do not exist in aggregate outputs. Use non-aggregate shared columns
        # (typically GROUP BY dimensions) as row keys. If this is a global
        # aggregation (e.g., COUNT(*)), align the single-row outputs with a
        # constant synthetic key.
        shared_non_agg_keys = [
            c for c in gold_df.columns
            if c in pred_df.columns and not _looks_like_aggregate_column(c)
        ]
        if shared_non_agg_keys:
            primary_keys = shared_non_agg_keys
        else:
            gold_df = gold_df.copy()
            pred_df = pred_df.copy()
            gold_df["__agg_key"] = "__all__"
            pred_df["__agg_key"] = "__all__"
            primary_keys = ["__agg_key"]
    else:
        primary_keys = _resolve_primary_keys(primary_keys, gold_df, pred_df)

    match_result = row_matcher.match(
        gold_df=gold_df,
        pred_df=pred_df,
        primary_keys=primary_keys,
        attr_descriptions=attributes,
        query_type=parsed.query_type,
    )

    calc = _MetricCalculator(manifest, settings)
    metrics = calc.compute(match_result)
    macro_f1 = metrics.get("macro_f1", 0.0)
    macro_precision = metrics.get("macro_precision", 0.0)
    macro_recall = metrics.get("macro_recall", 0.0)
    if not math.isfinite(macro_f1) or not math.isfinite(macro_precision) or not math.isfinite(macro_recall):
        raise RuntimeError(
            f"Non-finite metrics produced: "
            f"F1={macro_f1}, P={macro_precision}, R={macro_recall}"
        )

    from evaluation.result_writer import ResultWriter as _ResultWriter
    writer = _ResultWriter(output_dir=output_dir)
    writer.write(gold_df, match_result.gold_aligned, match_result.pred_aligned, metrics)

    return {
        "macro_f1": macro_f1,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "is_agg": is_agg,
        "gt_result_count": len(gold_df),
        "matched_rows": match_result.matched_rows,
    }


def _execute_uqe_query(query_text: str) -> pd.DataFrame:
    """Run a single query through UQE's parse → plan → optimize → execute pipeline."""
    from parse import parser
    from plan import planner
    from optimize import optimizer
    from execute import executor
    from schema.nba import NBAData

    source_data = NBAData("nba")
    parsed_query = parser(query_text)
    plan, invalid = planner(parsed_query, source_data)
    if invalid:
        raise RuntimeError(f"UQE planner rejected query as invalid: {query_text}")
    assert plan is not None
    optimized_plan = optimizer(plan)
    result_df = executor(optimized_plan)

    if result_df is None:
        return pd.DataFrame()

    result_df = _strip_description_prefix(result_df)

    if "id" in result_df.columns:
        result_df = result_df.drop(columns=["id"])

    return result_df


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


def run_trend_queries_uqe(run_dir: Path) -> List[TrendQueryMetrics]:
    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    plots_dir = run_dir / "plots"

    run_dir.mkdir(parents=True, exist_ok=True)
    query_results_dir.mkdir(parents=True, exist_ok=True)
    query_tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    token_tracker = TokenTracker()
    patch_uqe_for_token_tracking(token_tracker)

    eval_attributes: Dict[str, Any] = (
        _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    )
    if not eval_attributes:
        raise RuntimeError(f"Missing or empty attributes file: {ATTRIBUTES_FILE}")
    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=eval_attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")
    if len(trend_queries) != 10:
        raise RuntimeError(f"Strict mode expects exactly 10 queries, got {len(trend_queries)}")

    logger.info(f"Loaded {len(trend_queries)} trend queries from {TREND_SQL_FILE}")
    for qid, qtxt in trend_queries:
        logger.info(f"  {qid}: {qtxt[:80]}...")

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info(f"Executing {query_id} with UQE")
        logger.info(f"SQL: {query_text}")
        before = token_tracker.snapshot()
        t0 = time.time()

        result_df = _execute_uqe_query(query_text)
        rows = result_df.to_dict("records")
        latency = time.time() - t0
        d_prompt, d_completion = token_tracker.delta(before)
        d_total = d_prompt + d_completion

        out_csv = query_tables_dir / f"{query_id}.csv"
        out_json = query_tables_dir / f"{query_id}.json"
        _save_rows_csv(rows, out_csv)
        out_json.write_text(json.dumps(rows, indent=2, default=str))

        eval_out = evaluate_with_official_framework(
            query_text,
            rows,
            gt_runner=eval_gt_runner,
            sql_parser=eval_sql_parser,
            row_matcher=eval_row_matcher,
            settings=eval_settings,
            attributes=eval_attributes,
            identity_col="name",
            output_dir=query_results_dir / query_id,
        )

        item = TrendQueryMetrics(
            query_id=query_id,
            query_text=query_text,
            success=True,
            delta_type="UQE",
            latency_s=latency,
            result_rows=len(rows),
            prompt_tokens=d_prompt,
            completion_tokens=d_completion,
            total_tokens=d_total,
            macro_f1=eval_out["macro_f1"],
            macro_precision=eval_out["macro_precision"],
            macro_recall=eval_out["macro_recall"],
            gt_result_count=eval_out["gt_result_count"],
            matched_rows=eval_out["matched_rows"],
            is_agg=eval_out["is_agg"],
        )
        metrics.append(item)

        acc_path = query_results_dir / query_id / "acc.json"
        acc_path.parent.mkdir(parents=True, exist_ok=True)
        acc_data = {
            "query_id": query_id,
            "latency_s": round(latency, 4),
            "prompt_tokens": d_prompt,
            "completion_tokens": d_completion,
            "total_tokens": d_total,
            "result_rows": len(rows),
            "success": True,
            "macro_f1": eval_out["macro_f1"],
            "macro_precision": eval_out["macro_precision"],
            "macro_recall": eval_out["macro_recall"],
        }
        acc_path.write_text(json.dumps(acc_data, indent=2))

        logger.info(
            f"{query_id}: rows={item.result_rows} latency={item.latency_s:.3f}s "
            f"tokens={item.total_tokens} F1={item.macro_f1:.3f}"
        )

    return metrics


def run_preflight_checks() -> int:
    """
    Fast structural preflight:
    - parses all Q1..Q10
    - builds plans
    - executes with monkey-patched LLM/sampling stubs
    This catches operator wiring crashes quickly before long full runs.
    """
    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    logger.info(f"[Preflight] Checking {len(trend_queries)} queries")
    with _PreflightPatcher():
        for query_id, query_text in trend_queries:
            logger.info(f"[Preflight] {query_id}: {query_text}")
            _ = _execute_uqe_query(query_text)
    logger.info("[Preflight] All queries passed structural execution checks.")
    return 0


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
        "Player Query-Awareness Trend with UQE (Q1..Q10)",
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

    p = [m.macro_precision for m in ordered]
    r = [m.macro_recall for m in ordered]
    fig2, ax2 = plt.subplots(figsize=(12, 5))
    ax2.plot(x, p, marker="o", label="Precision")
    ax2.plot(x, r, marker="o", label="Recall")
    ax2.plot(x, f1, marker="o", label="F1")
    ax2.set_xticks(x)
    ax2.set_xticklabels(x_labels)
    ax2.set_ylim(0.0, 1.0)
    ax2.set_title("Macro Precision/Recall/F1 by Query")
    ax2.set_ylabel("score")
    ax2.grid(alpha=0.3)
    ax2.legend()
    plt.tight_layout()
    prf_plot = plots_dir / "query_awareness_trend_prf.png"
    plt.savefig(prf_plot, dpi=300, bbox_inches="tight")
    plt.close(fig2)
    logger.info(f"Saved trend PRF plot: {prf_plot}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run UQE Player trend benchmark")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Run fast structural checks without full LLM execution.",
    )
    args = parser.parse_args()

    ensure_precise_tokenizer_ready()

    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    run_tag = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_BASE_DIR / f"run_{run_tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(run_dir / "query_awareness_trend_uqe.log")

    logger.info("Starting Player query-awareness trend test (UQE)...")
    logger.info(f"Run directory: {run_dir}")
    logger.info(f"Trend query source: {TREND_SQL_FILE}")
    logger.info(f"Identity columns (for eval): {IDENTITY_COLUMNS}")

    import config_uqe
    logger.info(f"UQE model: {config_uqe.MODEL} @ {config_uqe.BASE_URL}")
    logger.info(f"UQE batch size: {config_uqe.BATCH_SIZE}")
    logger.info(f"UQE optimizations: {config_uqe.ENABLE_OPTIMIZATIONS}")

    try:
        if args.preflight:
            return run_preflight_checks()
        metrics = run_trend_queries_uqe(run_dir)
        save_metrics(metrics, run_dir)
        plot_metrics(metrics, run_dir)

        success_count = sum(1 for m in metrics if m.success)
        avg_f1 = sum(m.macro_f1 for m in metrics) / len(metrics) if metrics else 0.0
        if not math.isfinite(avg_f1):
            avg_f1 = 0.0
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
        logger.exception(f"UQE trend test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

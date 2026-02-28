"""
Run Q1..Q10 query-awareness trend benchmarking with DocETL on Player.

This mirrors systems/WDIRS/test_player_query_awareness_trend.py, but executes
queries through DocETL operators (equijoin/filter) driven by natural-language
instructions derived from SQL.
"""

import argparse
import csv
import json
import logging
import math
import shutil
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import sqlglot
import sqlglot.expressions as exp

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False


logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
WDIRS_DIR = PROJECT_ROOT / "systems" / "WDIRS"
DOCETL_MAIN_DIR = PROJECT_ROOT / "systems" / "docetl-main"

sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(DOCETL_MAIN_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from config import QUERY_DIR, RESULTS_DIR  # type: ignore
import test_player_query_awareness_trend as baseline  # type: ignore
import docetl  # noqa: F401  # Registers pandas semantic accessor.
from docetl.operations.utils.api import APIWrapper
from docetl.operations.utils.llm import approx_count_tokens

from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.row_matcher import RowMatcher as _RowMatcher
from evaluation.sql_parser import SqlParser as _SqlParser


DATASET = "Player"
DATASET_QUERY = "Player"
TREND_SQL_FILE = QUERY_DIR / DATASET_QUERY / "query_aware_trend_queries.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_docetl"
RUN_DIR = RESULTS_BASE_DIR / "run"
QUERY_RESULTS_DIR = RUN_DIR / "query_results"
QUERY_TABLES_DIR = RUN_DIR / "query_tables"
PLOTS_DIR = RUN_DIR / "plots"

OLLAMA_BASE_URL = "http://localhost:11434"
DOCETL_MODEL = "ollama/qwen2.5:7b-instruct"
DOCETL_THREADS = 4


@dataclass
class TrendQueryMetrics:
    query_id: str
    query_text: str
    nl_query: str
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
    """Tracks DocETL/LiteLLM token usage for this process."""

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


def _extract_usage_tokens(response_obj: Any) -> Tuple[int, int]:
    usage = getattr(response_obj, "usage", None)
    if usage is None:
        return 0, 0
    if isinstance(usage, dict):
        return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
    return int(getattr(usage, "prompt_tokens", 0)), int(
        getattr(usage, "completion_tokens", 0)
    )


def patch_docetl_for_token_tracking(token_tracker: TokenTracker) -> None:
    """Monkey-patch DocETL API wrapper to collect token counts per LLM call."""
    original_call_llm = APIWrapper.call_llm

    def wrapped_call_llm(self, *args, **kwargs):  # noqa: ANN001
        result = original_call_llm(self, *args, **kwargs)
        prompt_toks = 0
        completion_toks = 0
        response_obj = getattr(result, "response", None)
        if response_obj is not None:
            prompt_toks, completion_toks = _extract_usage_tokens(response_obj)

        # Fallback estimation when provider usage is absent.
        if prompt_toks == 0 and completion_toks == 0:
            messages = kwargs.get("messages")
            if messages is None and len(args) >= 3:
                messages = args[2]
            if isinstance(messages, list):
                prompt_toks = approx_count_tokens(messages)

            try:
                content = response_obj.choices[0].message.content if response_obj else ""
                completion_toks = max(0, int(len(str(content)) / 4))
            except Exception:
                completion_toks = 0

        token_tracker.add(prompt_toks, completion_toks)
        return result

    APIWrapper.call_llm = wrapped_call_llm


def _load_tables(conn: sqlite3.Connection) -> Dict[str, pd.DataFrame]:
    return {
        "player": pd.read_sql_query("SELECT * FROM player", conn),
        "team": pd.read_sql_query("SELECT * FROM team", conn),
        "city": pd.read_sql_query("SELECT * FROM city", conn),
    }


def _col_name(col_expr: exp.Column) -> str:
    return col_expr.name


def _describe_sql_nl(query_id: str, sql: str) -> str:
    parsed = sqlglot.parse_one(sql, read="sqlite")
    selected = []
    for sel in parsed.expressions:
        if isinstance(sel, exp.Column):
            selected.append(f"{sel.table}.{sel.name}" if sel.table else sel.name)
        else:
            selected.append(sel.sql(dialect="sqlite"))

    from_table = parsed.args["from"].this.name
    joins = []
    for j in parsed.find_all(exp.Join):
        j_table = j.this.name
        on_expr = j.args.get("on")
        joins.append(f"join {j_table} on {on_expr.sql(dialect='sqlite') if on_expr else 'condition'}")

    where_expr = parsed.args.get("where")
    where_txt = where_expr.this.sql(dialect="sqlite") if where_expr else "no filter"
    return (
        f"{query_id}: Select {', '.join(selected)} from {from_table}, "
        f"{'; '.join(joins) if joins else 'no joins'}, and apply filter: {where_txt}."
    )


def _resolve_join_keys(on_expr: exp.Expression, right_table: str) -> Tuple[str, str]:
    if not isinstance(on_expr, exp.EQ):
        raise ValueError(f"Unsupported join predicate: {on_expr.sql()}")
    if not isinstance(on_expr.this, exp.Column) or not isinstance(on_expr.expression, exp.Column):
        raise ValueError(f"Unsupported join operands: {on_expr.sql()}")

    c1 = on_expr.this
    c2 = on_expr.expression
    if c1.table and c1.table.lower() == right_table.lower():
        return _col_name(c2), _col_name(c1)
    if c2.table and c2.table.lower() == right_table.lower():
        return _col_name(c1), _col_name(c2)
    # Fallback to left/right expression order.
    return _col_name(c1), _col_name(c2)


def _apply_where_filter(df: pd.DataFrame, where_expr: Optional[exp.Expression]) -> pd.DataFrame:
    if where_expr is None:
        return df
    if not isinstance(where_expr, (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.EQ)):
        raise ValueError(f"Unsupported WHERE predicate: {where_expr.sql()}")
    if not isinstance(where_expr.this, exp.Column):
        raise ValueError(f"Unsupported WHERE left operand: {where_expr.sql()}")
    col = where_expr.this.name
    rhs = where_expr.expression
    if not isinstance(rhs, exp.Literal):
        raise ValueError(f"Unsupported WHERE right operand: {where_expr.sql()}")

    rhs_txt = rhs.sql(dialect="sqlite")
    nl_operator = {
        exp.GT: "greater than",
        exp.GTE: "greater than or equal to",
        exp.LT: "less than",
        exp.LTE: "less than or equal to",
        exp.EQ: "exactly equal to",
    }[type(where_expr)]
    prompt = (
        f"Given value {{input.{col}}}, return keep=true iff it is {nl_operator} {rhs_txt}. "
        "Interpret numeric values numerically."
    )
    return df.semantic.filter(
        prompt=prompt,
        output={"schema": {"keep": "bool"}},
        model=DOCETL_MODEL,
        timeout=180,
        max_retries_per_timeout=1,
    )


def execute_sql_via_docetl_nl(sql: str, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    parsed = sqlglot.parse_one(sql, read="sqlite")
    table_map = _load_tables(conn)
    from_table = parsed.args["from"].this.name.lower()
    if from_table not in table_map:
        raise ValueError(f"Unknown base table: {from_table}")

    current = table_map[from_table].copy()
    current.semantic.set_config(
        default_model=DOCETL_MODEL,
        default_lm_api_base=OLLAMA_BASE_URL,
        default_embedding_api_base=OLLAMA_BASE_URL,
        max_threads=DOCETL_THREADS,
    )

    for join_expr in parsed.find_all(exp.Join):
        right_table = join_expr.this.name.lower()
        if right_table not in table_map:
            raise ValueError(f"Unknown join table: {right_table}")
        right_df = table_map[right_table].copy()
        on_expr = join_expr.args.get("on")
        if on_expr is None:
            raise ValueError("JOIN without ON is unsupported in this benchmark")

        left_key, right_key = _resolve_join_keys(on_expr, right_table)
        join_prompt = (
            "You are executing a database equijoin. Return true iff these keys match.\n"
            f"Left key ({left_key}): {{{{ left.{left_key} }}}}\n"
            f"Right key ({right_key}): {{{{ right.{right_key} }}}}\n"
            "Match rule: exact equality after trimming whitespace and lowercasing."
        )
        blocking_rule = (
            f"str(left.get('{left_key}', '')).strip().lower() == "
            f"str(right.get('{right_key}', '')).strip().lower()"
        )

        current = current.semantic.merge(
            right_df,
            comparison_prompt=join_prompt,
            fuzzy=False,
            model=DOCETL_MODEL,
            comparison_model=DOCETL_MODEL,
            blocking_conditions=[blocking_rule],
            timeout=180,
            max_retries_per_timeout=1,
        )

    where_node = parsed.args.get("where")
    current = _apply_where_filter(current, where_node.this if where_node else None)

    selected_cols: List[str] = []
    for sel in parsed.expressions:
        if isinstance(sel, exp.Column):
            selected_cols.append(sel.name)
        else:
            raise ValueError(f"Only column projections are supported, got: {sel.sql()}")

    missing_cols = [c for c in selected_cols if c not in current.columns]
    if missing_cols:
        raise ValueError(f"Projected columns missing after execution: {missing_cols}")

    out_df = current[selected_cols].copy()
    return out_df.to_dict("records")


def _save_rows_csv(rows: List[Dict[str, Any]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with out_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["_empty"])
        return
    cols: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in cols:
                cols.append(key)
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def run_trend_queries_docetl(snapshot_db: Path, identity_file: Optional[Path]) -> List[TrendQueryMetrics]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    QUERY_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    QUERY_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    working_db = RUN_DIR / "player_trend_working_docetl.db"
    shutil.copy2(snapshot_db, working_db)
    logger.info(f"Working DB copied from snapshot: {working_db}")

    identity_columns: Dict[str, str] = {}
    if identity_file and identity_file.exists():
        identity_columns = json.loads(identity_file.read_text())
        logger.info(f"Loaded identity columns: {identity_columns}")
    else:
        logger.warning("No identity columns file found; fallback identity rules will be used.")

    token_tracker = TokenTracker()
    patch_docetl_for_token_tracking(token_tracker)

    eval_attributes: Dict[str, Any] = (
        _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    )
    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=eval_attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    trend_queries = baseline.parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")

    metrics: List[TrendQueryMetrics] = []
    with sqlite3.connect(working_db) as conn:
        for query_id, query_text in trend_queries:
            logger.info("=" * 70)
            logger.info(f"Executing {query_id} with DocETL")
            nl_query = _describe_sql_nl(query_id, query_text)
            logger.info(f"[NL] {nl_query}")
            before = token_tracker.snapshot()
            t0 = time.time()

            try:
                rows = execute_sql_via_docetl_nl(query_text, conn)
                latency = time.time() - t0
                d_prompt, d_completion = token_tracker.delta(before)
                d_total = d_prompt + d_completion

                out_csv = QUERY_TABLES_DIR / f"{query_id}.csv"
                out_json = QUERY_TABLES_DIR / f"{query_id}.json"
                _save_rows_csv(rows, out_csv)
                out_json.write_text(json.dumps(rows, indent=2, default=str))

                eval_out = baseline.evaluate_with_official_framework(
                    query_text,
                    rows,
                    gt_runner=eval_gt_runner,
                    sql_parser=eval_sql_parser,
                    row_matcher=eval_row_matcher,
                    settings=eval_settings,
                    attributes=eval_attributes,
                    identity_col=baseline._infer_identity_col_for_query(
                        query_text, identity_columns
                    ),
                    phase2_db=working_db,
                    output_dir=QUERY_RESULTS_DIR / query_id,
                )

                item = TrendQueryMetrics(
                    query_id=query_id,
                    query_text=query_text,
                    nl_query=nl_query,
                    success=True,
                    delta_type="DOCETL_NL",
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
                logger.info(
                    f"{query_id}: rows={item.result_rows} latency={item.latency_s:.3f}s "
                    f"tokens={item.total_tokens} F1={item.macro_f1:.3f}"
                )
            except Exception as exc:
                latency = time.time() - t0
                d_prompt, d_completion = token_tracker.delta(before)
                metrics.append(
                    TrendQueryMetrics(
                        query_id=query_id,
                        query_text=query_text,
                        nl_query=nl_query,
                        success=False,
                        delta_type="ERROR",
                        latency_s=latency,
                        result_rows=0,
                        prompt_tokens=d_prompt,
                        completion_tokens=d_completion,
                        total_tokens=d_prompt + d_completion,
                        macro_f1=0.0,
                        macro_precision=0.0,
                        macro_recall=0.0,
                        gt_result_count=0,
                        matched_rows=0,
                        is_agg=False,
                        error=str(exc),
                    )
                )
                logger.exception(f"{query_id} failed: {exc}")

    return metrics


def save_metrics(metrics: List[TrendQueryMetrics]) -> None:
    rows = [asdict(m) for m in metrics]
    out_json = RUN_DIR / "trend_metrics.json"
    out_csv = RUN_DIR / "trend_metrics.csv"
    out_json.write_text(json.dumps(rows, indent=2))
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    logger.info(f"Saved metrics JSON: {out_json}")
    logger.info(f"Saved metrics CSV:  {out_csv}")


def plot_metrics(metrics: List[TrendQueryMetrics]) -> None:
    if not MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available - skipping plot generation")
        return
    if not metrics:
        logger.warning("No metrics to plot.")
        return

    ordered = sorted(metrics, key=lambda m: int(m.query_id[1:]))
    x_labels = [m.query_id for m in ordered]
    x = list(range(len(x_labels)))

    result_rows = [m.result_rows for m in ordered]
    token_cost = [m.total_tokens for m in ordered]
    latency = [m.latency_s for m in ordered]
    f1 = [m.macro_f1 for m in ordered]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "Player Query-Awareness Trend with DocETL (Q1..Q10)",
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
    summary_plot = PLOTS_DIR / "query_awareness_trend_summary.png"
    plt.savefig(summary_plot, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved trend summary plot: {summary_plot}")


def main() -> int:
    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    setup_logging(RESULTS_BASE_DIR / "query_awareness_trend_docetl.log")
    ap = argparse.ArgumentParser(
        description="Run Player query-awareness trend test using DocETL"
    )
    ap.add_argument(
        "--refresh-snapshot",
        action="store_true",
        help="Recreate snapshot DB from preferred source before running",
    )
    args = ap.parse_args()

    logger.info("Starting Player query-awareness trend test (DocETL)...")
    logger.info(f"Trend query source: {TREND_SQL_FILE}")
    logger.info(f"Model: {DOCETL_MODEL} @ {OLLAMA_BASE_URL}")

    try:
        snapshot_db, identity_file = baseline.ensure_snapshot_artifacts(
            refresh_snapshot=args.refresh_snapshot
        )
        metrics = run_trend_queries_docetl(snapshot_db, identity_file)
        save_metrics(metrics)
        plot_metrics(metrics)

        success_count = sum(1 for m in metrics if m.success)
        avg_f1 = sum(m.macro_f1 for m in metrics) / len(metrics) if metrics else 0.0
        if not math.isfinite(avg_f1):
            avg_f1 = 0.0
        logger.info("=" * 80)
        logger.info(
            f"Completed: {success_count}/{len(metrics)} queries succeeded, "
            f"avg macro F1={avg_f1:.3f}"
        )
        logger.info(f"Outputs under: {RUN_DIR}")
        logger.info("=" * 80)
        return 0
    except Exception as exc:
        logger.exception(f"DocETL trend test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""
Run query-awareness trend benchmarking with DocETL on Player.

Query set matches WDIRS/ReDD (category SQL folders, filtered by ReDD
NL_QUERY_SPECS).

DocETL's role follows the paper (Shankar et al.): declarative **pipelines** whose
operators include **map** for semantic projection (§2.2). For each base table
referenced by the benchmark SQL we run a dedicated `docetl.api.Pipeline` with a
memory `Dataset` and one `MapOp`. Joins, filters, and aggregations in the SQL are
relational closure: executed with SQLite on the extracted tables (deterministic),
matching the paper's split between LLM operators and auxiliary processing.
"""

import csv
import importlib.util
import json
import logging
import os
import math
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import sqlglot
from sqlglot import exp

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
sys.path.insert(0, str(SCRIPT_DIR))

from config import RESULTS_DIR  # type: ignore
from docetl.api import Dataset, MapOp, Pipeline, PipelineOutput, PipelineStep
from docetl.operations.utils.api import APIWrapper
from token_counter import GLOBAL_COUNTER, ensure_precise_tokenizer_ready

from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.row_matcher import RowMatcher as _RowMatcher
from evaluation.sql_parser import SqlParser as _SqlParser

# Import only utility functions from WDIRS trend script (no system-level dependencies)
from test_player_query_awareness_trend import (  # type: ignore
    evaluate_with_official_framework,
    load_redd_enabled_query_ids,
    parse_all_category_queries,
    _infer_identity_col_for_query,
)


DATASET_QUERY = "Player"
REDD_TREND_FILE = PROJECT_ROOT / "systems" / "ReDD" / "test_player_query_awareness_trend_redd.py"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"
SOURCE_DATA_PLAYER_DIR = PROJECT_ROOT / "source_data" / "Player"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_docetl"

OLLAMA_BASE_URL = "http://localhost:11434"
DOCETL_MODEL = "ollama/qwen2.5:7b-instruct"
DOCETL_THREADS = 4
DOCETL_MAP_TIMEOUT = 420
DOCETL_MAX_RETRIES_PER_TIMEOUT = 2

NUMERIC_FIELDS = {
    "age",
    "draft_pick",
    "draft_year",
    "founded_year",
    "population",
    "gdp",
    "area",
    "mvp_awards",
    "olympic_gold_medals",
    "fiba_world_cup",
    "nba_championships",
    "championship",
    "own_year",
}

# Column dictionary for resolving unqualified SQL columns (e.g., SELECT position FROM player).
TABLE_COLUMNS: Dict[str, set[str]] = {
    "player": {
        "name",
        "birth_date",
        "nationality",
        "age",
        "team",
        "position",
        "draft_pick",
        "draft_year",
        "college",
        "nba_championships",
        "mvp_awards",
        "olympic_gold_medals",
        "fiba_world_cup",
    },
    "team": {
        "team_name",
        "founded_year",
        "location",
        "ownership",
        "championship",
    },
    "city": {
        "city_name",
        "state_name",
        "population",
        "area",
        "gdp",
    },
    "owner": {
        "name",
        "age",
        "nationality",
        "nba_team",
        "own_year",
    },
}

# Identity columns for evaluation (table -> identity_column_name)
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


def _extract_usage_tokens_strict(response_obj: Any) -> Optional[Tuple[int, int]]:
    """Return (prompt, completion) only when provider usage is explicitly available."""
    usage = getattr(response_obj, "usage", None)
    if usage is None:
        return None
    if isinstance(usage, dict):
        if "prompt_tokens" not in usage or "completion_tokens" not in usage:
            return None
        if usage["prompt_tokens"] is None or usage["completion_tokens"] is None:
            return None
        return int(usage["prompt_tokens"]), int(usage["completion_tokens"])
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if prompt is None or completion is None:
        return None
    return int(prompt), int(completion)


def patch_docetl_for_token_tracking(token_tracker: TokenTracker) -> None:
    """
    Monkey-patch at the lowest DocETL API layer so we count every actual LLM
    completion call (including retries/internal loops), not just top-level
    operation calls.
    """
    original_low_level = APIWrapper._call_llm_with_cache

    def wrapped_low_level(self, *args, **kwargs):  # noqa: ANN001
        response = original_low_level(self, *args, **kwargs)
        usage = _extract_usage_tokens_strict(response)
        if usage is None:
            raise RuntimeError(
                "[DocETL TokenCounter] Precise tokenization required, but provider "
                "usage tokens are missing for a DocETL LLM call."
            )
        prompt_toks, completion_toks = usage
        token_tracker.add(prompt_toks, completion_toks)
        GLOBAL_COUNTER.record(
            input_tokens=prompt_toks,
            output_tokens=completion_toks,
            operation="docetl",
        )
        return response

    APIWrapper._call_llm_with_cache = wrapped_low_level


def _raw_doc_records_for_table(table: str) -> List[Dict[str, Any]]:
    """One JSON object per source document (for DocETL memory datasets)."""
    table_dir = SOURCE_DATA_PLAYER_DIR / table
    if not table_dir.exists():
        raise FileNotFoundError(f"Missing source table directory: {table_dir}")
    rows: List[Dict[str, Any]] = []
    for p in sorted(table_dir.glob("*.txt"), key=lambda x: int(x.stem)):
        txt = p.read_text(errors="ignore")
        rows.append({"doc_id": p.stem, "text": txt})
    if not rows:
        raise RuntimeError(f"No source files found for table: {table}")
    return rows


def _coerce_numeric_columns(table: str, df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    numeric_cols = {
        "player": [
            "age",
            "draft_pick",
            "draft_year",
            "mvp_awards",
            "olympic_gold_medals",
            "fiba_world_cup",
            "nba_championships",
        ],
        "team": ["founded_year", "championship"],
        "city": ["population", "gdp", "area"],
        "owner": ["age", "own_year"],
    }.get(table, [])
    for col in numeric_cols:
        if col in out.columns:
            out[col] = (
                out[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _run_docetl_map_pipeline_for_table(
    query_id: str,
    table: str,
    needed_cols: List[str],
    nl_query: str,
    work_dir: Path,
) -> pd.DataFrame:
    """
    One DocETL Pipeline per (query, table): memory Dataset + MapOp (paper §2.2.1).
    DSLRunner writes JSON output; we load it back into a DataFrame.
    """
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / "pipeline_output.json"
    intermediate_dir = work_dir / "docetl_intermediate"

    output_schema = {
        c: ("number" if c in NUMERIC_FIELDS else "str") for c in needed_cols
    }
    field_list = "\n".join(f"- {c}" for c in needed_cols)
    numeric_guidance = ", ".join([c for c in needed_cols if c in NUMERIC_FIELDS])
    # Jinja: use {{ input.text }} — literal braces via f-string doubling.
    prompt = (
        f"You are building a structured {table} table for this natural-language query:\n"
        f"{nl_query}\n\n"
        f"From this {table} document, extract exactly one record with these fields:\n"
        f"{field_list}\n\n"
        "For numeric fields, return numbers (not quoted strings). "
        f"Numeric fields in this extraction: {numeric_guidance if numeric_guidance else 'none'}.\n"
        "If a numeric field is unknown, return -1. "
        "If a text field is unknown, return empty string. "
        "Keep names concise and normalized.\n\n"
        "Document:\n{{{{ input.text }}}}"
    )

    map_op = MapOp(
        name="extract_fields",
        type="map",
        prompt=prompt,
        output={"schema": output_schema},
        model=DOCETL_MODEL,
        skip_on_error=True,
        timeout=DOCETL_MAP_TIMEOUT,
        max_retries_per_timeout=DOCETL_MAX_RETRIES_PER_TIMEOUT,
    )

    pipeline = Pipeline(
        name="extract",
        datasets={
            "raw": Dataset(
                type="memory",
                path=_raw_doc_records_for_table(table),
                source="local",
            )
        },
        operations=[map_op],
        steps=[
            PipelineStep(
                name="extract_step",
                input="raw",
                operations=["extract_fields"],
            )
        ],
        output=PipelineOutput(
            type="file",
            path=str(out_path),
            intermediate_dir=str(intermediate_dir),
        ),
        default_model=DOCETL_MODEL,
        default_lm_api_base=OLLAMA_BASE_URL,
        default_embedding_api_base=OLLAMA_BASE_URL,
        bypass_cache=True,
    )

    old_cwd = os.getcwd()
    try:
        os.chdir(work_dir)
        pipeline.run(max_threads=DOCETL_THREADS)
    finally:
        os.chdir(old_cwd)

    if not out_path.exists():
        raise RuntimeError(f"DocETL pipeline did not write output: {out_path}")
    records = json.loads(out_path.read_text())
    if not records:
        raise RuntimeError(f"DocETL map produced no rows for table '{table}'")
    mapped = pd.DataFrame(records)
    keep_cols = [c for c in needed_cols if c in mapped.columns]
    if not keep_cols:
        raise RuntimeError(
            f"Extraction produced no expected columns for table '{table}' in query ETL"
        )
    out = mapped[keep_cols].copy()
    return _coerce_numeric_columns(table, out)


def _write_query_tables_sqlite(table_map: Dict[str, pd.DataFrame], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        for table, df in table_map.items():
            df.to_sql(table, conn, if_exists="replace", index=False)


def load_redd_nl_query_specs(redd_path: Path) -> Dict[str, str]:
    """NL strings from ReDD's NL_QUERY_SPECS (same source WDIRS uses for filtering)."""
    module_name = "_docetl_redd_nl_specs"
    if module_name in sys.modules:
        mod = sys.modules[module_name]
    else:
        spec = importlib.util.spec_from_file_location(module_name, redd_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load ReDD module from {redd_path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
    raw = getattr(mod, "NL_QUERY_SPECS", None)
    if not isinstance(raw, dict):
        raise RuntimeError("NL_QUERY_SPECS missing or invalid in ReDD trend module")
    return {str(k): str(v) for k, v in raw.items()}


def columns_per_table_from_sql(sql_text: str) -> Dict[str, List[str]]:
    """
    Collect table -> column names referenced as table.col in the benchmark SQL.
    Drives one DocETL map extraction per (table, column set).
    """
    tree = sqlglot.parse_one(sql_text)

    # Map aliases to base table names; also include identity mapping table->table.
    alias_to_table: Dict[str, str] = {}
    tables_in_query: List[str] = []
    for t in tree.find_all(exp.Table):
        base = (t.name or "").strip().lower()
        if not base:
            continue
        alias_to_table[base] = base
        alias_or_name = (t.alias_or_name or "").strip().lower()
        if alias_or_name:
            alias_to_table[alias_or_name] = base
        if base not in tables_in_query:
            tables_in_query.append(base)

    if not tables_in_query:
        raise ValueError("No base tables found in SQL query")

    by_table: Dict[str, set[str]] = defaultdict(set)
    unqualified_cols: List[str] = []

    for col in tree.find_all(exp.Column):
        cname = (col.name or "").strip().lower()
        if not cname:
            continue
        tname = (col.table or "").strip().lower()
        if tname:
            resolved = alias_to_table.get(tname, tname)
            by_table[resolved].add(cname)
        else:
            unqualified_cols.append(cname)

    # Resolve unqualified columns:
    # - single-table query: assign to that table
    # - multi-table query: assign when exactly one table schema contains it
    for cname in unqualified_cols:
        if len(tables_in_query) == 1:
            by_table[tables_in_query[0]].add(cname)
            continue

        matches = [t for t in tables_in_query if cname in TABLE_COLUMNS.get(t, set())]
        if len(matches) == 1:
            by_table[matches[0]].add(cname)
            continue
        if len(matches) == 0:
            raise ValueError(
                f"Cannot resolve unqualified column '{cname}' in multi-table query "
                f"with tables {tables_in_query}"
            )
        raise ValueError(
            f"Ambiguous unqualified column '{cname}' (matches tables {matches})"
        )

    if not by_table:
        raise ValueError("Could not infer any table columns from SQL query")
    return {t: sorted(cols) for t, cols in by_table.items()}


def _execute_benchmark_sql(
    sql_text: str, table_map: Dict[str, pd.DataFrame]
) -> List[Dict[str, Any]]:
    """Run the benchmark query on extracted relations (deterministic SQLite)."""
    sql = sql_text.strip().rstrip(";").strip()
    parsed = _SqlParser().parse(sql_text)
    out_names = list(parsed.output_columns)
    with sqlite3.connect(":memory:") as conn:
        for table in sorted(table_map.keys()):
            table_map[table].to_sql(table, conn, if_exists="replace", index=False)
        cur = conn.execute(sql)
        tuples = cur.fetchall()
    if not out_names:
        return []
    rows: List[Dict[str, Any]] = []
    for tup in tuples:
        if len(tup) != len(out_names):
            raise ValueError(
                f"SQL result has {len(tup)} columns but parser expects {len(out_names)}"
            )
        rows.append({out_names[i]: tup[i] for i in range(len(out_names))})
    return rows


def execute_query_via_docetl_nl(
    query_id: str,
    sql_text: str,
    nl_query: str,
    pipeline_parent_dir: Path,
) -> Tuple[List[Dict[str, Any]], Dict[str, pd.DataFrame], str]:
    need = columns_per_table_from_sql(sql_text)
    table_map: Dict[str, pd.DataFrame] = {}
    qdir = pipeline_parent_dir / query_id
    for table, cols in need.items():
        logger.info(f"[{query_id}] DocETL Pipeline (map) for '{table}': {cols}")
        table_map[table] = _run_docetl_map_pipeline_for_table(
            query_id, table, cols, nl_query, qdir / f"table_{table}"
        )
    rows = _execute_benchmark_sql(sql_text, table_map)
    return rows, table_map, nl_query


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


def run_trend_queries_docetl(
    run_dir: Path,
) -> List[TrendQueryMetrics]:
    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    plots_dir = run_dir / "plots"
    query_eval_db_dir = run_dir / "query_eval_dbs"
    pipeline_runs_dir = run_dir / "docetl_pipelines"

    run_dir.mkdir(parents=True, exist_ok=True)
    query_results_dir.mkdir(parents=True, exist_ok=True)
    query_tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    query_eval_db_dir.mkdir(parents=True, exist_ok=True)
    pipeline_runs_dir.mkdir(parents=True, exist_ok=True)

    identity_columns = IDENTITY_COLUMNS.copy()
    logger.info(f"Using hardcoded identity columns: {identity_columns}")

    token_tracker = TokenTracker()
    patch_docetl_for_token_tracking(token_tracker)

    eval_attributes: Dict[str, Any] = (
        _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    )
    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=eval_attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    redd_nl_specs = load_redd_nl_query_specs(REDD_TREND_FILE)
    redd_enabled_ids = load_redd_enabled_query_ids()
    trend_queries = [
        (qid, sql)
        for qid, sql in parse_all_category_queries()
        if qid in redd_enabled_ids
    ]
    if not trend_queries:
        raise RuntimeError(
            "No runnable queries after applying ReDD NL_QUERY_SPECS filter. "
            f"ReDD file: {REDD_TREND_FILE}"
        )
    logger.info(
        "Running %d DocETL queries aligned with WDIRS/ReDD (uncommented ReDD IDs)",
        len(trend_queries),
    )

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info(f"Executing {query_id} with DocETL")
        before = token_tracker.snapshot()
        t0 = time.time()

        try:
            nl_query = redd_nl_specs.get(query_id)
            if not nl_query:
                raise ValueError(
                    f"No NL_QUERY_SPECS entry for {query_id} in {REDD_TREND_FILE}"
                )
            rows, query_table_map, nl_query = execute_query_via_docetl_nl(
                query_id, query_text, nl_query, pipeline_runs_dir
            )
            logger.info(f"[NL] {nl_query}")
            latency = time.time() - t0
            d_prompt, d_completion = token_tracker.delta(before)
            d_total = d_prompt + d_completion

            out_csv = query_tables_dir / f"{query_id}.csv"
            out_json = query_tables_dir / f"{query_id}.json"
            _save_rows_csv(rows, out_csv)
            out_json.write_text(json.dumps(rows, indent=2, default=str))

            query_eval_db = query_eval_db_dir / f"{query_id}.db"
            _write_query_tables_sqlite(query_table_map, query_eval_db)

            eval_out = evaluate_with_official_framework(
                query_text,
                rows,
                gt_runner=eval_gt_runner,
                sql_parser=eval_sql_parser,
                row_matcher=eval_row_matcher,
                settings=eval_settings,
                attributes=eval_attributes,
                identity_col=_infer_identity_col_for_query(
                    query_text, identity_columns
                ),
                phase2_db=query_eval_db,
                output_dir=query_results_dir / query_id,
            )

            item = TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                nl_query=nl_query,
                success=True,
                delta_type="DOCETL_MAP_SQLITE",
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

            # Ensure acc.json has token and latency (merge with existing or create).
            acc_path = query_results_dir / query_id / "acc.json"
            acc_path.parent.mkdir(parents=True, exist_ok=True)
            try:
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
                acc_data.setdefault("macro_f1", eval_out.get("macro_f1", 0.0))
                acc_data.setdefault("macro_precision", eval_out.get("macro_precision", 0.0))
                acc_data.setdefault("macro_recall", eval_out.get("macro_recall", 0.0))
                acc_path.write_text(json.dumps(acc_data, indent=2))
            except Exception as acc_err:
                logger.warning(f"Could not write {acc_path} with token/latency: {acc_err}")

            logger.info(
                f"{query_id}: rows={item.result_rows} latency={item.latency_s:.3f}s "
                f"tokens={item.total_tokens} F1={item.macro_f1:.3f}"
            )
        except Exception as exc:
            latency = time.time() - t0
            d_prompt, d_completion = token_tracker.delta(before)
            d_total = d_prompt + d_completion
            nl_query = redd_nl_specs.get(query_id, "")
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
                    total_tokens=d_total,
                    macro_f1=0.0,
                    macro_precision=0.0,
                    macro_recall=0.0,
                    gt_result_count=0,
                    matched_rows=0,
                    is_agg=False,
                    error=str(exc),
                )
            )
            # Write acc.json with token and latency for failed query too.
            acc_path = query_results_dir / query_id / "acc.json"
            acc_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                acc_data = {
                    "query_id": query_id,
                    "latency_s": round(latency, 4),
                    "prompt_tokens": d_prompt,
                    "completion_tokens": d_completion,
                    "total_tokens": d_total,
                    "result_rows": 0,
                    "success": False,
                    "error": str(exc),
                    "macro_f1": 0.0,
                    "macro_precision": 0.0,
                    "macro_recall": 0.0,
                }
                acc_path.write_text(json.dumps(acc_data, indent=2))
            except Exception as acc_err:
                logger.warning(f"Could not write {acc_path}: {acc_err}")
            logger.exception(f"{query_id} failed: {exc}")

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


def _trend_query_sort_key(query_id: str) -> Tuple[int, int]:
    if len(query_id) < 2 or not query_id[1:].isdigit():
        return (99, 0)
    prefix = query_id[0]
    n = int(query_id[1:])
    order = {"S": 0, "F": 1, "A": 2, "J": 3, "M": 4}
    return (order.get(prefix, 99), n)


def plot_metrics(metrics: List[TrendQueryMetrics], run_dir: Path) -> None:
    if not MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available - skipping plot generation")
        return
    if not metrics:
        logger.warning("No metrics to plot.")
        return

    ordered = sorted(metrics, key=lambda m: _trend_query_sort_key(m.query_id))
    x_labels = [m.query_id for m in ordered]
    x = list(range(len(x_labels)))

    result_rows = [m.result_rows for m in ordered]
    token_cost = [m.total_tokens for m in ordered]
    latency = [m.latency_s for m in ordered]
    f1 = [m.macro_f1 for m in ordered]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "Player Query-Awareness Trend with DocETL (ReDD-aligned IDs)",
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
    setup_logging(run_dir / "query_awareness_trend_docetl.log")

    logger.info("Starting Player query-awareness trend test (DocETL)...")
    logger.info(f"Run directory: {run_dir}")
    logger.info(
        "Query set: Query/Player/{S,F,A,J,M}/*.sql filtered by ReDD NL_QUERY_SPECS"
    )
    logger.info(f"ReDD spec file: {REDD_TREND_FILE}")
    logger.info(
        "Execution: one docetl.api.Pipeline (Dataset + MapOp) per table, "
        "then benchmark SQL on SQLite."
    )
    logger.info(f"Per-query pipeline artifacts: {run_dir / 'docetl_pipelines'}/<query_id>/")
    logger.info(f"Source data dir: {SOURCE_DATA_PLAYER_DIR}")
    logger.info(f"Model: {DOCETL_MODEL} @ {OLLAMA_BASE_URL}")
    logger.info(f"Identity columns (for eval): {IDENTITY_COLUMNS}")

    try:
        metrics = run_trend_queries_docetl(run_dir)
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
        logger.exception(f"DocETL trend test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

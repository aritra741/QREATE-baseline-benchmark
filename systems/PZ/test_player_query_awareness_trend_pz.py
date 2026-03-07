"""
Run Q1..Q10 query-awareness trend benchmarking with Palimpzest on Player.

This mirrors systems/DocETL/test_player_query_awareness_trend_docetl.py, but:
- uses Palimpzest extraction (`sem_map`) over source text documents
- uses Palimpzest relational join operator (`join`) for equijoins
- uses deterministic row filters for SQL-like predicates
"""

import csv
import json
import logging
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Force Ollama-only mode before importing Palimpzest.
os.environ["PALIMPZEST_USE_OLLAMA_ONLY"] = "true"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
os.environ["LITELLM_DROP_PARAMS"] = "True"
if not os.getenv("OLLAMA_API_BASE"):
    os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"


logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
WDIRS_DIR = PROJECT_ROOT / "systems" / "WDIRS"
PZ_SRC_DIR = PROJECT_ROOT / "systems" / "PZ" / "PZ_original" / "palimpzest" / "src"

sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(PZ_SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from config import QUERY_DIR, RESULTS_DIR  # type: ignore
from token_counter import GLOBAL_COUNTER, ensure_precise_tokenizer_ready

import palimpzest as pz  # type: ignore

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
SOURCE_DATA_PLAYER_DIR = PROJECT_ROOT / "source_data" / "Player"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_pz"

PZ_MODEL = pz.Model.OLLAMA_QWEN_2_5_7B_INSTRUCT
PZ_MAX_WORKERS = 4

NUMERIC_FIELDS = {
    "age",
    "draft_pick",
    "founded_year",
    "population",
    "gdp",
    "area",
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


def _to_builtin(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if hasattr(v, "item"):
        return v.item()
    return v


def _short_col_name(col: Any) -> str:
    s = str(col)
    # Handle qualified names such as "table.column" or "dataset.table.column".
    s = s.split(".")[-1]
    # Handle pandas-style merge suffixes if they ever appear.
    if s.endswith("_x") or s.endswith("_y"):
        s = s[:-2]
    return s


def _resolve_project_columns(df: pd.DataFrame, selected_cols: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    if not selected_cols:
        return df, selected_cols

    resolved: List[str] = []
    rename_map: Dict[str, str] = {}
    all_cols = list(df.columns)
    used_source_cols: set[str] = set()

    for want in selected_cols:
        # 1) exact match
        if want in df.columns:
            resolved.append(want)
            used_source_cols.add(want)
            continue

        # 2) resolve by short name (e.g., "Q8_player.name" -> "name")
        candidates = [c for c in all_cols if _short_col_name(c) == want and str(c) not in used_source_cols]
        if not candidates:
            continue

        # Prefer a stable deterministic candidate.
        chosen = str(sorted(candidates, key=lambda x: str(x))[0])
        used_source_cols.add(chosen)
        rename_map[chosen] = want
        resolved.append(want)

    out = df.copy()
    if rename_map:
        out = out.rename(columns=rename_map)
    return out, resolved


def _extract_token_usage(record_collection: Any) -> Tuple[int, int]:
    stats = getattr(record_collection, "execution_stats", None)
    if stats is None:
        raise RuntimeError("Missing execution_stats in Palimpzest run output; token accounting cannot proceed.")
    p = int(getattr(stats, "total_input_tokens", 0) or 0)
    c = int(getattr(stats, "total_output_tokens", 0) or 0)
    if p < 0 or c < 0:
        raise RuntimeError(f"Invalid token counts from Palimpzest execution stats: prompt={p}, completion={c}")
    return p, c


def _pz_run_config() -> "pz.QueryProcessorConfig":
    return pz.QueryProcessorConfig(
        policy=pz.MaxQuality(),
        execution_strategy="parallel",
        max_workers=PZ_MAX_WORKERS,
        progress=False,
        available_models=[PZ_MODEL],
    )


def _load_source_docs(table: str) -> "pz.TextFileDataset":
    table_dir = SOURCE_DATA_PLAYER_DIR / table
    if not table_dir.exists():
        raise FileNotFoundError(f"Missing source table directory: {table_dir}")
    return pz.TextFileDataset(id=f"{table}_docs", path=str(table_dir))


def _coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in list(out.columns):
        if col in NUMERIC_FIELDS:
            out[col] = (
                out[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _extract_table_for_query(
    table: str,
    needed_cols: List[str],
    nl_query: str,
) -> Tuple[pd.DataFrame, int, int]:
    docs_ds = _load_source_docs(table)
    schema_fields = [
        {
            "name": col,
            "type": (float if col in NUMERIC_FIELDS else str),
            "desc": (
                f"{col} from the {table} document for query: {nl_query}. "
                f"Return {'a number' if col in NUMERIC_FIELDS else 'a short normalized string'}."
            ),
        }
        for col in needed_cols
    ]

    extracted_ds = docs_ds.sem_map(schema_fields)
    output = extracted_ds.run(_pz_run_config())
    prompt_toks, completion_toks = _extract_token_usage(output)

    df = output.to_df()
    keep_cols = [c for c in needed_cols if c in df.columns]
    if not keep_cols:
        raise RuntimeError(
            f"Extraction produced no expected columns for table '{table}' in query ETL"
        )

    out = df[keep_cols].copy()
    out = _coerce_numeric_columns(out)

    GLOBAL_COUNTER.record(
        input_tokens=prompt_toks,
        output_tokens=completion_toks,
        operation="pz",
    )
    return out, prompt_toks, completion_toks


NL_QUERY_SPECS: Dict[str, Dict[str, Any]] = {
    "Q1": {
        "nl_query": "List each player's name, nationality, and age with their team name and team location.",
        "base_table": "player",
        "tables": {"player": ["name", "nationality", "age", "team"], "team": ["team_name", "location"]},
        "joins": [{"right_table": "team", "left_key": "team", "right_key": "team_name"}],
        "filters": [],
        "select": ["name", "nationality", "age", "team_name", "location"],
    },
    "Q2": {
        "nl_query": "For players older than 25, list player name, position, team name, and team founded year.",
        "base_table": "player",
        "tables": {"player": ["name", "position", "age", "team"], "team": ["team_name", "founded_year"]},
        "joins": [{"right_table": "team", "left_key": "team", "right_key": "team_name"}],
        "filters": [{"column": "age", "operator": "greater than", "value": "25"}],
        "select": ["name", "position", "team_name", "founded_year"],
    },
    "Q3": {
        "nl_query": "For players with draft pick at least 0, list player name, draft pick, college, and team name.",
        "base_table": "player",
        "tables": {"player": ["name", "draft_pick", "college", "team"], "team": ["team_name"]},
        "joins": [{"right_table": "team", "left_key": "team", "right_key": "team_name"}],
        "filters": [{"column": "draft_pick", "operator": "greater than or equal to", "value": "0"}],
        "select": ["name", "draft_pick", "college", "team_name"],
    },
    "Q4": {
        "nl_query": "List team name and location with the matched city name and state name.",
        "base_table": "team",
        "tables": {"team": ["team_name", "location"], "city": ["city_name", "state_name"]},
        "joins": [{"right_table": "city", "left_key": "location", "right_key": "city_name"}],
        "filters": [],
        "select": ["team_name", "location", "city_name", "state_name"],
    },
    "Q5": {
        "nl_query": "List player name with team name, city name, and city state by linking player -> team -> city.",
        "base_table": "player",
        "tables": {
            "player": ["name", "team"],
            "team": ["team_name", "location"],
            "city": ["city_name", "state_name"],
        },
        "joins": [
            {"right_table": "team", "left_key": "team", "right_key": "team_name"},
            {"right_table": "city", "left_key": "location", "right_key": "city_name"},
        ],
        "filters": [],
        "select": ["name", "team_name", "city_name", "state_name"],
    },
    "Q6": {
        "nl_query": "For players younger than 35, list player name, position, city name, and city population via player -> team -> city.",
        "base_table": "player",
        "tables": {
            "player": ["name", "position", "age", "team"],
            "team": ["team_name", "location"],
            "city": ["city_name", "population"],
        },
        "joins": [
            {"right_table": "team", "left_key": "team", "right_key": "team_name"},
            {"right_table": "city", "left_key": "location", "right_key": "city_name"},
        ],
        "filters": [{"column": "age", "operator": "less than", "value": "35"}],
        "select": ["name", "position", "city_name", "population"],
    },
    "Q7": {
        "nl_query": "For players with draft pick greater than 0, list player name, college, team name, and city GDP via player -> team -> city.",
        "base_table": "player",
        "tables": {
            "player": ["name", "college", "draft_pick", "team"],
            "team": ["team_name", "location"],
            "city": ["city_name", "gdp"],
        },
        "joins": [
            {"right_table": "team", "left_key": "team", "right_key": "team_name"},
            {"right_table": "city", "left_key": "location", "right_key": "city_name"},
        ],
        "filters": [{"column": "draft_pick", "operator": "greater than", "value": "0"}],
        "select": ["name", "college", "team_name", "gdp"],
    },
    "Q8": {
        "nl_query": "For cities with area greater than 100, list player name, player birth date, team name, and city area via player -> team -> city.",
        "base_table": "player",
        "tables": {
            "player": ["name", "birth_date", "team"],
            "team": ["team_name", "location"],
            "city": ["city_name", "area"],
        },
        "joins": [
            {"right_table": "team", "left_key": "team", "right_key": "team_name"},
            {"right_table": "city", "left_key": "location", "right_key": "city_name"},
        ],
        "filters": [{"column": "area", "operator": "greater than", "value": "100"}],
        "select": ["name", "birth_date", "team_name", "area"],
    },
    "Q9": {
        "nl_query": "Starting from city and traversing city -> team -> player, list city name, state, team name, and player name for players younger than 40.",
        "base_table": "city",
        "tables": {
            "city": ["city_name", "state_name"],
            "team": ["team_name", "location"],
            "player": ["name", "age", "team"],
        },
        "joins": [
            {"right_table": "team", "left_key": "city_name", "right_key": "location"},
            {"right_table": "player", "left_key": "team_name", "right_key": "team"},
        ],
        "filters": [{"column": "age", "operator": "less than", "value": "40"}],
        "select": ["city_name", "state_name", "team_name", "name"],
    },
    "Q10": {
        "nl_query": "Starting from city and traversing city -> team -> player, list city name, state, team name, player name, and player college for players older than 20.",
        "base_table": "city",
        "tables": {
            "city": ["city_name", "state_name"],
            "team": ["team_name", "location"],
            "player": ["name", "college", "age", "team"],
        },
        "joins": [
            {"right_table": "team", "left_key": "city_name", "right_key": "location"},
            {"right_table": "player", "left_key": "team_name", "right_key": "team"},
        ],
        "filters": [{"column": "age", "operator": "greater than", "value": "20"}],
        "select": ["city_name", "state_name", "team_name", "name", "college"],
    },
}


def _make_numeric_filter_fn(column: str, operator: str, value: str) -> Callable[[Dict[str, Any]], bool]:
    val = float(value)
    op = operator.strip().lower()

    def _strict_float(v: Any) -> float:
        if v is None:
            raise ValueError(f"Numeric filter column '{column}' has null value.")
        try:
            return float(v)
        except Exception as exc:
            raise ValueError(
                f"Numeric filter column '{column}' has non-numeric value: {v!r}"
            ) from exc

    if op == "greater than":
        return lambda row: _strict_float(row.get(column)) > val
    if op == "greater than or equal to":
        return lambda row: _strict_float(row.get(column)) >= val
    if op == "less than":
        return lambda row: _strict_float(row.get(column)) < val
    if op == "less than or equal to":
        return lambda row: _strict_float(row.get(column)) <= val
    raise ValueError(f"Unsupported numeric filter operator: {operator}")


def _apply_filters(current_ds: "pz.Dataset", filters: List[Dict[str, str]]) -> "pz.Dataset":
    out = current_ds
    for f in filters:
        col = f["column"]
        op = f["operator"]
        value = f["value"]
        fn = _make_numeric_filter_fn(col, op, value)
        out = out.filter(fn, depends_on=[col])
    return out


def execute_query_via_pz(
    query_id: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, pd.DataFrame], str, int, int]:
    if query_id not in NL_QUERY_SPECS:
        raise ValueError(f"No NL query specification found for {query_id}")
    spec = NL_QUERY_SPECS[query_id]
    nl_query = spec["nl_query"]

    table_map: Dict[str, pd.DataFrame] = {}
    prompt_tokens = 0
    completion_tokens = 0
    for table, cols in spec["tables"].items():
        logger.info(f"[{query_id}] PZ query-local ETL for '{table}' with columns: {cols}")
        table_df, p_tok, c_tok = _extract_table_for_query(table, cols, nl_query)
        table_map[table] = table_df
        prompt_tokens += p_tok
        completion_tokens += c_tok

    base_table = spec["base_table"]
    if base_table not in table_map:
        raise ValueError(f"Unknown base table in spec: {base_table}")

    current_ds = pz.MemoryDataset(id=f"{query_id}_{base_table}", vals=table_map[base_table].copy())
    for join_idx, join_spec in enumerate(spec["joins"]):
        right_table = join_spec["right_table"]
        if right_table not in table_map:
            raise ValueError(f"Unknown join table: {right_table}")
        left_key = join_spec["left_key"]
        right_key = join_spec["right_key"]

        right_df = table_map[right_table].copy()
        if left_key not in right_df.columns and right_key in right_df.columns:
            # Align key names so we can use deterministic equijoin via `join(on=...)`.
            right_df[left_key] = right_df[right_key]
        if left_key not in right_df.columns:
            raise ValueError(
                f"Right table '{right_table}' lacks joinable key '{left_key}' "
                f"(right_key={right_key})."
            )

        right_ds = pz.MemoryDataset(id=f"{query_id}_{right_table}_{join_idx}", vals=right_df)
        current_ds = current_ds.join(right_ds, on=left_key, how="inner")

    current_ds = _apply_filters(current_ds, spec["filters"])

    joined_out = current_ds.run(_pz_run_config())
    p_tok, c_tok = _extract_token_usage(joined_out)
    prompt_tokens += p_tok
    completion_tokens += c_tok
    GLOBAL_COUNTER.record(
        input_tokens=p_tok,
        output_tokens=c_tok,
        operation="pz",
    )
    out_df = joined_out.to_df()

    selected_cols: List[str] = list(spec["select"])
    out_df, resolved_cols = _resolve_project_columns(out_df, selected_cols)
    missing_cols = [c for c in selected_cols if c not in resolved_cols]
    if missing_cols:
        available = [str(c) for c in out_df.columns]
        raise ValueError(
            f"Projected columns missing after execution: {missing_cols}. "
            f"Available columns: {available}"
        )

    out_df = out_df[selected_cols].copy()
    rows = [{k: _to_builtin(v) for k, v in r.items()} for r in out_df.to_dict("records")]
    return rows, table_map, nl_query, prompt_tokens, completion_tokens


def _write_query_tables_sqlite(table_map: Dict[str, pd.DataFrame], db_path: Path) -> None:
    def _sqlite_safe_scalar(v: Any) -> Any:
        # Keep NULLs as NULL in SQLite.
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, (str, int, float, bool, bytes)):
            return v
        if isinstance(v, (list, tuple, dict, set)):
            return json.dumps(v, ensure_ascii=False, default=str)
        if hasattr(v, "item"):
            try:
                return v.item()
            except Exception:
                pass
        return str(v)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with pd.option_context("mode.copy_on_write", True):
        with __import__("sqlite3").connect(db_path) as conn:
            for table, df in table_map.items():
                safe_df = df.copy()
                for col in safe_df.columns:
                    safe_df[col] = safe_df[col].map(_sqlite_safe_scalar)
                safe_df.to_sql(table, conn, if_exists="replace", index=False)


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


def run_trend_queries_pz(
    run_dir: Path,
) -> List[TrendQueryMetrics]:
    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    plots_dir = run_dir / "plots"
    query_eval_db_dir = run_dir / "query_eval_dbs"

    run_dir.mkdir(parents=True, exist_ok=True)
    query_results_dir.mkdir(parents=True, exist_ok=True)
    query_tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    query_eval_db_dir.mkdir(parents=True, exist_ok=True)

    identity_columns = IDENTITY_COLUMNS.copy()
    logger.info(f"Using hardcoded identity columns: {identity_columns}")

    eval_attributes: Dict[str, Any] = (
        _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    )
    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=eval_attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info(f"Executing {query_id} with PZ")
        t0 = time.time()
        rows, query_table_map, nl_query, d_prompt, d_completion = execute_query_via_pz(query_id)
        logger.info(f"[NL] {nl_query}")
        latency = time.time() - t0
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
            delta_type="PZ",
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
        "Player Query-Awareness Trend with Palimpzest (Q1..Q10)",
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
    setup_logging(run_dir / "query_awareness_trend_pz.log")

    logger.info("Starting Player query-awareness trend test (Palimpzest)...")
    logger.info(f"Run directory: {run_dir}")
    logger.info(f"Trend query source: {TREND_SQL_FILE}")
    logger.info(f"Source data dir: {SOURCE_DATA_PLAYER_DIR}")
    logger.info(f"Model: {PZ_MODEL.value} @ {os.getenv('OLLAMA_API_BASE')}")
    logger.info(f"Identity columns (for eval): {IDENTITY_COLUMNS}")

    try:
        metrics = run_trend_queries_pz(run_dir)
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
        logger.exception(f"Palimpzest trend test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

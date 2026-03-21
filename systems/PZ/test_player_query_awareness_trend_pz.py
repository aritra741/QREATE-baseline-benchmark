"""
Run query-awareness trend benchmarking with Palimpzest on Player.

Query set matches WDIRS/ReDD (Query/Player/{Select,Filter,Agg,Join,Mixed}/*.sql,
filtered by uncommented IDs in ReDD's NL_QUERY_SPECS), same as
systems/DocETL/test_player_query_awareness_trend_docetl.py.

For each query: Palimpzest `sem_map` extracts per-table columns inferred from the
benchmark SQL; joins/filters/aggregations run deterministically in SQLite on the
extracted relations (DocETL-style closure).
"""

import sys


def _ensure_sqlite3_for_chromadb() -> None:
    """
    ChromaDB (pulled in by Palimpzest) requires SQLite >= 3.35.0. Cluster images often
    ship older libsqlite3. If so, install a bundled build:

        pip install pysqlite3-binary

    then re-run. This replaces the stdlib ``sqlite3`` binding before Palimpzest loads.
    """
    import sqlite3 as _stdlib_sqlite3

    if _stdlib_sqlite3.sqlite_version_info >= (3, 35, 0):
        return
    del sys.modules["sqlite3"]
    try:
        import pysqlite3 as _pysqlite3  # type: ignore[import-untyped]
    except ImportError as exc:
        ver = ".".join(str(x) for x in _stdlib_sqlite3.sqlite_version_info)
        raise RuntimeError(
            f"SQLite {ver} is too old for ChromaDB (needs >= 3.35.0). "
            "Typical fix on HPC: pip install pysqlite3-binary\n"
            "https://docs.trychroma.com/troubleshooting#sqlite"
        ) from exc
    sys.modules["sqlite3"] = _pysqlite3


_ensure_sqlite3_for_chromadb()

import csv
import importlib.util
import json
import logging
import math
import os
import sqlite3
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import sqlglot
from sqlglot import exp

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

from config import RESULTS_DIR  # type: ignore
from token_counter import GLOBAL_COUNTER, ensure_precise_tokenizer_ready

import palimpzest as pz  # type: ignore

from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.row_matcher import RowMatcher as _RowMatcher
from evaluation.sql_parser import SqlParser as _SqlParser
from test_player_query_awareness_trend import (  # type: ignore
    _infer_identity_col_for_query,
    evaluate_with_official_framework,
    load_redd_enabled_query_ids,
    parse_all_category_queries,
)


DATASET_QUERY = "Player"
REDD_TREND_FILE = PROJECT_ROOT / "systems" / "ReDD" / "test_player_query_awareness_trend_redd.py"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"
SOURCE_DATA_PLAYER_DIR = PROJECT_ROOT / "source_data" / "Player"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_pz"

PZ_MODEL = pz.Model.OLLAMA_QWEN_2_5_7B_INSTRUCT
PZ_MAX_WORKERS = 4

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

# Column dictionary for resolving unqualified SQL columns (mirrors DocETL trend harness).
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
    macro_f1: Optional[float]
    macro_precision: Optional[float]
    macro_recall: Optional[float]
    gt_result_count: int
    matched_rows: Optional[int]
    is_agg: bool
    relative_error: Optional[float] = None
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


def load_redd_nl_query_specs(redd_path: Path) -> Dict[str, str]:
    """NL strings from ReDD's NL_QUERY_SPECS (same source WDIRS uses for filtering)."""
    module_name = "_pz_redd_nl_specs"
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
    """Collect table -> column names from benchmark SQL (DocETL trend harness logic)."""
    tree = sqlglot.parse_one(sql_text)

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
        rows.append(
            {out_names[i]: _to_builtin(tup[i]) for i in range(len(out_names))}
        )
    return rows


def execute_query_via_pz(
    query_id: str,
    sql_text: str,
    nl_query: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, pd.DataFrame], str, int, int]:
    need = columns_per_table_from_sql(sql_text)
    table_map: Dict[str, pd.DataFrame] = {}
    prompt_tokens = 0
    completion_tokens = 0
    for table, cols in need.items():
        logger.info(f"[{query_id}] PZ sem_map for '{table}': {cols}")
        table_df, p_tok, c_tok = _extract_table_for_query(table, cols, nl_query)
        table_map[table] = table_df
        prompt_tokens += p_tok
        completion_tokens += c_tok

    rows = _execute_benchmark_sql(sql_text, table_map)
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
        with sqlite3.connect(db_path) as conn:
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
        "Running %d Palimpzest queries aligned with WDIRS/ReDD (uncommented ReDD IDs)",
        len(trend_queries),
    )

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info(f"Executing {query_id} with PZ")
        t0 = time.time()

        try:
            nl_query = redd_nl_specs.get(query_id)
            if not nl_query:
                raise ValueError(
                    f"No NL_QUERY_SPECS entry for {query_id} in {REDD_TREND_FILE}"
                )
            rows, query_table_map, nl_query, d_prompt, d_completion = execute_query_via_pz(
                query_id, query_text, nl_query
            )
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
                macro_f1=eval_out.get("macro_f1"),
                macro_precision=eval_out.get("macro_precision"),
                macro_recall=eval_out.get("macro_recall"),
                gt_result_count=eval_out.get("gt_result_count", 0),
                matched_rows=eval_out.get("matched_rows"),
                is_agg=eval_out.get("is_agg", False),
                relative_error=eval_out.get("relative_error"),
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
            acc_data["relative_error"] = eval_out.get("relative_error")
            acc_data.setdefault("macro_f1", eval_out.get("macro_f1"))
            acc_data.setdefault("macro_precision", eval_out.get("macro_precision"))
            acc_data.setdefault("macro_recall", eval_out.get("macro_recall"))
            acc_path.write_text(json.dumps(acc_data, indent=2))

            if item.is_agg:
                rel_err_str = (
                    "n/a"
                    if item.relative_error is None
                    else f"{item.relative_error:.4f}"
                )
                logger.info(
                    f"{query_id}: rows={item.result_rows} latency={item.latency_s:.3f}s "
                    f"tokens={item.total_tokens} RelErr={rel_err_str}"
                )
            else:
                f1 = item.macro_f1 if item.macro_f1 is not None else 0.0
                logger.info(
                    f"{query_id}: rows={item.result_rows} latency={item.latency_s:.3f}s "
                    f"tokens={item.total_tokens} F1={f1:.3f}"
                )
        except Exception as exc:
            latency = time.time() - t0
            nl_fallback = redd_nl_specs.get(query_id, "")
            metrics.append(
                TrendQueryMetrics(
                    query_id=query_id,
                    query_text=query_text,
                    nl_query=nl_fallback,
                    success=False,
                    delta_type="ERROR",
                    latency_s=latency,
                    result_rows=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    macro_f1=0.0,
                    macro_precision=0.0,
                    macro_recall=0.0,
                    gt_result_count=0,
                    matched_rows=0,
                    is_agg=False,
                    relative_error=None,
                    error=str(exc),
                )
            )
            acc_path = query_results_dir / query_id / "acc.json"
            acc_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                acc_path.write_text(
                    json.dumps(
                        {
                            "query_id": query_id,
                            "latency_s": round(latency, 4),
                            "success": False,
                            "error": str(exc),
                        },
                        indent=2,
                    )
                )
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
    if not metrics:
        raise RuntimeError("No metrics to plot.")

    ordered = sorted(metrics, key=lambda m: _trend_query_sort_key(m.query_id))
    x_labels = [m.query_id for m in ordered]
    x = list(range(len(x_labels)))

    result_rows = [m.result_rows for m in ordered]
    token_cost = [m.total_tokens for m in ordered]
    latency = [m.latency_s for m in ordered]
    f1 = [
        m.macro_f1 if m.macro_f1 is not None else float("nan") for m in ordered
    ]
    rel_err = [
        m.relative_error if m.relative_error is not None else float("nan")
        for m in ordered
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "Player Query-Awareness Trend with Palimpzest (ReDD-aligned IDs)",
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

    non_agg_x = [i for i, m in enumerate(ordered) if not m.is_agg]
    non_agg_f1 = [f1[i] for i in non_agg_x]
    agg_x = [i for i, m in enumerate(ordered) if m.is_agg]
    agg_re = [rel_err[i] for i in agg_x]
    if non_agg_x:
        axes[1, 1].plot(
            non_agg_x, non_agg_f1, marker="o", color="#27ae60", label="Macro F1 (non-agg)"
        )
    if agg_x:
        axes[1, 1].plot(
            agg_x,
            agg_re,
            marker="s",
            color="#e67e22",
            label="Rel. Error (agg, lower=better)",
        )
    axes[1, 1].set_title("Accuracy by query type")
    axes[1, 1].set_xticks(x)
    axes[1, 1].set_xticklabels(x_labels)
    axes[1, 1].set_ylabel("score")
    axes[1, 1].grid(alpha=0.3)
    axes[1, 1].legend(fontsize=8)

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
    logger.info(
        "Query set: Query/Player/{{S,F,A,J,M}}/*.sql filtered by ReDD NL_QUERY_SPECS "
        f"({REDD_TREND_FILE})"
    )
    logger.info(f"Source data dir: {SOURCE_DATA_PLAYER_DIR}")
    logger.info(f"Model: {PZ_MODEL.value} @ {os.getenv('OLLAMA_API_BASE')}")
    logger.info(f"Identity columns (for eval): {IDENTITY_COLUMNS}")

    try:
        metrics = run_trend_queries_pz(run_dir)
        save_metrics(metrics, run_dir)
        plot_metrics(metrics, run_dir)

        success_count = sum(1 for m in metrics if m.success)
        non_agg = [m for m in metrics if m.success and not m.is_agg]
        agg_ok = [
            m for m in metrics if m.success and m.is_agg and m.relative_error is not None
        ]
        avg_f1 = (
            sum(m.macro_f1 for m in non_agg if m.macro_f1 is not None) / len(non_agg)
            if non_agg
            else 0.0
        )
        avg_rel_err = (
            sum(m.relative_error for m in agg_ok) / len(agg_ok) if agg_ok else None
        )
        if not math.isfinite(avg_f1):
            avg_f1 = 0.0
        logger.info("=" * 80)
        logger.info(f"Completed: {success_count}/{len(metrics)} queries succeeded")
        if non_agg:
            logger.info(
                f"Non-aggregation queries ({len(non_agg)}): avg macro F1={avg_f1:.3f}"
            )
        if avg_rel_err is not None and math.isfinite(avg_rel_err):
            logger.info(
                f"Aggregation queries ({len(agg_ok)}): avg relative error={avg_rel_err:.4f}"
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

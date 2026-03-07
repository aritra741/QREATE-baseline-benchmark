"""
Run Q1..Q10 query-awareness trend benchmarking with Doctopus on Player.

Strategy
--------
Doctopus is an extraction-only system.  We adapt it to the full benchmark
contract by following three steps for every query:

  1. EXTRACT  – Call Doctopus's LLM extraction prompt (via Ollama /
                qwen2.5:7b-instruct, unlimited token budget) on each
                source .txt document for the tables that the query needs.
                This produces flat DataFrames keyed by identity column.

  2. LOAD     – Write those DataFrames into a per-query SQLite database,
                mirroring the same pattern used by DocETL / WDIRS.

  3. EXECUTE  – Run the original SQL query text from
                Query/Player/query_aware_trend_queries.sql against the
                SQLite DB and collect the result rows.

Token accounting uses the shared WDIRS token_counter (GLOBAL_COUNTER +
count_tokens), monkey-patching the single low-level Ollama call site so
every completion – including retries – is counted.

Evaluation uses the shared official framework imported from the WDIRS
test script (evaluate_with_official_framework + parse_trend_queries +
_infer_identity_col_for_query).
"""

import csv
import json
import logging
import math
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False


# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent
WDIRS_DIR = PROJECT_ROOT / "systems" / "WDIRS"
DOCTOPUS_CORE_DIR = PROJECT_ROOT / "systems" / "Doctopus" / "Doctopus"

sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(DOCTOPUS_CORE_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from token_counter import GLOBAL_COUNTER, count_tokens, ensure_precise_tokenizer_ready  # type: ignore
from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json  # type: ignore
from evaluation.gt_runner import GtRunner as _GtRunner  # type: ignore
from evaluation.row_matcher import RowMatcher as _RowMatcher  # type: ignore
from evaluation.sql_parser import SqlParser as _SqlParser  # type: ignore
from Utils import prompt as doctopus_prompt  # type: ignore
from test_player_query_awareness_trend import (  # type: ignore
    parse_trend_queries,
    evaluate_with_official_framework,
    _infer_identity_col_for_query,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATASET = "Player"
TREND_SQL_FILE = PROJECT_ROOT / "Query" / "Player" / "query_aware_trend_queries.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / "Player" / "Player_attributes.json"
SOURCE_DATA_DIR = PROJECT_ROOT / "source_data" / "Player"
RESULTS_BASE_DIR = PROJECT_ROOT / "results" / "player_query_awareness_trend_doctopus"

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_API_URL = f"{OLLAMA_BASE_URL}/api/chat"
MODEL = "qwen2.5:7b-instruct"

IDENTITY_COLUMNS: Dict[str, str] = {
    "player": "name",
    "team": "team_name",
    "city": "city_name",
    "owner": "name",
}

NUMERIC_FIELDS = {"age", "draft_pick", "founded_year", "population", "gdp", "area"}

# Columns each table exposes (superset; extraction always returns all of them
# and the query executor SELECT-trims to what the SQL actually needs).
TABLE_SCHEMA: Dict[str, List[str]] = {
    "player": ["name", "nationality", "age", "position", "draft_pick", "college", "birth_date", "team"],
    "team": ["team_name", "location", "founded_year"],
    "city": ["city_name", "state_name", "population", "gdp", "area"],
}

# Q1..Q10 natural-language queries (mirror DocETL / WDIRS NL_QUERY_SPECS)
NL_QUERY_SPECS: Dict[str, str] = {
    "Q1":  "List each player's name, nationality, and age with their team name and team location.",
    "Q2":  "For players older than 25, list player name, position, team name, and team founded year.",
    "Q3":  "For players with draft pick at least 0, list player name, draft pick, college, and team name.",
    "Q4":  "List team name and location with matched city name and state name.",
    "Q5":  "List player name with team name, city name, and city state by linking player → team → city.",
    "Q6":  "For players younger than 35, list player name, position, city name, and city population via player → team → city.",
    "Q7":  "For players with draft pick greater than 0, list player name, college, team name, and city GDP via player → team → city.",
    "Q8":  "For cities with area greater than 100, list player name, player birth date, team name, and city area via player → team → city.",
    "Q9":  "Starting from city and traversing city → team → player, list city name, state, team name, and player name for players younger than 40.",
    "Q10": "Starting from city and traversing city → team → player, list city name, state, team name, player name, and player college for players older than 20.",
}

# Which tables each query needs extracted
QUERY_TABLES: Dict[str, List[str]] = {
    "Q1":  ["player", "team"],
    "Q2":  ["player", "team"],
    "Q3":  ["player", "team"],
    "Q4":  ["team", "city"],
    "Q5":  ["player", "team", "city"],
    "Q6":  ["player", "team", "city"],
    "Q7":  ["player", "team", "city"],
    "Q8":  ["player", "team", "city"],
    "Q9":  ["city", "team", "player"],
    "Q10": ["city", "team", "player"],
}

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------

@dataclass
class _TokenSnapshot:
    prompt: int
    completion: int


class TokenTracker:
    """Accumulates prompt + completion tokens across Ollama calls."""

    def __init__(self) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0

    def snapshot(self) -> _TokenSnapshot:
        return _TokenSnapshot(self.prompt_tokens, self.completion_tokens)

    def delta(self, before: _TokenSnapshot) -> Tuple[int, int]:
        return self.prompt_tokens - before.prompt, self.completion_tokens - before.completion

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += max(0, int(prompt))
        self.completion_tokens += max(0, int(completion))


_TRACKER: TokenTracker = TokenTracker()
_ORIGINAL_POST = requests.post


def _patched_post(url: str, *args: Any, **kwargs: Any) -> requests.Response:
    """Intercept every Ollama /api/chat call to count tokens."""
    response = _ORIGINAL_POST(url, *args, **kwargs)
    if OLLAMA_API_URL in url and response.ok:
        try:
            data = response.json()
            prompt_eval = data.get("prompt_eval_count", 0) or 0
            eval_count = data.get("eval_count", 0) or 0
            _TRACKER.add(prompt_eval, eval_count)
            GLOBAL_COUNTER.record(
                input_tokens=prompt_eval,
                output_tokens=eval_count,
                operation="doctopus",
            )
        except Exception:
            pass
    return response


def patch_ollama_for_token_tracking() -> None:
    """Monkey-patch requests.post so every Ollama call is counted."""
    import requests as _req_module
    _req_module.post = _patched_post  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Doctopus extraction prompt (directly reused from Doctopus/Utils/prompt.py)
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT_TEMPLATE = doctopus_prompt.prompt_template_for_extract


def _clean_json(raw: str) -> Optional[Dict[str, Any]]:
    """Strip markdown fences and parse JSON, returning None on failure."""
    parsed = doctopus_prompt.clean_json_response(raw)
    if isinstance(parsed, dict) and "error" not in parsed:
        return parsed
    text = raw.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def _ollama_extract(doc_text: str, columns: List[str]) -> Dict[str, Any]:
    """
    Call qwen2.5:7b-instruct via Ollama to extract *columns* from *doc_text*.
    Returns a dict {col: value}.  On failure returns a dict of empty strings.
    """
    numeric_attrs = [c for c in columns if c in NUMERIC_FIELDS]
    prompt = _EXTRACT_PROMPT_TEMPLATE.format(
        file_content=doc_text,
        attributes_list=", ".join(columns),
    )
    prompt += (
        "\n\nAdditional constraints for this benchmark:\n"
        f"- Numeric attributes ({', '.join(numeric_attrs) if numeric_attrs else 'none'}) "
        "must be plain numbers without commas/units; unknown numeric values should be -1.\n"
        '- If a text attribute is unknown, return "".\n'
        "- Always return exactly the requested keys.\n"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are an assistant that extracts structured data from text documents.",
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }

    try:
        resp = requests.post(OLLAMA_API_URL, json=payload, timeout=300)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = _clean_json(content)
        if parsed and isinstance(parsed, dict):
            return parsed
        logger.warning("Extraction returned unparseable JSON for a doc; using empty.")
    except Exception as exc:
        logger.warning("Ollama extraction error: %s", exc)

    return {c: "" for c in columns}


def _coerce_numerics(df: pd.DataFrame, table: str) -> pd.DataFrame:
    out = df.copy()
    for col in TABLE_SCHEMA.get(table, []):
        if col in NUMERIC_FIELDS and col in out.columns:
            out[col] = (
                out[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(r"\s+", "", regex=True)
            )
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def extract_table(table: str) -> pd.DataFrame:
    """
    Run Doctopus-style extraction over all .txt files for *table*.
    Returns a DataFrame with the full TABLE_SCHEMA columns for that table.
    """
    table_dir = SOURCE_DATA_DIR / table
    if not table_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {table_dir}")

    columns = TABLE_SCHEMA[table]
    rows: List[Dict[str, Any]] = []

    txt_files = sorted(table_dir.glob("*.txt"), key=lambda p: int(p.stem))
    if not txt_files:
        raise RuntimeError(f"No .txt files found in {table_dir}")

    logger.info("  Extracting table '%s' from %d docs...", table, len(txt_files))
    for txt_path in txt_files:
        doc_text = txt_path.read_text(errors="ignore")
        extracted = _ollama_extract(doc_text, columns)
        # Keep only expected keys, fill missing with ""
        row: Dict[str, Any] = {c: extracted.get(c, "") for c in columns}
        rows.append(row)

    df = pd.DataFrame(rows, columns=columns)
    df = _coerce_numerics(df, table)
    return df


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def write_tables_to_sqlite(table_map: Dict[str, pd.DataFrame], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        for tbl_name, df in table_map.items():
            df.to_sql(tbl_name, conn, if_exists="replace", index=False)


def execute_sql_on_db(db_path: Path, sql: str) -> List[Dict[str, Any]]:
    """Run *sql* against *db_path* and return rows as list-of-dicts."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as exc:
            logger.error("SQL execution error: %s\nSQL: %s", exc, sql)
            raise


# ---------------------------------------------------------------------------
# Per-query execution
# ---------------------------------------------------------------------------

def execute_query(
    query_id: str,
    query_text: str,
    query_eval_db_dir: Path,
) -> Tuple[List[Dict[str, Any]], Dict[str, pd.DataFrame]]:
    """
    Extract required tables, persist to SQLite, execute the SQL, return rows.
    """
    needed_tables = QUERY_TABLES[query_id]
    table_map: Dict[str, pd.DataFrame] = {}
    for tbl in needed_tables:
        logger.info("[%s] Extracting table '%s'...", query_id, tbl)
        table_map[tbl] = extract_table(tbl)

    db_path = query_eval_db_dir / f"{query_id}.db"
    write_tables_to_sqlite(table_map, db_path)
    logger.info("[%s] Tables written to %s", query_id, db_path)

    rows = execute_sql_on_db(db_path, query_text)
    logger.info("[%s] SQL returned %d rows", query_id, len(rows))
    return rows, table_map


# ---------------------------------------------------------------------------
# Result I/O
# ---------------------------------------------------------------------------

def save_rows_csv(rows: List[Dict[str, Any]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with out_csv.open("w", newline="") as f:
            csv.writer(f).writerow(["_empty"])
        return
    cols: List[str] = []
    for row in rows:
        for k in row:
            if k not in cols:
                cols.append(k)
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Metrics dataclass
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main benchmark loop
# ---------------------------------------------------------------------------

def run_trend_queries_doctopus(run_dir: Path) -> List[TrendQueryMetrics]:
    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    plots_dir = run_dir / "plots"
    query_eval_db_dir = run_dir / "query_eval_dbs"

    for d in [run_dir, query_results_dir, query_tables_dir, plots_dir, query_eval_db_dir]:
        d.mkdir(parents=True, exist_ok=True)

    patch_ollama_for_token_tracking()

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
        logger.info("Executing %s with Doctopus", query_id)
        nl_query = NL_QUERY_SPECS.get(query_id, query_text)
        logger.info("[NL] %s", nl_query)

        before = _TRACKER.snapshot()
        t0 = time.time()

        try:
            rows, query_table_map = execute_query(query_id, query_text, query_eval_db_dir)
            latency = time.time() - t0
            d_prompt, d_completion = _TRACKER.delta(before)
            d_total = d_prompt + d_completion

            # Persist result rows
            out_csv = query_tables_dir / f"{query_id}.csv"
            out_json = query_tables_dir / f"{query_id}.json"
            save_rows_csv(rows, out_csv)
            out_json.write_text(json.dumps(rows, indent=2, default=str))

            # Official evaluation
            identity_col = _infer_identity_col_for_query(query_text, IDENTITY_COLUMNS)
            eval_out = evaluate_with_official_framework(
                query_text,
                rows,
                gt_runner=eval_gt_runner,
                sql_parser=eval_sql_parser,
                row_matcher=eval_row_matcher,
                settings=eval_settings,
                attributes=eval_attributes,
                identity_col=identity_col,
                phase2_db=query_eval_db_dir / f"{query_id}.db",
                output_dir=query_results_dir / query_id,
            )

            item = TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                nl_query=nl_query,
                success=True,
                delta_type="DOCTOPUS_EXTRACT_SQL",
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

            # Write acc.json
            acc_path = query_results_dir / query_id / "acc.json"
            acc_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                acc_data: Dict[str, Any] = {}
                if acc_path.exists():
                    acc_data = json.loads(acc_path.read_text())
                acc_data.update(
                    {
                        "query_id": query_id,
                        "latency_s": round(latency, 4),
                        "prompt_tokens": d_prompt,
                        "completion_tokens": d_completion,
                        "total_tokens": d_total,
                        "result_rows": len(rows),
                        "success": True,
                    }
                )
                acc_data.setdefault("macro_f1", eval_out.get("macro_f1", 0.0))
                acc_data.setdefault("macro_precision", eval_out.get("macro_precision", 0.0))
                acc_data.setdefault("macro_recall", eval_out.get("macro_recall", 0.0))
                acc_path.write_text(json.dumps(acc_data, indent=2))
            except Exception as acc_err:
                logger.warning("Could not write %s: %s", acc_path, acc_err)

            logger.info(
                "%s: rows=%d latency=%.3fs tokens=%d F1=%.3f",
                query_id, len(rows), latency, d_total, item.macro_f1,
            )

        except Exception as exc:
            latency = time.time() - t0
            d_prompt, d_completion = _TRACKER.delta(before)
            d_total = d_prompt + d_completion

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
            # Write acc.json for failed query too
            acc_path = query_results_dir / query_id / "acc.json"
            acc_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                acc_path.write_text(
                    json.dumps(
                        {
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
                        },
                        indent=2,
                    )
                )
            except Exception as acc_err:
                logger.warning("Could not write %s: %s", acc_path, acc_err)
            logger.exception("%s failed: %s", query_id, exc)

    return metrics


# ---------------------------------------------------------------------------
# Save + plot
# ---------------------------------------------------------------------------

def save_metrics(metrics: List[TrendQueryMetrics], run_dir: Path) -> None:
    rows = [asdict(m) for m in metrics]
    out_json = run_dir / "trend_metrics.json"
    out_csv = run_dir / "trend_metrics.csv"
    out_json.write_text(json.dumps(rows, indent=2))
    if rows:
        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    logger.info("Saved metrics JSON: %s", out_json)
    logger.info("Saved metrics CSV:  %s", out_csv)


def plot_metrics(metrics: List[TrendQueryMetrics], run_dir: Path) -> None:
    if not MATPLOTLIB_AVAILABLE or not metrics:
        logger.warning("matplotlib unavailable or no metrics – skipping plots")
        return

    plots_dir = run_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    ordered = sorted(metrics, key=lambda m: int(m.query_id[1:]))
    x_labels = [m.query_id for m in ordered]
    x = list(range(len(x_labels)))

    result_rows = [m.result_rows for m in ordered]
    token_cost = [m.total_tokens for m in ordered]
    latency = [m.latency_s for m in ordered]
    f1 = [m.macro_f1 for m in ordered]
    precision = [m.macro_precision for m in ordered]
    recall = [m.macro_recall for m in ordered]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "Player Query-Awareness Trend with Doctopus (Q1..Q10)",
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
    summary_plot = plots_dir / "query_awareness_trend_summary.png"
    plt.savefig(summary_plot, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved summary plot: %s", summary_plot)

    # Precision / Recall / F1 line chart
    fig2, ax2 = plt.subplots(figsize=(12, 5))
    ax2.plot(x, precision, marker="o", label="Precision")
    ax2.plot(x, recall, marker="o", label="Recall")
    ax2.plot(x, f1, marker="o", label="F1")
    ax2.set_xticks(x)
    ax2.set_xticklabels(x_labels)
    ax2.set_ylim(0.0, 1.0)
    ax2.set_title("Macro Precision / Recall / F1 by Query")
    ax2.set_ylabel("score")
    ax2.grid(alpha=0.3)
    ax2.legend()
    plt.tight_layout()
    prf_plot = plots_dir / "query_awareness_trend_prf.png"
    plt.savefig(prf_plot, dpi=300, bbox_inches="tight")
    plt.close(fig2)
    logger.info("Saved PRF plot: %s", prf_plot)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ensure_precise_tokenizer_ready()

    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    run_tag = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_BASE_DIR / f"run_{run_tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(run_dir / "query_awareness_trend_doctopus.log")

    logger.info("Starting Player query-awareness trend test (Doctopus)...")
    logger.info("Run directory: %s", run_dir)
    logger.info("Trend SQL: %s", TREND_SQL_FILE)
    logger.info("Source data: %s", SOURCE_DATA_DIR)
    logger.info("Model: %s @ %s (unlimited token budget)", MODEL, OLLAMA_BASE_URL)

    try:
        metrics = run_trend_queries_doctopus(run_dir)
        save_metrics(metrics, run_dir)
        plot_metrics(metrics, run_dir)

        success_count = sum(1 for m in metrics if m.success)
        avg_f1 = sum(m.macro_f1 for m in metrics) / len(metrics) if metrics else 0.0
        if not math.isfinite(avg_f1):
            avg_f1 = 0.0

        logger.info("=" * 80)
        logger.info(
            "Completed: %d/%d queries succeeded, avg macro F1=%.3f",
            success_count, len(metrics), avg_f1,
        )
        token_summary = GLOBAL_COUNTER.summary_str()
        logger.info(token_summary)
        token_json_path = run_dir / "token_cost.json"
        GLOBAL_COUNTER.save_json(token_json_path)
        logger.info("Token cost JSON: %s", token_json_path)
        logger.info("All outputs under: %s", run_dir)
        logger.info("=" * 80)
        return 0
    except Exception as exc:
        logger.exception("Doctopus trend test failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

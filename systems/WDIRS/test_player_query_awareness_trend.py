"""
Run Q1..Q10 query-awareness trend evaluation on Player.

What this script does:
1) Snapshot previously created artifacts (DB/cache/extractions) once, if absent.
2) Execute Q1..Q10 trend queries on a working copy of the snapshot DB.
3) Save per-query result tables and metrics (latency, token counts, macro F1/P/R).
4) Generate plots with Q1..Q10 on the x-axis.
"""

import csv
import json
import logging
import re
import shutil
import sqlite3
import sys
import time
import argparse
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

import pandas as pd
import sqlglot
import sqlglot.expressions as _sqlglot_exp

# Add systems/WDIRS to path
sys.path.insert(0, str(Path(__file__).parent))

from extractor import OllamaClient
from wdirs_runner import WDIRSRunner
from config import (
    CACHE_DIR,
    DB_DIR,
    PROJECT_ROOT,
    QUERY_DIR,
    RESULTS_DIR,
)

sys.path.insert(0, str(PROJECT_ROOT))
from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.metrics import MetricCalculator as _MetricCalculator
from evaluation.query_manifest import QueryManifest as _QueryManifest
from evaluation.result_writer import ResultWriter as _ResultWriter
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

logger = logging.getLogger(__name__)

DATASET = "Player"
DATASET_QUERY = "Player"
TREND_SQL_FILE = QUERY_DIR / DATASET_QUERY / "query_aware_trend_queries.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend"
SNAPSHOT_DIR = RESULTS_BASE_DIR / "snapshot"
RUN_DIR = RESULTS_BASE_DIR / "run"
QUERY_RESULTS_DIR = RUN_DIR / "query_results"
QUERY_TABLES_DIR = RUN_DIR / "query_tables"
PLOTS_DIR = RUN_DIR / "plots"

_ENTITY_SUFFIX_RE = re.compile(r"\b(jr\.?|sr\.?|iii|iv|ii)\b\.?", re.IGNORECASE)


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
    """Tracks LLM token usage across calls in this process."""

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


def _approx_tokens(text: Optional[str]) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def patch_ollama_for_token_tracking(token_tracker: TokenTracker) -> None:
    """
    Monkey-patch OllamaClient.generate for per-query token tracking.
    Uses conservative token estimation from prompt/response text length.
    """
    original_generate = OllamaClient.generate

    def wrapped_generate(self, prompt: str, max_tokens: int = 0, temperature: float = 0.0, system_prompt: Optional[str] = None) -> str:  # noqa: ANN001
        result = original_generate(self, prompt, max_tokens=max_tokens, temperature=temperature, system_prompt=system_prompt)
        p_tok = _approx_tokens(prompt) + _approx_tokens(system_prompt)
        c_tok = _approx_tokens(result)
        token_tracker.add(p_tok, c_tok)
        return result

    OllamaClient.generate = wrapped_generate


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


def _norm_key(val: Any) -> str:
    s = " ".join(str(val).strip().lower().split())
    s = _ENTITY_SUFFIX_RE.sub("", s)
    s = re.sub(r"[,\.\(\)]", "", s)
    return " ".join(s.split())


def _normalize_key_cols(df: "pd.DataFrame", key_cols: List[str]) -> "pd.DataFrame":
    out = df.copy()
    for col in key_cols:
        if col in out.columns:
            out[col] = out[col].apply(lambda v: _norm_key(v) if pd.notna(v) else "")
    return out


def _resolve_primary_keys_for_alignment(
    primary_keys: List[str],
    gold_df: "pd.DataFrame",
    pred_df: "pd.DataFrame",
) -> List[str]:
    """
    Resolve evaluator key names against actual DataFrame columns.

    sql_parser may return qualified keys (e.g., "city.state_name"), while
    result DataFrames commonly contain unqualified columns ("state_name").
    """
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

    return resolved or primary_keys


def _augment_sql_with_entity(sql: str, entity_col: str, dialect: str = "duckdb") -> Optional[str]:
    try:
        parsed = sqlglot.parse_one(sql, error_level="ignore")
    except Exception:
        return None
    if parsed.find(_sqlglot_exp.Star):
        return None
    if parsed.args.get("group"):
        return None
    existing = {
        c.name.lower()
        for c in parsed.find_all(_sqlglot_exp.Column)
        if isinstance(c.parent, _sqlglot_exp.Select)
    }
    if entity_col.lower() in existing:
        return None
    parsed = parsed.select(_sqlglot_exp.column(entity_col))
    return parsed.sql(dialect=dialect)


def _fetch_wdirs_with_entity(wdirs_db: Path, sql: str, entity_col: str) -> Optional[List[Dict[str, Any]]]:
    aug = _augment_sql_with_entity(sql, entity_col, dialect="sqlite")
    if aug is None:
        return None
    try:
        con = sqlite3.connect(str(wdirs_db))
        con.row_factory = sqlite3.Row
        cur = con.execute(aug)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        con.close()
        return rows
    except Exception as exc:
        logger.warning(f"[Eval] Augmented WDIRS query failed: {exc}")
        return None


def _build_pred_df(
    wdirs_rows: List[Dict[str, Any]],
    expected_columns: List[str],
    stop_columns: List[str],
    attributes: Dict[str, Any],
) -> "pd.DataFrame":
    df = pd.DataFrame(wdirs_rows) if wdirs_rows else pd.DataFrame(columns=expected_columns)
    df = _drop_unnamed(df)
    df = df.rename(columns={c: _std_col(c) for c in df.columns})
    df = _norm_file_cols(df)
    df = _add_missing_cols(df, expected_columns)
    df = _add_missing_cols(df, stop_columns)
    df = _clean_string_cols(df)
    df = _norm_types(df, attributes)
    return df


def evaluate_with_official_framework(
    sql: str,
    wdirs_rows: List[Dict[str, Any]],
    *,
    gt_runner: "_GtRunner",
    sql_parser: "_SqlParser",
    row_matcher: "_RowMatcher",
    settings: "_EvalSettings",
    attributes: Dict[str, Any],
    identity_col: Optional[str],
    phase2_db: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    parsed = sql_parser.parse(sql)
    is_agg = parsed.query_type == "aggregation"
    entity = identity_col or "name"

    if is_agg:
        gt_sql = sql
        effective_wdirs = wdirs_rows
        primary_keys = parsed.primary_keys
    else:
        aug_gt = _augment_sql_with_entity(sql, entity, dialect="duckdb")
        gt_sql = aug_gt if aug_gt else sql
        wdirs_cols = {k.lower() for k in (wdirs_rows[0].keys() if wdirs_rows else {})}
        if entity.lower() not in wdirs_cols and phase2_db.exists():
            aug_wdirs = _fetch_wdirs_with_entity(phase2_db, sql, entity)
            effective_wdirs = aug_wdirs if aug_wdirs is not None else wdirs_rows
        else:
            effective_wdirs = wdirs_rows
        primary_keys = [entity]

    gold_df = gt_runner.run(gt_sql)
    if not is_agg and entity not in gold_df.columns:
        primary_keys = parsed.primary_keys

    manifest_for_pred = _QueryManifest(gt_sql, sql_parser.parse(gt_sql), attributes)
    pred_df = _build_pred_df(
        effective_wdirs,
        expected_columns=list(gold_df.columns),
        stop_columns=manifest_for_pred.stop_columns,
        attributes=attributes,
    )

    primary_keys = _resolve_primary_keys_for_alignment(primary_keys, gold_df, pred_df)

    gold_norm = _normalize_key_cols(gold_df, primary_keys)
    pred_norm = _normalize_key_cols(pred_df, primary_keys)

    try:
        match_result = row_matcher.match(
            gold_df=gold_norm,
            pred_df=pred_norm,
            primary_keys=primary_keys,
            attr_descriptions=attributes,
            query_type=parsed.query_type,
        )
    except KeyError as ke:
        logger.warning(f"[Eval] RowMatcher key error ({ke}) — returning zero metrics")
        return {
            "macro_f1": 0.0,
            "macro_precision": 0.0,
            "macro_recall": 0.0,
            "is_agg": is_agg,
            "gt_result_count": len(gold_df),
            "matched_rows": 0,
        }

    calc = _MetricCalculator(manifest_for_pred, settings)
    metrics = calc.compute(match_result)
    macro_f1 = metrics.get("macro_f1", 0.0)
    macro_precision = metrics.get("macro_precision", 0.0)
    macro_recall = metrics.get("macro_recall", 0.0)
    if not math.isfinite(macro_f1):
        macro_f1 = 0.0
    if not math.isfinite(macro_precision):
        macro_precision = 0.0
    if not math.isfinite(macro_recall):
        macro_recall = 0.0

    try:
        writer = _ResultWriter(output_dir=output_dir)
        writer.write(gold_df, match_result.gold_aligned, match_result.pred_aligned, metrics)
    except Exception as we:
        logger.warning(f"[Eval] Could not write per-query outputs: {we}")

    return {
        "macro_f1": macro_f1,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "is_agg": is_agg,
        "gt_result_count": len(gold_df),
        "matched_rows": match_result.matched_rows,
    }


def collect_training_workload(dataset_query: str) -> List[str]:
    """Collect all training queries used to restore lattice state."""
    all_queries: List[str] = []
    base = QUERY_DIR / dataset_query

    def _load(path: Path) -> None:
        if not path.exists():
            return
        txt = path.read_text()
        parts = re.split(r"-- (?:Inspiration: )?Query ", txt)
        for part in parts[1:]:
            lines = part.strip().split("\n")
            if not lines:
                continue
            sql_text = "\n".join(lines[1:]).strip()
            while sql_text and sql_text.split("\n")[0].strip().startswith("--"):
                sql_text = "\n".join(sql_text.split("\n")[1:]).strip()
            if sql_text:
                all_queries.append(sql_text)

    _load(base / "Agg" / "agg_queries.sql")
    for query_type in ["Filter", "Select", "Mixed"]:
        type_dir = base / query_type
        if type_dir.exists():
            for sql_file in sorted(type_dir.glob("*.sql")):
                _load(sql_file)
    _load(base / "Join" / "join_queries.sql")
    return all_queries


def parse_trend_queries(sql_file: Path) -> List[Tuple[str, str]]:
    """Parse Q1..Q10 from query_aware_trend_queries.sql."""
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

        sql = "\n".join(sql_lines).strip()
        if sql and not sql.endswith(";"):
            sql += ";"
        if sql:
            queries.append((qid, sql))

    queries.sort(key=lambda x: int(x[0][1:]))
    return queries


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


def _first_existing(paths: List[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None


def ensure_snapshot_artifacts(refresh_snapshot: bool = False) -> Tuple[Path, Optional[Path]]:
    """
    Ensure snapshot copies exist for:
    - DB file
    - cache directory
    - extraction cache directory
    Returns (snapshot_db_path, snapshot_identity_columns_path_or_none)
    """
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Prefer the full Player workload checkpoint first.
    source_db_candidates = [
        RESULTS_DIR / "player_workload_test" / "checkpoint" / "Player_preprocessed.db",
        Path(__file__).parent / "wdirs-2.db",
        DB_DIR / "wdirs.db",
        Path(__file__).parent / "wdirs-owner-only.db",
    ]
    source_db = _first_existing(source_db_candidates)
    if source_db is None:
        raise FileNotFoundError(
            "No source DB found. Checked: "
            + ", ".join(str(p) for p in source_db_candidates)
        )

    snapshot_db = SNAPSHOT_DIR / "player_snapshot.db"
    if refresh_snapshot and snapshot_db.exists():
        snapshot_db.unlink()
        logger.info(f"Removed existing snapshot DB (refresh): {snapshot_db}")
    if snapshot_db.exists():
        logger.info(f"Snapshot DB already exists: {snapshot_db}")
    else:
        shutil.copy2(source_db, snapshot_db)
        logger.info(f"Created snapshot DB: {snapshot_db} (from {source_db})")

    source_cache = CACHE_DIR
    snapshot_cache = SNAPSHOT_DIR / "cache_snapshot"
    if snapshot_cache.exists():
        logger.info(f"Snapshot cache already exists: {snapshot_cache}")
    elif source_cache.exists():
        shutil.copytree(source_cache, snapshot_cache)
        logger.info(f"Created snapshot cache: {snapshot_cache}")
    else:
        logger.warning(f"Cache dir not found, skipping copy: {source_cache}")

    source_extractions = CACHE_DIR / "extractions"
    snapshot_extractions = SNAPSHOT_DIR / "extractions_snapshot"
    if snapshot_extractions.exists():
        logger.info(f"Snapshot extraction cache already exists: {snapshot_extractions}")
    elif source_extractions.exists():
        shutil.copytree(source_extractions, snapshot_extractions)
        logger.info(f"Created snapshot extraction cache: {snapshot_extractions}")
    else:
        logger.warning(f"Extraction cache dir not found, skipping copy: {source_extractions}")

    identity_candidates = [
        RESULTS_DIR / "player_workload_test" / "checkpoint" / "Player_identity_columns.json",
        RESULTS_DIR / "player_workload_test" / "checkpoint" / "player_identity_columns.json",
    ]
    source_identity = _first_existing(identity_candidates)
    snapshot_identity = SNAPSHOT_DIR / "Player_identity_columns.json"
    if source_identity and not snapshot_identity.exists():
        shutil.copy2(source_identity, snapshot_identity)
        logger.info(f"Created snapshot identity file: {snapshot_identity}")
    elif snapshot_identity.exists():
        logger.info(f"Snapshot identity file already exists: {snapshot_identity}")

    return snapshot_db, (snapshot_identity if snapshot_identity.exists() else None)


def _infer_identity_col_for_query(sql: str, identity_columns: Dict[str, str]) -> Optional[str]:
    """
    Pick identity column based on first table in FROM clause.
    Falls back to player/name if unknown.
    """
    try:
        parsed = sqlglot.parse_one(sql, error_level="ignore")
        first_table = None
        for t in parsed.find_all(sqlglot.expressions.Table):
            first_table = t.name
            break
        if first_table:
            if first_table in identity_columns:
                return identity_columns[first_table]
            lc_map = {k.lower(): v for k, v in identity_columns.items()}
            if first_table.lower() in lc_map:
                return lc_map[first_table.lower()]
    except Exception:
        pass
    return identity_columns.get("player", "name")


def run_trend_queries(snapshot_db: Path, identity_file: Optional[Path]) -> List[TrendQueryMetrics]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    QUERY_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    QUERY_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    working_db = RUN_DIR / "player_trend_working.db"
    shutil.copy2(snapshot_db, working_db)
    logger.info(f"Working DB copied from snapshot: {working_db}")

    identity_columns: Dict[str, str] = {}
    if identity_file and identity_file.exists():
        identity_columns = json.loads(identity_file.read_text())
        logger.info(f"Loaded identity columns: {identity_columns}")
    else:
        logger.warning("No identity columns file found; fallback identity rules will be used.")

    token_tracker = TokenTracker()
    patch_ollama_for_token_tracking(token_tracker)

    runner = WDIRSRunner(dataset=DATASET, postgres_uri=f"sqlite:///{working_db}")
    training_queries = collect_training_workload(DATASET_QUERY)
    if training_queries:
        runner.restore_lattice(training_queries)
        logger.info(f"Restored lattice with {len(training_queries)} training queries.")
    if identity_columns:
        runner.identity_columns.update(identity_columns)
        runner.delta_engine.identity_columns = runner.identity_columns

    eval_attributes: Dict[str, Any] = _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
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
        logger.info(f"Executing {query_id}")
        before = token_tracker.snapshot()
        t0 = time.time()

        try:
            result = runner.execute_query(query_text)
            latency = time.time() - t0
            d_prompt, d_completion = token_tracker.delta(before)
            d_total = d_prompt + d_completion

            out_csv = QUERY_TABLES_DIR / f"{query_id}.csv"
            out_json = QUERY_TABLES_DIR / f"{query_id}.json"
            _save_rows_csv(result.results, out_csv)
            out_json.write_text(json.dumps(result.results, indent=2, default=str))

            eval_out: Dict[str, Any] = {}
            if result.success:
                eval_out = evaluate_with_official_framework(
                    query_text,
                    result.results,
                    gt_runner=eval_gt_runner,
                    sql_parser=eval_sql_parser,
                    row_matcher=eval_row_matcher,
                    settings=eval_settings,
                    attributes=eval_attributes,
                    identity_col=_infer_identity_col_for_query(query_text, identity_columns),
                    phase2_db=working_db,
                    output_dir=QUERY_RESULTS_DIR / query_id,
                )

            item = TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                success=result.success,
                delta_type=result.delta_type,
                latency_s=latency,
                result_rows=len(result.results),
                prompt_tokens=d_prompt,
                completion_tokens=d_completion,
                total_tokens=d_total,
                macro_f1=eval_out.get("macro_f1", 0.0),
                macro_precision=eval_out.get("macro_precision", 0.0),
                macro_recall=eval_out.get("macro_recall", 0.0),
                gt_result_count=eval_out.get("gt_result_count", 0),
                matched_rows=eval_out.get("matched_rows", 0),
                is_agg=eval_out.get("is_agg", False),
                error=result.error if not result.success else None,
            )
            metrics.append(item)
            logger.info(
                f"{query_id}: success={item.success} rows={item.result_rows} "
                f"latency={item.latency_s:.3f}s tokens={item.total_tokens} "
                f"F1={item.macro_f1:.3f}"
            )
        except Exception as exc:
            latency = time.time() - t0
            d_prompt, d_completion = token_tracker.delta(before)
            metrics.append(
                TrendQueryMetrics(
                    query_id=query_id,
                    query_text=query_text,
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
    fig.suptitle("Player Query-Awareness Trend (Q1..Q10)", fontsize=16, fontweight="bold")

    axes[0, 0].plot(x, result_rows, marker="o", color="#7f8c8d")
    axes[0, 0].set_title("Result Table Size (rows)")
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels(x_labels)
    axes[0, 0].set_ylabel("rows")
    axes[0, 0].grid(alpha=0.3)

    axes[0, 1].plot(x, token_cost, marker="o", color="#8e44ad")
    axes[0, 1].set_title("Token Cost (estimated total tokens)")
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

    # Separate detailed F1/P/R plot
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
    prf_plot = PLOTS_DIR / "query_awareness_trend_prf.png"
    plt.savefig(prf_plot, dpi=300, bbox_inches="tight")
    plt.close(fig2)
    logger.info(f"Saved trend PRF plot: {prf_plot}")


def main() -> int:
    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    setup_logging(RESULTS_BASE_DIR / "query_awareness_trend.log")
    ap = argparse.ArgumentParser(description="Run Player query-awareness trend test")
    ap.add_argument(
        "--refresh-snapshot",
        action="store_true",
        help="Recreate snapshot DB from preferred source before running",
    )
    args = ap.parse_args()

    logger.info("Starting Player query-awareness trend test...")
    logger.info(f"Trend query source: {TREND_SQL_FILE}")

    try:
        snapshot_db, identity_file = ensure_snapshot_artifacts(refresh_snapshot=args.refresh_snapshot)
        metrics = run_trend_queries(snapshot_db, identity_file)
        save_metrics(metrics)
        plot_metrics(metrics)

        success_count = sum(1 for m in metrics if m.success)
        avg_f1 = sum(m.macro_f1 for m in metrics) / len(metrics) if metrics else 0.0
        logger.info("=" * 80)
        logger.info(
            f"Completed: {success_count}/{len(metrics)} queries succeeded, "
            f"avg macro F1={avg_f1:.3f}"
        )
        logger.info(f"Outputs under: {RUN_DIR}")
        logger.info("=" * 80)
        return 0
    except Exception as exc:
        logger.exception(f"Trend test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

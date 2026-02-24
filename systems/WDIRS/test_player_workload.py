"""
Comprehensive test script for WDIRS system with Player workload.
Orchestrates preprocessing with training queries and validates with test queries.

Phase 1: Preprocessing with Training Workload
  - Workload: Agg, Filter, Select, Mixed, and Join queries from Query/Player/
  - Output: Serialized database + metadata checkpoint in results/

Phase 2: Testing with Test Workload
  - Test Queries: Subsample and Variations
  - Validates: Row/Column Delta execution, query correctness, and performance
"""

import json
import logging
import sys
import time
from pathlib import Path
from dataclasses import asdict, dataclass
from typing import List, Dict, Any, Optional, Tuple
import shutil

# Try to import matplotlib for chart generation
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Add systems/WDIRS to path
sys.path.insert(0, str(Path(__file__).parent))

from data_layer import DataLayer
from wdirs_runner import WDIRSRunner, PreprocessingResult, QueryResult
from config import (
    PROJECT_ROOT, QUERY_DIR, SOURCE_DATA_DIR, RESULTS_DIR,
    DB_DIR, MAX_PARALLEL_REQUESTS
)

# ============================================================================
# Configuration
# ============================================================================

logger = logging.getLogger(__name__)

DATASET = "Player"               # Source data directory name
DATASET_QUERY = "Player"         # Query directory name
GT_TABLE_NAME = "player"         # Primary table name for identity column resolution
TRAINING_QUERY_TYPES = ["Agg", "Filter", "Select", "Mixed", "Join"]
TEST_QUERY_TYPES = ["Subsample", "Variations"]
RESULTS_BASE_DIR = RESULTS_DIR / "player_workload_test"
CHECKPOINT_DIR = RESULTS_BASE_DIR / "checkpoint"

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class TestQueryMetrics:
    """Metrics for a single test query."""
    query_id: str
    query_text: str
    query_type: str
    success: bool
    results_count: int
    delta_type: str
    execution_time: float
    error: Optional[str] = None
    # Official UDA-Bench evaluation metrics (macro-averaged over projected columns)
    macro_f1: float = 0.0
    macro_precision: float = 0.0
    macro_recall: float = 0.0
    gt_result_count: int = 0
    matched_rows: int = 0
    is_agg: bool = False

# ============================================================================
# Helper Functions
# ============================================================================

# ============================================================================
# Official UDA-Bench Evaluation Integration
# ============================================================================

import re as _re
import sqlite3 as _sqlite3
import sys as _sys
import sqlglot
import sqlglot.expressions as _sqlglot_exp
import pandas as pd

_sys.path.insert(0, str(PROJECT_ROOT))  # make the top-level "evaluation" package importable

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

# Paths for the official evaluator (Player has multiple GT tables: player, team, city, manager)
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"

# Primary entity column for the main table (player)
GT_ENTITY_COL = "name"

# Optional: strip common suffixes when normalizing entity keys (e.g. "Jr." for player names)
_ENTITY_SUFFIX_RE = _re.compile(
    r"\b(jr\.?|sr\.?|iii|iv|ii)\b\.?",
    _re.IGNORECASE,
)


def _norm_key(val: Any) -> str:
    """Lowercase, optionally strip suffixes, collapse whitespace — used for key normalization."""
    s = " ".join(str(val).strip().lower().split())
    s = _ENTITY_SUFFIX_RE.sub("", s)
    s = _re.sub(r"[,\.\(\)]", "", s)
    return " ".join(s.split())


def _normalize_key_cols(df: "pd.DataFrame", key_cols: List[str]) -> "pd.DataFrame":
    """
    Apply entity-style normalization to key columns for row alignment.
    """
    df = df.copy()
    for col in key_cols:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: _norm_key(v) if pd.notna(v) else "")
    return df


def _augment_sql_with_entity(sql: str, entity_col: str, dialect: str = "duckdb") -> Optional[str]:
    """
    Rewrite a SELECT query to also fetch *entity_col* when it is absent from the
    projection.  Returns None when no rewrite is needed (already present / SELECT *
    / aggregation).
    """
    try:
        parsed = sqlglot.parse_one(sql, error_level="ignore")
    except Exception:
        return None
    if parsed.find(_sqlglot_exp.Star):
        return None
    if parsed.args.get("group"):
        return None  # aggregation — don't touch
    existing = {
        c.name.lower()
        for c in parsed.find_all(_sqlglot_exp.Column)
        if isinstance(c.parent, _sqlglot_exp.Select)
    }
    if entity_col.lower() in existing:
        return None
    parsed = parsed.select(_sqlglot_exp.column(entity_col))
    return parsed.sql(dialect=dialect)


def _fetch_wdirs_with_entity(wdirs_db: Path, sql: str, entity_col: str) -> Optional[List[Dict]]:
    """Query the phase-2 WDIRS SQLite DB with entity_col injected into the SELECT."""
    aug = _augment_sql_with_entity(sql, entity_col, dialect="sqlite")
    if aug is None:
        return None
    try:
        con = _sqlite3.connect(str(wdirs_db))
        con.row_factory = _sqlite3.Row
        cur = con.execute(aug)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        con.close()
        return rows
    except Exception as exc:
        logger.warning(f"[Eval] Augmented WDIRS query failed: {exc}")
        return None


def _build_pred_df(
    wdirs_rows: List[Dict],
    expected_columns: List[str],
    stop_columns: List[str],
    attributes: Dict,
) -> "pd.DataFrame":
    """
    Convert WDIRS result rows to a normalized DataFrame that mirrors what
    ResultLoader would produce if it read a CSV file.
    """
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
    wdirs_rows: List[Dict],
    *,
    gt_runner: "_GtRunner",
    sql_parser: "_SqlParser",
    row_matcher: "_RowMatcher",
    settings: "_EvalSettings",
    attributes: Dict,
    identity_col: Optional[str],
    phase2_db: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    """
    Evaluate one WDIRS query result against the official UDA-Bench evaluation
    framework.

    Returns a dict with keys:
        macro_f1, macro_precision, macro_recall, is_agg,
        column_metrics, gt_result_count, matched_rows, gt_results.
    """
    parsed = sql_parser.parse(sql)
    is_agg = (parsed.query_type == "aggregation")
    entity = identity_col or GT_ENTITY_COL

    # ── Ground-truth ─────────────────────────────────────────────────────────
    if is_agg:
        gt_sql = sql
        effective_wdirs = wdirs_rows
        primary_keys = parsed.primary_keys  # GROUP BY cols
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

    # ── Prediction DataFrame ──────────────────────────────────────────────────
    manifest_for_pred = _QueryManifest(gt_sql, sql_parser.parse(gt_sql), attributes)
    pred_df = _build_pred_df(
        effective_wdirs,
        expected_columns=list(gold_df.columns),
        stop_columns=manifest_for_pred.stop_columns,
        attributes=attributes,
    )

    gold_norm = _normalize_key_cols(gold_df, primary_keys)
    pred_norm = _normalize_key_cols(pred_df, primary_keys)

    # ── Row alignment ─────────────────────────────────────────────────────────
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
            "macro_f1": 0.0, "macro_precision": 0.0, "macro_recall": 0.0,
            "is_agg": is_agg, "column_metrics": {},
            "gt_result_count": len(gold_df), "gt_results": gold_df.to_dict("records"),
            "matched_rows": 0,
        }

    calc = _MetricCalculator(manifest_for_pred, settings)
    metrics = calc.compute(match_result)

    try:
        writer = _ResultWriter(output_dir=output_dir)
        writer.write(gold_df, match_result.gold_aligned, match_result.pred_aligned, metrics)
    except Exception as we:
        logger.warning(f"[Eval] Could not write per-query outputs: {we}")

    return {
        "macro_f1": metrics["macro_f1"],
        "macro_precision": metrics["macro_precision"],
        "macro_recall": metrics["macro_recall"],
        "is_agg": is_agg,
        "column_metrics": metrics.get("columns", {}),
        "gt_result_count": len(gold_df),
        "gt_results": gold_df.to_dict("records"),
        "matched_rows": match_result.matched_rows,
    }


def setup_logging(log_file: Path) -> None:
    """Configure logging to file and console."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler_file = logging.FileHandler(log_file)
    handler_console = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler_file.setFormatter(formatter)
    handler_console.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler_file)
    root_logger.addHandler(handler_console)


def load_sql_queries(sql_file: Path) -> List[Tuple[str, str]]:
    """
    Parse SQL file and extract query ID and query text.
    Supports both "Query N: ..." and "Inspiration: Query N ..." (Variations) style.
    Returns list of (query_id, query_text) tuples.
    """
    queries = []
    try:
        with open(sql_file, 'r') as f:
            content = f.read()
    except Exception as e:
        logger.warning(f"Could not read {sql_file}: {e}")
        return queries

    # Split by "-- Query " or "-- Inspiration: Query " so we get blocks that contain a query ID
    parts = _re.split(r'-- (?:Inspiration: )?Query ', content)

    for part in parts[1:]:
        lines = part.strip().split('\n')
        if not lines:
            continue
        query_id_line = lines[0]
        try:
            query_id = query_id_line.split(':')[0].split('(')[0].strip()
        except Exception:
            continue
        if not query_id or not query_id[0].isdigit():
            continue

        sql_text = '\n'.join(lines[1:]).strip()
        # Strip leading comment lines (for Variation-style: "-- Variation: ..." before the SELECT)
        while sql_text and sql_text.split('\n')[0].strip().startswith('--'):
            sql_text = '\n'.join(sql_text.split('\n')[1:]).strip()
        if sql_text:
            queries.append((f"Query_{query_id}", sql_text))

    return queries


def collect_training_workload(dataset_query: str) -> List[str]:
    """
    Collect all training queries from Agg, Filter, Select, Mixed, Join.
    Player has multiple SQL files per type (e.g. Select/*.sql, Filter/*.sql).
    Returns list of SQL query strings.
    """
    all_queries = []
    base = QUERY_DIR / dataset_query

    # Agg: single file
    agg_file = base / "Agg" / "agg_queries.sql"
    if agg_file.exists():
        logger.info(f"Loading training queries from {agg_file}")
        for qid, qtext in load_sql_queries(agg_file):
            all_queries.append(qtext)

    # Filter, Select, Mixed: all .sql in the type folder
    for query_type in ["Filter", "Select", "Mixed"]:
        type_dir = base / query_type
        if not type_dir.exists():
            continue
        for sql_file in sorted(type_dir.glob("*.sql")):
            logger.info(f"Loading training queries from {sql_file}")
            for qid, qtext in load_sql_queries(sql_file):
                all_queries.append(qtext)

    # Join: single file
    join_file = base / "Join" / "join_queries.sql"
    if join_file.exists():
        logger.info(f"Loading training queries from {join_file}")
        for qid, qtext in load_sql_queries(join_file):
            all_queries.append(qtext)

    logger.info(f"Total training queries collected: {len(all_queries)}")
    return all_queries


def collect_test_workload(dataset_query: str) -> Dict[str, List[Tuple[str, str]]]:
    """
    Collect all test queries from Subsample and Variations.
    Returns dict with test type as key, list of (query_id, query_text) as value.
    """
    test_queries = {}
    base = QUERY_DIR / dataset_query

    subsample_dir = base / "Subsample"
    if subsample_dir.exists():
        logger.info("Loading test queries from Subsample")
        subsample_queries = []
        for sql_file in sorted(subsample_dir.glob("*.sql")):
            subsample_queries.extend(load_sql_queries(sql_file))
        if subsample_queries:
            test_queries["Subsample"] = subsample_queries

    variations_dir = base / "Variations"
    if variations_dir.exists():
        logger.info("Loading test queries from Variations")
        variations_queries = []
        for sql_file in sorted(variations_dir.glob("**/*.sql")):
            variations_queries.extend(load_sql_queries(sql_file))
        if variations_queries:
            test_queries["Variations"] = variations_queries

    return test_queries


def verify_data_availability(dataset: str) -> bool:
    """Verify that source data and queries are available."""
    data_dir = SOURCE_DATA_DIR / dataset

    if not data_dir.exists():
        logger.error(f"Source data directory not found: {data_dir}")
        return False

    data_files = list(data_dir.glob("**/*.txt"))
    if not data_files:
        logger.error(f"No text files found in {data_dir}")
        return False

    logger.info(f"Found {len(data_files)} source documents in {data_dir}")
    return True


# ============================================================================
# Phase 1: Preprocessing
# ============================================================================

def run_preprocessing_phase(dataset: str, dataset_query: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Phase 1: Offline Relational Synthesis with Training Workload.
    """
    logger.info("=" * 80)
    logger.info("PHASE 1: OFFLINE RELATIONAL SYNTHESIS (Preprocessing)")
    logger.info("=" * 80)

    phase_start = time.time()
    stats = {
        "dataset": dataset,
        "dataset_query": dataset_query,
        "training_workload": TRAINING_QUERY_TYPES,
        "steps": {}
    }

    try:
        if not verify_data_availability(dataset):
            logger.error("Data verification failed")
            return False, stats

        logger.info(f"\nCollecting training queries from {TRAINING_QUERY_TYPES}")
        training_queries = collect_training_workload(dataset_query)

        if not training_queries:
            logger.error("No training queries collected!")
            return False, stats

        logger.info(f"Collected {len(training_queries)} training queries")

        logger.info(f"\nInitializing WDIRS Runner for {dataset}")
        runner = WDIRSRunner(dataset=dataset)

        logger.info("\nRunning unified preprocessing pipeline...")
        step_start = time.time()
        preprocessing_result = runner.preprocess(workload_queries=training_queries)
        step_time = time.time() - step_start

        if not preprocessing_result.success:
            logger.error(f"Preprocessing failed: {preprocessing_result.error}")
            stats["success"] = False
            stats["error"] = preprocessing_result.error
            stats["total_time"] = step_time
            return False, stats

        stats["steps"]["preprocessing"] = {
            "time": step_time,
            "tables_processed": len(preprocessing_result.tables_processed),
            "total_chunks": preprocessing_result.total_chunks,
            "total_records": preprocessing_result.total_records,
            "tables": preprocessing_result.tables_processed
        }
        logger.info(f"✓ Preprocessing complete in {step_time:.2f}s")
        logger.info(f"  - Tables: {preprocessing_result.tables_processed}")
        logger.info(f"  - Chunks: {preprocessing_result.total_chunks}")
        logger.info(f"  - Records: {preprocessing_result.total_records}")

        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint_path = CHECKPOINT_DIR / f"{dataset}_preprocessed.db"
        db_path = DB_DIR / "wdirs.db"
        if db_path.exists():
            shutil.copy2(db_path, checkpoint_path)
            logger.info(f"Saved checkpoint to {checkpoint_path}")
        else:
            logger.warning(f"Expected database not found at {db_path}")

        identity_file = CHECKPOINT_DIR / f"{dataset}_identity_columns.json"
        identity_payload = {
            table: col
            for table, col in runner.identity_columns.items()
        }
        with open(identity_file, "w") as _idf:
            json.dump(identity_payload, _idf, indent=2)
        logger.info(f"Saved identity column map to {identity_file}: {identity_payload}")

        stats_file = CHECKPOINT_DIR / f"{dataset}_preprocessing_stats.json"
        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)

        stats["steps"]["save_checkpoint"] = {
            "time": 0.0,
            "checkpoint_path": str(checkpoint_path)
        }
        if checkpoint_path.exists():
            stats["steps"]["save_checkpoint"]["checkpoint_size_mb"] = checkpoint_path.stat().st_size / (1024 * 1024)

        total_time = time.time() - phase_start
        stats["total_time"] = total_time
        stats["success"] = True

        logger.info("\n" + "=" * 80)
        logger.info(f"PHASE 1 COMPLETE - Total Time: {total_time:.2f}s")
        logger.info("=" * 80)

        return True, stats

    except Exception as e:
        logger.exception(f"Preprocessing phase failed: {e}")
        stats["success"] = False
        stats["error"] = str(e)
        stats["total_time"] = time.time() - phase_start
        return False, stats


# ============================================================================
# Phase 2: Testing
# ============================================================================

def run_test_phase(dataset: str, dataset_query: str, checkpoint_path: Path) -> Tuple[bool, List[TestQueryMetrics], Dict[str, Any]]:
    """
    Phase 2: Runtime Query Execution with Test Workload.
    """
    logger.info("=" * 80)
    logger.info("PHASE 2: RUNTIME EXECUTION (Testing)")
    logger.info("=" * 80)

    phase_start = time.time()
    test_metrics = []
    stats = {
        "dataset": dataset,
        "dataset_query": dataset_query,
        "test_workload": TEST_QUERY_TYPES,
        "checkpoint_path": str(checkpoint_path),
        "test_results": {}
    }

    try:
        if not checkpoint_path.exists():
            logger.error(f"Checkpoint not found at {checkpoint_path}")
            stats["success"] = False
            stats["error"] = "Checkpoint not found"
            stats["total_time"] = time.time() - phase_start
            return False, test_metrics, stats

        phase2_db = checkpoint_path.parent / f"{dataset}_phase2_working.db"
        shutil.copy2(checkpoint_path, phase2_db)
        logger.info(f"Phase 2 working DB: {phase2_db}")

        phase2_uri = f"sqlite:///{phase2_db}"
        runner = WDIRSRunner(dataset=dataset, postgres_uri=phase2_uri)

        logger.info("Restoring lattice from training workload...")
        training_queries_for_restore = collect_training_workload(dataset_query)
        if not training_queries_for_restore:
            logger.error("Cannot restore lattice: no training queries found")
            stats["success"] = False
            stats["error"] = "Lattice restore failed: no training queries"
            stats["total_time"] = time.time() - phase_start
            return False, test_metrics, stats
        runner.restore_lattice(training_queries_for_restore)
        logger.info("Lattice restored successfully")

        identity_file = CHECKPOINT_DIR / f"{dataset}_identity_columns.json"
        identity_columns: Dict[str, Optional[str]] = {}
        if identity_file.exists():
            with open(identity_file) as _idf:
                identity_columns = json.load(_idf)
        logger.info("=" * 60)
        logger.info("IDENTITY COLUMNS (primary entity attribute per table):")
        for _tbl, _icol in identity_columns.items():
            logger.info(f"  {_tbl}: {_icol!r}")
        logger.info("=" * 60)

        identity_col: Optional[str] = (
            identity_columns.get(GT_TABLE_NAME)
            or identity_columns.get(GT_TABLE_NAME.capitalize())
            or GT_ENTITY_COL
        )

        # Stage all Player GT CSVs (player, team, city, manager) for DuckDB
        gt_staging_dir = RESULTS_BASE_DIR / "gt_staging"
        gt_staging_dir.mkdir(parents=True, exist_ok=True)
        if GROUND_TRUTH_DIR.exists():
            for csv_path in GROUND_TRUTH_DIR.glob("*.csv"):
                dest = gt_staging_dir / csv_path.name
                shutil.copy2(csv_path, dest)
                logger.info(f"Staged GT CSV: {dest}")
        else:
            logger.warning(f"Ground truth directory not found: {GROUND_TRUTH_DIR}")

        eval_attributes: Dict = (
            _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
        )
        eval_settings = _EvalSettings(llm_provider="none")
        eval_gt_runner = _GtRunner(gt_dir=gt_staging_dir, attributes=eval_attributes)
        eval_sql_parser = _SqlParser()
        eval_row_matcher = _RowMatcher(settings=eval_settings)

        query_results_dir = RESULTS_BASE_DIR / "query_results"
        query_results_dir.mkdir(parents=True, exist_ok=True)

        test_queries = collect_test_workload(dataset_query)
        total_queries = sum(len(queries) for queries in test_queries.values())
        logger.info(f"Loaded {total_queries} test queries")

        if total_queries == 0:
            logger.warning("No test queries found!")
            stats["total_queries"] = 0
            stats["successful_queries"] = 0
            stats["failed_queries"] = 0
            stats["success_rate"] = 0.0
            stats["success"] = True
        else:
            successful_queries = 0
            failed_queries = 0

            for test_type, queries in test_queries.items():
                logger.info(f"\nExecuting {test_type} test queries ({len(queries)} queries)")
                stats["test_results"][test_type] = {
                    "total": len(queries),
                    "successful": 0,
                    "failed": 0,
                    "average_execution_time": 0.0
                }
                execution_times = []

                for query_id, query_text in queries:
                    query_start = time.time()
                    try:
                        result = runner.execute_query(query_text)
                        execution_time = time.time() - query_start
                        execution_times.append(execution_time)

                        eval_out: Dict[str, Any] = {}
                        if result.success:
                            try:
                                eval_out = evaluate_with_official_framework(
                                    query_text,
                                    result.results,
                                    gt_runner=eval_gt_runner,
                                    sql_parser=eval_sql_parser,
                                    row_matcher=eval_row_matcher,
                                    settings=eval_settings,
                                    attributes=eval_attributes,
                                    identity_col=identity_col,
                                    phase2_db=phase2_db,
                                    output_dir=query_results_dir / query_id,
                                )
                            except Exception as _fe:
                                logger.warning(f"  GT evaluation failed for {query_id}: {_fe}")

                        is_agg = eval_out.get("is_agg", False)
                        metric = TestQueryMetrics(
                            query_id=query_id,
                            query_text=query_text[:80] + "..." if len(query_text) > 80 else query_text,
                            query_type=test_type,
                            success=result.success,
                            results_count=len(result.results),
                            delta_type=result.delta_type,
                            execution_time=execution_time,
                            macro_f1=eval_out.get("macro_f1", 0.0),
                            macro_precision=eval_out.get("macro_precision", 0.0),
                            macro_recall=eval_out.get("macro_recall", 0.0),
                            gt_result_count=eval_out.get("gt_result_count", 0),
                            matched_rows=eval_out.get("matched_rows", 0),
                            is_agg=is_agg,
                        )

                        if result.success:
                            successful_queries += 1
                            stats["test_results"][test_type]["successful"] += 1
                            logger.info(
                                f"  ✓ {query_id}: {len(result.results)} rows "
                                f"(GT={eval_out.get('gt_result_count', '?')}, "
                                f"matched={eval_out.get('matched_rows', '?')}) "
                                f"in {execution_time:.3f}s | "
                                f"macro_F1={eval_out.get('macro_f1', 0):.3f}"
                            )
                        else:
                            failed_queries += 1
                            stats["test_results"][test_type]["failed"] += 1
                            metric.error = result.error
                            logger.warning(f"  ✗ {query_id}: {result.error}")

                        test_metrics.append(metric)

                    except Exception as e:
                        failed_queries += 1
                        stats["test_results"][test_type]["failed"] += 1
                        execution_time = time.time() - query_start
                        metric = TestQueryMetrics(
                            query_id=query_id,
                            query_text=query_text[:80] + "..." if len(query_text) > 80 else query_text,
                            query_type=test_type,
                            success=False,
                            results_count=0,
                            delta_type="ERROR",
                            execution_time=execution_time,
                            error=str(e)
                        )
                        test_metrics.append(metric)
                        logger.error(f"  ✗ {query_id}: Exception: {e}")

                if execution_times:
                    stats["test_results"][test_type]["average_execution_time"] = sum(execution_times) / len(execution_times)

            stats["total_queries"] = total_queries
            stats["successful_queries"] = successful_queries
            stats["failed_queries"] = failed_queries
            stats["success_rate"] = successful_queries / total_queries if total_queries > 0 else 0.0
            stats["success"] = True

            scored = [m for m in test_metrics if m.success]
            select_scored = [m for m in scored if not m.is_agg]
            agg_scored = [m for m in scored if m.is_agg]

            def _avg(lst):
                return sum(lst) / len(lst) if lst else 0.0

            f1_eval: Dict[str, Any] = {}
            if select_scored:
                f1_eval["select_filter"] = {
                    "macro_precision": _avg([m.macro_precision for m in select_scored]),
                    "macro_recall": _avg([m.macro_recall for m in select_scored]),
                    "macro_f1": _avg([m.macro_f1 for m in select_scored]),
                    "queries_scored": len(select_scored),
                }
            if agg_scored:
                f1_eval["aggregation"] = {
                    "macro_f1": _avg([m.macro_f1 for m in agg_scored]),
                    "queries_scored": len(agg_scored),
                }
            stats["f1_evaluation"] = f1_eval

        stats["total_time"] = time.time() - phase_start
        logger.info("\n" + "=" * 80)
        logger.info(f"PHASE 2 COMPLETE - Total Time: {stats['total_time']:.2f}s")
        if total_queries > 0:
            logger.info(f"Success Rate: {stats['success_rate']*100:.1f}% ({stats['successful_queries']}/{total_queries})")
        f1e = stats.get("f1_evaluation", {})
        sf = f1e.get("select_filter", {})
        ag = f1e.get("aggregation", {})
        if sf:
            logger.info(
                f"SELECT/FILTER — macro F1={sf['macro_f1']:.3f}  "
                f"P={sf['macro_precision']:.3f}  R={sf['macro_recall']:.3f}  "
                f"({sf['queries_scored']} queries)"
            )
        if ag:
            logger.info(
                f"AGGREGATION   — macro F1={ag['macro_f1']:.3f}  "
                f"({ag['queries_scored']} queries)"
            )
        logger.info("=" * 80)

        return True, test_metrics, stats

    except Exception as e:
        logger.exception(f"Testing phase failed: {e}")
        stats["success"] = False
        stats["error"] = str(e)
        stats["total_time"] = time.time() - phase_start
        return False, test_metrics, stats


# ============================================================================
# Report Generation
# ============================================================================

def generate_query_type_charts(test_metrics: List[TestQueryMetrics]) -> None:
    """Generate bar charts for query types."""
    if not MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available - skipping chart generation")
        return

    for query_category in ["Agg", "Filter", "Select", "Mixed", "Join"]:
        category_metrics = [m for m in test_metrics if query_category.lower() in m.query_text.lower() or m.query_type == query_category]
        if not category_metrics:
            continue

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f"Query Type: {query_category}", fontsize=16, fontweight='bold')

        ax = axes[0, 0]
        success_count = sum(1 for m in category_metrics if m.success)
        failed_count = len(category_metrics) - success_count
        ax.bar(['Successful', 'Failed'], [success_count, failed_count], color=['#2ecc71', '#e74c3c'], edgecolor='black', linewidth=1.5)
        ax.set_ylabel('Count', fontweight='bold')
        ax.set_title('Query Success Rate', fontweight='bold')
        for i, v in enumerate([success_count, failed_count]):
            ax.text(i, v + 0.1, str(v), ha='center', fontweight='bold')

        ax = axes[0, 1]
        execution_times = [m.execution_time for m in category_metrics if m.success]
        if execution_times:
            ax.bar(range(len(execution_times)), execution_times, color='#3498db', edgecolor='black', linewidth=1.5, alpha=0.7)
            ax.axhline(y=sum(execution_times)/len(execution_times), color='red', linestyle='--', linewidth=2, label='Average')
            ax.set_ylabel('Time (seconds)', fontweight='bold')
            ax.set_xlabel('Query Index', fontweight='bold')
            ax.set_title('Execution Time per Query', fontweight='bold')
            ax.legend()

        ax = axes[1, 0]
        result_counts = [m.results_count for m in category_metrics if m.success]
        if result_counts:
            ax.bar(range(len(result_counts)), result_counts, color='#9b59b6', edgecolor='black', linewidth=1.5, alpha=0.7)
            ax.set_ylabel('Result Count', fontweight='bold')
            ax.set_xlabel('Query Index', fontweight='bold')
            ax.set_title('Result Row Count per Query', fontweight='bold')

        ax = axes[1, 1]
        delta_types = {}
        for m in category_metrics:
            dt = m.delta_type if m.delta_type else "UNKNOWN"
            delta_types[dt] = delta_types.get(dt, 0) + 1
        if delta_types:
            ax.pie(delta_types.values(), labels=delta_types.keys(), autopct='%1.1f%%',
                   colors=plt.cm.Set3(range(len(delta_types))), startangle=90, wedgeprops={'edgecolor': 'black', 'linewidth': 1.5})
            ax.set_title('Delta Type Distribution', fontweight='bold')

        plt.tight_layout()
        chart_file = RESULTS_BASE_DIR / f"chart_{query_category.lower()}.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        logger.info(f"Saved {query_category} chart to {chart_file}")
        plt.close()

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Overall Test Results Summary", fontsize=16, fontweight='bold')

    ax = axes[0]
    test_type_stats = {}
    for metric in test_metrics:
        tt = metric.query_type
        if tt not in test_type_stats:
            test_type_stats[tt] = {"success": 0, "failed": 0}
        if metric.success:
            test_type_stats[tt]["success"] += 1
        else:
            test_type_stats[tt]["failed"] += 1
    test_types = list(test_type_stats.keys())
    success_counts = [test_type_stats[tt]["success"] for tt in test_types]
    failed_counts = [test_type_stats[tt]["failed"] for tt in test_types]
    x = range(len(test_types))
    width = 0.35
    ax.bar([i - width/2 for i in x], success_counts, width, label='Successful', color='#2ecc71', edgecolor='black', linewidth=1.5)
    ax.bar([i + width/2 for i in x], failed_counts, width, label='Failed', color='#e74c3c', edgecolor='black', linewidth=1.5)
    ax.set_ylabel('Count', fontweight='bold')
    ax.set_title('Success Rate by Test Type', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(test_types)
    ax.legend()

    ax = axes[1]
    avg_times = {}
    for metric in test_metrics:
        tt = metric.query_type
        if tt not in avg_times:
            avg_times[tt] = []
        if metric.success:
            avg_times[tt].append(metric.execution_time)
    test_types_avg = list(avg_times.keys())
    avg_time_values = [sum(avg_times[tt])/len(avg_times[tt]) if avg_times[tt] else 0 for tt in test_types_avg]
    ax.bar(test_types_avg, avg_time_values, color='#3498db', edgecolor='black', linewidth=1.5, alpha=0.7)
    ax.set_ylabel('Average Time (seconds)', fontweight='bold')
    ax.set_title('Average Execution Time by Test Type', fontweight='bold')
    for i, v in enumerate(avg_time_values):
        ax.text(i, v + 0.01, f'{v:.3f}s', ha='center', fontweight='bold')

    plt.tight_layout()
    summary_chart = RESULTS_BASE_DIR / "chart_summary.png"
    plt.savefig(summary_chart, dpi=300, bbox_inches='tight')
    logger.info(f"Saved summary chart to {summary_chart}")
    plt.close()


def generate_report(
    preprocessing_stats: Dict[str, Any],
    test_metrics: List[TestQueryMetrics],
    test_stats: Dict[str, Any]
) -> None:
    """Generate comprehensive test report."""
    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)

    metrics_file = RESULTS_BASE_DIR / "test_metrics.json"
    with open(metrics_file, 'w') as f:
        json.dump([asdict(m) for m in test_metrics], f, indent=2)
    logger.info(f"✓ Test metrics saved to {metrics_file}")

    test_stats_file = RESULTS_BASE_DIR / "test_stats.json"
    with open(test_stats_file, 'w') as f:
        json.dump(test_stats, f, indent=2)
    logger.info(f"✓ Test statistics saved to {test_stats_file}")

    preproc_stats_file = RESULTS_BASE_DIR / "preprocessing_stats.json"
    with open(preproc_stats_file, 'w') as f:
        json.dump(preprocessing_stats, f, indent=2)
    logger.info(f"✓ Preprocessing statistics saved to {preproc_stats_file}")

    generate_query_type_charts(test_metrics)

    report_file = RESULTS_BASE_DIR / "TEST_REPORT.md"
    with open(report_file, 'w') as f:
        f.write("# WDIRS Player Workload Test Report\n\n")
        f.write(f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Phase 1: Preprocessing\n\n")
        f.write(f"- **Duration**: {preprocessing_stats.get('total_time', 0):.2f}s\n")
        f.write(f"- **Training Workload**: {', '.join(TRAINING_QUERY_TYPES)}\n")
        f.write(f"- **Status**: {'✓ SUCCESS' if preprocessing_stats.get('success') else '✗ FAILED'}\n\n")
        if preprocessing_stats.get('steps'):
            f.write("### Step Breakdown\n\n")
            for step, details in preprocessing_stats.get('steps', {}).items():
                if isinstance(details, dict):
                    f.write(f"- **{step}**: {details.get('time', 0):.2f}s\n")
                    if 'tables' in details:
                        f.write(f"  - Tables: {details.get('tables')}\n")
                    if 'total_chunks' in details:
                        f.write(f"  - Total Chunks: {details.get('total_chunks')}\n")
                    if 'total_records' in details:
                        f.write(f"  - Total Records: {details.get('total_records')}\n")
        f.write("\n## Phase 2: Testing\n\n")
        f.write(f"- **Duration**: {test_stats.get('total_time', 0):.2f}s\n")
        f.write(f"- **Total Queries**: {test_stats.get('total_queries', 0)}\n")
        f.write(f"- **Successful**: {test_stats.get('successful_queries', 0)}\n")
        f.write(f"- **Failed**: {test_stats.get('failed_queries', 0)}\n")
        f.write(f"- **Success Rate**: {test_stats.get('success_rate', 0)*100:.1f}%\n\n")
        f1e = test_stats.get("f1_evaluation", {})
        sf, ag = f1e.get("select_filter", {}), f1e.get("aggregation", {})
        if sf or ag:
            f.write("### Official UDA-Bench Evaluation\n\n")
            f.write("| Query Type | Macro Precision | Macro Recall | Macro F1 | Queries |\n")
            f.write("|------------|-----------------|--------------|----------|---------|\n")
        if sf:
            f.write(f"| SELECT/FILTER | {sf['macro_precision']:.3f} | {sf['macro_recall']:.3f} | {sf['macro_f1']:.3f} | {sf['queries_scored']} |\n")
        if ag:
            f.write(f"| AGGREGATION   | — | — | {ag['macro_f1']:.3f} | {ag['queries_scored']} |\n")
        if test_stats.get('test_results'):
            f.write("\n### Test Results by Type\n\n")
            for test_type, results in test_stats.get('test_results', {}).items():
                f.write(f"- **{test_type}**: {results.get('successful')}/{results.get('total')} passed, avg {results.get('average_execution_time', 0):.3f}s/query\n")
        f.write("\n### Query Execution Details\n\n")
        queries_by_type = {}
        for metric in test_metrics:
            if metric.query_type not in queries_by_type:
                queries_by_type[metric.query_type] = []
            queries_by_type[metric.query_type].append(metric)
        for test_type in sorted(queries_by_type.keys()):
            metrics = queries_by_type[test_type]
            f.write(f"#### {test_type} Queries ({len(metrics)} total)\n\n")
            for i, metric in enumerate(metrics[:10], 1):
                status = "✓" if metric.success else "✗"
                f.write(f"{i}. {status} {metric.query_id}: {metric.results_count} rows, {metric.execution_time:.3f}s, Delta: {metric.delta_type}")
                if metric.error:
                    f.write(f" - Error: {metric.error}")
                f.write("\n")
            if len(metrics) > 10:
                f.write(f"\n... and {len(metrics) - 10} more queries\n\n")
        f.write("\n## Visualizations\n\n")
        if MATPLOTLIB_AVAILABLE:
            for query_type in ["Agg", "Filter", "Select", "Mixed", "Join"]:
                chart_file = RESULTS_BASE_DIR / f"chart_{query_type.lower()}.png"
                if chart_file.exists():
                    f.write(f"- ![{query_type} Queries](chart_{query_type.lower()}.png)\n")
            if (RESULTS_BASE_DIR / "chart_summary.png").exists():
                f.write("\n### Overall Summary\n\n![Summary Chart](chart_summary.png)\n")
        else:
            f.write("*Matplotlib not available - charts not generated*\n\n")

    logger.info(f"✓ Report saved to {report_file}")
    logger.info("\n" + "=" * 80)
    logger.info("TEST RESULTS SAVED")
    logger.info("=" * 80)
    logger.info(f"📊 Metrics:       {metrics_file}")
    logger.info(f"📈 Statistics:    {test_stats_file}")
    logger.info(f"📋 Report:        {report_file}")
    if MATPLOTLIB_AVAILABLE:
        logger.info(f"📉 Charts:        {RESULTS_BASE_DIR}/chart_*.png")
    logger.info("=" * 80)


# ============================================================================
# Main
# ============================================================================

def main(skip_preprocessing: bool = False):
    """Main orchestration function."""
    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = RESULTS_BASE_DIR / "test_execution.log"
    setup_logging(log_file)

    logger.info("Starting WDIRS Player Workload Test")
    logger.info(f"Dataset: {DATASET}")
    logger.info(f"Query Dataset: {DATASET_QUERY}")
    logger.info(f"Results Directory: {RESULTS_BASE_DIR}")
    logger.info(f"Log File: {log_file}")
    logger.info(f"Source Data: {SOURCE_DATA_DIR / DATASET}")
    logger.info(f"Query Directory: {QUERY_DIR / DATASET_QUERY}")

    checkpoint_path = CHECKPOINT_DIR / f"{DATASET}_preprocessed.db"

    if skip_preprocessing:
        logger.info("\nSkipping Phase 1 (--skip-preprocessing flag set)")
        if not checkpoint_path.exists():
            db_path = DB_DIR / "wdirs.db"
            if db_path.exists():
                CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(db_path, checkpoint_path)
                logger.info(f"Copied existing DB to checkpoint: {checkpoint_path}")
            else:
                logger.error(
                    f"No existing DB at {db_path} and no checkpoint at {checkpoint_path}. "
                    "Run without --skip-preprocessing first."
                )
                return 1
        preprocessing_success = True
        preprocessing_stats = {"skipped": True}
    else:
        logger.info("\n" + "=" * 80)
        logger.info("Starting Phase 1: Preprocessing")
        logger.info("=" * 80)
        preprocessing_success, preprocessing_stats = run_preprocessing_phase(DATASET, DATASET_QUERY)
        if not preprocessing_success:
            logger.error("Preprocessing failed, skipping testing phase")
            logger.info(f"Error: {preprocessing_stats.get('error')}")
            return 1

    logger.info("\n" + "=" * 80)
    logger.info("Starting Phase 2: Testing")
    logger.info("=" * 80)
    test_success, test_metrics, test_stats = run_test_phase(DATASET, DATASET_QUERY, checkpoint_path)
    generate_report(preprocessing_stats, test_metrics, test_stats)

    logger.info("\n" + "=" * 80)
    logger.info("OVERALL TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Preprocessing: {'✓ PASSED' if preprocessing_success else '✗ FAILED'}")
    logger.info(f"Testing: {'✓ PASSED' if test_success else '✗ FAILED'}")
    logger.info(f"Results saved to: {RESULTS_BASE_DIR}")
    logger.info("=" * 80)

    return 0 if (preprocessing_success and test_success) else 1


if __name__ == "__main__":
    import argparse as _ap
    _parser = _ap.ArgumentParser()
    _parser.add_argument(
        "--skip-preprocessing",
        action="store_true",
        help="Skip Phase 1 and go straight to Phase 2 using the existing DB.",
    )
    _args, _unknown = _parser.parse_known_args()
    sys.exit(main(_args.skip_preprocessing))

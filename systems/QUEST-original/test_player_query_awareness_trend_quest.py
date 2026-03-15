"""
Run Q1..Q10 player query-awareness trend benchmarking with the original QUEST codebase.

This script is intentionally built on top of `systems/QUEST-original`, not the
separate `quest-old` package. The original repository exposes single-table
extraction primitives (`document_index.py`, `segment_index.py`,
`query_optimization.py`) but does not provide a reusable Python harness for the
benchmark's join-heavy trend workload. To stay faithful to the original codebase
while still supporting the benchmark contract, this script:

1. Bridges benchmark source documents into QUEST's expected datalake layout.
2. Runs the original QUEST extraction pipeline once per base table involved in a
   query (`player`, `team`, `city`, `owner`).
3. Materializes the extracted tables into SQLite.
4. Executes the benchmark SQL join over those extracted tables unchanged.
5. Evaluates with the shared official evaluator used by the other systems.

This is therefore a "QUEST-original extraction + benchmark join execution"
runner. It does not depend on the incompatible `quest-old` codebase.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd
import sqlglot
from sqlglot import expressions as exp

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
QUEST_DIR = SCRIPT_DIR

sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(QUEST_DIR))
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

import document_index as quest_document_index
import llm as quest_llm
import query_optimization as quest_query_optimization
import segment_index as quest_segment_index


DATASET = "Player"
DATASET_QUERY = "Player"
TREND_SQL_FILE = QUERY_DIR / DATASET_QUERY / "query_aware_trend_queries.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"
SOURCE_DATA_PLAYER_DIR = PROJECT_ROOT / "source_data" / "Player"
RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_quest_original"

DEFAULT_DOC_SAMPLE_SIZE = 20
DEFAULT_SEGMENT_SAMPLE_SIZE = 10

IDENTITY_COLUMNS: Dict[str, str] = {
    "city": "city_name",
    "player": "name",
    "team": "team_name",
    "owner": "name",
}

TABLE_NUMERIC_COLUMNS: Dict[str, List[str]] = {
    "player": [
        "age",
        "draft_pick",
        "draft_year",
        "nba_championships",
        "mvp_awards",
        "olympic_gold_medals",
        "fiba_world_cup",
    ],
    "team": ["founded_year", "championship", "championships"],
    "city": ["population", "area", "gdp"],
    "owner": ["age", "own_year", "ownership_percentage", "asset_net_worth"],
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


@dataclass
class TableExtractionPlan:
    table: str
    select_columns: List[str]
    all_columns: List[str]
    local_predicates: List[str]


@dataclass(frozen=True)
class JoinEdge:
    left_table: str
    left_col: str
    right_table: str
    right_col: str


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


def _patch_pandas_append() -> None:
    """Provide the old DataFrame.append API expected by QUEST-original on pandas>=2."""
    if hasattr(pd.DataFrame, "append"):
        return

    def _append(self, other, ignore_index: bool = False, **_kwargs):  # type: ignore[no-untyped-def]
        if isinstance(other, dict):
            other_df = pd.DataFrame([other])
        elif isinstance(other, pd.Series):
            other_df = other.to_frame().T
        elif isinstance(other, pd.DataFrame):
            other_df = other
        else:
            other_df = pd.DataFrame(other)
        return pd.concat([self, other_df], ignore_index=ignore_index)

    pd.DataFrame.append = _append  # type: ignore[attr-defined]


def _patch_quest_embedding_model() -> None:
    """
    Replace QUEST-original's hardcoded `/intfloat/multilingual-e5-large` path with a
    configurable HuggingFace model name/path so this script can run in modern setups.
    """
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer

    model_name = os.getenv("QUEST_E5_MODEL", "intfloat/multilingual-e5-large")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    state: Dict[str, Any] = {}

    def _load() -> Tuple[Any, Any]:
        if "tokenizer" not in state:
            logger.info("Loading QUEST embedding model: %s on %s", model_name, device)
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModel.from_pretrained(model_name)
            model = model.to(device)
            model.eval()
            state["tokenizer"] = tokenizer
            state["model"] = model
        return state["tokenizer"], state["model"]

    def _get_embed(sentences: Sequence[str]) -> "np.ndarray":
        tokenizer, model = _load()
        embeddings: List[Any] = []
        for text in sentences:
            inputs = tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512,
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = model(**inputs)
            embedding = outputs.last_hidden_state[:, 0, :].squeeze().detach().cpu().numpy()
            embeddings.append(embedding)
        return np.array(embeddings)

    quest_document_index.get_embed = _get_embed
    quest_segment_index.get_embed = _get_embed


def _normalize_cell(value: Any) -> Any:
    if pd.isna(value):
        return ""
    if isinstance(value, str):
        return " ".join(value.strip().split())
    return value


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        out[col] = out[col].apply(_normalize_cell)
    return out


def _coerce_numeric_columns(table: str, df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in TABLE_NUMERIC_COLUMNS.get(table, []):
        if col not in out.columns:
            continue
        out[col] = (
            out[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(" ", "", regex=False)
            .replace({"": None, "nan": None, "NAN": None})
        )
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _save_rows_csv(rows: List[Dict[str, Any]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with out_csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["_empty"])
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


def _write_query_tables_sqlite(table_map: Dict[str, pd.DataFrame], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        for table, df in table_map.items():
            df.to_sql(table, conn, if_exists="replace", index=False)


def _execute_sql_on_db(db_path: Path, sql: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return rows


def _read_info_file(path: Path) -> Dict[str, float]:
    info: Dict[str, float] = {}
    if not path.exists():
        return info
    for line in path.read_text().splitlines():
        if ":" not in line:
            continue
        key, raw_val = line.split(":", 1)
        key = key.strip()
        raw_val = raw_val.strip()
        try:
            info[key] = float(raw_val)
        except ValueError:
            continue
    return info


def _source_table_dir(table: str) -> Path:
    table_dir = SOURCE_DATA_PLAYER_DIR / table
    if not table_dir.exists():
        raise FileNotFoundError(f"Missing source table directory: {table_dir}")
    return table_dir


def ensure_bridge_datalake(run_dir: Path, table: str) -> Path:
    """
    Convert benchmark source docs into the file layout expected by QUEST-original:
    each document lives in its own folder with `origin.txt`, `no_title.txt`,
    and `content.txt`.
    """
    datalake_dir = run_dir / "bridge_datalake" / table
    if datalake_dir.exists() and any(datalake_dir.iterdir()):
        return datalake_dir

    datalake_dir.mkdir(parents=True, exist_ok=True)
    source_dir = _source_table_dir(table)
    for txt_file in sorted(source_dir.glob("*.txt"), key=lambda p: int(p.stem)):
        text = txt_file.read_text(errors="ignore").strip()
        doc_dir = datalake_dir / txt_file.stem
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "origin.txt").write_text(text)
        (doc_dir / "no_title.txt").write_text(text)
        (doc_dir / "content.txt").write_text(text)
    return datalake_dir


def _qualifier_names(parsed: exp.Expression) -> Dict[str, str]:
    alias_to_table: Dict[str, str] = {}
    for table in parsed.find_all(exp.Table):
        table_name = table.name.lower()
        alias_name = (table.alias_or_name or table.name).lower()
        alias_to_table[alias_name] = table_name
        alias_to_table[table_name] = table_name
    return alias_to_table


def _resolve_col_table(column: exp.Column, alias_to_table: Dict[str, str], tables: List[str]) -> Optional[str]:
    if column.table:
        return alias_to_table.get(column.table.lower(), column.table.lower())
    if len(tables) == 1:
        return tables[0]
    return None


def _flatten_and_conditions(expr_obj: Optional[exp.Expression]) -> List[exp.Expression]:
    if expr_obj is None:
        return []
    if isinstance(expr_obj, exp.And):
        return _flatten_and_conditions(expr_obj.left) + _flatten_and_conditions(expr_obj.right)
    return [expr_obj]


def _dequalify_sql(sql_text: str, alias_to_table: Dict[str, str]) -> str:
    out = sql_text
    for alias in sorted(alias_to_table.keys(), key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(alias)}\.", "", out)
    return out


def _query_has_where(sql: str) -> bool:
    return bool(re.search(r"\bWHERE\b", sql, flags=re.IGNORECASE))


def _parse_table_plans(sql: str) -> Dict[str, TableExtractionPlan]:
    parsed = sqlglot.parse_one(sql, error_level="raise")
    alias_to_table = _qualifier_names(parsed)
    tables = list(dict.fromkeys(alias_to_table.values()))
    table_selects: Dict[str, List[str]] = {table: [] for table in tables}
    table_all_cols: Dict[str, List[str]] = {table: [] for table in tables}
    table_predicates: Dict[str, List[str]] = {table: [] for table in tables}

    select_exprs = parsed.args.get("expressions") or []
    for select_expr in select_exprs:
        for col in select_expr.find_all(exp.Column):
            table = _resolve_col_table(col, alias_to_table, tables)
            if not table:
                continue
            if col.name not in table_selects[table]:
                table_selects[table].append(col.name)
            if col.name not in table_all_cols[table]:
                table_all_cols[table].append(col.name)

    for col in parsed.find_all(exp.Column):
        table = _resolve_col_table(col, alias_to_table, tables)
        if not table:
            continue
        if col.name not in table_all_cols[table]:
            table_all_cols[table].append(col.name)

    where_clause = parsed.args.get("where")
    predicates = _flatten_and_conditions(where_clause.this if where_clause else None)
    for predicate in predicates:
        pred_cols = list(predicate.find_all(exp.Column))
        pred_tables = {
            _resolve_col_table(col, alias_to_table, tables)
            for col in pred_cols
            if _resolve_col_table(col, alias_to_table, tables)
        }
        if len(pred_tables) != 1:
            continue
        if len(pred_cols) >= 2 and len(pred_tables) == 1:
            # This is likely an intra-table column-vs-column comparison; QUEST-original's
            # single-table optimizer does not expect these in the benchmark workload.
            continue
        table = next(iter(pred_tables))
        table_predicates[table].append(_dequalify_sql(predicate.sql(dialect="sqlite"), alias_to_table))

    plans: Dict[str, TableExtractionPlan] = {}
    for table in tables:
        if not table_all_cols[table]:
            identity = IDENTITY_COLUMNS.get(table, "name")
            table_all_cols[table].append(identity)
        plans[table] = TableExtractionPlan(
            table=table,
            select_columns=table_selects[table][:],
            all_columns=table_all_cols[table][:],
            local_predicates=table_predicates[table][:],
        )
    return plans


def _parse_join_edges(sql: str) -> List[JoinEdge]:
    parsed = sqlglot.parse_one(sql, error_level="raise")
    alias_to_table = _qualifier_names(parsed)
    tables = list(dict.fromkeys(alias_to_table.values()))
    edges: List[JoinEdge] = []

    for join in parsed.find_all(exp.Join):
        on_expr = join.args.get("on")
        if on_expr is None:
            continue
        for eq_expr in on_expr.find_all(exp.EQ):
            left = eq_expr.left
            right = eq_expr.right
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                continue
            left_table = _resolve_col_table(left, alias_to_table, tables)
            right_table = _resolve_col_table(right, alias_to_table, tables)
            if not left_table or not right_table or left_table == right_table:
                continue
            edge = JoinEdge(
                left_table=left_table,
                left_col=left.name,
                right_table=right_table,
                right_col=right.name,
            )
            if edge not in edges:
                edges.append(edge)
    return edges


def _build_query_description(
    table: str,
    columns: Sequence[str],
    attributes: Dict[str, Any],
) -> str:
    table_attrs = attributes.get(table, {})
    lines = [""]
    for col in columns:
        desc = str(table_attrs.get(col, {}).get("description", f"{col} in {table}.")).strip()
        lines.append(f"{col}: {desc}")
    lines.append("")
    return "\n".join(lines)


def _build_table_query(
    plan: TableExtractionPlan,
    extra_predicates: Optional[Sequence[str]] = None,
) -> str:
    identity_col = IDENTITY_COLUMNS.get(plan.table, plan.all_columns[0])
    columns = list(dict.fromkeys(plan.all_columns))
    if identity_col not in columns:
        columns.append(identity_col)
    predicates = [p for p in plan.local_predicates if p.strip()]
    if extra_predicates:
        predicates.extend([p for p in extra_predicates if p.strip()])
    if not predicates:
        raise ValueError(
            "QUEST-original bridge requires real WHERE predicates; "
            f"query table '{plan.table}' has neither a local predicate nor a derived join predicate."
        )
    select_clause = ", ".join(columns)
    where_clause = " AND ".join(f"({p})" for p in predicates)
    return f"SELECT {select_clause} FROM {plan.table} WHERE {where_clause}"


def _build_extraction_order(
    plans: Dict[str, TableExtractionPlan],
    edges: List[JoinEdge],
) -> List[str]:
    anchors = [table for table, plan in plans.items() if plan.local_predicates]
    if not anchors:
        raise ValueError("No real table-local predicates found for this query.")

    adjacency: Dict[str, List[str]] = {table: [] for table in plans}
    for edge in edges:
        adjacency.setdefault(edge.left_table, []).append(edge.right_table)
        adjacency.setdefault(edge.right_table, []).append(edge.left_table)

    ordered: List[str] = []
    visited: Set[str] = set()
    queue: List[str] = anchors[:]

    while queue:
        table = queue.pop(0)
        if table in visited:
            continue
        visited.add(table)
        ordered.append(table)
        for neighbor in adjacency.get(table, []):
            if neighbor not in visited and neighbor not in queue:
                queue.append(neighbor)

    for table in plans:
        if table not in visited:
            ordered.append(table)
    return ordered


def _render_eq_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    text = str(value).strip()
    if not text:
        return ""
    return text.replace("'", "")


def _derive_join_predicates(
    table: str,
    edges: List[JoinEdge],
    extracted_tables: Dict[str, pd.DataFrame],
) -> List[str]:
    predicates: List[str] = []
    for edge in edges:
        if edge.left_table == table and edge.right_table in extracted_tables:
            target_col = edge.left_col
            source_df = extracted_tables[edge.right_table]
            source_col = edge.right_col
        elif edge.right_table == table and edge.left_table in extracted_tables:
            target_col = edge.right_col
            source_df = extracted_tables[edge.left_table]
            source_col = edge.left_col
        else:
            continue

        if source_col not in source_df.columns:
            raise ValueError(
                f"Upstream extracted table is missing join column '{source_col}' needed for '{table}'."
            )

        values: List[str] = []
        for raw in source_df[source_col].tolist():
            rendered = _render_eq_value(raw)
            if rendered and rendered not in values:
                values.append(rendered)

        if not values:
            raise ValueError(
                f"No join values extracted from upstream table for '{table}.{target_col}'."
            )

        disjuncts: List[str] = []
        for val in values:
            is_number = bool(re.fullmatch(r"-?\d+(?:\.\d+)?", val))
            if is_number:
                rhs = val
            else:
                rhs = "'" + val.replace("'", "''") + "'"
            disjuncts.append(f"{target_col} = {rhs}")
        predicates.append(disjuncts[0] if len(disjuncts) == 1 else "(" + " OR ".join(disjuncts) + ")")
    return predicates


def _load_sampled_table(candidate_dir: Path, table: str) -> pd.DataFrame:
    """
    Load QUEST-original's own sampled data from segment-index artifacts.

    This avoids leaking benchmark ground-truth tables into selectivity estimation.
    """
    csv_path = candidate_dir / "data.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Missing QUEST sampled CSV for table '{table}': {csv_path}. "
            "Expected segment_index.get_segment_index() to generate candidate/data.csv."
        )
    df = pd.read_csv(csv_path)
    if "ID" in df.columns:
        df = df.drop(columns=["ID"])
    return df


def _extract_table_with_quest_original(
    *,
    run_dir: Path,
    query_id: str,
    table: str,
    plan: TableExtractionPlan,
    attributes: Dict[str, Any],
    api_key: str,
    doc_sample_size: int,
    segment_sample_size: int,
    extra_predicates: Optional[Sequence[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, float], Dict[str, Any]]:
    table_dir = run_dir / "bridge_artifacts" / query_id / table
    candidate_dir = table_dir / "candidate"
    result_dir = table_dir / "result"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "candi").mkdir(parents=True, exist_ok=True)
    (candidate_dir / "key").mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    datalake_dir = ensure_bridge_datalake(run_dir, table)
    all_file_list = [p.name for p in sorted(datalake_dir.iterdir(), key=lambda p: int(p.name)) if p.is_dir()]
    if not all_file_list:
        raise RuntimeError(f"No bridged documents found for table: {table}")

    sql_query = _build_table_query(plan, extra_predicates=extra_predicates)
    sql_query_description = _build_query_description(table, plan.all_columns, attributes)
    logger.info("QUEST-original table extraction %s/%s", query_id, table)
    logger.info("Table query: %s", sql_query)

    quest_document_index.init_chatgpt(api_key)
    quest_segment_index.init_chatgpt(api_key)
    quest_llm.init_chatgpt(api_key)

    file_lake_dir = str(datalake_dir) + "/"
    file_candidate_dir = str(candidate_dir)
    result_dir_str = str(result_dir) + "/"

    file_list = quest_document_index.get_document_index(
        api_key,
        sql_query,
        sql_query_description,
        all_file_list,
        file_lake_dir,
        file_candidate_dir,
        n=min(doc_sample_size, len(all_file_list)),
    )
    if not file_list:
        raise RuntimeError(f"QUEST-original returned no candidate files for table '{table}'")

    quest_segment_index.get_segment_index(
        api_key,
        sql_query,
        sql_query_description,
        file_list,
        file_lake_dir,
        file_candidate_dir,
        n=min(segment_sample_size, len(file_list)),
    )
    sampled_df = _load_sampled_table(candidate_dir, table)

    extracted_df = quest_query_optimization.generate_output(
        sql_query,
        result_dir_str,
        file_candidate_dir,
        sampled_df,
    )
    if not isinstance(extracted_df, pd.DataFrame):
        extracted_df = pd.DataFrame(extracted_df)

    extracted_df = _normalize_dataframe(extracted_df)
    extracted_df = _coerce_numeric_columns(table, extracted_df)

    for col in plan.all_columns:
        if col not in extracted_df.columns:
            extracted_df[col] = ""
    extracted_df = extracted_df[plan.all_columns]

    info = _read_info_file(result_dir / "infor.txt")
    raw_artifacts = {
        "table_query": sql_query,
        "table_query_description": sql_query_description,
        "derived_predicates": list(extra_predicates or []),
        "candidate_dir": str(candidate_dir),
        "result_dir": str(result_dir),
        "info": info,
    }
    return extracted_df, info, raw_artifacts


def _parse_query_range(range_str: Optional[str]) -> Optional[Set[str]]:
    if not range_str or not range_str.strip():
        return None
    s = range_str.strip()
    m = re.match(r"^Q(\d+)$", s, re.IGNORECASE)
    if m:
        return {f"Q{int(m.group(1))}"}
    m = re.match(r"^Q(\d+)\s*-\s*Q(\d+)$", s, re.IGNORECASE)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            raise ValueError(f"Invalid query range: start Q{lo} > end Q{hi}")
        return {f"Q{i}" for i in range(lo, hi + 1)}
    raise ValueError(f"Invalid --query-range '{range_str}'. Use e.g. Q6-Q8 or Q3.")


def run_trend_queries_quest_original(
    *,
    run_dir: Path,
    api_key: str,
    query_range: Optional[str],
    doc_sample_size: int,
    segment_sample_size: int,
) -> List[TrendQueryMetrics]:
    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    plots_dir = run_dir / "plots"
    query_eval_db_dir = run_dir / "query_eval_dbs"
    per_query_meta_dir = run_dir / "query_metadata"

    run_dir.mkdir(parents=True, exist_ok=True)
    query_results_dir.mkdir(parents=True, exist_ok=True)
    query_tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    query_eval_db_dir.mkdir(parents=True, exist_ok=True)
    per_query_meta_dir.mkdir(parents=True, exist_ok=True)

    attributes: Dict[str, Any] = _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    if not attributes:
        raise RuntimeError(f"Missing or empty attributes JSON: {ATTRIBUTES_FILE}")

    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")

    allowed_ids = _parse_query_range(query_range)
    if allowed_ids is not None:
        trend_queries = [(qid, sql) for qid, sql in trend_queries if qid in allowed_ids]
        if not trend_queries:
            raise RuntimeError(f"No queries matched range {query_range!r}")
        logger.info("Query range filter active: %s", sorted(qid for qid, _ in trend_queries))

    skipped_without_where = [qid for qid, sql in trend_queries if not _query_has_where(sql)]
    if skipped_without_where:
        logger.info("Skipping queries without real WHERE clause: %s", skipped_without_where)
    trend_queries = [(qid, sql) for qid, sql in trend_queries if _query_has_where(sql)]
    if not trend_queries:
        raise RuntimeError("No trend queries with a real WHERE clause remain to run.")

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info("Executing %s with QUEST-original bridge harness", query_id)
        t0 = time.time()

        try:
            plans = _parse_table_plans(query_text)
            join_edges = _parse_join_edges(query_text)
            extraction_order = _build_extraction_order(plans, join_edges)
            table_map: Dict[str, pd.DataFrame] = {}
            query_meta: Dict[str, Any] = {
                "query_id": query_id,
                "query_sql": query_text,
                "table_plans": {},
                "bridge_mode": "quest_original_single_table_extraction_plus_sql_join",
                "join_edges": [asdict(edge) for edge in join_edges],
                "extraction_order": extraction_order,
            }
            prompt_tokens = 0

            for table in extraction_order:
                plan = plans[table]
                derived_predicates = _derive_join_predicates(table, join_edges, table_map)
                extracted_df, info, raw_artifacts = _extract_table_with_quest_original(
                    run_dir=run_dir,
                    query_id=query_id,
                    table=table,
                    plan=plan,
                    attributes=attributes,
                    api_key=api_key,
                    doc_sample_size=doc_sample_size,
                    segment_sample_size=segment_sample_size,
                    extra_predicates=derived_predicates,
                )
                table_map[table] = extracted_df
                actual_tokens = int(info.get("all_actual_token", 0))
                prompt_tokens += actual_tokens
                GLOBAL_COUNTER.record(
                    input_tokens=actual_tokens,
                    output_tokens=0,
                    operation="quest_original",
                )
                query_meta["table_plans"][table] = {
                    "select_columns": plan.select_columns,
                    "all_columns": plan.all_columns,
                    "local_predicates": plan.local_predicates,
                    "derived_predicates": derived_predicates,
                    "raw_artifacts": raw_artifacts,
                    "rows_extracted": int(len(extracted_df)),
                }

            query_eval_db = query_eval_db_dir / f"{query_id}.db"
            _write_query_tables_sqlite(table_map, query_eval_db)

            rows = _execute_sql_on_db(query_eval_db, query_text)
            latency = time.time() - t0

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
                attributes=attributes,
                identity_col=_infer_identity_col_for_query(query_text, IDENTITY_COLUMNS),
                phase2_db=query_eval_db,
                output_dir=query_results_dir / query_id,
            )

            item = TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                success=True,
                delta_type="QUEST_ORIGINAL",
                latency_s=latency,
                result_rows=len(rows),
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=prompt_tokens,
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
            acc_data = json.loads(acc_path.read_text()) if acc_path.exists() else {}
            acc_data["query_id"] = query_id
            acc_data["latency_s"] = round(latency, 4)
            acc_data["prompt_tokens"] = prompt_tokens
            acc_data["completion_tokens"] = 0
            acc_data["total_tokens"] = prompt_tokens
            acc_data["result_rows"] = len(rows)
            acc_data["success"] = True
            acc_data["macro_f1"] = eval_out.get("macro_f1", 0.0)
            acc_data["macro_precision"] = eval_out.get("macro_precision", 0.0)
            acc_data["macro_recall"] = eval_out.get("macro_recall", 0.0)
            acc_data["token_source"] = "quest_original_all_actual_token_sum"
            acc_path.write_text(json.dumps(acc_data, indent=2))

            query_meta["result_rows"] = len(rows)
            query_meta["latency_s"] = latency
            query_meta["prompt_tokens"] = prompt_tokens
            query_meta["completion_tokens"] = 0
            query_meta["total_tokens"] = prompt_tokens
            query_meta["evaluation"] = eval_out
            (per_query_meta_dir / f"{query_id}.json").write_text(json.dumps(query_meta, indent=2))

            logger.info(
                "%s: rows=%s latency=%.3fs tokens=%s F1=%.3f",
                query_id,
                item.result_rows,
                item.latency_s,
                item.total_tokens,
                item.macro_f1,
            )
        except Exception as exc:
            latency = time.time() - t0
            logger.exception("%s failed: %s", query_id, exc)
            metrics.append(
                TrendQueryMetrics(
                    query_id=query_id,
                    query_text=query_text,
                    success=False,
                    delta_type="QUEST_ORIGINAL",
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
                    error=str(exc),
                )
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
    logger.info("Saved metrics JSON: %s", out_json)
    logger.info("Saved metrics CSV:  %s", out_csv)


def plot_metrics(metrics: List[TrendQueryMetrics], run_dir: Path) -> None:
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
        "Player Query-Awareness Trend with QUEST-original (Q1..Q10)",
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
    axes[0, 1].set_title("Token Cost (QUEST actual-token sum)")
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
    logger.info("Saved trend summary plot: %s", summary_plot)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Player query-awareness trend on QUEST-original")
    parser.add_argument(
        "--openai-key",
        type=str,
        default=os.getenv("OPENAI_API_KEY", ""),
        help="API key for the original QUEST LLM calls. Defaults to OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--query-range",
        type=str,
        default=None,
        metavar="RANGE",
        help="Run only queries in range, e.g. Q6-Q8 or Q3. Default: all queries.",
    )
    parser.add_argument(
        "--doc-sample-size",
        type=int,
        default=DEFAULT_DOC_SAMPLE_SIZE,
        help="Document-level sample size used by QUEST-original document indexing.",
    )
    parser.add_argument(
        "--segment-sample-size",
        type=int,
        default=DEFAULT_SEGMENT_SAMPLE_SIZE,
        help="Segment-level sample size used by QUEST-original segment indexing.",
    )
    args = parser.parse_args()

    if not args.openai_key:
        raise RuntimeError("Missing API key. Pass --openai-key or set OPENAI_API_KEY.")

    ensure_precise_tokenizer_ready()
    _patch_pandas_append()
    _patch_quest_embedding_model()

    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    run_tag = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_BASE_DIR / f"run_{run_tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(run_dir / "query_awareness_trend_quest.log")

    metadata = {
        "script": str(Path(__file__).name),
        "source_codebase": "systems/QUEST-original",
        "query_file": str(TREND_SQL_FILE),
        "ground_truth_dir": str(GROUND_TRUTH_DIR),
        "source_docs_dir": str(SOURCE_DATA_PLAYER_DIR),
        "bridge_mode": "quest_original_single_table_extraction_plus_sql_join",
        "doc_sample_size": args.doc_sample_size,
        "segment_sample_size": args.segment_sample_size,
        "token_accounting": "sum(all_actual_token) across per-table QUEST-original runs",
        "notes": [
            "This script uses the original QUEST extraction modules, not quest-old.",
            "Join queries are executed over SQLite tables built from QUEST-original extractions.",
            "Only benchmark queries with a real top-level WHERE clause are run.",
            "Anchor tables use real benchmark predicates; downstream tables use real derived join predicates built from upstream extracted join values.",
            "No synthetic always-true WHERE clause is used anywhere in the extraction pipeline.",
        ],
    }
    (run_dir / "method_metadata.json").write_text(json.dumps(metadata, indent=2))

    logger.info("Starting Player query-awareness trend test (QUEST-original)...")
    logger.info("Run directory: %s", run_dir)
    logger.info("Trend query source: %s", TREND_SQL_FILE)
    logger.info("Source docs dir: %s", SOURCE_DATA_PLAYER_DIR)
    logger.info("Results base dir: %s", RESULTS_BASE_DIR)
    logger.info("Doc sample size: %s", args.doc_sample_size)
    logger.info("Segment sample size: %s", args.segment_sample_size)
    logger.info("Identity columns (for eval): %s", IDENTITY_COLUMNS)

    try:
        metrics = run_trend_queries_quest_original(
            run_dir=run_dir,
            api_key=args.openai_key,
            query_range=args.query_range,
            doc_sample_size=args.doc_sample_size,
            segment_sample_size=args.segment_sample_size,
        )
        save_metrics(metrics, run_dir)
        plot_metrics(metrics, run_dir)

        success_count = sum(1 for m in metrics if m.success)
        avg_f1 = sum(m.macro_f1 for m in metrics) / len(metrics) if metrics else 0.0
        if not math.isfinite(avg_f1):
            avg_f1 = 0.0

        logger.info("=" * 80)
        logger.info(
            "Completed: %s/%s queries succeeded, avg macro F1=%.3f",
            success_count,
            len(metrics),
            avg_f1,
        )
        token_summary = GLOBAL_COUNTER.summary_str()
        logger.info(token_summary)
        token_json_path = run_dir / "token_cost.json"
        GLOBAL_COUNTER.save_json(token_json_path)
        logger.info("Token cost JSON saved to: %s", token_json_path)
        logger.info("Outputs under: %s", run_dir)
        logger.info("=" * 80)
        return 0
    except Exception as exc:
        logger.exception("QUEST-original trend test failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

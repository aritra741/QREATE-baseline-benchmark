"""
Run Q1..Q10 query-awareness trend benchmarking with strict ReDD variants on Player.

This script is aligned with the WDIRS/DocETL trend harness for comparability:
- same query source (Query/Player/query_aware_trend_queries.sql)
- same official evaluator wiring (macro P/R/F1)
- same per-query artifacts + run-level metrics outputs

Strictness policy:
- fixed model family: Qwen2.5-7B-Instruct only
- fixed backend path: local HuggingFace model runtime only
- no silent fallback to alternative backends/models
- fail fast: any query failure aborts the run

Ground-truth isolation:
- GT data (Data/Player/*.csv) is NEVER provided to the model or the
  ReDD extraction pipeline.  It is loaded ONLY after extraction to
  (a) build correctness labels for the SCAPE error-detection classifier
      (Section 3.1 of the paper) and
  (b) run the official evaluator for benchmark metrics.
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
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import torch

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
REDD_DIR = PROJECT_ROOT / "systems" / "ReDD"

sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(REDD_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from config import QUERY_DIR, RESULTS_DIR  # type: ignore
from token_counter import GLOBAL_COUNTER, ensure_precise_tokenizer_ready
from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.row_matcher import RowMatcher as _RowMatcher
from evaluation.sql_parser import SqlParser as _SqlParser
from test_player_query_awareness_trend import (  # type: ignore
    parse_trend_queries,
    evaluate_with_official_framework,
    _infer_identity_col_for_query,
)
from core.data_population import DataPopLocal
from core.data_loader import create_data_loader
from core.correction import ClassifierTrainer, ClassifierVal
from core.utils.constants import PATH_TEMPLATES as REDD_PATHS


DATASET = "Player"
DATASET_QUERY = "Player"
TREND_SQL_FILE = QUERY_DIR / DATASET_QUERY / "query_aware_trend_queries.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"
SOURCE_DATA_PLAYER_DIR = PROJECT_ROOT / "source_data" / "Player"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_redd"

REQUIRED_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
ALLOWED_MODEL_IDS = {"Qwen/Qwen2.5-7B-Instruct", "qwen2.5:7b-instruct"}
DEFAULT_MODEL = os.getenv("REDD_MODEL_ID", REQUIRED_MODEL_ID)
DEFAULT_TEMPERATURE = float(os.getenv("REDD_TREND_TEMPERATURE", "0.0"))
DEFAULT_MAX_TOKENS = int(os.getenv("REDD_TREND_MAX_TOKENS", "600"))
REDD_MODEL_LOCAL_PATH = str(
    Path(os.getenv("REDD_MODEL_LOCAL_PATH", str(REDD_DIR / ".models" / "qwen2_5_7b_instruct")))
)
REDD_PROMPT_TABLE = str(REDD_DIR / "prompts" / "datapop_table_json.txt")
REDD_PROMPT_ATTR = str(REDD_DIR / "prompts" / "datapop_attr_json.txt")
REDD_PARAM_STR = "redd_qwen25_7b_local"
DEFAULT_VARIANT = os.getenv("REDD_VARIANT", "ReDD_SCAPE")
SUPPORTED_VARIANTS = {"ReDD_NoCorrection", "ReDD_SCAPE", "ReDD_SCAPE_Hyb"}
SCAPE_ALPHA = float(os.getenv("REDD_SCAPE_ALPHA", "0.05"))

NUMERIC_FIELDS = {
    "age",
    "draft_pick",
    "founded_year",
    "population",
    "gdp",
    "area",
}

KNOWN_TABLE_COLUMNS: Dict[str, Set[str]] = {
    "player": {
        "name",
        "nationality",
        "age",
        "position",
        "draft_pick",
        "college",
        "birth_date",
        "team",
    },
    "team": {
        "team_name",
        "location",
        "founded_year",
    },
    "city": {
        "city_name",
        "state_name",
        "population",
        "gdp",
        "area",
    },
    "owner": {
        "name",
        "team",
        "ownership_percentage",
        "asset_net_worth",
    },
}

IDENTITY_COLUMNS: Dict[str, str] = {
    "city": "city_name",
    "player": "name",
    "team": "team_name",
    "owner": "name",
}

NL_QUERY_SPECS: Dict[str, str] = {
    "Q1": "List each player's name, nationality, and age with their team name and team location.",
    "Q2": "For players older than 25, list player name, position, team name, and team founded year.",
    "Q3": "For players with draft pick at least 0, list player name, draft pick, college, and team name.",
    "Q4": "List team name and location with the matched city name and state name.",
    "Q5": "List player name with team name, city name, and city state by linking player to team to city.",
    "Q6": "For players younger than 35, list player name, position, city name, and city population via player to team to city.",
    "Q7": "For players with draft pick greater than 0, list player name, college, team name, and city GDP via player to team to city.",
    "Q8": "For cities with area greater than 100, list player name, player birth date, team name, and city area via player to team to city.",
    "Q9": "Starting from city and traversing city to team to player, list city name, state, team name, and player name for players younger than 40.",
    "Q10": "Starting from city and traversing city to team to player, list city name, state, team name, player name, and player college for players older than 20.",
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
    """Tracks process-local prompt/completion totals for per-query deltas."""

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


def _install_token_tracking_hook(datapop: DataPopLocal, tracker: TokenTracker) -> None:
    """Monkey-patch DataPopLocal.llm_generate to capture token counts."""
    _original_generate = datapop.llm_generate

    def _count_prompt_tokens(prompt: str, msg: str) -> int:
        chat = datapop.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt + "\n\n" + msg}],
            add_generation_prompt=True,
            return_tensors="pt",
        )
        # HF tokenizers may return either a Tensor or BatchEncoding-like object.
        if hasattr(chat, "shape"):
            return int(chat.shape[1])
        if hasattr(chat, "get"):
            ids = chat.get("input_ids")
            if ids is not None and hasattr(ids, "shape"):
                return int(ids.shape[1])
        # Conservative fallback
        return 0

    def _tracked_generate(prompt: str, msg: str):
        prompt_tok_count = _count_prompt_tokens(prompt, msg)
        gen_text, token_info = _original_generate(prompt, msg)
        completion_tok_count = len(token_info)
        tracker.add(prompt_tok_count, completion_tok_count)
        GLOBAL_COUNTER.record(
            input_tokens=prompt_tok_count,
            output_tokens=completion_tok_count,
            operation="redd_trend",
        )
        return gen_text, token_info

    datapop.llm_generate = _tracked_generate


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


def _strip_sql_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _extract_tables_from_sql(sql: str) -> List[str]:
    pattern = re.compile(
        r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)|\bJOIN\s+([A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    )
    tables: List[str] = []
    for m in pattern.finditer(sql):
        t = (m.group(1) or m.group(2) or "").strip().lower()
        if t and t not in tables:
            tables.append(t)
    if not tables:
        raise ValueError(f"Could not parse tables from SQL: {sql}")
    return tables


def _extract_table_columns_from_sql(sql: str, tables: List[str]) -> Dict[str, Set[str]]:
    sql_clean = _strip_sql_comments(sql)
    pairs = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b", sql_clean)
    out: Dict[str, Set[str]] = {t: set() for t in tables}
    for table, col in pairs:
        t = table.lower()
        c = col.lower()
        if t in out:
            out[t].add(c)

    for t in tables:
        if not out[t]:
            if t == "player":
                out[t].update({"name"})
            elif t == "team":
                out[t].update({"team_name"})
            elif t == "city":
                out[t].update({"city_name"})

    for t in tables:
        known = KNOWN_TABLE_COLUMNS.get(t, set())
        out[t] = {c for c in out[t] if c in known}
        if not out[t]:
            out[t] = set(known)
    return out


def _coerce_numeric_columns(table: str, df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    numeric_cols = {
        "player": ["age", "draft_pick"],
        "team": ["founded_year"],
        "city": ["population", "gdp", "area"],
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


def _load_source_docs(table: str) -> List[Tuple[str, str]]:
    table_dir = SOURCE_DATA_PLAYER_DIR / table
    if not table_dir.exists():
        raise FileNotFoundError(f"Missing source table directory: {table_dir}")
    rows: List[Tuple[str, str]] = []
    for p in sorted(table_dir.glob("*.txt"), key=lambda x: int(x.stem)):
        rows.append((p.stem, p.read_text(errors="ignore")))
    if not rows:
        raise RuntimeError(f"No source files found for table: {table}")
    return rows


def _write_query_tables_sqlite(table_map: Dict[str, pd.DataFrame], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        for table, df in table_map.items():
            df.to_sql(table, conn, if_exists="replace", index=False)


def _execute_sql_on_query_db(db_path: Path, sql: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return rows


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


def _to_redd_schema_blocks(table_cols: Dict[str, Set[str]]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for table, cols in table_cols.items():
        attrs = [{"Attribute Name": c, "Description": f"{c} in {table}"} for c in sorted(cols)]
        blocks.append({"Schema Name": table, "Attributes": attrs})
    return blocks


def _prepare_redd_query_dataset(
    run_dir: Path,
    query_id: str,
    query_sql: str,
    nl_query: str,
    tables: List[str],
    table_cols: Dict[str, Set[str]],
) -> Tuple[Path, str, Dict[str, Dict[str, Any]]]:
    """Prepare dataset for ReDD.  NO ground-truth data is embedded."""
    dataset_name = f"player_{query_id.lower()}"
    data_root = run_dir / "redd_bridge_data" / dataset_name
    data_root.mkdir(parents=True, exist_ok=True)

    db_path = data_root / "documents.db"
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE documents (
                doc_id TEXT PRIMARY KEY,
                doc_text TEXT NOT NULL,
                source_file TEXT,
                parent_doc_id TEXT,
                chunk_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        doc_info: Dict[str, Any] = {}
        did_meta: Dict[str, Dict[str, Any]] = {}
        idx = 0
        for table in tables:
            for source_doc_id, text in _load_source_docs(table):
                idx += 1
                did = str(idx)
                conn.execute(
                    """
                    INSERT INTO documents (doc_id, doc_text, source_file, parent_doc_id, chunk_index)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (did, text, table, source_doc_id, 0),
                )
                doc_info[did] = {"doc": text, "fn": table, "doc_id": did, "data": {}}
                did_meta[did] = {
                    "table": table,
                    "source_doc_id": str(source_doc_id),
                }
        conn.commit()

    (data_root / "doc_info.json").write_text(json.dumps(doc_info, indent=2))
    schema_general = _to_redd_schema_blocks(table_cols)
    (data_root / "schema_general.json").write_text(json.dumps(schema_general, indent=2))
    (data_root / f"schema_query_{query_id}.json").write_text(json.dumps(schema_general, indent=2))
    queries = {
        query_id: {
            "query": nl_query,
            "attributes": sorted({c for cs in table_cols.values() for c in cs}),
            "sql": query_sql,
        }
    }
    (data_root / "queries.json").write_text(json.dumps(queries, indent=2))
    table_map_identity = {t: t for t in tables}
    attr_map_identity = {t: {c: c for c in sorted(table_cols.get(t, set()))} for t in tables}
    name_map = {"table": table_map_identity, "attribute": attr_map_identity}
    (data_root / REDD_PATHS.eval_name_mapping(query_id)).write_text(json.dumps(name_map, indent=2))
    return data_root, dataset_name, did_meta


def _load_gt_rows_by_table(tables: List[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Load ground-truth rows.  Used ONLY for evaluation / correction labels."""
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for table in tables:
        csv_path = GROUND_TRUTH_DIR / f"{table}.csv"
        if not csv_path.exists():
            raise RuntimeError(f"Missing GT CSV for table '{table}': {csv_path}")
        df = pd.read_csv(csv_path, dtype=str).fillna("")
        if "ID" not in df.columns:
            raise RuntimeError(f"GT CSV missing ID column: {csv_path}")
        rows: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            rid = str(row.get("ID", "")).strip()
            if not rid:
                continue
            row_dict = {str(k).strip(): ("" if pd.isna(v) else str(v).strip()) for k, v in row.to_dict().items()}
            rows[rid] = row_dict
        out[table] = rows
    return out


def _canonicalize_value(v: Any) -> str:
    s = "" if v is None else str(v).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" \t\r\n\"'")
    return s


def _build_eval_output_from_gt(
    res_data: Dict[str, Any],
    did_meta: Dict[str, Dict[str, Any]],
    table_cols: Dict[str, Set[str]],
    gt_rows_by_table: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Compare extraction results against GT to produce correctness labels.

    These labels are used for:
    - SCAPE classifier training (small labeled subset, per Section 3.1)
    - Official evaluator metrics
    GT is NEVER fed to the extraction model.
    """
    eval_out: Dict[str, Any] = {}
    for did, meta in did_meta.items():
        gt_table = str(meta["table"]).strip().lower()
        source_doc_id = meta["source_doc_id"]
        gt_data = gt_rows_by_table.get(gt_table, {}).get(source_doc_id, {})
        pred_item = res_data.get(did, {})
        pred_table = str(pred_item.get("res", "")).strip().lower()
        table_ok = pred_table == gt_table
        attr_ok: Dict[str, bool] = {}
        for c in sorted(table_cols.get(gt_table, set())):
            pred_v = _canonicalize_value(pred_item.get("data", {}).get(c, ""))
            gt_v = _canonicalize_value(gt_data.get(c, ""))
            attr_ok[c] = table_ok and (pred_v == gt_v)
        final_ok = table_ok and all(attr_ok.values())
        eval_out[did] = {"table": table_ok, "attr": attr_ok, "final": final_ok}
    return eval_out


def _infer_classifier_shape(hidden_states_dir: Path) -> Tuple[int, int]:
    table_files = sorted(hidden_states_dir.glob("doc-*-table.pt"))
    if not table_files:
        raise RuntimeError(f"No table hidden-state files found in: {hidden_states_dir}")
    sample = torch.load(table_files[0], weights_only=False)
    if not sample:
        raise RuntimeError(f"Empty hidden-state file: {table_files[0]}")
    first = sample[0]["hidden_states"]
    num_layers = int(first.shape[0]) if hasattr(first, "shape") else len(first)
    hidden_dim = int(first.shape[-1]) if hasattr(first, "shape") else int(len(first[0]))
    pooled_dim = hidden_dim * 2
    return num_layers, pooled_dim


def _run_redd_correction(
    query_id: str,
    dataset_name: str,
    query_data_root: Path,
    out_main: Path,
    train_size: int,
    mode: str,
) -> Dict[str, int]:
    """Run the ReDD error-detection pipeline and return per-doc error flags.

    For ``mode="scape"`` this uses the paper's SCAPE conformal prediction
    (``ClassifierVal._multi_conformal_prediction``).
    For ``mode="scape_hyb"`` it runs SCAPE first, then falls back to
    soft-voting for ambiguous (abstained) docs.
    """
    out_root = out_main / dataset_name
    eval_path = out_root / REDD_PATHS.eval_result(query_id, REDD_PARAM_STR)
    hs_dir = out_root / REDD_PATHS.hidden_states_dir(query_id, REDD_PARAM_STR)
    if not eval_path.exists():
        raise RuntimeError(f"Missing eval labels required for correction: {eval_path}")
    if not hs_dir.exists():
        raise RuntimeError(f"Missing hidden-state directory required for correction: {hs_dir}")
    eval_output = json.loads(eval_path.read_text())
    all_dids = sorted(int(d) for d in eval_output.keys())
    if len(all_dids) < 10:
        raise RuntimeError(f"Insufficient docs for correction training in {query_id}: {len(all_dids)}")

    num_layers, pooled_dim = _infer_classifier_shape(hs_dir)
    exp_layers = list(range(max(0, num_layers - 7), num_layers))
    effective_train_size = min(train_size, max(1, len(all_dids) - 1))
    if effective_train_size < 1:
        raise RuntimeError(f"Invalid train size for correction: {effective_train_size}")

    # Partition docs: train | cells | recal | test
    # Reserve proportional slices; ensure cell+recal leave enough for test.
    remaining_after_train = len(all_dids) - effective_train_size
    num_cells = min(20, max(5, remaining_after_train // 4))
    num_recal = min(40, max(10, remaining_after_train // 3))
    if remaining_after_train - num_cells - num_recal < 5:
        num_cells = max(3, remaining_after_train // 5)
        num_recal = max(5, remaining_after_train // 4)
    # SCAPE needs non-trivial cell/recal/test partitions
    min_required = num_cells + num_recal + 5
    use_conformal = remaining_after_train >= min_required

    corr_config = {
        "mode": "local",
        "llm_model": REQUIRED_MODEL_ID,
        "llm_model_path": REDD_MODEL_LOCAL_PATH,
        "res_param_str": REDD_PARAM_STR,
        "data_loader_type": "sqlite",
        "data_main": str(query_data_root.parent),
        "out_main": str(out_main),
        "exp_dn_fn_list": [dataset_name],
        "cls_train_trials": [0],
        "exp_layers": exp_layers,
        "exp_train_sizes": [effective_train_size],
        "train_size": effective_train_size,
        "classifier_threshold": 0.5,
        "num_cells": num_cells,
        "num_recal": num_recal,
        "num_layers": num_layers,
        "hidden_size": pooled_dim,
        "trainer": {
            "train_percentage": 0.8,
            "batch_size": 64,
            "epochs": 8,
            "early_stop_patience": 2,
            "learning_rate": 1e-4,
        },
    }

    # --- Step 1: train classifiers on a small labeled subset ---
    trainer = ClassifierTrainer(corr_config)
    trainer([dataset_name])

    # --- Step 2: get classifier outputs for ALL docs ---
    val = ClassifierVal(corr_config)
    val.cls_train_trial = 0
    val.all_dids = all_dids
    val.exp_layers = exp_layers

    # Set partitioning boundaries (indices into all_dids)
    val.max_train_did = effective_train_size
    val.max_cells_did = effective_train_size + num_cells
    val.max_recal_did = effective_train_size + num_cells + num_recal
    val.min_test_did = val.max_recal_did
    val.max_test_did = 99999

    val.cell_dids = all_dids[val.max_train_did:val.max_cells_did]
    val.recal_dids = all_dids[val.max_cells_did:val.max_recal_did]
    # test_dids: everything after the recal partition (index-based, no overlap)
    val.test_dids = all_dids[val.max_recal_did:]
    if not val.test_dids:
        logger.warning(f"No test docs remaining after partitioning for {query_id}; "
                       f"using last quarter of all_dids as fallback")
        fallback_start = max(0, len(all_dids) * 3 // 4)
        val.test_dids = all_dids[fallback_start:]

    loader = create_data_loader(
        data_root=query_data_root,
        loader_type="sqlite",
        loader_config={},
    )
    model_dict = val._get_model_dict([dataset_name])
    classifier_outputs = val._get_classifier_outputs(
        loader=loader,
        model_dict=model_dict,
        out_root=str(out_root),
        qid=query_id,
        dids=all_dids,
        eval_output=eval_output,
    )

    size_key = f"s{effective_train_size}"
    gt_all = {did: (0 if eval_output[str(did)]["final"] else 1) for did in all_dids}

    layer_outputs = [
        classifier_outputs[dataset_name][query_id][str(layer)][size_key]
        for layer in exp_layers
    ]

    if (mode == "scape" or mode == "scape_hyb") and use_conformal:
        did2prediction_sets = val._multi_conformal_prediction(
            layer_outputs, gt_all, SCAPE_ALPHA,
        )

        did2error: Dict[str, int] = {}
        for did in all_dids:
            if did in did2prediction_sets:
                pred_set = did2prediction_sets[did]
                if 1 in pred_set and 0 not in pred_set:
                    did2error[str(did)] = 1
                elif mode == "scape_hyb" and len(pred_set) > 1:
                    # SCAPE-Hyb: for ambiguous docs ({0,1}), fall back to
                    # soft voting across layers as a tiebreaker.
                    probs = []
                    for layer_out in layer_outputs:
                        outputs_for_did = layer_out.get(str(did), [0.5])
                        probs.append(max(outputs_for_did))
                    avg_prob = sum(probs) / len(probs)
                    did2error[str(did)] = 1 if avg_prob >= 0.5 else 0
                else:
                    did2error[str(did)] = 0
            else:
                did2error[str(did)] = 0
        return did2error

    # Fallback: soft voting when dataset is too small for conformal prediction
    logger.warning(f"Dataset too small for SCAPE conformal prediction ({query_id}), "
                   f"falling back to soft voting")
    cls_outputs_list = [layer_outputs]
    voting_mode = "soft" if mode == "scape_hyb" else "half"
    row_preds, _labels, _ = val._apply_voting(gt_all, cls_outputs_list, voting_mode=voting_mode)
    return {str(did): int(pred) for did, pred in zip(val.test_dids, row_preds)}


def _apply_error_correction_to_res_data(
    res_data: Dict[str, Any],
    did2error: Dict[str, int],
) -> Dict[str, Any]:
    """Remove rows flagged as erroneous (conservative: drop rather than corrupt)."""
    corrected = {}
    for did, item in res_data.items():
        if did2error.get(did, 0) == 1:
            continue
        corrected[did] = item
    return corrected


def _redd_output_to_table_map(
    res_data: Dict[str, Any],
    table_cols: Dict[str, Set[str]],
) -> Dict[str, pd.DataFrame]:
    table_rows: Dict[str, List[Dict[str, Any]]] = {t: [] for t in table_cols}
    for _did, item in res_data.items():
        table = str(item.get("res", "")).strip().lower()
        if table not in table_rows:
            continue
        data = item.get("data", {})
        row = {c: data.get(c) for c in table_cols[table]}
        table_rows[table].append(row)

    table_map: Dict[str, pd.DataFrame] = {}
    for table, cols in table_cols.items():
        rows = table_rows.get(table, [])
        df = pd.DataFrame(rows, columns=sorted(cols))
        table_map[table] = _coerce_numeric_columns(table, df)
    return table_map


def execute_query_via_redd(
    run_dir: Path,
    query_id: str,
    query_sql: str,
    variant: str,
    token_tracker: TokenTracker,
) -> Tuple[List[Dict[str, Any]], Dict[str, pd.DataFrame], str]:
    tables = _extract_tables_from_sql(query_sql)
    table_cols = _extract_table_columns_from_sql(query_sql, tables)
    nl_query = NL_QUERY_SPECS.get(query_id, f"Answer query {query_id} over Player dataset.")

    # --- Prepare dataset (NO ground truth) ---
    query_data_root, dataset_name, did_meta = _prepare_redd_query_dataset(
        run_dir=run_dir,
        query_id=query_id,
        query_sql=query_sql,
        nl_query=nl_query,
        tables=tables,
        table_cols=table_cols,
    )

    out_main = run_dir / "redd_bridge_out"
    out_main.mkdir(parents=True, exist_ok=True)
    out_root = out_main / dataset_name

    # --- Run ReDD TDP (extraction) ---
    config = {
        "mode": "local",
        "llm_model": REQUIRED_MODEL_ID,
        "llm_model_path": REDD_MODEL_LOCAL_PATH,
        "res_param_str": REDD_PARAM_STR,
        "prompts": {
            "prompt_table": REDD_PROMPT_TABLE,
            "prompt_attr": REDD_PROMPT_ATTR,
        },
        "data_loader_type": "sqlite",
        "data_main": str(query_data_root.parent),
        "out_main": str(out_main),
        "exp_dn_fn_list": [dataset_name],
    }
    datapop = DataPopLocal(config)
    _install_token_tracking_hook(datapop, token_tracker)
    datapop([dataset_name])

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "queries.json").write_text((query_data_root / "queries.json").read_text())

    res_path = out_main / dataset_name / REDD_PATHS.data_population_result(query_id, REDD_PARAM_STR)
    if not res_path.exists():
        raise RuntimeError(f"ReDD datapop did not produce output: {res_path}")
    res_data = json.loads(res_path.read_text())

    # --- Load GT ONLY NOW (post-extraction) for correction labels / eval ---
    gt_rows_by_table = _load_gt_rows_by_table(tables)
    eval_output = _build_eval_output_from_gt(
        res_data=res_data,
        did_meta=did_meta,
        table_cols=table_cols,
        gt_rows_by_table=gt_rows_by_table,
    )
    eval_path = out_root / REDD_PATHS.eval_result(query_id, REDD_PARAM_STR)
    eval_path.write_text(json.dumps(eval_output, indent=2))

    final_res_data = res_data
    if variant in {"ReDD_SCAPE", "ReDD_SCAPE_Hyb"}:
        did2error = _run_redd_correction(
            query_id=query_id,
            dataset_name=dataset_name,
            query_data_root=query_data_root,
            out_main=out_main,
            train_size=32,
            mode="scape_hyb" if variant == "ReDD_SCAPE_Hyb" else "scape",
        )
        final_res_data = _apply_error_correction_to_res_data(res_data, did2error)
        corrected_path = out_root / f"res_tabular_data_{query_id}_{REDD_PARAM_STR}_corrected.json"
        corrected_path.write_text(json.dumps(final_res_data, indent=2))

    table_map = _redd_output_to_table_map(final_res_data, table_cols)

    temp_db = RESULTS_BASE_DIR / "_tmp" / f"{query_id}.db"
    _write_query_tables_sqlite(table_map, temp_db)
    return_rows = _execute_sql_on_query_db(temp_db, query_sql)
    return return_rows, table_map, nl_query


def run_trend_queries_redd(
    run_dir: Path,
    variant: str,
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

    eval_attributes: Dict[str, Any] = _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=eval_attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")

    token_tracker = TokenTracker()
    metrics: List[TrendQueryMetrics] = []

    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info(f"Executing {query_id} with ReDD trend harness")
        t0 = time.time()
        tok_before = token_tracker.snapshot()

        try:
            rows, query_table_map, _nl_query = execute_query_via_redd(
                run_dir=run_dir,
                query_id=query_id,
                query_sql=query_text,
                variant=variant,
                token_tracker=token_tracker,
            )
        except Exception as exc:
            latency = time.time() - t0
            d_prompt, d_completion = token_tracker.delta(tok_before)
            logger.exception(f"{query_id} FAILED: {exc}")
            metrics.append(TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                success=False,
                delta_type=variant.upper(),
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
            ))
            continue

        latency = time.time() - t0
        d_prompt, d_completion = token_tracker.delta(tok_before)
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
            identity_col=_infer_identity_col_for_query(query_text, identity_columns),
            phase2_db=query_eval_db,
            output_dir=query_results_dir / query_id,
        )

        item = TrendQueryMetrics(
            query_id=query_id,
            query_text=query_text,
            success=True,
            delta_type=variant.upper(),
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
        "Player Query-Awareness Trend with ReDD (Q1..Q10)",
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
    parser = argparse.ArgumentParser(description="Run ReDD Player trend benchmark")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--variant", type=str, default=DEFAULT_VARIANT, choices=sorted(SUPPORTED_VARIANTS))
    args = parser.parse_args()

    if args.model not in ALLOWED_MODEL_IDS:
        raise RuntimeError(
            "Strict fail-fast: invalid model. "
            f"Expected one of {sorted(ALLOWED_MODEL_IDS)}; got {args.model}"
        )
    if not torch.cuda.is_available():
        raise RuntimeError("Strict fail-fast: CUDA is required for official ReDD local pipeline.")

    ensure_precise_tokenizer_ready()

    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    run_tag = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_BASE_DIR / f"run_{run_tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(run_dir / "query_awareness_trend_redd.log")

    logger.info("Starting Player query-awareness trend test (ReDD)...")
    logger.info(f"Run directory: {run_dir}")
    logger.info(f"Trend query source: {TREND_SQL_FILE}")
    logger.info(f"Source data dir: {SOURCE_DATA_PLAYER_DIR}")
    logger.info(f"Model: {args.model} (canonical={REQUIRED_MODEL_ID})")
    logger.info(f"Variant: {args.variant}")
    logger.info(f"Identity columns (for eval): {IDENTITY_COLUMNS}")
    logger.info("Strict mode: no backend/model fallback; fail fast on query error.")
    logger.info("TDP bridge: using official ReDD DataPopLocal pipeline per query.")
    logger.info("GT isolation: ground truth NEVER provided to extraction pipeline.")

    metadata = {
        "variant": args.variant,
        "model_requested": args.model,
        "model_canonical": REQUIRED_MODEL_ID,
        "backend": "huggingface_local",
        "tdp_path": "official_redd_datapop_local",
        "query_file": str(TREND_SQL_FILE),
        "ground_truth_dir": str(GROUND_TRUTH_DIR),
        "gt_isolation": True,
        "scape_alpha": SCAPE_ALPHA,
        "notes": [
            "This run is strict ReDD variant mode.",
            "No backend/model fallback is allowed in this script.",
            "Tabular data population runs through systems/ReDD/core/data_population/DataPopLocal.",
            "SCAPE/SCAPE-Hyb correction uses systems/ReDD/core/correction modules.",
            "Ground truth is NEVER provided to the extraction model.",
            "GT is used ONLY for (a) SCAPE classifier labels and (b) evaluation metrics.",
        ],
    }
    (run_dir / "method_metadata.json").write_text(json.dumps(metadata, indent=2))

    try:
        metrics = run_trend_queries_redd(run_dir=run_dir, variant=args.variant)
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
        logger.exception(f"ReDD trend test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

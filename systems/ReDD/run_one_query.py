#!/usr/bin/env python3
"""
Run a single SQL query with ReDD extraction and compare against ground truth.

Usage:
  python run_one_query.py --query-id Q1
  python run_one_query.py --query "SELECT ..." [--tables player,team]

This script runs the full ReDD pipeline for ONE query:
  1. Creates query-specific dataset from source documents
  2. Runs DataPopLocal to extract tables with hidden states
  3. Optionally runs SCAPE/SCAPE-Hyb correction
  4. Materializes extracted tables to SQLite
  5. Runs query and compares to gold
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REDD_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(REDD_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from core.data_population import DataPopLocal
from core.data_loader import create_data_loader
from core.correction import ClassifierTrainer, ClassifierVal
from core.utils.constants import PATH_TEMPLATES as REDD_PATHS

GROUND_TRUTH_DB = PROJECT_ROOT / "Data" / "Player" / "player.db"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
SOURCE_DATA_DIR = PROJECT_ROOT / "source_data" / "Player"
QUERY_FILE = PROJECT_ROOT / "Query" / "Player" / "query_aware_trend_queries.sql"

REDD_PROMPT_TABLE = str(REDD_ROOT / "prompts" / "datapop_table_json.txt")
REDD_PROMPT_ATTR = str(REDD_ROOT / "prompts" / "datapop_attr_json.txt")
REDD_PARAM_STR = "redd_run_one_query"

REQUIRED_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
DEFAULT_MODEL_PATH = str(Path(os.getenv("REDD_MODEL_LOCAL_PATH", REDD_ROOT / ".models" / "qwen2_5_7b_instruct")))


def _extract_tables_from_sql(sql: str) -> List[str]:
    """Parse SQL to extract table names from FROM and JOIN clauses."""
    import re
    tables = set()
    pattern = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)|\bJOIN\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
    for m in pattern.finditer(sql):
        t = m.group(1) or m.group(2)
        if t:
            tables.add(t.lower())
    return sorted(tables)


def _load_source_docs(table: str) -> List[Tuple[str, str]]:
    """Load raw text documents for a table. Returns [(doc_id, text), ...]."""
    docs: List[Tuple[str, str]] = []
    table_dir = SOURCE_DATA_DIR / table
    if not table_dir.exists():
        return docs
    for f in sorted(table_dir.glob("*.txt")):
        doc_id = f.stem
        text = f.read_text(encoding="utf-8")
        docs.append((doc_id, text))
    return docs


def _load_gt_rows_by_table(tables: List[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Load ground truth CSVs by table and ID."""
    import pandas as pd
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for table in tables:
        csv_path = GROUND_TRUTH_DIR / f"{table}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, dtype=str).fillna("")
        if "ID" not in df.columns:
            continue
        rows: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            rid = str(row.get("ID", "")).strip()
            if rid:
                rows[rid] = {str(k): ("" if pd.isna(v) else str(v)) for k, v in row.to_dict().items()}
        out[table] = rows
    return out


def _prepare_query_dataset(
    work_dir: Path,
    query_id: str,
    query_sql: str,
    tables: List[str],
) -> Tuple[Path, str, Dict[str, Dict[str, Any]]]:
    """Create ReDD-format dataset for single query. Returns (data_root, dataset_name, did_meta)."""
    dataset_name = f"player_{query_id.lower()}"
    data_root = work_dir / "data" / dataset_name
    data_root.mkdir(parents=True, exist_ok=True)

    # Build SQLite corpus
    db_path = data_root / "documents.db"
    if db_path.exists():
        db_path.unlink()

    gt_by_table = _load_gt_rows_by_table(tables)
    doc_info: Dict[str, Any] = {}
    did_meta: Dict[str, Dict[str, Any]] = {}

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
        idx = 0
        for table in tables:
            for source_doc_id, text in _load_source_docs(table):
                idx += 1
                did = str(idx)
                conn.execute(
                    "INSERT INTO documents (doc_id, doc_text, source_file, parent_doc_id, chunk_index) VALUES (?, ?, ?, ?, ?)",
                    (did, text, table, source_doc_id, 0),
                )
                gt_data = gt_by_table.get(table, {}).get(str(source_doc_id), {})
                doc_info[did] = {"doc": text, "fn": table, "doc_id": did, "data": gt_data}
                did_meta[did] = {"table": table, "source_doc_id": str(source_doc_id), "gt_data": gt_data}
        conn.commit()

    # Write metadata files
    (data_root / "doc_info.json").write_text(json.dumps(doc_info, indent=2))

    # Build schemas from query
    schema_general = []
    for table in tables:
        attrs = [{"Attribute Name": c, "Description": f"{c} in {table}"} for c in gt_by_table.get(table, {}).get(list(gt_by_table.get(table, {}).keys())[0] if gt_by_table.get(table) else "", {}).keys()]
        schema_general.append({"Schema Name": table, "Attributes": attrs})

    (data_root / "schema_general.json").write_text(json.dumps(schema_general, indent=2))
    (data_root / f"schema_query_{query_id}.json").write_text(json.dumps(schema_general, indent=2))

    queries = {
        query_id: {
            "query": f"Query {query_id}",
            "attributes": [],
            "sql": query_sql,
        }
    }
    (data_root / "queries.json").write_text(json.dumps(queries, indent=2))

    # Identity name mapping
    table_map = {t: t for t in tables}
    attr_map = {t: {c: c for c in gt_by_table.get(t, {}).get(list(gt_by_table.get(t, {}).keys())[0] if gt_by_table.get(t) else "", {}).keys()} for t in tables}
    name_map = {"table": table_map, "attribute": attr_map}
    (data_root / REDD_PATHS.eval_name_mapping(query_id)).write_text(json.dumps(name_map, indent=2))

    return data_root, dataset_name, did_meta


def _run_redd_extraction(
    data_root: Path,
    out_main: Path,
    dataset_name: str,
    query_id: str,
    variant: str,
) -> Tuple[Dict[str, Any], Path]:
    """Run DataPopLocal + optional correction. Returns (res_data, db_path)."""
    config = {
        "mode": "local",
        "llm_model": REQUIRED_MODEL_ID,
        "llm_model_path": DEFAULT_MODEL_PATH,
        "res_param_str": REDD_PARAM_STR,
        "prompts": {
            "prompt_table": REDD_PROMPT_TABLE,
            "prompt_attr": REDD_PROMPT_ATTR,
        },
        "data_loader_type": "sqlite",
        "data_main": str(data_root.parent),
        "out_main": str(out_main),
        "exp_dn_fn_list": [dataset_name],
    }

    # Data population
    datapop = DataPopLocal(config)
    datapop([dataset_name])

    out_root = out_main / dataset_name
    res_path = out_root / REDD_PATHS.data_population_result(query_id, REDD_PARAM_STR)
    if not res_path.exists():
        raise RuntimeError(f"Data population failed: {res_path}")
    res_data = json.loads(res_path.read_text())

    # Build eval labels from GT
    did_meta_path = data_root / "doc_info.json"
    did_meta = {k: {"table": v["fn"], "gt_data": v.get("data", {})} for k, v in json.loads(did_meta_path.read_text()).items()}

    eval_output = {}
    for did, meta in did_meta.items():
        pred = res_data.get(did, {})
        table_ok = str(pred.get("res", "")).strip().lower() == meta["table"]
        attr_ok = {}
        for c, gt_v in meta.get("gt_data", {}).items():
            pred_v = pred.get("data", {}).get(c, "")
            attr_ok[c] = str(pred_v).strip().lower() == str(gt_v).strip().lower()
        final_ok = table_ok and all(attr_ok.values())
        eval_output[did] = {"table": table_ok, "attr": attr_ok, "final": final_ok}

    eval_path = out_root / REDD_PATHS.eval_result(query_id, REDD_PARAM_STR)
    eval_path.write_text(json.dumps(eval_output, indent=2))
    (out_root / "queries.json").write_text((data_root / "queries.json").read_text())

    # Correction if requested
    if variant in {"ReDD_SCAPE", "ReDD_SCAPE_Hyb"}:
        hs_dir = out_root / REDD_PATHS.hidden_states_dir(query_id, REDD_PARAM_STR)
        if not hs_dir.exists():
            raise RuntimeError(f"Hidden states required for correction: {hs_dir}")

        # Infer shape from first file
        table_files = list(hs_dir.glob("doc-*-table.pt"))
        if not table_files:
            raise RuntimeError("No hidden state files found")
        sample = torch.load(table_files[0], weights_only=False)
        first_hs = sample[0]["hidden_states"]
        num_layers = int(first_hs.shape[0]) if hasattr(first_hs, "shape") else len(first_hs)
        hidden_dim = int(first_hs.shape[-1]) if hasattr(first_hs, "shape") else len(first_hs[0])
        pooled_dim = hidden_dim * 2
        exp_layers = list(range(max(0, num_layers - 7), num_layers))

        all_dids = sorted(int(d) for d in eval_output.keys())
        train_size = min(32, max(1, len(all_dids) - 1))

        corr_config = {
            "mode": "local",
            "llm_model": REQUIRED_MODEL_ID,
            "llm_model_path": DEFAULT_MODEL_PATH,
            "res_param_str": REDD_PARAM_STR,
            "data_loader_type": "sqlite",
            "data_main": str(data_root.parent),
            "out_main": str(out_main),
            "exp_dn_fn_list": [dataset_name],
            "cls_train_trials": [0],
            "exp_layers": exp_layers,
            "exp_train_sizes": [train_size],
            "train_size": train_size,
            "classifier_threshold": 0.5,
            "num_cells": 0,
            "num_recal": 0,
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

        trainer = ClassifierTrainer(corr_config)
        trainer([dataset_name])

        val = ClassifierVal(corr_config)
        val.cls_train_trial = 0
        val.test_dids = all_dids
        loader = create_data_loader(data_root=data_root, loader_type="sqlite", loader_config={})
        model_dict = val._get_model_dict([dataset_name])
        classifier_outputs = val._get_classifier_outputs(loader, model_dict, str(out_root), query_id, all_dids, eval_output)

        size_key = f"s{train_size}"
        cls_outputs_list = [classifier_outputs[dataset_name][query_id][str(layer)][size_key] for layer in exp_layers]
        voting_mode = "soft" if variant == "ReDD_SCAPE_Hyb" else "half"
        gt_all = {did: (0 if eval_output[str(did)]["final"] else 1) for did in all_dids}
        row_preds, _, _ = val._apply_voting(gt_all, [cls_outputs_list], voting_mode=voting_mode)
        did2error = {str(did): int(pred) for did, pred in zip(all_dids, row_preds)}

        # Apply abstention
        for did, is_error in did2error.items():
            if is_error == 1 and did in res_data:
                res_data[did]["res"] = "None"
                res_data[did]["data"] = {}

    # Build result DB
    db_path = out_main / f"{query_id}_result.db"
    table_cols: Dict[str, Set[str]] = {}
    for did, item in res_data.items():
        table = str(item.get("res", "")).strip().lower()
        if table and table != "none":
            if table not in table_cols:
                table_cols[table] = set()
            table_cols[table].update(item.get("data", {}).keys())

    with sqlite3.connect(db_path) as conn:
        for table, cols in table_cols.items():
            rows = []
            for did, item in res_data.items():
                if str(item.get("res", "")).strip().lower() == table:
                    rows.append({c: item.get("data", {}).get(c) for c in cols})
            if rows:
                import pandas as pd
                df = pd.DataFrame(rows)
                df.to_sql(table, conn, if_exists="replace", index=False)

    return res_data, db_path


def _run_query(conn: sqlite3.Connection, query: str) -> Tuple[List[dict], List[str], float]:
    """Execute query, return (rows, columns, elapsed)."""
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(query)
    rows = cur.fetchall()
    elapsed = time.perf_counter() - t0
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, r)) for r in rows], cols, elapsed


def _compare_rows(gold_rows: List[dict], redd_rows: List[dict], key_cols: List[str]) -> Tuple[int, int, int]:
    """Compare row sets, return (matched, extra, missed)."""
    def _row_key(row):
        return tuple(str(row.get(c, "")).strip().lower() for c in key_cols)

    gold_keys = {_row_key(r) for r in gold_rows}
    redd_keys = {_row_key(r) for r in redd_rows}

    matched = len(gold_keys & redd_keys)
    extra = len(redd_keys - gold_keys)
    missed = len(gold_keys - redd_keys)
    return matched, extra, missed


def _get_query_from_trend(query_id: str) -> Optional[str]:
    """Extract SQL for query_id from trend queries file."""
    if not QUERY_FILE.exists():
        return None
    content = QUERY_FILE.read_text()
    import re
    pattern = rf"--\s*{re.escape(query_id)}[\s\S]*?;"
    m = re.search(pattern, content, re.IGNORECASE)
    if m:
        sql = m.group(0)
        # Remove comments
        lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
        return "\n".join(lines).strip()
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run single query with ReDD extraction")
    ap.add_argument("--query-id", type=str, default="Q1", help="Trend query ID (Q1..Q10)")
    ap.add_argument("--query", "-q", type=str, default="", help="Custom SQL (overrides --query-id)")
    ap.add_argument("--variant", type=str, default="ReDD_SCAPE", choices=["ReDD_NoCorrection", "ReDD_SCAPE", "ReDD_SCAPE_Hyb"])
    ap.add_argument("--work-dir", type=str, default="", help="Working directory for outputs")
    ap.add_argument("--model-path", type=str, default=DEFAULT_MODEL_PATH, help="Path to local model")
    args = ap.parse_args()

    # Get SQL
    if args.query:
        query_sql = args.query.strip()
    else:
        query_sql = _get_query_from_trend(args.query_id)
        if not query_sql:
            print(f"Could not find query {args.query_id} in {QUERY_FILE}")
            return 1

    if not query_sql.endswith(";"):
        query_sql += ";"

    # Setup directories
    if args.work_dir:
        work_dir = Path(args.work_dir)
    else:
        work_dir = Path(os.getenv("REDD_RESULTS_BASE_DIR", PROJECT_ROOT / "results" / "redd_run_one_query"))
    work_dir = work_dir / f"run_{args.query_id.lower()}_{int(time.time())}"
    work_dir.mkdir(parents=True, exist_ok=True)

    out_main = work_dir / "output"
    out_main.mkdir(parents=True, exist_ok=True)

    # Check gold DB
    if not GROUND_TRUTH_DB.exists():
        print(f"Gold database not found: {GROUND_TRUTH_DB}")
        return 1

    print("=" * 70)
    print(f"ReDD Run One Query: {args.query_id}")
    print(f"Variant: {args.variant}")
    print(f"Work dir: {work_dir}")
    print("=" * 70)
    print(f"Query:\n{query_sql}")
    print("=" * 70)

    # Step 1: Prepare dataset
    print("\n[1/4] Preparing dataset...")
    tables = _extract_tables_from_sql(query_sql)
    print(f"  Tables: {tables}")
    data_root, dataset_name, did_meta = _prepare_query_dataset(work_dir, args.query_id, query_sql, tables)
    print(f"  Dataset: {dataset_name}")
    print(f"  Docs: {len(did_meta)}")

    # Step 2: Run ReDD extraction
    print(f"\n[2/4] Running ReDD extraction ({args.variant})...")
    try:
        res_data, db_path = _run_redd_extraction(data_root, out_main, dataset_name, args.query_id, args.variant)
        print(f"  Extracted tables: {list(set(str(item.get('res', 'none')).lower() for item in res_data.values()) - {'none'})}")
        print(f"  Result DB: {db_path}")
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Step 3: Run queries
    print("\n[3/4] Running queries...")
    conn_gold = sqlite3.connect(str(GROUND_TRUTH_DB))
    try:
        gold_rows, gold_cols, gold_time = _run_query(conn_gold, query_sql)
        print(f"  Gold: {len(gold_rows)} rows in {gold_time:.3f}s")
    except Exception as e:
        print(f"  Gold DB error: {e}")
        return 1
    finally:
        conn_gold.close()

    conn_redd = sqlite3.connect(str(db_path))
    try:
        redd_rows, redd_cols, redd_time = _run_query(conn_redd, query_sql)
        print(f"  ReDD: {len(redd_rows)} rows in {redd_time:.3f}s")
    except Exception as e:
        print(f"  ReDD DB error: {e}")
        return 1
    finally:
        conn_redd.close()

    # Step 4: Compare
    print("\n[4/4] Comparison:")
    key_cols = [c for c in ["team_name", "location", "name"] if c in gold_cols] or gold_cols[:2]
    matched, extra, missed = _compare_rows(gold_rows, redd_rows, key_cols)
    print(f"  Matched: {matched}")
    print(f"  Extra:   {extra} (in ReDD, not in gold)")
    print(f"  Missed:  {missed} (in gold, not in ReDD)")

    # Show sample rows
    print("\n--- Gold sample (first 5) ---")
    for r in gold_rows[:5]:
        print(f"  {r}")

    print("\n--- ReDD sample (first 5) ---")
    for r in redd_rows[:5]:
        print(f"  {r}")

    print(f"\nDone. Results in: {work_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

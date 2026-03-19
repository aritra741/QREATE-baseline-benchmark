#!/usr/bin/env python3
"""
Run a single query with ReDD extraction and compare against ground truth.

ReDD takes a NATURAL LANGUAGE query description which drives table resolution
and attribute extraction. The SQL is only used for final execution and evaluation.

Matches WDIRS/SQUiD run_one_query.py behavior:
  - Same default SQL (team player_count with OR conditions)
  - Uses NL description to guide extraction (as per ReDD paper)
  - Creates SQLite DB, runs SQL, compares against gold player.db

Usage:
  python run_one_query.py                              # default NL + SQL
  python run_one_query.py --nl "..." --query "SELECT ..." # custom NL + SQL
"""

import argparse
import json
import os
import re
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

REDD_PROMPT_TABLE = str(REDD_ROOT / "prompts" / "datapop_table_json.txt")
REDD_PROMPT_ATTR = str(REDD_ROOT / "prompts" / "datapop_attr_json.txt")
REDD_PARAM_STR = "redd_run_one"

REQUIRED_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

# Scratch space avoids home-directory quota on HPC.
# Override with REDD_MODEL_LOCAL_PATH env var if needed.
_SCRATCH_BASE = Path("/scratch/general/vast/u1592362")
_DEFAULT_MODEL_DIR = _SCRATCH_BASE / "uda_bench_cache" / "redd_models" / "qwen2_5_7b_instruct"
DEFAULT_MODEL_PATH = str(Path(os.getenv("REDD_MODEL_LOCAL_PATH", str(_DEFAULT_MODEL_DIR))))

# Same query as WDIRS/SQUiD run_one_query.py
DEFAULT_QUERY = """
SELECT t.team_name, t.location,
       COUNT(p.name) as player_count
FROM player p
JOIN team t ON p.team = t.team_name
WHERE p.draft_year > 2000
   OR p.position = 'Frontcourt'
   OR t.founded_year < 1980
GROUP BY t.team_name, t.location, t.founded_year;
""".strip()

# NL description that drives ReDD's table resolver and attribute extractor.
# This is what the paper takes as input — not the SQL.
DEFAULT_NL_QUERY = (
    "For each NBA team, find the team name and city location along with the count of players "
    "who were either drafted after the year 2000, play a Frontcourt position, "
    "or whose team was founded before 1980."
)


def _extract_tables_from_sql(sql: str) -> List[str]:
    """Parse SQL to extract table names from FROM and JOIN clauses."""
    tables = set()
    # Match FROM table or JOIN table (with optional alias)
    pattern = re.compile(
        r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+(?:AS\s+)?[A-Za-z_][A-Za-z0-9_]*)?|\bJOIN\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+(?:AS\s+)?[A-Za-z_][A-Za-z0-9_]*)?",
        re.IGNORECASE
    )
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


def _prepare_dataset(
    work_dir: Path,
    nl_query: str,
    query_sql: str,
    tables: List[str],
) -> Tuple[Path, str, Dict[str, Dict[str, Any]]]:
    """Create ReDD-format dataset. Returns (data_root, dataset_name, did_meta).

    nl_query drives ReDD's table resolver and attribute extractor prompts.
    query_sql is only used for final execution.
    """
    dataset_name = "player_run_one"
    data_root = work_dir / "data" / dataset_name
    data_root.mkdir(parents=True, exist_ok=True)

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

    (data_root / "doc_info.json").write_text(json.dumps(doc_info, indent=2))

    # Build schemas
    schema_general = []
    for table in tables:
        if gt_by_table.get(table):
            first_id = list(gt_by_table[table].keys())[0]
            cols = list(gt_by_table[table][first_id].keys())
            attrs = [{"Attribute Name": c, "Description": f"{c} in {table}"} for c in cols]
            schema_general.append({"Schema Name": table, "Attributes": attrs})

    (data_root / "schema_general.json").write_text(json.dumps(schema_general, indent=2))
    (data_root / "schema_query_run.json").write_text(json.dumps(schema_general, indent=2))

    # "query" here is the NATURAL LANGUAGE description — this is what ReDD's
    # table resolver and attribute extractor receive as their task description.
    queries = {
        "run": {
            "query": nl_query,
            "attributes": [],
            "sql": query_sql,
        }
    }
    (data_root / "queries.json").write_text(json.dumps(queries, indent=2))

    # Identity name mapping
    table_map = {t: t for t in tables}
    attr_map = {}
    for t in tables:
        if gt_by_table.get(t):
            first_id = list(gt_by_table[t].keys())[0]
            cols = list(gt_by_table[t][first_id].keys())
            attr_map[t] = {c: c for c in cols}
    name_map = {"table": table_map, "attribute": attr_map}
    (data_root / REDD_PATHS.eval_name_mapping("run")).write_text(json.dumps(name_map, indent=2))

    return data_root, dataset_name, did_meta


def _committee_label_documents(
    datapop: "DataPopLocal",
    res_data: Dict[str, Any],
    did_meta: Dict[str, Dict[str, Any]],
    table_cols: Dict[str, Set[str]],
    query_data_root: Path,
) -> Dict[str, Any]:
    """Generate Dcls labels via self-consistency committee, per ReDD §3.1.

    The committee is M_TDP (Qwen2.5-7B-Instruct) re-run at temperature=1.0.
    No external API and no ground truth are used — same model throughout for
    a fair, reproducible benchmark.  Labels are recomputed fresh every run so
    they always reflect the current M_TDP extraction output.
    """
    doc_info: Dict[str, Any] = json.loads((query_data_root / "doc_info.json").read_text())
    schema_general: List[Dict[str, Any]] = json.loads(
        (query_data_root / "schema_general.json").read_text()
    )
    table2schema: Dict[str, Any] = {s["Schema Name"]: s for s in schema_general}
    attr_general = [
        {"Schema Name": s["Schema Name"], "Attributes": [a["Attribute Name"] for a in s["Attributes"]]}
        for s in schema_general
    ]
    prompt_table = Path(REDD_PROMPT_TABLE).read_text()
    prompt_attr = Path(REDD_PROMPT_ATTR).read_text()

    def _committee_generate(prompt: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        msg = prompt + "\n\n" + json.dumps(payload, ensure_ascii=False)
        messages = [{"role": "user", "content": msg}]
        chat_inputs = datapop.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        )
        if hasattr(chat_inputs, "get"):
            input_tensor = chat_inputs["input_ids"]
            attention_mask = chat_inputs.get("attention_mask")
        else:
            input_tensor = chat_inputs
            attention_mask = None
        input_tensor = input_tensor.to(datapop.model.device)
        if attention_mask is not None:
            attention_mask = attention_mask.to(datapop.model.device)
        with torch.no_grad():
            gen_kwargs: Dict[str, Any] = dict(
                input_ids=input_tensor,
                max_new_tokens=256,
                do_sample=True,
                temperature=1.0,
            )
            if attention_mask is not None:
                gen_kwargs["attention_mask"] = attention_mask
            outputs = datapop.model.generate(**gen_kwargs)
        gen_tokens = outputs[0][input_tensor.shape[1]:]
        raw = datapop.tokenizer.decode(gen_tokens, skip_special_tokens=True)
        result, _, _ = DataPopLocal._extract_json_block(raw, [])
        return result

    eval_out: Dict[str, Any] = {}
    total = len(did_meta)
    print(f"  [committee] Labeling {total} docs with Qwen2.5-7B at temperature=1.0 …")

    for i, (did, meta) in enumerate(did_meta.items(), 1):
        doc_text: str = doc_info.get(did, {}).get("doc", "")
        m_tdp_result = res_data.get(did, {})
        m_tdp_table: str = str(m_tdp_result.get("res", "")).strip().lower()
        m_tdp_data: Dict[str, Any] = m_tdp_result.get("data", {})
        expected_table: str = str(meta.get("table", "")).strip().lower()
        attrs = sorted(table_cols.get(expected_table, set()))

        comm_tbl_resp = _committee_generate(
            prompt_table, {"Document": doc_text, "Schema": attr_general}
        )
        if comm_tbl_resp is not None and "Table Assignment" in comm_tbl_resp:
            comm_table: str = str(comm_tbl_resp["Table Assignment"]).strip().lower()
        else:
            comm_table = m_tdp_table
        table_ok: bool = comm_table == m_tdp_table

        attr_ok: Dict[str, bool] = {}
        if table_ok:
            tbl_key = comm_table if comm_table in table2schema else expected_table
            for c in attrs:
                comm_attr_resp = _committee_generate(
                    prompt_attr,
                    {
                        "Document": doc_text,
                        "Schema": table2schema.get(tbl_key, table2schema.get(expected_table, {})),
                        "Target Attribute": c,
                    },
                )
                if comm_attr_resp is not None and c in comm_attr_resp:
                    comm_val = str(comm_attr_resp[c]).strip().lower()
                else:
                    comm_val = str(m_tdp_data.get(c, "")).strip().lower()
                attr_ok[c] = comm_val == str(m_tdp_data.get(c, "")).strip().lower()
        else:
            attr_ok = {c: False for c in attrs}

        eval_out[did] = {
            "table": table_ok,
            "attr": attr_ok,
            "final": table_ok and all(attr_ok.values()),
        }
        if i % 20 == 0 or i == total:
            print(f"  [committee] {i}/{total} labeled")

    return eval_out


def _run_redd_pipeline(
    data_root: Path,
    out_main: Path,
    dataset_name: str,
    variant: str,
) -> Tuple[Dict[str, Any], Path]:
    """Run DataPopLocal + optional correction + materialize DB."""
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
    res_path = out_root / REDD_PATHS.data_population_result("run", REDD_PARAM_STR)
    if not res_path.exists():
        raise RuntimeError(f"Data population failed: {res_path}")
    res_data = json.loads(res_path.read_text())

    (out_root / "queries.json").write_text((data_root / "queries.json").read_text())

    # Build SCAPE classifier labels via self-consistency committee (paper §3.1).
    # Only needed for SCAPE/SCAPE-Hyb — same Qwen2.5-7B re-run at temperature=1.0,
    # no external API, no ground truth.
    if variant in {"ReDD_SCAPE", "ReDD_SCAPE_Hyb"}:
        did_meta = {k: {"table": v["fn"]} for k, v in json.loads((data_root / "doc_info.json").read_text()).items()}
        table_cols_local: Dict[str, Set[str]] = {}
        schema_general_local = json.loads((data_root / "schema_general.json").read_text())
        for s in schema_general_local:
            table_cols_local[s["Schema Name"]] = {a["Attribute Name"] for a in s["Attributes"]}
        eval_output = _committee_label_documents(
            datapop=datapop,
            res_data=res_data,
            did_meta=did_meta,
            table_cols=table_cols_local,
            query_data_root=data_root,
        )
        eval_path = out_root / REDD_PATHS.eval_result("run", REDD_PARAM_STR)
        eval_path.write_text(json.dumps(eval_output, indent=2))

    # Correction if requested — mirrors _run_redd_correction in the trend script
    # exactly: SCAPE conformal prediction with train|cells|recal|test partitions.
    if variant in {"ReDD_SCAPE", "ReDD_SCAPE_Hyb"}:
        hs_dir = out_root / REDD_PATHS.hidden_states_dir("run", REDD_PARAM_STR)
        if not hs_dir.exists():
            raise RuntimeError(f"Hidden states required: {hs_dir}")

        table_files = list(hs_dir.glob("doc-*-table.pt"))
        if not table_files:
            raise RuntimeError("No hidden state files found in hidden-states dir")

        # Require both a table.pt AND at least one attr.pt — docs that hit the
        # 32K context limit mid-generation have table.pt but no attr files;
        # LazyHiddenStatesDataset fills those with zeros which corrupts the classifier.
        dids_with_table_hs: set = set()
        for f in table_files:
            try:
                dids_with_table_hs.add(int(f.stem.split("-")[1]))
            except (IndexError, ValueError):
                pass

        dids_with_any_attr_hs: set = set()
        for f in hs_dir.glob("doc-*-attr-*.pt"):
            try:
                dids_with_any_attr_hs.add(int(f.stem.split("-")[1]))
            except (IndexError, ValueError):
                pass

        dids_with_hs = dids_with_table_hs & dids_with_any_attr_hs
        all_dids = sorted(int(d) for d in eval_output.keys() if int(d) in dids_with_hs)
        print(f"  Hidden-state coverage: {len(all_dids)}/{len(eval_output)} docs "
              f"(table={len(dids_with_table_hs)}, attr≥1={len(dids_with_any_attr_hs)})")

        if not all_dids:
            print("  WARNING: no documents with complete hidden states — skipping correction")
        else:
            sample = torch.load(table_files[0], weights_only=False)
            first_hs = sample[0]["hidden_states"]
            num_layers = int(first_hs.shape[0]) if hasattr(first_hs, "shape") else len(first_hs)
            hidden_dim = int(first_hs.shape[-1]) if hasattr(first_hs, "shape") else len(first_hs[0])
            pooled_dim = hidden_dim * 2
            exp_layers = list(range(max(0, num_layers - 7), num_layers))

            train_size = min(50, max(1, len(all_dids) - 1))  # paper default: 50 entries for Dcls §6.1.3
            remaining = len(all_dids) - train_size
            num_cells = min(20, max(5, remaining // 4))
            num_recal = min(40, max(10, remaining // 3))
            if remaining - num_cells - num_recal < 5:
                num_cells = max(3, remaining // 5)
                num_recal = max(5, remaining // 4)
            use_conformal = remaining >= (num_cells + num_recal + 5)

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

            trainer = ClassifierTrainer(corr_config)
            trainer([dataset_name])

            val = ClassifierVal(corr_config)
            val.cls_train_trial = 0
            val.all_dids = all_dids
            val.exp_layers = exp_layers
            val.max_train_did = train_size
            val.max_cells_did = train_size + num_cells
            val.max_recal_did = train_size + num_cells + num_recal
            val.min_test_did = val.max_recal_did
            val.max_test_did = 99999
            val.cell_dids = all_dids[val.max_train_did:val.max_cells_did]
            val.recal_dids = all_dids[val.max_cells_did:val.max_recal_did]
            val.test_dids = all_dids[val.max_recal_did:]
            if not val.test_dids:
                val.test_dids = all_dids[max(0, len(all_dids) * 3 // 4):]

            loader = create_data_loader(data_root=data_root, loader_type="sqlite", loader_config={})
            model_dict = val._get_model_dict([dataset_name])
            classifier_outputs = val._get_classifier_outputs(
                loader, model_dict, str(out_root), "run", all_dids, eval_output
            )

            size_key = f"s{train_size}"
            gt_all = {did: (0 if eval_output[str(did)]["final"] else 1) for did in all_dids}
            layer_outputs = [
                classifier_outputs[dataset_name]["run"][str(layer)][size_key]
                for layer in exp_layers
            ]

            did2error: Dict[str, int] = {}
            if use_conformal:
                did2prediction_sets = val._multi_conformal_prediction(layer_outputs, gt_all, 0.15)  # paper default §6.1.3
                mode = "scape_hyb" if variant == "ReDD_SCAPE_Hyb" else "scape"
                for did in all_dids:
                    if did in did2prediction_sets:
                        pred_set = did2prediction_sets[did]
                        if 1 in pred_set and 0 not in pred_set:
                            did2error[str(did)] = 1
                        elif mode == "scape_hyb" and len(pred_set) > 1:
                            probs = [max(layer_outputs[i].get(str(did), [0.5])) for i in range(len(layer_outputs))]
                            did2error[str(did)] = 1 if sum(probs) / len(probs) >= 0.5 else 0
                        else:
                            did2error[str(did)] = 0
                    else:
                        did2error[str(did)] = 0
            else:
                print("  WARNING: dataset too small for conformal prediction, using soft voting")
                voting_mode = "soft" if variant == "ReDD_SCAPE_Hyb" else "half"
                row_preds, _, _ = val._apply_voting(gt_all, [layer_outputs], voting_mode=voting_mode)
                did2error = {str(did): int(pred) for did, pred in zip(val.test_dids, row_preds)}

            abstained = 0
            for did, is_error in did2error.items():
                if is_error == 1 and did in res_data:
                    res_data[did]["res"] = "None"
                    res_data[did]["data"] = {}
                    abstained += 1
            print(f"  Correction: abstained {abstained}/{len(did2error)} test docs")

    # Materialize to SQLite
    db_path = out_main / "result.db"
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


def _compare(gold_rows: List[dict], redd_rows: List[dict]) -> Tuple[int, int, int]:
    """Compare rows on ALL columns, return (matched, extra, missed).

    A row is 'matched' only when every column value agrees exactly.
    Identity-only matching (ignoring aggregates like player_count) would
    silently accept wrong answers.
    """
    def _row_key(row: dict) -> tuple:
        return tuple(
            (k, str(v).strip().lower())
            for k, v in sorted(row.items())
        )
    gold_keys = [_row_key(r) for r in gold_rows]
    redd_keys = [_row_key(r) for r in redd_rows]
    gold_multiset = {}
    for k in gold_keys:
        gold_multiset[k] = gold_multiset.get(k, 0) + 1
    redd_multiset = {}
    for k in redd_keys:
        redd_multiset[k] = redd_multiset.get(k, 0) + 1
    matched = sum(min(gold_multiset.get(k, 0), cnt) for k, cnt in redd_multiset.items())
    extra = sum(max(0, cnt - gold_multiset.get(k, 0)) for k, cnt in redd_multiset.items())
    missed = sum(max(0, cnt - redd_multiset.get(k, 0)) for k, cnt in gold_multiset.items())
    return matched, extra, missed


def main() -> int:
    ap = argparse.ArgumentParser(description="Run single query with ReDD extraction")
    ap.add_argument("--nl", type=str, default=DEFAULT_NL_QUERY, help="Natural language query description (drives ReDD extraction)")
    ap.add_argument("--query", "-q", type=str, default=DEFAULT_QUERY, help="SQL query (for final execution and evaluation only)")
    ap.add_argument("--variant", type=str, default="ReDD_SCAPE", choices=["ReDD_NoCorrection", "ReDD_SCAPE", "ReDD_SCAPE_Hyb"])
    ap.add_argument("--work-dir", type=str, default="", help="Working directory for outputs")
    ap.add_argument("--model-path", type=str, default=DEFAULT_MODEL_PATH, help="Path to local model")
    args = ap.parse_args()

    nl_query = args.nl.strip()
    query_sql = args.query.strip()
    if not query_sql.endswith(";"):
        query_sql += ";"

    tables = _extract_tables_from_sql(query_sql)

    if args.work_dir:
        work_dir = Path(args.work_dir)
    else:
        work_dir = Path(os.getenv("REDD_RESULTS_BASE_DIR", str(_SCRATCH_BASE / "uda_bench_results" / "redd_run_one")))
    work_dir = work_dir / f"run_{int(time.time())}"
    work_dir.mkdir(parents=True, exist_ok=True)

    out_main = work_dir / "output"
    out_main.mkdir(parents=True, exist_ok=True)

    if not GROUND_TRUTH_DB.exists():
        print(f"Gold database not found: {GROUND_TRUTH_DB}")
        return 1

    print("=" * 70)
    print(f"ReDD Run One Query  [{args.variant}]")
    print(f"NL query: {nl_query}")
    print(f"SQL:      {query_sql[:80]}{'...' if len(query_sql) > 80 else ''}")
    print(f"Tables:   {tables}")
    print(f"Work dir: {work_dir}")
    print("=" * 70)

    # Step 1: Prepare dataset
    print("\n[1/4] Preparing dataset...")
    data_root, dataset_name, did_meta = _prepare_dataset(work_dir, nl_query, query_sql, tables)
    print(f"  Dataset: {dataset_name}")
    print(f"  Documents: {len(did_meta)}")

    # Step 2: Run ReDD extraction
    print(f"\n[2/4] Running ReDD extraction ({args.variant})...")
    try:
        res_data, db_path = _run_redd_pipeline(data_root, out_main, dataset_name, args.variant)
        extracted_tables = list(set(str(item.get("res", "none")).lower() for item in res_data.values()) - {"none"})
        print(f"  Extracted tables: {extracted_tables}")
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
    matched, extra, missed = _compare(gold_rows, redd_rows)
    print(f"  Matched: {matched}")
    print(f"  Extra:   {extra} (in ReDD, not in gold)")
    print(f"  Missed:  {missed} (in gold, not in ReDD)")

    print("\n--- Gold output (first 10) ---")
    print("  ".join(f"{c:>18}" for c in gold_cols))
    print("-" * 70)
    for r in gold_rows[:10]:
        print("  ".join(f"{str(r.get(c, '')):>18}" for c in gold_cols))

    print("\n--- ReDD output (first 10) ---")
    print("  ".join(f"{c:>18}" for c in redd_cols))
    print("-" * 70)
    for r in redd_rows[:10]:
        print("  ".join(f"{str(r.get(c, '')):>18}" for c in redd_cols))

    print(f"\nDone. Results in: {work_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

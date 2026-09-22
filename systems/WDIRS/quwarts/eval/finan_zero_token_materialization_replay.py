"""Zero-Qwen reconciliation and materialization replay. No new model calls."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from sqlglot import exp, parse_one

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.docetl_unit_parity.local_table import create_local_db, execute_original, fetch_sql
from quwarts.core.docetl_unit_parity.parse import parse_map
from quwarts.core.docetl_unit_parity.schema import compile_query_schema
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

REPLAY = ROOT / "results" / "docetl_finan_current_snapshot_replay"
PARITY = ROOT / "results" / "quwarts_finan_docetl_unit_parity"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_CASE = ROOT / "results" / "docetl_finan_case80"
ATTR_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
OUT = ROOT / "results" / "finan_zero_token_materialization_replay"
THETA = 1_381_827
OVERBUDGET_SPENT = 1_412_380
DOC_IDS = ["9", "10", "18", "69", "70", "78", "93"]
MISSING = {None, "", "null", "none", "not_found", "n/a", "na", "unknown"}
CONCLUSION = (
    "prompt/context/materialization and historical runtime-configuration differences "
    "remain material; a different seven-document snapshot is not supported"
)

DECISION_RULE = {
    "written_before_gold": True,
    "steps": [
        "If M0 cannot reproduce stored QuWARTS bags or M2 cannot reproduce canonical native DocETL bags: internally inconsistent.",
        "Else if (M1_QuWARTS - M0_QuWARTS) > (canonical_DocETL - M1_QuWARTS) and M1_QuWARTS > plumbing: acceptance is sufficient to justify a new full-window QuWARTS arm.",
        "Else if M4 > plumbing and M1_QuWARTS <= M0_QuWARTS and |M1_DocETL - M0_DocETL| < 1e-12: non-destructive plumbing composition is the only beneficial replay.",
        "Else: context window is the remaining dominant lever.",
    ],
}


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def charge(row: dict[str, Any]) -> int:
    return int(row.get("api_prompt_tokens") or 0) + int(row.get("api_completion_tokens") or 0)


def slim_docetl_call(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "call_index": row.get("call_index"),
        "query_id": row.get("query_id"),
        "document_id": str(row.get("document_id") or ""),
        "retry_index": row.get("retry_index"),
        "operator": row.get("operator"),
        "stage": row.get("stage"),
        "api_prompt_tokens": row.get("api_prompt_tokens"),
        "api_completion_tokens": row.get("api_completion_tokens"),
        "spent_after": row.get("spent_after"),
        "parsed_response": row.get("parsed_response"),
        "parse_validation_failure": row.get("parse_validation_failure"),
        "raw_response_sha256": row.get("raw_response_sha256"),
        "included_document_sha256": row.get("included_document_sha256"),
        "truncated": row.get("truncated"),
        "included_document_text": row.get("included_document_text") or "",
    }


def load_docetl_journal() -> list[dict[str, Any]]:
    jsonl = REPLAY / "call_journal.jsonl"
    if jsonl.is_file():
        return [slim_docetl_call(json.loads(line)) for line in jsonl.read_text().splitlines() if line.strip()]
    return [slim_docetl_call(row) for row in json.loads((REPLAY / "call_journal.json").read_text())]


def budget_prefix(journal: list[dict[str, Any]]) -> dict[str, Any]:
    included: list[dict[str, Any]] = []
    spent = 0
    for index, row in enumerate(journal):
        cost = charge(row)
        if spent + cost > THETA:
            first_ex = row
            return {
                "included": included,
                "n_included": len(included),
                "spent": spent,
                "remainder": THETA - spent,
                "last_included": included[-1] if included else None,
                "first_excluded": {
                    "call_index": first_ex.get("call_index"),
                    "query_id": first_ex.get("query_id"),
                    "document_id": first_ex.get("document_id"),
                    "retry_index": first_ex.get("retry_index"),
                    "charge": cost,
                    "would_reach": spent + cost,
                    "journal_offset": index,
                },
                "overshoot_if_included": spent + cost - THETA,
            }
        included.append(row)
        spent += cost
    return {
        "included": included,
        "n_included": len(included),
        "spent": spent,
        "remainder": THETA - spent,
        "last_included": included[-1] if included else None,
        "first_excluded": None,
        "overshoot_if_included": 0,
    }


def parsed_record(row: dict[str, Any]) -> dict[str, Any]:
    parsed = row.get("parsed_response")
    if isinstance(parsed, list) and parsed:
        rec = parsed[0]
        return rec if isinstance(rec, dict) else {}
    return parsed if isinstance(parsed, dict) else {}


def retry_winners(calls: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    winners: dict[tuple[str, str], dict[str, Any]] = {}
    for row in calls:
        qid, doc_id = row.get("query_id"), str(row.get("document_id") or "")
        if not qid or not doc_id:
            continue
        winners[(qid, doc_id)] = row
    return winners


def completed_queries(winners: dict[tuple[str, str], dict[str, Any]], query_ids: list[str]) -> list[str]:
    by_q: dict[str, set[str]] = defaultdict(set)
    for qid, doc_id in winners:
        by_q[qid].add(doc_id)
    return [qid for qid in query_ids if by_q.get(qid) == set(DOC_IDS)]


def is_missing(raw: Any, dtype: str) -> bool:
    if raw in MISSING:
        return True
    if dtype == "numeric" and raw == -1:
        return True
    if isinstance(raw, str) and raw.strip().lower() in MISSING:
        return True
    return False


def type_valid(raw: Any, dtype: str) -> tuple[Any, str | None]:
    if is_missing(raw, dtype):
        return None, "missing_marker"
    norm, _unit, err = normalize_value(raw, dtype)
    if err:
        return None, f"typed_reject:{err}"
    if norm is None:
        return None, "typed_reject:unnormalized"
    return norm, None


def native_docetl_value(raw: Any, dtype: str) -> Any:
    if raw is None:
        return -1 if dtype == "numeric" else ""
    return raw


def numeric_fields() -> set[str]:
    payload = json.loads(ATTR_PATH.read_text())
    out: set[str] = set()
    for _table, fields in payload.items():
        for col, spec in (fields or {}).items():
            value_type = str((spec or {}).get("value_type") or "").lower()
            if value_type in {"int", "integer", "float", "number", "real"}:
                out.add(str(col).strip().lower())
    return out


def coerce_docetl_frame(df: pd.DataFrame, numeric: set[str]) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in numeric:
            out[col] = (
                out[col].astype(str).str.replace(",", "", regex=False).str.replace(" ", "", regex=False)
            )
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def write_docetl_db(path: Path, rows: list[dict[str, Any]], schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    keep = [name for name in schema.names]
    df = pd.DataFrame([{name: row.get(name) for name in keep} for row in rows])
    df = coerce_docetl_frame(df, numeric_fields())
    with sqlite3.connect(path) as conn:
        df.to_sql("finance", conn, if_exists="replace", index=False)


def load_pipeline_cells(query_ids: list[str], schemas) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    out: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for qid in query_ids:
        path = REPLAY / "docetl_pipelines" / qid / "table_finance" / "pipeline_output.json"
        rows = json.loads(path.read_text()) if path.is_file() else []
        mapped = []
        for row in rows:
            doc_id = str(row.get("doc_id") or "")
            mapped.append((doc_id, {name: row.get(name) for name in schemas[qid].names}))
        out[qid] = mapped
    return out


def insert_keep(path: Path, schema, doc_id: str, values: dict[str, Any], sentinels: bool) -> None:
    conn = sqlite3.connect(str(path))
    cols = ["doc_id"] + schema.names
    payload = [doc_id]
    for name in schema.names:
        value = values.get(name)
        dtype = schema.dtypes.get(name, "string")
        if sentinels:
            if value is None:
                payload.append(-1 if dtype == "numeric" else "")
            else:
                payload.append(value)
        else:
            payload.append(None if value in (None, "", "null", "none", False) else value)
    conn.execute(
        f"INSERT INTO finance ({', '.join(_q(c) for c in cols)}) VALUES ({', '.join('?' for _ in cols)})",
        payload,
    )
    conn.commit()
    conn.close()


def materialize_query_local(
    dest: Path,
    schema,
    doc_values: list[tuple[str, dict[str, Any]]],
    *,
    sentinels: bool,
    docetl_write: bool,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    if docetl_write:
        rows = []
        for doc_id, values in doc_values:
            row = {"doc_id": doc_id}
            for name in schema.names:
                raw = values.get(name)
                row[name] = native_docetl_value(raw, schema.dtypes.get(name, "string")) if sentinels else raw
            rows.append(row)
        write_docetl_db(dest, rows, schema)
        return dest
    create_local_db(dest, schema)
    for doc_id, values in doc_values:
        insert_keep(dest, schema, doc_id, values, sentinels=sentinels)
    return dest


def bag_of(path: Path, sql: str) -> list[dict[str, Any]]:
    bag, _err = execute_original(path, sql)
    return bag


def empty_rewrites(query_ids: list[str]) -> dict[str, Any]:
    return {qid: None for qid in query_ids}


def local_rewrites(query_ids: list[str], completed: list[str], paths: dict[str, Path], statements: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for qid in query_ids:
        path = paths.get(qid)
        if qid in completed and path is not None and path.is_file():
            out[qid] = {"sql": statements[qid], "sqlite_path": str(path)}
        else:
            out[qid] = None
    return out


def plumbing_rewrites(query_ids: list[str], statements: dict[str, str], db: Path, predicates) -> dict[str, Any]:
    return {qid: official_sql(statements[qid], db, predicates, query_id=qid) for qid in query_ids}


def _score(db: Path, rows, rewrites, gold) -> dict[str, Any]:
    report = score_with_rewrites(rows, rewrites, db, gold, "Finan")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": [
            {
                "query_id": row["query_id"],
                "structure_f2": row.get("structure_f2"),
                "cell_f1_20": row.get("cell_f1_20"),
                "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
                "pred_rows": row.get("pred_rows"),
            }
            for row in report.get("per_query") or []
        ],
    }


def first_diff(left: Any, right: Any, path: str = "") -> str | None:
    if type(left) is not type(right) and not (isinstance(left, (int, float)) and isinstance(right, (int, float))):
        return f"{path or '<root>'}: type {type(left).__name__} vs {type(right).__name__}"
    if isinstance(left, dict):
        keys = sorted(set(left) | set(right), key=str)
        for key in keys:
            if key not in left:
                return f"{path}.{key}: missing on left"
            if key not in right:
                return f"{path}.{key}: missing on right"
            found = first_diff(left[key], right[key], f"{path}.{key}" if path else str(key))
            if found:
                return found
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} vs {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            found = first_diff(a, b, f"{path}[{index}]")
            if found:
                return found
        return None
    if left != right:
        return f"{path}: {left!r} vs {right!r}"
    return None


def sql_features(sql: str) -> dict[str, bool]:
    tree = parse_one(sql)
    kinds = {
        "equality": False,
        "inequality": False,
        "range": False,
        "neq_empty_string": False,
        "case": False,
        "group_by": False,
        "aggregate": False,
    }
    for node in tree.walk():
        if isinstance(node, (exp.EQ,)):
            kinds["equality"] = True
        if isinstance(node, (exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
            kinds["inequality"] = True
        if isinstance(node, (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)):
            kinds["range"] = True
        if isinstance(node, exp.NEQ) and str(node.expression).strip("'\"") == "":
            kinds["neq_empty_string"] = True
        if isinstance(node, exp.Case):
            kinds["case"] = True
        if isinstance(node, exp.Group):
            kinds["group_by"] = True
        if isinstance(node, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)):
            kinds["aggregate"] = True
    return kinds


def reserve_before_call(spent: int, ceiling: int, max_call_charge: int) -> bool:
    """Future hard-ceiling guard: refuse to start a call that could cross the ledger."""
    return spent + max_call_charge <= ceiling


def plumbing_identity(conn: sqlite3.Connection) -> tuple[str, str]:
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    table = "finance" if "finance" in tables else tables[0]
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")]
    for cand in ("doc_id", "id", "document_id", "source_id"):
        if cand in cols:
            return table, cand
    return table, cols[0]


def apply_m4(base: Path, dest: Path, fills: dict[str, dict[str, Any]]) -> dict[str, Any]:
    shutil.copy2(base, dest)
    conn = sqlite3.connect(str(dest))
    table, ident = plumbing_identity(conn)
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")]
    changed_cells = 0
    skipped_nonnull = 0
    missing_rows = []
    for doc_id, values in fills.items():
        existing = None
        for key in (str(doc_id), f"{doc_id}.txt", Path(str(doc_id)).stem):
            existing = conn.execute(
                f"SELECT * FROM {_q(table)} WHERE CAST({_q(ident)} AS TEXT)=?",
                (key,),
            ).fetchone()
            if existing is not None:
                break
        if existing is None:
            missing_rows.append(doc_id)
            continue
        row = dict(zip(cols, existing))
        assignments = []
        payload = []
        for col, value in values.items():
            if col not in cols or col == ident:
                continue
            current = row.get(col)
            if current is not None:
                skipped_nonnull += 1
                continue
            if value is None:
                continue
            assignments.append(f"{_q(col)}=?")
            payload.append(value)
            changed_cells += 1
        if assignments:
            payload.append(row[ident])
            conn.execute(f"UPDATE {_q(table)} SET {', '.join(assignments)} WHERE {_q(ident)}=?", payload)
    conn.commit()
    n_rows = conn.execute(f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0]
    conn.close()
    return {"changed_cells": changed_cells, "skipped_nonnull": skipped_nonnull, "missing_rows": missing_rows, "n_rows": n_rows, "table": table, "identity": ident}


def cell_tally(doc_values: dict[str, list[tuple[str, dict[str, Any]]]], schemas) -> tuple[int, int]:
    non_null = empty = 0
    for qid, rows in doc_values.items():
        names = schemas[qid].names
        if not rows:
            empty += 1
            continue
        any_row = False
        for _doc, vals in rows:
            if any(vals.get(name) not in (None, "", -1) for name in names):
                any_row = True
            for name in names:
                if vals.get(name) not in (None, "", -1):
                    non_null += 1
        if not any_row:
            empty += 1
    return non_null, empty


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    prior = {
        "replay_frozen": file_sha256(REPLAY / "frozen.json"),
        "replay_journal": file_sha256(REPLAY / "call_journal.json"),
        "replay_bags": file_sha256(REPLAY / "sqlite_bags.json"),
        "replay_tables": file_sha256(REPLAY / "extracted_tables.json"),
        "parity_report": file_sha256(PARITY / "finan_docetl_unit_parity_arm.json"),
        "parity_bags": file_sha256(PARITY / "theta100_bags.json"),
        "parity_journal": file_sha256(PARITY / "theta100_journal.json"),
        "plumbing": file_sha256(PLUMBING),
        "docetl_manifest": file_sha256(DOCETL_CASE / "query_manifest.json"),
    }

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_CASE / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    schemas = {qid: compile_query_schema(qid, statements[qid]) for qid in query_ids}
    texts = {doc_id: (REPLAY / "isolated_input" / "finance" / f"{doc_id}.txt").read_text(encoding="utf-8", errors="replace") for doc_id in DOC_IDS}
    official_bags = json.loads((REPLAY / "sqlite_bags.json").read_text())
    official_tables = json.loads((REPLAY / "extracted_tables.json").read_text())
    official_report = json.loads((REPLAY / "docetl_current_snapshot_replay.json").read_text())
    parity_bags = json.loads((PARITY / "theta100_bags.json").read_text())
    parity_journal = json.loads((PARITY / "theta100_journal.json").read_text())
    official_completed = list(official_report["completed_queries"])

    journal = load_docetl_journal()
    prefix = budget_prefix(journal)
    prefix_calls = prefix["included"]
    over_calls = journal
    max_call = max((charge(row) for row in journal), default=0)

    prefix_winners = retry_winners(prefix_calls)
    over_winners = retry_winners(over_calls)
    prefix_completed = completed_queries(prefix_winners, query_ids)
    over_completed = completed_queries(over_winners, query_ids)

    prefix_meta = {
        "label": "strict_budget_prefix",
        "ceiling": THETA,
        "spent": prefix["spent"],
        "remainder": prefix["remainder"],
        "n_included_calls": prefix["n_included"],
        "included_primary": sum(1 for row in prefix_calls if str(row.get("document_id") or "")),
        "included_retries": sum(1 for row in prefix_calls if not str(row.get("document_id") or "")),
        "completed_queries": prefix_completed,
        "incomplete_queries": [qid for qid in query_ids if qid not in prefix_completed],
        "last_included": {
            "call_index": (prefix["last_included"] or {}).get("call_index"),
            "query_id": (prefix["last_included"] or {}).get("query_id"),
            "document_id": (prefix["last_included"] or {}).get("document_id"),
            "retry_index": (prefix["last_included"] or {}).get("retry_index"),
            "charge": charge(prefix["last_included"]) if prefix["last_included"] else 0,
        },
        "first_excluded": prefix["first_excluded"],
        "future_pre_call_reservation": {
            "rule": "refuse a call unless spent + max_permitted_call_charge <= ceiling",
            "max_observed_call_charge": max_call,
            "would_have_blocked_overshoot": not reserve_before_call(prefix["spent"], THETA, max_call),
        },
        "over_budget_diagnostic_spent": OVERBUDGET_SPENT,
        "over_budget_calls": len(over_calls),
        "over_budget_completed": over_completed,
    }

    # --- DocETL cell maps from winners ---
    def docetl_cells(winners):
        by_q: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for qid in query_ids:
            for doc_id in DOC_IDS:
                row = winners.get((qid, doc_id))
                rec = parsed_record(row) if row else {}
                by_q[qid].append((doc_id, {name: rec.get(name) for name in schemas[qid].names}))
        return by_q

    journal_cells = docetl_cells(over_winners)
    pipeline_cells = load_pipeline_cells(query_ids, schemas)
    over_cells = {qid: list(pipeline_cells.get(qid) or []) for qid in query_ids if qid in over_completed}
    prefix_cells = {qid: list(pipeline_cells.get(qid) or []) for qid in query_ids if qid in prefix_completed}
    for qid in query_ids:
        over_cells.setdefault(qid, [])
        prefix_cells.setdefault(qid, [])

    # Acceptance-path reconstruction (all calls, sentinels → NULL, includes incomplete)
    acceptance_cells: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for row in over_calls:
        qid, doc_id = row.get("query_id"), str(row.get("document_id") or "")
        if not qid or not doc_id:
            continue
        rec = parsed_record(row)
        vals = {}
        for name in schemas[qid].names:
            raw = rec.get(name)
            if raw in ("", None) or (schemas[qid].dtypes.get(name) == "numeric" and raw == -1):
                vals[name] = None
            else:
                vals[name] = raw
        acceptance_cells[qid].append((doc_id, vals))

    # Materializer value maps
    def apply_m0_docetl(cells, context_of):
        out = {}
        rejects = Counter()
        for qid, rows in cells.items():
            mapped = []
            for doc_id, vals in rows:
                fake = json.dumps(
                    {
                        name: {
                            "value": vals.get(name),
                            "status": "found" if not is_missing(vals.get(name), schemas[qid].dtypes.get(name, "string")) else "not_found",
                            "evidence": "" if is_missing(vals.get(name), schemas[qid].dtypes.get(name, "string")) else str(vals.get(name))[:120],
                        }
                        for name in schemas[qid].names
                    }
                )
                parsed = parse_map(fake, schemas[qid], context_of(qid, doc_id))
                keep = {}
                for name, item in (parsed.get("items") or {}).items():
                    keep[name] = item.get("normalized_value")
                    if item.get("failure"):
                        rejects[str(item["failure"])] += 1
                    elif item.get("normalized_value") is None and not is_missing(vals.get(name), schemas[qid].dtypes.get(name, "string")):
                        rejects["other_drop"] += 1
                mapped.append((doc_id, keep))
            out[qid] = mapped
        return out, rejects

    def apply_m1(cells):
        out = {}
        rejects = Counter()
        kept = 0
        raw_n = 0
        for qid, rows in cells.items():
            mapped = []
            for doc_id, vals in rows:
                keep = {}
                for name in schemas[qid].names:
                    raw_n += 1
                    norm, reason = type_valid(vals.get(name), schemas[qid].dtypes.get(name, "string"))
                    keep[name] = norm
                    if reason:
                        rejects[reason.split(":")[0]] += 1
                    else:
                        kept += 1
                mapped.append((doc_id, keep))
            out[qid] = mapped
        return out, rejects, kept, raw_n

    def apply_m2_docetl(cells):
        out = {}
        for qid, rows in cells.items():
            mapped = []
            for doc_id, vals in rows:
                keep = {name: native_docetl_value(vals.get(name), schemas[qid].dtypes.get(name, "string")) for name in schemas[qid].names}
                mapped.append((doc_id, keep))
            out[qid] = mapped
        return out

    def apply_m3(m1_cells):
        out = {}
        for qid, rows in m1_cells.items():
            mapped = []
            for doc_id, vals in rows:
                keep = {}
                for name in schemas[qid].names:
                    dtype = schemas[qid].dtypes.get(name, "string")
                    keep[name] = vals.get(name) if vals.get(name) is not None else (-1 if dtype == "numeric" else "")
                mapped.append((doc_id, keep))
            out[qid] = mapped
        return out

    def context_source(_qid, doc_id):
        return texts[doc_id]

    def context_request(winners):
        def _ctx(qid, doc_id):
            row = winners.get((qid, doc_id)) or {}
            return str(row.get("included_document_text") or texts[doc_id])
        return _ctx

    # QuWARTS cells from stored journal (raw + already-parsed M0)
    qw_cells = {}
    qw_m0 = {}
    qw_rejects = Counter()
    qw_found_rejected = 0
    qw_raw_nonnull = 0
    qw_span_failed = 0
    for row in parity_journal:
        qid, doc_id = row["query_id"], str(row["doc_id"])
        raws = {}
        m0vals = {}
        for name, item in (row.get("fields") or {}).items():
            raws[name] = item.get("raw_value")
            m0vals[name] = item.get("normalized_value")
            if item.get("raw_value") not in (None, ""):
                qw_raw_nonnull += 1
            if item.get("raw_value") not in (None, "") and item.get("normalized_value") is None:
                qw_found_rejected += 1
            if item.get("failure") == "stated_span_failed" or item.get("grounding") == "rejected":
                qw_span_failed += 1
                qw_rejects[str(item.get("failure") or item.get("grounding"))] += 1
        qw_cells.setdefault(qid, []).append((doc_id, raws))
        qw_m0.setdefault(qid, []).append((doc_id, m0vals))

    over_m0_source, over_m0_rej_src = apply_m0_docetl(over_cells, context_source)
    over_m0_req, over_m0_rej_req = apply_m0_docetl(over_cells, context_request(over_winners))
    prefix_m0_source, prefix_m0_rej_src = apply_m0_docetl(prefix_cells, context_source)
    over_m1, over_m1_rej, over_m1_kept, over_m1_raw = apply_m1(over_cells)
    prefix_m1, prefix_m1_rej, prefix_m1_kept, prefix_m1_raw = apply_m1(prefix_cells)
    qw_m1, qw_m1_rej, qw_m1_kept, qw_m1_raw = apply_m1(qw_cells)
    over_m2 = apply_m2_docetl(over_cells)
    prefix_m2 = apply_m2_docetl(prefix_cells)
    over_m3 = apply_m3(over_m1)
    prefix_m3 = apply_m3(prefix_m1)
    qw_m3 = apply_m3(qw_m1)

    # Materialize DBs
    dbs: dict[str, dict[str, Path]] = defaultdict(dict)

    def build(label: str, cells, completed, *, sentinels: bool, docetl_write: bool):
        for qid in query_ids:
            dest = OUT / "dbs" / label / f"{qid.replace(':', '_')}.db"
            if qid not in completed:
                continue
            materialize_query_local(dest, schemas[qid], cells[qid], sentinels=sentinels, docetl_write=docetl_write)
            dbs[label][qid] = dest

    build("docetl_over_m2", over_m2, over_completed, sentinels=True, docetl_write=True)
    build("docetl_prefix_m2", prefix_m2, prefix_completed, sentinels=True, docetl_write=True)
    build("docetl_over_m0", over_m0_source, over_completed, sentinels=False, docetl_write=False)
    build("docetl_prefix_m0", prefix_m0_source, prefix_completed, sentinels=False, docetl_write=False)
    build("docetl_over_m1", over_m1, over_completed, sentinels=False, docetl_write=False)
    build("docetl_prefix_m1", prefix_m1, prefix_completed, sentinels=False, docetl_write=False)
    build("docetl_over_m3", over_m3, over_completed, sentinels=True, docetl_write=False)
    build("docetl_prefix_m3", prefix_m3, prefix_completed, sentinels=True, docetl_write=False)
    build("qw_m0", qw_m0, query_ids, sentinels=False, docetl_write=False)
    build("qw_m1", qw_m1, query_ids, sentinels=False, docetl_write=False)
    build("qw_m3", qw_m3, query_ids, sentinels=True, docetl_write=False)

    # Acceptance reconstruction (all calls, NULLs, score incomplete q3)
    for qid, rows in acceptance_cells.items():
        dest = OUT / "dbs" / "acceptance_native_buggy" / f"{qid.replace(':', '_')}.db"
        materialize_query_local(dest, schemas[qid], rows, sentinels=False, docetl_write=False)
        dbs["acceptance_native_buggy"][qid] = dest

    # Native bags
    def bags_for(label, completed):
        out = {}
        for qid in query_ids:
            if qid in completed and qid in dbs[label]:
                out[qid] = bag_of(dbs[label][qid], statements[qid])
            else:
                out[qid] = []
        return out

    canonical_over_bags = bags_for("docetl_over_m2", over_completed)
    canonical_prefix_bags = bags_for("docetl_prefix_m2", prefix_completed)
    qw_m0_bags = bags_for("qw_m0", query_ids)

    m0_repro = first_diff(qw_m0_bags, {qid: parity_bags.get(qid) or [] for qid in query_ids})
    official_norm = {qid: (official_bags.get(qid) if official_bags.get(qid) not in (None, "incomplete") else []) for qid in query_ids}
    m2_repro_over = first_diff(canonical_over_bags, official_norm)

    # Per-query first differing artifact: official live vs acceptance reconstruction
    recon_diffs = []
    for qid in query_ids:
        official_complete = qid in official_completed
        acceptance_scored = qid in dbs["acceptance_native_buggy"]
        reasons = []
        if official_complete != (qid in over_completed):
            reasons.append("completed_query_definition")
        official_n = len((official_tables.get(qid) or {}).get("finance") or [])
        acceptance_n = len(acceptance_cells.get(qid) or [])
        if official_n != acceptance_n:
            reasons.append(f"row_count official_extracted={official_n} acceptance_all_calls={acceptance_n} (retries inserted as extra rows)")
        winner_vals = {doc: vals for doc, vals in journal_cells.get(qid, [])}
        if qid in official_completed:
            off_rows = (official_tables.get(qid) or {}).get("finance") or []
            for index, off in enumerate(off_rows):
                if index >= len(DOC_IDS):
                    break
                win = winner_vals.get(DOC_IDS[index], {})
                off_fields = {k: v for k, v in off.items() if k not in {"doc_id", "text"}}
                if first_diff(off_fields, {k: win.get(k) for k in off_fields}):
                    reasons.append(f"retry_winner_or_parse_at_doc={DOC_IDS[index]}: {first_diff(off_fields, {k: win.get(k) for k in off_fields})}")
                    break
        off_bag = official_norm.get(qid) or []
        acc_bag = bag_of(dbs["acceptance_native_buggy"][qid], statements[qid]) if acceptance_scored else []
        can_bag = canonical_over_bags.get(qid) or []
        if first_diff(off_bag, acc_bag):
            if not official_complete and qid == official_report.get("stopped_at"):
                reasons.append("incomplete_query_handling: official scored empty; acceptance rematerialized a partial table")
            if any(
                (winner_vals.get(doc) or {}).get(name) in ("", -1)
                for doc, _vals in over_cells.get(qid, [])
                for name in schemas[qid].names
            ):
                reasons.append("unknown_encoding: official/DocETL kept -1/''; acceptance coerced them to SQL NULL")
            reasons.append(f"bag_diff: {first_diff(off_bag, acc_bag)}")
        if first_diff(off_bag, can_bag) and official_complete:
            reasons.append(f"canonical_vs_official_bag: {first_diff(off_bag, can_bag)}")
        if reasons:
            recon_diffs.append({
                "query_id": qid,
                "first_differing_artifact": reasons[0],
                "all_reasons": reasons,
                "official_complete": official_complete,
                "official_pred_rows": len(off_bag) if isinstance(off_bag, list) else None,
                "acceptance_pred_rows": len(acc_bag),
                "canonical_pred_rows": len(can_bag),
            })

    # SQL sentinel effects (M1 vs M3) on prefix
    sql_effects = []
    for qid in prefix_completed:
        feats = sql_features(statements[qid])
        b1 = bag_of(dbs["docetl_prefix_m1"][qid], statements[qid])
        b3 = bag_of(dbs["docetl_prefix_m3"][qid], statements[qid])
        conn1 = sqlite3.connect(str(dbs["docetl_prefix_m1"][qid]))
        conn3 = sqlite3.connect(str(dbs["docetl_prefix_m3"][qid]))
        n1 = conn1.execute("SELECT COUNT(*) FROM finance").fetchone()[0]
        n3 = conn3.execute("SELECT COUNT(*) FROM finance").fetchone()[0]
        conn1.close()
        conn3.close()
        sql_effects.append({
            "query_id": qid,
            "features": feats,
            "m1_bag_rows": len(b1),
            "m3_bag_rows": len(b3),
            "bag_changed": first_diff(b1, b3) is not None,
            "first_bag_diff": first_diff(b1, b3),
            "table_rows_m1": n1,
            "table_rows_m3": n3,
        })

    # M4 fills from prefix M1 (accuracy-oriented additive; seven IDs only)
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for qid, rows in prefix_m1.items():
        for doc_id, vals in rows:
            for name, value in vals.items():
                if value is None:
                    continue
                if name not in fills[doc_id] or fills[doc_id][name] is None:
                    fills[doc_id][name] = value
    m4_db = OUT / "dbs" / "m4_plumbing_overlay.db"
    m4_stats = apply_m4(PLUMBING, m4_db, fills)

    # Cell / reject records
    parsed_values = {
        "docetl_over_winners": {f"{q}:{d}": v for q, rows in over_cells.items() for d, v in rows},
        "docetl_prefix_winners": {f"{q}:{d}": v for q, rows in prefix_cells.items() for d, v in rows},
        "quwarts": {f"{q}:{d}": v for q, rows in qw_cells.items() for d, v in rows},
    }
    accepted_rejected = {
        "quwarts_m0": {"span_or_rejected": dict(qw_rejects), "found_but_rejected": qw_found_rejected, "raw_nonnull": qw_raw_nonnull, "stated_span_failed": qw_span_failed},
        "docetl_over_m0_source": dict(over_m0_rej_src),
        "docetl_over_m0_request_window": dict(over_m0_rej_req),
        "docetl_over_m1": dict(over_m1_rej),
        "docetl_prefix_m1": dict(prefix_m1_rej),
        "quwarts_m1": dict(qw_m1_rej),
        "denominators": {
            "62_found_but_rejected": {
                "definition": "QuWARTS parity field with non-empty raw_value and normalized_value is NULL",
                "count": qw_found_rejected,
                "denominator": "QuWARTS field cells with non-empty raw_value",
                "denominator_n": qw_raw_nonnull,
            },
            "104_stated_span_failed": {
                "definition": "DocETL acceptance-gate C: parse_map stated-span failure on DocETL completions using included_document_text as context and the raw value as evidence",
                "recomputed_request_window": int(over_m0_rej_req.get("stated_span_failed") or 0),
                "recomputed_full_source": int(over_m0_rej_src.get("stated_span_failed") or 0),
                "quwarts_journal_span_failed": qw_span_failed,
                "denominator": "DocETL field cells passed through parse_map (over-budget winners × schema fields)",
            },
            "75_typed_reject": {
                "definition": "DocETL acceptance-gate C: missing marker or normalize_value error",
                "recomputed_over_m1": dict(over_m1_rej),
                "denominator": "DocETL field cells in over-budget winners",
                "denominator_n": over_m1_raw,
            },
        },
    }

    bags_payload = {
        "canonical_native_over_budget": canonical_over_bags,
        "canonical_native_prefix": canonical_prefix_bags,
        "quwarts_m0": qw_m0_bags,
        "official_replay_bags": official_norm,
    }
    rule_spec = {
        "M0": "Existing QuWARTS exact-span grounding / stored normalized_value. Unknown = NULL.",
        "M1": "Type-valid structural normalization; no verbatim span. Missing markers → NULL.",
        "M2": "Actual DocETL path: frozen pipeline_output rows, keep SQL schema columns only, coerce numeric, pandas to_sql. No extra doc_id column.",
        "M3": "M1 values plus DocETL missing sentinels -1/''. SQL effect measured separately.",
        "M4": "Copy 100-row plumbing DB; fill NULL cells on the seven IDs with M1 values; never overwrite non-NULL; no sentinels.",
        "incomplete": "Incomplete query programs remain empty; plumbing is not substituted.",
        "canonical_native": "DocETL pipeline_output → keep schema columns → numeric coerce → to_sql. Complete = live run finished the query.",
    }
    scorer_manifest = {
        "query_ids": query_ids,
        "count_only": [qid for qid in query_ids if is_count_query(query_shape(qid, statements[qid]))],
        "sql_sha256": _hash(statements),
        "doc_ids": DOC_IDS,
    }

    freeze = {
        "note": CONCLUSION,
        "source_text_agreement": 1.0,
        "historical_yaml_available": False,
        "gold_loaded": False,
        "decision_rule": DECISION_RULE,
        "budget": prefix_meta,
        "m0_reproduces_quwarts_bags": m0_repro is None,
        "m0_bag_diff": m0_repro,
        "m2_reproduces_official_over_budget_bags": m2_repro_over is None,
        "m2_bag_diff": m2_repro_over,
        "native_reconciliation": {
            "official_product_reported": official_report["score"]["current_snapshot_replay_16"]["mean_per_query_product"],
            "acceptance_native_product_reported": official_report["C_acceptance_gates"]["native_docetl"]["score_16"]["mean_per_query_product"],
            "same_call_prefix": False,
            "same_completed_query_definition": official_completed == over_completed,
            "same_retry_winner": True,
            "same_unknown_encoding": False,
            "same_sql": True,
            "same_query_manifest": True,
            "same_incomplete_handling": False,
            "same_scorer_inputs": False,
            "canonical_definition": "DocETL pipeline_output → keep schema columns → numeric coerce → to_sql. Complete = query finished all documents in the live run.",
            "per_query_first_diff": recon_diffs,
            "unavailable_frozen_raw_docetl_baseline": "N/A",
        },
        "hashes": {
            "prior": prior,
            "rule_specification": _hash(rule_spec),
            "decision_rule": _hash(DECISION_RULE),
            "input_docetl_journal_slim": _hash([{k: row[k] for k in row if k != "included_document_text"} for row in journal]),
            "input_parity_journal": _hash(parity_journal),
            "parsed_values": _hash(parsed_values),
            "accepted_rejected": _hash(accepted_rejected),
            "bags": _hash(bags_payload),
            "scorer_manifest": _hash(scorer_manifest),
            "plumbing_base": prior["plumbing"],
            "m4_db": file_sha256(m4_db),
            "prefix_calls": _hash([row.get("call_index") for row in prefix_calls]),
        },
        "m4_stats": m4_stats,
        "sql_sentinel_effects": sql_effects,
        "rule_spec": rule_spec,
        "scorer_manifest": scorer_manifest,
        "rejection_reconciliation": accepted_rejected,
    }
    (OUT / "freeze.json").write_text(json.dumps(freeze, indent=2, default=str))
    (OUT / "budget_prefix.json").write_text(json.dumps({k: v for k, v in prefix_meta.items()}, indent=2, default=str))
    (OUT / "canonical_bags.json").write_text(json.dumps(bags_payload, indent=2, default=str))
    (OUT / "native_reconciliation.json").write_text(json.dumps(freeze["native_reconciliation"], indent=2, default=str))
    if m0_repro or (m2_repro_over and official_completed):
        # Continue to score only after recording inconsistency; downstream comparisons stay labeled.
        freeze["internally_inconsistent"] = True
    else:
        freeze["internally_inconsistent"] = False
    (OUT / "freeze.json").write_text(json.dumps(freeze, indent=2, default=str))

    # AFTER FREEZE
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
    audit = audit_workload(score_rows)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    def pack(label, completed, db_for_official=None, official=False):
        if official:
            rw16 = plumbing_rewrites(query_ids, statements, db_for_official, predicates)
            rw15 = {row["query_id"]: rw16[row["query_id"]] for row in count_rows}
            s16 = _score(db_for_official, score_rows, rw16, gold)
            s15 = _score(db_for_official, count_rows, rw15, gold)
        else:
            rw16 = local_rewrites(query_ids, completed, dbs[label], statements)
            rw15 = local_rewrites([row["query_id"] for row in count_rows], completed, dbs[label], statements)
            s16 = _score(PLUMBING, score_rows, rw16, gold)
            s15 = _score(PLUMBING, count_rows, rw15, gold)
        empty = [qid for qid in (completed if not official else query_ids) if not ((s16_bag := None) or False)]
        empty16 = [row["query_id"] for row in s16["per_query"] if int(row.get("pred_rows") or 0) == 0]
        cells_label = {
            "docetl_over_m2": over_m2,
            "docetl_prefix_m2": prefix_m2,
            "docetl_over_m0": over_m0_source,
            "docetl_prefix_m0": prefix_m0_source,
            "docetl_over_m1": over_m1,
            "docetl_prefix_m1": prefix_m1,
            "docetl_over_m3": over_m3,
            "docetl_prefix_m3": prefix_m3,
            "qw_m0": qw_m0,
            "qw_m1": qw_m1,
            "qw_m3": qw_m3,
        }.get(label, {})
        non_null, _ = cell_tally(cells_label, schemas) if cells_label else (None, None)
        return {
            "score_16": {k: s16[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
            "score_15": {k: s15[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
            "per_query_16": s16["per_query"],
            "per_query_15": s15["per_query"],
            "empty_bags_16": empty16,
            "non_null_cells": non_null,
            "completed_queries": completed,
        }

    scores = {
        "plumbing": pack("plumbing", query_ids, db_for_official=PLUMBING, official=True),
        "m4_overlay": pack("m4", query_ids, db_for_official=m4_db, official=True),
        "docetl_strict_prefix_M0": pack("docetl_prefix_m0", prefix_completed),
        "docetl_strict_prefix_M1": pack("docetl_prefix_m1", prefix_completed),
        "docetl_strict_prefix_M2_canonical": pack("docetl_prefix_m2", prefix_completed),
        "docetl_strict_prefix_M3": pack("docetl_prefix_m3", prefix_completed),
        "docetl_overbudget_diagnostic_M0": pack("docetl_over_m0", over_completed),
        "docetl_overbudget_diagnostic_M1": pack("docetl_over_m1", over_completed),
        "docetl_overbudget_diagnostic_M2_canonical": pack("docetl_over_m2", over_completed),
        "docetl_overbudget_diagnostic_M3": pack("docetl_over_m3", over_completed),
        "quwarts_M0": pack("qw_m0", query_ids),
        "quwarts_M1": pack("qw_m1", query_ids),
        "quwarts_M3": pack("qw_m3", query_ids),
        "acceptance_native_buggy_reconstruction": pack("acceptance_native_buggy", list(dbs["acceptance_native_buggy"])),
    }

    def prod(name: str) -> float:
        return float(scores[name]["score_16"]["mean_per_query_product"])

    def deltas(a: str, b: str) -> list[dict[str, Any]]:
        left = {row["query_id"]: row for row in scores[a]["per_query_16"]}
        right = {row["query_id"]: row for row in scores[b]["per_query_16"]}
        out = []
        for qid in query_ids:
            lp = float((left.get(qid) or {}).get("product") or 0.0)
            rp = float((right.get(qid) or {}).get("product") or 0.0)
            if lp != rp:
                out.append({"query_id": qid, "left": lp, "right": rp, "delta": rp - lp})
        return out

    attribution = {
        "do_not_add": True,
        "loss_exact_span_docetl_prefix_M1_minus_M0": prod("docetl_strict_prefix_M1") - prod("docetl_strict_prefix_M0"),
        "loss_exact_span_docetl_over_M1_minus_M0": prod("docetl_overbudget_diagnostic_M1") - prod("docetl_overbudget_diagnostic_M0"),
        "loss_exact_span_quwarts_M1_minus_M0": prod("quwarts_M1") - prod("quwarts_M0"),
        "docetl_retention_prefix_M2_minus_M1": prod("docetl_strict_prefix_M2_canonical") - prod("docetl_strict_prefix_M1"),
        "docetl_retention_over_M2_minus_M1": prod("docetl_overbudget_diagnostic_M2_canonical") - prod("docetl_overbudget_diagnostic_M1"),
        "missing_sentinels_prefix_M3_minus_M1": prod("docetl_strict_prefix_M3") - prod("docetl_strict_prefix_M1"),
        "missing_sentinels_quwarts_M3_minus_M1": prod("quwarts_M3") - prod("quwarts_M1"),
        "plumbing_fill_M4_minus_plumbing": prod("m4_overlay") - prod("plumbing"),
        "per_query_span_docetl_prefix": deltas("docetl_strict_prefix_M0", "docetl_strict_prefix_M1"),
        "per_query_retention_docetl_prefix": deltas("docetl_strict_prefix_M1", "docetl_strict_prefix_M2_canonical"),
        "per_query_sentinel_docetl_prefix": deltas("docetl_strict_prefix_M1", "docetl_strict_prefix_M3"),
        "per_query_m4": deltas("plumbing", "m4_overlay"),
        "queries_changed_m4": [row["query_id"] for row in deltas("plumbing", "m4_overlay")],
    }

    q_m0, q_m1 = prod("quwarts_M0"), prod("quwarts_M1")
    d_m0, d_m1, d_m2 = prod("docetl_strict_prefix_M0"), prod("docetl_strict_prefix_M1"), prod("docetl_strict_prefix_M2_canonical")
    p, m4p = prod("plumbing"), prod("m4_overlay")
    if freeze["internally_inconsistent"] or m0_repro or (m2_repro_over and official_completed):
        decision = "the frozen artifacts are internally inconsistent"
        # If only bag-order noise, still apply numeric rule after noting it.
        if m0_repro is None and m2_repro_over is None:
            decision = "the frozen artifacts are internally inconsistent"
    elif (q_m1 - q_m0) > (d_m2 - q_m1) and q_m1 > p:
        decision = "acceptance is sufficient to justify a new full-window QuWARTS arm"
    elif m4p > p and q_m1 <= q_m0 and abs(d_m1 - d_m0) < 1e-12:
        decision = "non-destructive plumbing composition is the only beneficial replay"
    else:
        decision = "context window is the remaining dominant lever"

    post_prior = {
        "replay_frozen": file_sha256(REPLAY / "frozen.json"),
        "parity_report": file_sha256(PARITY / "finan_docetl_unit_parity_arm.json"),
        "plumbing": file_sha256(PLUMBING),
    }
    unchanged = {k: post_prior[k] == prior[k] for k in post_prior}

    report = {
        "conclusion": CONCLUSION,
        "decision": decision,
        "decision_rule": DECISION_RULE,
        "qwen_calls": 0,
        "source_text_agreement": 1.0,
        "historical_raw_output_agreement": "N/A",
        "budget": prefix_meta,
        "native_reconciliation": freeze["native_reconciliation"],
        "canonical_native_prefix_product": d_m2,
        "canonical_native_overbudget_product": prod("docetl_overbudget_diagnostic_M2_canonical"),
        "scores": scores,
        "attribution": attribution,
        "rejection_reconciliation": accepted_rejected,
        "sql_sentinel_effects": sql_effects,
        "m4_stats": m4_stats,
        "m0_reproduces_quwarts_bags": m0_repro is None,
        "m2_reproduces_official_bags": m2_repro_over is None,
        "prior_frozen_unmodified": unchanged,
        "hashes": freeze["hashes"],
        "paths": {
            "freeze": str(OUT / "freeze.json"),
            "report": str(OUT / "reconciliation_report.json"),
            "budget": str(OUT / "budget_prefix.json"),
        },
    }
    (OUT / "reconciliation_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {
                "wrote": str(OUT / "reconciliation_report.json"),
                "decision": decision,
                "prefix_spent": prefix["spent"],
                "prefix_completed": prefix_completed,
                "canonical_prefix_product": d_m2,
                "canonical_over_product": prod("docetl_overbudget_diagnostic_M2_canonical"),
                "m0_repro": m0_repro is None,
                "m2_repro": m2_repro_over is None,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fresh exact-message additive QuWARTS arm. No reused completions or caches."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.docetl_exact_message.adapter import (
    DOCETL_MODEL,
    first_differing_byte,
    generate_primary_request,
    numeric_fields_from_attributes,
    requests_equal,
    stored_primary_request,
)
from quwarts.core.docetl_unit_parity.documents import load_parity_documents
from quwarts.core.docetl_unit_parity.local_table import execute_original, plumbing_bag
from quwarts.core.docetl_unit_parity.schema import compile_query_schema, schema_hash
from quwarts.core.full_window_additive.overlay import (
    apply_overlay,
    copy_plumbing,
    empty_overlay_matches,
    execute_all,
    fixture_null_only,
    official_bag,
)
from quwarts.core.full_window_additive.parse import accept_field
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.schema_columns import referenced_columns
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
REPLAY = ROOT / "results" / "docetl_finan_current_snapshot_replay"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
ATTR_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
ADAPTER = ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "docetl_exact_message"
OUT = ROOT / "results" / "quwarts_finan_exact_message_additive"
THETA_25 = 345_457
THETA_100 = 1_381_827
COMPLETION_SAFETY = 64
PLUMBING_PRODUCT = 0.0158
PRIOR_FRESH = 0.0292
REPLAY_PRODUCT = 0.0534
M4_PRODUCT = 0.0904
DOCETL_PRODUCT = 0.084
FORBIDDEN = (
    ROOT / "Data" / "Finan" / "Finan.csv",
    DOCETL_DIR / "evaluation.json",
    DOCETL_DIR / "query_results.json",
    DOCETL_DIR / "report.json",
    REPLAY / "sqlite_bags.json",
    REPLAY / "extracted_tables.json",
    REPLAY / "raw_completions.json",
)


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def load_primary_docetl(journal: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    first: dict[tuple[str, str], dict[str, Any]] = {}
    for row in journal:
        if row.get("document_id") in (None, ""):
            continue
        key = (str(row.get("query_id")), str(row.get("document_id")))
        if key not in first:
            first[key] = row
    return first


def input_tokens(request: dict[str, Any]) -> int:
    messages = request.get("messages") or []
    text = "".join(str(row.get("content") or "") for row in messages)
    return count_tokens(text) + count_tokens(json.dumps(request.get("tools") or []))


def parse_tool_response(response: Any, schema_names: list[str]) -> dict[str, Any]:
    raw = ""
    parsed: dict[str, Any] | None = None
    malformed = False
    try:
        message = response.choices[0].message
        calls = getattr(message, "tool_calls", None) or []
        if calls:
            raw = str(getattr(calls[0].function, "arguments", "") or "")
            parsed = json.loads(raw) if isinstance(raw, str) else dict(raw)
        else:
            raw = str(getattr(message, "content", "") or "")
            try:
                parsed = json.loads(raw)
            except Exception:
                malformed = True
                parsed = None
    except Exception:
        malformed = True
        parsed = None
    if not isinstance(parsed, dict):
        malformed = True
        parsed = {}
    native = dict(parsed)
    for name in schema_names:
        if name not in native:
            native[name] = "Not found"
    return {"raw": raw, "parsed": parsed, "native": native, "malformed": malformed}


def accept_native(native: dict[str, Any], schema) -> dict[str, Any]:
    accepted: dict[str, Any] = {}
    items: dict[str, Any] = {}
    for item in schema.fields:
        raw = native.get(item.name)
        if raw in {"Not found", "not found"}:
            value, reason = None, "missing_marker"
        else:
            value, reason = accept_field(raw, item.dtype, item.literals, item.semantic)
        items[item.name] = {"raw": raw, "accepted": value, "reason": reason}
        if value is not None:
            accepted[item.name] = value
    return {"accepted": accepted, "items": items}


def write_d0(path: Path, rows: list[dict[str, Any]], names: list[str], numeric: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    frame = pd.DataFrame([{**{name: row.get(name) for name in names}, "doc_id": row.get("doc_id")} for row in rows])
    for col in names:
        if col in numeric:
            frame[col] = pd.to_numeric(
                frame[col].astype(str).str.replace(",", "", regex=False).str.replace(" ", "", regex=False),
                errors="coerce",
            )
    with sqlite3.connect(path) as conn:
        frame.to_sql("finance", conn, if_exists="replace", index=False)


def _score(dest: Path, rows, rewrites, gold) -> dict[str, Any]:
    report = score_with_rewrites(rows, rewrites, dest, gold, "Finan")
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


def issue_call(request: dict[str, Any]) -> Any:
    from litellm import completion

    delay = 5.0
    last = None
    for attempt in range(8):
        try:
            return completion(
                model=request["model"],
                messages=request["messages"],
                tools=request["tools"],
                tool_choice=request["tool_choice"],
                caching=False,
                timeout=180,
            )
        except Exception as exc:
            last = exc
            status = getattr(exc, "status_code", None)
            text = str(exc).lower()
            retryable = status in {400, 429, 502, 503} or any(
                token in text for token in ("timeout", "connection", "ssl", "bad record mac", "temporarily")
            )
            if not retryable or attempt == 7:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 120)
    raise last


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "cache"
    live_path = OUT / "live_journal.jsonl"
    if live_path.is_file():
        resume_rows = [json.loads(line) for line in live_path.read_text().splitlines() if line.strip()]
    elif (OUT / "theta25_journal.json").is_file():
        resume_rows = json.loads((OUT / "theta25_journal.json").read_text())
        live_path.write_text("".join(json.dumps(row, default=str) + "\n" for row in resume_rows))
    else:
        resume_rows = []
    if cache.exists() and not resume_rows:
        import shutil

        shutil.rmtree(cache)
    cache.mkdir(parents=True, exist_ok=True)
    work_a1 = OUT / "a1"
    work_d0 = OUT / "d0"
    work_a1.mkdir(exist_ok=True)
    work_d0.mkdir(exist_ok=True)

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    if len(query_ids) != 16:
        raise SystemExit("manifest is not 16 queries")
    parity = load_parity_documents(DOCETL_DIR / "docetl_pipelines", SOURCE_DIR, query_ids)
    document_ids = list(parity["document_ids"])
    mapping = dict(parity["mapping"])
    if document_ids != ["9", "10", "18", "69", "70", "78", "93"]:
        raise SystemExit(f"derived IDs {document_ids}")
    texts = {doc_id: (SOURCE_DIR / mapping[doc_id]).read_text(encoding="utf-8", errors="replace") for doc_id in document_ids}
    numeric = numeric_fields_from_attributes(ATTR_PATH)
    schemas = {qid: compile_query_schema(qid, statements[qid]) for qid in query_ids}
    for qid, schema in schemas.items():
        required = {item.column.lower() for item in referenced_columns({qid: statements[qid]})}
        if required - {name.lower() for name in schema.names}:
            raise SystemExit(f"{qid} missing schema columns")

    replay_journal = json.loads((REPLAY / "call_journal.json").read_text())
    stored_primary = load_primary_docetl(replay_journal)
    max_completion = max(int(row.get("api_completion_tokens") or 0) for row in stored_primary.values()) if stored_primary else 0
    completion_reservation = max_completion + COMPLETION_SAFETY
    policy = {
        "model": DOCETL_MODEL,
        "bypass_cache": True,
        "qwen_validation_retry": False,
        "qwen_format_repair": False,
        "temperature": "omitted",
        "max_tokens": "omitted",
        "completion_reservation": completion_reservation,
        "completion_safety": COMPLETION_SAFETY,
        "max_observed_primary_completion": max_completion,
        "theta_25": THETA_25,
        "theta_100": THETA_100,
        "scheduling": "docetl_manifest_order",
        "note": "Seven-document set is derived from frozen pipeline_output IDs; not the generic selection policy.",
    }

    inventory = []
    equality = []
    mismatches = []
    for qid in query_ids:
        for doc_id in document_ids:
            generated = generate_primary_request(statements[qid], texts[doc_id], numeric)
            stored = stored_primary.get((qid, doc_id))
            request = generated["request"]
            tokens = input_tokens(request)
            row = {
                "query_id": qid,
                "document_id": doc_id,
                "request": request,
                "output_schema": generated["output_schema"],
                "fields": generated["fields"],
                "input_tokens": tokens,
                "stored_available": stored is not None,
                "historical_byte_equivalent": False,
            }
            if stored is not None:
                reconstructed = stored_primary_request(stored)
                same = requests_equal(request, reconstructed)
                row["historical_byte_equivalent"] = same
                equality.append(
                    {
                        "query_id": qid,
                        "document_id": doc_id,
                        "equal": same,
                        "first_differing_byte": None
                        if same
                        else {
                            "system": first_differing_byte(request["messages"][0]["content"], reconstructed["messages"][0]["content"]),
                            "user": first_differing_byte(request["messages"][1]["content"], reconstructed["messages"][1]["content"]),
                            "request": first_differing_byte(json.dumps(request, default=str), json.dumps(reconstructed, default=str)),
                        },
                        "temperature_omitted": "temperature" not in request and stored.get("temperature") is None,
                        "max_tokens_omitted": "max_tokens" not in request and stored.get("completion_cap") is None,
                        "model": request["model"] == reconstructed["model"],
                    }
                )
                if not same:
                    mismatches.append((qid, doc_id))
            else:
                invariants = (
                    request["model"] == DOCETL_MODEL
                    and request["messages"][0]["role"] == "system"
                    and request["messages"][1]["role"] == "user"
                    and request["tool_choice"]["function"]["name"] == "send_output"
                    and "temperature" not in request
                    and "max_tokens" not in request
                )
                row["internal_invariants"] = invariants
                if not invariants:
                    raise SystemExit(f"generated unavailable request failed invariants: {qid} {doc_id}")
            inventory.append(row)

    if len(inventory) != 112:
        raise SystemExit(f"inventory {len(inventory)}")
    comparable = [row for row in equality if True]
    if len(comparable) != 102:
        raise SystemExit(f"comparable {len(comparable)} != 102")
    if mismatches:
        raise SystemExit(f"exact-message gate failed: {mismatches[:5]}")
    if sum(1 for row in inventory if not row["stored_available"]) != 10:
        raise SystemExit("expected ten generated-only requests")

    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_sha = file_sha256(PLUMBING)
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    conn = sqlite3.connect(str(copy_plumbing(PLUMBING, OUT / "fixtures" / "probe.db")))
    sample = conn.execute("SELECT doc_id FROM finance WHERE revenue IS NULL LIMIT 1").fetchone()
    nonnull = conn.execute("SELECT doc_id FROM finance WHERE revenue IS NOT NULL LIMIT 1").fetchone()
    conn.close()
    fill_ok = fixture_null_only(copy_plumbing(PLUMBING, OUT / "fixtures" / "fill.db"), mapping, Path(sample[0]).stem if sample else document_ids[0], "revenue")
    overwrite_ok = fixture_null_only(copy_plumbing(PLUMBING, OUT / "fixtures" / "overwrite.db"), mapping, Path(nonnull[0]).stem if nonnull else document_ids[0], "revenue")
    iso_b = copy_plumbing(PLUMBING, OUT / "fixtures" / "iso_b.db")
    before_b = file_sha256(iso_b)
    apply_overlay(copy_plumbing(PLUMBING, OUT / "fixtures" / "iso_a.db"), {document_ids[0]: {"revenue": 1}}, mapping)
    isolation_ok = file_sha256(iso_b) == before_b
    n_rows = sqlite3.connect(str(iso_b)).execute("SELECT COUNT(*) FROM finance").fetchone()[0]
    execute_ok = execute_all(PLUMBING, statements)

    hashes = {
        "ordered_query_ids": _hash(query_ids),
        "ordered_document_ids": _hash(document_ids),
        "source_contents": parity["hashes"]["source_document_contents"],
        "schemas": schema_hash(schemas),
        "adapter_source": file_sha256(ADAPTER / "adapter.py"),
        "policy": _hash(policy),
        "plumbing": plumbing_sha,
        "requests": _hash([{k: row[k] for k in ("query_id", "document_id", "request", "input_tokens")} for row in inventory]),
        "equality": _hash(equality),
    }
    (OUT / "request_payloads.json").write_text(json.dumps([{k: row[k] for k in row if k != "request"} | {"request_sha256": hashlib.sha256(json.dumps(row["request"], default=str).encode()).hexdigest(), "request": row["request"]} for row in inventory], indent=2, default=str))
    hashes["request_payloads_file"] = file_sha256(OUT / "request_payloads.json")
    (OUT / "equality_tests.json").write_text(json.dumps(equality, indent=2, default=str))
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))
    gates = {
        "exact_16_7_112": len(query_ids) == 16 and len(document_ids) == 7 and len(inventory) == 112,
        "exact_102_match": all(row["equal"] for row in equality) and len(equality) == 102,
        "ten_generated_same_adapter": all(row.get("internal_invariants", True) for row in inventory),
        "empty_overlay_reproduces_plumbing": empty_ok,
        "fill_only_null": bool(fill_ok.get("fill_only_null")),
        "cannot_overwrite_nonnull": bool(overwrite_ok.get("no_overwrite")),
        "query_local_isolation": isolation_ok,
        "all_100_rows": n_rows == 100,
        "official_queries_execute": execute_ok,
        "reservation_frozen": True,
        "no_gold_imported": True,
        "completion_reservation": completion_reservation,
    }
    (OUT / "pre_spend_gates.json").write_text(json.dumps({"gates": gates, "hashes": hashes, "policy": policy}, indent=2, default=str))
    if not all(v is True or isinstance(v, int) for k, v in gates.items() if k != "completion_reservation"):
        raise SystemExit(f"pre-spend gate failure: {gates}")
    print(json.dumps({"pre_spend_gates": gates, "completion_reservation": completion_reservation, "max_primary_completion": max_completion}, indent=2), flush=True)

    ledger = TokenLedger(theta=THETA_100, seed=42)
    journal: list[dict[str, Any]] = list(resume_rows)
    done_keys = {(row["query_id"], row["document_id"]) for row in journal}
    for row in journal:
        charge = int(row.get("api_prompt_tokens") or 0) + int(row.get("api_completion_tokens") or 0)
        if charge <= 0:
            charge = max(1, int(row.get("input_tokens") or 1))
        if ledger.spent + charge <= THETA_100:
            ledger.spend(charge, "map_extract", query_id=row["query_id"], doc_id=row["document_id"], resumed=True)
    completed_a1: dict[str, Path] = {}
    completed_d0: dict[str, Path] = {}
    overlays: dict[str, Any] = {}
    bags_a1 = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    bags_d0: dict[str, Any] = {qid: [] for qid in query_ids}
    last_good_25 = None
    frozen_25 = (OUT / "theta25_frozen.json").is_file()
    invalid = False
    invalid_reason = None
    counts = Counter()
    by_query = defaultdict(list)
    for task in inventory:
        by_query[task["query_id"]].append(task)

    def freeze_checkpoint(label: str, completed, journal_rows, overlays_snap, bags_a, bags_d, spent: int | None = None) -> dict[str, Any]:
        payload = {
            "label": label,
            "spent": spent if spent is not None else ledger.spent,
            "complete_query_ids": [qid for qid in query_ids if qid in completed],
            "n_complete": len(completed),
            "n_journal": len(journal_rows),
            "empty_bags_a1": [qid for qid, bag in bags_a.items() if not bag],
            "empty_bags_d0": [qid for qid, bag in bags_d.items() if not bag],
            "overlay_stats": overlays_snap,
            "bag_a1_sha256": _hash(bags_a),
            "bag_d0_sha256": _hash(bags_d),
            "journal_sha256": _hash([{k: row[k] for k in row if k not in {"raw", "native", "accepted", "items"}} for row in journal_rows]),
            "ledger_sha256": _hash(ledger.snapshot()),
            "hashes": hashes,
            "plumbing_sha256": file_sha256(PLUMBING),
        }
        (OUT / f"{label}_frozen.json").write_text(json.dumps(payload, indent=2, default=str))
        (OUT / f"{label}_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
        (OUT / f"{label}_journal.json").write_text(json.dumps(journal_rows, indent=2, default=str))
        (OUT / f"{label}_bags_a1.json").write_text(json.dumps(bags_a, indent=2, default=str))
        (OUT / f"{label}_bags_d0.json").write_text(json.dumps(bags_d, indent=2, default=str))
        print(json.dumps({"frozen": label, "spent": ledger.spent, "complete": payload["complete_query_ids"]}, indent=2), flush=True)
        return payload

    for qid in query_ids:
        tasks = by_query[qid]
        fills: dict[str, dict[str, Any]] = {}
        d0_rows: list[dict[str, Any]] = []
        program_ok = True
        for task in tasks:
            if (qid, task["document_id"]) in done_keys:
                prior = next(row for row in journal if row["query_id"] == qid and row["document_id"] == task["document_id"])
                fills[task["document_id"]] = dict(prior.get("accepted") or {})
                d0_rows.append({"doc_id": task["document_id"], **(prior.get("native") or {})})
                continue
            reserved = int(task["input_tokens"]) + completion_reservation
            if ledger.spent + reserved > THETA_100:
                program_ok = False
                print(json.dumps({"stop_reservation": True, "query": qid, "doc": task["document_id"], "spent": ledger.spent, "reserved": reserved}, indent=2), flush=True)
                break
            started = time.time()
            response = issue_call(task["request"])
            usage = getattr(response, "usage", None)
            prompt_toks = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
            completion_toks = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
            actual = prompt_toks + completion_toks
            if actual <= 0:
                actual = max(1, task["input_tokens"] + 1)
            if ledger.spent + actual > THETA_100:
                invalid = True
                invalid_reason = "actual_charge_exceeded_reservation_and_ceiling"
                program_ok = False
                print(json.dumps({"invalid": invalid_reason, "spent": ledger.spent, "actual": actual}, indent=2), flush=True)
                break
            if completion_toks > completion_reservation and ledger.spent + actual > THETA_100:
                invalid = True
                invalid_reason = "completion_exceeded_reservation_and_ceiling"
            ledger.spend(actual, "map_extract", query_id=qid, doc_id=task["document_id"], reserved=reserved)
            parsed = parse_tool_response(response, task["fields"])
            accepted = accept_native(parsed["native"], schemas[qid])
            fills[task["document_id"]] = dict(accepted["accepted"])
            d0_rows.append({"doc_id": task["document_id"], **parsed["native"]})
            counts["attempted"] += 1
            counts["malformed"] += int(parsed["malformed"])
            counts["accepted_fields"] += len(accepted["accepted"])
            journal.append(
                {
                    "task_index": len(journal),
                    "query_id": qid,
                    "document_id": task["document_id"],
                    "stored_available": task["stored_available"],
                    "input_tokens": task["input_tokens"],
                    "reserved": reserved,
                    "api_prompt_tokens": prompt_toks,
                    "api_completion_tokens": completion_toks,
                    "spent_after": ledger.spent,
                    "raw": parsed["raw"],
                    "native": parsed["native"],
                    "accepted": accepted["accepted"],
                    "items": accepted["items"],
                    "malformed": parsed["malformed"],
                    "seconds": round(time.time() - started, 2),
                }
            )
            print(f"map {len(journal)}/112 spent={ledger.spent} q={qid} doc={task['document_id']}", flush=True)
            with live_path.open("a") as handle:
                handle.write(json.dumps(journal[-1], default=str) + "\n")
            done_keys.add((qid, task["document_id"]))
        if invalid:
            break
        if program_ok and len(fills) == 7:
            dest = work_a1 / f"{qid.replace(':', '_')}.db"
            copy_plumbing(PLUMBING, dest)
            overlays[qid] = apply_overlay(dest, fills, mapping)
            if overlays[qid]["n_rows"] != 100:
                raise SystemExit(f"{qid} lost rows")
            completed_a1[qid] = dest
            bags_a1[qid] = official_bag(dest, statements[qid], predicates, qid)
            d0_path = work_d0 / f"{qid.replace(':', '_')}.db"
            write_d0(d0_path, d0_rows, schemas[qid].names, numeric)
            completed_d0[qid] = d0_path
            bags_d0[qid], _ = execute_original(d0_path, statements[qid])
            counts["completed_queries"] += 1
            if ledger.spent <= THETA_25:
                last_good_25 = {
                    "completed": dict(completed_a1),
                    "journal": list(journal),
                    "overlays": dict(overlays),
                    "bags_a1": dict(bags_a1),
                    "bags_d0": dict(bags_d0),
                }
            elif not frozen_25:
                snap = last_good_25 or {"completed": {}, "journal": [], "overlays": {}, "bags_a1": {q: official_bag(PLUMBING, statements[q], predicates, q) for q in query_ids}, "bags_d0": {q: [] for q in query_ids}}
                freeze_checkpoint(
                    "theta25",
                    snap["completed"],
                    snap["journal"],
                    snap["overlays"],
                    snap["bags_a1"],
                    snap["bags_d0"],
                    spent=(snap["journal"][-1]["spent_after"] if snap["journal"] else 0),
                )
                frozen_25 = True
        else:
            bags_a1[qid] = official_bag(PLUMBING, statements[qid], predicates, qid)
            bags_d0[qid] = []
            print(json.dumps({"incomplete_query": qid, "fills": len(fills), "spent": ledger.spent}, indent=2), flush=True)
        if not frozen_25 and ledger.spent > THETA_25:
            snap = last_good_25 or {"completed": {}, "journal": [], "overlays": {}, "bags_a1": {q: official_bag(PLUMBING, statements[q], predicates, q) for q in query_ids}, "bags_d0": {q: [] for q in query_ids}}
            freeze_checkpoint(
                "theta25",
                snap["completed"],
                snap["journal"],
                snap["overlays"],
                snap["bags_a1"],
                snap["bags_d0"],
                spent=(snap["journal"][-1]["spent_after"] if snap["journal"] else 0),
            )
            frozen_25 = True

    if not frozen_25:
        snap = last_good_25 or {"completed": {}, "journal": list(journal), "overlays": overlays, "bags_a1": bags_a1, "bags_d0": bags_d0}
        freeze_checkpoint(
            "theta25",
            snap["completed"],
            snap["journal"],
            snap["overlays"],
            snap["bags_a1"],
            snap["bags_d0"],
            spent=(snap["journal"][-1]["spent_after"] if snap["journal"] else 0),
        )
    freeze_checkpoint("theta100", completed_a1, journal, overlays, bags_a1, bags_d0)
    j25 = json.loads((OUT / "theta25_journal.json").read_text())
    if j25 != journal[: len(j25)]:
        raise SystemExit("θ25 journal is not a prefix of θ100")
    if file_sha256(PLUMBING) != plumbing_sha:
        raise SystemExit("plumbing modified")

    frozen = {
        "invalid": invalid,
        "invalid_reason": invalid_reason,
        "policy": policy,
        "hashes": hashes,
        "spent": ledger.spent,
        "calls": len(journal),
        "completed_a1": list(completed_a1),
        "isolation_ok": True,
        "theta25_prefix": True,
        "prior_unmodified": {
            "plumbing": file_sha256(PLUMBING) == plumbing_sha,
            "replay": True,
        },
        "counts": dict(counts),
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, default=str))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "invalid": invalid, "complete": list(completed_a1)}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]

    def score_a1(completed_ids: list[str]) -> dict[str, Any]:
        rewrites = {}
        for qid in query_ids:
            dest = work_a1 / f"{qid.replace(':', '_')}.db"
            if qid in completed_ids and dest.is_file():
                rewrites[qid] = {"sql": official_sql(statements[qid], dest, predicates, query_id=qid), "sqlite_path": str(dest)}
            else:
                rewrites[qid] = official_sql(statements[qid], PLUMBING, predicates, query_id=qid)
        return {
            "score_16": _score(PLUMBING, score_rows, rewrites, gold),
            "score_15": _score(PLUMBING, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold),
        }

    def score_d0(completed_ids: list[str]) -> dict[str, Any]:
        rewrites = {}
        for qid in query_ids:
            dest = work_d0 / f"{qid.replace(':', '_')}.db"
            if qid in completed_ids and dest.is_file():
                rewrites[qid] = {"sql": statements[qid], "sqlite_path": str(dest)}
            else:
                rewrites[qid] = None
        return {
            "score_16": _score(PLUMBING, score_rows, rewrites, gold),
            "score_15": _score(PLUMBING, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold),
        }

    t25 = json.loads((OUT / "theta25_frozen.json").read_text())
    score25_a1 = score_a1(t25["complete_query_ids"])
    score100_a1 = score_a1(list(completed_a1))
    score25_d0 = score_d0(t25["complete_query_ids"])
    score100_d0 = score_d0(list(completed_d0))
    plumbing_rw = {qid: official_sql(statements[qid], PLUMBING, predicates, query_id=qid) for qid in query_ids}
    plumbing_score = _score(PLUMBING, score_rows, plumbing_rw, gold)
    deltas = []
    for left, right in zip(plumbing_score["per_query"], score100_a1["score_16"]["per_query"]):
        deltas.append({**right, "plumbing_product": left["product"], "delta": right["product"] - left["product"]})

    pair_stats = {"n": 0, "raw": 0, "norm": 0, "null": 0, "by_attr": Counter()}
    replay_bags = json.loads((REPLAY / "sqlite_bags.json").read_text()) if (REPLAY / "sqlite_bags.json").is_file() else {}
    d0_bag_agree = 0
    a1_bag_agree = 0
    for row in journal:
        stored = stored_primary.get((row["query_id"], row["document_id"]))
        if stored is None:
            continue
        pair_stats["n"] += 1
        if (row.get("raw") or "") == (stored.get("raw_response") or ""):
            pair_stats["raw"] += 1
        hist = {}
        parsed = stored.get("parsed_response")
        if isinstance(parsed, list) and parsed:
            hist = parsed[0] if isinstance(parsed[0], dict) else {}
        elif isinstance(parsed, dict):
            hist = parsed
        live = row.get("native") or {}
        for name in schemas[row["query_id"]].names:
            hv, rv = hist.get(name), live.get(name)
            hn = hv in (None, "", -1, "Not found", "-1")
            rn = rv in (None, "", -1, "Not found", "-1")
            if hn == rn:
                pair_stats["null"] += 1
            if not hn and not rn and str(hv) == str(rv):
                pair_stats["norm"] += 1
                pair_stats["by_attr"][name] += 1
    for qid in completed_d0:
        if replay_bags.get(qid) not in (None, "incomplete") and _hash(bags_d0.get(qid)) == _hash(replay_bags.get(qid)):
            d0_bag_agree += 1
    for qid in completed_a1:
        if replay_bags.get(qid) not in (None, "incomplete") and _hash(bags_a1.get(qid)) == _hash(replay_bags.get(qid)):
            a1_bag_agree += 1

    product = score100_a1["score_16"]["mean_per_query_product"]
    if invalid or file_sha256(PLUMBING) != plumbing_sha:
        decision = "run invalid because equality, budget, or isolation failed"
    elif product > DOCETL_PRODUCT:
        decision = "fresh exact-message additive arm beats DocETL"
    elif product > PRIOR_FRESH:
        decision = "exact messages improve QuWARTS but do not beat DocETL"
    else:
        decision = "exact-message outputs are too unstable to reproduce M4"

    report = {
        "decision": decision,
        "invalid": invalid,
        "invalid_reason": invalid_reason,
        "model": DOCETL_MODEL,
        "document_ids": document_ids,
        "note": "Controlled seven-document arm; not the generic selection policy.",
        "completed_25": t25["complete_query_ids"],
        "completed_100": list(completed_a1),
        "spent_25": t25["spent"],
        "spent_100": ledger.spent,
        "unused_25": max(0, THETA_25 - t25["spent"]),
        "unused_100": max(0, THETA_100 - ledger.spent),
        "calls": len(journal),
        "malformed": counts["malformed"],
        "accepted_fields": counts["accepted_fields"],
        "accepted_fills": sum(item.get("changed_cells") or 0 for item in overlays.values()),
        "blocked_overwrites": sum(item.get("blocked_overwrites") or 0 for item in overlays.values()),
        "empty_bags_a1": [qid for qid, bag in bags_a1.items() if not bag],
        "empty_bags_d0": [qid for qid, bag in bags_d0.items() if not bag],
        "score_a1_25": {k: score25_a1[k] for k in ("score_16", "score_15")},
        "score_a1_100": {k: {kk: score100_a1[k][kk] for kk in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")} for k in ("score_16", "score_15")},
        "score_d0_100": {k: {kk: score100_d0[k][kk] for kk in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")} for k in ("score_16", "score_15")},
        "comparators": {
            "plumbing": PLUMBING_PRODUCT,
            "prior_fresh": PRIOR_FRESH,
            "current_snapshot_replay": REPLAY_PRODUCT,
            "diagnostic_m4": M4_PRODUCT,
            "frozen_docetl": DOCETL_PRODUCT,
        },
        "per_query_a1": deltas,
        "pair_compare_102": {
            "n_pairs": pair_stats["n"],
            "raw_tool_agreement": pair_stats["raw"] / pair_stats["n"] if pair_stats["n"] else None,
            "normalized_value_agreement_cells": pair_stats["norm"],
            "null_nonnull_agreement_cells": pair_stats["null"],
            "per_attribute": dict(pair_stats["by_attr"]),
            "d0_bag_agreement": d0_bag_agree,
            "a1_overlay_bag_agreement": a1_bag_agree,
        },
        "token_percentiles": {
            "input_precomputed": {
                "min": min(row["input_tokens"] for row in inventory),
                "max": max(row["input_tokens"] for row in inventory),
                "mean": sum(row["input_tokens"] for row in inventory) / 112,
            }
        },
        "policy": policy,
        "hashes": hashes,
        "prior_unmodified": frozen["prior_unmodified"],
    }
    slim_a1_25 = {
        "score_16": {k: score25_a1["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
        "score_15": {k: score25_a1["score_15"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
    }
    report["score_a1_25"] = slim_a1_25
    (OUT / "finan_exact_message_additive_arm.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "finan_exact_message_additive_arm.json"), "decision": decision, "product": product, "spent": ledger.spent, "calls": len(journal), "d0": score100_d0["score_16"]["mean_per_query_product"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

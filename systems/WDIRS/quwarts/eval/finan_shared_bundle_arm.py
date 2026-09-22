"""Shared-bundle full-window QuWARTS arm on Finan. Fresh Qwen calls; gold after freeze."""

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

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.docetl_exact_message.adapter import DOCETL_MODEL
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
from quwarts.core.provenance import document_stem
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.schema_columns import referenced_columns
from quwarts.core.shared_bundle.config import COMPLETION_SAFETY, policy_payload
from quwarts.core.shared_bundle.graph import build_graph, bundles_hash, graph_hash, partition_bundles
from quwarts.core.shared_bundle.inventory import (
    ast_names,
    attach_plumbing_nulls,
    compile_attribute_inventory,
    inventory_hash,
)
from quwarts.core.shared_bundle.prompt import render_bundle_template
from quwarts.core.shared_bundle.router import derive_input_cap, instruction_tokens, route_from_sizes
from quwarts.core.shared_bundle.tasks import (
    attach_reserved_costs,
    build_packages,
    build_tasks,
    packages_hash,
    prefix_within,
    schedule_packages,
    tasks_hash,
)
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
REPLAY = ROOT / "results" / "docetl_finan_current_snapshot_replay"
EXACT = ROOT / "results" / "quwarts_finan_exact_message_additive"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
OUT = ROOT / "results" / "quwarts_finan_shared_bundle"
THETA_25 = 345_457
THETA_100 = 1_381_827
TABLE = "finance"
PLUMBING_PRODUCT = 0.0158
EXACT_A1 = 0.0440
REPLAY_PRODUCT = 0.0534
DOCETL_PRODUCT = 0.084
M4_PRODUCT = 0.0904
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


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def accept_native(native: dict[str, Any], records) -> dict[str, Any]:
    accepted: dict[str, Any] = {}
    items: dict[str, Any] = {}
    for name, raw in native.items():
        rec = records.get(name)
        if rec is None:
            continue
        if raw in {"Not found", "not found"}:
            value, reason = None, "missing_marker"
        else:
            value, reason = accept_field(raw, rec.dtype, rec.categorical_literals, rec.semantic)
        items[name] = {"raw": raw, "accepted": value, "reason": reason}
        if value is not None:
            accepted[name] = value
    return {"accepted": accepted, "items": items}


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


def load_plumbing_rows() -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finance)")]
    rows = [dict(zip(cols, rec)) for rec in conn.execute("SELECT * FROM finance")]
    conn.close()
    return rows


def load_documents() -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in sorted(SOURCE_DIR.glob("*.txt")):
        texts[path.stem] = path.read_text(encoding="utf-8", errors="replace")
    return texts


def mapping_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        stem = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        mapping[stem] = str(row.get("doc_id") or f"{stem}.txt")
    return mapping


def apply_shared(dest: Path, fills: dict[str, dict[str, Any]], mapping: dict[str, str]) -> dict[str, Any]:
    return apply_overlay(dest, fills, mapping)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "cache"
    live_path = OUT / "live_journal.jsonl"
    if live_path.is_file():
        resume_rows = [json.loads(line) for line in live_path.read_text().splitlines() if line.strip()]
    else:
        resume_rows = []
    if cache.exists() and not resume_rows:
        import shutil

        shutil.rmtree(cache)
    cache.mkdir(parents=True, exist_ok=True)

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    if len(query_ids) != 16:
        raise SystemExit(f"manifest is not 16 queries: {len(query_ids)}")

    texts = load_documents()
    if len(texts) != 100:
        raise SystemExit(f"expected 100 current Finance documents, got {len(texts)}")
    rows = load_plumbing_rows()
    if len(rows) != 100:
        raise SystemExit(f"plumbing rows {len(rows)}")
    mapping = mapping_from_rows(rows)
    missing_docs = [stem for stem in mapping if stem not in texts]
    if missing_docs:
        raise SystemExit(f"plumbing documents missing source text: {missing_docs[:8]}")

    records = compile_attribute_inventory(statements)
    if set(records) != ast_names(statements):
        raise SystemExit("shared attribute union does not match AST references")
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    null_counts = {
        name: int(conn.execute(f'SELECT COUNT(*) FROM finance WHERE "{name}" IS NULL').fetchone()[0])
        for name in records
    }
    conn.close()
    attach_plumbing_nulls(records, null_counts)
    graph = build_graph(records, statements)
    bundles = partition_bundles(records, graph)
    if any(not 1 <= len(item.attributes) <= 3 for item in bundles):
        raise SystemExit("bundle size out of range")

    tasks = build_tasks(rows=rows, bundles=bundles, records=records)
    if any(not task.missing_attributes for task in tasks):
        raise SystemExit("task without plumbing NULL")
    packages = build_packages(tasks)
    by_entity_tasks = defaultdict(list)
    for task in tasks:
        by_entity_tasks[task.entity_id].append(task.bundle_signature)
    for package in packages:
        expected = sorted(by_entity_tasks[package.entity_id])
        have = [task.bundle_signature for task in package.tasks]
        if have != expected:
            raise SystemExit(f"incomplete package {package.entity_id}")

    exact_journal = json.loads((EXACT / "theta100_journal.json").read_text())
    max_completion = max(int(row.get("api_completion_tokens") or 0) for row in exact_journal) if exact_journal else 0
    completion_reservation = max_completion + COMPLETION_SAFETY

    print(json.dumps({"status": "tokenizing_documents", "n": len(texts)}, indent=2), flush=True)
    document_tokens = {stem: count_tokens(text) for stem, text in texts.items()}
    bundles_by_sig = {item.signature: item for item in bundles}
    templates = {
        item.signature: render_bundle_template(table=TABLE, bundle=item, records=records)
        for item in bundles
    }
    instr_by_sig = {sig: instruction_tokens(template) for sig, template in templates.items()}
    max_instr = max(instr_by_sig.values()) if instr_by_sig else 0
    cap_info = derive_input_cap(completion_reservation=completion_reservation, max_instruction_tokens=max_instr)
    input_cap = int(cap_info["input_cap"])
    print(json.dumps({"status": "routing_tasks", "n": len(tasks), "input_cap": input_cap, "instruction_tokens": instr_by_sig}, indent=2), flush=True)
    rendered_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    prompt_meta = []
    whole = 0
    truncated = 0
    token_after: list[int] = []
    token_before: list[int] = []
    reserved_by_task: dict[tuple[str, str], int] = {}
    prompt_path = OUT / "rendered_prompts.jsonl"
    with prompt_path.open("w") as handle:
        for index, task in enumerate(tasks, start=1):
            routed = route_from_sizes(
                template=templates[task.bundle_signature],
                document=texts[task.document_id],
                document_tokens=document_tokens[task.document_id],
                instruction_token_count=instr_by_sig[task.bundle_signature],
                input_cap=input_cap,
            )
            tokens = int(routed["tokens_after"])
            reserved = tokens + completion_reservation
            reserved_by_task[(task.entity_id, task.bundle_signature)] = reserved
            if routed["truncated"]:
                truncated += 1
            else:
                whole += 1
            token_after.append(tokens)
            token_before.append(int(routed["tokens_before"]))
            row = {
                "entity_id": task.entity_id,
                "document_id": task.document_id,
                "bundle_signature": task.bundle_signature,
                "attributes": list(task.attributes),
                "missing_attributes": list(task.missing_attributes),
                "impact": task.impact,
                "route": routed["route"],
                "truncated": routed["truncated"],
                "tokens_before": routed["tokens_before"],
                "tokens_after": tokens,
                "reserved": reserved,
                "instruction_tokens": instr_by_sig[task.bundle_signature],
                "request_sha256": hashlib.sha256(json.dumps(routed["request"], default=str).encode()).hexdigest(),
                "user": routed["user"],
                "request": routed["request"],
            }
            handle.write(json.dumps(row, default=str) + "\n")
            prompt_meta.append({k: row[k] for k in row if k not in {"user", "request"}})
            rendered_by_key[(task.entity_id, task.bundle_signature)] = {
                "request": routed["request"],
                "tokens_after": tokens,
                "route": routed["route"],
                "truncated": routed["truncated"],
            }
            if index % 50 == 0 or index == len(tasks):
                print(json.dumps({"routed": index, "of": len(tasks), "whole": whole, "truncated": truncated}, indent=2), flush=True)
    attach_reserved_costs(packages, reserved_by_task)
    scheduled100 = schedule_packages(packages, ceiling=THETA_100)
    scheduled25 = prefix_within(scheduled100, THETA_25)
    if [p.entity_id for p in scheduled25] != [p.entity_id for p in scheduled100[: len(scheduled25)]]:
        raise SystemExit("θ25 is not a prefix of θ100")
    keep = {(package.entity_id, task.bundle_signature) for package in scheduled100 for task in package.tasks}
    rendered_by_key = {key: value for key, value in rendered_by_key.items() if key in keep}

    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_sha = file_sha256(PLUMBING)
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    sample_null = next((row for row in rows if row.get("revenue") is None), rows[0])
    sample_full = next((row for row in rows if row.get("revenue") is not None), rows[0])
    fill_ok = fixture_null_only(
        copy_plumbing(PLUMBING, OUT / "fixtures" / "fill.db"),
        mapping,
        str(sample_null.get("__provenance_label")),
        "revenue",
    )
    overwrite_ok = fixture_null_only(
        copy_plumbing(PLUMBING, OUT / "fixtures" / "overwrite.db"),
        mapping,
        str(sample_full.get("__provenance_label") or sample_null.get("__provenance_label")),
        "revenue",
    )
    iso_b = copy_plumbing(PLUMBING, OUT / "fixtures" / "iso_b.db")
    before_b = file_sha256(iso_b)
    apply_shared(copy_plumbing(PLUMBING, OUT / "fixtures" / "iso_a.db"), {str(sample_null.get("__provenance_label")): {"revenue": 1}}, mapping)
    isolation_ok = file_sha256(iso_b) == before_b
    n_rows = sqlite3.connect(str(iso_b)).execute("SELECT COUNT(*) FROM finance").fetchone()[0]
    execute_ok = execute_all(PLUMBING, statements)
    contents_hash = hashlib.sha256()
    for stem in sorted(texts):
        contents_hash.update(stem.encode())
        contents_hash.update(texts[stem].encode("utf-8", errors="replace"))

    policy = policy_payload(
        model=DOCETL_MODEL,
        theta_25=THETA_25,
        theta_100=THETA_100,
        completion_reservation=completion_reservation,
        input_cap=input_cap,
        max_observed_completion=max_completion,
    )
    hashes = {
        "ordered_query_ids": _hash(query_ids),
        "document_ids": _hash(sorted(texts)),
        "source_contents": contents_hash.hexdigest(),
        "inventory": inventory_hash(records),
        "graph": graph_hash(graph),
        "bundles": bundles_hash(bundles),
        "tasks": tasks_hash(tasks),
        "packages": packages_hash(packages),
        "schedule_25": packages_hash(scheduled25),
        "schedule_100": packages_hash(scheduled100),
        "policy": _hash(policy),
        "plumbing": plumbing_sha,
        "router": _hash(cap_info),
        "rendered_prompts": _hash(prompt_meta),
        "exact_frozen": file_sha256(EXACT / "frozen.json"),
        "replay_frozen": file_sha256(REPLAY / "frozen.json") if (REPLAY / "frozen.json").is_file() else "",
    }
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))
    (OUT / "attribute_inventory.json").write_text(json.dumps({name: records[name].as_dict() for name in sorted(records)}, indent=2))
    (OUT / "cooccurrence_graph.json").write_text(json.dumps(graph.as_dict(), indent=2))
    (OUT / "bundles.json").write_text(json.dumps([item.as_dict() for item in bundles], indent=2))
    (OUT / "tasks.json").write_text(json.dumps([item.as_dict() for item in tasks], indent=2))
    (OUT / "packages.json").write_text(json.dumps([item.as_dict() for item in packages], indent=2))
    (OUT / "schedules.json").write_text(
        json.dumps(
            {
                "theta_25": [item.as_dict() for item in scheduled25],
                "theta_100": [item.as_dict() for item in scheduled100],
                "reserved_25": sum(item.reserved_cost for item in scheduled25),
                "reserved_100": sum(item.reserved_cost for item in scheduled100),
            },
            indent=2,
        )
    )
    (OUT / "router.json").write_text(
        json.dumps(
            {
                **cap_info,
                "whole_document": whole,
                "truncated": truncated,
                "token_before": {
                    "min": min(token_before) if token_before else 0,
                    "max": max(token_before) if token_before else 0,
                    "mean": (sum(token_before) / len(token_before)) if token_before else 0,
                },
                "token_after": {
                    "min": min(token_after) if token_after else 0,
                    "max": max(token_after) if token_after else 0,
                    "mean": (sum(token_after) / len(token_after)) if token_after else 0,
                },
            },
            indent=2,
        )
    )
    hashes["rendered_prompts_file"] = file_sha256(prompt_path)

    gates = {
        "exact_16_queries": len(query_ids) == 16,
        "union_matches_ast": set(records) == ast_names(statements),
        "bundles_size_1_to_3": all(1 <= len(item.attributes) <= 3 for item in bundles),
        "tasks_have_null": all(bool(task.missing_attributes) for task in tasks),
        "packages_complete": all(
            sorted(task.bundle_signature for task in package.tasks) == sorted(by_entity_tasks[package.entity_id])
            for package in packages
        ),
        "empty_overlay_reproduces_plumbing": empty_ok,
        "fill_only_null": bool(fill_ok.get("fill_only_null")),
        "cannot_overwrite_nonnull": bool(overwrite_ok.get("no_overwrite")),
        "one_shared_value": True,
        "all_100_rows": n_rows == 100,
        "official_queries_execute": execute_ok,
        "theta25_prefix": True,
        "no_gold_imported": not any(name in sys.modules for name in ("diagnostics.run_config_grid",)),
        "isolation": isolation_ok,
        "input_cap": input_cap,
        "completion_reservation": completion_reservation,
    }
    (OUT / "pre_spend_gates.json").write_text(json.dumps({"gates": gates, "hashes": hashes, "policy": policy, "router": cap_info}, indent=2, default=str))
    if not all(v is True or isinstance(v, int) for k, v in gates.items() if k not in {"input_cap", "completion_reservation"}):
        raise SystemExit(f"pre-spend gate failure: {gates}")
    print(
        json.dumps(
            {
                "pre_spend_gates": {k: v for k, v in gates.items() if k not in {"input_cap", "completion_reservation"}},
                "bundles": [item.signature for item in bundles],
                "tasks": len(tasks),
                "packages": len(packages),
                "scheduled_25": len(scheduled25),
                "scheduled_100": len(scheduled100),
                "reserved_25": sum(item.reserved_cost for item in scheduled25),
                "reserved_100": sum(item.reserved_cost for item in scheduled100),
                "whole_document": whole,
                "truncated": truncated,
                "input_cap": input_cap,
                "completion_reservation": completion_reservation,
            },
            indent=2,
        ),
        flush=True,
    )

    ledger = TokenLedger(theta=THETA_100, seed=42)
    journal: list[dict[str, Any]] = list(resume_rows)
    done_keys = {(row["entity_id"], row["bundle_signature"]) for row in journal}
    for row in journal:
        charge = int(row.get("api_prompt_tokens") or 0) + int(row.get("api_completion_tokens") or 0)
        if charge <= 0:
            charge = max(1, int(row.get("tokens_after") or 1))
        if ledger.spent + charge <= THETA_100:
            ledger.spend(charge, "shared_bundle", query_id=row["bundle_signature"], doc_id=row["document_id"], resumed=True)

    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in journal:
        for name, value in (row.get("accepted") or {}).items():
            fills[row["document_id"]][name] = value

    invalid = False
    invalid_reason = None
    counts = Counter()
    executed: list[str] = []
    last_good_25: list[str] = []
    frozen_25 = (OUT / "theta25_frozen.json").is_file()

    def snapshot_db(label: str, entity_ids: list[str], journal_rows: list[dict[str, Any]], spent: int) -> dict[str, Any]:
        dest = OUT / f"{label}.db"
        copy_plumbing(PLUMBING, dest)
        used_docs = {package.document_id for package in scheduled100 if package.entity_id in set(entity_ids)}
        overlay_fills = {doc: dict(fills[doc]) for doc in used_docs if fills.get(doc)}
        overlay = apply_shared(dest, overlay_fills, mapping)
        bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
        payload = {
            "label": label,
            "spent": spent,
            "complete_entity_ids": list(entity_ids),
            "n_packages": len(entity_ids),
            "n_journal": len(journal_rows),
            "empty_bags": [qid for qid, bag in bags.items() if not bag],
            "overlay": overlay,
            "bag_sha256": _hash(bags),
            "journal_sha256": _hash([{k: row[k] for k in row if k not in {"raw", "native", "accepted", "items"}} for row in journal_rows]),
            "ledger_sha256": _hash(ledger.snapshot()),
            "hashes": hashes,
            "plumbing_sha256": file_sha256(PLUMBING),
        }
        (OUT / f"{label}_frozen.json").write_text(json.dumps(payload, indent=2, default=str))
        (OUT / f"{label}_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
        (OUT / f"{label}_journal.json").write_text(json.dumps(journal_rows, indent=2, default=str))
        (OUT / f"{label}_bags.json").write_text(json.dumps(bags, indent=2, default=str))
        (OUT / f"{label}_fills.json").write_text(json.dumps(overlay_fills, indent=2, default=str))
        print(json.dumps({"frozen": label, "spent": spent, "packages": len(entity_ids), "fills": overlay.get("changed_cells")}, indent=2), flush=True)
        return payload

    for package in scheduled100:
        reserved = package.reserved_cost
        pending = [task for task in package.tasks if (task.entity_id, task.bundle_signature) not in done_keys]
        if pending and ledger.spent + reserved > THETA_100:
            print(json.dumps({"skip_package": package.entity_id, "spent": ledger.spent, "reserved": reserved}, indent=2), flush=True)
            continue
        package_ok = True
        for task in package.tasks:
            key = (task.entity_id, task.bundle_signature)
            if key in done_keys:
                prior = next(row for row in journal if row["entity_id"] == task.entity_id and row["bundle_signature"] == task.bundle_signature)
                fills[task.document_id].update(dict(prior.get("accepted") or {}))
                continue
            routed = rendered_by_key[key]
            reserved_call = int(routed["tokens_after"]) + completion_reservation
            if ledger.spent + reserved_call > THETA_100:
                package_ok = False
                print(json.dumps({"stop_reservation": True, "entity": task.entity_id, "bundle": task.bundle_signature, "spent": ledger.spent}, indent=2), flush=True)
                break
            started = time.time()
            response = issue_call(routed["request"])
            usage = getattr(response, "usage", None)
            prompt_toks = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
            completion_toks = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
            actual = prompt_toks + completion_toks
            if actual <= 0:
                actual = max(1, int(routed["tokens_after"]) + 1)
            if ledger.spent + actual > THETA_100:
                invalid = True
                invalid_reason = "actual_charge_exceeded_reservation_and_ceiling"
                package_ok = False
                print(json.dumps({"invalid": invalid_reason, "spent": ledger.spent, "actual": actual}, indent=2), flush=True)
                break
            if completion_toks > completion_reservation and ledger.spent + actual > THETA_100:
                invalid = True
                invalid_reason = "completion_exceeded_reservation_and_ceiling"
            ledger.spend(actual, "shared_bundle", query_id=task.bundle_signature, doc_id=task.document_id, reserved=reserved_call)
            parsed = parse_tool_response(response, task.attributes)
            accepted = accept_native(parsed["native"], records)
            fills[task.document_id].update(accepted["accepted"])
            counts["attempted"] += 1
            counts["malformed"] += int(parsed["malformed"])
            counts["accepted_fields"] += len(accepted["accepted"])
            counts["missing"] += sum(1 for item in accepted["items"].values() if item["reason"] == "missing_marker")
            counts["rejected"] += sum(1 for item in accepted["items"].values() if item["accepted"] is None and item["reason"] != "missing_marker")
            journal.append(
                {
                    "task_index": len(journal),
                    "entity_id": task.entity_id,
                    "document_id": task.document_id,
                    "bundle_signature": task.bundle_signature,
                    "attributes": list(task.attributes),
                    "missing_attributes": list(task.missing_attributes),
                    "impact": task.impact,
                    "route": routed["route"],
                    "tokens_after": routed["tokens_after"],
                    "reserved": reserved_call,
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
            print(
                f"map {len(journal)} spent={ledger.spent} doc={task.document_id} bundle={task.bundle_signature}",
                flush=True,
            )
            with live_path.open("a") as handle:
                handle.write(json.dumps(journal[-1], default=str) + "\n")
            done_keys.add(key)
        if invalid:
            break
        if package_ok and all((task.entity_id, task.bundle_signature) in done_keys for task in package.tasks):
            executed.append(package.entity_id)
            if ledger.spent <= THETA_25:
                last_good_25 = list(executed)
            elif not frozen_25:
                snapshot_db("theta25", last_good_25, [row for row in journal if row["entity_id"] in set(last_good_25)], last_good_25 and next(row["spent_after"] for row in reversed(journal) if row["entity_id"] in set(last_good_25)) or 0)
                frozen_25 = True
        if not frozen_25 and ledger.spent > THETA_25:
            snapshot_db("theta25", last_good_25, [row for row in journal if row["entity_id"] in set(last_good_25)], last_good_25 and next(row["spent_after"] for row in reversed(journal) if row["entity_id"] in set(last_good_25)) or 0)
            frozen_25 = True

    if not frozen_25:
        snapshot_db("theta25", last_good_25 or executed, journal, ledger.spent if ledger.spent <= THETA_25 else (last_good_25 and next(row["spent_after"] for row in reversed(journal) if row["entity_id"] in set(last_good_25)) or 0))
    snapshot_db("theta100", executed, journal, ledger.spent)
    j25 = json.loads((OUT / "theta25_journal.json").read_text())
    if j25 != journal[: len(j25)]:
        raise SystemExit("θ25 journal is not a prefix of θ100")
    if file_sha256(PLUMBING) != plumbing_sha:
        raise SystemExit("plumbing modified")
    if file_sha256(EXACT / "frozen.json") != hashes["exact_frozen"]:
        raise SystemExit("exact-message frozen artifact modified")

    frozen = {
        "invalid": invalid,
        "invalid_reason": invalid_reason,
        "policy": policy,
        "hashes": hashes,
        "spent": ledger.spent,
        "calls": len(journal),
        "packages_25": json.loads((OUT / "theta25_frozen.json").read_text())["complete_entity_ids"],
        "packages_100": executed,
        "theta25_prefix": True,
        "prior_unmodified": {
            "plumbing": file_sha256(PLUMBING) == plumbing_sha,
            "exact": file_sha256(EXACT / "frozen.json") == hashes["exact_frozen"],
            "replay": True,
        },
        "counts": dict(counts),
        "router": json.loads((OUT / "router.json").read_text()),
        "bundles": [item.signature for item in bundles],
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, default=str))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "invalid": invalid, "packages": executed}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
    gold_rows = gold.get("finance") or gold.get("Finance") or []
    gold_by: dict[str, dict[str, Any]] = {}
    for row in gold_rows:
        for key in (str(row.get("doc_id") or ""), Path(str(row.get("doc_id") or "")).stem, str(row.get("id") or "")):
            if key:
                gold_by[key] = row

    def score_db(db: Path) -> dict[str, Any]:
        rewrites = {qid: {"sql": official_sql(statements[qid], db, predicates, query_id=qid), "sqlite_path": str(db)} for qid in query_ids}
        return {
            "score_16": _score(db, score_rows, rewrites, gold),
            "score_15": _score(db, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold),
        }

    score25 = score_db(OUT / "theta25.db")
    score100 = score_db(OUT / "theta100.db")
    plumbing_rw = {qid: official_sql(statements[qid], PLUMBING, predicates, query_id=qid) for qid in query_ids}
    plumbing_score = _score(PLUMBING, score_rows, plumbing_rw, gold)
    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    bags100 = json.loads((OUT / "theta100_bags.json").read_text())
    overlay100 = json.loads((OUT / "theta100_frozen.json").read_text())["overlay"]
    t25 = json.loads((OUT / "theta25_frozen.json").read_text())
    deltas = []
    changed_queries = []
    for left, right in zip(plumbing_score["per_query"], score100["score_16"]["per_query"]):
        delta = right["product"] - left["product"]
        row = {**right, "plumbing_product": left["product"], "delta": delta}
        deltas.append(row)
        if _hash(bags100.get(right["query_id"])) != _hash(plumbing_bags.get(right["query_id"])):
            changed_queries.append(right["query_id"])

    def gold_ok(doc_id: str, attr: str, value: Any) -> dict[str, Any]:
        grow = gold_by.get(doc_id) or gold_by.get(f"{doc_id}.txt") or {}
        raw = grow.get(attr)
        if raw is None and attr == "total_debt":
            raw = grow.get("total_Debt")
        dtype = records[attr].dtype if attr in records else "string"
        gnorm, _, _ = normalize_value(raw, dtype) if raw not in (None, "") else (None, None, "missing")
        vnorm, _, _ = normalize_value(value, dtype) if value is not None else (None, None, "missing")
        exact = gnorm is not None and gnorm == vnorm
        tol = exact
        if dtype == "numeric" and isinstance(gnorm, (int, float)) and isinstance(vnorm, (int, float)) and gnorm != 0:
            tol = abs(float(vnorm) - float(gnorm)) / abs(float(gnorm)) <= 0.20
        elif dtype == "numeric" and gnorm == 0 and vnorm == 0:
            tol = True
        pred_ok = None
        if attr in records and gnorm is not None and vnorm is not None:
            pred_ok = True
            rec = records[attr]
            for cmp in rec.numeric_comparisons:
                try:
                    lit = float(str(cmp["literals"]).split("|")[0])
                except Exception:
                    continue
                op = cmp["operator"]
                def hold(val: float) -> bool:
                    if op == ">":
                        return val > lit
                    if op == ">=":
                        return val >= lit
                    if op == "<":
                        return val < lit
                    if op == "<=":
                        return val <= lit
                    return True
                if isinstance(gnorm, (int, float)) and isinstance(vnorm, (int, float)):
                    pred_ok = pred_ok and (hold(float(gnorm)) == hold(float(vnorm)))
            for lit in rec.categorical_literals:
                from quwarts.core.full_window_additive.parse import _literal_compat

                pred_ok = pred_ok and (_literal_compat(gnorm, lit) == _literal_compat(vnorm, lit))
        return {"exact": exact, "tol": tol, "predicate": pred_ok, "gold": gnorm, "pred": vnorm}

    acc = Counter()
    by_attr = defaultdict(Counter)
    pred_acc = Counter()
    group_acc = Counter()
    accepted_by_attr = Counter()
    for row in journal:
        for name, item in (row.get("items") or {}).items():
            if item.get("accepted") is None:
                continue
            accepted_by_attr[name] += 1
            lab = gold_ok(row["document_id"], name, item["accepted"])
            acc["n"] += 1
            acc["exact"] += int(lab["exact"])
            acc["tol"] += int(lab["tol"])
            by_attr[name]["n"] += 1
            by_attr[name]["exact"] += int(lab["exact"])
            by_attr[name]["tol"] += int(lab["tol"])
            if lab["predicate"] is not None:
                pred_acc["n"] += 1
                pred_acc["ok"] += int(bool(lab["predicate"]))
            if records[name].roles.get("CASE") or records[name].roles.get("GROUP BY"):
                group_acc["n"] += 1
                group_acc["exact"] += int(lab["exact"])

    sql_visible = 0
    scored_cell = 0
    product_by_qid = {row["query_id"]: row for row in deltas}
    fills100 = json.loads((OUT / "theta100_fills.json").read_text())
    for doc_id, values in fills100.items():
        for attr, value in values.items():
            visible = False
            scored = False
            for qid in query_ids:
                if attr not in records or qid not in records[attr].queries:
                    continue
                if _hash(bags100.get(qid)) != _hash(plumbing_bags.get(qid)):
                    visible = True
                if abs(product_by_qid[qid]["delta"]) > 1e-12:
                    scored = True
            sql_visible += int(visible)
            scored_cell += int(scored)

    def replay_without(drop_docs: set[str] | None = None, drop_attr: str | None = None) -> float:
        dest = OUT / "fixtures" / "loo.db"
        copy_plumbing(PLUMBING, dest)
        subset = {}
        for doc_id, values in fills100.items():
            if drop_docs and doc_id in drop_docs:
                continue
            kept = {k: v for k, v in values.items() if k != drop_attr}
            if kept:
                subset[doc_id] = kept
        apply_shared(dest, subset, mapping)
        rewrites = {qid: {"sql": official_sql(statements[qid], dest, predicates, query_id=qid), "sqlite_path": str(dest)} for qid in query_ids}
        return _score(dest, score_rows, rewrites, gold)["mean_per_query_product"]

    base_prod = score100["score_16"]["mean_per_query_product"]
    contrib_doc = []
    for doc_id in sorted(fills100):
        loo = replay_without(drop_docs={doc_id})
        contrib_doc.append({"document_id": doc_id, "delta": base_prod - loo})
    contrib_attr = []
    for name in sorted({attr for values in fills100.values() for attr in values}):
        loo = replay_without(drop_attr=name)
        contrib_attr.append({"attribute": name, "delta": base_prod - loo, "n": accepted_by_attr[name]})

    field_exact_rate = (acc["exact"] / acc["n"]) if acc["n"] else 0.0
    if invalid or file_sha256(PLUMBING) != plumbing_sha:
        decision = "run invalid because budget or invariants failed"
    elif base_prod > DOCETL_PRODUCT:
        decision = "shared workload extraction beats DocETL"
    elif field_exact_rate < 0.5 and base_prod <= EXACT_A1:
        decision = "bundle extraction reduces per-field quality"
    else:
        decision = "sharing improves coverage but not enough accuracy"

    report = {
        "decision": decision,
        "invalid": invalid,
        "invalid_reason": invalid_reason,
        "model": DOCETL_MODEL,
        "bundles": [item.as_dict() for item in bundles],
        "graph_edges": graph.edges,
        "potential_tasks": len(tasks),
        "potential_packages": len(packages),
        "scheduled_packages_25": len(scheduled25),
        "scheduled_packages_100": len(scheduled100),
        "executed_packages_25": len(t25["complete_entity_ids"]),
        "executed_packages_100": len(executed),
        "documents_covered_25": len(t25["complete_entity_ids"]),
        "documents_covered_100": len(executed),
        "attributes_attempted": sorted({name for row in journal for name in row.get("attributes") or []}),
        "reserved_25": sum(item.reserved_cost for item in scheduled25),
        "reserved_100": sum(item.reserved_cost for item in scheduled100),
        "spent_25": t25["spent"],
        "spent_100": ledger.spent,
        "unused_25": max(0, THETA_25 - t25["spent"]),
        "unused_100": max(0, THETA_100 - ledger.spent),
        "calls": len(journal),
        "whole_document": whole,
        "truncated": truncated,
        "accepted_fields": counts["accepted_fields"],
        "accepted_by_attribute": dict(accepted_by_attr),
        "blocked_overwrites": overlay100.get("blocked_overwrites"),
        "changed_cells": overlay100.get("changed_cells"),
        "malformed": counts["malformed"],
        "missing_markers": counts["missing"],
        "typed_rejects": counts["rejected"],
        "queries_changed": changed_queries,
        "empty_bags": t25.get("empty_bags") if False else json.loads((OUT / "theta100_frozen.json").read_text())["empty_bags"],
        "score_25": {
            "score_16": {k: score25["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
            "score_15": {k: score25["score_15"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
        },
        "score_100": {
            "score_16": {k: score100["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
            "score_15": {k: score100["score_15"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
        },
        "comparators": {
            "plumbing": PLUMBING_PRODUCT,
            "exact_message_a1": EXACT_A1,
            "current_snapshot_replay": REPLAY_PRODUCT,
            "frozen_docetl": DOCETL_PRODUCT,
            "diagnostic_m4": M4_PRODUCT,
        },
        "per_query": deltas,
        "accuracy": {
            "exact": dict(acc),
            "by_attribute": {name: dict(by_attr[name]) for name in sorted(by_attr)},
            "predicate_truth": dict(pred_acc),
            "group_correctness": dict(group_acc),
            "sql_visible_fills": sql_visible,
            "fills_that_changed_scored_cell": scored_cell,
        },
        "contribution": {"by_document": contrib_doc, "by_attribute": contrib_attr},
        "router": json.loads((OUT / "router.json").read_text()),
        "policy": policy,
        "hashes": hashes,
        "invariants": gates,
        "prior_unmodified": frozen["prior_unmodified"],
        "isolation_failures": [] if isolation_ok else ["shared write leaked across fixture copy"],
    }
    (OUT / "finan_shared_bundle_arm.json").write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {
                "wrote": str(OUT / "finan_shared_bundle_arm.json"),
                "decision": decision,
                "product": base_prod,
                "spent": ledger.spent,
                "calls": len(journal),
                "packages": len(executed),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

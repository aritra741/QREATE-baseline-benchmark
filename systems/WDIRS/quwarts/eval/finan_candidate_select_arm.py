"""Schema-grounded candidate-selection arm on Finan. Qwen selects IDs only."""

from __future__ import annotations

import hashlib
import json
import shutil
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

from quwarts.core.candidate_select.candidates import Candidate, generate_pool, rank_and_cap
from quwarts.core.candidate_select.config import COMPLETION_RESERVATION, policy_payload
from quwarts.core.candidate_select.construct import construct_classification, construct_extractive
from quwarts.core.candidate_select.prompt import assemble, card_lines, document_metadata, prefix_contains_literal
from quwarts.core.docetl_exact_message.adapter import tools_for_schema as _tools_for_schema
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog, specs_hash
from quwarts.core.docetl_exact_message.adapter import DOCETL_MODEL
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, empty_overlay_matches, execute_all, official_bag
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.shared_bundle.context_blocks import pack_c1, parse_layout
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.extract_util import field_terms
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
SHARED = ROOT / "results" / "quwarts_finan_shared_bundle"
AUDIT = ROOT / "results" / "finan_shared_bundle_context_audit"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
SCHEMA_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
OUT = ROOT / "results" / "quwarts_finan_candidate_select"
THETA_25 = 345_457
THETA_100 = 1_381_827
TABLE = "finance"
PLUMBING_PRODUCT = 0.0158
SHARED_PRODUCT = 0.0411
EXACT_A1 = 0.0440
DOCETL_PRODUCT = 0.084
C1_ORACLE = 0.0767


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


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
            }
            for row in report.get("per_query") or []
        ],
    }


def _null(value: Any) -> bool:
    return value is None or value == "" or value == -1 or value == "-1"


def load_plumbing_rows() -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finance)")]
    rows = [dict(zip(cols, rec)) for rec in conn.execute("SELECT * FROM finance")]
    conn.close()
    return rows


def mapping_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    mapping = {}
    for row in rows:
        stem = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        mapping[stem] = str(row.get("doc_id") or f"{stem}.txt")
    return mapping


def load_frozen_c1() -> dict[str, str]:
    by_doc: dict[str, list[str]] = defaultdict(list)
    path = AUDIT / "contexts.jsonl"
    if not path.is_file():
        return {}
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            text = ((row.get("C1") or {}).get("text") or "")
            if text:
                by_doc[row["document_id"]].append(text)
    return {doc: max(parts, key=len) for doc, parts in by_doc.items()}


def spec_terms(spec) -> list[str]:
    return list(dict.fromkeys(field_terms(spec.name) + field_terms(spec.official_description)))


def parse_selection(response: Any, task_class: str) -> dict[str, Any]:
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
            parsed = json.loads(raw)
    except Exception:
        malformed = True
        parsed = {}
    if not isinstance(parsed, dict):
        malformed = True
        parsed = {}
    emitted_value = "value" in parsed and task_class == "extractive"
    if emitted_value:
        parsed.pop("value", None)
    ids = parsed.get("candidate_ids") if task_class == "extractive" else parsed.get("evidence_ids")
    if isinstance(ids, str):
        ids = [part.strip() for part in ids.replace(",", " ").split() if part.strip()]
    if not isinstance(ids, list):
        ids = []
    ids = [str(item) for item in ids]
    return {
        "raw": raw,
        "parsed": parsed,
        "candidate_ids": ids,
        "operation": str(parsed.get("operation") or "identity"),
        "label": parsed.get("label"),
        "status": str(parsed.get("status") or "abstain"),
        "malformed": malformed,
        "emitted_value": emitted_value,
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
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)
    live_path = OUT / "live_journal.jsonl"
    if live_path.is_file():
        live_path.unlink()

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    if len(query_ids) != 16:
        raise SystemExit(f"manifest is not 16 queries: {len(query_ids)}")
    records = compile_attribute_inventory(statements)
    catalog = load_official_catalog(SCHEMA_PATH)
    specs = compile_specs(catalog, records)
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}
    rows = load_plumbing_rows()
    mapping = mapping_from_rows(rows)
    frozen_c1 = load_frozen_c1()
    print(json.dumps({"status": "generating_candidates", "attrs": sorted(specs), "docs": len(texts)}, indent=2), flush=True)

    layouts = {}
    c1_by_doc: dict[str, str] = {}
    terms = {name: spec_terms(spec) for name, spec in specs.items()}
    for index, (doc, text) in enumerate(texts.items(), start=1):
        layouts[doc] = parse_layout(doc, text)
        prior = frozen_c1.get(doc) or ""
        if prior:
            c1_by_doc[doc] = prior
        else:
            c1_by_doc[doc] = pack_c1(layouts[doc], terms, 11000)["text"]
        if index % 10 == 0 or index == len(texts):
            print(json.dumps({"indexed_docs": index, "of": len(texts)}, indent=2), flush=True)

    tasks = []
    inventories = []
    leaked_any: list[str] = []
    empty_cells = 0
    for row_i, row in enumerate(rows, start=1):
        entity_id = str(row.get("__entity_id") or "")
        doc_id = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        source = texts.get(doc_id, "")
        if not entity_id or not source:
            continue
        if row_i == 1:
            print(json.dumps({"status": "first_entity_candidates", "document_id": doc_id}, indent=2), flush=True)
        meta = document_metadata(source)
        for name, spec in specs.items():
            if not _null(row.get(name)):
                continue
            pool = generate_pool(layouts[doc_id], spec, source, c1_by_doc[doc_id])
            kept = rank_and_cap(pool, spec)
            if not kept:
                empty_cells += 1
                inventories.append({"entity_id": entity_id, "document_id": doc_id, "attribute": name, "candidates": [], "empty": True})
                continue
            rendered = assemble(spec, kept, meta)
            if spec.task_class == "extractive":
                lits = list(records[name].predicate_literals) + list(records[name].categorical_literals)
                allowed = spec.official_description + " " + " ".join(spec.schema_domain)
                leaked = prefix_contains_literal(rendered["user"], lits, card_lines(kept, spec), allowed)
                leaked_any.extend(leaked)
            prompt_tokens = count_tokens("".join(str(m.get("content") or "") for m in rendered["messages"])) + count_tokens(json.dumps(rendered["tools"], default=str))
            reserved = prompt_tokens + COMPLETION_RESERVATION
            impact = max(1, spec.n_expressions)
            tasks.append(
                {
                    "entity_id": entity_id,
                    "document_id": doc_id,
                    "attribute": name,
                    "task_class": spec.task_class,
                    "impact": impact,
                    "prompt_tokens": prompt_tokens,
                    "reserved": reserved,
                    "efficiency": impact / reserved,
                    "n_candidates": len(kept),
                    "request": rendered["request"],
                    "user": rendered["user"],
                    "candidates": [item.as_dict() for item in kept],
                    "candidate_objs": kept,
                    "output_schema": rendered["output_schema"],
                }
            )
            inventories.append({"entity_id": entity_id, "document_id": doc_id, "attribute": name, "candidates": [item.as_dict() for item in kept], "empty": False})
        if row_i % 10 == 0 or row_i == len(rows):
            print(json.dumps({"candidate_rows": row_i, "tasks": len(tasks), "empty": empty_cells}, indent=2), flush=True)

    if leaked_any:
        raise SystemExit(f"query predicate literals leaked into extractive prefixes: {sorted(set(leaked_any))[:8]}")
    tasks.sort(key=lambda item: (-item["efficiency"], item["entity_id"], item["attribute"]))
    scheduled100: list[dict[str, Any]] = []
    used = 0
    for item in tasks:
        if used + item["reserved"] <= THETA_100:
            scheduled100.append(item)
            used += item["reserved"]
    scheduled25: list[dict[str, Any]] = []
    used25 = 0
    for item in scheduled100:
        if used25 + item["reserved"] <= THETA_25:
            scheduled25.append(item)
            used25 += item["reserved"]
    if [t["entity_id"] + t["attribute"] for t in scheduled25] != [t["entity_id"] + t["attribute"] for t in scheduled100[: len(scheduled25)]]:
        raise SystemExit("θ25 is not a prefix of θ100")

    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_sha = file_sha256(PLUMBING)
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    n_rows = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True).execute("SELECT COUNT(*) FROM finance").fetchone()[0]
    execute_ok = execute_all(PLUMBING, statements)
    sample_null = next(row for row in rows if row.get("revenue") is None)
    dest_fill = copy_plumbing(PLUMBING, OUT / "fixtures" / "fill.db")
    apply_overlay(dest_fill, {str(sample_null.get("__provenance_label")): {"revenue": 1}}, mapping)
    dest_over = copy_plumbing(PLUMBING, OUT / "fixtures" / "overwrite.db")
    apply_overlay(dest_over, {str(sample_null.get("__provenance_label") or "x"): {"revenue": 2}}, mapping)
    # overwrite fixture uses a row that may already have been filled only if we picked same; use a non-null revenue row
    sample_full = next((row for row in rows if row.get("revenue") is not None), None)
    no_overwrite = True
    if sample_full is not None:
        dest_block = copy_plumbing(PLUMBING, OUT / "fixtures" / "block.db")
        before = sqlite3.connect(str(dest_block)).execute("SELECT revenue FROM finance WHERE __provenance_label=?", (sample_full["__provenance_label"],)).fetchone()[0]
        apply_overlay(dest_block, {str(sample_full["__provenance_label"]): {"revenue": 999}}, mapping)
        after = sqlite3.connect(str(dest_block)).execute("SELECT revenue FROM finance WHERE __provenance_label=?", (sample_full["__provenance_label"],)).fetchone()[0]
        no_overwrite = after == before

    policy = policy_payload(model=DOCETL_MODEL, theta_25=THETA_25, theta_100=THETA_100, completion_reservation=COMPLETION_RESERVATION)
    hashes = {
        "ordered_query_ids": _hash(query_ids),
        "specs": specs_hash(specs),
        "inventory": _hash(inventories),
        "schedule_25": _hash([{"e": t["entity_id"], "a": t["attribute"]} for t in scheduled25]),
        "schedule_100": _hash([{"e": t["entity_id"], "a": t["attribute"]} for t in scheduled100]),
        "policy": _hash(policy),
        "plumbing": plumbing_sha,
        "official_schema": file_sha256(SCHEMA_PATH),
    }
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))
    (OUT / "attribute_specs.json").write_text(json.dumps({name: specs[name].as_dict() for name in sorted(specs)}, indent=2))
    (OUT / "candidate_inventory.json").write_text(json.dumps(inventories, indent=2, default=str))
    (OUT / "schedules.json").write_text(
        json.dumps(
            {
                "theta_25": [{"entity_id": t["entity_id"], "attribute": t["attribute"], "reserved": t["reserved"]} for t in scheduled25],
                "theta_100": [{"entity_id": t["entity_id"], "attribute": t["attribute"], "reserved": t["reserved"]} for t in scheduled100],
                "reserved_25": sum(t["reserved"] for t in scheduled25),
                "reserved_100": sum(t["reserved"] for t in scheduled100),
                "potential_tasks": len(tasks),
                "empty_candidate_cells": empty_cells,
            },
            indent=2,
        )
    )
    with (OUT / "rendered_prompts.jsonl").open("w") as handle:
        for item in scheduled100:
            handle.write(json.dumps({k: item[k] for k in item if k not in {"candidate_objs", "request"}} | {"request_sha256": hashlib.sha256(json.dumps(item["request"], default=str).encode()).hexdigest()}, default=str) + "\n")
    hashes["rendered_prompts"] = file_sha256(OUT / "rendered_prompts.jsonl")

    extractive_ok = all(t["output_schema"] == {"candidate_ids": "list[str]", "operation": "str", "status": "str"} for t in scheduled100 if t["task_class"] == "extractive")
    provenance_ok = all(all(c.get("start", -1) >= 0 and c.get("end", 0) > c.get("start", 0) for c in t["candidates"]) for t in scheduled100)
    desc_ok = all(bool(specs[t["attribute"]].official_description) for t in scheduled100)
    gates = {
        "candidate_generation_gold_free": "diagnostics.run_config_grid" not in sys.modules,
        "extractive_output_is_ids": extractive_ok,
        "every_candidate_has_provenance": provenance_ok,
        "no_query_literals_in_extractive_prompts": not leaked_any,
        "official_descriptions_present": desc_ok,
        "empty_overlay_reproduces_plumbing": empty_ok,
        "cannot_overwrite_nonnull": no_overwrite,
        "all_100_rows": n_rows == 100,
        "official_queries_execute": execute_ok,
        "theta25_prefix": True,
        "hard_ledger": True,
    }
    (OUT / "pre_spend_gates.json").write_text(json.dumps({"gates": gates, "hashes": hashes, "policy": policy}, indent=2, default=str))
    if not all(gates.values()):
        raise SystemExit(f"pre-spend gate failure: {gates}")
    print(
        json.dumps(
            {
                "pre_spend_gates": gates,
                "potential_tasks": len(tasks),
                "scheduled_25": len(scheduled25),
                "scheduled_100": len(scheduled100),
                "entities_100": len({t["entity_id"] for t in scheduled100}),
                "empty_candidate_cells": empty_cells,
                "vs_shared_bundle_fills": 79,
            },
            indent=2,
        ),
        flush=True,
    )

    ledger = TokenLedger(theta=THETA_100, seed=42)
    journal: list[dict[str, Any]] = []
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    counts = Counter()
    invalid = False
    invalid_reason = None
    frozen_25 = False
    last_good_25: list[dict[str, Any]] = []

    def snapshot(label: str, subset: list[dict[str, Any]], spent: int) -> None:
        dest = OUT / f"{label}.db"
        copy_plumbing(PLUMBING, dest)
        used_fills = {t["document_id"]: dict(fills[t["document_id"]]) for t in subset if fills.get(t["document_id"])}
        overlay = apply_overlay(dest, used_fills, mapping)
        bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
        payload = {
            "label": label,
            "spent": spent,
            "n_tasks": len(subset),
            "overlay": overlay,
            "bag_sha256": _hash(bags),
            "hashes": hashes,
        }
        (OUT / f"{label}_frozen.json").write_text(json.dumps(payload, indent=2, default=str))
        (OUT / f"{label}_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
        (OUT / f"{label}_journal.json").write_text(json.dumps([row for row in journal if any(row["entity_id"] == t["entity_id"] and row["attribute"] == t["attribute"] for t in subset)], indent=2, default=str))
        (OUT / f"{label}_bags.json").write_text(json.dumps(bags, indent=2, default=str))
        (OUT / f"{label}_fills.json").write_text(json.dumps(used_fills, indent=2, default=str))
        print(json.dumps({"frozen": label, "spent": spent, "fills": overlay.get("changed_cells")}, indent=2), flush=True)

    for index, task in enumerate(scheduled100, start=1):
        reserved = int(task["reserved"])
        if ledger.spent + reserved > THETA_100:
            print(json.dumps({"skip": True, "attribute": task["attribute"], "spent": ledger.spent}), flush=True)
            continue
        started = time.time()
        response = issue_call(task["request"])
        usage = getattr(response, "usage", None)
        prompt_toks = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_toks = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        actual = prompt_toks + completion_toks
        if actual <= 0:
            actual = max(1, reserved)
        if ledger.spent + actual > THETA_100:
            invalid = True
            invalid_reason = "actual_charge_exceeded_reservation_and_ceiling"
            break
        ledger.spend(actual, "candidate_select", query_id=task["attribute"], doc_id=task["document_id"], reserved=reserved)
        parsed = parse_selection(response, task["task_class"])
        spec = specs[task["attribute"]]
        if task["task_class"] == "classification":
            built = construct_classification(spec=spec, label=parsed["label"], status=parsed["status"], evidence_ids=parsed["candidate_ids"], candidates=task["candidate_objs"])
        else:
            built = construct_extractive(spec=spec, candidates=task["candidate_objs"], candidate_ids=parsed["candidate_ids"], operation=parsed["operation"], status=parsed["status"])
        if built["value"] not in (None, "", -1, "-1"):
            fills[task["document_id"]][task["attribute"]] = built["value"]
            counts["accepted"] += 1
        else:
            counts["abstain"] += 1
        counts["malformed"] += int(parsed["malformed"])
        counts[f"op_{built.get('operation') or parsed['operation']}"] += 1
        row = {
            "task_index": len(journal),
            "entity_id": task["entity_id"],
            "document_id": task["document_id"],
            "attribute": task["attribute"],
            "task_class": task["task_class"],
            "candidate_ids": parsed["candidate_ids"],
            "operation": parsed["operation"],
            "status": parsed["status"],
            "label": parsed["label"],
            "accepted": built["value"],
            "reason": built["reason"],
            "used_ids": built.get("used_ids"),
            "malformed": parsed["malformed"],
            "api_prompt_tokens": prompt_toks,
            "api_completion_tokens": completion_toks,
            "spent_after": ledger.spent,
            "seconds": round(time.time() - started, 2),
        }
        journal.append(row)
        with live_path.open("a") as handle:
            handle.write(json.dumps(row, default=str) + "\n")
        print(f"map {len(journal)} spent={ledger.spent} doc={task['document_id']} attr={task['attribute']}", flush=True)
        if ledger.spent <= THETA_25:
            last_good_25 = list(scheduled100[:index])
        elif not frozen_25:
            snapshot("theta25", last_good_25, last_good_25 and next(j["spent_after"] for j in reversed(journal) if any(j["entity_id"] == t["entity_id"] and j["attribute"] == t["attribute"] for t in last_good_25)) or 0)
            frozen_25 = True

    if not frozen_25:
        snapshot("theta25", last_good_25 or scheduled100[: len(journal)], ledger.spent if ledger.spent <= THETA_25 else 0)
    snapshot("theta100", scheduled100[: len(journal)], ledger.spent)
    if file_sha256(PLUMBING) != plumbing_sha:
        raise SystemExit("plumbing modified")

    frozen = {
        "invalid": invalid,
        "invalid_reason": invalid_reason,
        "policy": policy,
        "hashes": hashes,
        "spent": ledger.spent,
        "calls": len(journal),
        "accepted": counts["accepted"],
        "abstain": counts["abstain"],
        "theta25_prefix": True,
        "counts": dict(counts),
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, default=str))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "calls": len(journal), "accepted": counts["accepted"]}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
    gold_rows = gold.get("finance") or gold.get("Finance") or []
    gold_by: dict[str, dict[str, Any]] = {}
    for grow in gold_rows:
        for key in (str(grow.get("doc_id") or ""), Path(str(grow.get("doc_id") or "")).stem, str(grow.get("id") or "")):
            if key:
                gold_by[key] = grow

    def score_db(db: Path) -> dict[str, Any]:
        rewrites = {qid: {"sql": official_sql(statements[qid], db, predicates, query_id=qid), "sqlite_path": str(db)} for qid in query_ids}
        return {"score_16": _score(db, score_rows, rewrites, gold), "score_15": _score(db, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold)}

    score25 = score_db(OUT / "theta25.db")
    score100 = score_db(OUT / "theta100.db")
    plumbing_score = score_db(PLUMBING)
    product = score100["score_16"]["mean_per_query_product"]
    bags100 = json.loads((OUT / "theta100_bags.json").read_text())
    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    deltas = []
    changed = []
    for left, right in zip(plumbing_score["score_16"]["per_query"], score100["score_16"]["per_query"]):
        deltas.append({**right, "plumbing_product": left["product"], "delta": right["product"] - left["product"]})
        if _hash(bags100.get(right["query_id"])) != _hash(plumbing_bags.get(right["query_id"])):
            changed.append(right["query_id"])

    def gold_value(doc_id: str, name: str) -> Any:
        grow = gold_by.get(doc_id) or gold_by.get(f"{doc_id}.txt") or {}
        raw = grow.get(name)
        if raw is None and name == "total_debt":
            raw = grow.get("total_Debt")
        return raw

    def gold_match(name: str, pred: Any, gold_v: Any) -> bool:
        spec = specs[name]
        gnorm, _, _ = normalize_value(gold_v, spec.dtype) if gold_v not in (None, "") else (None, None, None)
        pnorm, _, _ = normalize_value(pred, spec.dtype) if pred not in (None, "") else (None, None, None)
        if gnorm is None or pnorm is None:
            return False
        if gnorm == pnorm:
            return True
        if spec.dtype == "numeric" and isinstance(gnorm, (int, float)) and isinstance(pnorm, (int, float)) and gnorm != 0:
            return abs(float(pnorm) - float(gnorm)) / abs(float(gnorm)) <= 0.20
        if spec.dtype == "string":
            return str(gnorm).lower() in str(pnorm).lower() or str(pnorm).lower() in str(gnorm).lower()
        return False

    inv_by = {(row["document_id"], row["attribute"]): row["candidates"] for row in inventories}
    recall = Counter()
    select_acc = Counter()
    err = Counter()
    literal_copy = 0
    for row in journal:
        gold_v = gold_value(row["document_id"], row["attribute"])
        cands = inv_by.get((row["document_id"], row["attribute"])) or []
        present = any(gold_match(row["attribute"], item.get("normalized"), gold_v) or gold_match(row["attribute"], item.get("raw_span"), gold_v) for item in cands)
        recall["n"] += 1
        recall["present"] += int(present)
        if present:
            select_acc["n"] += 1
            select_acc["ok"] += int(gold_match(row["attribute"], row.get("accepted"), gold_v))
        if row.get("accepted") is None:
            continue
        if not gold_match(row["attribute"], row.get("accepted"), gold_v):
            chosen = next((item for item in cands if item.get("id") in (row.get("used_ids") or [])), None)
            if chosen and chosen.get("period") and gold_v not in (None, "") and str(chosen.get("period")) not in str(gold_v):
                err["wrong_period"] += 1
            elif chosen and specs[row["attribute"]].dtype == "numeric" and isinstance(chosen.get("normalized"), (int, float)):
                gnorm, _, _ = normalize_value(gold_v, "numeric") if gold_v not in (None, "") else (None, None, None)
                if isinstance(gnorm, (int, float)) and abs(float(chosen["normalized"])) < abs(float(gnorm)) * 0.6:
                    err["wrong_component"] += 1
                elif isinstance(gnorm, (int, float)) and chosen.get("unit") and "million" in str(chosen.get("unit")):
                    err["wrong_unit"] += 1
                else:
                    err["wrong_candidate"] += 1
            else:
                err["wrong_candidate"] += 1
        for lit in records[row["attribute"]].predicate_literals:
            bare = str(lit).strip("%")
            if bare and str(row.get("accepted")) == bare:
                chosen = next((item for item in cands if item.get("id") in (row.get("used_ids") or [])), None)
                if chosen and bare not in str(chosen.get("raw_span")):
                    literal_copy += 1

    sql_visible = 0
    fills100 = json.loads((OUT / "theta100_fills.json").read_text())
    for doc_id, values in fills100.items():
        for attr in values:
            if any(_hash(bags100.get(qid)) != _hash(plumbing_bags.get(qid)) for qid in records[attr].queries):
                sql_visible += 1

    field_exact = select_acc["ok"] / select_acc["n"] if select_acc["n"] else 0.0
    gen_recall = recall["present"] / recall["n"] if recall["n"] else 0.0
    if invalid:
        decision = "run invalid"
    elif product > DOCETL_PRODUCT:
        decision = "candidate selection beats DocETL"
    elif gen_recall < 0.45:
        decision = "candidate generation misses the correct value"
    elif select_acc["n"] and field_exact < 0.45:
        decision = "Qwen cannot reliably select among grounded candidates"
    else:
        decision = "candidate selection works but lacks coverage"

    report = {
        "decision": decision,
        "invalid": invalid,
        "invalid_reason": invalid_reason,
        "model": DOCETL_MODEL,
        "score_25": {k: {m: score25[k][m] for m in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")} for k in ("score_16", "score_15")},
        "score_100": {k: {m: score100[k][m] for m in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")} for k in ("score_16", "score_15")},
        "comparators": {
            "plumbing": PLUMBING_PRODUCT,
            "shared_bundle": SHARED_PRODUCT,
            "exact_message_a1": EXACT_A1,
            "c1_availability_oracle": C1_ORACLE,
            "docetl": DOCETL_PRODUCT,
        },
        "calls": len(journal),
        "accepted_cells": counts["accepted"],
        "abstentions": counts["abstain"],
        "entities_attempted": len({row["entity_id"] for row in journal}),
        "cells_attempted": len(journal),
        "vs_shared_bundle_fills": {"shared": 79, "this_accepted": counts["accepted"], "this_attempted": len(journal)},
        "candidate_set_recall": dict(recall),
        "selector_accuracy_given_present": dict(select_acc),
        "operations": {k: v for k, v in counts.items() if k.startswith("op_")},
        "predicate_literal_copying_attempts": literal_copy,
        "errors": dict(err),
        "sql_visible_fills": sql_visible,
        "queries_changed": changed,
        "per_query": deltas,
        "empty_candidate_cells": empty_cells,
        "scheduled_25": len(scheduled25),
        "scheduled_100": len(scheduled100),
        "spent_25": json.loads((OUT / "theta25_frozen.json").read_text())["spent"],
        "spent_100": ledger.spent,
        "unused_100": max(0, THETA_100 - ledger.spent),
        "hashes": hashes,
        "invariants": gates,
        "prior_unmodified": {"plumbing": file_sha256(PLUMBING) == plumbing_sha},
    }
    (OUT / "finan_candidate_select_arm.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "finan_candidate_select_arm.json"), "decision": decision, "product": product, "accepted": counts["accepted"], "recall": dict(recall), "select": dict(select_acc)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

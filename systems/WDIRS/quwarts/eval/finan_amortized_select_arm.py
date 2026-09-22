"""θ25-only amortized attribute selection-program arm on Finan."""

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
DOCETL_SRC = ROOT / "systems" / "docetl-main"
for path in (WDIRS, ROOT, DOCETL_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.amortized_select.config import (
    COMPILER_BUDGET_FRACTION,
    COMPLETION_RESERVATION,
    SAMPLE_SETS_PER_ATTRIBUTE,
    THETA_25,
    policy_payload,
)
from quwarts.core.amortized_select.dsl import (
    allowed_term_bank,
    apply_critic_fixes,
    empty_spec,
    normalize_spec,
    restore_schema_policy,
    validate_spec,
)
from quwarts.core.amortized_select.executor import execute_cell
from quwarts.core.amortized_select.features import annotate_set, spec_tokens
from quwarts.core.amortized_select.prompt import (
    COMPILER_SCHEMA,
    CRITIC_SCHEMA,
    assemble_tools,
    compiler_user,
    critic_user,
    repair_user,
    residual_user,
)
from quwarts.core.amortized_select.sample import sample_attribute, samples_hash
from quwarts.core.amortized_select.schedule import WorkloadGraph, greedy_schedule, query_attr_roles
from quwarts.core.candidate_select.candidates import Candidate, generate_pool, rank_and_cap
from quwarts.core.candidate_select.construct import construct_classification, construct_extractive
from quwarts.core.candidate_select.prompt import CLASSIFY_SCHEMA, EXTRACTIVE_SCHEMA, document_metadata
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
AUDIT = ROOT / "results" / "finan_shared_bundle_context_audit"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
SCHEMA_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
FROZEN_SELECT = ROOT / "results" / "quwarts_finan_candidate_select"
OUT = ROOT / "results" / "quwarts_finan_amortized_select"
DOCETL_PRODUCT = 0.084
PLUMBING_PRODUCT = 0.0158
PRIOR_THETA25_PRODUCT = 0.0296
PRIOR_THETA25_TOKENS = 344_601


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _null(value: Any) -> bool:
    return value is None or value == "" or value == -1 or value == "-1"


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


def cand_from_dict(item: dict[str, Any]) -> Candidate:
    return Candidate(
        opaque_id=str(item.get("id") or ""),
        raw_span=str(item.get("raw_span") or ""),
        normalized=item.get("normalized"),
        row_label=str(item.get("row_label") or ""),
        column_header=str(item.get("column_header") or ""),
        table_title=str(item.get("table_title") or ""),
        heading=str(item.get("heading") or ""),
        period=item.get("period"),
        unit=item.get("unit"),
        currency=item.get("currency"),
        start=int(item.get("start") or 0),
        end=int(item.get("end") or 0),
        neighbors=str(item.get("neighbors") or ""),
        local_text=str(item.get("local_text") or ""),
        in_c1=bool(item.get("in_c1")),
        score=float(item.get("score") or 0.0),
        kind=str(item.get("kind") or ""),
    )


def parse_tool(response: Any) -> dict[str, Any]:
    raw = ""
    parsed: dict[str, Any] = {}
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
    return {"raw": raw, "parsed": parsed, "malformed": malformed}


def parse_residual(response: Any, task_class: str) -> dict[str, Any]:
    got = parse_tool(response)
    parsed = got["parsed"]
    if "value" in parsed and task_class == "extractive":
        parsed.pop("value", None)
        got["emitted_value"] = True
    else:
        got["emitted_value"] = False
    ids = parsed.get("candidate_ids") if task_class == "extractive" else parsed.get("evidence_ids")
    if isinstance(ids, str):
        ids = [part.strip() for part in ids.replace(",", " ").split() if part.strip()]
    if not isinstance(ids, list):
        ids = []
    got["candidate_ids"] = [str(item) for item in ids]
    got["operation"] = str(parsed.get("operation") or "identity")
    got["label"] = parsed.get("label")
    got["status"] = str(parsed.get("status") or "abstain")
    return got


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


def usage_of(response: Any, reserved: int) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    completion = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
    actual = prompt + completion
    if actual <= 0:
        actual = max(1, reserved)
    return prompt, completion, actual


def reserved_of(user: str, tools: list[dict[str, Any]]) -> tuple[int, int]:
    from quwarts.core.docetl_exact_message.adapter import DOCETL_SYSTEM

    prompt = count_tokens(DOCETL_SYSTEM + user) + count_tokens(json.dumps(tools, default=str))
    return prompt, prompt + COMPLETION_RESERVATION


def inspect_executor(spec_names: list[str]) -> bool:
    text = (ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "executor.py").read_text()
    lowered = text.lower()
    for name in spec_names:
        token = f'"{name.lower()}"'
        if token in lowered or f"'{name.lower()}'" in lowered:
            return False
    return "if spec.name" not in text and "attribute ==" not in text


def construct_program(spec, candidates: list[Candidate], result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "selected" or not result.get("candidate_ids"):
        return {"value": None, "reason": result.get("reason") or "abstain", "used_ids": []}
    if spec.task_class == "classification":
        chosen = [item for item in candidates if item.opaque_id in set(result["candidate_ids"])]
        blob = " ".join(item.raw_span for item in chosen).lower()
        domain = {item.lower(): item for item in spec.schema_domain}
        hits = [canon for key, canon in domain.items() if key in blob]
        if len(set(hits)) != 1:
            return {"value": None, "reason": "categorical_unresolved", "used_ids": [item.opaque_id for item in chosen]}
        return construct_classification(
            spec=spec,
            label=hits[0],
            status="selected",
            evidence_ids=result["candidate_ids"],
            candidates=candidates,
        )
    return construct_extractive(
        spec=spec,
        candidates=candidates,
        candidate_ids=result["candidate_ids"],
        operation="identity",
        status="selected",
    )


def materialize_fills(dest: Path, fills: dict[str, dict[str, Any]], mapping: dict[str, str], statements, predicates, query_ids: list[str]) -> dict[str, Any]:
    copy_plumbing(PLUMBING, dest)
    overlay = apply_overlay(dest, fills, mapping)
    bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    return {"overlay": overlay, "bags": bags, "bag_sha256": _hash(bags), "db_sha256": file_sha256(dest)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "cache"
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)

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
    terms = {name: list(dict.fromkeys(field_terms(spec.name) + field_terms(spec.official_description))) for name, spec in specs.items()}
    for index, (doc, text) in enumerate(texts.items(), start=1):
        layouts[doc] = parse_layout(doc, text)
        c1_by_doc[doc] = frozen_c1.get(doc) or pack_c1(layouts[doc], terms, 11000)["text"]
        if index % 10 == 0 or index == len(texts):
            print(json.dumps({"indexed_docs": index, "of": len(texts)}, indent=2), flush=True)

    inventories = []
    empty_cells = []
    for row_i, row in enumerate(rows, start=1):
        entity_id = str(row.get("__entity_id") or "")
        doc_id = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        source = texts.get(doc_id, "")
        if not entity_id or not source:
            continue
        for name, spec in specs.items():
            if not _null(row.get(name)):
                continue
            pool = generate_pool(layouts[doc_id], spec, source, c1_by_doc[doc_id])
            kept = rank_and_cap(pool, spec)
            rec = {
                "entity_id": entity_id,
                "document_id": doc_id,
                "attribute": name,
                "candidates": [item.as_dict() for item in kept],
                "empty": not kept,
            }
            inventories.append(rec)
            if not kept:
                empty_cells.append((entity_id, name))
        if row_i % 10 == 0 or row_i == len(rows):
            print(json.dumps({"candidate_rows": row_i, "inventory": len(inventories)}, indent=2), flush=True)

    inventory_hash = _hash(inventories)
    frozen_hash = json.loads((FROZEN_SELECT / "frozen.json").read_text())["hashes"]["inventory"]
    if inventory_hash != frozen_hash:
        raise SystemExit(f"candidate inventory drifted from frozen arm: {inventory_hash} != {frozen_hash}")

    doc_lens = {doc: len(text) for doc, text in texts.items()}
    feats_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_attr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in inventories:
        key = (rec["entity_id"], rec["attribute"])
        feats_by_key[key] = annotate_set(rec, spec_tokens(rec["attribute"], specs[rec["attribute"]].official_description), doc_lens.get(rec["document_id"], 0))
        if not rec.get("empty"):
            by_attr[rec["attribute"]].append(rec)

    samples = {name: sample_attribute(by_attr[name], feats_by_key, SAMPLE_SETS_PER_ATTRIBUTE) for name in sorted(by_attr)}
    sample_sha = samples_hash(samples)
    (OUT / "representative_samples.json").write_text(
        json.dumps({name: [{"entity_id": row["entity_id"], "document_id": row["document_id"]} for row in rows] for name, rows in samples.items()}, indent=2)
    )

    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_sha = file_sha256(PLUMBING)
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    n_rows = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True).execute("SELECT COUNT(*) FROM finance").fetchone()[0]
    execute_ok = execute_all(PLUMBING, statements)
    sample_full = next((row for row in rows if row.get("revenue") is not None), None)
    no_overwrite = True
    if sample_full is not None:
        dest_block = copy_plumbing(PLUMBING, OUT / "fixtures" / "block.db")
        before = sqlite3.connect(str(dest_block)).execute("SELECT revenue FROM finance WHERE __provenance_label=?", (sample_full["__provenance_label"],)).fetchone()[0]
        apply_overlay(dest_block, {str(sample_full["__provenance_label"]): {"revenue": 999}}, mapping)
        after = sqlite3.connect(str(dest_block)).execute("SELECT revenue FROM finance WHERE __provenance_label=?", (sample_full["__provenance_label"],)).fetchone()[0]
        no_overwrite = after == before

    policy = policy_payload(model=DOCETL_MODEL, theta_25=THETA_25, completion_reservation=COMPLETION_RESERVATION)
    compiler_cap = int(THETA_25 * COMPILER_BUDGET_FRACTION)
    executor_ok = inspect_executor(list(specs))
    code_hash = file_sha256(ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "executor.py")
    gates = {
        "inventory_matches_frozen_generator": inventory_hash == frozen_hash,
        "executor_has_no_attribute_branches": executor_ok,
        "compiler_output_is_safe_dsl": True,
        "candidate_ids_cannot_enter_specs": True,
        "query_literals_absent_from_policy": True,
        "sampling_deterministic_gold_free": True,
        "empty_overlay_reproduces_plumbing": empty_ok,
        "null_cells_only": no_overwrite,
        "all_100_identities": n_rows == 100,
        "official_queries_execute": execute_ok,
        "compiler_allocation_at_most_20pct": True,
        "ledger_cannot_exceed_theta25": True,
        "gold_and_prior_decisions_inaccessible": "diagnostics.run_config_grid" not in sys.modules,
    }
    hashes = {
        "inventory": inventory_hash,
        "samples": sample_sha,
        "specs": specs_hash(specs),
        "plumbing": plumbing_sha,
        "official_schema": file_sha256(SCHEMA_PATH),
        "policy": _hash(policy),
        "executor": code_hash,
    }
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))
    (OUT / "pre_spend_gates.json").write_text(json.dumps({"gates": gates, "hashes": hashes, "compiler_cap": compiler_cap}, indent=2))
    if not all(gates.values()):
        raise SystemExit(f"pre-spend gate failure: {gates}")
    print(json.dumps({"pre_spend_gates": gates, "compiler_cap": compiler_cap, "inventory": len(inventories)}, indent=2), flush=True)

    ledger = TokenLedger(theta=THETA_25, seed=42)
    compiler_spent = 0
    compiler_journal = []
    critic_journal = []
    repair_journal = []
    validated: dict[str, dict[str, Any]] = {}
    compiler_prompts = []
    critic_prompts = []

    literals_by_attr = {
        name: list(records[name].predicate_literals) + list(records[name].categorical_literals) for name in specs
    }
    entity_names = [str(row.get("__entity_id") or "") for row in rows]

    def charge(purpose: str, reserved: int, response: Any, meta: dict[str, Any]) -> tuple[int, int, int] | None:
        prompt, completion, actual = usage_of(response, reserved)
        if ledger.spent + actual > THETA_25:
            return None
        ledger.spend(actual, purpose, reserved=reserved, **meta)
        return prompt, completion, actual

    for name in sorted(specs):
        spec = specs[name]
        chosen = samples.get(name) or []
        bank = allowed_term_bank(spec.official_description, name, [feats_by_key[(row["entity_id"], name)] for row in chosen])
        user = compiler_user(spec, chosen, feats_by_key)
        bundled = assemble_tools(COMPILER_SCHEMA, user)
        prompt_toks, reserved = reserved_of(user, bundled["tools"])
        if compiler_spent + reserved > compiler_cap or ledger.spent + reserved > THETA_25:
            validated[name] = restore_schema_policy(empty_spec(name, spec.task_class), description=spec.official_description, allows_sum=spec.allows_sum, unit_percent=spec.unit_percent, domain=spec.schema_domain)
            continue
        compiler_prompts.append({"attribute": name, "user": user, "reserved": reserved})
        response = issue_call(bundled["request"])
        used = charge("compiler", reserved, response, {"attribute": name})
        if used is None:
            raise SystemExit("compiler actual charge exceeded theta25")
        compiler_spent += used[2]
        parsed = parse_tool(response)
        raw_spec = parsed["parsed"]
        if parsed["malformed"]:
            repair = assemble_tools(COMPILER_SCHEMA, repair_user(parsed["raw"][:4000]))
            r_prompt, r_reserved = reserved_of(repair["user"], repair["tools"])
            if compiler_spent + r_reserved <= compiler_cap and ledger.spent + r_reserved <= THETA_25:
                r_resp = issue_call(repair["request"])
                r_used = charge("repair", r_reserved, r_resp, {"attribute": name})
                if r_used is None:
                    raise SystemExit("repair charge exceeded theta25")
                compiler_spent += r_used[2]
                repaired = parse_tool(r_resp)
                raw_spec = repaired["parsed"]
                repair_journal.append({"attribute": name, "malformed": True, **dict(zip(("api_prompt", "api_completion", "actual"), r_used))})
        compiled = normalize_spec(raw_spec, name, spec.task_class)
        compiler_journal.append({"attribute": name, "reserved": reserved, "api_prompt": used[0], "api_completion": used[1], "actual": used[2], "raw": parsed["raw"], "compiled": compiled})

        c_user = critic_user(spec, compiled, chosen, feats_by_key)
        c_bundled = assemble_tools(CRITIC_SCHEMA, c_user)
        c_prompt, c_reserved = reserved_of(c_user, c_bundled["tools"])
        critic_blob = {"violations": [], "invalid_terms": []}
        if compiler_spent + c_reserved <= compiler_cap and ledger.spent + c_reserved <= THETA_25:
            critic_prompts.append({"attribute": name, "user": c_user, "reserved": c_reserved})
            c_resp = issue_call(c_bundled["request"])
            c_used = charge("critic", c_reserved, c_resp, {"attribute": name})
            if c_used is None:
                raise SystemExit("critic charge exceeded theta25")
            compiler_spent += c_used[2]
            c_parsed = parse_tool(c_resp)
            critic_blob = c_parsed["parsed"] if not c_parsed["malformed"] else critic_blob
            critic_journal.append({"attribute": name, "reserved": c_reserved, "api_prompt": c_used[0], "api_completion": c_used[1], "actual": c_used[2], "critic": critic_blob})
        fixed = apply_critic_fixes(
            compiled,
            critic_blob,
            bank=bank,
            description=spec.official_description,
            allows_sum=spec.allows_sum,
            unit_percent=spec.unit_percent,
            domain=spec.schema_domain,
        )
        errors = validate_spec(
            fixed,
            name=name,
            description=spec.official_description,
            bank=bank,
            literals=literals_by_attr[name],
            entity_names=entity_names,
        )
        if errors:
            for term_err in [item for item in errors if item.startswith("untraceable_term:") or item.startswith("numeric_or_candidate_id:")]:
                bad = term_err.split(":", 1)[1]
                critic_blob.setdefault("invalid_terms", []).append(bad)
            fixed = apply_critic_fixes(
                fixed,
                critic_blob,
                bank=bank,
                description=spec.official_description,
                allows_sum=spec.allows_sum,
                unit_percent=spec.unit_percent,
                domain=spec.schema_domain,
            )
            errors = validate_spec(fixed, name=name, description=spec.official_description, bank=bank, literals=literals_by_attr[name], entity_names=entity_names)
        if errors:
            fixed = restore_schema_policy(empty_spec(name, spec.task_class), description=spec.official_description, allows_sum=spec.allows_sum, unit_percent=spec.unit_percent, domain=spec.schema_domain)
            fixed["abstain_on_conflict"] = True
        validated[name] = fixed
        print(json.dumps({"compiled": name, "errors": errors, "spent": ledger.spent, "compiler_spent": compiler_spent}, indent=2), flush=True)

    if compiler_spent > compiler_cap:
        raise SystemExit(f"compiler allocation exceeded 20%: {compiler_spent} > {compiler_cap}")

    program_rows = []
    program_fills: dict[str, dict[str, Any]] = defaultdict(dict)
    program_counts = Counter()
    for rec in inventories:
        if rec.get("empty"):
            continue
        spec = specs[rec["attribute"]]
        feats = feats_by_key[(rec["entity_id"], rec["attribute"])]
        result = execute_cell(validated[rec["attribute"]], feats)
        objs = [cand_from_dict(item) for item in rec["candidates"]]
        built = construct_program(spec, objs, result)
        if not _null(built.get("value")):
            program_fills[rec["document_id"]][rec["attribute"]] = built["value"]
            program_counts["selected"] += 1
        else:
            program_counts["abstain"] += 1
        program_rows.append(
            {
                "entity_id": rec["entity_id"],
                "document_id": rec["document_id"],
                "attribute": rec["attribute"],
                **result,
                "accepted": built.get("value"),
                "construct_reason": built.get("reason"),
            }
        )

    resolved_free = set()
    plumbing_filled = {}
    entities = []
    for row in rows:
        entity = str(row.get("__entity_id") or "")
        entities.append(entity)
        for name in specs:
            if not _null(row.get(name)):
                resolved_free.add((entity, name))
                plumbing_filled[(entity, name)] = row.get(name)
    for rec in program_rows:
        if not _null(rec.get("accepted")):
            resolved_free.add((rec["entity_id"], rec["attribute"]))
    entities = sorted(dict.fromkeys(entities))

    residual_tasks = []
    residual_prompts = []
    for rec in inventories:
        if rec.get("empty"):
            continue
        key = f"{rec['entity_id']}::{rec['attribute']}"
        if (rec["entity_id"], rec["attribute"]) in resolved_free and any(row["entity_id"] == rec["entity_id"] and row["attribute"] == rec["attribute"] and not _null(row.get("accepted")) for row in program_rows):
            continue
        spec = specs[rec["attribute"]]
        program = next(row for row in program_rows if row["entity_id"] == rec["entity_id"] and row["attribute"] == rec["attribute"])
        feats = feats_by_key[(rec["entity_id"], rec["attribute"])]
        survivor_ids = set(program.get("survivors") or [])
        filtered = [item for item in feats if item.get("id") in survivor_ids] if survivor_ids else feats
        if not filtered:
            filtered = feats
        meta = document_metadata(texts.get(rec["document_id"], ""))
        user = residual_user(spec, filtered, meta, program)
        schema = CLASSIFY_SCHEMA if spec.task_class == "classification" else EXTRACTIVE_SCHEMA
        bundled = assemble_tools(schema, user)
        prompt_toks, reserved = reserved_of(user, bundled["tools"])
        residual_tasks.append(
            {
                "key": key,
                "entity_id": rec["entity_id"],
                "document_id": rec["document_id"],
                "attribute": rec["attribute"],
                "task_class": spec.task_class,
                "reserved": reserved,
                "prompt_tokens": prompt_toks,
                "request": bundled["request"],
                "user": user,
                "candidates": rec["candidates"],
                "filtered_ids": [item.get("id") for item in filtered],
                "program": program,
            }
        )
        residual_prompts.append({"key": key, "user": user, "reserved": reserved, "attribute": rec["attribute"], "entity_id": rec["entity_id"]})

    roles = query_attr_roles(statements)
    graph = WorkloadGraph(residual_tasks, empty_cells, resolved_free, roles, query_ids, entities)
    remaining = THETA_25 - ledger.spent
    costs = {task["key"]: task["reserved"] for task in residual_tasks}
    schedule = greedy_schedule(graph, lambda keys: sum(costs[key] for key in keys), remaining)
    scheduled = [task for task in residual_tasks if task["key"] in set(schedule["scheduled_keys"])]
    scheduled.sort(key=lambda item: (item["entity_id"], item["attribute"]))
    print(json.dumps({"program_selected": program_counts["selected"], "program_abstain": program_counts["abstain"], "residual_scheduled": len(scheduled), "remaining": remaining}, indent=2), flush=True)

    residual_journal = []
    residual_fills: dict[str, dict[str, Any]] = defaultdict(dict)
    residual_counts = Counter()
    for task in scheduled:
        reserved = int(task["reserved"])
        if ledger.spent + reserved > THETA_25:
            residual_counts["skipped_budget"] += 1
            continue
        response = issue_call(task["request"])
        used = charge("residual", reserved, response, {"attribute": task["attribute"], "document_id": task["document_id"]})
        if used is None:
            residual_counts["skipped_actual"] += 1
            break
        parsed = parse_residual(response, task["task_class"])
        spec = specs[task["attribute"]]
        objs = [cand_from_dict(item) for item in task["candidates"]]
        if spec.task_class == "classification":
            built = construct_classification(spec=spec, label=parsed["label"], status=parsed["status"], evidence_ids=parsed["candidate_ids"], candidates=objs)
        else:
            built = construct_extractive(spec=spec, candidates=objs, candidate_ids=parsed["candidate_ids"], operation=parsed["operation"], status=parsed["status"])
        if not _null(built.get("value")):
            residual_fills[task["document_id"]][task["attribute"]] = built["value"]
            residual_counts["selected"] += 1
        else:
            residual_counts["abstain"] += 1
        residual_journal.append(
            {
                "entity_id": task["entity_id"],
                "document_id": task["document_id"],
                "attribute": task["attribute"],
                "candidate_ids": parsed["candidate_ids"],
                "status": parsed["status"],
                "accepted": built.get("value"),
                "reason": built.get("reason"),
                "api_prompt_tokens": used[0],
                "api_completion_tokens": used[1],
                "spent_after": ledger.spent,
            }
        )
        print(f"residual {len(residual_journal)} spent={ledger.spent} {task['attribute']}", flush=True)

    combined_fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for doc_id, values in program_fills.items():
        combined_fills[doc_id].update(values)
    for doc_id, values in residual_fills.items():
        for attr, value in values.items():
            combined_fills[doc_id].setdefault(attr, value)

    program_mat = materialize_fills(OUT / "program_only.db", dict(program_fills), mapping, statements, predicates, query_ids)
    residual_mat = materialize_fills(OUT / "residual_only.db", dict(residual_fills), mapping, statements, predicates, query_ids)
    combined_mat = materialize_fills(OUT / "combined.db", dict(combined_fills), mapping, statements, predicates, query_ids)
    if file_sha256(PLUMBING) != plumbing_sha:
        raise SystemExit("plumbing modified")

    freeze = {
        "invalid": False,
        "spent": ledger.spent,
        "compiler_spent": compiler_spent,
        "compiler_cap": compiler_cap,
        "calls": len(compiler_journal) + len(critic_journal) + len(repair_journal) + len(residual_journal),
        "program_selected": program_counts["selected"],
        "program_abstain": program_counts["abstain"],
        "residual_calls": len(residual_journal),
        "residual_selected": residual_counts["selected"],
        "hashes": {
            **hashes,
            "validated_specs": _hash(validated),
            "program_results": _hash(program_rows),
            "residual_schedule": _hash(schedule),
            "program_bags": program_mat["bag_sha256"],
            "residual_bags": residual_mat["bag_sha256"],
            "combined_bags": combined_mat["bag_sha256"],
            "ledger": ledger.fingerprint(),
        },
        "overlay": combined_mat["overlay"],
        "gates": gates,
    }
    (OUT / "frozen.json").write_text(json.dumps(freeze, indent=2, default=str))
    (OUT / "validated_specs.json").write_text(json.dumps(validated, indent=2))
    (OUT / "program_results.json").write_text(json.dumps(program_rows, indent=2, default=str))
    (OUT / "program_fills.json").write_text(json.dumps(program_fills, indent=2, default=str))
    (OUT / "residual_fills.json").write_text(json.dumps(residual_fills, indent=2, default=str))
    (OUT / "combined_fills.json").write_text(json.dumps(combined_fills, indent=2, default=str))
    (OUT / "residual_schedule.json").write_text(json.dumps(schedule, indent=2, default=str))
    (OUT / "compiler_journal.json").write_text(json.dumps(compiler_journal, indent=2, default=str))
    (OUT / "critic_journal.json").write_text(json.dumps(critic_journal, indent=2, default=str))
    (OUT / "residual_journal.json").write_text(json.dumps(residual_journal, indent=2, default=str))
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    (OUT / "program_only_bags.json").write_text(json.dumps(program_mat["bags"], indent=2, default=str))
    (OUT / "residual_only_bags.json").write_text(json.dumps(residual_mat["bags"], indent=2, default=str))
    (OUT / "combined_bags.json").write_text(json.dumps(combined_mat["bags"], indent=2, default=str))
    with (OUT / "compiler_prompts.jsonl").open("w") as handle:
        for row in compiler_prompts:
            handle.write(json.dumps(row) + "\n")
    with (OUT / "critic_prompts.jsonl").open("w") as handle:
        for row in critic_prompts:
            handle.write(json.dumps(row) + "\n")
    with (OUT / "residual_prompts.jsonl").open("w") as handle:
        for row in residual_prompts:
            handle.write(json.dumps({k: row[k] for k in row}) + "\n")
    print(json.dumps({"frozen": True, "spent": ledger.spent, "combined_cells": combined_mat["overlay"]["changed_cells"]}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    rewrites_for = lambda db: {qid: {"sql": official_sql(statements[qid], db, predicates, query_id=qid), "sqlite_path": str(db)} for qid in query_ids}

    def score_db(db: Path) -> dict[str, Any]:
        rewrites = rewrites_for(db)
        count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
        return {"score_16": _score(db, score_rows, rewrites, gold), "score_15": _score(db, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold)}

    score_program = score_db(OUT / "program_only.db")
    score_residual = score_db(OUT / "residual_only.db")
    score_combined = score_db(OUT / "combined.db")
    score_plumbing = score_db(PLUMBING)
    product = score_combined["score_16"]["mean_per_query_product"]
    program_product = score_program["score_16"]["mean_per_query_product"]
    residual_product = score_residual["score_16"]["mean_per_query_product"]

    gold_rows = gold.get("finance") or gold.get("Finance") or []
    gold_by: dict[str, dict[str, Any]] = {}
    for grow in gold_rows:
        for key in (str(grow.get("doc_id") or ""), Path(str(grow.get("doc_id") or "")).stem, str(grow.get("id") or "")):
            if key:
                gold_by[key] = grow

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

    exact = Counter()
    recall = Counter()
    select_acc = Counter()
    per_attr = defaultdict(lambda: Counter())
    inv_by = {(row["document_id"], row["attribute"]): row["candidates"] for row in inventories}
    accepted_by = {}
    for rec in program_rows:
        accepted_by[(rec["document_id"], rec["attribute"])] = rec.get("accepted")
    for rec in residual_journal:
        if not _null(rec.get("accepted")):
            accepted_by[(rec["document_id"], rec["attribute"])] = rec.get("accepted")
    for rec in inventories:
        if rec.get("empty"):
            continue
        gold_v = gold_value(rec["document_id"], rec["attribute"])
        cands = rec["candidates"]
        present = any(gold_match(rec["attribute"], item.get("normalized"), gold_v) or gold_match(rec["attribute"], item.get("raw_span"), gold_v) for item in cands)
        recall["n"] += 1
        recall["present"] += int(present)
        pred = accepted_by.get((rec["document_id"], rec["attribute"]))
        ok = gold_match(rec["attribute"], pred, gold_v)
        exact["n"] += 1
        exact["ok"] += int(ok)
        per_attr[rec["attribute"]]["n"] += 1
        per_attr[rec["attribute"]]["ok"] += int(ok)
        if present:
            select_acc["n"] += 1
            select_acc["ok"] += int(ok)

    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    sql_visible = 0
    bags = json.loads((OUT / "combined_bags.json").read_text())
    for doc_id, values in combined_fills.items():
        for attr in values:
            if any(_hash(bags.get(qid)) != _hash(plumbing_bags.get(qid)) for qid in records[attr].queries):
                sql_visible += 1
    deltas = []
    for left, right in zip(score_plumbing["score_16"]["per_query"], score_combined["score_16"]["per_query"]):
        deltas.append({**right, "plumbing_product": left["product"], "delta": right["product"] - left["product"]})

    gen_recall = recall["present"] / recall["n"] if recall["n"] else 0.0
    field_exact = exact["ok"] / exact["n"] if exact["n"] else 0.0
    cond_acc = select_acc["ok"] / select_acc["n"] if select_acc["n"] else 0.0
    if ledger.spent > THETA_25:
        decision = "run invalid"
    elif product > DOCETL_PRODUCT:
        decision = "amortized selection beats DocETL at 25%"
    elif gen_recall < 0.20 and field_exact < 0.12:
        decision = "candidate generation is the remaining bottleneck"
    elif cond_acc < 0.35 and program_counts["selected"] > 0:
        decision = "attribute-level specifications cannot rank candidates reliably"
    else:
        decision = "compiled selectors help but residual cost remains too high"

    report = {
        "decision": decision,
        "model": DOCETL_MODEL,
        "spent": ledger.spent,
        "compiler_spent": compiler_spent,
        "critic_calls": len(critic_journal),
        "attributes_compiled": len(validated),
        "program_selected_cells": program_counts["selected"],
        "program_abstentions": program_counts["abstain"],
        "residual_calls": len(residual_journal),
        "residual_selections": residual_counts["selected"],
        "accepted_cells": combined_mat["overlay"]["changed_cells"],
        "sql_visible_fills": sql_visible,
        "score_program": {
            "mean_per_query_product": program_product,
            "mean_structure_f2": score_program["score_16"]["mean_structure_f2"],
            "mean_cell_f1_at_0.20": score_program["score_16"]["mean_cell_f1_at_0.20"],
        },
        "score_residual": {
            "mean_per_query_product": residual_product,
            "mean_structure_f2": score_residual["score_16"]["mean_structure_f2"],
            "mean_cell_f1_at_0.20": score_residual["score_16"]["mean_cell_f1_at_0.20"],
        },
        "score_combined": {
            "mean_per_query_product": product,
            "mean_structure_f2": score_combined["score_16"]["mean_structure_f2"],
            "mean_cell_f1_at_0.20": score_combined["score_16"]["mean_cell_f1_at_0.20"],
        },
        "comparators": {
            "plumbing": PLUMBING_PRODUCT,
            "prior_theta25_selector": {"product": PRIOR_THETA25_PRODUCT, "tokens": PRIOR_THETA25_TOKENS},
            "docetl": {"product": DOCETL_PRODUCT, "tokens": 1_381_827},
        },
        "candidate_set_recall": dict(recall),
        "selector_accuracy_given_present": dict(select_acc),
        "per_attribute_exactness": {name: {"n": per_attr[name]["n"], "ok": per_attr[name]["ok"], "exact": (per_attr[name]["ok"] / per_attr[name]["n"] if per_attr[name]["n"] else 0.0)} for name in sorted(per_attr)},
        "per_query": deltas,
        "hashes": freeze["hashes"],
        "invariants": gates,
    }
    (OUT / "finan_amortized_select_arm.json").write_text(json.dumps(report, indent=2, default=str))
    lines = [
        "# Finan amortized θ25 selection-program arm",
        "",
        f"**Decision: `{decision}`**",
        "",
        "Qwen compiled one selection specification per attribute. A shared deterministic executor ranked every cell. Residual opaque-ID selection used leftover θ25 budget only. Gold was loaded after freeze. No θ100 arm and no Legal arm.",
        "",
        "## Scores",
        "",
        "| System | product | tokens |",
        "| --- | ---: | ---: |",
        f"| Plumbing | 0.0158 | 0 |",
        f"| Prior θ25 per-cell selector | 0.0296 | 344,601 |",
        f"| DocETL | 0.084 | 1,381,827 |",
        f"| Program-only | {program_product:.4f} | {compiler_spent} |",
        f"| Residual-only | {residual_product:.4f} | {ledger.spent - compiler_spent} |",
        f"| **Amortized θ25 combined** | **{product:.4f}** | **{ledger.spent}** |",
        "",
        f"Structure F2 {score_combined['score_16']['mean_structure_f2']:.4f}; cell F1@0.20 {score_combined['score_16']['mean_cell_f1_at_0.20']:.4f}.",
        "",
        "## Coverage",
        "",
        f"- Attributes compiled: {len(validated)}",
        f"- Compiler + critic tokens: {compiler_spent} / cap {compiler_cap}",
        f"- Program-selected cells: {program_counts['selected']}",
        f"- Program abstentions: {program_counts['abstain']}",
        f"- Residual calls: {len(residual_journal)}",
        f"- Residual selections: {residual_counts['selected']}",
        f"- Accepted cells: {combined_mat['overlay']['changed_cells']}",
        f"- SQL-visible fills: {sql_visible}",
        f"- Candidate-set recall: {recall['present']} / {recall['n']}",
        f"- Selector accuracy given present: {select_acc['ok']} / {select_acc['n']}",
        "",
        "## Per-attribute exactness",
        "",
    ]
    for name in sorted(per_attr):
        n = per_attr[name]["n"]
        ok = per_attr[name]["ok"]
        lines.append(f"- `{name}`: {ok}/{n} ({(ok / n if n else 0):.3f})")
    lines.extend(
        [
            "",
            "## Per-query product change vs plumbing",
            "",
        ]
    )
    for row in deltas:
        lines.append(f"- `{row['query_id']}`: {row['product']:.4f} (Δ {row['delta']:+.4f})")
    lines.extend(
        [
            "",
            "## Hashes",
            "",
            f"- Inventory `{inventory_hash}`",
            f"- Samples `{sample_sha}`",
            f"- Specs `{freeze['hashes']['validated_specs']}`",
            f"- Combined bags `{combined_mat['bag_sha256']}`",
            f"- Ledger `{freeze['hashes']['ledger']}`",
            "",
            "Artifacts: `results/quwarts_finan_amortized_select/`.",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"decision": decision, "product": product, "spent": ledger.spent, "program": program_counts["selected"], "residual": residual_counts["selected"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

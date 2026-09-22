"""Validate the frozen program-only sidecar, then run a 3-replica θ25 program-only test."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
DOCETL_SRC = ROOT / "systems" / "docetl-main"
for path in (WDIRS, ROOT, DOCETL_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.amortized_select.config import COMPILER_BUDGET_FRACTION, COMPLETION_RESERVATION, THETA_25
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
from quwarts.core.amortized_select.prompt import COMPILER_SCHEMA, CRITIC_SCHEMA, assemble_tools, compiler_user, critic_user, repair_user
from quwarts.core.amortized_select.sample import samples_hash
from quwarts.core.amortized_select.schedule import query_attr_roles
from quwarts.core.candidate_select.construct import construct_classification, construct_extractive
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
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
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import (
    cand_from_dict,
    construct_program,
    issue_call,
    load_plumbing_rows,
    mapping_from_rows,
    materialize_fills,
    parse_tool,
    reserved_of,
    usage_of,
    _hash,
    _null,
    _score,
)
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

AMORTIZED = ROOT / "results" / "quwarts_finan_amortized_select"
FROZEN_INV = ROOT / "results" / "quwarts_finan_candidate_select"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
SCHEMA_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
OUT = ROOT / "results" / "quwarts_finan_amortized_program_only_repro"
DOCETL_PRODUCT = 0.084
COMPILER_CAP = 69_091
N_REPLICAS = 3
REPLICA_BUDGET = COMPILER_CAP * N_REPLICAS


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def bag_empty(bag: list) -> bool:
    return not bag


def ledger_purpose_sum(records: list[dict[str, Any]], purposes: set[str]) -> int:
    return sum(int(row["tokens"]) for row in records if row.get("purpose") in purposes)


def validate_existing() -> dict[str, Any]:
    frozen = json.loads((AMORTIZED / "frozen.json").read_text())
    report = json.loads((AMORTIZED / "finan_amortized_select_arm.json").read_text())
    ledger = json.loads((AMORTIZED / "theta25_ledger.json").read_text())
    source = (ROOT / "systems" / "WDIRS" / "quwarts" / "eval" / "finan_amortized_select_arm.py").read_text()
    gold_line = source.find("load_ground_truth")
    freeze_line = source.find('(OUT / "frozen.json").write_text')
    mat_line = source.find("program_mat = materialize_fills")
    pre_gold = freeze_line < gold_line and mat_line < gold_line and freeze_line > 0
    compiler = ledger_purpose_sum(ledger["records"], {"compiler", "critic", "repair"})
    residual = ledger_purpose_sum(ledger["records"], {"residual"})
    program_bags = json.loads((AMORTIZED / "program_only_bags.json").read_text())
    residual_bags = json.loads((AMORTIZED / "residual_only_bags.json").read_text())
    combined_bags = json.loads((AMORTIZED / "combined_bags.json").read_text())
    checks = {
        "materialization_fixed_in_code_before_gold": pre_gold,
        "program_bags_hashed_in_frozen_json_before_gold": frozen["hashes"]["program_bags"] == _hash(program_bags),
        "residual_bags_hashed_in_frozen_json_before_gold": frozen["hashes"]["residual_bags"] == _hash(residual_bags),
        "combined_bags_hashed_in_frozen_json_before_gold": frozen["hashes"]["combined_bags"] == _hash(combined_bags),
        "program_db_present": (AMORTIZED / "program_only.db").is_file(),
        "residual_db_present": (AMORTIZED / "residual_only.db").is_file(),
        "compiler_ledger_sum": compiler,
        "residual_ledger_sum": residual,
        "reported_compiler_spent": frozen["compiler_spent"],
        "compiler_matches_reported": compiler == frozen["compiler_spent"],
        "total_spent": ledger["spent"],
    }
    independent = bool(pre_gold and checks["program_bags_hashed_in_frozen_json_before_gold"] and checks["program_db_present"])
    return {
        "program_only": {
            "independently_frozen_before_gold": independent,
            "claimable_as_official_existing_win": independent,
            "materialization_rule_fixed_before_gold": pre_gold,
            "database_and_bags_hashed_before_gold": checks["program_bags_hashed_in_frozen_json_before_gold"],
            "token_cost": compiler,
            "token_cost_includes_all_compiler_and_critic": compiler == frozen["compiler_spent"] == 66700,
            "score_16": report["score_program"],
            "hashes": {
                "bags": frozen["hashes"]["program_bags"],
                "policy": frozen["hashes"]["policy"],
                "specs": frozen["hashes"]["validated_specs"],
                "program_results": frozen["hashes"]["program_results"],
                "inventory": frozen["hashes"]["inventory"],
                "samples": frozen["hashes"]["samples"],
                "ledger": frozen["hashes"]["ledger"],
                "db": file_sha256(AMORTIZED / "program_only.db"),
            },
        },
        "residual_only": {
            "independently_frozen_before_gold": pre_gold and checks["residual_bags_hashed_in_frozen_json_before_gold"],
            "materialization_rule_fixed_before_gold": pre_gold,
            "database_and_bags_hashed_before_gold": checks["residual_bags_hashed_in_frozen_json_before_gold"],
            "sidecar_fill_tokens": residual,
            "requires_compiled_programs": True,
            "causal_token_cost": ledger["spent"],
            "causal_cost_reason": "Residual prompts, filters, and schedule depend on compiled specifications and program executor outputs. Residual-only fills cannot be produced without the 66,700 compiler/critic tokens.",
            "score_16": report["score_residual"],
            "hashes": {
                "bags": frozen["hashes"]["residual_bags"],
                "residual_schedule": frozen["hashes"]["residual_schedule"],
                "ledger": frozen["hashes"]["ledger"],
                "db": file_sha256(AMORTIZED / "residual_only.db"),
            },
        },
        "combined": {
            "token_cost": ledger["spent"],
            "score_16": report["score_combined"],
            "hashes": {"bags": frozen["hashes"]["combined_bags"], "db": file_sha256(AMORTIZED / "combined.db")},
        },
        "checks": checks,
        "existing_0.0872_is_diagnostic_only": not independent,
    }


def interference_audit(statements: dict[str, str], query_ids: list[str]) -> dict[str, Any]:
    program_bags = json.loads((AMORTIZED / "program_only_bags.json").read_text())
    residual_bags = json.loads((AMORTIZED / "residual_only_bags.json").read_text())
    combined_bags = json.loads((AMORTIZED / "combined_bags.json").read_text())
    program_fills = json.loads((AMORTIZED / "program_fills.json").read_text())
    residual_fills = json.loads((AMORTIZED / "residual_fills.json").read_text())
    combined_fills = json.loads((AMORTIZED / "combined_fills.json").read_text())
    roles = query_attr_roles(statements)
    overwrite = []
    for doc, values in residual_fills.items():
        for attr in values:
            if attr in (program_fills.get(doc) or {}):
                overwrite.append({"document_id": doc, "attribute": attr})
    per_query = []
    for qid in query_ids:
        pbag, rbag, cbag = program_bags.get(qid) or [], residual_bags.get(qid) or [], combined_bags.get(qid) or []
        attrs = sorted(roles.get(qid, {}))
        residual_only_cells = []
        program_only_cells = []
        both = []
        for doc, values in combined_fills.items():
            for attr, value in values.items():
                if attr not in attrs:
                    continue
                in_p = attr in (program_fills.get(doc) or {})
                in_r = attr in (residual_fills.get(doc) or {})
                rec = {"document_id": doc, "attribute": attr}
                if in_p and in_r:
                    both.append(rec)
                elif in_p:
                    program_only_cells.append(rec)
                elif in_r:
                    residual_only_cells.append(rec)
        role_set = set()
        for attr in {item["attribute"] for item in residual_only_cells}:
            role_set.update(roles.get(qid, {}).get(attr) or [])
        if _hash(pbag) == _hash(cbag):
            kind = "no_combined_regression"
        elif overwrite:
            kind = "residual_overwrote_or_displaced_program_selection"
        elif role_set & {"WHERE", "JOIN", "HAVING"} and _hash(pbag) != _hash(cbag):
            if len(cbag) > len(pbag):
                kind = "increased_false_positive_support"
            else:
                kind = "two_individually_useful_selections_interacted_through_a_filter"
        elif role_set & {"GROUP BY"}:
            kind = "group_reassignment"
        elif role_set & {"aggregate input"}:
            kind = "aggregate_value_interaction"
        else:
            kind = "other_sql_interaction"
        per_query.append(
            {
                "query_id": qid,
                "program_rows": len(pbag),
                "residual_rows": len(rbag),
                "combined_rows": len(cbag),
                "program_empty": bag_empty(pbag),
                "residual_empty": bag_empty(rbag),
                "combined_empty": bag_empty(cbag),
                "program_equals_combined": _hash(pbag) == _hash(cbag),
                "residual_equals_combined": _hash(rbag) == _hash(cbag),
                "classification": kind,
                "residual_only_cells_in_query_attrs": residual_only_cells,
                "program_only_cells_in_query_attrs": program_only_cells,
                "same_cell_both_selectors": both,
                "residual_roles": sorted(role_set),
            }
        )
    return {
        "combined_fill_rule": "program fills applied first; residual uses setdefault and cannot overwrite a program cell",
        "same_cell_conflicts_in_fills": overwrite,
        "per_query": per_query,
        "counts": dict(Counter(row["classification"] for row in per_query)),
    }


def score_db(dest: Path, statements: dict[str, str], predicates, query_ids: list[str], gold) -> dict[str, Any]:
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    rewrites = {qid: {"sql": official_sql(statements[qid], dest, predicates, query_id=qid), "sqlite_path": str(dest)} for qid in query_ids}
    report = _score(dest, score_rows, rewrites, gold)
    return report


def verify_db(dest: Path, fills: dict[str, dict[str, Any]], mapping: dict[str, str], inventory, statements, plumbing_rows, specs) -> dict[str, bool]:
    conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finance)")]
    rows = [dict(zip(cols, rec)) for rec in conn.execute("SELECT * FROM finance")]
    conn.close()
    identities = [row.get("__entity_id") for row in rows]
    plumbing_ids = [row.get("__entity_id") for row in plumbing_rows]
    inv_ok = True
    by_doc = {(rec["document_id"], rec["attribute"]): rec for rec in inventory}
    for doc, values in fills.items():
        for attr, value in values.items():
            if _null(value):
                continue
            rec = by_doc.get((doc, attr))
            if rec is None:
                inv_ok = False
                continue
            objs = [cand_from_dict(item) for item in rec.get("candidates") or []]
            matched = False
            for item in rec.get("candidates") or []:
                built = construct_program(specs[attr], objs, {"status": "selected", "candidate_ids": [item.get("id")]})
                if built.get("value") == value:
                    matched = True
                    break
            if not matched:
                inv_ok = False
    no_overwrite = True
    current = {row.get("__entity_id"): row for row in rows}
    for prow in plumbing_rows:
        crow = current.get(prow.get("__entity_id")) or {}
        for col in cols:
            if col in {"__entity_id", "__provenance_label", "doc_id"}:
                continue
            if prow.get(col) not in (None, "", -1, "-1") and prow.get(col) != crow.get(col):
                no_overwrite = False
    return {
        "n_rows_100": len(rows) == 100,
        "entity_ids_unchanged": identities == plumbing_ids,
        "incumbent_nonnull_unchanged": no_overwrite,
        "writes_from_inventory_candidates": inv_ok,
    }


def compile_replica(
    replica_id: int,
    specs,
    samples,
    feats_by_key,
    records,
    entity_names,
    ledger: TokenLedger,
    replica_cap: int,
) -> dict[str, Any]:
    compiler_spent = 0
    compiler_journal = []
    critic_journal = []
    repair_journal = []
    validated = {}
    prompts = []

    def charge(purpose: str, reserved: int, response: Any, meta: dict[str, Any]):
        prompt, completion, actual = usage_of(response, reserved)
        if ledger.spent + actual > THETA_25:
            return None
        ledger.spend(actual, purpose, reserved=reserved, replica_id=replica_id, **meta)
        return prompt, completion, actual

    for name in sorted(specs):
        spec = specs[name]
        chosen = samples.get(name) or []
        bank = allowed_term_bank(spec.official_description, name, [feats_by_key[(row["entity_id"], name)] for row in chosen])
        user = compiler_user(spec, chosen, feats_by_key)
        bundled = assemble_tools(COMPILER_SCHEMA, user)
        _pt, reserved = reserved_of(user, bundled["tools"])
        if compiler_spent + reserved > replica_cap or ledger.spent + reserved > THETA_25:
            validated[name] = restore_schema_policy(
                empty_spec(name, spec.task_class),
                description=spec.official_description,
                allows_sum=spec.allows_sum,
                unit_percent=spec.unit_percent,
                domain=spec.schema_domain,
            )
            continue
        prompts.append({"replica_id": replica_id, "stage": "compiler", "attribute": name, "user": user, "reserved": reserved})
        response = issue_call(bundled["request"])
        used = charge("compiler", reserved, response, {"attribute": name})
        if used is None:
            raise SystemExit("replica compiler exceeded global theta25")
        compiler_spent += used[2]
        parsed = parse_tool(response)
        raw_spec = parsed["parsed"]
        if parsed["malformed"]:
            repair = assemble_tools(COMPILER_SCHEMA, repair_user(parsed["raw"][:4000]))
            _rp, r_reserved = reserved_of(repair["user"], repair["tools"])
            if compiler_spent + r_reserved <= replica_cap and ledger.spent + r_reserved <= THETA_25:
                r_resp = issue_call(repair["request"])
                r_used = charge("repair", r_reserved, r_resp, {"attribute": name})
                if r_used is None:
                    raise SystemExit("replica repair exceeded global theta25")
                compiler_spent += r_used[2]
                raw_spec = parse_tool(r_resp)["parsed"]
                repair_journal.append({"replica_id": replica_id, "attribute": name, "actual": r_used[2]})
        compiled = normalize_spec(raw_spec, name, spec.task_class)
        compiler_journal.append({"replica_id": replica_id, "attribute": name, "reserved": reserved, "api_prompt": used[0], "api_completion": used[1], "actual": used[2], "compiled": compiled, "raw": parsed["raw"]})
        c_user = critic_user(spec, compiled, chosen, feats_by_key)
        c_bundled = assemble_tools(CRITIC_SCHEMA, c_user)
        _cp, c_reserved = reserved_of(c_user, c_bundled["tools"])
        critic_blob = {"violations": [], "invalid_terms": []}
        if compiler_spent + c_reserved <= replica_cap and ledger.spent + c_reserved <= THETA_25:
            prompts.append({"replica_id": replica_id, "stage": "critic", "attribute": name, "user": c_user, "reserved": c_reserved})
            c_resp = issue_call(c_bundled["request"])
            c_used = charge("critic", c_reserved, c_resp, {"attribute": name})
            if c_used is None:
                raise SystemExit("replica critic exceeded global theta25")
            compiler_spent += c_used[2]
            c_parsed = parse_tool(c_resp)
            critic_blob = c_parsed["parsed"] if not c_parsed["malformed"] else critic_blob
            critic_journal.append({"replica_id": replica_id, "attribute": name, "reserved": c_reserved, "api_prompt": c_used[0], "api_completion": c_used[1], "actual": c_used[2], "critic": critic_blob})
        fixed = apply_critic_fixes(compiled, critic_blob, bank=bank, description=spec.official_description, allows_sum=spec.allows_sum, unit_percent=spec.unit_percent, domain=spec.schema_domain)
        errors = validate_spec(fixed, name=name, description=spec.official_description, bank=bank, literals=list(records[name].predicate_literals) + list(records[name].categorical_literals), entity_names=entity_names)
        if errors:
            for item in errors:
                if ":" in item:
                    critic_blob.setdefault("invalid_terms", []).append(item.split(":", 1)[1])
            fixed = apply_critic_fixes(fixed, critic_blob, bank=bank, description=spec.official_description, allows_sum=spec.allows_sum, unit_percent=spec.unit_percent, domain=spec.schema_domain)
            errors = validate_spec(fixed, name=name, description=spec.official_description, bank=bank, literals=list(records[name].predicate_literals) + list(records[name].categorical_literals), entity_names=entity_names)
        if errors:
            fixed = restore_schema_policy(empty_spec(name, spec.task_class), description=spec.official_description, allows_sum=spec.allows_sum, unit_percent=spec.unit_percent, domain=spec.schema_domain)
            fixed["abstain_on_conflict"] = True
        validated[name] = fixed
        print(json.dumps({"replica": replica_id, "compiled": name, "errors": errors, "replica_spent": compiler_spent, "global_spent": ledger.spent}, indent=2), flush=True)
    return {
        "replica_id": replica_id,
        "spent": compiler_spent,
        "validated": validated,
        "compiler_journal": compiler_journal,
        "critic_journal": critic_journal,
        "repair_journal": repair_journal,
        "prompts": prompts,
    }


def execute_program(validated, inventories, feats_by_key, specs) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = []
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for rec in inventories:
        if rec.get("empty"):
            continue
        spec = specs[rec["attribute"]]
        feats = feats_by_key[(rec["entity_id"], rec["attribute"])]
        result = execute_cell(validated[rec["attribute"]], feats)
        objs = [cand_from_dict(item) for item in rec["candidates"]]
        built = construct_program(spec, objs, result)
        if not _null(built.get("value")):
            fills[rec["document_id"]][rec["attribute"]] = built["value"]
        rows.append(
            {
                "entity_id": rec["entity_id"],
                "document_id": rec["document_id"],
                "attribute": rec["attribute"],
                "candidate_ids": result.get("candidate_ids") or [],
                "status": result.get("status"),
                "reason": result.get("reason"),
                "accepted": built.get("value"),
                "used_ids": built.get("used_ids") or result.get("candidate_ids") or [],
            }
        )
    return rows, dict(fills)


def consensus_select(replica_rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rows in replica_rows:
        for row in rows:
            by_key[(row["entity_id"], row["attribute"])].append(row)
    out = []
    for key, votes in sorted(by_key.items()):
        chosen = []
        for row in votes:
            ids = [item for item in (row.get("used_ids") or row.get("candidate_ids") or []) if item]
            if row.get("status") == "selected" and ids and not _null(row.get("accepted")):
                chosen.append(ids[0])
            else:
                chosen.append(None)
        counts = Counter(item for item in chosen if item)
        winner = None
        status = "abstain"
        reason = "no_majority"
        if not counts:
            reason = "all_abstain" if all(item is None for item in chosen) else "no_majority"
        else:
            top, n = counts.most_common(1)[0]
            if n >= 2:
                winner = top
                status = "selected"
                reason = "majority_2" if n == 2 else "unanimous_3"
            elif n == 1 and sum(item is not None for item in chosen) == 1:
                reason = "single_selection_abstain"
            else:
                reason = "conflict_no_majority"
        out.append(
            {
                "entity_id": key[0],
                "attribute": key[1],
                "votes": chosen,
                "winner_id": winner,
                "status": status,
                "reason": reason,
                "document_id": votes[0]["document_id"],
            }
        )
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "cache"
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    existing = validate_existing()
    interference = interference_audit(statements, query_ids)
    (OUT / "existing_subarm_validation.json").write_text(json.dumps(existing, indent=2))
    (OUT / "interference_audit.json").write_text(json.dumps(interference, indent=2, default=str))
    print(json.dumps({"existing_independent": existing["program_only"]["independently_frozen_before_gold"], "interference": interference["counts"]}, indent=2), flush=True)

    inventory = json.loads((FROZEN_INV / "candidate_inventory.json").read_text())
    if _hash(inventory) != json.loads((AMORTIZED / "frozen.json").read_text())["hashes"]["inventory"]:
        raise SystemExit("frozen inventory hash mismatch")
    sample_meta = json.loads((AMORTIZED / "representative_samples.json").read_text())
    inv_index = {(row["entity_id"], row["attribute"]): row for row in inventory}
    samples = {}
    for name, rows in sample_meta.items():
        samples[name] = [inv_index[(row["entity_id"], name)] for row in rows]
    if samples_hash(samples) != json.loads((AMORTIZED / "frozen.json").read_text())["hashes"]["samples"]:
        raise SystemExit("frozen sample hash mismatch")

    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}
    feats_by_key = {}
    for rec in inventory:
        feats_by_key[(rec["entity_id"], rec["attribute"])] = annotate_set(
            rec,
            spec_tokens(rec["attribute"], specs[rec["attribute"]].official_description),
            len(texts.get(rec["document_id"], "")),
        )

    consensus_policy = {
        "rule": "majority_candidate_id",
        "majority_threshold": 2,
        "single_vote_abstains": True,
        "conflict_abstains": True,
        "no_union": True,
        "no_confidence_tiebreak": True,
        "no_residual_fallback": True,
        "no_query_effect_inspection": True,
        "replicas": N_REPLICAS,
        "per_replica_compiler_cap": COMPILER_CAP,
        "global_theta": THETA_25,
        "replica_budget_total": REPLICA_BUDGET,
    }
    (OUT / "consensus_policy.json").write_text(json.dumps(consensus_policy, indent=2))
    print(json.dumps({"frozen_consensus_policy": _hash(consensus_policy)}, indent=2), flush=True)

    if REPLICA_BUDGET > THETA_25:
        raise SystemExit("three replica caps exceed theta25")
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    execute_ok = execute_all(PLUMBING, statements)
    if not empty_ok or not execute_ok:
        raise SystemExit("pre-replica overlay/query gate failed")

    ledger = TokenLedger(theta=THETA_25, seed=42)
    replicas = []
    replica_execs = []
    for replica_id in range(1, N_REPLICAS + 1):
        remaining = THETA_25 - ledger.spent
        if remaining < 1000:
            raise SystemExit(f"cannot complete replica {replica_id} within theta25")
        compiled = compile_replica(replica_id, specs, samples, feats_by_key, records, [str(row.get("__entity_id") or "") for row in plumbing_rows], ledger, COMPILER_CAP)
        rows, fills = execute_program(compiled["validated"], inventory, feats_by_key, specs)
        dest = OUT / f"replica_{replica_id}.db"
        mat = materialize_fills(dest, fills, mapping, statements, predicates, query_ids)
        replicas.append(compiled)
        replica_execs.append({"rows": rows, "fills": fills, "mat": mat})
        (OUT / f"replica_{replica_id}_specs.json").write_text(json.dumps(compiled["validated"], indent=2))
        (OUT / f"replica_{replica_id}_journal.json").write_text(json.dumps({"compiler": compiled["compiler_journal"], "critic": compiled["critic_journal"], "repair": compiled["repair_journal"]}, indent=2, default=str))
        (OUT / f"replica_{replica_id}_results.json").write_text(json.dumps(rows, indent=2, default=str))
        (OUT / f"replica_{replica_id}_fills.json").write_text(json.dumps(fills, indent=2, default=str))
        (OUT / f"replica_{replica_id}_bags.json").write_text(json.dumps(mat["bags"], indent=2, default=str))
        with (OUT / f"replica_{replica_id}_prompts.jsonl").open("w") as handle:
            for row in compiled["prompts"]:
                handle.write(json.dumps(row) + "\n")
        print(json.dumps({"replica_done": replica_id, "spent": compiled["spent"], "global": ledger.spent, "fills": mat["overlay"]["changed_cells"]}, indent=2), flush=True)

    if len(replicas) != N_REPLICAS:
        raise SystemExit("run invalid: not all replicas completed")
    if ledger.spent > THETA_25:
        raise SystemExit("run invalid: ledger exceeded theta25")

    consensus_rows = consensus_select([item["rows"] for item in replica_execs])
    inv_cands = {(rec["entity_id"], rec["attribute"]): rec for rec in inventory}
    consensus_fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in consensus_rows:
        if row["status"] != "selected" or not row.get("winner_id"):
            continue
        rec = inv_cands[(row["entity_id"], row["attribute"])]
        spec = specs[row["attribute"]]
        objs = [cand_from_dict(item) for item in rec["candidates"]]
        built = construct_program(spec, objs, {"status": "selected", "candidate_ids": [row["winner_id"]]})
        if not _null(built.get("value")):
            consensus_fills[row["document_id"]][row["attribute"]] = built["value"]
            row["accepted"] = built.get("value")
        else:
            row["status"] = "abstain"
            row["reason"] = built.get("reason") or "construct_failed"
    consensus_mat = materialize_fills(OUT / "consensus.db", dict(consensus_fills), mapping, statements, predicates, query_ids)
    (OUT / "consensus_log.json").write_text(json.dumps(consensus_rows, indent=2, default=str))
    (OUT / "consensus_fills.json").write_text(json.dumps(consensus_fills, indent=2, default=str))
    (OUT / "consensus_bags.json").write_text(json.dumps(consensus_mat["bags"], indent=2, default=str))

    agree = Counter(row["reason"] for row in consensus_rows)
    pairwise_spec = {}
    pairwise_cell = {}
    for i in range(N_REPLICAS):
        for j in range(i + 1, N_REPLICAS):
            sa = replicas[i]["validated"]
            sb = replicas[j]["validated"]
            spec_same = sum(1 for name in sa if _hash(sa[name]) == _hash(sb[name]))
            cells_a = {(r["entity_id"], r["attribute"]): (r.get("used_ids") or [None])[:1] for r in replica_execs[i]["rows"]}
            cells_b = {(r["entity_id"], r["attribute"]): (r.get("used_ids") or [None])[:1] for r in replica_execs[j]["rows"]}
            keys = set(cells_a) | set(cells_b)
            same = 0
            for key in keys:
                left = (cells_a.get(key) or [None])[0]
                right = (cells_b.get(key) or [None])[0]
                sel_l = left if replica_execs[i]["rows"] and True else left
                same += int(left == right)
            pairwise_spec[f"{i+1}-{j+1}"] = {"attributes_equal": spec_same, "n": len(sa)}
            pairwise_cell[f"{i+1}-{j+1}"] = {"cells_equal": same, "n": len(keys)}

    agreement = {
        "all_three_same_candidate": agree.get("unanimous_3", 0),
        "exactly_two_same_candidate": agree.get("majority_2", 0),
        "conflicting_selections": agree.get("conflict_no_majority", 0),
        "one_selection_plus_abstentions": agree.get("single_selection_abstain", 0),
        "all_abstain": agree.get("all_abstain", 0),
        "pairwise_specification_agreement": pairwise_spec,
        "pairwise_cell_selection_agreement": pairwise_cell,
        "reason_counts": dict(agree),
    }
    (OUT / "agreement_before_gold.json").write_text(json.dumps(agreement, indent=2))

    arms = {
        "replica_1": replica_execs[0],
        "replica_2": replica_execs[1],
        "replica_3": replica_execs[2],
        "consensus": {"fills": dict(consensus_fills), "mat": consensus_mat, "db": OUT / "consensus.db"},
    }
    for idx in range(3):
        arms[f"replica_{idx+1}"]["db"] = OUT / f"replica_{idx+1}.db"
    pre_score_gates = {}
    for name, arm in arms.items():
        fills = arm["fills"] if name != "consensus" else dict(consensus_fills)
        dest = arm["db"]
        pre_score_gates[name] = verify_db(dest, fills, mapping, inventory, statements, plumbing_rows, specs)
        pre_score_gates[name]["queries_execute"] = execute_all(dest, statements)
        pre_score_gates[name]["empty_sidecar_reproduces_plumbing"] = empty_ok
    pre_score_gates["total_spend_le_theta25"] = ledger.spent <= THETA_25
    pre_score_gates["n_replicas"] = len(replicas) == 3
    if not all(all(v.values()) if isinstance(v, dict) else v for k, v in pre_score_gates.items() if k not in {"total_spend_le_theta25", "n_replicas"}):
        print(json.dumps({"pre_score_gates": pre_score_gates}, indent=2), flush=True)
        raise SystemExit("pre-score gate failure")
    if ledger.spent > THETA_25:
        raise SystemExit("pre-score spend gate failure")

    freeze = {
        "consensus_policy": consensus_policy,
        "agreement": agreement,
        "spent": ledger.spent,
        "replica_spends": [row["spent"] for row in replicas],
        "hashes": {
            "inventory": _hash(inventory),
            "samples": samples_hash(samples),
            "consensus_policy": _hash(consensus_policy),
            "ledger": ledger.fingerprint(),
            "replica_specs": [_hash(row["validated"]) for row in replicas],
            "replica_bags": [item["mat"]["bag_sha256"] for item in replica_execs],
            "consensus_bags": consensus_mat["bag_sha256"],
            "agreement": _hash(agreement),
        },
        "gates": pre_score_gates,
    }
    (OUT / "frozen.json").write_text(json.dumps(freeze, indent=2, default=str))
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "agreement": {k: agreement[k] for k in agreement if k != "pairwise_specification_agreement" and k != "pairwise_cell_selection_agreement"}}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    plumbing_score = score_db(PLUMBING, statements, predicates, query_ids, gold)
    scores = {"plumbing": plumbing_score}
    for name, arm in arms.items():
        scores[name] = score_db(arm["db"], statements, predicates, query_ids, gold)

    docetl_eval = json.loads((DOCETL_DIR / "evaluation.json").read_text())
    docetl_score = {
        "mean_structure_f2": float(docetl_eval.get("mean_structure_fbeta_score") or 0.0),
        "mean_cell_f1_at_0.20": float((docetl_eval.get("mean_cell_f1") or {}).get("0.2") or 0.0),
        "mean_per_query_product": float((docetl_eval.get("mean_query_score") or {}).get("0.2") or DOCETL_PRODUCT),
        "tokens": 1_381_827,
        "source": "frozen_docetl_finan_case80_evaluation.json",
    }

    gold_rows = gold.get("finance") or gold.get("Finance") or []
    gold_by = {}
    for grow in gold_rows:
        for key in (str(grow.get("doc_id") or ""), Path(str(grow.get("doc_id") or "")).stem, str(grow.get("id") or "")):
            if key:
                gold_by[key] = grow

    def gold_value(doc_id: str, name: str):
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

    def diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
        recall = Counter()
        acc = Counter()
        accepted = {(row["document_id"], row["attribute"]): row.get("accepted") for row in rows if not _null(row.get("accepted"))}
        for rec in inventory:
            if rec.get("empty"):
                continue
            gold_v = gold_value(rec["document_id"], rec["attribute"])
            present = any(gold_match(rec["attribute"], item.get("normalized"), gold_v) or gold_match(rec["attribute"], item.get("raw_span"), gold_v) for item in rec.get("candidates") or [])
            recall["n"] += 1
            recall["present"] += int(present)
            if present:
                acc["n"] += 1
                acc["ok"] += int(gold_match(rec["attribute"], accepted.get((rec["document_id"], rec["attribute"])), gold_v))
        return {"candidate_set_recall": dict(recall), "selector_accuracy_given_present": dict(acc)}

    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}

    def arm_report(name: str, tokens: int, score: dict[str, Any], fills: dict[str, dict[str, Any]], bags: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        sql_visible = 0
        for doc, values in fills.items():
            for attr in values:
                if any(_hash(bags.get(qid)) != _hash(plumbing_bags.get(qid)) for qid in records[attr].queries):
                    sql_visible += 1
        per_query = []
        for left, right in zip(plumbing_score["per_query"], score["per_query"]):
            per_query.append({**right, "plumbing_product": left["product"], "delta": right["product"] - left["product"]})
        return {
            "tokens": tokens,
            "mean_structure_f2": score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": score["mean_per_query_product"],
            "accepted_cells": overlay.get("changed_cells"),
            "sql_visible_fills": sql_visible,
            "empty_bags": [qid for qid, bag in bags.items() if bag_empty(bag)],
            "n_empty_bags": sum(1 for bag in bags.values() if bag_empty(bag)),
            "per_query": per_query,
        }

    consensus_score_rows = []
    for row in consensus_rows:
        consensus_score_rows.append({**row, "accepted": row.get("accepted") if row.get("status") == "selected" else None})

    payload = {
        "existing_validation": existing,
        "interference": {"counts": interference["counts"], "overwrite_cells": interference["same_cell_conflicts_in_fills"]},
        "agreement_before_gold": agreement,
        "spent": ledger.spent,
        "replica_spends": [row["spent"] for row in replicas],
        "arms": {
            "plumbing": arm_report("plumbing", 0, plumbing_score, {}, plumbing_bags, {"changed_cells": 0}),
            "replica_1": arm_report("replica_1", replicas[0]["spent"], scores["replica_1"], replica_execs[0]["fills"], replica_execs[0]["mat"]["bags"], replica_execs[0]["mat"]["overlay"]),
            "replica_2": arm_report("replica_2", replicas[1]["spent"], scores["replica_2"], replica_execs[1]["fills"], replica_execs[1]["mat"]["bags"], replica_execs[1]["mat"]["overlay"]),
            "replica_3": arm_report("replica_3", replicas[2]["spent"], scores["replica_3"], replica_execs[2]["fills"], replica_execs[2]["mat"]["bags"], replica_execs[2]["mat"]["overlay"]),
            "consensus": arm_report("consensus", ledger.spent, scores["consensus"], dict(consensus_fills), consensus_mat["bags"], consensus_mat["overlay"]),
            "docetl": {**docetl_score, "accepted_cells": None, "sql_visible_fills": None, "empty_bags": None},
        },
        "diagnostics_after_gold": {
            "replica_1": diagnostics(replica_execs[0]["rows"]),
            "replica_2": diagnostics(replica_execs[1]["rows"]),
            "replica_3": diagnostics(replica_execs[2]["rows"]),
            "consensus": diagnostics(consensus_score_rows),
        },
        "hashes": freeze["hashes"],
    }
    consensus_product = scores["consensus"]["mean_per_query_product"]
    replica_products = [scores[f"replica_{i}"]["mean_per_query_product"] for i in (1, 2, 3)]
    if ledger.spent > THETA_25 or len(replicas) != 3:
        decision = "run invalid"
    elif consensus_product > DOCETL_PRODUCT and ledger.spent <= THETA_25:
        decision = "program-only reproducibly beats DocETL below θ25"
    elif any(p > DOCETL_PRODUCT for p in replica_products) and consensus_product <= DOCETL_PRODUCT:
        decision = "program-only win is replica-dependent; consensus does not beat DocETL"
    else:
        decision = "original program-only win does not reproduce"
    payload["decision"] = decision
    (OUT / "finan_amortized_program_only_repro.json").write_text(json.dumps(payload, indent=2, default=str))

    def fmt(arm: dict[str, Any]) -> str:
        return f"{arm['mean_structure_f2']:.4f} | {arm['mean_cell_f1_at_0.20']:.4f} | {arm['mean_per_query_product']:.4f} | {arm.get('tokens')}"

    lines = [
        "# Finan program-only three-replica reproducibility test",
        "",
        f"**Decision: `{decision}`**",
        "",
        "## Part 1. Existing sub-arm validation",
        "",
        f"- Program-only independently frozen before gold: **{existing['program_only']['independently_frozen_before_gold']}**",
        f"- Program-only tokens: {existing['program_only']['token_cost']} (compiler+critic+repair {existing['program_only']['token_cost_includes_all_compiler_and_critic']})",
        f"- Program-only F2/F1/product: {existing['program_only']['score_16']['mean_structure_f2']:.4f} / {existing['program_only']['score_16']['mean_cell_f1_at_0.20']:.4f} / {existing['program_only']['score_16']['mean_per_query_product']:.4f}",
        f"- Residual-only sidecar fill tokens: {existing['residual_only']['sidecar_fill_tokens']}; causal cost **{existing['residual_only']['causal_token_cost']}** because residual calls require compiled programs.",
        f"- Residual-only F2/F1/product: {existing['residual_only']['score_16']['mean_structure_f2']:.4f} / {existing['residual_only']['score_16']['mean_cell_f1_at_0.20']:.4f} / {existing['residual_only']['score_16']['mean_per_query_product']:.4f}",
        f"- Combined tokens: {existing['combined']['token_cost']}; product {existing['combined']['score_16']['mean_per_query_product']:.4f}",
        f"- Existing 0.0872 is diagnostic only: {existing['existing_0.0872_is_diagnostic_only']}",
        "",
        "## Combined-arm interference",
        "",
        f"- Residual overwrite of a program cell in combined fills: {len(interference['same_cell_conflicts_in_fills'])} (combined used setdefault).",
        f"- Query classifications: {interference['counts']}",
        "",
    ]
    for row in interference["per_query"]:
        if row["classification"] != "no_combined_regression":
            lines.append(f"- `{row['query_id']}`: {row['classification']} (program {row['program_rows']} rows, residual {row['residual_rows']}, combined {row['combined_rows']})")
    lines.extend(
        [
            "",
            "## Part 2. Fresh three-replica program-only scores",
            "",
            f"Global spend {ledger.spent} / {THETA_25}. Replica spends { [row['spent'] for row in replicas] }.",
            "",
            "| Arm | structure F2 | cell F1@0.20 | product | tokens | accepted | SQL-visible | empty bags |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name in ("plumbing", "replica_1", "replica_2", "replica_3", "consensus"):
        arm = payload["arms"][name]
        lines.append(
            f"| {name} | {arm['mean_structure_f2']:.4f} | {arm['mean_cell_f1_at_0.20']:.4f} | {arm['mean_per_query_product']:.4f} | {arm['tokens']} | {arm.get('accepted_cells')} | {arm.get('sql_visible_fills')} | {arm.get('n_empty_bags')} |"
        )
    d = payload["arms"]["docetl"]
    lines.append(f"| frozen DocETL | {d['mean_structure_f2']:.4f} | {d['mean_cell_f1_at_0.20']:.4f} | {d['mean_per_query_product']:.4f} | {d['tokens']} | — | — | — |")
    lines.extend(["", "## Agreement before gold", "", json.dumps(agreement, indent=2), "", "## Diagnostics after gold", "", json.dumps(payload["diagnostics_after_gold"], indent=2), "", f"**Primary decision:** `{decision}`", ""])
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"decision": decision, "consensus": consensus_product, "replicas": replica_products, "spent": ledger.spent}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

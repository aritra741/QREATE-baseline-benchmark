"""Fresh Finan uncertainty-triggered program-selection arm. Locked compiler stack."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.amortized_select.adjudicate import (
    annotate_schedule,
    assemble_adjudicate,
    build_card,
    card_has_query_literals,
    classify_votes,
    parse_choice,
    primary_user,
    repair_user,
    sort_disputes,
    verify_user,
)
from quwarts.core.amortized_select.config import COMPLETION_RESERVATION, THETA_25
from quwarts.core.amortized_select.features import annotate_set, spec_tokens
from quwarts.core.amortized_select.sample import samples_hash
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import empty_overlay_matches, execute_all, official_bag
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_program_only_repro import (
    bag_empty,
    compile_replica,
    execute_program,
    score_db,
    verify_db,
)
from quwarts.eval.finan_amortized_select_arm import (
    cand_from_dict,
    construct_program,
    inspect_executor,
    issue_call,
    load_plumbing_rows,
    mapping_from_rows,
    materialize_fills,
    parse_tool,
    reserved_of,
    usage_of,
    _hash,
    _null,
)
from quwarts.experiments.synthesize_case80 import gold_name, queries_for

load_env_file(ROOT / ".env")

AMORTIZED = ROOT / "results" / "quwarts_finan_amortized_select"
FROZEN_INV = ROOT / "results" / "quwarts_finan_candidate_select"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
SCHEMA_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
OUT = ROOT / "results" / "quwarts_finan_amortized_uncertainty_adjudicate"
DOCETL_PRODUCT = 0.084
COMPILER_CAP = 69_091
N_REPLICAS = 3


def fills_from_ids(rows: list[dict[str, Any]], inventory, specs) -> dict[str, dict[str, Any]]:
    inv = {(rec["entity_id"], rec["attribute"]): rec for rec in inventory}
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in rows:
        cid = row.get("winner_id")
        if row.get("status") != "selected" or not cid:
            continue
        rec = inv[(row["entity_id"], row["attribute"])]
        spec = specs[row["attribute"]]
        objs = [cand_from_dict(item) for item in rec["candidates"]]
        built = construct_program(spec, objs, {"status": "selected", "candidate_ids": [cid]})
        if not _null(built.get("value")):
            fills[row["document_id"]][row["attribute"]] = built["value"]
            row["accepted"] = built.get("value")
            row["used_ids"] = built.get("used_ids") or [cid]
        else:
            row["status"] = "abstain"
            row["reason"] = built.get("reason") or "construct_failed"
            row["winner_id"] = None
    return dict(fills)


def merge_official(majority: dict[str, dict[str, Any]], adjudicated: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = defaultdict(dict)
    for doc, values in majority.items():
        out[doc].update(values)
    for doc, values in adjudicated.items():
        for attr, value in values.items():
            if attr not in out[doc]:
                out[doc][attr] = value
    return dict(out)


def charge(ledger: TokenLedger, purpose: str, reserved: int, response: Any, meta: dict[str, Any]):
    prompt, completion, actual = usage_of(response, reserved)
    if ledger.spent + actual > THETA_25:
        return None
    ledger.spend(actual, purpose, reserved=reserved, **meta)
    return prompt, completion, actual


def run_adjudication(card: dict[str, Any], inventory_row, feats, source_text, ledger: TokenLedger) -> dict[str, Any]:
    allowed = card["allowed"]
    primary = assemble_adjudicate(primary_user(card))
    _pt, reserved = reserved_of(primary["user"], primary["tools"])
    verify_reserved = 0
    verify_bundle = None
    if card["cohort"] == "conflict":
        verify_bundle = assemble_adjudicate(verify_user(card, inventory_row, feats, source_text))
        _vt, verify_reserved = reserved_of(verify_bundle["user"], verify_bundle["tools"])
        if ledger.spent + reserved + verify_reserved > THETA_25:
            return {"status": "abstain", "winner_id": None, "reason": "budget_unattempted", "attempted": False}
    elif ledger.spent + reserved > THETA_25:
        return {"status": "abstain", "winner_id": None, "reason": "budget_unattempted", "attempted": False}

    response = issue_call(primary["request"])
    used = charge(ledger, "adjudicate", reserved, response, {"attribute": card["attribute"], "cohort": card["cohort"], "stage": "primary"})
    if used is None:
        return {"status": "abstain", "winner_id": None, "reason": "budget_exhausted", "attempted": True}
    parsed = parse_tool(response)
    choice = "NONE"
    repair_spent = 0
    if parsed["malformed"]:
        repair = assemble_adjudicate(repair_user(parsed["raw"], allowed))
        _rp, r_reserved = reserved_of(repair["user"], repair["tools"])
        if ledger.spent + r_reserved <= THETA_25:
            r_resp = issue_call(repair["request"])
            r_used = charge(ledger, "adjudicate_repair", r_reserved, r_resp, {"attribute": card["attribute"], "stage": "repair"})
            if r_used is None:
                return {"status": "abstain", "winner_id": None, "reason": "repair_exhausted", "attempted": True, "spent": used[2]}
            repair_spent = r_used[2]
            parsed = parse_tool(r_resp)
            choice = parse_choice(parsed["parsed"], allowed) if not parsed["malformed"] else "NONE"
        else:
            choice = "NONE"
    else:
        choice = parse_choice(parsed["parsed"], allowed)

    journal = {
        "entity_id": card["entity_id"],
        "attribute": card["attribute"],
        "document_id": card["document_id"],
        "cohort": card["cohort"],
        "listed_ids": card["listed_ids"],
        "primary_choice": choice,
        "primary_spent": used[2],
        "repair_spent": repair_spent,
        "verify_choice": None,
        "attempted": True,
    }
    if choice == "NONE" or card["cohort"] != "conflict":
        journal["winner_id"] = None if choice == "NONE" else choice
        journal["status"] = "abstain" if choice == "NONE" else "selected"
        journal["reason"] = "primary_none" if choice == "NONE" else "primary_accept"
        return journal

    if verify_bundle is None:
        journal["winner_id"] = None
        journal["status"] = "abstain"
        journal["reason"] = "missing_verify"
        return journal
    v_resp = issue_call(verify_bundle["request"])
    v_used = charge(ledger, "adjudicate_verify", verify_reserved, v_resp, {"attribute": card["attribute"], "stage": "verify"})
    if v_used is None:
        journal["winner_id"] = None
        journal["status"] = "abstain"
        journal["reason"] = "verify_exhausted"
        return journal
    v_parsed = parse_tool(v_resp)
    v_choice = parse_choice(v_parsed["parsed"], allowed) if not v_parsed["malformed"] else "NONE"
    journal["verify_choice"] = v_choice
    journal["verify_spent"] = v_used[2]
    if v_choice == choice and choice != "NONE":
        journal["winner_id"] = choice
        journal["status"] = "selected"
        journal["reason"] = "conflict_agree"
    else:
        journal["winner_id"] = None
        journal["status"] = "abstain"
        journal["reason"] = "conflict_disagree"
    return journal


def arm_report(tokens: int, score: dict[str, Any], fills: dict[str, dict[str, Any]], bags: dict[str, Any], overlay: dict[str, Any], plumbing_score, plumbing_bags, records) -> dict[str, Any]:
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
        "accepted_cells": overlay.get("changed_cells"),
        "sql_visible_fills": sql_visible,
        "mean_structure_f2": score["mean_structure_f2"],
        "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
        "mean_per_query_product": score["mean_per_query_product"],
        "empty_bags": [qid for qid, bag in bags.items() if bag_empty(bag)],
        "n_empty_bags": sum(1 for bag in bags.values() if bag_empty(bag)),
        "per_query": per_query,
    }


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

    frozen_prev = json.loads((AMORTIZED / "frozen.json").read_text())
    inventory = json.loads((FROZEN_INV / "candidate_inventory.json").read_text())
    if _hash(inventory) != frozen_prev["hashes"]["inventory"]:
        raise SystemExit("frozen inventory hash mismatch")
    sample_meta = json.loads((AMORTIZED / "representative_samples.json").read_text())
    inv_index = {(row["entity_id"], row["attribute"]): row for row in inventory}
    samples = {name: [inv_index[(row["entity_id"], name)] for row in rows] for name, rows in sample_meta.items()}
    if samples_hash(samples) != frozen_prev["hashes"]["samples"]:
        raise SystemExit("frozen sample hash mismatch")

    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}
    feats_by_key = {}
    for rec in inventory:
        feats_by_key[(rec["entity_id"], rec["attribute"])] = annotate_set(
            rec,
            spec_tokens(rec["attribute"], specs[rec["attribute"]].official_description),
            len(texts.get(rec["document_id"], "")),
        )

    policy = {
        "rule": "majority_plus_uncertainty_adjudication",
        "majority_threshold": 2,
        "singleton_to_adjudication": True,
        "conflict_to_adjudication": True,
        "conflict_requires_verify": True,
        "no_residual_selector": True,
        "no_vote_leak": True,
        "per_replica_compiler_cap": COMPILER_CAP,
        "global_theta": THETA_25,
        "completion_reservation": COMPLETION_RESERVATION,
        "replicas": N_REPLICAS,
    }
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))

    if not inspect_executor(sorted(specs)):
        raise SystemExit("executor grew attribute branches")
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    if not empty_ok or not execute_all(PLUMBING, statements):
        raise SystemExit("pre-replica overlay/query gate failed")

    ledger = TokenLedger(theta=THETA_25, seed=42)
    replicas = []
    replica_execs = []
    for replica_id in range(1, N_REPLICAS + 1):
        compiled = compile_replica(
            replica_id,
            specs,
            samples,
            feats_by_key,
            records,
            [str(row.get("__entity_id") or "") for row in plumbing_rows],
            ledger,
            COMPILER_CAP,
        )
        rows, fills = execute_program(compiled["validated"], inventory, feats_by_key, specs)
        dest = OUT / f"replica_{replica_id}.db"
        mat = materialize_fills(dest, fills, mapping, statements, predicates, query_ids)
        replicas.append(compiled)
        replica_execs.append({"rows": rows, "fills": fills, "mat": mat, "db": dest})
        (OUT / f"replica_{replica_id}_specs.json").write_text(json.dumps(compiled["validated"], indent=2))
        (OUT / f"replica_{replica_id}_journal.json").write_text(
            json.dumps({"compiler": compiled["compiler_journal"], "critic": compiled["critic_journal"], "repair": compiled["repair_journal"]}, indent=2, default=str)
        )
        (OUT / f"replica_{replica_id}_results.json").write_text(json.dumps(rows, indent=2, default=str))
        (OUT / f"replica_{replica_id}_fills.json").write_text(json.dumps(fills, indent=2, default=str))
        (OUT / f"replica_{replica_id}_bags.json").write_text(json.dumps(mat["bags"], indent=2, default=str))
        with (OUT / f"replica_{replica_id}_prompts.jsonl").open("w") as handle:
            for row in compiled["prompts"]:
                handle.write(json.dumps(row) + "\n")
        print(json.dumps({"replica_done": replica_id, "spent": compiled["spent"], "global": ledger.spent, "fills": mat["overlay"]["changed_cells"]}, indent=2), flush=True)

    if len(replicas) != 3:
        raise SystemExit("run invalid: not all replicas completed")

    classified = classify_votes([item["rows"] for item in replica_execs])
    majority_rows = [dict(row) for row in classified if row["cohort"] in {"unanimous_3", "majority_2"}]
    dispute_rows = [dict(row) for row in classified if row["cohort"] in {"singleton", "conflict"}]
    (OUT / "disagreement_inventory.json").write_text(json.dumps({"classified": classified, "disputes": dispute_rows}, indent=2, default=str))

    cards = []
    for row in dispute_rows:
        rec = inv_index[(row["entity_id"], row["attribute"])]
        card = build_card(row, specs[row["attribute"]], rec, feats_by_key[(row["entity_id"], row["attribute"])], texts.get(row["document_id"], ""))
        if card_has_query_literals(card, records):
            raise SystemExit(f"query literal leaked into card {row['entity_id']} {row['attribute']}")
        primary = assemble_adjudicate(primary_user(card))
        _pt, p_res = reserved_of(primary["user"], primary["tools"])
        v_res = 0
        if card["cohort"] == "conflict":
            verify = assemble_adjudicate(verify_user(card, rec, feats_by_key[(row["entity_id"], row["attribute"])], texts.get(row["document_id"], "")))
            _vt, v_res = reserved_of(verify["user"], verify["tools"])
        cards.append(annotate_schedule(card, records[row["attribute"]], p_res, v_res))
    cards = sort_disputes(cards)
    (OUT / "adjudication_cards.json").write_text(json.dumps(cards, indent=2, default=str))
    (OUT / "adjudication_schedule.json").write_text(
        json.dumps([{"entity_id": c["entity_id"], "attribute": c["attribute"], "cohort": c["cohort"], "priority": c["priority"], "estimated_cost": c["estimated_cost"]} for c in cards], indent=2)
    )
    with (OUT / "adjudication_prompts.jsonl").open("w") as handle:
        for card in cards:
            handle.write(json.dumps({"stage": "primary", "attribute": card["attribute"], "entity_id": card["entity_id"], "user": primary_user(card)}) + "\n")

    adj_journal = []
    for card in cards:
        rec = inv_index[(card["entity_id"], card["attribute"])]
        result = run_adjudication(card, rec, feats_by_key[(card["entity_id"], card["attribute"])], texts.get(card["document_id"], ""), ledger)
        result["priority"] = card["priority"]
        adj_journal.append(result)
        print(json.dumps({"adjudicated": f"{card['attribute']}:{card['document_id']}", "reason": result.get("reason"), "global": ledger.spent}, indent=2), flush=True)

    (OUT / "adjudication_journal.json").write_text(json.dumps(adj_journal, indent=2, default=str))

    majority_fills = fills_from_ids(majority_rows, inventory, specs)
    adj_selected = []
    for item in adj_journal:
        if item.get("status") == "selected" and item.get("winner_id"):
            adj_selected.append(
                {
                    "entity_id": item["entity_id"],
                    "attribute": item["attribute"],
                    "document_id": item["document_id"],
                    "winner_id": item["winner_id"],
                    "status": "selected",
                    "cohort": item["cohort"],
                }
            )
    adj_fills = fills_from_ids(adj_selected, inventory, specs)
    official_fills = merge_official(majority_fills, adj_fills)

    majority_mat = materialize_fills(OUT / "majority_only.db", majority_fills, mapping, statements, predicates, query_ids)
    adj_mat = materialize_fills(OUT / "adjudication_only.db", adj_fills, mapping, statements, predicates, query_ids)
    official_mat = materialize_fills(OUT / "official.db", official_fills, mapping, statements, predicates, query_ids)
    (OUT / "majority_fills.json").write_text(json.dumps(majority_fills, indent=2, default=str))
    (OUT / "adjudication_fills.json").write_text(json.dumps(adj_fills, indent=2, default=str))
    (OUT / "official_fills.json").write_text(json.dumps(official_fills, indent=2, default=str))
    (OUT / "majority_bags.json").write_text(json.dumps(majority_mat["bags"], indent=2, default=str))
    (OUT / "adjudication_only_bags.json").write_text(json.dumps(adj_mat["bags"], indent=2, default=str))
    (OUT / "official_bags.json").write_text(json.dumps(official_mat["bags"], indent=2, default=str))

    counts = Counter(row["cohort"] for row in classified)
    adj_counts = Counter(item.get("reason") for item in adj_journal)
    before_gold = {
        "unanimous_selection": counts.get("unanimous_3", 0),
        "two_of_three_selection": counts.get("majority_2", 0),
        "singleton_selection": counts.get("singleton", 0),
        "conflicting_selection": counts.get("conflict", 0),
        "all_abstain": counts.get("all_abstain", 0),
        "singleton_adjudicator_accept": sum(1 for item in adj_journal if item.get("cohort") == "singleton" and item.get("status") == "selected"),
        "singleton_adjudicator_reject": sum(1 for item in adj_journal if item.get("cohort") == "singleton" and item.get("reason") not in {"budget_unattempted"} and item.get("status") != "selected"),
        "conflict_adjudicator_agreement": sum(1 for item in adj_journal if item.get("reason") == "conflict_agree"),
        "conflict_adjudicator_disagreement": sum(1 for item in adj_journal if item.get("reason") == "conflict_disagree"),
        "budget_unattempted_disputes": sum(1 for item in adj_journal if item.get("reason") == "budget_unattempted"),
        "reason_counts": dict(adj_counts),
        "n_dispute_cards": len(cards),
    }
    (OUT / "agreement_before_gold.json").write_text(json.dumps(before_gold, indent=2))

    arms = {
        "replica_1": replica_execs[0],
        "replica_2": replica_execs[1],
        "replica_3": replica_execs[2],
        "majority": {"fills": majority_fills, "mat": majority_mat, "db": OUT / "majority_only.db"},
        "adjudication_only": {"fills": adj_fills, "mat": adj_mat, "db": OUT / "adjudication_only.db"},
        "official": {"fills": official_fills, "mat": official_mat, "db": OUT / "official.db"},
    }
    pre_score_gates = {}
    for name, arm in arms.items():
        pre_score_gates[name] = verify_db(arm["db"], arm["fills"], mapping, inventory, statements, plumbing_rows, specs)
        pre_score_gates[name]["queries_execute"] = execute_all(arm["db"], statements)
        pre_score_gates[name]["empty_sidecar_reproduces_plumbing"] = empty_ok
        pre_score_gates[name]["ids_resolve_to_inventory"] = pre_score_gates[name]["writes_from_inventory_candidates"]
    pre_score_gates["cards_have_no_query_literals"] = not any(card_has_query_literals(card, records) for card in cards)
    pre_score_gates["executor_unchanged"] = inspect_executor(sorted(specs))
    pre_score_gates["total_spend_le_theta25"] = ledger.spent <= THETA_25
    pre_score_gates["n_replicas"] = len(replicas) == 3
    if not all(all(v.values()) if isinstance(v, dict) else v for v in pre_score_gates.values()):
        print(json.dumps({"pre_score_gates": pre_score_gates}, indent=2), flush=True)
        raise SystemExit("pre-score gate failure")

    freeze = {
        "spent": ledger.spent,
        "replica_spends": [row["spent"] for row in replicas],
        "adjudication_spent": ledger.spent - sum(row["spent"] for row in replicas),
        "policy": policy,
        "before_gold": before_gold,
        "hashes": {
            "inventory": _hash(inventory),
            "samples": samples_hash(samples),
            "policy": _hash(policy),
            "replica_specs": [_hash(row["validated"]) for row in replicas],
            "cards": _hash(cards),
            "schedule": _hash([{"entity_id": c["entity_id"], "attribute": c["attribute"], "priority": c["priority"]} for c in cards]),
            "adjudication_journal": _hash(adj_journal),
            "majority_bags": majority_mat["bag_sha256"],
            "adjudication_only_bags": adj_mat["bag_sha256"],
            "official_bags": official_mat["bag_sha256"],
            "ledger": ledger.fingerprint(),
            "agreement": _hash(before_gold),
        },
        "gates": pre_score_gates,
    }
    (OUT / "frozen.json").write_text(json.dumps(freeze, indent=2, default=str))
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "before_gold": before_gold}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    plumbing_score = score_db(PLUMBING, statements, predicates, query_ids, gold)
    scores = {"plumbing": plumbing_score}
    for name, arm in arms.items():
        scores[name] = score_db(arm["db"], statements, predicates, query_ids, gold)
    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}

    docetl_eval = json.loads((DOCETL_DIR / "evaluation.json").read_text())
    docetl_score = {
        "mean_structure_f2": float(docetl_eval.get("mean_structure_fbeta_score") or 0.0),
        "mean_cell_f1_at_0.20": float((docetl_eval.get("mean_cell_f1") or {}).get("0.2") or 0.0),
        "mean_per_query_product": float((docetl_eval.get("mean_query_score") or {}).get("0.2") or DOCETL_PRODUCT),
        "tokens": 1_381_827,
        "accepted_cells": None,
        "sql_visible_fills": None,
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

    def accepted_map(rows: list[dict[str, Any]]) -> dict[tuple[str, str], Any]:
        return {(row["document_id"], row["attribute"]): row.get("accepted") for row in rows if not _null(row.get("accepted"))}

    def diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
        recall = Counter()
        acc = Counter()
        accepted = accepted_map(rows)
        for rec in inventory:
            if rec.get("empty"):
                continue
            gold_v = gold_value(rec["document_id"], rec["attribute"])
            present = any(
                gold_match(rec["attribute"], item.get("normalized"), gold_v) or gold_match(rec["attribute"], item.get("raw_span"), gold_v)
                for item in rec.get("candidates") or []
            )
            recall["n"] += 1
            recall["present"] += int(present)
            if present:
                acc["n"] += 1
                acc["ok"] += int(gold_match(rec["attribute"], accepted.get((rec["document_id"], rec["attribute"])), gold_v))
        return {"candidate_set_recall": dict(recall), "selector_accuracy_given_present": dict(acc)}

    def cohort_accuracy(cells: list[dict[str, Any]], accepted: dict[tuple[str, str], Any]) -> dict[str, int]:
        out = Counter()
        for row in cells:
            rec = inv_index[(row["entity_id"], row["attribute"])]
            gold_v = gold_value(row["document_id"], row["attribute"])
            present = any(
                gold_match(row["attribute"], item.get("normalized"), gold_v) or gold_match(row["attribute"], item.get("raw_span"), gold_v)
                for item in rec.get("candidates") or []
            )
            out["n"] += 1
            out["gold_present"] += int(present)
            if present:
                out["ok"] += int(gold_match(row["attribute"], accepted.get((row["document_id"], row["attribute"])), gold_v))
        return dict(out)

    official_rows = []
    official_accepted = {}
    for doc, values in official_fills.items():
        for attr, value in values.items():
            official_accepted[(doc, attr)] = value
            official_rows.append({"document_id": doc, "attribute": attr, "accepted": value})
    majority_accepted = {(doc, attr): value for doc, values in majority_fills.items() for attr, value in values.items()}
    adj_accepted_map = {(doc, attr): value for doc, values in adj_fills.items() for attr, value in values.items()}

    error_kinds = Counter()
    for rec in inventory:
        if rec.get("empty"):
            continue
        key = (rec["document_id"], rec["attribute"])
        pred = official_accepted.get(key)
        if _null(pred):
            continue
        gold_v = gold_value(rec["document_id"], rec["attribute"])
        matches = [
            item
            for item in rec.get("candidates") or []
            if gold_match(rec["attribute"], item.get("normalized"), gold_v) or gold_match(rec["attribute"], item.get("raw_span"), gold_v)
        ]
        chosen = next((item for item in rec.get("candidates") or [] if construct_program(specs[rec["attribute"]], [cand_from_dict(x) for x in rec["candidates"]], {"status": "selected", "candidate_ids": [item.get("id")]}).get("value") == pred), None)
        if not matches:
            if gold_v not in (None, ""):
                error_kinds["gold_absent_from_inventory"] += 1
            continue
        if chosen is None:
            continue
        if any(item.get("id") == chosen.get("id") for item in matches):
            error_kinds["correct_candidate"] += 1
            continue
        error_kinds["wrong_candidate"] += 1
        gold_periods = {str(item.get("period") or "") for item in matches}
        if str(chosen.get("period") or "") not in gold_periods:
            error_kinds["wrong_period"] += 1
        gold_units = {str(item.get("unit") or "") for item in matches}
        if str(chosen.get("unit") or "") not in gold_units:
            error_kinds["wrong_unit"] += 1
        from quwarts.core.amortized_select.features import scope_role

        chosen_scope = scope_role(str(chosen.get("row_label") or ""), str(chosen.get("column_header") or ""), str(chosen.get("table_title") or ""), str(chosen.get("heading") or ""))
        gold_scopes = {
            scope_role(str(item.get("row_label") or ""), str(item.get("column_header") or ""), str(item.get("table_title") or ""), str(item.get("heading") or ""))
            for item in matches
        }
        if chosen_scope in {"component", "segment"} and gold_scopes & {"total", "consolidated", "entity_level"}:
            error_kinds["wrong_component"] += 1

    replica_diff = []
    for row in classified:
        votes = row["votes"]
        if row["cohort"] in {"singleton", "conflict"}:
            replica_diff.append(row)
    recovered = []
    rejected = []
    for item in adj_journal:
        key = (item["document_id"], item["attribute"])
        rec = {"document_id": item["document_id"], "attribute": item["attribute"], "reason": item.get("reason"), "winner_id": item.get("winner_id")}
        if item.get("status") == "selected":
            recovered.append(rec)
        elif item.get("reason") != "budget_unattempted":
            rejected.append(rec)

    compiler_tokens = sum(row["spent"] for row in replicas)
    adj_tokens = ledger.spent - compiler_tokens
    payload = {
        "spent": ledger.spent,
        "replica_spends": [row["spent"] for row in replicas],
        "adjudication_spent": adj_tokens,
        "before_gold": before_gold,
        "arms": {
            "plumbing": arm_report(0, plumbing_score, {}, plumbing_bags, {"changed_cells": 0}, plumbing_score, plumbing_bags, records),
            "replica_1": arm_report(replicas[0]["spent"], scores["replica_1"], replica_execs[0]["fills"], replica_execs[0]["mat"]["bags"], replica_execs[0]["mat"]["overlay"], plumbing_score, plumbing_bags, records),
            "replica_2": arm_report(replicas[1]["spent"], scores["replica_2"], replica_execs[1]["fills"], replica_execs[1]["mat"]["bags"], replica_execs[1]["mat"]["overlay"], plumbing_score, plumbing_bags, records),
            "replica_3": arm_report(replicas[2]["spent"], scores["replica_3"], replica_execs[2]["fills"], replica_execs[2]["mat"]["bags"], replica_execs[2]["mat"]["overlay"], plumbing_score, plumbing_bags, records),
            "majority": arm_report(compiler_tokens, scores["majority"], majority_fills, majority_mat["bags"], majority_mat["overlay"], plumbing_score, plumbing_bags, records),
            "adjudication_only": arm_report(adj_tokens, scores["adjudication_only"], adj_fills, adj_mat["bags"], adj_mat["overlay"], plumbing_score, plumbing_bags, records),
            "official": arm_report(ledger.spent, scores["official"], official_fills, official_mat["bags"], official_mat["overlay"], plumbing_score, plumbing_bags, records),
            "docetl": docetl_score,
        },
        "diagnostics_after_gold": {
            "replica_1": diagnostics(replica_execs[0]["rows"]),
            "replica_2": diagnostics(replica_execs[1]["rows"]),
            "replica_3": diagnostics(replica_execs[2]["rows"]),
            "majority": diagnostics([{"document_id": d, "attribute": a, "accepted": v} for d, vals in majority_fills.items() for a, v in vals.items()]),
            "official": diagnostics(official_rows),
            "majority_cohort": cohort_accuracy([row for row in classified if row["cohort"] in {"unanimous_3", "majority_2"}], majority_accepted),
            "singleton_adjudicated": cohort_accuracy([row for row in classified if row["cohort"] == "singleton"], adj_accepted_map),
            "conflict_adjudicated": cohort_accuracy([row for row in classified if row["cohort"] == "conflict"], adj_accepted_map),
            "error_kinds": dict(error_kinds),
            "replica_difference_cells": len(replica_diff),
            "adjudication_recovered": recovered,
            "adjudication_rejected": rejected,
        },
        "hashes": freeze["hashes"],
    }
    official_product = scores["official"]["mean_per_query_product"]
    majority_product = scores["majority"]["mean_per_query_product"]
    if ledger.spent > THETA_25 or len(replicas) != 3:
        decision = "run invalid"
    elif official_product > DOCETL_PRODUCT and ledger.spent <= THETA_25:
        decision = "targeted adjudication reproducibly beats DocETL within theta25"
    elif official_product < majority_product:
        decision = "adjudication harms the stable compiler consensus"
    else:
        decision = "compiler instability remains unresolved within theta25"
    payload["decision"] = decision
    (OUT / "finan_amortized_uncertainty_adjudicate.json").write_text(json.dumps(payload, indent=2, default=str))

    def row_line(name: str, arm: dict[str, Any]) -> str:
        return (
            f"| {name} | {arm.get('tokens')} | {arm.get('accepted_cells')} | {arm.get('sql_visible_fills')} | "
            f"{arm.get('mean_structure_f2', 0):.4f} | {arm.get('mean_cell_f1_at_0.20', 0):.4f} | {arm.get('mean_per_query_product', 0):.4f} |"
        )

    lines = [
        "# Finan uncertainty-triggered program-selection arm",
        "",
        f"**Decision: `{decision}`**",
        "",
        f"Global spend {ledger.spent} / {THETA_25}. Compiler {compiler_tokens}; adjudication {adj_tokens}.",
        "",
        "| Arm | Tokens | Accepted | SQL-visible | F2 | F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        row_line("plumbing", payload["arms"]["plumbing"]),
        row_line("compiler replica 1", payload["arms"]["replica_1"]),
        row_line("compiler replica 2", payload["arms"]["replica_2"]),
        row_line("compiler replica 3", payload["arms"]["replica_3"]),
        row_line("majority-only", payload["arms"]["majority"]),
        row_line("adjudication-only", payload["arms"]["adjudication_only"]),
        row_line("official combined", payload["arms"]["official"]),
        f"| DocETL | {docetl_score['tokens']} | — | — | {docetl_score['mean_structure_f2']:.4f} | {docetl_score['mean_cell_f1_at_0.20']:.4f} | {docetl_score['mean_per_query_product']:.4f} |",
        "",
        "## Before-gold decision counts",
        "",
        json.dumps(before_gold, indent=2),
        "",
        "## Per-query official deltas vs plumbing",
        "",
    ]
    for row in payload["arms"]["official"]["per_query"]:
        lines.append(f"- `{row['query_id']}`: {row['product']:.4f} (Δ {row['delta']:+.4f})")
    lines.extend(
        [
            "",
            "## Diagnostics after gold",
            "",
            json.dumps(payload["diagnostics_after_gold"], indent=2, default=str),
            "",
            f"**Primary decision:** `{decision}`",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"decision": decision, "official": official_product, "majority": majority_product, "spent": ledger.spent}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

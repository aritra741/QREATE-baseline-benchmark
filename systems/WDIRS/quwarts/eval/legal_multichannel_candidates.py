"""Legal multi-channel candidate generation plus the frozen coverage-selected selector."""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.amortized_select.config import SAMPLE_SETS_PER_ATTRIBUTE
from quwarts.core.amortized_select.features import annotate_set, spec_tokens
from quwarts.core.amortized_select.sample import sample_attribute, samples_hash
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog, specs_hash
from quwarts.core.full_window_additive.overlay import empty_overlay_matches, execute_all, official_bag
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.multichannel_candidates.context import EFFECTIVE_INPUT_LIMIT
from quwarts.core.multichannel_candidates.normalize import compose_deterministic, expand_normalized, replay_trace
from quwarts.core.multichannel_candidates.propose import propose_cell, route_attribute, verify_candidate
from quwarts.core.multichannel_candidates.representation import (
    dedup_candidates,
    official_candidates,
    provenance_ok,
    surface_to_record,
)
from quwarts.core.multichannel_candidates.schedule import order_jobs
from quwarts.core.multichannel_candidates.workload import attach_supported_labels, compile_visible_labels
from quwarts.core.shared_bundle.context_blocks import parse_layout
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_coverage_select import RANKING_RULE, coverage_stats, pairwise_ids, select_replica
from quwarts.eval.finan_amortized_program_only_repro import compile_replica, execute_program
from quwarts.eval.finan_amortized_select_arm import inspect_executor, mapping_from_rows, _hash, _null
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_DIR,
    DOCETL_F1,
    DOCETL_F2,
    DOCETL_PRODUCT,
    DOCETL_TOKENS,
    N_EXPECTED_ROWS,
    N_REPLICAS,
    PLUMBING,
    SCHEMA_PATH,
    SOURCE_DIR,
    TABLE,
    diagnostics,
    docetl_products,
    error_kinds,
    first_gold_candidate,
    generate_inventory,
    gold_index,
    gold_match,
    gold_value,
    load_plumbing_rows,
    materialize_fills,
    oracle_fills,
    score_db,
    verify_db,
)
from quwarts.experiments.extract_util import field_terms
from quwarts.experiments.synthesize_case80 import gold_name, queries_for

load_env_file(ROOT / ".env")

PRIOR = ROOT / "results" / "quwarts_legal_coverage_transfer"
OUT = ROOT / "results" / "quwarts_legal_multichannel_candidates"
THETA_25 = 12_610_011
SELECTION_RESERVE = 345_457
GENERATION_CAP = 12_264_554
COMPILER_CAP = 69_000
EST_PROPOSAL = 4_200


def structures_of(layouts: dict[str, list[Any]], limit: int = 3) -> list[str]:
    names = []
    for doc, blocks in list(layouts.items())[:limit]:
        kinds = sorted({getattr(block, "kind", "") for block in blocks})
        names.append(f"{len(blocks)} blocks kinds={kinds}")
    return names


def channel_filter(inventory: list[dict[str, Any]], channels: set[str] | None, exclude: str | None = None) -> list[dict[str, Any]]:
    out = []
    for rec in inventory:
        items = []
        for item in rec.get("candidates") or []:
            channel = str(item.get("channel") or item.get("derivation") or "")
            if exclude and channel == exclude:
                continue
            if channels is not None and channel not in channels:
                continue
            items.append(item)
        out.append({**rec, "candidates": items, "empty": not items})
    return out


def decide(official: float, replicas: list[float], availability: float) -> str:
    if official > DOCETL_PRODUCT:
        return "multi-channel candidates beat Legal DocETL within theta25"
    if availability <= DOCETL_PRODUCT:
        return "expanded candidate availability remains insufficient"
    if any(item > DOCETL_PRODUCT for item in replicas):
        return "coverage ranking fails after candidate expansion"
    return "selection programs cannot exploit sufficient candidates"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "cache"
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    prior_ids = json.loads((PRIOR / "query_manifest.json").read_text())["query_ids"]
    query_list_hash = _hash(query_ids)
    prior_hash = json.loads((PRIOR / "query_set_parity.json").read_text())["query_list_hash"]
    if query_ids != prior_ids or query_list_hash != prior_hash:
        raise SystemExit(f"query list drifted from frozen transfer: {query_list_hash} != {prior_hash}")
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    labels_by_attr = compile_visible_labels(statements, records)
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}
    layouts = {doc: parse_layout(doc, text) for doc, text in texts.items()}
    terms = {name: list(dict.fromkeys(field_terms(spec.name) + field_terms(spec.official_description))) for name, spec in specs.items()}
    if (PRIOR / "candidate_inventory.json").is_file():
        surface_raw = json.loads((PRIOR / "candidate_inventory.json").read_text())
        print(json.dumps({"status": "reused_frozen_surface_inventory", "cells": len(surface_raw)}, indent=2), flush=True)
    else:
        surface_raw = generate_inventory(plumbing_rows, specs, texts)
    surface_cells = []
    for rec in surface_raw:
        converted = [surface_to_record(item, rec["attribute"], rec["document_id"], texts.get(rec["document_id"], "")) for item in rec.get("candidates") or []]
        surface_cells.append({**rec, "candidates": converted, "empty": not converted})

    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    if not empty_ok or not execute_all(PLUMBING, statements) or len(plumbing_rows) != N_EXPECTED_ROWS:
        raise SystemExit("plumbing gate failed")

    policy = {
        "theta_25": THETA_25,
        "selection_reserve": SELECTION_RESERVE,
        "generation_cap": GENERATION_CAP,
        "effective_input_limit": EFFECTIVE_INPUT_LIMIT,
        "n_replicas": N_REPLICAS,
        "per_replica_compiler_cap": COMPILER_CAP,
        "ranking": RANKING_RULE,
        "no_union": True,
        "no_gold": True,
        "model": "openrouter/qwen/qwen-2.5-7b-instruct",
        "cache": False,
    }
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))
    (OUT / "query_manifest.json").write_text(json.dumps({"query_ids": query_ids, "hash": query_list_hash}, indent=2))

    ledger = TokenLedger(theta=THETA_25, seed=42)
    density_stats = {}
    for name in specs:
        rows = [rec for rec in surface_cells if rec["attribute"] == name]
        density_stats[name] = {
            "n_cells": len(rows),
            "empty": sum(1 for rec in rows if rec.get("empty")),
            "mean_surface": (sum(len(rec.get("candidates") or []) for rec in rows) / max(1, len(rows))),
        }
    structures = structures_of(layouts)
    routes = {}
    router_journal = []
    for name in sorted(specs):
        routed = route_attribute(ledger, specs[name], records[name], labels_by_attr[name], density_stats[name], structures, SELECTION_RESERVE)
        routes[name] = routed
        router_journal.append({"attribute": name, **routed})
        print(json.dumps({"routed": name, "channels": routed["channels"], "spent": ledger.spent}, indent=2), flush=True)
    (OUT / "routing_specifications.json").write_text(json.dumps(routes, indent=2))
    (OUT / "router_journal.json").write_text(json.dumps(router_journal, indent=2))
    print(json.dumps({"routing_frozen": True, "spent": ledger.spent}, indent=2), flush=True)

    expanded: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in surface_cells:
        spec = specs[rec["attribute"]]
        source = texts.get(rec["document_id"], "")
        surface = list(rec.get("candidates") or [])
        normalized = expand_normalized(surface, spec, rec["document_id"], source) if "normalized" in routes[rec["attribute"]]["channels"] else []
        labels = attach_supported_labels(labels_by_attr[rec["attribute"]]["all_labels"], spec, rec["document_id"], source) if "workload_label" in routes[rec["attribute"]]["channels"] else []
        composed = compose_deterministic(surface, spec, rec["document_id"], source) if "composed" in routes[rec["attribute"]]["channels"] else []
        existing = dedup_candidates(surface + normalized + labels + composed)
        expanded[(rec["entity_id"], rec["attribute"])] = {
            **rec,
            "surface": surface,
            "normalized": normalized,
            "workload_label": labels,
            "composed_det": composed,
            "semantic": [],
            "composed_llm": [],
            "existing": existing,
            "candidates": existing,
            "empty": not existing,
        }

    jobs = order_jobs(
        [
            {
                "entity_id": rec["entity_id"],
                "document_id": rec["document_id"],
                "attribute": rec["attribute"],
                "existing": expanded[(rec["entity_id"], rec["attribute"])]["existing"],
            }
            for rec in surface_cells
        ],
        records,
        labels_by_attr,
        EST_PROPOSAL,
    )
    proposal_path = OUT / "proposal_journal.jsonl"
    verify_path = OUT / "verification_journal.jsonl"
    done = set()
    proposal_handle = proposal_path.open("w")
    verify_handle = verify_path.open("w")
    context_modes = Counter()
    attempted = skipped = 0
    try:
        for job in jobs:
            key = (job["entity_id"], job["attribute"])
            route = routes[job["attribute"]]["channels"]
            if "semantic" not in route and "composed" not in route:
                continue
            if key in done:
                continue
            if ledger.spent >= GENERATION_CAP or ledger.remaining() <= SELECTION_RESERVE + EST_PROPOSAL:
                skipped += 1
                continue
            cell = expanded[key]
            spec = specs[job["attribute"]]
            source = texts[job["document_id"]]
            proposed = propose_cell(
                ledger,
                spec,
                labels_by_attr[job["attribute"]]["all_labels"],
                job["document_id"],
                source,
                layouts[job["document_id"]],
                {job["attribute"]: terms[job["attribute"]]},
                cell["existing"],
                "composed" in route,
                SELECTION_RESERVE,
                job["document_id"],
                job["entity_id"],
            )
            if proposed.get("skipped"):
                skipped += 1
                break
            attempted += 1
            context_modes[proposed["context"]["mode"]] += 1
            verified_rows = []
            for cand in proposed["candidates"]:
                if ledger.remaining() <= SELECTION_RESERVE + 800:
                    break
                checked = verify_candidate(
                    ledger,
                    spec,
                    cand,
                    job["document_id"],
                    proposed["context"]["text"],
                    SELECTION_RESERVE,
                    job["entity_id"],
                )
                verified_rows.append(checked)
                verify_handle.write(json.dumps({"entity_id": job["entity_id"], "attribute": job["attribute"], **{k: checked[k] for k in ("verdict", "reason", "actual") if k in checked}, "candidate_id": cand.get("id")}) + "\n")
                if cand.get("derivation") == "composed":
                    cell["composed_llm"].append(cand)
                else:
                    cell["semantic"].append(cand)
            cell["existing"] = dedup_candidates(cell["existing"] + [row["candidate"] for row in verified_rows])
            cell["candidates"] = cell["existing"]
            cell["empty"] = not cell["candidates"]
            proposal_handle.write(
                json.dumps(
                    {
                        "entity_id": job["entity_id"],
                        "document_id": job["document_id"],
                        "attribute": job["attribute"],
                        "actual": proposed.get("actual"),
                        "context_mode": proposed["context"]["mode"],
                        "context_tokens": proposed["context"]["context_tokens"],
                        "n_proposals": len(proposed["candidates"]),
                        "malformed": proposed.get("malformed"),
                    }
                )
                + "\n"
            )
            if attempted % 25 == 0:
                print(json.dumps({"proposed_cells": attempted, "spent": ledger.spent, "remaining": ledger.remaining(), "mode": dict(context_modes)}, indent=2), flush=True)
    finally:
        proposal_handle.close()
        verify_handle.close()

    inventory = []
    channels = {name: [] for name in ("surface", "normalized", "workload_label", "semantic", "composed")}
    for rec in surface_cells:
        cell = expanded[(rec["entity_id"], rec["attribute"])]
        all_items = dedup_candidates(
            cell.get("surface")
            + cell.get("normalized")
            + cell.get("workload_label")
            + cell.get("composed_det")
            + cell.get("semantic")
            + cell.get("composed_llm")
        )
        for item in all_items:
            channels.setdefault(str(item.get("channel") or item.get("derivation") or "surface"), []).append(item)
        official = official_candidates(all_items)
        inventory.append(
            {
                "entity_id": rec["entity_id"],
                "document_id": rec["document_id"],
                "attribute": rec["attribute"],
                "candidates": official,
                "all_candidates": all_items,
                "empty": not official,
            }
        )
    for name, rows in channels.items():
        (OUT / f"channel_{name}.json").write_text(json.dumps(rows, default=str))
    (OUT / "candidate_inventory.json").write_text(json.dumps(inventory, default=str))
    (OUT / "diagnostic_inventory.json").write_text(json.dumps([{**rec, "candidates": rec["all_candidates"]} for rec in inventory], default=str))

    replay_ok = True
    for rec in inventory:
        spec = specs[rec["attribute"]]
        for item in rec["all_candidates"]:
            if not provenance_ok(item):
                replay_ok = False
            if item.get("derivation") == "normalized" and item.get("normalization_trace"):
                replayed = replay_trace(item.get("value"), item.get("normalization_trace") or [], item.get("raw_span") or "", spec.dtype)
                if replayed not in {item.get("value"), item.get("normalized")} and str(replayed) != str(item.get("value")):
                    replay_ok = False

    gen_hashes = {
        "query_manifest": query_list_hash,
        "plumbing": file_sha256(PLUMBING),
        "routing": _hash(routes),
        "router_prompt": file_sha256(ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "multichannel_candidates" / "prompts.py"),
        "policy": _hash(policy),
        "inventory": _hash([{k: rec[k] for k in ("entity_id", "document_id", "attribute", "candidates")} for rec in inventory]),
        "generation_ledger": ledger.fingerprint(),
    }
    (OUT / "generation_frozen.json").write_text(
        json.dumps(
            {
                "spent": ledger.spent,
                "attempted_proposal_cells": attempted,
                "skipped_or_unattempted": skipped,
                "context_modes": dict(context_modes),
                "hashes": gen_hashes,
                "routes": {name: row["channels"] for name, row in routes.items()},
            },
            indent=2,
        )
    )
    print(json.dumps({"generation_frozen": True, "spent": ledger.spent, "attempted": attempted, "inventory": len(inventory)}, indent=2), flush=True)
    if ledger.spent > GENERATION_CAP or ledger.remaining() < 8_000:
        raise SystemExit("run invalid: generation consumed the selection reserve")

    selector_inventory = [{k: rec[k] for k in ("entity_id", "document_id", "attribute", "candidates", "empty")} for rec in inventory]
    feats_by_key = {
        (rec["entity_id"], rec["attribute"]): annotate_set(
            rec,
            spec_tokens(rec["attribute"], specs[rec["attribute"]].official_description),
            len(texts.get(rec["document_id"], "")),
        )
        for rec in selector_inventory
    }
    by_attr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in selector_inventory:
        if not rec.get("empty"):
            by_attr[rec["attribute"]].append(rec)
    samples = {name: sample_attribute(by_attr[name], feats_by_key, SAMPLE_SETS_PER_ATTRIBUTE) for name in sorted(by_attr)}
    (OUT / "representative_samples.json").write_text(
        json.dumps({name: [{"entity_id": row["entity_id"], "document_id": row["document_id"]} for row in rows] for name, rows in samples.items()}, indent=2)
    )

    selection_ledger = TokenLedger(theta=SELECTION_RESERVE, seed=42)
    replicas = []
    replica_execs = []
    stats_list = []
    for replica_id in range(1, N_REPLICAS + 1):
        compiled = compile_replica(
            replica_id,
            specs,
            samples,
            feats_by_key,
            records,
            [str(row.get("__entity_id") or "") for row in plumbing_rows],
            selection_ledger,
            COMPILER_CAP,
        )
        rows, fills = execute_program(compiled["validated"], selector_inventory, feats_by_key, specs)
        dest = OUT / f"replica_{replica_id}.db"
        mat = materialize_fills(dest, fills, mapping, statements, predicates, query_ids)
        stats = coverage_stats(replica_id, compiled["spent"], fills, mat["bags"], rows, mat["overlay"], records, plumbing_bags)
        replicas.append(compiled)
        replica_execs.append({"rows": rows, "fills": fills, "mat": mat, "db": dest, "stats": stats})
        stats_list.append(stats)
        (OUT / f"replica_{replica_id}_specs.json").write_text(json.dumps(compiled["validated"], indent=2))
        (OUT / f"replica_{replica_id}_journal.json").write_text(
            json.dumps({"compiler": compiled["compiler_journal"], "critic": compiled["critic_journal"], "repair": compiled["repair_journal"]}, indent=2, default=str)
        )
        (OUT / f"replica_{replica_id}_results.json").write_text(json.dumps(rows, indent=2, default=str))
        (OUT / f"replica_{replica_id}_fills.json").write_text(json.dumps(fills, indent=2, default=str))
        (OUT / f"replica_{replica_id}_bags.json").write_text(json.dumps(mat["bags"], indent=2, default=str))
        (OUT / f"replica_{replica_id}_stats.json").write_text(json.dumps(stats, indent=2))
        print(json.dumps({"replica_done": replica_id, **stats, "selection_spent": selection_ledger.spent, "global": ledger.spent + selection_ledger.spent}, indent=2), flush=True)

    if len(replicas) != N_REPLICAS or selection_ledger.spent > SELECTION_RESERVE:
        raise SystemExit("run invalid: not all five selection replicas completed within the reserve")
    if ledger.spent + selection_ledger.spent > THETA_25:
        raise SystemExit("run invalid: global ledger exceeded theta25")
    ledger.spend(selection_ledger.spent, "frozen_selection_stage")

    selected_stats = select_replica(stats_list)
    selected_id = int(selected_stats["replica_id"])
    selected_exec = replica_execs[selected_id - 1]
    shutil.copy2(selected_exec["db"], OUT / "official.db")
    (OUT / "selected_replica.json").write_text(json.dumps({"selected_replica_id": selected_id, "stats": selected_stats, "ranking": RANKING_RULE}, indent=2))
    (OUT / "official_fills.json").write_text(json.dumps(selected_exec["fills"], indent=2, default=str))
    (OUT / "official_bags.json").write_text(json.dumps(selected_exec["mat"]["bags"], indent=2, default=str))
    (OUT / "coverage_stats.json").write_text(json.dumps(stats_list, indent=2))
    agreement = pairwise_ids([item["rows"] for item in replica_execs])

    pre_score = {}
    for idx, arm in enumerate(replica_execs, start=1):
        pre_score[f"replica_{idx}"] = verify_db(arm["db"], arm["fills"], mapping, selector_inventory, statements, plumbing_rows, specs)
        pre_score[f"replica_{idx}"]["queries_execute"] = execute_all(arm["db"], statements)
        pre_score[f"replica_{idx}"]["provenance"] = all(provenance_ok(item) for rec in inventory for item in rec["candidates"])
    pre_score["official"] = verify_db(OUT / "official.db", selected_exec["fills"], mapping, selector_inventory, statements, plumbing_rows, specs)
    pre_score["official"]["queries_execute"] = execute_all(OUT / "official.db", statements)
    pre_score["five_replicas"] = len(replicas) == 5
    pre_score["selected_before_gold"] = selected_id in {1, 2, 3, 4, 5}
    pre_score["empty_overlay"] = empty_ok
    pre_score["replayable_transforms"] = replay_ok
    pre_score["no_train_queries"] = len(query_ids) == 16
    pre_score["spend_le_theta25"] = ledger.spent <= THETA_25
    pre_score["executor_unchanged"] = inspect_executor(sorted(specs))
    if not all(all(v.values()) if isinstance(v, dict) else v for v in pre_score.values()):
        print(json.dumps({"pre_score_gates": pre_score}, indent=2), flush=True)
        raise SystemExit("pre-score gate failure")

    freeze = {
        "selected_replica_id": selected_id,
        "selected_stats": selected_stats,
        "spent": ledger.spent,
        "generation_spent": ledger.spent - selection_ledger.spent,
        "selection_spent": selection_ledger.spent,
        "hashes": {
            **gen_hashes,
            "samples": samples_hash(samples),
            "specs": specs_hash(specs),
            "replica_specs": [_hash(row["validated"]) for row in replicas],
            "replica_bags": [item["mat"]["bag_sha256"] for item in replica_execs],
            "official_bags": selected_exec["mat"]["bag_sha256"],
            "selected": _hash({"selected_replica_id": selected_id, "stats": selected_stats}),
            "ledger": ledger.fingerprint(),
        },
        "gates": pre_score,
    }
    (OUT / "frozen.json").write_text(json.dumps(freeze, indent=2, default=str))
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    (OUT / "selection_ledger.json").write_text(json.dumps(selection_ledger.snapshot(), indent=2, default=str))
    print(json.dumps({"frozen": True, "selected": selected_id, "spent": ledger.spent}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    plumbing_score = score_db(PLUMBING, statements, predicates, query_ids, gold)
    scores = {"plumbing": plumbing_score}
    for idx, arm in enumerate(replica_execs, start=1):
        scores[f"replica_{idx}"] = score_db(arm["db"], statements, predicates, query_ids, gold)
    scores["official"] = scores[f"replica_{selected_id}"]

    diagnostic = [{**rec, "candidates": rec["all_candidates"]} for rec in inventory]
    oracle_defs = {
        "surface": {"channels": {"surface"}},
        "surface_normalized": {"channels": {"surface", "normalized"}},
        "workload_label": {"channels": {"workload_label"}},
        "semantic": {"channels": {"semantic"}},
        "composed": {"channels": {"composed"}},
        "all_expanded": {"channels": None},
    }
    oracle_scores = {}
    for name, spec in oracle_defs.items():
        subset = channel_filter(diagnostic, spec["channels"])
        fills = oracle_fills(subset, specs, gold_by, None)
        dest = OUT / f"oracle_{name}.db"
        mat = materialize_fills(dest, fills, mapping, statements, predicates, query_ids)
        oracle_scores[name] = {**score_db(dest, statements, predicates, query_ids, gold), "accepted_cells": mat["overlay"].get("changed_cells")}
    for name in ("surface", "normalized", "workload_label", "semantic", "composed"):
        subset = channel_filter(diagnostic, None, exclude=name)
        fills = oracle_fills(subset, specs, gold_by, None)
        dest = OUT / f"oracle_loo_{name}.db"
        mat = materialize_fills(dest, fills, mapping, statements, predicates, query_ids)
        oracle_scores[f"loo_{name}"] = {**score_db(dest, statements, predicates, query_ids, gold), "accepted_cells": mat["overlay"].get("changed_cells")}

    prior_payload = json.loads((PRIOR / "legal_coverage_transfer.json").read_text())
    old = prior_payload["arms"]["official"]
    docetl_eval = json.loads((DOCETL_DIR / "evaluation.json").read_text())

    def pack(tokens, score, accepted=None, sql_visible=None, cells=None):
        return {
            "tokens": tokens,
            "candidate_cells": cells,
            "accepted": accepted,
            "sql_visible": sql_visible,
            "mean_structure_f2": score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": score["mean_per_query_product"],
            "per_query": score.get("per_query"),
        }

    products = [scores[f"replica_{i}"]["mean_per_query_product"] for i in range(1, 6)]
    payload = {
        "spent": ledger.spent,
        "generation_spent": freeze["generation_spent"],
        "selection_spent": selection_ledger.spent,
        "selected_replica_id": selected_id,
        "coverage_stats": stats_list,
        "context_modes": dict(context_modes),
        "attempted_proposal_cells": attempted,
        "arms": {
            "plumbing": pack(0, plumbing_score, 0, 0, 0),
            "old_extractive": pack(old.get("tokens"), {"mean_structure_f2": old["mean_structure_f2"], "mean_cell_f1_at_0.20": old["mean_cell_f1_at_0.20"], "mean_per_query_product": old["mean_per_query_product"], "per_query": old.get("per_query")}, old.get("accepted_candidate_count"), old.get("sql_visible_fill_count"), 2978),
            **{
                f"replica_{i}": pack(replicas[i - 1]["spent"], scores[f"replica_{i}"], stats_list[i - 1]["accepted_candidate_count"], stats_list[i - 1]["sql_visible_fill_count"], sum(1 for rec in selector_inventory if rec["candidates"]))
                for i in range(1, 6)
            },
            "official": pack(replicas[selected_id - 1]["spent"], scores["official"], selected_stats["accepted_candidate_count"], selected_stats["sql_visible_fill_count"], sum(1 for rec in selector_inventory if rec["candidates"])),
            "docetl": pack(DOCETL_TOKENS, {"mean_structure_f2": DOCETL_F2, "mean_cell_f1_at_0.20": DOCETL_F1, "mean_per_query_product": DOCETL_PRODUCT, "per_query": [{"query_id": qid, "product": docetl_products(docetl_eval).get(qid)} for qid in query_ids]}),
        },
        "oracles": {name: pack(0, score, score.get("accepted_cells")) for name, score in oracle_scores.items()},
        "diagnostics": {
            **{f"replica_{i}": diagnostics(replica_execs[i - 1]["rows"], diagnostic, specs, gold_by) for i in range(1, 6)},
            "official": diagnostics(selected_exec["rows"], diagnostic, specs, gold_by),
            "error_kinds_official": error_kinds(selected_exec["fills"], diagnostic, specs, gold_by),
        },
        "pairwise": agreement,
        "hashes": freeze["hashes"],
    }
    decision = decide(scores["official"]["mean_per_query_product"], products, oracle_scores["all_expanded"]["mean_per_query_product"])
    if ledger.spent > THETA_25 or len(replicas) != 5:
        decision = "run invalid"
    payload["decision"] = decision
    (OUT / "legal_multichannel_candidates.json").write_text(json.dumps(payload, indent=2, default=str))

    def row(name: str, arm: dict[str, Any]) -> str:
        def fmt(key):
            value = arm.get(key)
            return "" if value is None else value

        return (
            f"| {name} | {fmt('tokens')} | {fmt('candidate_cells')} | {fmt('accepted')} | {fmt('sql_visible')} | "
            f"{arm['mean_structure_f2']:.4f} | {arm['mean_cell_f1_at_0.20']:.4f} | {arm['mean_per_query_product']:.4f} |"
        )

    lines = [
        "# Legal multi-channel candidate generation",
        "",
        f"**Decision: `{decision}`**",
        "",
        f"Global spend {ledger.spent} / {THETA_25}. Generation {freeze['generation_spent']}. Selection {selection_ledger.spent}. Selected replica {selected_id}.",
        "",
        "| Arm | Tokens | Candidate cells | Accepted | SQL-visible | F2 | F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        row("plumbing", payload["arms"]["plumbing"]),
        row("old extractive inventory", payload["arms"]["old_extractive"]),
    ]
    for i in range(1, 6):
        lines.append(row(f"replica {i}", payload["arms"][f"replica_{i}"]))
    lines.append(row("selected official", payload["arms"]["official"]))
    lines.append(row("DocETL", payload["arms"]["docetl"]))
    lines.extend(["", "## Channel-availability oracles (zero new calls)", ""])
    for name, arm in payload["oracles"].items():
        lines.append(row(name, arm))
    lines.extend(["", "## Official per-query products", ""])
    for item in scores["official"]["per_query"]:
        lines.append(f"- `{item['query_id']}`: {item['product']:.4f}")
    lines.extend(
        [
            "",
            f"Context modes: {dict(context_modes)}",
            f"Proposal cells attempted: {attempted}",
            "",
            json.dumps(payload["diagnostics"]["official"], indent=2, default=str),
            "",
            f"**Primary decision:** `{decision}`",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"decision": decision, "official": scores["official"]["mean_per_query_product"], "availability": oracle_scores["all_expanded"]["mean_per_query_product"], "replicas": products, "spent": ledger.spent}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

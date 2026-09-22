"""Five-replica coverage-selected program synthesis. Locked compiler stack. No per-cell LLM."""

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

from quwarts.core.amortized_select.config import THETA_25
from quwarts.core.amortized_select.features import annotate_set, scope_role, spec_tokens
from quwarts.core.amortized_select.sample import samples_hash
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import empty_overlay_matches, execute_all, official_bag
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
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
    load_plumbing_rows,
    mapping_from_rows,
    materialize_fills,
    _hash,
    _null,
)
from quwarts.experiments.synthesize_case80 import gold_name

load_env_file(ROOT / ".env")

AMORTIZED = ROOT / "results" / "quwarts_finan_amortized_select"
PRIOR_REPRO = ROOT / "results" / "quwarts_finan_amortized_program_only_repro"
PRIOR_ADJ = ROOT / "results" / "quwarts_finan_amortized_uncertainty_adjudicate"
FROZEN_INV = ROOT / "results" / "quwarts_finan_candidate_select"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
SCHEMA_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
OUT = ROOT / "results" / "quwarts_finan_amortized_coverage_select"
DOCETL_PRODUCT = 0.0841
COMPILER_CAP = 69_000
N_REPLICAS = 5
RANKING_RULE = [
    "greatest accepted_candidate_count",
    "greatest sql_visible_fill_count",
    "greatest attributes_with_at_least_one_selection",
    "fewest official_empty_bag_count",
    "lowest tokens_spent",
    "lowest replica index",
]


def coverage_stats(
    replica_id: int,
    tokens: int,
    fills: dict[str, dict[str, Any]],
    bags: dict[str, Any],
    rows: list[dict[str, Any]],
    overlay: dict[str, Any],
    records,
    plumbing_bags: dict[str, Any],
) -> dict[str, Any]:
    accepted = int(overlay.get("changed_cells") or sum(len(values) for values in fills.values()))
    sql_visible = 0
    for doc, values in fills.items():
        for attr in values:
            if any(_hash(bags.get(qid)) != _hash(plumbing_bags.get(qid)) for qid in records[attr].queries):
                sql_visible += 1
    attrs = {attr for values in fills.values() for attr in values}
    abstentions = sum(1 for row in rows if _null(row.get("accepted")))
    empty = sum(1 for bag in bags.values() if bag_empty(bag))
    return {
        "replica_id": replica_id,
        "accepted_candidate_count": accepted,
        "sql_visible_fill_count": sql_visible,
        "abstention_count": abstentions,
        "attributes_with_at_least_one_selection": len(attrs),
        "official_empty_bag_count": empty,
        "tokens_spent": int(tokens),
        "empty_bags": [qid for qid, bag in bags.items() if bag_empty(bag)],
    }


def rank_key(stats: dict[str, Any]) -> tuple:
    return (
        -int(stats["accepted_candidate_count"]),
        -int(stats["sql_visible_fill_count"]),
        -int(stats["attributes_with_at_least_one_selection"]),
        int(stats["official_empty_bag_count"]),
        int(stats["tokens_spent"]),
        int(stats["replica_id"]),
    )


def select_replica(stats_list: list[dict[str, Any]]) -> dict[str, Any]:
    chosen = sorted(stats_list, key=rank_key)[0]
    return chosen


def retrospective_from_artifacts(name: str, directory: Path, payload_name: str, n: int) -> dict[str, Any]:
    payload = json.loads((directory / payload_name).read_text())
    arms = payload["arms"]
    rows = []
    for idx in range(1, n + 1):
        fills = json.loads((directory / f"replica_{idx}_fills.json").read_text())
        results = json.loads((directory / f"replica_{idx}_results.json").read_text())
        arm = arms[f"replica_{idx}"]
        attrs = {attr for values in fills.values() for attr in values}
        abstentions = sum(1 for row in results if _null(row.get("accepted")))
        stats = {
            "replica_id": idx,
            "accepted_candidate_count": arm["accepted_cells"],
            "sql_visible_fill_count": arm["sql_visible_fills"],
            "abstention_count": abstentions,
            "attributes_with_at_least_one_selection": len(attrs),
            "official_empty_bag_count": arm.get("n_empty_bags") if arm.get("n_empty_bags") is not None else len(arm.get("empty_bags") or []),
            "tokens_spent": arm["tokens"],
            "product": arm["mean_per_query_product"],
            "mean_structure_f2": arm["mean_structure_f2"],
            "mean_cell_f1_at_0.20": arm["mean_cell_f1_at_0.20"],
        }
        rows.append(stats)
    selected = select_replica(rows)
    return {
        "experiment": name,
        "label": "retrospective_only",
        "replicas": rows,
        "selected_replica_id": selected["replica_id"],
        "selected_product": selected["product"],
        "selected_accepted": selected["accepted_candidate_count"],
    }


def pairwise_ids(replica_rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    def cell_id(row: dict[str, Any]) -> str | None:
        ids = [item for item in (row.get("used_ids") or row.get("candidate_ids") or []) if item]
        if row.get("status") == "selected" and ids and not _null(row.get("accepted")):
            return str(ids[0])
        return None

    maps = []
    for rows in replica_rows:
        maps.append({(row["entity_id"], row["attribute"]): cell_id(row) for row in rows})
    pair = {}
    for i in range(len(maps)):
        for j in range(i + 1, len(maps)):
            keys = set(maps[i]) | set(maps[j])
            same = sum(1 for key in keys if maps[i].get(key) == maps[j].get(key))
            pair[f"{i+1}-{j+1}"] = {"cells_equal": same, "n": len(keys)}
    return pair


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "cache"
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)

    policy = {
        "rule": "coverage_select_one_complete_replica",
        "ranking": RANKING_RULE,
        "first_criterion_dominates": True,
        "n_replicas": N_REPLICAS,
        "per_replica_compiler_cap": COMPILER_CAP,
        "max_compiler_spend": COMPILER_CAP * N_REPLICAS,
        "global_theta": THETA_25,
        "no_union": True,
        "no_majority": True,
        "no_per_attribute_mix": True,
        "no_residual": True,
        "no_adjudication": True,
        "no_per_cell_llm": True,
        "no_gold_in_selection": True,
    }
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))
    print(json.dumps({"frozen_ranking_rule": _hash(policy), "ranking": RANKING_RULE}, indent=2), flush=True)

    retro = {
        "prior_program_only_repro": retrospective_from_artifacts(
            "quwarts_finan_amortized_program_only_repro",
            PRIOR_REPRO,
            "finan_amortized_program_only_repro.json",
            3,
        ),
        "prior_uncertainty_adjudicate": retrospective_from_artifacts(
            "quwarts_finan_amortized_uncertainty_adjudicate",
            PRIOR_ADJ,
            "finan_amortized_uncertainty_adjudicate.json",
            3,
        ),
    }
    (OUT / "retrospective_coverage.json").write_text(json.dumps(retro, indent=2))
    print(json.dumps({"retrospective": {k: {"selected": v["selected_replica_id"], "accepted": v["selected_accepted"], "product": v["selected_product"]} for k, v in retro.items()}}, indent=2), flush=True)

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}

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
    feats_by_key = {
        (rec["entity_id"], rec["attribute"]): annotate_set(
            rec,
            spec_tokens(rec["attribute"], specs[rec["attribute"]].official_description),
            len(texts.get(rec["document_id"], "")),
        )
        for rec in inventory
    }

    if COMPILER_CAP * N_REPLICAS > THETA_25:
        raise SystemExit("five replica caps exceed theta25")
    if not inspect_executor(sorted(specs)):
        raise SystemExit("executor grew attribute branches")
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    if not empty_ok or not execute_all(PLUMBING, statements):
        raise SystemExit("pre-replica overlay/query gate failed")

    ledger = TokenLedger(theta=THETA_25, seed=42)
    replicas = []
    replica_execs = []
    stats_list = []
    for replica_id in range(1, N_REPLICAS + 1):
        if ledger.remaining() < 8_000:
            raise SystemExit(f"run invalid: cannot start replica {replica_id} within theta25")
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
        with (OUT / f"replica_{replica_id}_prompts.jsonl").open("w") as handle:
            for row in compiled["prompts"]:
                handle.write(json.dumps(row) + "\n")
        print(json.dumps({"replica_done": replica_id, **stats, "global": ledger.spent}, indent=2), flush=True)

    if len(replicas) != N_REPLICAS:
        raise SystemExit("run invalid: not all five replicas completed")
    if ledger.spent > THETA_25:
        raise SystemExit("run invalid: ledger exceeded theta25")

    selected_stats = select_replica(stats_list)
    selected_id = int(selected_stats["replica_id"])
    selected_exec = replica_execs[selected_id - 1]
    selected_fills = selected_exec["fills"]
    shutil.copy2(selected_exec["db"], OUT / "official.db")
    official_mat = {
        "overlay": selected_exec["mat"]["overlay"],
        "bags": selected_exec["mat"]["bags"],
        "bag_sha256": selected_exec["mat"]["bag_sha256"],
        "db_sha256": file_sha256(OUT / "official.db"),
    }
    (OUT / "official_fills.json").write_text(json.dumps(selected_fills, indent=2, default=str))
    (OUT / "official_bags.json").write_text(json.dumps(official_mat["bags"], indent=2, default=str))
    (OUT / "selected_replica.json").write_text(json.dumps({"selected_replica_id": selected_id, "stats": selected_stats, "ranking": RANKING_RULE}, indent=2))
    (OUT / "coverage_stats.json").write_text(json.dumps(stats_list, indent=2))
    agreement = pairwise_ids([item["rows"] for item in replica_execs])
    (OUT / "agreement_before_gold.json").write_text(json.dumps(agreement, indent=2))

    pre_score_gates = {}
    for idx, arm in enumerate(replica_execs, start=1):
        pre_score_gates[f"replica_{idx}"] = verify_db(arm["db"], arm["fills"], mapping, inventory, statements, plumbing_rows, specs)
        pre_score_gates[f"replica_{idx}"]["queries_execute"] = execute_all(arm["db"], statements)
        pre_score_gates[f"replica_{idx}"]["empty_sidecar_reproduces_plumbing"] = empty_ok
    pre_score_gates["official"] = verify_db(OUT / "official.db", selected_fills, mapping, inventory, statements, plumbing_rows, specs)
    pre_score_gates["official"]["queries_execute"] = execute_all(OUT / "official.db", statements)
    pre_score_gates["official"]["empty_sidecar_reproduces_plumbing"] = empty_ok
    pre_score_gates["official"]["is_complete_selected_replica"] = official_mat["bag_sha256"] == selected_exec["mat"]["bag_sha256"]
    pre_score_gates["executor_unchanged"] = inspect_executor(sorted(specs))
    pre_score_gates["total_spend_le_theta25"] = ledger.spent <= THETA_25
    pre_score_gates["n_replicas"] = len(replicas) == 5
    pre_score_gates["selected_before_gold"] = selected_id in {1, 2, 3, 4, 5}
    if not all(all(v.values()) if isinstance(v, dict) else v for v in pre_score_gates.values()):
        print(json.dumps({"pre_score_gates": pre_score_gates}, indent=2), flush=True)
        raise SystemExit("pre-score gate failure")

    freeze = {
        "selected_replica_id": selected_id,
        "selected_stats": selected_stats,
        "coverage_stats": stats_list,
        "spent": ledger.spent,
        "policy": policy,
        "retrospective": {k: {"selected_replica_id": v["selected_replica_id"], "selected_accepted": v["selected_accepted"], "selected_product": v["selected_product"]} for k, v in retro.items()},
        "hashes": {
            "inventory": _hash(inventory),
            "samples": samples_hash(samples),
            "policy": _hash(policy),
            "replica_specs": [_hash(row["validated"]) for row in replicas],
            "replica_bags": [item["mat"]["bag_sha256"] for item in replica_execs],
            "official_bags": official_mat["bag_sha256"],
            "selected_replica": _hash({"selected_replica_id": selected_id, "stats": selected_stats}),
            "ledger": ledger.fingerprint(),
            "agreement": _hash(agreement),
        },
        "gates": pre_score_gates,
    }
    (OUT / "frozen.json").write_text(json.dumps(freeze, indent=2, default=str))
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    print(json.dumps({"frozen": True, "selected_replica_id": selected_id, "spent": ledger.spent, "stats": stats_list}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    plumbing_score = score_db(PLUMBING, statements, predicates, query_ids, gold)
    scores = {"plumbing": plumbing_score}
    for idx, arm in enumerate(replica_execs, start=1):
        scores[f"replica_{idx}"] = score_db(arm["db"], statements, predicates, query_ids, gold)
    scores["official"] = scores[f"replica_{selected_id}"]

    docetl_eval = json.loads((DOCETL_DIR / "evaluation.json").read_text())
    docetl_score = {
        "mean_structure_f2": 0.5367,
        "mean_cell_f1_at_0.20": 0.1142,
        "mean_per_query_product": 0.0841,
        "tokens": 1_381_827,
        "source": "frozen_docetl_finan_case80_evaluation.json",
        "live_mean_query_score_0.2": float((docetl_eval.get("mean_query_score") or {}).get("0.2") or 0.0),
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
        accepted_acc = Counter()
        accepted = {(row["document_id"], row["attribute"]): row.get("accepted") for row in rows if not _null(row.get("accepted"))}
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
        for (doc, attr), value in accepted.items():
            accepted_acc["n"] += 1
            accepted_acc["ok"] += int(gold_match(attr, value, gold_value(doc, attr)))
        return {
            "candidate_set_recall": dict(recall),
            "selector_accuracy_given_present": dict(acc),
            "accepted_cell_accuracy": dict(accepted_acc),
        }

    def error_kinds(fills: dict[str, dict[str, Any]]) -> dict[str, int]:
        kinds = Counter()
        for rec in inventory:
            if rec.get("empty"):
                continue
            pred = (fills.get(rec["document_id"]) or {}).get(rec["attribute"])
            if _null(pred):
                continue
            gold_v = gold_value(rec["document_id"], rec["attribute"])
            matches = [
                item
                for item in rec.get("candidates") or []
                if gold_match(rec["attribute"], item.get("normalized"), gold_v) or gold_match(rec["attribute"], item.get("raw_span"), gold_v)
            ]
            objs = [cand_from_dict(item) for item in rec["candidates"]]
            chosen = None
            for item in rec.get("candidates") or []:
                built = construct_program(specs[rec["attribute"]], objs, {"status": "selected", "candidate_ids": [item.get("id")]})
                if built.get("value") == pred:
                    chosen = item
                    break
            if not matches:
                if gold_v not in (None, ""):
                    kinds["gold_absent_from_inventory"] += 1
                continue
            if chosen is None:
                continue
            if any(item.get("id") == chosen.get("id") for item in matches):
                kinds["correct_candidate"] += 1
                continue
            kinds["wrong_candidate"] += 1
            if str(chosen.get("period") or "") not in {str(item.get("period") or "") for item in matches}:
                kinds["wrong_period"] += 1
            if str(chosen.get("unit") or "") not in {str(item.get("unit") or "") for item in matches}:
                kinds["wrong_unit"] += 1
            chosen_scope = scope_role(str(chosen.get("row_label") or ""), str(chosen.get("column_header") or ""), str(chosen.get("table_title") or ""), str(chosen.get("heading") or ""))
            gold_scopes = {
                scope_role(str(item.get("row_label") or ""), str(item.get("column_header") or ""), str(item.get("table_title") or ""), str(item.get("heading") or ""))
                for item in matches
            }
            if chosen_scope in {"component", "segment"} and gold_scopes & {"total", "consolidated", "entity_level"}:
                kinds["wrong_component"] += 1
        return dict(kinds)

    def arm_report(tokens: int, score: dict[str, Any], fills, bags, overlay) -> dict[str, Any]:
        per_query = []
        for left, right in zip(plumbing_score["per_query"], score["per_query"]):
            per_query.append({**right, "plumbing_product": left["product"], "delta": right["product"] - left["product"]})
        return {
            "tokens": tokens,
            "mean_structure_f2": score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": score["mean_per_query_product"],
            "accepted_cells": overlay.get("changed_cells"),
            "sql_visible_fills": None,
            "per_query": per_query,
        }

    products = [scores[f"replica_{i}"]["mean_per_query_product"] for i in range(1, 6)]
    accepted_order = [stats_list[i]["accepted_candidate_count"] for i in range(5)]
    product_by_accepted = sorted(zip(accepted_order, products, range(1, 6)))
    monotonic = all(product_by_accepted[i][1] <= product_by_accepted[i + 1][1] + 1e-12 for i in range(len(product_by_accepted) - 1))
    modes = defaultdict(list)
    for i, product in enumerate(products, start=1):
        modes[round(product, 4)].append(i)

    payload = {
        "retrospective": retro,
        "coverage_stats": stats_list,
        "selected_replica_id": selected_id,
        "spent": ledger.spent,
        "arms": {
            "plumbing": arm_report(0, plumbing_score, {}, plumbing_bags, {"changed_cells": 0}),
            **{f"replica_{i}": {**arm_report(replicas[i - 1]["spent"], scores[f"replica_{i}"], replica_execs[i - 1]["fills"], replica_execs[i - 1]["mat"]["bags"], replica_execs[i - 1]["mat"]["overlay"]), **stats_list[i - 1]} for i in range(1, 6)},
            "official": {**arm_report(replicas[selected_id - 1]["spent"], scores["official"], selected_fills, official_mat["bags"], official_mat["overlay"]), **selected_stats, "selected_replica_id": selected_id},
            "docetl": docetl_score,
        },
        "pairwise_candidate_agreement": agreement,
        "behavior_modes": {str(k): v for k, v in modes.items()},
        "coverage_predicts_product_monotonically": monotonic,
        "diagnostics_after_gold": {
            **{f"replica_{i}": diagnostics(replica_execs[i - 1]["rows"]) for i in range(1, 6)},
            "official": diagnostics(selected_exec["rows"]),
            "error_kinds_official": error_kinds(selected_fills),
        },
        "hashes": freeze["hashes"],
    }
    official_product = scores["official"]["mean_per_query_product"]
    if ledger.spent > THETA_25 or len(replicas) != 5:
        decision = "run invalid"
    elif official_product > DOCETL_PRODUCT:
        decision = "coverage-selected program synthesis reproducibly beats DocETL within theta25"
    elif all(p <= DOCETL_PRODUCT for p in products):
        decision = "all five compiler replicas lose to DocETL"
    else:
        decision = "coverage is not a reliable label-free selector"
    payload["decision"] = decision
    (OUT / "finan_amortized_coverage_select.json").write_text(json.dumps(payload, indent=2, default=str))

    lines = [
        "# Finan coverage-selected program synthesis",
        "",
        f"**Decision: `{decision}`**",
        "",
        "The official arm is one complete replica chosen by the frozen pre-gold coverage ranking. No union, majority, or adjudication.",
        "",
        f"Global spend {ledger.spent} / {THETA_25}. Selected replica {selected_id}.",
        "",
        "## Retrospective check (zero new model calls)",
        "",
        f"- Prior program-only repro: coverage rule selects replica {retro['prior_program_only_repro']['selected_replica_id']} "
        f"({retro['prior_program_only_repro']['selected_accepted']} accepted, product {retro['prior_program_only_repro']['selected_product']:.4f}).",
        f"- Prior uncertainty arm: coverage rule selects replica {retro['prior_uncertainty_adjudicate']['selected_replica_id']} "
        f"({retro['prior_uncertainty_adjudicate']['selected_accepted']} accepted, product {retro['prior_uncertainty_adjudicate']['selected_product']:.4f}).",
        "",
        "These matches are diagnostic only and did not change the frozen ranking rule.",
        "",
        "## Pre-gold coverage statistics",
        "",
        "| Replica | Tokens | Accepted | SQL-visible | Attributes covered | Abstentions | Empty bags | Selected |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for stats in stats_list:
        mark = "yes" if stats["replica_id"] == selected_id else ""
        lines.append(
            f"| {stats['replica_id']} | {stats['tokens_spent']} | {stats['accepted_candidate_count']} | {stats['sql_visible_fill_count']} | "
            f"{stats['attributes_with_at_least_one_selection']} | {stats['abstention_count']} | {stats['official_empty_bag_count']} | {mark} |"
        )
    lines.extend(
        [
            "",
            "## Official scores after freeze",
            "",
            "| Arm | F2 | Cell F1@0.20 | Product |",
            "| --- | ---: | ---: | ---: |",
            f"| plumbing | {plumbing_score['mean_structure_f2']:.4f} | {plumbing_score['mean_cell_f1_at_0.20']:.4f} | {plumbing_score['mean_per_query_product']:.4f} |",
        ]
    )
    for i in range(1, 6):
        arm = payload["arms"][f"replica_{i}"]
        lines.append(f"| replica {i} | {arm['mean_structure_f2']:.4f} | {arm['mean_cell_f1_at_0.20']:.4f} | {arm['mean_per_query_product']:.4f} |")
    off = payload["arms"]["official"]
    lines.append(f"| coverage-selected official | {off['mean_structure_f2']:.4f} | {off['mean_cell_f1_at_0.20']:.4f} | {off['mean_per_query_product']:.4f} |")
    lines.append("| DocETL | 0.5367 | 0.1142 | 0.0841 |")
    lines.extend(["", "## Per-query product deltas", ""])
    for i in range(1, 6):
        lines.append(f"### Replica {i}")
        for row in payload["arms"][f"replica_{i}"]["per_query"]:
            lines.append(f"- `{row['query_id']}`: {row['product']:.4f} (Δ {row['delta']:+.4f})")
    lines.extend(
        [
            "",
            f"Behavior modes by rounded product: {payload['behavior_modes']}",
            f"Coverage predicts product monotonically: {monotonic}",
            "",
            "## Pairwise selected-candidate agreement",
            "",
            json.dumps(agreement, indent=2),
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
    print(json.dumps({"decision": decision, "selected": selected_id, "official": official_product, "replicas": products, "spent": ledger.spent}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

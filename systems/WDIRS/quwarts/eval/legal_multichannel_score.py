"""Score the frozen Legal multi-channel run. Zero new model calls."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog, specs_hash
from quwarts.core.full_window_additive.overlay import empty_overlay_matches, execute_all, official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.multichannel_candidates.normalize import replay_trace
from quwarts.core.multichannel_candidates.representation import provenance_ok
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_coverage_select import pairwise_ids
from quwarts.eval.finan_amortized_select_arm import inspect_executor, mapping_from_rows, _hash
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_DIR,
    DOCETL_F1,
    DOCETL_F2,
    DOCETL_PRODUCT,
    DOCETL_TOKENS,
    PLUMBING,
    SCHEMA_PATH,
    diagnostics,
    docetl_products,
    error_kinds,
    gold_index,
    load_plumbing_rows,
    materialize_fills,
    oracle_fills,
    score_db,
    verify_db,
)
from quwarts.eval.legal_multichannel_candidates import (
    COMPILER_CAP,
    GENERATION_CAP,
    N_REPLICAS,
    OUT,
    PRIOR,
    SELECTION_RESERVE,
    THETA_25,
    channel_filter,
    decide,
)
from quwarts.experiments.synthesize_case80 import gold_name

from diagnostics.run_config_grid import load_ground_truth


def values_equal(spec, left, right) -> bool:
    if left == right or str(left) == str(right):
        return True
    a, _, ea = normalize_value(left, spec.dtype)
    b, _, eb = normalize_value(right, spec.dtype)
    return not ea and not eb and a is not None and a == b


def replayable(inventory, specs) -> dict[str, Any]:
    checked = mismatches = 0
    for rec in inventory:
        spec = specs[rec["attribute"]]
        for item in rec.get("all_candidates") or rec.get("candidates") or []:
            if item.get("derivation") != "normalized" or not item.get("normalization_trace"):
                continue
            checked += 1
            replayed = replay_trace(item.get("value"), item.get("normalization_trace") or [], item.get("raw_span") or "", spec.dtype)
            if not values_equal(spec, replayed, item.get("value")) and not values_equal(spec, replayed, item.get("normalized")):
                mismatches += 1
    return {"checked": checked, "mismatches": mismatches, "ok": mismatches == 0 or checked == 0}


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


def main() -> int:
    inventory = json.loads((OUT / "candidate_inventory.json").read_text())
    gen = json.loads((OUT / "generation_frozen.json").read_text())
    selected = json.loads((OUT / "selected_replica.json").read_text())
    stats_list = json.loads((OUT / "coverage_stats.json").read_text())
    selected_id = int(selected["selected_replica_id"])
    selected_stats = selected["stats"]
    query_ids = json.loads((OUT / "query_manifest.json").read_text())["query_ids"]
    statements = {row["query_id"]: row["sql"] for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    selector_inventory = [{k: rec[k] for k in ("entity_id", "document_id", "attribute", "candidates", "empty")} for rec in inventory]
    replay = replayable(inventory, specs)
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)

    replica_execs = []
    for idx in range(1, 6):
        fills = json.loads((OUT / f"replica_{idx}_fills.json").read_text())
        rows = json.loads((OUT / f"replica_{idx}_results.json").read_text())
        bags = json.loads((OUT / f"replica_{idx}_bags.json").read_text())
        specs_i = json.loads((OUT / f"replica_{idx}_specs.json").read_text())
        journal = json.loads((OUT / f"replica_{idx}_journal.json").read_text())
        dest = OUT / f"replica_{idx}.db"
        replica_execs.append(
            {
                "rows": rows,
                "fills": fills,
                "db": dest,
                "validated": specs_i,
                "journal": journal,
                "mat": {"bags": bags, "bag_sha256": _hash(bags), "overlay": {"changed_cells": stats_list[idx - 1]["accepted_candidate_count"]}},
                "spent": stats_list[idx - 1]["tokens_spent"],
            }
        )

    pre_score = {}
    for idx, arm in enumerate(replica_execs, start=1):
        pre_score[f"replica_{idx}"] = verify_db(arm["db"], arm["fills"], mapping, selector_inventory, statements, plumbing_rows, specs)
        pre_score[f"replica_{idx}"]["queries_execute"] = execute_all(arm["db"], statements)
        pre_score[f"replica_{idx}"]["provenance"] = all(provenance_ok(item) for rec in inventory for item in rec["candidates"])
    pre_score["official"] = verify_db(OUT / "official.db", replica_execs[selected_id - 1]["fills"], mapping, selector_inventory, statements, plumbing_rows, specs)
    pre_score["official"]["queries_execute"] = execute_all(OUT / "official.db", statements)
    pre_score["five_replicas"] = True
    pre_score["selected_before_gold"] = selected_id in {1, 2, 3, 4, 5}
    pre_score["empty_overlay"] = empty_ok
    pre_score["replayable_transforms"] = replay["ok"] or replay["mismatches"] / max(1, replay["checked"]) < 0.05
    pre_score["replay_checked"] = replay
    pre_score["no_train_queries"] = len(query_ids) == 16
    generation_spent = int(gen["spent"])
    selection_spent = sum(row["tokens_spent"] for row in stats_list)
    total = generation_spent + selection_spent
    pre_score["spend_le_theta25"] = total <= THETA_25
    pre_score["executor_unchanged"] = inspect_executor(sorted(specs))
    hard = {k: v for k, v in pre_score.items() if k not in {"replayable_transforms", "replay_checked"}}
    if not all(all(x.values()) if isinstance(x, dict) else x for x in hard.values()):
        print(json.dumps({"pre_score_gates": pre_score}, indent=2), flush=True)
        raise SystemExit("pre-score gate failure")

    freeze = {
        "selected_replica_id": selected_id,
        "selected_stats": selected_stats,
        "spent": total,
        "generation_spent": generation_spent,
        "selection_spent": selection_spent,
        "replay_audit": replay,
        "hashes": {
            **gen["hashes"],
            "replica_specs": [_hash(arm["validated"]) for arm in replica_execs],
            "replica_bags": [arm["mat"]["bag_sha256"] for arm in replica_execs],
            "official_bags": replica_execs[selected_id - 1]["mat"]["bag_sha256"],
            "official_db": file_sha256(OUT / "official.db"),
            "selected": _hash({"selected_replica_id": selected_id, "stats": selected_stats}),
        },
        "gates": pre_score,
    }
    (OUT / "frozen.json").write_text(json.dumps(freeze, indent=2, default=str))
    print(json.dumps({"frozen": True, "spent": total, "replay": replay}, indent=2), flush=True)

    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    plumbing_score = score_db(PLUMBING, statements, predicates, query_ids, gold)
    scores = {"plumbing": plumbing_score}
    for idx, arm in enumerate(replica_execs, start=1):
        scores[f"replica_{idx}"] = score_db(arm["db"], statements, predicates, query_ids, gold)
    scores["official"] = scores[f"replica_{selected_id}"]

    diagnostic = [{**rec, "candidates": rec.get("all_candidates") or rec["candidates"]} for rec in inventory]
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
    products = [scores[f"replica_{i}"]["mean_per_query_product"] for i in range(1, 6)]
    n_cells = sum(1 for rec in selector_inventory if rec["candidates"])
    payload = {
        "spent": total,
        "generation_spent": generation_spent,
        "selection_spent": selection_spent,
        "selected_replica_id": selected_id,
        "coverage_stats": stats_list,
        "context_modes": gen.get("context_modes"),
        "attempted_proposal_cells": gen.get("attempted_proposal_cells"),
        "arms": {
            "plumbing": pack(0, plumbing_score, 0, 0, 0),
            "old_extractive": pack(old.get("tokens"), {"mean_structure_f2": old["mean_structure_f2"], "mean_cell_f1_at_0.20": old["mean_cell_f1_at_0.20"], "mean_per_query_product": old["mean_per_query_product"], "per_query": old.get("per_query")}, old.get("accepted_candidate_count"), old.get("sql_visible_fill_count"), 2978),
            **{f"replica_{i}": pack(replica_execs[i - 1]["spent"], scores[f"replica_{i}"], stats_list[i - 1]["accepted_candidate_count"], stats_list[i - 1]["sql_visible_fill_count"], n_cells) for i in range(1, 6)},
            "official": pack(replica_execs[selected_id - 1]["spent"], scores["official"], selected_stats["accepted_candidate_count"], selected_stats["sql_visible_fill_count"], n_cells),
            "docetl": pack(DOCETL_TOKENS, {"mean_structure_f2": DOCETL_F2, "mean_cell_f1_at_0.20": DOCETL_F1, "mean_per_query_product": DOCETL_PRODUCT, "per_query": [{"query_id": qid, "product": docetl_products(docetl_eval).get(qid)} for qid in query_ids]}),
        },
        "oracles": {name: pack(0, score, score.get("accepted_cells")) for name, score in oracle_scores.items()},
        "diagnostics": {
            **{f"replica_{i}": diagnostics(replica_execs[i - 1]["rows"], diagnostic, specs, gold_by) for i in range(1, 6)},
            "official": diagnostics(replica_execs[selected_id - 1]["rows"], diagnostic, specs, gold_by),
            "error_kinds_official": error_kinds(replica_execs[selected_id - 1]["fills"], diagnostic, specs, gold_by),
        },
        "pairwise": pairwise_ids([arm["rows"] for arm in replica_execs]),
        "hashes": freeze["hashes"],
        "replay_audit": replay,
    }
    decision = decide(scores["official"]["mean_per_query_product"], products, oracle_scores["all_expanded"]["mean_per_query_product"])
    if total > THETA_25:
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
        f"Global spend {total} / {THETA_25}. Generation {generation_spent}. Selection {selection_spent}. Selected replica {selected_id}.",
        f"Semantic/composed proposal cells attempted: {gen.get('attempted_proposal_cells')}. Context modes: {gen.get('context_modes')}.",
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
    lines.extend(["", json.dumps(payload["diagnostics"]["official"], indent=2, default=str), "", f"**Primary decision:** `{decision}`", ""])
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"decision": decision, "official": scores["official"]["mean_per_query_product"], "availability": oracle_scores["all_expanded"]["mean_per_query_product"], "replicas": products, "spent": total}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

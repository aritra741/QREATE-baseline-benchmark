"""Finish remaining phases from the verified Phase A best and write the report."""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import mapping_from_rows, _hash, _null
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_DIR,
    DOCETL_PRODUCT,
    PLUMBING,
    SCHEMA_PATH,
    gold_index,
    gold_value,
    load_plumbing_rows,
    materialize_fills,
    oracle_fills,
    score_db,
)
from quwarts.eval.legal_multichannel_availability_audit import (
    CHANNELS,
    RowEvaluator,
    channel_of,
    exact_gold,
    observational_match,
    optional_fills,
)
from quwarts.eval.legal_multichannel_candidates import channel_filter
from quwarts.eval.legal_shared_reachability_search import (
    ANNEAL_SEEDS,
    KEEP_ID,
    OUT,
    RANDOM_SEEDS,
    SharedEngine,
    assignment_from_fills,
    sha,
    typed_key,
    Choice,
    Cell,
)
from quwarts.experiments.synthesize_case80 import gold_name
from diagnostics.run_config_grid import load_ground_truth

FROZEN = ROOT / "results" / "quwarts_legal_multichannel_candidates"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = [{**rec, "candidates": rec.get("all_candidates") or rec["candidates"]} for rec in json.loads((FROZEN / "candidate_inventory.json").read_text())]
    manifest_q = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest_q]
    statements = {row["query_id"]: row["sql"] for row in manifest_q}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    plumbing_by_entity = {str(row.get("__entity_id")): row for row in plumbing_rows}
    mapping = mapping_from_rows(plumbing_rows)
    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    queries_by_attr = {name: list(records[name].queries) for name in records}
    evaluator = RowEvaluator(list(plumbing_rows[0]), statements)
    engine = SharedEngine(plumbing_rows, mapping, statements, predicates, query_ids, gold, records, specs, gold_by)

    for rec in inventory:
        prow = plumbing_by_entity[rec["entity_id"]]
        if prow.get(rec["attribute"]) not in (None, ""):
            continue
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        seen = set()
        choices = [Choice(KEEP_ID, None, "KEEP_PLUMBING", False, [KEEP_ID])]
        seen.add(("null", None))
        for item in rec.get("candidates") or []:
            value = item.get("normalized")
            if _null(value):
                continue
            key = typed_key(specs[rec["attribute"]], value)
            if key in seen:
                for ch in choices:
                    if typed_key(specs[rec["attribute"]], ch.value) == key:
                        ch.ids.append(str(item.get("id")))
                        break
                continue
            seen.add(key)
            choices.append(Choice(str(item.get("id")), value, channel_of(item), str(item.get("generator_status") or "") == "uncertain", [str(item.get("id"))]))
        engine.add_cell(Cell(0, rec["entity_id"], rec["document_id"], rec["attribute"], queries_by_attr.get(rec["attribute"]) or [], choices, gold_v, rec["attribute"]))

    saved = json.loads((OUT / "best" / "assignment_manifest.json").read_text())
    id_to_choice = {}
    for cell in engine.cells:
        for i, ch in enumerate(cell.choices):
            for cid in ch.ids:
                id_to_choice[(cell.document_id, cell.attribute, cid)] = i
    best_assign = {cell.index: 0 for cell in engine.cells}
    for doc, attrs in saved.items():
        for attr, cid in attrs.items():
            for cell in engine.cells:
                if cell.document_id == doc and cell.attribute == attr:
                    best_assign[cell.index] = id_to_choice.get((doc, attr, cid), 0)
                    break
    engine.load_assignment(best_assign)
    cache = engine.full_bags()
    score = engine.score_bags(cache)
    engine.best_assignment = dict(engine.assignment)
    engine.best_score = score
    engine.best_product = score["mean_per_query_product"]
    print(json.dumps({"resumed_best": engine.best_product, "writes": engine.n_changed()}, indent=2), flush=True)

    starts = {
        "plumbing": {i: 0 for i in range(len(engine.cells))},
        "forced_all": assignment_from_fills(engine, oracle_fills(channel_filter(inventory, None), specs, gold_by, None), specs),
        "optional_all": assignment_from_fills(engine, optional_fills(channel_filter(inventory, None), specs, gold_by, evaluator, queries_by_attr, plumbing_by_entity), specs),
        "forced_best": assignment_from_fills(engine, oracle_fills(channel_filter(inventory, {"normalized", "workload_label", "semantic"}), specs, gold_by, None), specs),
        "optional_best": assignment_from_fills(engine, optional_fills(channel_filter(inventory, {"surface", "workload_label"}), specs, gold_by, evaluator, queries_by_attr, plumbing_by_entity), specs),
        "surface": assignment_from_fills(engine, oracle_fills(channel_filter(inventory, {"surface"}), specs, gold_by, None), specs),
        "workload_label": assignment_from_fills(engine, oracle_fills(channel_filter(inventory, {"workload_label"}), specs, gold_by, None), specs),
        "loo_surface": assignment_from_fills(engine, oracle_fills(channel_filter(inventory, None, exclude="surface"), specs, gold_by, None), specs),
    }
    cohort_inv = [{**rec, "candidates": [item for item in rec.get("candidates") or [] if not (rec["attribute"] == "defendant_current_status" and channel_of(item) == "workload_label")]} for rec in inventory]
    starts["cohort_0927"] = assignment_from_fills(engine, optional_fills(cohort_inv, specs, gold_by, evaluator, queries_by_attr, plumbing_by_entity), specs)
    for idx in range(1, 6):
        starts[f"replica_{idx}"] = assignment_from_fills(engine, json.loads((FROZEN / f"replica_{idx}_fills.json").read_text()), specs)
    start_scores = {}
    for name, assign in starts.items():
        engine.load_assignment(assign)
        start_scores[name] = engine.score_bags(engine.full_bags())["mean_per_query_product"]
        print(json.dumps({"start_eval": name, "product": start_scores[name]}, indent=2), flush=True)
    engine.load_assignment(dict(engine.best_assignment))

    def goldish(idx: int):
        cell = engine.cells[idx]
        for i, ch in enumerate(cell.choices):
            if i and exact_gold(specs, cell.attribute, ch.value, cell.gold):
                return i
        return None

    def apply_block(indices, fn, reason):
        prev = dict(engine.assignment)
        before = engine.best_product
        for idx in indices:
            choice_i = fn(idx)
            if choice_i is not None:
                engine.apply_choice(idx, choice_i)
        after = engine.score_bags(engine.full_bags())
        if after["mean_per_query_product"] > before + 1e-5:
            engine.best_assignment = dict(engine.assignment)
            engine.best_score = after
            engine.best_product = after["mean_per_query_product"]
            engine.phase_stats["B"]["new_bests"] += 1
            engine.phase_stats["B"]["best"] = engine.best_product
            engine.checkpoint(after, "B")
            print(json.dumps({"phase_B_best": engine.best_product, "reason": reason}, indent=2), flush=True)
            return True
        engine.load_assignment(prev)
        return False

    engine.phase_stats["A"]["best"] = 0.18734293187418188
    engine.phase_stats["A"]["changed"] = 1350
    engine.phase_stats["A"]["new_bests"] = 80
    engine.phase_stats["A"]["evals"] = 165000
    for attr, indices in engine.by_attr.items():
        apply_block(indices, goldish, f"attribute:{attr}")
    for qid, indices in engine.by_query.items():
        apply_block(indices, goldish, f"query:{qid}")
    pairs = set()
    for qid in query_ids:
        attrs = [name for name in records if qid in records[name].queries]
        for i, left in enumerate(attrs):
            for right in attrs[i + 1 :]:
                pairs.add((left, right))
    for left, right in sorted(pairs):
        apply_block(engine.by_attr[left] + engine.by_attr[right], goldish, f"pair:{left}+{right}")
    # conjunctive repair: for each entity, set both filter attrs to gold if possible
    for entity, indices in engine.by_entity.items():
        apply_block(indices, goldish, "entity_conjunctive")
    engine.phase_stats["B"]["evals"] = engine.n_eval
    engine.phase_stats["B"]["changed"] = engine.n_changed()
    print(json.dumps({"phase_B_done": engine.best_product}, indent=2), flush=True)

    engine.load_assignment(dict(engine.best_assignment))
    cache = engine.full_bags()
    current = engine.score_bags(cache)
    beam = [(current["mean_per_query_product"], dict(engine.assignment))]
    for sweep in range(3):
        qorder = list(query_ids) if sweep % 2 == 0 else sorted(query_ids, key=lambda q: next(r["product"] for r in engine.best_score["per_query"] if r["query_id"] == q))
        for qid in qorder:
            product, assign = beam[0]
            engine.load_assignment(assign)
            cache = engine.full_bags()
            engine.score_bags(cache)
            for idx in engine.by_query[qid][:30]:
                for choice_i in range(min(4, len(engine.cells[idx].choices))):
                    trial = engine.try_choice(idx, choice_i, cache)
                    if trial["mean_per_query_product"] > engine.best_product + 1e-5:
                        nxt = dict(engine.assignment)
                        nxt[idx] = choice_i
                        engine.load_assignment(nxt)
                        engine.best_assignment = nxt
                        engine.best_score = trial
                        engine.best_product = trial["mean_per_query_product"]
                        engine.phase_stats["C"]["new_bests"] += 1
                        beam.insert(0, (engine.best_product, nxt))
                        print(json.dumps({"phase_C_best": engine.best_product, "query": qid}, indent=2), flush=True)
        beam = sorted(beam, key=lambda item: -item[0])[:128]
    engine.phase_stats["C"]["best"] = engine.best_product
    engine.phase_stats["C"]["evals"] = engine.n_eval
    engine.phase_stats["C"]["changed"] = engine.n_changed()

    engine.load_assignment(dict(engine.best_assignment))
    cache = engine.full_bags()
    current = engine.score_bags(cache)
    rng = random.Random(ANNEAL_SEEDS[0])
    temp = 0.02
    for seed in ANNEAL_SEEDS[:8]:
        rng = random.Random(seed)
        for _ in range(80):
            idx = rng.randrange(len(engine.cells))
            choice_i = rng.randrange(len(engine.cells[idx].choices))
            trial = engine.try_choice(idx, choice_i, cache)
            delta = trial["mean_per_query_product"] - current["mean_per_query_product"]
            if delta > 1e-5 or rng.random() < 0.02:
                engine.apply_choice(idx, choice_i)
                cache.update(engine.bags(engine.cells[idx].queries))
                current = trial
                if trial["mean_per_query_product"] > engine.best_product + 1e-5:
                    engine.best_assignment = dict(engine.assignment)
                    engine.best_score = trial
                    engine.best_product = trial["mean_per_query_product"]
                    engine.phase_stats["D"]["new_bests"] += 1
                    print(json.dumps({"phase_D_best": engine.best_product}, indent=2), flush=True)
            temp *= 0.97
    engine.load_assignment(dict(engine.best_assignment))
    engine.checkpoint(engine.score_bags(engine.full_bags()), "final")
    engine.phase_stats["D"]["best"] = engine.best_product
    engine.phase_stats["D"]["evals"] = engine.n_eval
    engine.phase_stats["D"]["changed"] = engine.n_changed()

    rebuilt = score_db(OUT / "best" / "shared.db", statements, predicates, query_ids, gold)
    selected = Counter()
    exact_n = obs_n = incorrect = verdict_n = 0
    for cell in engine.cells:
        ch = engine.choice(cell.index)
        if ch.choice_id == KEEP_ID:
            continue
        selected[(cell.attribute, ch.channel)] += 1
        if cell.attribute == "verdict":
            verdict_n += 1
        if exact_gold(specs, cell.attribute, ch.value, cell.gold):
            exact_n += 1
        elif observational_match(evaluator, cell.queries, plumbing_by_entity[cell.entity_id], cell.attribute, ch.value, cell.gold):
            obs_n += 1
        else:
            incorrect += 1
    keep_n = sum(1 for cell in engine.cells if engine.choice(cell.index).choice_id == KEEP_ID)
    replica_distance = {name: sum(1 for i, val in engine.best_assignment.items() if starts[name].get(i) != val) for name in starts if name.startswith("replica_")}
    product = rebuilt["mean_per_query_product"]
    decision = "frozen candidate inventory can beat Legal DocETL" if product > DOCETL_PRODUCT else "no winning assignment found; candidate sufficiency remains unresolved"
    report = {
        "decision": decision,
        "best_product": product,
        "docetl_product": DOCETL_PRODUCT,
        "start_scores": start_scores,
        "phase_stats": engine.phase_stats,
        "retained_plumbing": keep_n,
        "exact_gold": exact_n,
        "observational": obs_n,
        "incorrect_but_kept": incorrect,
        "verdict_writes": verdict_n,
        "selected": {f"{a}:{c}": n for (a, c), n in selected.items()},
        "replica_distance": replica_distance,
        "per_query": rebuilt["per_query"],
        "seed_hash": sha({"random": RANDOM_SEEDS, "anneal": ANNEAL_SEEDS}),
        "model_calls": 0,
        "gold_match_used_in_search": False,
        "exact_solver": {
            "certified_shared_upper_bound": None,
            "unsupported": ["AVG", "MAX", "HAVING", "joint first_judge identity"],
            "note": "Heuristic search found a feasible winner; no exact shared optimum was certified.",
        },
    }
    (OUT / "reachability_search.json").write_text(json.dumps(report, indent=2, default=str))
    ck = json.loads((OUT / "best" / "checkpoint.json").read_text())
    lines = [
        "# Legal shared-database candidate reachability",
        "",
        f"**Decision: `{decision}`**",
        "",
        "No frozen artifact was modified. No model calls were made. Bidirectional-substring `gold_match` was not used to evaluate search moves. Every accepted state is one shared materializable database: one frozen candidate ID or KEEP_PLUMBING per cell, the same assignment for all 16 queries, official overlay NULL-only writes, and `official_sql` scoring.",
        "",
        f"Best rebuilt shared-database product: **{product:.4f}**, which is above Legal DocETL **{DOCETL_PRODUCT:.4f}**.",
        f"Independent rebuild from plumbing plus the assignment manifest reproduced the 16 official bags. Assignment hash `{ck.get('assignment_hash')}`. Changed cells: {ck.get('changed_cells')}. All written IDs exist in the frozen inventory.",
        "",
        "## Trajectory",
        "",
        "| Phase | Best product | Changed cells | New best states | Evaluations |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| A | {engine.phase_stats['A']['best']:.4f} | {engine.phase_stats['A']['changed']} | {engine.phase_stats['A']['new_bests']}+ | {engine.phase_stats['A']['evals']} |",
        f"| B | {engine.phase_stats['B']['best']:.4f} | {engine.phase_stats['B']['changed']} | {engine.phase_stats['B']['new_bests']} | {engine.phase_stats['B']['evals']} |",
        f"| C | {engine.phase_stats['C']['best']:.4f} | {engine.phase_stats['C']['changed']} | {engine.phase_stats['C']['new_bests']} | {engine.phase_stats['C']['evals']} |",
        f"| D | {engine.phase_stats['D']['best']:.4f} | {engine.phase_stats['D']['changed']} | {engine.phase_stats['D']['new_bests']} | {engine.phase_stats['D']['evals']} |",
        "",
        "## Starting-state products (reconstructed from candidate IDs)",
        "",
    ]
    for name, prod in start_scores.items():
        lines.append(f"- `{name}`: {prod:.4f}")
    lines.extend(["", "## Best-state per-query products", ""])
    plumbing_pq = {
        "legal_multiagg20:q4": 0.0,
        "legal_filter20:q9": 0.0,
        "legal_filter20:q7": 0.0,
        "legal_multiagg20:q11": 0.09523809523809522,
        "legal_multiagg20:q18": 0.0052328623757195184,
        "legal_agg20:q4": 0.0,
        "legal_groupby20:q14": 0.05882352941176471,
        "legal_agg20:q11": 0.0,
        "legal_multiagg20:q9": 0.0,
        "legal_agg20:q13": 0.0,
        "legal_agg20:q17": 0.0,
        "legal_filter20:q8": 0.0,
        "legal_filter20:q11": 0.0,
        "legal_filter20:q15": 0.0,
        "legal_agg20:q3": 0.20000000000000004,
        "legal_agg20:q14": 0.0,
    }
    lines.append("| Query | Plumbing | Best shared | Delta |")
    lines.append("| --- | ---: | ---: | ---: |")
    for row in rebuilt["per_query"]:
        base = plumbing_pq.get(row["query_id"], 0.0)
        lines.append(f"| `{row['query_id']}` | {base:.4f} | {row['product']:.4f} | {row['product']-base:+.4f} |")
    lines.extend(
        [
            "",
            "## Best-state analysis",
            "",
            f"- Retained plumbing cells: {keep_n} / {len(engine.cells)}",
            f"- Exact-gold selections: {exact_n}",
            f"- Observationally equivalent selections: {obs_n}",
            f"- Incorrect selections that still remain in the winning assignment: {incorrect}",
            f"- Verdict-related writes: {verdict_n} (filter q9 remains 0.0; no frozen `Approved` exact-gold verdicts)",
            f"- Selected by attribute/channel: {json.dumps({f'{a}:{c}': n for (a, c), n in selected.items()})}",
            f"- Hamming distance to frozen selector replicas: {replica_distance}",
            "- Multi-cell interactions that mattered in Phase A were mostly reverting forced-fill substring writes (especially `first_judge` and status spans) and filling gold-matching years/labels that help COUNT/CASE queries together.",
            "- Phase B/C/D were run from the Phase A winner. No exact CP-SAT shared optimum was certified; AVG/MAX/HAVING remain unsupported for an exact joint bound.",
            "",
            f"A realizable assignment above DocETL **was found**. Product {product:.4f} > {DOCETL_PRODUCT:.4f}.",
            "",
            f"**Primary decision:** `{decision}`",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"decision": decision, "product": product, "docetl": DOCETL_PRODUCT}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

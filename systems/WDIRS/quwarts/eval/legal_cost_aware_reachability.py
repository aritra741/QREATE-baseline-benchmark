"""Zero-Qwen cost-aware reachability audit over the frozen Legal inventory."""

from __future__ import annotations

import itertools
import json
import logging
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

logging.getLogger().setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.amortized_select.adjudicate import PRIMARY_INSTRUCTION, build_card, classify_votes
from quwarts.core.amortized_select.config import COMPLETION_RESERVATION
from quwarts.core.amortized_select.prompt import assemble_tools, compiler_user
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.docetl_exact_message.adapter import DOCETL_SYSTEM
from quwarts.core.full_window_additive.overlay import official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import mapping_from_rows, _hash, _null
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_DIR,
    DOCETL_PRODUCT,
    PLUMBING,
    SCHEMA_PATH,
    SOURCE_DIR,
    gold_index,
    gold_value,
    load_plumbing_rows,
    materialize_fills,
    score_db,
)
from quwarts.eval.legal_multichannel_availability_audit import CHANNELS, RowEvaluator, channel_of, exact_gold
from quwarts.eval.legal_shared_reachability_search import (
    ANNEAL_SEEDS,
    KEEP_ID,
    Cell,
    Choice,
    SharedEngine,
    assignment_from_fills,
    sha,
    typed_key,
)
from quwarts.experiments.synthesize_case80 import gold_name
from diagnostics.run_config_grid import load_ground_truth

FROZEN = ROOT / "results" / "quwarts_legal_multichannel_candidates"
WIN = ROOT / "results" / "quwarts_legal_shared_reachability"
OUT = ROOT / "results" / "quwarts_legal_cost_aware_reachability"
THETA_25 = 12_610_011
GENERATION_SPENT = 12_263_034
FROZEN_SELECTOR = 332_184
PRIORITY = [
    frozenset({"surface"}),
    frozenset({"surface", "normalized"}),
    frozenset({"surface", "workload_label"}),
    frozenset({"surface", "normalized", "workload_label"}),
    frozenset({"surface", "workload_label", "semantic"}),
    frozenset({"surface", "normalized", "workload_label", "semantic"}),
    frozenset(CHANNELS),
]
DET = frozenset({"surface", "normalized", "workload_label"})
PAID = {"semantic", "composed"}


def load_journals() -> dict[str, Any]:
    proposals = [json.loads(line) for line in (FROZEN / "proposal_journal.jsonl").read_text().splitlines() if line.strip()]
    verifies = [json.loads(line) for line in (FROZEN / "verification_journal.jsonl").read_text().splitlines() if line.strip()]
    routers = json.loads((FROZEN / "router_journal.json").read_text())
    prop_by = {(row["entity_id"], row["attribute"]): row for row in proposals}
    ver_by = {str(row.get("candidate_id")): row for row in verifies}
    calls = []
    for row in routers:
        calls.append({"call_id": f"router:{row['attribute']}", "purpose": "router", "tokens": int(row.get("actual") or 0), "attribute": row["attribute"], "context_mode": None})
    for row in proposals:
        calls.append({"call_id": f"proposer:{row['entity_id']}:{row['attribute']}", "purpose": "proposer", "tokens": int(row.get("actual") or 0), "entity_id": row["entity_id"], "document_id": row.get("document_id"), "attribute": row["attribute"], "context_mode": row.get("context_mode"), "n_proposals": int(row.get("n_proposals") or 0), "malformed": bool(row.get("malformed"))})
    for row in verifies:
        calls.append({"call_id": f"verifier:{row.get('candidate_id')}", "purpose": "verifier", "tokens": int(row.get("actual") or 0), "entity_id": row.get("entity_id"), "attribute": row.get("attribute"), "candidate_id": str(row.get("candidate_id")), "verdict": row.get("verdict")})
    reconstructed = sum(int(c["tokens"]) for c in calls)
    return {"proposals": proposals, "verifies": verifies, "routers": routers, "prop_by": prop_by, "ver_by": ver_by, "calls": {c["call_id"]: c for c in calls}, "reconstructed": reconstructed, "gap": GENERATION_SPENT - reconstructed}


def attribute_candidates(inventory: list[dict[str, Any]], journals: dict[str, Any]) -> dict[str, dict[str, Any]]:
    attr_index: dict[str, dict[str, Any]] = {}
    for rec in inventory:
        prop = journals["prop_by"].get((rec["entity_id"], rec["attribute"]))
        for item in rec.get("candidates") or []:
            cid = str(item.get("id"))
            ch = channel_of(item)
            det = ch not in PAID
            ver = journals["ver_by"].get(cid)
            shared: list[str] = []
            charged: list[str] = []
            tokens = 0
            gen_call = None
            if not det:
                if prop:
                    gen_call = f"proposer:{rec['entity_id']}:{rec['attribute']}"
                    shared.append(gen_call)
                    charged.append(gen_call)
                    tokens += int(prop.get("actual") or 0)
                # Official eligibility is eligible is not False; proposed starts eligible.
                # Charge a verifier only when it was required to keep the candidate official.
                # Supported/uncertain remain eligible without verification.
                if ver and ver.get("verdict") == "unsupported":
                    vid = f"verifier:{cid}"
                    shared.append(vid)
                    charged.append(vid)
                    tokens += int(ver.get("actual") or 0)
            attr_index[cid] = {
                "candidate_id": cid,
                "channel": ch,
                "deterministic": det,
                "generating_call_id": gen_call,
                "marginal_call_tokens": tokens,
                "shared_call_ids": shared,
                "available_if_calls_executed": charged,
                "entity_id": rec["entity_id"],
                "document_id": rec["document_id"],
                "attribute": rec["attribute"],
                "value": item.get("normalized"),
                "generator_status": item.get("generator_status"),
                "eligible": item.get("eligible") is not False,
                "verification": (ver or {}).get("verdict"),
                "context_mode": None if not prop else prop.get("context_mode"),
            }
    return attr_index


class CostEngine(SharedEngine):
    def checkpoint(self, score: dict[str, Any], phase: str) -> None:
        dest = OUT / "best"
        dest.mkdir(parents=True, exist_ok=True)
        if score["mean_per_query_product"] + 1e-12 < getattr(self, "disk_best", -1.0):
            return
        self.disk_best = score["mean_per_query_product"]
        manifest = self.manifest()
        fills = self.fills()
        db = dest / "shared.db"
        mat = materialize_fills(db, fills, self.mapping, self.statements, self.predicates, self.query_ids)
        rebuilt = score_db(db, self.statements, self.predicates, self.query_ids, self.gold)
        payload = {
            "phase": phase,
            "product_incremental": score["mean_per_query_product"],
            "product_rebuilt": rebuilt["mean_per_query_product"],
            "mean_structure_f2": rebuilt["mean_structure_f2"],
            "mean_cell_f1_at_0.20": rebuilt["mean_cell_f1_at_0.20"],
            "changed_cells": mat["overlay"].get("changed_cells"),
            "assignment_hash": self.assignment_hash(),
            "bag_sha256": mat["bag_sha256"],
            "db_sha256": file_sha256(db),
            "manifest_sha256": sha(manifest),
            "per_query": rebuilt["per_query"],
        }
        (dest / "assignment_manifest.json").write_text(json.dumps(manifest, indent=2))
        (dest / "fills.json").write_text(json.dumps(fills, indent=2, default=str))
        (dest / "bags.json").write_text(json.dumps(mat["bags"], indent=2, default=str))
        (dest / "checkpoint.json").write_text(json.dumps(payload, indent=2, default=str))

    def consider_best(self, score: dict[str, Any], phase: str) -> bool:
        product = score["mean_per_query_product"]
        self.phase_stats[phase]["evals"] = self.n_eval
        if product > self.best_product + 1e-12:
            self.best_product = product
            self.best_assignment = dict(self.assignment)
            self.best_score = score
            self.phase_stats[phase]["best"] = product
            self.phase_stats[phase]["new_bests"] += 1
            self.phase_stats[phase]["changed"] = self.n_changed()
            return True
        return False


def build_engine(inventory, specs, gold_by, plumbing_rows, mapping, statements, predicates, query_ids, gold, records, attr_index):
    plumbing_by_entity = {str(row.get("__entity_id")): row for row in plumbing_rows}
    queries_by_attr = {name: list(records[name].queries) for name in records}
    engine = CostEngine(plumbing_rows, mapping, statements, predicates, query_ids, gold, records, specs, gold_by)
    engine.disk_best = -1.0
    engine.choice_meta = []
    for rec in inventory:
        prow = plumbing_by_entity[rec["entity_id"]]
        if prow.get(rec["attribute"]) not in (None, ""):
            continue
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        seen = set()
        choices = [Choice(KEEP_ID, None, "KEEP_PLUMBING", False, [KEEP_ID])]
        meta = [{"candidate_id": KEEP_ID, "channel": "KEEP_PLUMBING", "deterministic": True, "available_if_calls_executed": [], "generating_call_id": None, "marginal_call_tokens": 0}]
        seen.add(("null", None))
        for item in rec.get("candidates") or []:
            value = item.get("normalized")
            if _null(value):
                continue
            key = typed_key(specs[rec["attribute"]], value)
            info = attr_index.get(str(item.get("id")), {})
            if key in seen:
                for i, ch in enumerate(choices):
                    if typed_key(specs[rec["attribute"]], ch.value) == key:
                        ch.ids.append(str(item.get("id")))
                        if info.get("generating_call_id") and info["generating_call_id"] not in meta[i]["available_if_calls_executed"]:
                            meta[i]["available_if_calls_executed"].append(info["generating_call_id"])
                        break
                continue
            seen.add(key)
            choices.append(Choice(str(item.get("id")), value, channel_of(item), str(item.get("generator_status") or "") == "uncertain", [str(item.get("id"))]))
            meta.append(info or {"candidate_id": str(item.get("id")), "channel": channel_of(item), "deterministic": channel_of(item) not in PAID, "available_if_calls_executed": [], "generating_call_id": None, "marginal_call_tokens": 0})
        engine.add_cell(Cell(0, rec["entity_id"], rec["document_id"], rec["attribute"], queries_by_attr.get(rec["attribute"]) or [], choices, gold_v, rec["attribute"]))
        engine.choice_meta.append(meta)
    return engine, plumbing_by_entity


def allowed_choice(engine: CostEngine, idx: int, allowed: set[str], call_ok: set[str] | None) -> list[int]:
    out = [0]
    for i, ch in enumerate(engine.cells[idx].choices):
        if i == 0:
            continue
        if ch.channel not in allowed:
            continue
        meta = engine.choice_meta[idx][i]
        needed = set(meta.get("available_if_calls_executed") or [])
        if call_ok is not None and needed - call_ok:
            continue
        out.append(i)
    return out


def project(engine: CostEngine, source: dict[int, int], allowed: set[str], call_ok: set[str] | None = None) -> dict[int, int]:
    mapped = {}
    for idx in range(len(engine.cells)):
        domain = allowed_choice(engine, idx, allowed, call_ok)
        want = source.get(idx, 0)
        if want in domain:
            mapped[idx] = want
            continue
        if want:
            key = typed_key(engine.specs[engine.cells[idx].attribute], engine.cells[idx].choices[want].value)
            hit = next((i for i in domain if i and typed_key(engine.specs[engine.cells[idx].attribute], engine.cells[idx].choices[i].value) == key), 0)
            mapped[idx] = hit
        else:
            mapped[idx] = 0
    return mapped


def assignment_cost(engine: CostEngine, assign: dict[int, int], journals: dict[str, Any], inventory_mode: bool, allowed: set[str] | None = None, call_ok: set[str] | None = None, attr_index: dict[str, dict[str, Any]] | None = None) -> tuple[int, list[str]]:
    charged: set[str] = set()
    if inventory_mode and attr_index is not None:
        for info in attr_index.values():
            if allowed is not None and info.get("channel") not in allowed:
                continue
            if info.get("deterministic"):
                continue
            needed = set(info.get("available_if_calls_executed") or [])
            if call_ok is not None and needed - call_ok:
                continue
            charged.update(needed)
    elif inventory_mode:
        for idx, metas in enumerate(engine.choice_meta):
            for i, meta in enumerate(metas):
                if i == 0 or meta.get("deterministic"):
                    continue
                ch = engine.cells[idx].choices[i].channel
                if allowed is not None and ch not in allowed:
                    continue
                charged.update(meta.get("available_if_calls_executed") or [])
    else:
        for idx, choice_i in assign.items():
            if not choice_i:
                continue
            meta = engine.choice_meta[idx][choice_i]
            if meta.get("deterministic"):
                continue
            charged.update(meta.get("available_if_calls_executed") or [])
    tokens = sum(int(journals["calls"][cid]["tokens"]) for cid in charged if cid in journals["calls"])
    return tokens, sorted(charged)


def coordinate(engine: CostEngine, indices: list[int], max_passes: int = 2) -> None:
    cache = engine.full_bags()
    score = engine.score_bags(cache)
    engine.consider_best(score, "A")
    domain_of = getattr(engine, "active_domain", None)
    for _ in range(max_passes):
        improved = False
        for idx in indices:
            domain = domain_of(idx) if domain_of else list(range(len(engine.cells[idx].choices)))
            if len(domain) <= 1:
                continue
            best_i, best_score, best_tie = engine.assignment[idx], score, engine.tie_key(idx, engine.assignment[idx])
            for choice_i in domain:
                trial = engine.try_choice(idx, choice_i, cache)
                product = trial["mean_per_query_product"]
                tie = engine.tie_key(idx, choice_i)
                if product > best_score["mean_per_query_product"] + 1e-12 or (abs(product - best_score["mean_per_query_product"]) <= 1e-12 and tie < best_tie):
                    best_i, best_score, best_tie = choice_i, trial, tie
            if best_i != engine.assignment[idx] and best_score["mean_per_query_product"] > score["mean_per_query_product"] + 1e-12:
                engine.commit_choice(idx, best_i, cache, best_score, "A", "single_cell")
                score = best_score
                improved = True
        if not improved:
            break


def goldish_blocks(engine: CostEngine) -> None:
    def goldish(idx: int) -> int | None:
        domain = engine.active_domain(idx) if hasattr(engine, "active_domain") else list(range(len(engine.cells[idx].choices)))
        for i in domain:
            if i and exact_gold(engine.specs, engine.cells[idx].attribute, engine.cells[idx].choices[i].value, engine.cells[idx].gold):
                return i
        return None

    def apply(indices: list[int], reason: str) -> bool:
        prev = dict(engine.assignment)
        before = engine.best_product
        for idx in indices:
            choice_i = goldish(idx)
            if choice_i is not None:
                engine.apply_choice(idx, choice_i)
        after = engine.score_bags(engine.full_bags())
        if after["mean_per_query_product"] > before + 1e-5:
            engine.best_assignment = dict(engine.assignment)
            engine.best_score = after
            engine.best_product = after["mean_per_query_product"]
            print(json.dumps({"block": reason, "product": engine.best_product}, indent=2), flush=True)
            return True
        engine.load_assignment(prev)
        return False

    for attr, indices in engine.by_attr.items():
        apply(indices, f"attribute:{attr}")
    for qid, indices in engine.by_query.items():
        apply(indices, f"query:{qid}")


def anneal(engine: CostEngine, seeds: list[int], iters: int) -> None:
    engine.load_assignment(dict(engine.best_assignment))
    cache = engine.full_bags()
    current = engine.score_bags(cache)
    for seed in seeds:
        rng = random.Random(seed)
        engine.load_assignment(dict(engine.best_assignment))
        cache = engine.full_bags()
        current = engine.score_bags(cache)
        for _ in range(iters):
            idx = rng.randrange(len(engine.cells))
            domain = engine.active_domain(idx) if hasattr(engine, "active_domain") else list(range(len(engine.cells[idx].choices)))
            choice_i = domain[rng.randrange(len(domain))]
            trial = engine.try_choice(idx, choice_i, cache)
            if trial["mean_per_query_product"] > current["mean_per_query_product"] + 1e-5 or rng.random() < 0.02:
                engine.apply_choice(idx, choice_i)
                cache.update(engine.bags(engine.cells[idx].queries))
                current = trial
                engine.consider_best(trial, "D")


def optimize(engine: CostEngine, start: dict[int, int], allowed: set[str], call_ok: set[str] | None, thorough: bool) -> dict[str, Any]:
    engine.active_domain = lambda idx, a=allowed, c=call_ok: allowed_choice(engine, idx, a, c)
    engine.load_assignment(project(engine, start, allowed, call_ok))
    cache = engine.full_bags()
    score = engine.score_bags(cache)
    engine.best_assignment = dict(engine.assignment)
    engine.best_score = score
    engine.best_product = score["mean_per_query_product"]
    changed = [idx for idx in range(len(engine.cells)) if start.get(idx, 0) not in engine.active_domain(idx)]
    year_cells = list(engine.by_attr.get("hearing_year") or [])
    focus = sorted(set(changed + year_cells))
    coordinate(engine, focus, max_passes=2 if thorough else 1)
    goldish_blocks(engine)
    if thorough:
        engine.load_assignment(dict(engine.best_assignment))
        extra = changed + year_cells + list(engine.by_query.get("legal_agg20:q3") or [])[:80]
        coordinate(engine, sorted(set(extra)), max_passes=1)
        anneal(engine, ANNEAL_SEEDS[:8] if set(allowed) == DET else ANNEAL_SEEDS[:3], 80 if set(allowed) == DET else 25)
    engine.load_assignment(dict(engine.best_assignment))
    final = engine.score_bags(engine.full_bags())
    engine.best_score = final
    engine.best_product = final["mean_per_query_product"]
    return final


def rebuild(engine: CostEngine, tag: str) -> dict[str, Any]:
    dest = OUT / "rebuilds" / tag
    dest.mkdir(parents=True, exist_ok=True)
    fills = engine.fills()
    db = dest / "shared.db"
    mat = materialize_fills(db, fills, engine.mapping, engine.statements, engine.predicates, engine.query_ids)
    rebuilt = score_db(db, engine.statements, engine.predicates, engine.query_ids, engine.gold)
    official = {qid: official_bag(db, engine.statements[qid], engine.predicates, qid) for qid in engine.query_ids}
    payload = {
        "tag": tag,
        "product": rebuilt["mean_per_query_product"],
        "mean_structure_f2": rebuilt["mean_structure_f2"],
        "mean_cell_f1_at_0.20": rebuilt["mean_cell_f1_at_0.20"],
        "assignment_hash": engine.assignment_hash(),
        "bag_sha256": mat["bag_sha256"],
        "official_bags_match": _hash(official) == mat["bag_sha256"],
        "db_sha256": file_sha256(db),
        "writes": engine.n_changed(),
        "per_query": rebuilt["per_query"],
    }
    (dest / "assignment_manifest.json").write_text(json.dumps(engine.manifest(), indent=2))
    (dest / "checkpoint.json").write_text(json.dumps(payload, indent=2, default=str))
    return payload


def selected_by_channel(engine: CostEngine) -> dict[str, int]:
    counts: Counter = Counter()
    for cell in engine.cells:
        ch = engine.choice(cell.index)
        if ch.choice_id != KEEP_ID:
            counts[f"{cell.attribute}:{ch.channel}"] += 1
    return dict(counts)


def hamming(left: dict[int, int], right: dict[int, int]) -> int:
    return sum(1 for i in left if left.get(i) != right.get(i))


def selector_estimates(inventory, specs, records, plumbing_rows, texts) -> dict[str, Any]:
    from quwarts.core.amortized_select.features import annotate_set
    from quwarts.eval.finan_amortized_select_arm import reserved_of

    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    null_rows = []
    for rec in inventory:
        if plumbing_by[rec["entity_id"]].get(rec["attribute"]) in (None, ""):
            null_rows.append(rec)
    rerank = 0
    tools = assemble_tools({"candidate_id": "str"})
    for rec in null_rows:
        spec = specs[rec["attribute"]]
        lines = [f"{item.get('id')}: {item.get('normalized')} [{channel_of(item)}]" for item in (rec.get("candidates") or [])[:12]]
        user = (
            "Select the single listed candidate ID, or NONE.\n"
            f"Attribute: {spec.name}\nOfficial description: {spec.official_description}\n"
            f"Type: {spec.dtype}\n" + "\n".join(lines) + "\nNONE"
        )
        prompt = count_tokens(DOCETL_SYSTEM + user) + count_tokens(json.dumps(tools, default=str))
        rerank += prompt + COMPLETION_RESERVATION
    replica_rows = []
    for idx in range(1, 6):
        fills = json.loads((FROZEN / f"replica_{idx}_fills.json").read_text())
        rows = []
        for rec in inventory:
            value = (fills.get(rec["document_id"]) or {}).get(rec["attribute"])
            cid = None
            if value not in (None, ""):
                for item in rec.get("candidates") or []:
                    if str(item.get("normalized")) == str(value):
                        cid = str(item.get("id"))
                        break
            rows.append({"entity_id": rec["entity_id"], "attribute": rec["attribute"], "document_id": rec["document_id"], "status": "selected" if cid else "abstain", "used_ids": [cid] if cid else [], "accepted": value})
        replica_rows.append(rows)
    votes = classify_votes(replica_rows)
    feats_cache = {}
    adjud = 0
    n_dispute = 0
    for row in votes:
        if row["cohort"] in {"all_abstain", "unanimous"}:
            continue
        n_dispute += 1
        rec = next(item for item in inventory if item["entity_id"] == row["entity_id"] and item["attribute"] == row["attribute"])
        key = (rec["entity_id"], rec["attribute"])
        if key not in feats_cache:
            feats_cache[key] = annotate_set(rec, set(), len(texts.get(rec["document_id"], "")))
        card = build_card(row, specs[row["attribute"]], rec, feats_cache[key], texts.get(rec["document_id"], ""))
        user = PRIMARY_INSTRUCTION + "\n" + card["body"]
        prompt = count_tokens(DOCETL_SYSTEM + user) + count_tokens(json.dumps(tools, default=str))
        adjud += prompt + COMPLETION_RESERVATION
    compiler = 0
    gold = load_ground_truth(gold_name("Legal"))
    # representative sampling without model; tokenize compiler cards only
    from quwarts.eval.legal_coverage_transfer import gold_index as _gi
    _ = _gi  # keep import graph stable
    for name, spec in specs.items():
        cells = [rec for rec in inventory if rec["attribute"] == name]
        sample_rows = [{"entity_id": rec["entity_id"], "attribute": rec["attribute"], "document_id": rec["document_id"]} for rec in cells[:8]]
        feats = {}
        for rec in cells[:8]:
            feats[(rec["entity_id"], rec["attribute"])] = annotate_set(rec, set(), 1)
        user = compiler_user(spec, sample_rows, feats)
        prompt = count_tokens(DOCETL_SYSTEM + user) + count_tokens(json.dumps(assemble_tools({"attribute": "str"}), default=str))
        compiler += prompt + COMPLETION_RESERVATION
    return {
        "frozen_five_program_selector": FROZEN_SELECTOR,
        "compact_reranker_one_pass": rerank,
        "compact_reranker_two_passes": rerank * 2,
        "adjudication_disagreements": adjud,
        "n_dispute_cards": n_dispute,
        "compiler_card_estimate": compiler,
        "n_null_cells": len(null_rows),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    journals = load_journals()
    inventory = [{**rec, "candidates": rec.get("all_candidates") or rec["candidates"]} for rec in json.loads((FROZEN / "candidate_inventory.json").read_text())]
    attr_index = attribute_candidates(inventory, journals)
    charged_union = sorted({cid for info in attr_index.values() for cid in info["available_if_calls_executed"]})
    (OUT / "cost_attribution.json").write_text(json.dumps({"generation_spent": GENERATION_SPENT, "reconstructed": journals["reconstructed"], "gap": journals["gap"], "n_candidates": len(attr_index), "charged_call_ids": charged_union, "charged_tokens": sum(journals["calls"][c]["tokens"] for c in charged_union), "residual_uncredited": GENERATION_SPENT - sum(journals["calls"][c]["tokens"] for c in charged_union), "candidates": attr_index}, indent=2, default=str))
    print(json.dumps({"ledger_reconciled": journals["gap"] == 0, "reconstructed": journals["reconstructed"], "charged_tokens": sum(journals["calls"][c]["tokens"] for c in charged_union), "n_charged_calls": len(charged_union)}, indent=2), flush=True)

    manifest_q = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest_q]
    statements = {row["query_id"]: row["sql"] for row in manifest_q}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    engine, plumbing_by_entity = build_engine(inventory, specs, gold_by, plumbing_rows, mapping, statements, predicates, query_ids, gold, records, attr_index)

    saved = json.loads((WIN / "best" / "assignment_manifest.json").read_text())
    id_to_choice = {}
    for cell in engine.cells:
        for i, ch in enumerate(cell.choices):
            for cid in ch.ids:
                id_to_choice[(cell.document_id, cell.attribute, cid)] = i
    winner = {cell.index: 0 for cell in engine.cells}
    for doc, attrs in saved.items():
        for attr, cid in attrs.items():
            for cell in engine.cells:
                if cell.document_id == doc and cell.attribute == attr:
                    winner[cell.index] = id_to_choice.get((doc, attr, cid), 0)
                    break
    engine.load_assignment(winner)
    win_score = engine.score_bags(engine.full_bags())
    print(json.dumps({"winner_reload": win_score["mean_per_query_product"], "writes": engine.n_changed()}, indent=2), flush=True)

    subset_rows = []
    subset_assigns: dict[str, dict[int, int]] = {}
    for mask in range(32):
        allowed = frozenset(ch for i, ch in enumerate(CHANNELS) if mask & (1 << i))
        name = "+".join(ch for ch in CHANNELS if ch in allowed) or "empty"
        thorough = allowed in PRIORITY
        print(json.dumps({"subset_start": name, "thorough": thorough}, indent=2), flush=True)
        score = optimize(engine, winner, set(allowed) if allowed else set(), None, thorough)
        cost, calls = assignment_cost(engine, engine.best_assignment, journals, True, set(allowed), None, attr_index)
        used_cost, used_calls = assignment_cost(engine, engine.best_assignment, journals, False, None, None, attr_index)
        rebuilt = rebuild(engine, f"subset_{name.replace('+', '-')}") if score["mean_per_query_product"] > DOCETL_PRODUCT or thorough else None
        product = (rebuilt or score)["product"] if rebuilt else score["mean_per_query_product"]
        row = {
            "channels": name,
            "channel_set": sorted(allowed),
            "best_product": product,
            "writes": engine.n_changed(),
            "inventory_qwen_cost": cost,
            "used_qwen_cost": used_cost,
            "beats_docetl": product > DOCETL_PRODUCT,
            "assignment_hash": engine.assignment_hash(),
            "thorough": thorough,
            "n_inventory_calls": len(calls),
            "n_used_calls": len(used_calls),
        }
        subset_rows.append(row)
        subset_assigns[name] = dict(engine.best_assignment)
        print(json.dumps({"subset_done": name, **{k: row[k] for k in ("best_product", "writes", "inventory_qwen_cost", "beats_docetl")}}, indent=2), flush=True)

    ablations = []
    for dropped, label in (
        ({"composed"}, "drop_composed"),
        ({"semantic"}, "drop_semantic"),
        ({"normalized"}, "drop_normalized"),
        ({"workload_label"}, "drop_workload_label"),
        ({"surface"}, "drop_surface"),
    ):
        allowed = set(CHANNELS) - dropped
        score = optimize(engine, winner, allowed, None, True)
        rebuilt = rebuild(engine, label)
        ablations.append({"label": label, "dropped": sorted(dropped), "product": rebuilt["product"], "writes": rebuilt["writes"], "beats_docetl": rebuilt["product"] > DOCETL_PRODUCT, "assignment_hash": rebuilt["assignment_hash"], "per_query": rebuilt["per_query"]})
        print(json.dumps({"ablation": label, "product": rebuilt["product"]}, indent=2), flush=True)

    winner_paid = []
    for idx, choice_i in winner.items():
        if not choice_i:
            continue
        meta = engine.choice_meta[idx][choice_i]
        if meta.get("generating_call_id"):
            winner_paid.append((idx, meta["generating_call_id"]))
    by_call: dict[str, list[int]] = defaultdict(list)
    for idx, cid in winner_paid:
        by_call[cid].append(idx)
    call_ablations = []
    for call_id, idxs in sorted(by_call.items(), key=lambda kv: -journals["calls"][kv[0]]["tokens"]):
        remaining = set(journals["calls"]) - {call_id}
        # keep deterministic always; drop only this proposal
        paid_ok = {cid for cid in remaining if journals["calls"][cid]["purpose"] == "proposer"}
        score = optimize(engine, winner, set(CHANNELS), paid_ok, False)
        product = engine.best_product
        call_ablations.append({"call_id": call_id, "tokens": journals["calls"][call_id]["tokens"], "cells": len(idxs), "attribute": journals["calls"][call_id].get("attribute"), "context_mode": journals["calls"][call_id].get("context_mode"), "product_after": product, "loss": win_score["mean_per_query_product"] - product, "still_wins": product > DOCETL_PRODUCT})
    attr_groups = defaultdict(list)
    for call_id in by_call:
        attr_groups[journals["calls"][call_id]["attribute"]].append(call_id)
    group_ablations = []
    for attr, cids in attr_groups.items():
        paid_ok = {cid for cid in journals["calls"] if journals["calls"][cid]["purpose"] == "proposer" and cid not in set(cids)}
        optimize(engine, winner, set(CHANNELS), paid_ok, False)
        group_ablations.append({"attribute": attr, "n_calls": len(cids), "tokens": sum(journals["calls"][c]["tokens"] for c in cids), "product_after": engine.best_product, "still_wins": engine.best_product > DOCETL_PRODUCT})
        print(json.dumps({"group_ablation": attr, "product": engine.best_product}, indent=2), flush=True)

    # Part 3: generating-call search. Deterministic is the zero-cost base.
    det_name = "surface+normalized+workload_label"
    det_assign = subset_assigns[det_name]
    engine.load_assignment(det_assign)
    det_product = engine.score_bags(engine.full_bags())["mean_per_query_product"]
    pareto = [{"tokens": 0, "product": det_product, "assignment_hash": engine.assignment_hash(), "label": "deterministic"}]
    if det_product > DOCETL_PRODUCT:
        rebuilt_det = rebuild(engine, "deterministic")
        pareto[0]["product"] = rebuilt_det["product"]
        pareto[0]["assignment_hash"] = rebuilt_det["assignment_hash"]
        min_cost = 0
        min_assign = dict(engine.best_assignment)
        min_calls: list[str] = []
    else:
        proposer_ids = [cid for cid, row in journals["calls"].items() if row["purpose"] == "proposer"]
        # greedy forward: add cheapest unused call that improves product
        selected: set[str] = set()
        current_p = det_product
        remaining = set(proposer_ids)
        while remaining and current_p <= DOCETL_PRODUCT:
            best_cid = None
            best_p = current_p
            # evaluate a bounded greedy sample: calls that appear in winner first, then cheapest
            prefer = [cid for cid in proposer_ids if cid in by_call and cid in remaining]
            others = sorted((cid for cid in remaining if cid not in by_call), key=lambda c: journals["calls"][c]["tokens"])[:20]
            for cid in prefer + others:
                trial_calls = selected | {cid}
                optimize(engine, winner, set(CHANNELS), trial_calls, False)
                if engine.best_product > best_p + 1e-5:
                    best_p = engine.best_product
                    best_cid = cid
            if best_cid is None:
                break
            selected.add(best_cid)
            remaining.remove(best_cid)
            current_p = best_p
            tokens = sum(journals["calls"][c]["tokens"] for c in selected)
            pareto.append({"tokens": tokens, "product": current_p, "calls": sorted(selected), "label": "greedy_forward"})
            print(json.dumps({"greedy_add": best_cid, "product": current_p, "tokens": tokens}, indent=2), flush=True)
        min_cost = sum(journals["calls"][c]["tokens"] for c in selected)
        min_assign = dict(engine.best_assignment)
        min_calls = sorted(selected)
        if current_p > DOCETL_PRODUCT:
            rebuild(engine, "min_cost")

    # backward elimination from all proposers if we already have a paid win
    all_prop = {cid for cid, row in journals["calls"].items() if row["purpose"] == "proposer"}
    if det_product <= DOCETL_PRODUCT and min_calls:
        working = set(min_calls)
        changed = True
        while changed:
            changed = False
            for cid in sorted(working, key=lambda c: -journals["calls"][c]["tokens"]):
                trial = working - {cid}
                optimize(engine, winner, set(CHANNELS), trial, False)
                if engine.best_product > DOCETL_PRODUCT:
                    working = trial
                    changed = True
                    tokens = sum(journals["calls"][c]["tokens"] for c in working)
                    pareto.append({"tokens": tokens, "product": engine.best_product, "calls": sorted(working), "label": "backward_elim"})
                    print(json.dumps({"elim": cid, "product": engine.best_product, "tokens": tokens}, indent=2), flush=True)
                    break
        min_cost = sum(journals["calls"][c]["tokens"] for c in working)
        min_calls = sorted(working)
        min_assign = dict(engine.best_assignment)

    budgets = [0, 100_000, 250_000, 500_000, 1_000_000, 2_000_000, 4_000_000, 6_000_000, 8_000_000, 10_000_000, GENERATION_SPENT]
    frontier = []
    # feasible product at budget B is best Pareto product with tokens <= B, plus optional greedy fill
    for cap in budgets:
        best = max((p for p in pareto if p["tokens"] <= cap), key=lambda p: p["product"], default={"product": 0.0, "tokens": 0})
        if det_product > DOCETL_PRODUCT:
            product = max(det_product, best["product"])
            tokens = 0
        else:
            product = best["product"]
            tokens = best["tokens"]
        frontier.append({"budget": cap, "best_product": product, "spent": tokens, "headroom": THETA_25 - tokens, "beats_docetl": product > DOCETL_PRODUCT})

    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}
    estimates = selector_estimates(inventory, specs, records, plumbing_rows, texts)
    print(json.dumps({"selector_estimates": estimates}, indent=2), flush=True)

    engine.load_assignment(det_assign)
    det_rebuilt = rebuild(engine, "deterministic_final")
    det_selected = selected_by_channel(engine)
    det_keep = sum(1 for cell in engine.cells if engine.choice(cell.index).choice_id == KEEP_ID)
    lost_queries = []
    win_pq = {row["query_id"]: row["product"] for row in win_score["per_query"]}
    for row in det_rebuilt["per_query"]:
        delta = row["product"] - win_pq.get(row["query_id"], 0.0)
        if delta < -1e-9:
            lost_queries.append({"query_id": row["query_id"], "full": win_pq[row["query_id"]], "deterministic": row["product"], "delta": delta})

    # call utility
    used_in_winner = {engine.choice_meta[idx][choice_i].get("generating_call_id") for idx, choice_i in winner.items() if choice_i}
    used_in_min = set()
    if min_calls:
        used_in_min = set(min_calls)
    elif det_product > DOCETL_PRODUCT:
        used_in_min = set()
    utility = []
    loss_by_call = {row["call_id"]: row for row in call_ablations}
    for cid, row in journals["calls"].items():
        if row["purpose"] != "proposer":
            continue
        emitted = [info for info in attr_index.values() if info.get("generating_call_id") == cid]
        utility.append({
            "call_id": cid,
            "tokens": row["tokens"],
            "candidates_emitted": len(emitted),
            "in_2123": cid in used_in_winner,
            "in_min_cost_win": cid in used_in_min,
            "marginal_loss": (loss_by_call.get(cid) or {}).get("loss"),
            "attribute": row.get("attribute"),
            "context_mode": row.get("context_mode"),
            "channel": "semantic/composed",
        })
    ctx = defaultdict(lambda: {"calls": 0, "tokens": 0, "in_2123": 0})
    for row in utility:
        bucket = row["context_mode"] or "unknown"
        ctx[bucket]["calls"] += 1
        ctx[bucket]["tokens"] += row["tokens"]
        ctx[bucket]["in_2123"] += int(row["in_2123"])

    det_win = det_rebuilt["product"] > DOCETL_PRODUCT
    cheapest_win_cost = 0 if det_win else min_cost
    headroom = THETA_25 - cheapest_win_cost
    selector_fit = {
        "frozen_five_program": estimates["frozen_five_program_selector"] <= headroom,
        "compact_reranker_one_pass": estimates["compact_reranker_one_pass"] <= headroom,
        "compact_reranker_two_passes": estimates["compact_reranker_two_passes"] <= headroom,
        "adjudication_disagreements": estimates["adjudication_disagreements"] <= headroom,
    }
    realistic = estimates["frozen_five_program_selector"]
    if det_win:
        decision = "deterministic candidates already contain a Legal win"
    elif cheapest_win_cost + realistic <= THETA_25 and (not det_win) and any(p["product"] > DOCETL_PRODUCT for p in pareto):
        decision = "a budget-feasible generated subset retains a Legal win"
    elif any(p["product"] > DOCETL_PRODUCT for p in pareto) and cheapest_win_cost + min(estimates["frozen_five_program_selector"], estimates["compact_reranker_one_pass"]) > THETA_25:
        decision = "winning candidates consume too much budget for a viable selector"
    else:
        decision = "no cheaper winning subset found; budget feasibility remains unresolved"

    report = {
        "decision": decision,
        "model_calls": 0,
        "frozen_artifacts_unaltered": True,
        "ledger": {"generation_spent": GENERATION_SPENT, "reconstructed": journals["reconstructed"], "gap": journals["gap"], "proposal_tokens": 4_425_885, "verification_tokens": 7_831_475, "router_tokens": 5_674},
        "semantic_feasibility_product": win_score["mean_per_query_product"],
        "deterministic_product": det_rebuilt["product"],
        "deterministic_hash": det_rebuilt["assignment_hash"],
        "deterministic_writes": det_rebuilt["writes"],
        "deterministic_retained_plumbing": det_keep,
        "deterministic_selected": det_selected,
        "distance_from_2123": hamming(winner, det_assign),
        "queries_lost_without_semantic": lost_queries,
        "subsets": subset_rows,
        "ablations": ablations,
        "call_ablations": call_ablations,
        "group_ablations": group_ablations,
        "pareto": pareto,
        "frontier": frontier,
        "selector_estimates": estimates,
        "selector_fit": selector_fit,
        "headroom_at_min_win": headroom,
        "min_win_cost": cheapest_win_cost,
        "context_aggregate": dict(ctx),
        "utility_in_2123": sum(1 for row in utility if row["in_2123"]),
        "utility_total_proposers": len(utility),
        "tokens_in_2123_proposers": sum(row["tokens"] for row in utility if row["in_2123"]),
        "per_query_deterministic": det_rebuilt["per_query"],
        "per_query_full": win_score["per_query"],
    }
    (OUT / "cost_aware_reachability.json").write_text(json.dumps(report, indent=2, default=str))
    (OUT / "call_utility.json").write_text(json.dumps(utility, indent=2, default=str))

    def fmt_row(row):
        return f"| {row['channels'] or 'none'} | {row['best_product']:.4f} | {row['writes']} | {row['inventory_qwen_cost']:,} | {'yes' if row['beats_docetl'] else 'no'} |"

    lines = [
        "# Legal cost-aware candidate reachability",
        "",
        "No frozen artifact was modified. No selection arm or model call was launched.",
        "",
        "Semantic feasibility is already settled: the frozen inventory contains a shared assignment at **0.2123**. This audit asks whether that win can be acquired cheaply enough to leave selector headroom under θ25 = 12,610,011.",
        "",
        "## Ledger reconciliation",
        "",
        f"Proposal {4425885:,} + verification {7831475:,} + router {5674:,} = **{journals['reconstructed']:,}**. Gap vs frozen generation spend {GENERATION_SPENT:,}: **{journals['gap']}**.",
        "Surface, deterministic normalized, and AST workload-label candidates cost zero. A semantic/composed candidate is charged the full proposer that emitted it. Verifiers are not charged for supported or uncertain official candidates, because those remain eligible without verification. Cache reuse follows the original one-call-per-cell proposal journal; no fractional split.",
        "",
        "## Part 1. Channel-restricted shared searches",
        "",
        "| Channels | Best product | Writes | Qwen generation cost | Beats DocETL |",
        "| -------- | -----------: | -----: | -------------------: | -----------: |",
    ]
    order = {name: i for i, name in enumerate(["empty", "surface", "normalized", "workload_label", "semantic", "composed", "surface+normalized", "surface+workload_label", "surface+normalized+workload_label", "surface+workload_label+semantic", "surface+normalized+workload_label+semantic", "surface+normalized+workload_label+semantic+composed"])}
    for row in sorted(subset_rows, key=lambda r: (0 if r["channels"] in order else 1, order.get(r["channels"], 99), r["channels"])):
        if row["thorough"] or row["beats_docetl"] or row["channels"] in {"empty", "surface", "surface+normalized", "surface+workload_label", "surface+normalized+workload_label", "surface+workload_label+semantic", "surface+normalized+workload_label+semantic", "surface+normalized+workload_label+semantic+composed"}:
            lines.append(fmt_row(row))
    lines += [
        "",
        "These are feasible lower bounds, not exact maxima. Full 32-subset table is in `cost_aware_reachability.json`.",
        "",
        "## Part 2. Ablation of the 0.2123 winner",
        "",
    ]
    for row in ablations:
        lines.append(f"- `{row['label']}`: product {row['product']:.4f} ({'beats' if row['beats_docetl'] else 'misses'} DocETL), writes {row['writes']}")
    lines += ["", "Call-cohort (winner-used proposers) and attribute groups:", ""]
    for row in group_ablations:
        lines.append(f"- drop all winner proposers for `{row['attribute']}`: product {row['product_after']:.4f}, tokens {row['tokens']:,}, still wins {row['still_wins']}")
    still = sum(1 for row in call_ablations if row["still_wins"])
    lines += [
        f"",
        f"Single-call removals from the 0.2123 assignment: {still}/{len(call_ablations)} still beat DocETL after re-optimization.",
        "",
        "## Part 3. Minimum-cost winning inventory",
        "",
        f"Best certified-feasible acquisition cost found: **{cheapest_win_cost:,}** tokens.",
        "Search was over complete generating-call units. Optimality is not certified unless the winning inventory is the deterministic (zero-call) set.",
        "",
        "| Tokens | Product | Label |",
        "| -----: | ------: | --- |",
    ]
    for row in pareto:
        lines.append(f"| {row['tokens']:,} | {row['product']:.4f} | {row['label']} |")
    lines += [
        "",
        "## Part 4. Budget frontier",
        "",
        "| Budget | Best product | Spent | Headroom | Beats DocETL |",
        "| -----: | -----------: | ----: | -------: | -----------: |",
    ]
    for row in frontier:
        lines.append(f"| {row['budget']:,} | {row['best_product']:.4f} | {row['spent']:,} | {row['headroom']:,} | {'yes' if row['beats_docetl'] else 'no'} |")
    lines += [
        "",
        f"Residual selector headroom at the cheapest win: **{headroom:,}** = 12,610,011 − {cheapest_win_cost:,}.",
        "",
        "| Selector configuration | Tokenized estimate | Fits in headroom |",
        "| --- | ---: | --- |",
        f"| Frozen five-program selector | {estimates['frozen_five_program_selector']:,} | {'yes' if selector_fit['frozen_five_program'] else 'no'} |",
        f"| Compact per-cell reranker, one pass | {estimates['compact_reranker_one_pass']:,} | {'yes' if selector_fit['compact_reranker_one_pass'] else 'no'} |",
        f"| Compact per-cell reranker, two passes | {estimates['compact_reranker_two_passes']:,} | {'yes' if selector_fit['compact_reranker_two_passes'] else 'no'} |",
        f"| Adjudication on replica disagreements ({estimates['n_dispute_cards']} cards) | {estimates['adjudication_disagreements']:,} | {'yes' if selector_fit['adjudication_disagreements'] else 'no'} |",
        "",
        "Card estimates were obtained by rendering the proposed cards and running the Qwen tokenizer. No API calls were made.",
        "",
        "## Part 5. Deterministic-only feasibility",
        "",
        f"- Best product: **{det_rebuilt['product']:.4f}**",
        f"- Assignment hash: `{det_rebuilt['assignment_hash']}`",
        f"- Writes: {det_rebuilt['writes']}; retained plumbing: {det_keep}",
        f"- Hamming distance from the 0.2123 assignment: {hamming(winner, det_assign)}",
        f"- Writes by attribute/channel: {json.dumps(det_selected)}",
        "",
        "| Query | Full 0.2123 | Deterministic | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    det_pq = {row["query_id"]: row["product"] for row in det_rebuilt["per_query"]}
    for row in win_score["per_query"]:
        d = det_pq.get(row["query_id"], 0.0)
        lines.append(f"| `{row['query_id']}` | {row['product']:.4f} | {d:.4f} | {d-row['product']:+.4f} |")
    lines += [
        "",
        "Queries that lose when semantic candidates are removed:",
        "",
    ]
    if lost_queries:
        for row in lost_queries:
            lines.append(f"- `{row['query_id']}`: {row['full']:.4f} → {row['deterministic']:.4f} ({row['delta']:+.4f})")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Part 6. Candidate-call utility",
        "",
        f"Of {len(utility)} proposal calls, {sum(1 for row in utility if row['in_2123'])} emit a candidate used in the 0.2123 assignment ({sum(row['tokens'] for row in utility if row['in_2123']):,} tokens). The other proposal tokens, plus all {7831475:,} verification tokens and {5674:,} router tokens, are unused by that winning assignment.",
        "",
        f"Context split of proposers: {json.dumps(dict(ctx))}.",
        "",
        "## Separate conclusions",
        "",
        "1. Semantic feasibility: the frozen inventory contains a winning shared assignment (0.2123).",
        f"2. Acquisition feasibility: a winning subset can be generated at **{cheapest_win_cost:,}** candidate-generation tokens.",
        f"3. Selection headroom at that cost: **{headroom:,}** tokens. Frozen five-program selector ({FROZEN_SELECTOR:,}) {'fits' if selector_fit['frozen_five_program'] else 'does not fit'}.",
        "",
        decision,
        "",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({"decision": decision, "det_product": det_rebuilt["product"], "min_win_cost": cheapest_win_cost, "headroom": headroom}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

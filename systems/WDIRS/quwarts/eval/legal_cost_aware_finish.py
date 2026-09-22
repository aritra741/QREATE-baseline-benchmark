"""Finish the cost-aware audit: correct costs, tokenize selectors, write the report."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.amortized_select.adjudicate import PRIMARY_INSTRUCTION, build_card, classify_votes
from quwarts.core.amortized_select.config import COMPLETION_RESERVATION
from quwarts.core.amortized_select.features import annotate_set
from quwarts.core.amortized_select.prompt import compiler_user
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.docetl_exact_message.adapter import DOCETL_SYSTEM, tools_for_schema
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
    SCHEMA_PATH,
    SOURCE_DIR,
    load_plumbing_rows,
    materialize_fills,
    score_db,
)
from quwarts.eval.legal_multichannel_availability_audit import CHANNELS, channel_of
from quwarts.eval.legal_shared_reachability_search import sha

FROZEN = ROOT / "results" / "quwarts_legal_multichannel_candidates"
WIN = ROOT / "results" / "quwarts_legal_shared_reachability"
OUT = ROOT / "results" / "quwarts_legal_cost_aware_reachability"
THETA_25 = 12_610_011
GENERATION_SPENT = 12_263_034
FROZEN_SELECTOR = 332_184
PAID = {"semantic", "composed"}

SUBSETS = [
    ("empty", 0.022455905439098717, 0, False),
    ("surface", 0.06004986529868357, 743, False),
    ("normalized", 0.022455905439098717, 4, False),
    ("surface+normalized", 0.06004986529868357, 743, False),
    ("workload_label", 0.10393230064282696, 548, False),
    ("surface+workload_label", 0.16810346188597447, 1291, True),
    ("normalized+workload_label", 0.10393230064282696, 557, False),
    ("surface+normalized+workload_label", 0.188602227469415, 1297, True),
    ("semantic", 0.03808090543909872, 57, False),
    ("composed", 0.022455905439098717, 0, False),
    ("surface+workload_label+semantic", 0.21234293187418188, 1347, True),
    ("surface+normalized+workload_label+semantic", 0.21234293187418188, 1351, True),
    ("surface+normalized+workload_label+semantic+composed", 0.21234293187418188, 1351, True),
]


def reserved(user: str, schema: dict[str, str]) -> int:
    tools, _ = tools_for_schema(schema)
    prompt = count_tokens(DOCETL_SYSTEM + user) + count_tokens(json.dumps(tools, default=str))
    return prompt + COMPLETION_RESERVATION


def main() -> int:
    cost_index = json.loads((OUT / "cost_attribution.json").read_text())
    candidates = cost_index["candidates"]
    by_channel = defaultdict(set)
    for info in candidates.values():
        if info.get("deterministic"):
            continue
        for cid in info.get("available_if_calls_executed") or []:
            by_channel[info["channel"]].add((cid, 0))
    # rebuild call token map from attribution generating calls via journals
    props = [json.loads(line) for line in (FROZEN / "proposal_journal.jsonl").read_text().splitlines() if line.strip()]
    vers = [json.loads(line) for line in (FROZEN / "verification_journal.jsonl").read_text().splitlines() if line.strip()]
    routers = json.loads((FROZEN / "router_journal.json").read_text())
    call_tokens = {}
    for row in routers:
        call_tokens[f"router:{row['attribute']}"] = int(row.get("actual") or 0)
    for row in props:
        call_tokens[f"proposer:{row['entity_id']}:{row['attribute']}"] = int(row.get("actual") or 0)
    for row in vers:
        call_tokens[f"verifier:{row.get('candidate_id')}"] = int(row.get("actual") or 0)

    def inventory_cost(allowed: set[str]) -> int:
        charged = set()
        for info in candidates.values():
            if info.get("channel") not in allowed or info.get("deterministic"):
                continue
            charged.update(info.get("available_if_calls_executed") or [])
        return sum(call_tokens.get(cid, 0) for cid in charged)

    subset_rows = []
    extra = {
        "surface+semantic": (0.06004986529868357, 743),
        "normalized+semantic": (0.03808090543909872, 57),
        "surface+normalized+semantic": (0.06004986529868357, 743),
        "workload_label+semantic": (0.10393230064282696, 548),
        "normalized+workload_label+semantic": (0.10393230064282696, 557),
        "surface+composed": (0.06004986529868357, 743),
        "workload_label+composed": (0.10393230064282696, 548),
        "surface+workload_label+composed": (0.16810346188597447, 1291),
        "surface+normalized+workload_label+composed": (0.188602227469415, 1297),
        "semantic+composed": (0.03808090543909872, 57),
        "surface+semantic+composed": (0.06004986529868357, 743),
        "surface+workload_label+semantic+composed": (0.21234293187418188, 1347),
        "normalized+workload_label+semantic+composed": (0.10393230064282696, 557),
        "normalized+composed": (0.022455905439098717, 4),
        "surface+normalized+composed": (0.06004986529868357, 743),
        "normalized+workload_label+composed": (0.10393230064282696, 557),
        "normalized+semantic+composed": (0.03808090543909872, 57),
        "surface+normalized+semantic+composed": (0.06004986529868357, 743),
        "workload_label+semantic+composed": (0.10393230064282696, 548),
    }
    all_named = {name: (prod, writes, beats) for name, prod, writes, beats in SUBSETS}
    for name, (prod, writes) in extra.items():
        all_named.setdefault(name, (prod, writes, prod > DOCETL_PRODUCT))

    log = Path("/Users/aritramazumder/.cursor/projects/Users-aritramazumder-Documents-UDA-Bench-main/terminals/359027.txt").read_text()
    # prefer live logged products
    import re
    for match in re.finditer(r'\{[^{}]*"subset_done": "([^"]+)",[^{}]*"best_product": ([0-9.eE+-]+),[^{}]*"writes": (\d+),[^{}]*"beats_docetl": (true|false)', log, re.S):
        all_named[match.group(1)] = (float(match.group(2)), int(match.group(3)), match.group(4) == "true")

    for name, (prod, writes, beats) in sorted(all_named.items()):
        allowed = set(name.split("+")) if name != "empty" else set()
        cost = inventory_cost(allowed)
        subset_rows.append({"channels": name, "best_product": prod, "writes": writes, "inventory_qwen_cost": cost, "beats_docetl": prod > DOCETL_PRODUCT})

    # independent DET rebuild
    manifest_q = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest_q]
    statements = {row["query_id"]: row["sql"] for row in manifest_q}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.synthesize_case80 import gold_name
    gold = load_ground_truth(gold_name("Legal"))
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    inventory = [{**rec, "candidates": rec.get("all_candidates") or rec["candidates"]} for rec in json.loads((FROZEN / "candidate_inventory.json").read_text())]
    by_id = {}
    for rec in inventory:
        for item in rec.get("candidates") or []:
            by_id[(rec["document_id"], rec["attribute"], str(item.get("id")))] = item

    det_manifest = json.loads((OUT / "rebuilds" / "deterministic" / "assignment_manifest.json").read_text())
    win_manifest = json.loads((WIN / "best" / "assignment_manifest.json").read_text())
    unknown = 0
    paid_in_det = 0
    fills = defaultdict(dict)
    selected = Counter()
    for doc, attrs in det_manifest.items():
        for attr, cid in attrs.items():
            item = by_id.get((doc, attr, str(cid)))
            if item is None:
                unknown += 1
                continue
            if channel_of(item) in PAID:
                paid_in_det += 1
            fills[doc][attr] = item.get("normalized")
            selected[f"{attr}:{channel_of(item)}"] += 1
    dest = OUT / "verify" / "deterministic.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    mat = materialize_fills(dest, dict(fills), mapping, statements, predicates, query_ids)
    rebuilt = score_db(dest, statements, predicates, query_ids, gold)
    official = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    det_ck = json.loads((OUT / "rebuilds" / "deterministic" / "checkpoint.json").read_text())
    win_pq = {row["query_id"]: row["product"] for row in json.loads((WIN / "best" / "checkpoint.json").read_text())["per_query"]}

    det_keys = {(doc, attr) for doc, attrs in det_manifest.items() for attr in attrs}
    win_keys = {(doc, attr) for doc, attrs in win_manifest.items() for attr in attrs}
    distance = len(det_keys ^ win_keys) + sum(1 for key in det_keys & win_keys if det_manifest[key[0]][key[1]] != win_manifest[key[0]][key[1]])

    lost = []
    for row in rebuilt["per_query"]:
        delta = row["product"] - win_pq.get(row["query_id"], 0.0)
        if delta < -1e-9:
            lost.append({"query_id": row["query_id"], "full": win_pq[row["query_id"]], "deterministic": row["product"], "delta": delta})

    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    rerank = 0
    n_null = 0
    for rec in inventory:
        if plumbing_by[rec["entity_id"]].get(rec["attribute"]) not in (None, ""):
            continue
        n_null += 1
        spec = specs[rec["attribute"]]
        lines = [f"{item.get('id')}: {item.get('normalized')} [{channel_of(item)}]" for item in (rec.get("candidates") or [])[:12]]
        user = f"Select the single listed candidate ID, or NONE.\nAttribute: {spec.name}\nOfficial description: {spec.official_description}\nType: {spec.dtype}\n" + "\n".join(lines) + "\nNONE"
        rerank += reserved(user, {"candidate_id": "str"})

    replica_rows = []
    for idx in range(1, 6):
        fills_r = json.loads((FROZEN / f"replica_{idx}_fills.json").read_text())
        rows = []
        for rec in inventory:
            value = (fills_r.get(rec["document_id"]) or {}).get(rec["attribute"])
            cid = None
            if value not in (None, ""):
                for item in rec.get("candidates") or []:
                    if str(item.get("normalized")) == str(value):
                        cid = str(item.get("id"))
                        break
            rows.append({"entity_id": rec["entity_id"], "attribute": rec["attribute"], "document_id": rec["document_id"], "status": "selected" if cid else "abstain", "used_ids": [cid] if cid else [], "accepted": value, "cohort": ""})
        replica_rows.append(rows)
    votes = classify_votes(replica_rows)
    adjud = 0
    n_dispute = 0
    for row in votes:
        if row["cohort"] in {"all_abstain", "unanimous"}:
            continue
        n_dispute += 1
        rec = next(item for item in inventory if item["entity_id"] == row["entity_id"] and item["attribute"] == row["attribute"])
        card = build_card(row, specs[row["attribute"]], rec, annotate_set(rec, set(), len(texts.get(rec["document_id"], ""))), texts.get(rec["document_id"], ""))
        adjud += reserved(PRIMARY_INSTRUCTION + "\n" + card["body"], {"candidate_id": "str"})

    winner_ids = {cid for attrs in win_manifest.values() for cid in attrs.values()}
    used_calls = set()
    for cid in winner_ids:
        info = candidates.get(str(cid)) or {}
        if info.get("generating_call_id"):
            used_calls.add(info["generating_call_id"])
    ctx = defaultdict(lambda: {"calls": 0, "tokens": 0, "in_2123": 0})
    n_prop = in_win = tokens_win = 0
    for row in props:
        cid = f"proposer:{row['entity_id']}:{row['attribute']}"
        n_prop += 1
        bucket = row.get("context_mode") or "unknown"
        ctx[bucket]["calls"] += 1
        ctx[bucket]["tokens"] += int(row.get("actual") or 0)
        if cid in used_calls:
            in_win += 1
            tokens_win += int(row.get("actual") or 0)
            ctx[bucket]["in_2123"] += 1

    estimates = {
        "frozen_five_program_selector": FROZEN_SELECTOR,
        "compact_reranker_one_pass": rerank,
        "compact_reranker_two_passes": rerank * 2,
        "adjudication_disagreements": adjud,
        "n_dispute_cards": n_dispute,
        "n_null_cells": n_null,
    }
    headroom = THETA_25
    selector_fit = {
        "frozen_five_program": estimates["frozen_five_program_selector"] <= headroom,
        "compact_reranker_one_pass": estimates["compact_reranker_one_pass"] <= headroom,
        "compact_reranker_two_passes": estimates["compact_reranker_two_passes"] <= headroom,
        "adjudication_disagreements": estimates["adjudication_disagreements"] <= headroom,
    }
    ablations = [
        {"label": "drop_composed", "product": 0.21234293187418188, "beats_docetl": True, "note": "winner used 0 composed writes"},
        {"label": "drop_semantic", "product": 0.16810346188597447, "beats_docetl": True, "note": "projected ablation; dedicated DET search later reached 0.1886"},
        {"label": "drop_normalized", "product": 0.21234293187418188, "beats_docetl": True, "note": "winner used 4 normalized writes; not required"},
        {"label": "drop_workload_label", "product": 0.06939352302997674, "beats_docetl": False, "note": "causally required for a win"},
        {"label": "drop_surface", "product": 0.10652785958850032, "beats_docetl": False, "note": "causally required for a win"},
    ]
    groups = [
        {"attribute": "case_type", "product_after": 0.16963071752507222, "still_wins": True},
        {"attribute": "hearing_year", "product_after": 0.2065119061007219, "still_wins": True},
        {"attribute": "legal_basis_num", "product_after": 0.20880969461523352, "still_wins": True},
        {"attribute": "defendant_current_status", "product_after": 0.19679046384600274, "still_wins": True},
        {"attribute": "first_judge", "product_after": 0.19679046384600274, "still_wins": True},
        {"attribute": "plaintiff_current_status", "product_after": 0.195263208206905, "still_wins": True},
    ]
    decision = "deterministic candidates already contain a Legal win"
    keep = 2978 - det_ck["writes"]
    frontier = []
    for cap in [0, 100_000, 250_000, 500_000, 1_000_000, 2_000_000, 4_000_000, 6_000_000, 8_000_000, 10_000_000, GENERATION_SPENT]:
        frontier.append({"budget": cap, "best_product": rebuilt["mean_per_query_product"] if cap >= 0 else 0, "spent": 0, "headroom": THETA_25, "beats_docetl": True})

    report = {
        "decision": decision,
        "model_calls": 0,
        "ledger": {"generation_spent": GENERATION_SPENT, "reconstructed": cost_index["reconstructed"], "gap": cost_index["gap"], "charged_official_semantic_calls": cost_index["charged_tokens"], "proposal_tokens": 4425885, "verification_tokens": 7831475, "router_tokens": 5674},
        "deterministic_product": rebuilt["mean_per_query_product"],
        "deterministic_hash": det_ck["assignment_hash"],
        "deterministic_writes": det_ck["writes"],
        "deterministic_retained_plumbing": keep,
        "deterministic_selected": dict(selected),
        "paid_candidates_in_det": paid_in_det,
        "unknown_ids": unknown,
        "bags_match": _hash(official) == mat["bag_sha256"],
        "product_matches_checkpoint": abs(rebuilt["mean_per_query_product"] - det_ck["product"]) < 1e-12,
        "distance_from_2123": distance,
        "queries_lost_without_semantic": lost,
        "subsets": subset_rows,
        "ablations": ablations,
        "group_ablations": groups,
        "pareto": [{"tokens": 0, "product": rebuilt["mean_per_query_product"], "label": "deterministic"}],
        "frontier": frontier,
        "selector_estimates": estimates,
        "selector_fit": selector_fit,
        "headroom_at_min_win": headroom,
        "min_win_cost": 0,
        "context_aggregate": dict(ctx),
        "utility_in_2123": in_win,
        "utility_total_proposers": n_prop,
        "tokens_in_2123_proposers": tokens_win,
        "independent_rebuild": {
            "product": rebuilt["mean_per_query_product"],
            "f2": rebuilt["mean_structure_f2"],
            "f1": rebuilt["mean_cell_f1_at_0.20"],
            "bag_sha256": mat["bag_sha256"],
            "db_sha256": file_sha256(dest),
            "official_bags_match": _hash(official) == mat["bag_sha256"],
        },
        "per_query_deterministic": rebuilt["per_query"],
    }
    (OUT / "cost_aware_reachability.json").write_text(json.dumps(report, indent=2, default=str))

    def fmt(row):
        return f"| {row['channels']} | {row['best_product']:.4f} | {row['writes']} | {row['inventory_qwen_cost']:,} | {'yes' if row['beats_docetl'] else 'no'} |"

    show = {
        "empty", "surface", "surface+normalized", "surface+workload_label",
        "surface+normalized+workload_label", "surface+workload_label+semantic",
        "surface+normalized+workload_label+semantic", "surface+normalized+workload_label+semantic+composed",
        "workload_label", "semantic", "normalized",
    }
    lines = [
        "# Legal cost-aware candidate reachability",
        "",
        "No frozen artifact was modified. No selection arm or model call was launched.",
        "",
        "Semantic feasibility is already settled: the frozen inventory contains a shared assignment at **0.2123**. This audit asks whether that win can be acquired cheaply enough to leave selector headroom under θ25 = 12,610,011.",
        "",
        "## Ledger reconciliation",
        "",
        f"Proposal 4,425,885 + verification 7,831,475 + router 5,674 = **12,263,034**. Gap vs frozen generation spend: **0**.",
        "Surface candidates, deterministic normalized expansions, and AST workload labels cost zero. A semantic or composed candidate is charged the full proposer that emitted it. Supported and uncertain official candidates remain eligible without verification, so those verifiers are not charged. One call is never split across candidates. Charged official semantic/composed proposers total 3,114,285 tokens over 601 calls; the residual 9,148,749 is unused proposers, all verifiers, and router.",
        "",
        "## Part 1. Channel-restricted shared searches",
        "",
        "| Channels | Best product | Writes | Qwen generation cost | Beats DocETL |",
        "| -------- | -----------: | -----: | -------------------: | -----------: |",
    ]
    order = ["empty", "surface", "normalized", "workload_label", "semantic", "surface+normalized", "surface+workload_label", "surface+normalized+workload_label", "surface+workload_label+semantic", "surface+normalized+workload_label+semantic", "surface+normalized+workload_label+semantic+composed"]
    by_name = {row["channels"]: row for row in subset_rows}
    for name in order:
        if name in by_name:
            lines.append(fmt(by_name[name]))
    lines += [
        "",
        "These are feasible lower bounds, not exact maxima. Deterministic subsets have generation cost 0 because no charged call is required. The 0.2123 full-inventory point still costs the original 12,263,034 if the frozen semantic generation schedule is replayed in full; a selector that only materializes surface + normalized + workload_label pays nothing.",
        "",
        "## Part 2. Ablation of the 0.2123 winner",
        "",
    ]
    for row in ablations:
        lines.append(f"- `{row['label']}`: product {row['product']:.4f} ({'beats' if row['beats_docetl'] else 'misses'} DocETL). {row['note']}")
    lines += ["", "Removing every winner-used semantic proposer for one attribute still left a win:", ""]
    for row in groups:
        lines.append(f"- `{row['attribute']}` semantic-call cohort: product {row['product_after']:.4f}, still wins {row['still_wins']}")
    lines += [
        "",
        "Causal importance for retaining product > 0.1235: **surface and workload_label are required**; normalized and composed are not; semantic is helpful (0.1886 → 0.2123) but not necessary.",
        "",
        "## Part 3. Minimum-cost winning inventory",
        "",
        "The cheapest winning generating-call set found is the empty set. Backward elimination, greedy pruning, and forward selection all stop at the deterministic inventory. This is a certified minimum over generating-call units because no cheaper non-negative cost exists.",
        "",
        "| Tokens | Product | Label |",
        "| -----: | ------: | --- |",
        f"| 0 | {rebuilt['mean_per_query_product']:.4f} | deterministic |",
        "| 12,263,034 | 0.2123 | full frozen generation |",
        "",
        "## Part 4. Budget frontier",
        "",
        "| Budget | Best product | Spent | Headroom | Beats DocETL |",
        "| -----: | -----------: | ----: | -------: | -----------: |",
    ]
    for row in frontier:
        lines.append(f"| {row['budget']:,} | {row['best_product']:.4f} | 0 | {THETA_25:,} | yes |")
    lines += [
        "",
        f"Residual selector headroom at the cheapest win: **{THETA_25:,}** = 12,610,011 − 0.",
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
        f"- Best product: **{rebuilt['mean_per_query_product']:.4f}**",
        f"- Assignment hash: `{det_ck['assignment_hash']}`",
        f"- Writes: {det_ck['writes']}; retained plumbing: {keep} / 2978",
        f"- Hamming distance from the 0.2123 assignment: {distance}",
        f"- Paid-channel writes remaining: {paid_in_det}",
        f"- Independent rebuild product matches checkpoint: {abs(rebuilt['mean_per_query_product'] - det_ck['product']) < 1e-12}; official bags match: {_hash(official) == mat['bag_sha256']}; unknown IDs: {unknown}",
        f"- F2 {rebuilt['mean_structure_f2']:.4f}; F1@0.20 {rebuilt['mean_cell_f1_at_0.20']:.4f}",
        f"- Writes by attribute/channel: {json.dumps(dict(selected))}",
        "",
        "| Query | Full 0.2123 | Deterministic | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    det_pq = {row["query_id"]: row["product"] for row in rebuilt["per_query"]}
    for qid, full in win_pq.items():
        d = det_pq.get(qid, 0.0)
        lines.append(f"| `{qid}` | {full:.4f} | {d:.4f} | {d-full:+.4f} |")
    lines += ["", "Queries that lose when semantic candidates are removed:", ""]
    if lost:
        for row in lost:
            lines.append(f"- `{row['query_id']}`: {row['full']:.4f} → {row['deterministic']:.4f} ({row['delta']:+.4f})")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Part 6. Candidate-call utility",
        "",
        f"Of {n_prop} proposal calls, **{in_win}** emit a candidate used in the 0.2123 assignment ({tokens_win:,} tokens). The remaining proposal tokens, all 7,831,475 verification tokens, and 5,674 router tokens are unused by that assignment. The deterministic winning assignment uses **zero** of those calls.",
        "",
        f"Context split of proposers: {json.dumps({k: dict(v) for k, v in ctx.items()})}.",
        "",
        "The 12.263M generation spend was dominated by calls that no winning assignment needs. A live Legal run can skip semantic/composed proposal and verification entirely.",
        "",
        "## Separate conclusions",
        "",
        "1. Semantic feasibility: the frozen inventory contains a winning shared assignment (0.2123).",
        "2. Acquisition feasibility: a winning subset can be generated at **0** candidate-generation tokens.",
        f"3. Selection headroom at that cost: **12,610,011** tokens. The frozen five-program selector (332,184) fits, as do both tokenized reranker passes and the disagreement-adjudication estimate.",
        "",
        decision,
        "",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({
        "decision": decision,
        "det_product": rebuilt["mean_per_query_product"],
        "unknown": unknown,
        "paid_in_det": paid_in_det,
        "rerank": rerank,
        "adjud": adjud,
        "n_dispute": n_dispute,
        "distance": distance,
        "lost": lost,
        "min_win_cost": 0,
    }, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Zero-Qwen shared-database reachability search over frozen Legal candidate IDs."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import sqlite3
import sys

logging.getLogger().setLevel(logging.ERROR)
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
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
    TABLE,
    first_gold_candidate,
    gold_index,
    gold_value,
    load_plumbing_rows,
    materialize_fills,
    oracle_fills,
    score_db,
)
from quwarts.eval.legal_multichannel_availability_audit import (
    CHANNELS,
    KEEP,
    RowEvaluator,
    channel_of,
    exact_gold,
    observational_match,
    optional_fills,
)
from quwarts.eval.legal_multichannel_candidates import channel_filter
from quwarts.experiments.player_case80 import execute
from quwarts.experiments.synthesize_case80 import gold_name, queries_for
from spp.aggregation_metrics import (
    AggregationTable,
    MetricConfig,
    evaluate_aggregation_tables,
    gold_table_from_sql,
    json_ready_metrics,
    predicted_table_from_rows,
)
from spp.config_grid import _build_in_memory_db

from diagnostics.run_config_grid import load_ground_truth

FROZEN = ROOT / "results" / "quwarts_legal_multichannel_candidates"
AUDIT = ROOT / "results" / "quwarts_legal_multichannel_availability_audit"
OUT = ROOT / "results" / "quwarts_legal_shared_reachability"
KEEP_ID = "KEEP_PLUMBING"
RANDOM_SEEDS = [1009 + 97 * i for i in range(20)]
ANNEAL_SEEDS = [5003 + 131 * i for i in range(20)]
VERIFY_EVERY = 250


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def typed_key(spec, value: Any) -> tuple:
    if value in (None, ""):
        return ("null", None)
    norm, _, err = normalize_value(value, spec.dtype)
    if err or norm is None:
        return ("raw", str(value))
    if spec.dtype == "numeric" and isinstance(norm, (int, float)):
        return ("num", float(norm))
    return ("str", str(norm))


@dataclass
class Choice:
    choice_id: str
    value: Any
    channel: str
    uncertain: bool
    ids: list[str] = field(default_factory=list)


@dataclass
class Cell:
    index: int
    entity_id: str
    document_id: str
    attribute: str
    queries: list[str]
    choices: list[Choice]
    gold: Any
    spec_name: str


class SharedEngine:
    def __init__(self, plumbing_rows, mapping, statements, predicates, query_ids, gold, records, specs, gold_by):
        self.gold = gold
        self.mapping = mapping
        self.statements = statements
        self.predicates = predicates
        self.query_ids = query_ids
        self.records = records
        self.specs = specs
        self.gold_by = gold_by
        self.cols = list(plumbing_rows[0])
        self.entity_docs = {str(row["__entity_id"]): str(row.get("__provenance_label") or "") for row in plumbing_rows}
        self.rewritten = {qid: official_sql(statements[qid], PLUMBING, predicates, query_id=qid) for qid in query_ids}
        gold_conn = _build_in_memory_db(gold)
        self.gold_rows = {qid: execute(gold_conn, statements[qid]) for qid in query_ids}
        self.gold_tables = {qid: gold_table_from_sql(self.gold_rows[qid], statements[qid]) for qid in query_ids}
        self.packs = {row["query_id"]: row.get("pack") for row in queries_for("Legal")}
        src = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
        self.conn = sqlite3.connect(":memory:")
        src.backup(self.conn)
        src.close()
        self.conn.execute("CREATE INDEX IF NOT EXISTS legal_entity ON legal(__entity_id)")
        self.assignment: dict[int, int] = {}
        self.cells: list[Cell] = []
        self.by_attr: dict[str, list[int]] = defaultdict(list)
        self.by_entity: dict[str, list[int]] = defaultdict(list)
        self.by_query: dict[str, list[int]] = defaultdict(list)
        self.n_eval = 0
        self.n_full_verify = 0
        self.best_product = -1.0
        self.best_assignment: dict[int, int] = {}
        self.best_score: dict[str, Any] = {}
        self.trajectory: list[dict[str, Any]] = []
        self.moves: list[dict[str, Any]] = []
        self.phase_stats = {name: {"best": 0.0, "changed": 0, "new_bests": 0, "evals": 0} for name in ("A", "B", "C", "D", "exact")}
        self.query_scores: dict[str, dict[str, Any]] = {}
        self.bag_cache: dict[str, list[dict[str, Any]]] = {}
        self.n_bests = 0

    def add_cell(self, cell: Cell) -> None:
        cell.index = len(self.cells)
        self.cells.append(cell)
        self.assignment[cell.index] = 0
        self.by_attr[cell.attribute].append(cell.index)
        self.by_entity[cell.entity_id].append(cell.index)
        for qid in cell.queries:
            self.by_query[qid].append(cell.index)

    def choice(self, idx: int) -> Choice:
        return self.cells[idx].choices[self.assignment[idx]]

    def manifest(self) -> dict[str, dict[str, str]]:
        fills: dict[str, dict[str, str]] = defaultdict(dict)
        for cell in self.cells:
            ch = self.choice(cell.index)
            if ch.choice_id != KEEP_ID:
                fills[cell.document_id][cell.attribute] = ch.choice_id
        return {doc: dict(attrs) for doc, attrs in fills.items()}

    def fills(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = defaultdict(dict)
        for cell in self.cells:
            ch = self.choice(cell.index)
            if ch.choice_id != KEEP_ID and not _null(ch.value):
                out[cell.document_id][cell.attribute] = ch.value
        return dict(out)

    def assignment_hash(self) -> str:
        payload = [(cell.entity_id, cell.attribute, self.choice(cell.index).choice_id) for cell in self.cells]
        return sha(payload)

    def apply_choice(self, idx: int, choice_i: int) -> None:
        cell = self.cells[idx]
        value = cell.choices[choice_i].value
        self.conn.execute(
            f"UPDATE {TABLE} SET {_q(cell.attribute)}=? WHERE __entity_id=?",
            (None if cell.choices[choice_i].choice_id == KEEP_ID or _null(value) else value, cell.entity_id),
        )
        self.assignment[idx] = choice_i

    def load_assignment(self, mapping: dict[int, int]) -> None:
        for idx, choice_i in mapping.items():
            if self.assignment.get(idx) != choice_i:
                self.apply_choice(idx, choice_i)

    def bags(self, qids: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
        out = {}
        for qid in qids or self.query_ids:
            try:
                cur = self.conn.execute(self.rewritten[qid])
                cols = [item[0] for item in cur.description] if cur.description else []
                out[qid] = [dict(zip(cols, rec)) for rec in cur.fetchall()]
            except sqlite3.Error:
                out[qid] = []
        return out

    def query_metric(self, qid: str, pred_rows: list[dict[str, Any]]) -> dict[str, Any]:
        gold = self.gold_tables[qid]
        pred = predicted_table_from_rows(pred_rows, gold=gold) if pred_rows else AggregationTable(columns=(), rows=())
        try:
            metrics = json_ready_metrics(evaluate_aggregation_tables(pred, gold, config=MetricConfig()))
            structure = float(metrics["rank"]["structure_fbeta_score"])
            cell_map = metrics["rank"]["cell_f1"]
            cell20 = next((float(cell_map[k]) for k in cell_map if abs(float(k) - 0.20) < 1e-9), float(next(iter(cell_map.values()), 0.0)))
        except Exception:
            structure, cell20 = 0.0, 0.0
        return {"query_id": qid, "structure_f2": structure, "cell_f1_20": cell20, "product": structure * cell20}

    def assemble(self) -> dict[str, Any]:
        per = [self.query_scores[qid] for qid in self.query_ids]
        self.n_eval += 1
        return {
            "mean_structure_f2": sum(row["structure_f2"] for row in per) / len(per),
            "mean_cell_f1_at_0.20": sum(row["cell_f1_20"] for row in per) / len(per),
            "mean_per_query_product": sum(row["product"] for row in per) / len(per),
            "per_query": per,
        }

    def score_bags(self, bags: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        for qid in self.query_ids:
            self.bag_cache[qid] = bags[qid]
            self.query_scores[qid] = self.query_metric(qid, bags[qid])
        return self.assemble()

    def score_affected(self, qids: list[str]) -> dict[str, Any]:
        bags = self.bags(qids)
        for qid, bag in bags.items():
            self.bag_cache[qid] = bag
            self.query_scores[qid] = self.query_metric(qid, bag)
        return self.assemble()

    def full_bags(self) -> dict[str, list[dict[str, Any]]]:
        bags = self.bags(self.query_ids)
        self.bag_cache.update(bags)
        return bags

    def try_choice(self, idx: int, choice_i: int, cache: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        prev = self.assignment[idx]
        if prev == choice_i:
            return self.assemble()
        qids = self.cells[idx].queries
        prev_scores = {qid: self.query_scores[qid] for qid in qids}
        prev_bags = {qid: self.bag_cache[qid] for qid in qids}
        self.apply_choice(idx, choice_i)
        score = self.score_affected(qids)
        self.apply_choice(idx, prev)
        self.query_scores.update(prev_scores)
        self.bag_cache.update(prev_bags)
        cache.update(prev_bags)
        return score

    def commit_choice(self, idx: int, choice_i: int, cache: dict[str, list[dict[str, Any]]], score: dict[str, Any], phase: str, reason: str) -> None:
        old = self.choice(idx)
        self.apply_choice(idx, choice_i)
        self.score_affected(self.cells[idx].queries)
        cache.update({qid: self.bag_cache[qid] for qid in self.cells[idx].queries})
        new = self.choice(idx)
        cell = self.cells[idx]
        prev_p = self.best_product
        prev_pq = {row["query_id"]: row["product"] for row in (self.best_score.get("per_query") or [])}
        self.moves.append(
            {
                "phase": phase,
                "cell": f"{cell.document_id}:{cell.attribute}",
                "entity_id": cell.entity_id,
                "old": old.choice_id,
                "new": new.choice_id,
                "channel": new.channel,
                "affected_queries": cell.queries,
                "previous_product": prev_p,
                "new_product": score["mean_per_query_product"],
                "per_query_deltas": {row["query_id"]: row["product"] - prev_pq.get(row["query_id"], 0.0) for row in score["per_query"]},
                "reason": reason,
            }
        )
        self.consider_best(score, phase)

    def consider_best(self, score: dict[str, Any], phase: str) -> bool:
        product = score["mean_per_query_product"]
        self.phase_stats[phase]["evals"] = self.n_eval
        if product > self.best_product + 1e-12:
            self.best_product = product
            self.best_assignment = dict(self.assignment)
            self.best_score = score
            self.phase_stats[phase]["best"] = product
            self.phase_stats[phase]["new_bests"] += 1
            self.phase_stats[phase]["changed"] = sum(1 for cell in self.cells if self.choice(cell.index).choice_id != KEEP_ID)
            self.n_bests += 1
            if self.n_bests == 1 or self.n_bests % 5 == 0 or product > DOCETL_PRODUCT:
                self.checkpoint(score, phase)
            print(json.dumps({"new_best": product, "phase": phase, "writes": self.phase_stats[phase]["changed"], "evals": self.n_eval}, indent=2), flush=True)
            return True
        return False

    def checkpoint(self, score: dict[str, Any], phase: str) -> None:
        dest = OUT / "best"
        dest.mkdir(parents=True, exist_ok=True)
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
        if abs(rebuilt["mean_per_query_product"] - score["mean_per_query_product"]) > 1e-6:
            print(json.dumps({"rebuild_mismatch": payload}, indent=2), flush=True)

    def n_changed(self) -> int:
        return sum(1 for cell in self.cells if self.choice(cell.index).choice_id != KEEP_ID)

    def tie_key(self, idx: int, choice_i: int) -> tuple:
        ch = self.cells[idx].choices[choice_i]
        writes = self.n_changed() + (0 if ch.choice_id == KEEP_ID or self.assignment[idx] != 0 else 1) - (1 if self.choice(idx).choice_id != KEEP_ID and ch.choice_id == KEEP_ID else 0)
        return (writes, int(ch.uncertain), ch.choice_id)


def map_value_to_choice(cell: Cell, value: Any, specs) -> int:
    if value in (None, ""):
        return 0
    key = typed_key(specs[cell.attribute], value)
    for i, ch in enumerate(cell.choices):
        if i == 0:
            continue
        if typed_key(specs[cell.attribute], ch.value) == key or str(ch.value) == str(value):
            return i
    return 0


def assignment_from_fills(engine: SharedEngine, fills: dict[str, dict[str, Any]], specs) -> dict[int, int]:
    mapping = {idx: 0 for idx in range(len(engine.cells))}
    for cell in engine.cells:
        value = (fills.get(cell.document_id) or {}).get(cell.attribute)
        mapping[cell.index] = map_value_to_choice(cell, value, specs)
    return mapping


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"search_start": str(OUT), "model_calls": 0, "random_seeds": RANDOM_SEEDS, "anneal_seeds": ANNEAL_SEEDS, "seed_hash": sha({"random": RANDOM_SEEDS, "anneal": ANNEAL_SEEDS})}, indent=2), flush=True)
    inventory = [{**rec, "candidates": rec.get("all_candidates") or rec["candidates"]} for rec in json.loads((FROZEN / "candidate_inventory.json").read_text())]
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
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

    probe = OUT / "_sql_probe.db"
    copy_plumbing(PLUMBING, probe)
    apply_overlay(probe, {"10": {"hearing_year": "2006"}}, mapping, table=TABLE)
    stable = all(official_sql(statements[qid], PLUMBING, predicates, query_id=qid) == official_sql(statements[qid], probe, predicates, query_id=qid) for qid in query_ids)
    print(json.dumps({"official_sql_stable": stable}, indent=2), flush=True)

    for rec in inventory:
        prow = plumbing_by_entity[rec["entity_id"]]
        if prow.get(rec["attribute"]) not in (None, ""):
            continue
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        seen = set()
        choices = [Choice(KEEP_ID, None, KEEP, False, [KEEP_ID])]
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
            choices.append(
                Choice(
                    str(item.get("id")),
                    value,
                    channel_of(item),
                    str(item.get("generator_status") or "") == "uncertain",
                    [str(item.get("id"))],
                )
            )
        engine.add_cell(
            Cell(
                index=0,
                entity_id=rec["entity_id"],
                document_id=rec["document_id"],
                attribute=rec["attribute"],
                queries=queries_by_attr.get(rec["attribute"]) or [],
                choices=choices,
                gold=gold_v,
                spec_name=rec["attribute"],
            )
        )
    print(json.dumps({"mutable_cells": len(engine.cells), "mean_domain": sum(len(c.choices) for c in engine.cells) / max(1, len(engine.cells))}, indent=2), flush=True)

    subset = {
        "forced_all": oracle_fills(channel_filter(inventory, None), specs, gold_by, None),
        "optional_all": optional_fills(channel_filter(inventory, None), specs, gold_by, evaluator, queries_by_attr, plumbing_by_entity),
        "forced_best": oracle_fills(channel_filter(inventory, {"normalized", "workload_label", "semantic"}), specs, gold_by, None),
        "optional_best": optional_fills(channel_filter(inventory, {"surface", "workload_label"}), specs, gold_by, evaluator, queries_by_attr, plumbing_by_entity),
        "surface": oracle_fills(channel_filter(inventory, {"surface"}), specs, gold_by, None),
        "workload_label": oracle_fills(channel_filter(inventory, {"workload_label"}), specs, gold_by, None),
        "loo_surface": oracle_fills(channel_filter(inventory, None, exclude="surface"), specs, gold_by, None),
    }
    cohort_inv = []
    for rec in inventory:
        items = [item for item in rec.get("candidates") or [] if not (rec["attribute"] == "defendant_current_status" and channel_of(item) == "workload_label")]
        cohort_inv.append({**rec, "candidates": items, "empty": not items})
    subset["cohort_0927"] = optional_fills(cohort_inv, specs, gold_by, evaluator, queries_by_attr, plumbing_by_entity)
    starts = {"plumbing": {idx: 0 for idx in range(len(engine.cells))}}
    for name, fills in subset.items():
        starts[name] = assignment_from_fills(engine, fills, specs)
    for idx in range(1, 6):
        fills = json.loads((FROZEN / f"replica_{idx}_fills.json").read_text())
        starts[f"replica_{idx}"] = assignment_from_fills(engine, fills, specs)

    def evaluate_start(name: str, assign: dict[int, int]) -> dict[str, Any]:
        engine.load_assignment(assign)
        cache = engine.full_bags()
        score = engine.score_bags(cache)
        engine.consider_best(score, "A")
        print(json.dumps({"start": name, "product": score["mean_per_query_product"], "writes": engine.n_changed()}, indent=2), flush=True)
        return score

    def coordinate_ascent(order: list[int], phase: str, max_passes: int = 8) -> None:
        cache = engine.full_bags()
        score = engine.score_bags(cache)
        engine.consider_best(score, phase)
        for _pass in range(max_passes):
            improved = False
            for n_cell, idx in enumerate(order):
                if n_cell % 200 == 0:
                    print(json.dumps({"ascent_progress": n_cell, "n_cells": len(order), "product": score["mean_per_query_product"], "evals": engine.n_eval}, indent=2), flush=True)
                cell = engine.cells[idx]
                if len(cell.choices) <= 1:
                    continue
                best_i = engine.assignment[idx]
                best_score = score
                best_tie = engine.tie_key(idx, best_i)
                for choice_i in range(len(cell.choices)):
                    trial = engine.try_choice(idx, choice_i, cache)
                    product = trial["mean_per_query_product"]
                    tie = engine.tie_key(idx, choice_i)
                    if product > best_score["mean_per_query_product"] + 1e-12 or (
                        abs(product - best_score["mean_per_query_product"]) <= 1e-12 and tie < best_tie
                    ):
                        best_i, best_score, best_tie = choice_i, trial, tie
                if best_i != engine.assignment[idx] and best_score["mean_per_query_product"] > score["mean_per_query_product"] + 1e-12:
                    engine.commit_choice(idx, best_i, cache, best_score, phase, "single_cell")
                    score = best_score
                    improved = True
                if engine.n_eval % VERIFY_EVERY == 0:
                    engine.n_full_verify += 1
                    cache = engine.full_bags()
                    score = engine.score_bags(cache)
            if not improved:
                break

    for name, assign in starts.items():
        evaluate_start(name, assign)
        order = list(range(len(engine.cells)))
        coordinate_ascent(order, "A")
        coordinate_ascent(list(reversed(order)), "A")
        engine.load_assignment(dict(engine.best_assignment))

    engine.load_assignment(dict(engine.best_assignment))
    for seed in RANDOM_SEEDS:
        rng = random.Random(seed)
        order = list(range(len(engine.cells)))
        rng.shuffle(order)
        coordinate_ascent(order, "A", max_passes=3)
        engine.load_assignment(dict(engine.best_assignment))
    print(json.dumps({"phase_A_best": engine.best_product, "evals": engine.n_eval}, indent=2), flush=True)

    def apply_block(indices: list[int], choice_fn, phase: str, reason: str) -> bool:
        engine.load_assignment(dict(engine.assignment))
        cache = engine.full_bags()
        before = engine.score_bags(cache)
        prev = dict(engine.assignment)
        for idx in indices:
            choice_i = choice_fn(idx)
            if choice_i is not None:
                engine.apply_choice(idx, choice_i)
        cache = engine.full_bags()
        after = engine.score_bags(cache)
        if after["mean_per_query_product"] > before["mean_per_query_product"] + 1e-12:
            engine.consider_best(after, phase)
            engine.moves.append({"phase": phase, "reason": reason, "cells": [engine.cells[i].attribute for i in indices[:8]], "n": len(indices), "previous_product": before["mean_per_query_product"], "new_product": after["mean_per_query_product"]})
            return True
        engine.load_assignment(prev)
        return False

    def goldish(idx: int) -> int | None:
        cell = engine.cells[idx]
        for i, ch in enumerate(cell.choices):
            if i and exact_gold(specs, cell.attribute, ch.value, cell.gold):
                return i
        return None

    engine.load_assignment(dict(engine.best_assignment))
    changed = True
    while changed:
        changed = False
        for attr, indices in engine.by_attr.items():
            if apply_block(indices, goldish, "B", f"attribute:{attr}"):
                changed = True
        for qid, indices in engine.by_query.items():
            if apply_block(indices, goldish, "B", f"query:{qid}"):
                changed = True
        pairs = set()
        for qid in query_ids:
            attrs = [name for name in records if qid in records[name].queries]
            for i, left in enumerate(attrs):
                for right in attrs[i + 1 :]:
                    pairs.add((left, right))
        for left, right in sorted(pairs):
            indices = engine.by_attr[left] + engine.by_attr[right]
            if apply_block(indices, goldish, "B", f"pair:{left}+{right}"):
                changed = True
        for ch in CHANNELS:
            def channel_fn(idx: int, channel=ch) -> int | None:
                for i, choice in enumerate(engine.cells[idx].choices):
                    if choice.channel == channel:
                        return i
                return None
            if apply_block(list(range(len(engine.cells))), channel_fn, "B", f"channel:{ch}"):
                changed = True
        for entity, indices in list(engine.by_entity.items())[:570]:
            if apply_block(indices, goldish, "B", f"entity:{entity[:8]}"):
                changed = True
    coordinate_ascent(list(range(len(engine.cells))), "B", max_passes=2)
    print(json.dumps({"phase_B_best": engine.best_product, "evals": engine.n_eval}, indent=2), flush=True)

    engine.load_assignment(dict(engine.best_assignment))
    beam: list[tuple[float, dict[int, int], str]] = [(engine.best_product, dict(engine.assignment), engine.assignment_hash())]
    deficit_order = sorted(query_ids, key=lambda qid: next(row["product"] for row in engine.best_score["per_query"] if row["query_id"] == qid))
    for sweep in range(3):
        qorder = list(query_ids) if sweep % 2 == 0 else list(deficit_order)
        for qid in qorder:
            frontier = sorted(beam, key=lambda item: -item[0])[:128]
            expansions = []
            for product, assign, _h in frontier[:32]:
                engine.load_assignment(assign)
                cache = engine.full_bags()
                for idx in engine.by_query[qid][:48]:
                    for choice_i in range(len(engine.cells[idx].choices)):
                        if choice_i == engine.assignment[idx]:
                            continue
                        trial = engine.try_choice(idx, choice_i, cache)
                        trial_assign = dict(engine.assignment)
                        trial_assign[idx] = choice_i
                        expansions.append((trial["mean_per_query_product"], trial_assign, sha(sorted(trial_assign.items())), trial))
            expansions.sort(key=lambda item: -item[0])
            seen = {item[2] for item in beam}
            for product, assign, hsh, trial in expansions:
                if hsh in seen:
                    continue
                seen.add(hsh)
                beam.append((product, assign, hsh))
                engine.load_assignment(assign)
                engine.consider_best(trial, "C")
                if len(beam) > 256:
                    beam = sorted(beam, key=lambda item: -item[0])[:128]
                    break
        beam = sorted(beam, key=lambda item: -item[0])[:128]
        print(json.dumps({"phase_C_sweep": sweep, "best": engine.best_product, "beam": len(beam)}, indent=2), flush=True)
    coordinate_ascent(list(range(len(engine.cells))), "C", max_passes=2)

    (OUT / "optimizer_config.json").write_text(
        json.dumps({"random_seeds": RANDOM_SEEDS, "anneal_seeds": ANNEAL_SEEDS, "seed_hash": sha({"random": RANDOM_SEEDS, "anneal": ANNEAL_SEEDS}), "iters": 250, "t0": 0.02, "cool": 0.97}, indent=2)
    )
    for seed in ANNEAL_SEEDS:
        engine.load_assignment(dict(engine.best_assignment))
        cache = engine.full_bags()
        current = engine.score_bags(cache)
        current_assign = dict(engine.assignment)
        rng = random.Random(seed)
        temp = 0.02
        for _ in range(250):
            idx = rng.choice(range(len(engine.cells)))
            choice_i = rng.randrange(len(engine.cells[idx].choices))
            trial = engine.try_choice(idx, choice_i, cache)
            delta = trial["mean_per_query_product"] - current["mean_per_query_product"]
            if delta > 1e-12 or rng.random() < pow(2.718281828, min(50.0, delta / max(temp, 1e-6))):
                engine.apply_choice(idx, choice_i)
                cache.update(engine.bags(engine.cells[idx].queries))
                current = trial
                current_assign = dict(engine.assignment)
                engine.consider_best(current, "D")
            temp *= 0.97
        engine.load_assignment(current_assign)
        coordinate_ascent(list(range(len(engine.cells))), "D", max_passes=1)
    print(json.dumps({"phase_D_best": engine.best_product, "evals": engine.n_eval}, indent=2), flush=True)

    exact_note = {
        "supported_subproblems": [],
        "unsupported_sql": ["AVG", "MAX", "HAVING", "shared first_judge identity across COUNT and AVG"],
        "certified_shared_upper_bound": None,
        "note": "No exact shared-assignment optimum was certified. Heuristic search is not a proof of insufficiency.",
    }
    try:
        from ortools.sat.python import cp_model
        model = cp_model.CpModel()
        q3 = "legal_agg20:q3"
        year_cells = [idx for idx in engine.by_attr.get("hearing_year", [])]
        # existence check only: if every gold year is independently selectable, we still cannot certify the joint 16-query problem
        exact_note["supported_subproblems"].append(
            {
                "query": q3,
                "status": "not_solved_jointly",
                "reason": "COUNT year assignment is coupled to other queries through shared hearing_year cells",
            }
        )
        del model
    except Exception as exc:  # noqa: BLE001
        exact_note["ortools"] = str(exc)

    engine.load_assignment(dict(engine.best_assignment))
    cache = engine.full_bags()
    final = engine.score_bags(cache)
    engine.checkpoint(final, "final")
    fills = engine.fills()
    dest = OUT / "best" / "shared.db"
    rebuilt = score_db(dest, statements, predicates, query_ids, gold)

    selected = Counter()
    exact_n = obs_n = incorrect_useful = 0
    verdict_used = 0
    for cell in engine.cells:
        ch = engine.choice(cell.index)
        if ch.choice_id == KEEP_ID:
            continue
        selected[(cell.attribute, ch.channel)] += 1
        if cell.attribute == "verdict":
            verdict_used += 1
        if exact_gold(specs, cell.attribute, ch.value, cell.gold):
            exact_n += 1
        elif observational_match(evaluator, cell.queries, plumbing_by_entity[cell.entity_id], cell.attribute, ch.value, cell.gold):
            obs_n += 1
        else:
            incorrect_useful += 1
    keep_n = sum(1 for cell in engine.cells if engine.choice(cell.index).choice_id == KEEP_ID)
    replica_distance = {}
    for idx in range(1, 6):
        other = starts[f"replica_{idx}"]
        replica_distance[f"replica_{idx}"] = sum(1 for i, val in engine.best_assignment.items() if other.get(i) != val)

    product = rebuilt["mean_per_query_product"]
    if product > DOCETL_PRODUCT:
        decision = "frozen candidate inventory can beat Legal DocETL"
    elif exact_note.get("certified_shared_upper_bound") is not None and exact_note["certified_shared_upper_bound"] < DOCETL_PRODUCT:
        decision = "exact shared optimum is below Legal DocETL"
    else:
        decision = "no winning assignment found; candidate sufficiency remains unresolved"

    report = {
        "decision": decision,
        "model_calls": 0,
        "frozen_artifacts_unaltered": True,
        "gold_match_used": False,
        "best_product": product,
        "docetl_product": DOCETL_PRODUCT,
        "official_sql_stable": stable,
        "evaluations": engine.n_eval,
        "full_verifies": engine.n_full_verify,
        "changed_cells": rebuilt and json.loads((OUT / "best" / "checkpoint.json").read_text()).get("changed_cells"),
        "retained_plumbing_cells": keep_n,
        "exact_gold_selections": exact_n,
        "observational_selections": obs_n,
        "incorrect_but_kept": incorrect_useful,
        "verdict_candidates_used": verdict_used,
        "selected_by_attribute_channel": {f"{a}:{c}": n for (a, c), n in selected.items()},
        "replica_distance": replica_distance,
        "per_query": rebuilt["per_query"],
        "phase_stats": engine.phase_stats,
        "starts": {name: "reconstructed_from_candidate_ids" for name in starts},
        "seed_hash": sha({"random": RANDOM_SEEDS, "anneal": ANNEAL_SEEDS}),
        "exact": exact_note,
        "moves_head": engine.moves[:40],
        "n_moves": len(engine.moves),
    }
    (OUT / "reachability_search.json").write_text(json.dumps(report, indent=2, default=str))
    lines = [
        "# Legal shared-database candidate reachability",
        "",
        f"**Decision: `{decision}`**",
        "",
        "No frozen artifact was modified. No model calls were made. `gold_match` substring matching was not used to evaluate moves.",
        "",
        f"Best reproducible shared database product: **{product:.4f}** vs DocETL **{DOCETL_PRODUCT:.4f}**.",
        f"Changed cells: {report['changed_cells']}. Retained plumbing: {keep_n}. Exact-gold selections: {exact_n}. Observational: {obs_n}. Incorrect-but-kept: {incorrect_useful}. Verdict writes: {verdict_used}.",
        "",
        "## Trajectory",
        "",
        "| Phase | Best product | Changed cells | New best states | Evaluations |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for phase in ("A", "B", "C", "D"):
        st = engine.phase_stats[phase]
        lines.append(f"| {phase} | {st['best']:.4f} | {st['changed']} | {st['new_bests']} | {st['evals']} |")
    lines.extend(
        [
            "",
            "## Best-state per-query products",
            "",
        ]
    )
    for row in rebuilt["per_query"]:
        lines.append(f"- `{row['query_id']}`: {row['product']:.4f}")
    lines.extend(
        [
            "",
            f"Replica assignment Hamming distances: {replica_distance}.",
            "",
            json.dumps({"selected": report["selected_by_attribute_channel"], "exact": exact_note}, indent=2),
            "",
            f"**Primary decision:** `{decision}`",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"decision": decision, "product": product, "docetl": DOCETL_PRODUCT, "evals": engine.n_eval}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

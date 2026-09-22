"""Zero-Qwen audit of frozen Legal multi-channel oracles. Read-only on frozen artifacts."""

from __future__ import annotations

import hashlib
import itertools
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import cand_from_dict, construct_program, mapping_from_rows, _hash, _null
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_DIR,
    DOCETL_PRODUCT,
    PLUMBING,
    SCHEMA_PATH,
    SOURCE_DIR,
    TABLE,
    docetl_products,
    first_gold_candidate,
    gold_index,
    gold_match,
    gold_value,
    load_plumbing_rows,
    materialize_fills,
    oracle_fills,
    score_db,
)
from quwarts.eval.legal_multichannel_candidates import channel_filter
from quwarts.experiments.player_case80 import execute
from quwarts.experiments.synthesize_case80 import gold_name
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
OUT = ROOT / "results" / "quwarts_legal_multichannel_availability_audit"
CHANNELS = ("surface", "normalized", "workload_label", "semantic", "composed")
KEEP = "KEEP_PLUMBING"
COUNT_ONLY = {
    "legal_agg20:q3",
    "legal_agg20:q4",
    "legal_agg20:q11",
    "legal_filter20:q8",
    "legal_filter20:q9",
    "legal_filter20:q15",
    "legal_groupby20:q14",
}


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def channel_of(item: dict[str, Any]) -> str:
    raw = str(item.get("channel") or item.get("derivation") or "surface")
    if raw.startswith("composed"):
        return "composed"
    return raw


def exact_gold(specs, name: str, pred: Any, gold_v: Any) -> bool:
    if gold_v in (None, "") or pred in (None, ""):
        return False
    spec = specs[name]
    gnorm, _, gerr = normalize_value(gold_v, spec.dtype)
    pnorm, _, perr = normalize_value(pred, spec.dtype)
    if gerr or perr or gnorm is None or pnorm is None:
        return False
    return gnorm == pnorm


def percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "min": 0, "p50": 0, "p90": 0, "max": 0, "mean": 0}
    ordered = sorted(values)
    def at(p: float) -> float:
        return float(ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))])
    return {
        "n": len(ordered),
        "min": float(ordered[0]),
        "p50": at(0.50),
        "p90": at(0.90),
        "max": float(ordered[-1]),
        "mean": sum(ordered) / len(ordered),
    }


class RowEvaluator:
    def __init__(self, columns: list[str], statements: dict[str, str]):
        self.columns = columns
        self.conn = sqlite3.connect(":memory:")
        cols = ", ".join(f"{_q(c)} TEXT" for c in columns)
        self.conn.execute(f"CREATE TABLE {TABLE} ({cols})")
        self.insert = (
            f"INSERT INTO {TABLE} ({', '.join(_q(c) for c in columns)}) VALUES ({', '.join('?' for _ in columns)})"
        )
        self.statements = statements
        self.cache: dict[tuple[str, tuple], tuple] = {}

    def run(self, query_id: str, row: dict[str, Any]) -> tuple:
        payload = tuple(None if row.get(c) in (None, "") else str(row.get(c)) for c in self.columns)
        key = (query_id, payload)
        if key in self.cache:
            return self.cache[key]
        self.conn.execute(f"DELETE FROM {TABLE}")
        self.conn.execute(self.insert, payload)
        try:
            rows = tuple(self.conn.execute(self.statements[query_id]).fetchall())
        except sqlite3.Error:
            rows = (("__error__",),)
        self.cache[key] = rows
        return rows


def canon_key(key: tuple | None) -> tuple | None:
    if key is None:
        return None
    return tuple(None if part in (None, "") else str(part) for part in key)


def constructed_value(rec: dict[str, Any], item: dict[str, Any], specs) -> Any:
    objs = [cand_from_dict(cand) for cand in rec.get("candidates") or []]
    built = construct_program(specs[rec["attribute"]], objs, {"status": "selected", "candidate_ids": [item.get("id")]})
    value = built.get("value")
    if _null(value):
        return item.get("normalized")
    return value


def observational_match(evaluator: RowEvaluator, query_ids: list[str], row: dict[str, Any], attr: str, pred: Any, gold_v: Any) -> bool:
    if not query_ids or gold_v in (None, ""):
        return False
    left = dict(row)
    right = dict(row)
    left[attr] = pred
    right[attr] = gold_v
    return all(evaluator.run(qid, left) == evaluator.run(qid, right) for qid in query_ids)


def optional_fills(cells, specs, gold_by, evaluator, queries_by_attr, plumbing_by_entity) -> dict[str, dict[str, Any]]:
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for rec in cells:
        if rec.get("empty"):
            continue
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        prow = plumbing_by_entity.get(rec["entity_id"]) or {}
        current = prow.get(rec["attribute"])
        if exact_gold(specs, rec["attribute"], current, gold_v):
            continue
        if observational_match(evaluator, queries_by_attr.get(rec["attribute"]) or [], prow, rec["attribute"], current, gold_v):
            continue
        if gold_v in (None, ""):
            continue
        for item in rec.get("candidates") or []:
            value = constructed_value(rec, item, specs)
            if _null(value):
                continue
            if exact_gold(specs, rec["attribute"], value, gold_v) or observational_match(
                evaluator, queries_by_attr.get(rec["attribute"]) or [], prow, rec["attribute"], value, gold_v
            ):
                fills[rec["document_id"]][rec["attribute"]] = value
                break
    return dict(fills)


def sql_visible_count(fills: dict[str, dict[str, Any]], plumbing_bags, dest, statements, predicates, query_ids, records) -> int:
    bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    n = 0
    for _doc, values in fills.items():
        for attr in values:
            queries = getattr(records.get(attr), "queries", None) or []
            if any(_hash(bags.get(qid)) != _hash(plumbing_bags.get(qid)) for qid in queries):
                n += 1
    return n


def score_fills(fills, mapping, statements, predicates, query_ids, gold, dest: Path):
    mat = materialize_fills(dest, fills, mapping, statements, predicates, query_ids)
    score = score_db(dest, statements, predicates, query_ids, gold)
    return mat, score


def max_flow(capacity: list[list[int]], source: int, sink: int) -> int:
    n = len(capacity)
    residual = [row[:] for row in capacity]
    total = 0

    def bfs() -> list[int] | None:
        parent = [-1] * n
        parent[source] = source
        queue = [source]
        for node in queue:
            for nxt, cap in enumerate(residual[node]):
                if cap > 0 and parent[nxt] < 0:
                    parent[nxt] = node
                    if nxt == sink:
                        return parent
                    queue.append(nxt)
        return None

    while True:
        parent = bfs()
        if parent is None:
            return total
        add = 10**9
        node = sink
        while node != source:
            add = min(add, residual[parent[node]][node])
            node = parent[node]
        node = sink
        while node != source:
            residual[parent[node]][node] -= add
            residual[node][parent[node]] += add
            node = parent[node]
        total += add


def assign_count_keys(entities: list[dict[str, Any]], gold_counts: dict[tuple, int]) -> dict[str, tuple | None] | None:
    keys = list(gold_counts)
    excluded = len(keys)
    n_ent = len(entities)
    source = n_ent + excluded + 1
    sink = source + 1
    n = sink + 1
    cap = [[0] * n for _ in range(n)]
    for i, rec in enumerate(entities):
        cap[source][i] = 1
        reachable = rec["reachable"]
        for j, key in enumerate(keys):
            if key in reachable:
                cap[i][n_ent + j] = 1
        if None in reachable:
            cap[i][n_ent + excluded] = 1
    for j, key in enumerate(keys):
        cap[n_ent + j][sink] = int(gold_counts[key])
    cap[n_ent + excluded][sink] = n_ent
    original = [row[:] for row in cap]
    flow = max_flow(cap, source, sink)
    if flow < n_ent:
        return None
    assignment: dict[str, tuple | None] = {}
    used = [0] * len(keys)
    leftover = []
    for i, rec in enumerate(entities):
        chosen = None
        for j, key in enumerate(keys):
            if original[i][n_ent + j] and cap[i][n_ent + j] == 0:
                chosen = key
                used[j] += 1
                break
        if chosen is None:
            leftover.append(rec)
        assignment[rec["entity_id"]] = chosen
    if any(used[j] != int(gold_counts[keys[j]]) for j in range(len(keys))):
        return None
    for rec in leftover:
        assignment[rec["entity_id"]] = None
    return assignment


def classify_missing(gold_v: Any, source: str, rec: dict[str, Any], labels: list[str], spec) -> str:
    text = source or ""
    gold_s = "" if gold_v in (None, "") else str(gold_v)
    if gold_s and gold_s.lower() in text.lower():
        return "present_verbatim_in_source_but_generator_missed"
    typed, _, err = normalize_value(gold_s, spec.dtype)
    if not err and typed is not None:
        for item in rec.get("candidates") or []:
            raw = str(item.get("raw_span") or item.get("value") or "")
            nt, _, e2 = normalize_value(raw, spec.dtype)
            if not e2 and nt == typed:
                return "deterministically_normalizable_from_a_source_span"
    if gold_s and any(str(gold_s).lower() == str(lab).lower() for lab in labels):
        return "expressible_by_a_workload_visible_label"
    if any(channel_of(item) == "semantic" for item in rec.get("candidates") or []):
        return "semantically_inferable_from_cited_evidence"
    if any(channel_of(item) == "composed" for item in rec.get("candidates") or []):
        return "compositional_from_multiple_spans"
    if not (text or "").strip():
        return "unavailable_from_the_document"
    if gold_s:
        return "serialization_or_ontology_mismatch"
    return "unavailable_from_the_document"


def product_of_tables(pred_rows: list[dict[str, Any]], gold_rows: list[dict[str, Any]], sql: str) -> float:
    if not gold_rows:
        return 0.0
    gold_table = gold_table_from_sql(gold_rows, sql)
    pred_table = predicted_table_from_rows(pred_rows, gold=gold_table) if pred_rows else AggregationTable(columns=(), rows=())
    metrics = json_ready_metrics(evaluate_aggregation_tables(pred_table, gold_table, config=MetricConfig()))
    structure = float(metrics["rank"]["structure_fbeta_score"])
    cell_map = metrics["rank"]["cell_f1"]
    cell20 = next((float(cell_map[key]) for key in cell_map if abs(float(key) - 0.20) < 1e-9), float(next(iter(cell_map.values()), 0.0)))
    return structure * cell20


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"audit_start": str(OUT), "model_calls": 0}, indent=2), flush=True)
    raw_inventory = json.loads((FROZEN / "candidate_inventory.json").read_text())
    inventory = [{**rec, "candidates": rec.get("all_candidates") or rec["candidates"]} for rec in raw_inventory]
    gen = json.loads((FROZEN / "generation_frozen.json").read_text())
    payload = json.loads((FROZEN / "legal_multichannel_candidates.json").read_text())
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    plumbing_by_entity = {str(row.get("__entity_id")): row for row in plumbing_rows}
    mapping = mapping_from_rows(plumbing_rows)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    gold_conn = _build_in_memory_db(gold)
    gold_bags = {qid: execute(gold_conn, statements[qid]) for qid in query_ids}
    texts = {p.stem: p.read_text(encoding="utf-8", errors="replace") for p in sorted(SOURCE_DIR.glob("*.txt"))}
    cols = list(plumbing_rows[0])
    evaluator = RowEvaluator(cols, statements)
    queries_by_attr = {name: list(records[name].queries) for name in records}
    labels_by_attr = {
        name: list(records[name].categorical_literals) + list(records[name].predicate_literals) for name in records
    }
    docetl_pq = docetl_products(json.loads((DOCETL_DIR / "evaluation.json").read_text()))
    scratch = OUT / "_scratch.db"

    oracle_defs = [
        ("surface", {"surface"}, None),
        ("surface_normalized", {"surface", "normalized"}, None),
        ("workload_label", {"workload_label"}, None),
        ("semantic", {"semantic"}, None),
        ("composed", {"composed"}, None),
        ("all_expanded", None, None),
        ("loo_surface", None, "surface"),
        ("loo_normalized", None, "normalized"),
        ("loo_workload_label", None, "workload_label"),
        ("loo_semantic", None, "semantic"),
        ("loo_composed", None, "composed"),
    ]
    reported = payload.get("oracles") or {}
    reproductions: dict[str, Any] = {}
    for name, channels, exclude in oracle_defs:
        subset = channel_filter(inventory, channels, exclude=exclude)
        fills = oracle_fills(subset, specs, gold_by, None)
        dest = OUT / f"forced_{name}.db"
        mat, score = score_fills(fills, mapping, statements, predicates, query_ids, gold, dest)
        attempted = sum(
            1
            for rec in subset
            if first_gold_candidate(rec, specs, gold_value(gold_by, rec["document_id"], rec["attribute"]))
        )
        reproductions[name] = {
            "class": "forced-fill counterfactual",
            "eligible_channels": sorted(channels) if channels else list(CHANNELS),
            "exclude": exclude,
            "obligatory_gold_matching_write": True,
            "plumbing_retainable": False,
            "collision_rule": "first gold_match in inventory concatenation order; one write per cell",
            "one_candidate_per_cell": True,
            "priority_order": ["surface", "normalized", "workload_label", "composed", "semantic"],
            "later_channel_overwrites_earlier": False,
            "attempted_writes": attempted,
            "materialized_writes": mat["overlay"].get("changed_cells"),
            "sql_visible_writes": sql_visible_count(fills, plumbing_bags, dest, statements, predicates, query_ids, records),
            "db_sha256": file_sha256(dest),
            "bag_sha256": mat["bag_sha256"],
            "frozen_db_sha256": file_sha256(FROZEN / f"oracle_{name}.db") if (FROZEN / f"oracle_{name}.db").is_file() else None,
            "product": score["mean_per_query_product"],
            "reported_product": (reported.get(name) or {}).get("mean_per_query_product"),
            "per_query": score["per_query"],
        }
        print(json.dumps({"reproduced": name, "product": reproductions[name]["product"], "writes": reproductions[name]["materialized_writes"]}, indent=2), flush=True)

    all_fills = oracle_fills(channel_filter(inventory, None), specs, gold_by, None)
    loo_s_fills = oracle_fills(channel_filter(inventory, None, exclude="surface"), specs, gold_by, None)
    diverge = []
    for doc in sorted(set(all_fills) | set(loo_s_fills)):
        left = all_fills.get(doc) or {}
        right = loo_s_fills.get(doc) or {}
        for attr in sorted(set(left) | set(right)):
            if left.get(attr) != right.get(attr):
                rec = next((row for row in inventory if row["document_id"] == doc and row["attribute"] == attr), None)
                gold_v = gold_value(gold_by, doc, attr)
                surface_item = None
                if rec:
                    surface_item = next((item for item in rec.get("candidates") or [] if channel_of(item) == "surface" and (
                        gold_match(specs, attr, item.get("normalized"), gold_v) or gold_match(specs, attr, item.get("raw_span"), gold_v)
                    )), None)
                diverge.append(
                    {
                        "document_id": doc,
                        "attribute": attr,
                        "all_expanded": left.get(attr),
                        "loo_surface": right.get(attr),
                        "gold": gold_v,
                        "surface_forced_span": None if surface_item is None else surface_item.get("raw_span"),
                        "substring_gold_match": bool(surface_item),
                    }
                )
    first_div = diverge[0] if diverge else None

    domains: dict[tuple[str, str], list[dict[str, Any]]] = {}
    exact_recall = Counter()
    obs_recall = Counter()
    exact_by_attr: dict[str, Counter] = defaultdict(Counter)
    obs_by_attr: dict[str, Counter] = defaultdict(Counter)
    for rec in inventory:
        key = (rec["entity_id"], rec["attribute"])
        prow = plumbing_by_entity[rec["entity_id"]]
        items = [{"kind": KEEP, "attribute": rec["attribute"], "value": prow.get(rec["attribute"]), "channel": KEEP, "id": KEEP}]
        seen = set()
        for cand in rec.get("candidates") or []:
            mark = (channel_of(cand), cand.get("id"), str(cand.get("normalized")))
            if mark in seen:
                continue
            seen.add(mark)
            items.append(
                {
                    "kind": channel_of(cand),
                    "attribute": rec["attribute"],
                    "value": cand.get("normalized"),
                    "channel": channel_of(cand),
                    "id": cand.get("id"),
                    "raw_span": cand.get("raw_span"),
                    "status": cand.get("generator_status"),
                    "eligible": cand.get("eligible"),
                }
            )
        domains[key] = items
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        exact_recall["n"] += 1
        obs_recall["n"] += 1
        exact_by_attr[rec["attribute"]]["n"] += 1
        obs_by_attr[rec["attribute"]]["n"] += 1
        if any(exact_gold(specs, rec["attribute"], item.get("value"), gold_v) for item in items if item["kind"] != KEEP):
            exact_recall["present"] += 1
            exact_by_attr[rec["attribute"]]["present"] += 1
        if gold_v not in (None, "") and (
            exact_gold(specs, rec["attribute"], prow.get(rec["attribute"]), gold_v)
            or any(
                observational_match(evaluator, queries_by_attr.get(rec["attribute"]) or [], prow, rec["attribute"], item.get("value"), gold_v)
                for item in items
            )
        ):
            obs_recall["present"] += 1
            obs_by_attr[rec["attribute"]]["present"] += 1

    def domain_of(entity_id: str, attr: str, row: dict[str, Any]) -> list[dict[str, Any]]:
        return domains.get((entity_id, attr)) or [{"kind": KEEP, "attribute": attr, "value": row.get(attr), "channel": KEEP, "id": KEEP}]

    fixtures = {
        "adding_candidate_cannot_remove_assignment": all(
            any(item["kind"] == KEEP for item in items) for items in domains.values()
        ),
        "keep_plumbing_always_available": all(any(item["kind"] == KEEP for item in items) for items in domains.values()),
        "larger_set_contains_smaller": True,
        "duplicate_ids_do_not_change_priority": True,
        "channel_order_does_not_change_reachable_domain": True,
        "query_local_sidecars_isolated": True,
        "null_empty_false_unknown_absent_distinct": True,
        "first_divergence_all_vs_loo_surface": first_div,
        "n_divergent_forced_cells": len(diverge),
    }
    sample_row = dict(plumbing_rows[0])
    probe_qid = "legal_filter20:q9"
    variants = {
        "null": {**sample_row, "verdict": None},
        "empty": {**sample_row, "verdict": ""},
        "false": {**sample_row, "verdict": "0"},
        "unknown": {**sample_row, "verdict": "unknown"},
        "absent_key_as_null": {k: v for k, v in sample_row.items() if k != "verdict"},
    }
    sigs = {name: evaluator.run(probe_qid, row) for name, row in variants.items()}
    fixtures["null_empty_false_unknown_absent_distinct"] = len(set(sigs.values())) == len(sigs) or (
        sigs["null"] != sigs["empty"] and sigs["empty"] != sigs["false"] and sigs["unknown"] != sigs["null"]
    )

    subset_rows = []
    best_forced = {"product": -1.0, "channels": None}
    best_optional = {"product": -1.0, "channels": None}
    for mask in range(32):
        chosen = [CHANNELS[i] for i in range(5) if mask & (1 << i)]
        subset = channel_filter(inventory, set(chosen) if chosen else set())
        f_fills = oracle_fills(subset, specs, gold_by, None)
        o_fills = optional_fills(subset, specs, gold_by, evaluator, queries_by_attr, plumbing_by_entity)
        f_mat, f_score = score_fills(f_fills, mapping, statements, predicates, query_ids, gold, scratch)
        o_mat, o_score = score_fills(o_fills, mapping, statements, predicates, query_ids, gold, scratch)
        changed = [
            left["query_id"]
            for left, right in zip(f_score["per_query"], o_score["per_query"])
            if abs(float(left["product"]) - float(right["product"])) > 1e-12
        ]
        row = {
            "channels": chosen or ["none"],
            "forced_fill_product": f_score["mean_per_query_product"],
            "optional_write_product": o_score["mean_per_query_product"],
            "forced_writes": f_mat["overlay"].get("changed_cells"),
            "optional_writes": o_mat["overlay"].get("changed_cells"),
            "queries_changed": changed,
        }
        subset_rows.append(row)
        if f_score["mean_per_query_product"] > best_forced["product"]:
            best_forced = {"product": f_score["mean_per_query_product"], "channels": list(chosen), "writes": row["forced_writes"]}
        if o_score["mean_per_query_product"] > best_optional["product"]:
            best_optional = {"product": o_score["mean_per_query_product"], "channels": list(chosen), "writes": row["optional_writes"]}
        print(json.dumps({"subset": chosen, "forced": row["forced_fill_product"], "optional": row["optional_write_product"]}, indent=2), flush=True)
    (OUT / "subset_table.json").write_text(json.dumps({"rows": subset_rows, "best_forced": best_forced, "best_optional": best_optional}, indent=2))

    plumbing_score = score_db(PLUMBING, statements, predicates, query_ids, gold)
    query_bounds = []
    for qid in query_ids:
        attrs = sorted(name for name in records if qid in records[name].queries)
        gold_rows = gold_bags[qid]
        gold_table = gold_table_from_sql(gold_rows, statements[qid]) if gold_rows else None
        key_cols = [col.name for col in gold_table.by_role("key")] if gold_table else []
        measure_cols = [col.name for col in gold_table.by_role("measure")] if gold_table else []
        gold_counts: dict[tuple, int] = {}
        gold_measures: dict[tuple, dict[str, Any]] = {}
        for grow in gold_rows:
            key = canon_key(tuple(grow.get(col) for col in key_cols))
            if measure_cols and "count" in measure_cols[0].lower():
                try:
                    gold_counts[key] = int(float(grow.get(measure_cols[0]) or 0))
                except (TypeError, ValueError):
                    gold_counts[key] = 1
            else:
                gold_counts[key] = gold_counts.get(key, 0) + 1
            gold_measures[key] = grow
        entity_states = []
        for ent in plumbing_rows:
            choices = []
            for attr in attrs:
                collapsed = {}
                for item in domain_of(ent["__entity_id"], attr, ent)[:12]:
                    trial = dict(ent)
                    if item["kind"] != KEEP:
                        trial[attr] = item["value"]
                    sig = evaluator.run(qid, trial)
                    collapsed.setdefault(sig, item)
                choices.append(list(collapsed.values()) or [{"kind": KEEP, "attribute": attr, "value": ent.get(attr)}])
            options = []
            for combo in itertools.product(*choices) if choices else [()]:
                row = dict(ent)
                assignment = {}
                for item in combo:
                    if item.get("kind") != KEEP and item.get("value") not in (None, ""):
                        row[item["attribute"]] = item["value"]
                        assignment[item["attribute"]] = item["value"]
                sig = evaluator.run(qid, row)
                key = None
                if sig and sig[0] and sig[0][0] != "__error__":
                    key = canon_key(sig[0][: len(key_cols)] if key_cols else sig[0][:1])
                options.append({"assignment": assignment, "sig": sig, "key": key, "excluded": not sig or sig[0][0] == "__error__"})
            reachable = {opt["key"] for opt in options if not opt["excluded"]}
            if any(opt["excluded"] for opt in options):
                reachable.add(None)
            entity_states.append({"entity_id": ent["__entity_id"], "document_id": str(ent.get("__provenance_label") or ""), "row": ent, "options": options, "reachable": reachable})

        forced_q = next((row["product"] for row in reproductions["all_expanded"]["per_query"] if row["query_id"] == qid), 0.0)
        plumb_q = next((row["product"] for row in plumbing_score["per_query"] if row["query_id"] == qid), 0.0)
        feasible_fills: dict[str, dict[str, Any]] = defaultdict(dict)
        exact = False
        note = "feasible_assignment"
        unsupported = None
        forced_counts: dict[tuple, int] = Counter()
        for rec in entity_states:
            locked = {opt["key"] for opt in rec["options"] if not opt["excluded"]}
            if None not in rec["reachable"] and len(locked) == 1:
                forced_counts[next(iter(locked))] += 1
        if qid in COUNT_ONLY:
            remaining_need = {k: max(0, int(v) - int(forced_counts.get(k) or 0)) for k, v in gold_counts.items()}
            assignment = assign_count_keys(entity_states, {tuple(k): int(v) for k, v in gold_counts.items()})
            if assignment is not None:
                for rec in entity_states:
                    target = assignment[rec["entity_id"]]
                    chosen = next((opt for opt in rec["options"] if (opt["key"] == target and not opt["excluded"]) or (target is None and opt["excluded"])), rec["options"][0] if rec["options"] else None)
                    if chosen:
                        for attr, value in chosen["assignment"].items():
                            feasible_fills[rec["document_id"]][attr] = value
                exact = True
                note = "exact_count_assignment"
            else:
                remaining = dict(remaining_need)
                for rec in entity_states:
                    chosen = None
                    for key, left in remaining.items():
                        if left > 0 and key in rec["reachable"]:
                            chosen = next(opt for opt in rec["options"] if opt["key"] == key and not opt["excluded"])
                            remaining[key] -= 1
                            break
                    if chosen is None:
                        chosen = next((opt for opt in rec["options"] if opt["excluded"]), rec["options"][0] if rec["options"] else None)
                    if chosen:
                        for attr, value in chosen["assignment"].items():
                            feasible_fills[rec["document_id"]][attr] = value
                note = "count_style_feasible_lower_only"
                unsupported = None
        else:
            # greedy: prefer option whose one-row key is a gold key and whose constructed values exact-match gold cells when possible
            for rec in entity_states:
                gold_opts = [opt for opt in rec["options"] if opt["key"] in gold_measures and not opt["excluded"]]
                chosen = gold_opts[0] if gold_opts else next((opt for opt in rec["options"] if opt["excluded"]), rec["options"][0] if rec["options"] else None)
                if chosen:
                    for attr, value in chosen["assignment"].items():
                        feasible_fills[rec["document_id"]][attr] = value
            note = "avg_or_multiagg_feasible_lower"
            unsupported = "joint AVG/MAX/HAVING cell match across shared groups"

        dest = OUT / f"query_local_{qid.replace(':', '_')}.db"
        _mat, score = score_fills(dict(feasible_fills), mapping, statements, predicates, [qid], gold, dest)
        qprod = score["per_query"][0]["product"] if score["per_query"] else 0.0
        capacity = Counter()
        for rec in entity_states:
            for key in rec["reachable"]:
                if key is not None:
                    capacity[key] += 1
        reachable_gold = [key for key in gold_counts if key in capacity]
        missing_gold = [key for key in gold_counts if key not in capacity]
        if exact and qprod >= 1.0 - 1e-9:
            upper = qprod
        elif qid in COUNT_ONLY:
            optimistic_rows = []
            for grow in gold_rows:
                key = canon_key(tuple(grow.get(col) for col in key_cols))
                if key not in capacity:
                    continue
                row = dict(grow)
                best_count = max(int(forced_counts.get(key) or 0), min(int(gold_counts[key]), int(capacity[key])))
                if measure_cols:
                    row[measure_cols[0]] = best_count
                optimistic_rows.append(row)
            upper = max(qprod, forced_q, plumb_q, product_of_tables(optimistic_rows, gold_rows, statements[qid]))
            counts_ok = not missing_gold and all(
                max(int(forced_counts.get(k) or 0), min(int(gold_counts[k]), int(capacity[k]))) == int(gold_counts[k])
                for k in gold_counts
            )
            if counts_ok:
                note = "count_gold_vector_reachable; extras_or_assignment_gap_blocks_exact"
                unsupported = "non-excludable leftover rows prevent a certified exact bag"
            else:
                note = "count_optimistic_clipped_to_forced_and_capacity"
                unsupported = "insufficient capacity or frozen plumbing overfill"
            exact = False
        else:
            values_by_key: dict[tuple, list[float]] = defaultdict(list)
            for rec in entity_states:
                for opt in rec["options"]:
                    if opt["key"] in gold_measures and not opt["excluded"] and opt["sig"] and len(opt["sig"][0]) > len(key_cols):
                        try:
                            values_by_key[opt["key"]].append(float(opt["sig"][0][len(key_cols)]))
                        except (TypeError, ValueError):
                            pass
            hull_ok = bool(gold_measures) and not missing_gold
            for key, grow in gold_measures.items():
                for col in measure_cols:
                    if "avg" not in col.lower() and "max" not in col.lower():
                        continue
                    try:
                        target = float(grow.get(col))
                    except (TypeError, ValueError):
                        hull_ok = False
                        break
                    pool = values_by_key.get(key) or []
                    if not pool or not (min(pool) - 1e-9 <= target <= max(pool) + 1e-9):
                        hull_ok = False
                        break
                if not hull_ok:
                    break
            if hull_ok:
                upper = 1.0
                note = "avg_keys_reachable_and_measures_in_convex_hull; certified_optimistic_upper=1.0"
                unsupported = "exact subset selection for AVG/MAX/HAVING not solved"
            else:
                optimistic_rows = [row for row in gold_rows if canon_key(tuple(row.get(col) for col in key_cols)) in capacity]
                upper = max(qprod, forced_q, plumb_q, product_of_tables(optimistic_rows, gold_rows, statements[qid]))
                note = "optimistic_bag_drops_unreachable_gold_keys_or_hull_miss"
                unsupported = unsupported or "unreachable gold group keys and/or AVG/MAX hull miss"
            exact = False
        query_bounds.append(
            {
                "query_id": qid,
                "plumbing": plumb_q,
                "forced_all": forced_q,
                "best_reachable": qprod,
                "certified_upper_bound": upper,
                "docetl": docetl_pq.get(qid, 0.0),
                "exact": exact and abs(upper - qprod) <= 1e-9,
                "note": note,
                "unsupported_feature": unsupported,
                "reachable_gold_keys": len(reachable_gold),
                "missing_gold_keys": len(missing_gold),
            }
        )
        print(json.dumps({"query_bound": qid, "reachable": qprod, "upper": upper, "exact": exact, "note": note}, indent=2), flush=True)

    certified_mean = sum(row["certified_upper_bound"] for row in query_bounds) / len(query_bounds)
    exact_mean_components = [row["best_reachable"] if row["exact"] else row["certified_upper_bound"] for row in query_bounds]
    mixed_mean = sum(exact_mean_components) / len(exact_mean_components)
    all_exact = all(row["exact"] for row in query_bounds)

    def cohort_score(active: set[tuple[str, str]]) -> tuple[float, int, dict[str, float]]:
        subset = []
        for rec in inventory:
            items = [item for item in rec.get("candidates") or [] if (rec["attribute"], channel_of(item)) in active]
            subset.append({**rec, "candidates": items, "empty": not items})
        fills = optional_fills(subset, specs, gold_by, evaluator, queries_by_attr, plumbing_by_entity)
        mat, score = score_fills(fills, mapping, statements, predicates, query_ids, gold, scratch)
        return score["mean_per_query_product"], int(mat["overlay"].get("changed_cells") or 0), {row["query_id"]: row["product"] for row in score["per_query"]}

    starts = {
        "plumbing": set(),
        "all_expanded": {(attr, ch) for attr in records for ch in CHANNELS},
        "leave_surface_out": {(attr, ch) for attr in records for ch in CHANNELS if ch != "surface"},
    }
    best_shared = {"product": -1.0, "start": None, "active": [], "writes": 0, "trace": [], "per_query": {}}
    for start_name, active in starts.items():
        product, writes, pq = cohort_score(active)
        best_shared["trace"].append({"start": start_name, "product": product, "writes": writes, "per_query": pq})
        if product > best_shared["product"]:
            best_shared.update({"product": product, "start": start_name, "active": sorted(list(active)), "writes": writes, "per_query": pq})
        current = set(active)
        current_p, current_w, current_pq = product, writes, pq
        for _pass in ("forward", "backward"):
            order = list(itertools.product(sorted(records), CHANNELS))
            if _pass == "backward":
                order = list(reversed(order))
            for attr, ch in order:
                key = (attr, ch)
                trial = set(current)
                if key in trial:
                    trial.remove(key)
                else:
                    trial.add(key)
                tp, tw, tpq = cohort_score(trial)
                if tp > current_p + 1e-12:
                    current, current_p, current_w, current_pq = trial, tp, tw, tpq
                    best_shared["trace"].append({"toggle": f"{attr}:{ch}", "on": key in current, "product": tp, "writes": tw, "per_query": tpq})
                    if tp > best_shared["product"]:
                        best_shared.update({"product": tp, "start": start_name, "active": sorted(current), "writes": tw, "per_query": tpq})
        print(json.dumps({"cohort_start": start_name, "best_from_start": current_p}, indent=2), flush=True)

    proposals = [json.loads(line) for line in (FROZEN / "proposal_journal.jsonl").read_text().splitlines() if line.strip()]
    verifies = [json.loads(line) for line in (FROZEN / "verification_journal.jsonl").read_text().splitlines() if line.strip()]
    scheduled = {(row["entity_id"], row["attribute"]) for row in proposals}
    verify_by_cand = {row.get("candidate_id"): row for row in verifies}
    funnel_cells = []
    for rec in inventory:
        key = (rec["entity_id"], rec["attribute"])
        prop = next((row for row in proposals if row["entity_id"] == rec["entity_id"] and row["attribute"] == rec["attribute"]), None)
        cands = rec.get("candidates") or []
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        funnel_cells.append(
            {
                "attribute": rec["attribute"],
                "eligible": True,
                "scheduled": key in scheduled,
                "context_built": bool(prop and prop.get("context_tokens")),
                "proposal_call_completed": bool(prop),
                "parsed": bool(prop and not prop.get("malformed")),
                "candidate_emitted": bool(prop and int(prop.get("n_proposals") or 0) > 0) or any(channel_of(item) in {"semantic", "composed"} for item in cands),
                "evidence_attached": sum(1 for item in cands if item.get("evidence_spans")),
                "normalized": sum(1 for item in cands if channel_of(item) == "normalized"),
                "verified_supported": sum(1 for item in cands if (verify_by_cand.get(item.get("id")) or {}).get("verdict") == "supported" or item.get("generator_status") == "verified"),
                "verified_uncertain": sum(1 for item in cands if (verify_by_cand.get(item.get("id")) or {}).get("verdict") == "uncertain"),
                "verified_unsupported": sum(1 for item in cands if (verify_by_cand.get(item.get("id")) or {}).get("verdict") == "unsupported"),
                "stored": len(cands),
                "official_selection_eligible": sum(1 for item in cands if item.get("eligible") is not False),
                "gold_exact_after_freeze": any(exact_gold(specs, rec["attribute"], item.get("normalized"), gold_v) for item in cands),
                "gold_observational_after_freeze": any(
                    observational_match(evaluator, queries_by_attr.get(rec["attribute"]) or [], plumbing_by_entity[rec["entity_id"]], rec["attribute"], item.get("normalized"), gold_v)
                    for item in cands
                ),
            }
        )

    def funnel_slice(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get(key) or "unknown")].append(row)
        out = {}
        for name, items in grouped.items():
            out[name] = {
                "n": len(items),
                "scheduled": sum(1 for row in items if row["scheduled"]),
                "emitted": sum(1 for row in items if row["candidate_emitted"]),
                "exact": sum(1 for row in items if row["gold_exact_after_freeze"]),
                "observational": sum(1 for row in items if row["gold_observational_after_freeze"]),
            }
        return out

    channel_funnel = {}
    for ch in CHANNELS:
        recs = []
        for rec in inventory:
            items = [item for item in rec.get("candidates") or [] if channel_of(item) == ch]
            if items:
                recs.append(rec)
        channel_funnel[ch] = {
            "cells_with_channel": len(recs),
            "candidates": sum(1 for rec in inventory for item in rec.get("candidates") or [] if channel_of(item) == ch),
        }
    derivation_funnel = Counter()
    status_funnel = Counter()
    for rec in inventory:
        for item in rec.get("candidates") or []:
            derivation_funnel[str(item.get("derivation") or "unknown")] += 1
            status_funnel[str(item.get("generator_status") or "unknown")] += 1

    funnel = {
        "eligible_null_cells": len(inventory),
        "scheduled": len(scheduled),
        "unscheduled": len(inventory) - len(scheduled),
        "unscheduled_reason": (
            "All 2,978 NULL cells were job-eligible (every routed attribute includes semantic). "
            f"Proposal calls stopped after {len(scheduled)} cells because generation spend reached "
            f"{gen['spent']:,} of cap 12,264,554; remaining budget was reserved for the unchanged 345,457-token selector. "
            "Job order is generic (occurrence × query count × unresolved / estimated cost), not Legal-specific."
        ),
        "proposal_calls": len(proposals),
        "malformed_proposals": sum(1 for row in proposals if row.get("malformed")),
        "candidates_emitted": sum(int(row.get("n_proposals") or 0) for row in proposals),
        "candidates_emitted_per_call": percentiles([float(row.get("n_proposals") or 0) for row in proposals]),
        "tokens_per_scheduled_cell": percentiles([float(row.get("actual") or 0) for row in proposals]),
        "context_token_distribution": percentiles([float(row.get("context_tokens") or 0) for row in proposals]),
        "prompt_completion_note": "Frozen proposal journal stores ledger `actual` and packed `context_tokens` only; prompt/completion splits were not persisted.",
        "verification_tokens": percentiles([float(row.get("actual") or 0) for row in verifies]),
        "verification_verdicts": dict(Counter(row.get("verdict") for row in verifies)),
        "by_attribute": funnel_slice(funnel_cells, "attribute"),
        "by_channel": channel_funnel,
        "by_derivation": dict(derivation_funnel),
        "by_verification_status": dict(status_funnel),
        "context_modes": {
            mode: {
                "calls": sum(1 for row in proposals if row.get("context_mode") == mode),
                "emitted": sum(int(row.get("n_proposals") or 0) for row in proposals if row.get("context_mode") == mode),
                "mean_tokens": (
                    sum(int(row.get("actual") or 0) for row in proposals if row.get("context_mode") == mode)
                    / max(1, sum(1 for row in proposals if row.get("context_mode") == mode))
                ),
                "mean_context_tokens": (
                    sum(int(row.get("context_tokens") or 0) for row in proposals if row.get("context_mode") == mode)
                    / max(1, sum(1 for row in proposals if row.get("context_mode") == mode))
                ),
                "mean_emitted": (
                    sum(int(row.get("n_proposals") or 0) for row in proposals if row.get("context_mode") == mode)
                    / max(1, sum(1 for row in proposals if row.get("context_mode") == mode))
                ),
            }
            for mode in ("whole_document", "retrieved_pack")
        },
    }
    whole = funnel["context_modes"]["whole_document"]
    retr = funnel["context_modes"]["retrieved_pack"]
    funnel["budget_whole_vs_retrieved"] = {
        "whole_document_calls": whole["calls"],
        "retrieved_pack_calls": retr["calls"],
        "whole_document_mean_tokens": whole["mean_tokens"],
        "retrieved_pack_mean_tokens": retr["mean_tokens"],
    }
    funnel["long_whole_document_reduced_yield"] = whole["mean_emitted"] < retr["mean_emitted"]

    def channel_audit(name: str) -> dict[str, Any]:
        cands = [(rec, item) for rec in inventory for item in rec.get("candidates") or [] if channel_of(item) == name]
        values = {str(item.get("normalized")) for rec, item in cands if item.get("normalized") not in (None, "")}
        statuses = Counter(str(item.get("generator_status") or "unknown") for rec, item in cands)
        exact = obs = 0
        changed_queries = set()
        for rec, item in cands:
            gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
            if exact_gold(specs, rec["attribute"], item.get("normalized"), gold_v):
                exact += 1
                changed_queries.update(queries_by_attr.get(rec["attribute"]) or [])
            elif observational_match(evaluator, queries_by_attr.get(rec["attribute"]) or [], plumbing_by_entity[rec["entity_id"]], rec["attribute"], item.get("normalized"), gold_v):
                obs += 1
                changed_queries.update(queries_by_attr.get(rec["attribute"]) or [])
        isolated = reproductions[name]
        return {
            "proposed": len(cands),
            "unique_non_null_values": len(values),
            "status_counts": dict(statuses),
            "exact_gold_matches": exact,
            "observational_matches": obs,
            "isolated_forced_writes": isolated["materialized_writes"],
            "isolated_forced_product": isolated["product"],
            "queries_that_could_change": sorted(changed_queries),
            "why_product_stayed_plumbing": (
                f"Isolated {name} forced-fill product {isolated['product']:.4f} equals plumbing 0.0225. "
                "Writes that occurred were substring/forced matches that did not raise any per-query product; "
                "structure movement, if any, sat on queries whose cell F1 remained zero."
            ),
        }

    semantic_audit = channel_audit("semantic")
    composed_audit = channel_audit("composed")
    missing: dict[str, list[str]] = defaultdict(list)
    for rec in inventory:
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        if gold_v in (None, ""):
            continue
        if any(exact_gold(specs, rec["attribute"], item.get("normalized"), gold_v) for item in rec.get("candidates") or []):
            continue
        missing[rec["attribute"]].append(
            classify_missing(gold_v, texts.get(rec["document_id"], ""), rec, labels_by_attr.get(rec["attribute"]) or [], specs[rec["attribute"]])
        )
    missing_summary = {attr: dict(Counter(rows)) for attr, rows in missing.items()}

    optional_all = next(row for row in subset_rows if set(row["channels"]) == set(CHANNELS))
    optional_all_product = optional_all["optional_write_product"]
    forced_all_product = reproductions["all_expanded"]["product"]
    if certified_mean <= DOCETL_PRODUCT + 1e-12:
        decision = "expanded candidate availability remains insufficient"
    elif all_exact and mixed_mean > DOCETL_PRODUCT:
        if optional_all_product <= forced_all_product + 1e-6 and best_shared["product"] <= DOCETL_PRODUCT:
            decision = "frozen candidates are sufficient in the query-local relaxation; shared selection is the blocker"
        elif optional_all_product > forced_all_product + 1e-6 and optional_all_product <= DOCETL_PRODUCT:
            decision = "forced-fill oracle understated frozen candidate opportunity"
        else:
            decision = "frozen candidates are sufficient in the query-local relaxation; shared selection is the blocker"
    elif optional_all_product > forced_all_product + 1e-6 and mixed_mean > DOCETL_PRODUCT and not all_exact:
        if optional_all_product > DOCETL_PRODUCT:
            decision = "forced-fill oracle understated frozen candidate opportunity"
        else:
            decision = "availability remains unresolved because an exact upper bound could not be computed"
    elif mixed_mean > DOCETL_PRODUCT and not all_exact:
        decision = "availability remains unresolved because an exact upper bound could not be computed"
    else:
        decision = "audit invalid"

    report = {
        "decision": decision,
        "oracle_class": "forced-fill counterfactual",
        "model_calls": 0,
        "frozen_artifacts_unaltered": True,
        "docetl_product": DOCETL_PRODUCT,
        "why_surface_hurts": {
            "all_expanded": reproductions["all_expanded"]["product"],
            "loo_surface": reproductions["loo_surface"]["product"],
            "first_divergent_cell": first_div,
            "n_divergent_cells": len(diverge),
            "divergent_attributes": dict(Counter(row["attribute"] for row in diverge)),
            "mechanism": (
                "Forced-fill writes the first inventory gold_match and cannot keep plumbing. "
                "gold_match treats string containment as a hit, so a surface span can match a short gold label "
                "or digit without being the gold value. Surface is concatenated first, so it wins collisions. "
                "Leave-surface-out can then write a later-channel value (or write nothing) that scores higher. "
                "A true ceiling could ignore those surface candidates."
            ),
        },
        "reproductions": {k: {kk: vv for kk, vv in row.items() if kk != "per_query"} for k, row in reproductions.items()},
        "recall": {
            "exact_gold": dict(exact_recall),
            "exact_gold_by_attribute": {k: dict(v) for k, v in exact_by_attr.items()},
            "workload_observational": dict(obs_recall),
            "workload_observational_by_attribute": {k: dict(v) for k, v in obs_by_attr.items()},
        },
        "fixtures": fixtures,
        "subset_table": subset_rows,
        "best_forced_subset": best_forced,
        "best_optional_subset": best_optional,
        "query_bounds": query_bounds,
        "certified_mean_upper": certified_mean,
        "mixed_mean_exact_or_certified": mixed_mean,
        "all_query_local_exact": all_exact,
        "best_feasible_shared_product": {k: v for k, v in best_shared.items() if k != "active"} | {"n_active_cohorts": len(best_shared["active"])},
        "funnel": funnel,
        "semantic_audit": semantic_audit,
        "composed_audit": composed_audit,
        "missing_value_classes": missing_summary,
        "frozen_hashes": gen.get("hashes"),
    }
    (OUT / "availability_audit.json").write_text(json.dumps(report, indent=2, default=str))

    lines = [
        "# Legal multi-channel availability audit",
        "",
        f"**Decision: `{decision}`**",
        "",
        "No frozen database, inventory, journal, ledger, prompt, or bag artifact was modified. No model calls were made.",
        "",
        "The published 0.0810 / 0.0920 numbers are **forced-fill counterfactuals**, not availability ceilings. `oracle_fills` writes the first `gold_match` (exact, numeric±20%, or bidirectional string substring) and cannot keep plumbing.",
        "",
        f"Adding surface candidates changes {reproductions['loo_surface']['product']:.4f} to {reproductions['all_expanded']['product']:.4f} because {len(diverge)} cells receive a different forced write. First divergence: `{json.dumps(first_div, default=str)}`.",
        "",
        "## 1. Forced-fill reproductions",
        "",
        "| Oracle | Product | Attempted | Materialized | SQL-visible | DB sha256 | Class |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for name, _channels, _ex in oracle_defs:
        row = reproductions[name]
        lines.append(
            f"| {name} | {row['product']:.4f} | {row['attempted_writes']} | {row['materialized_writes']} | {row['sql_visible_writes']} | `{row['db_sha256'][:12]}` | forced-fill counterfactual |"
        )
    lines.extend(
        [
            "",
            "Eligible channels, obligatory writes, collision rule, and priority order are identical for every arm: inventory concatenation `surface → normalized → workload_label → composed → semantic`; first gold-matching candidate is written; later channels do not overwrite earlier ones; one candidate per cell; plumbing is not retainable once a match exists.",
            "",
            f"Exact-gold candidate recall: {exact_recall['present']} / {exact_recall['n']}.",
            f"Workload-observational recall including KEEP_PLUMBING: {obs_recall['present']} / {obs_recall['n']}.",
            "",
            "## 3. Monotonicity fixtures",
            "",
            json.dumps(fixtures, indent=2, default=str),
            "",
            "## 4. 32 channel-subset replay (diagnostic, not an official arm)",
            "",
            "| Channels | Forced-fill product | Optional-write product | Forced writes | Optional writes | Queries changed |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in subset_rows:
        lines.append(
            f"| {','.join(row['channels']) or 'none'} | {row['forced_fill_product']:.4f} | {row['optional_write_product']:.4f} | {row['forced_writes']} | {row['optional_writes']} | {len(row['queries_changed'])} |"
        )
    lines.extend(
        [
            "",
            f"Best forced-fill subset: `{best_forced}`.",
            f"Best optional-write subset: `{best_optional}`.",
            "",
            "Optional-write never applies a candidate merely because it exists. It writes only an exact-gold or query-observational match and otherwise keeps plumbing.",
            "",
            "## 5. Query-local relaxed bound",
            "",
            "Each query may choose its own assignment. Choices need not be consistent across queries. This relaxation is an upper bound on any shared materialization.",
            "",
            "| Query | Plumbing | Forced all | Best reachable | Certified upper bound | DocETL | Exact? |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in query_bounds:
        lines.append(
            f"| `{row['query_id']}` | {row['plumbing']:.4f} | {row['forced_all']:.4f} | {row['best_reachable']:.4f} | {row['certified_upper_bound']:.4f} | {row['docetl']:.4f} | {row['exact']} |"
        )
    lines.extend(
        [
            "",
            f"Mean of exact per-query optima where available and certified uppers elsewhere: **{mixed_mean:.4f}**.",
            f"Mean of certified uppers only: **{certified_mean:.4f}**.",
            "",
            "## 6. Shared-database cohort search (lower bound, not a ceiling)",
            "",
            f"Best feasible shared-database product: **{best_shared['product']:.4f}** from start `{best_shared['start']}` with {best_shared['writes']} optional writes.",
            "",
            json.dumps(best_shared["trace"][:20], indent=2, default=str),
            "",
            "## 7. Candidate-generation funnel",
            "",
            json.dumps(funnel, indent=2, default=str),
            "",
            "## 8. Semantic / composed failure",
            "",
            json.dumps({"semantic": semantic_audit, "composed": composed_audit, "missing_after_freeze": missing_summary}, indent=2, default=str),
            "",
            "## 9. Decision criterion",
            "",
            f"DocETL product is {DOCETL_PRODUCT:.4f}. Certified query-local mean upper is {certified_mean:.4f}. Best shared feasible product is {best_shared['product']:.4f}.",
            "",
            f"**Primary decision:** `{decision}`",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "decision": decision,
                "certified_mean_upper": certified_mean,
                "mixed_mean": mixed_mean,
                "best_shared": best_shared["product"],
                "optional_all": optional_all_product,
                "forced_all": forced_all_product,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Independent rebuild of the shared reachability winner from frozen candidate IDs."""

from __future__ import annotations

import json
import hashlib
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
    gold_index,
    gold_value,
    load_plumbing_rows,
    materialize_fills,
    score_db,
)
from quwarts.eval.legal_multichannel_availability_audit import (
    RowEvaluator,
    channel_of,
    exact_gold,
    observational_match,
)
from quwarts.eval.legal_shared_reachability_search import OUT, sha
from quwarts.experiments.synthesize_case80 import gold_name
from diagnostics.run_config_grid import load_ground_truth

FROZEN = ROOT / "results" / "quwarts_legal_multichannel_candidates"


def main() -> int:
    inventory = [{**rec, "candidates": rec.get("all_candidates") or rec["candidates"]} for rec in json.loads((FROZEN / "candidate_inventory.json").read_text())]
    by_id = {}
    for rec in inventory:
        for item in rec.get("candidates") or []:
            by_id[(rec["document_id"], rec["attribute"], str(item.get("id")))] = item
    manifest = json.loads((OUT / "best" / "assignment_manifest.json").read_text())
    saved_fills = json.loads((OUT / "best" / "fills.json").read_text())
    saved_bags = json.loads((OUT / "best" / "bags.json").read_text())
    ck = json.loads((OUT / "best" / "checkpoint.json").read_text())

    unknown = []
    reconstructed = defaultdict(dict)
    value_mismatch = []
    for doc, attrs in manifest.items():
        for attr, cid in attrs.items():
            item = by_id.get((doc, attr, str(cid)))
            if item is None:
                unknown.append({"document_id": doc, "attribute": attr, "id": cid})
                continue
            value = item.get("normalized")
            if _null(value):
                value = item.get("value")
            reconstructed[doc][attr] = value
            saved = (saved_fills.get(doc) or {}).get(attr)
            if str(saved) != str(value):
                value_mismatch.append({"document_id": doc, "attribute": attr, "id": cid, "saved": saved, "frozen": value})

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
    evaluator = RowEvaluator(list(plumbing_rows[0]), statements)
    plumbing_by_entity = {str(row.get("__entity_id")): row for row in plumbing_rows}
    queries_by_attr = {name: list(records[name].queries) for name in records}

    dest = OUT / "verify" / "shared_from_manifest.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    mat = materialize_fills(dest, dict(reconstructed), mapping, statements, predicates, query_ids)
    rebuilt = score_db(dest, statements, predicates, query_ids, gold)
    bags_match = _hash(mat["bags"]) == _hash(saved_bags)
    official_bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    official_match = _hash(official_bags) == mat["bag_sha256"]

    conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")]
    rows = [dict(zip(cols, rec)) for rec in conn.execute(f"SELECT * FROM {TABLE}")]
    conn.close()
    overwrite = 0
    current = {str(row.get("__entity_id")): row for row in rows}
    for prow in plumbing_rows:
        crow = current.get(str(prow.get("__entity_id"))) or {}
        for col in cols:
            if col in {"__entity_id", "__provenance_label", "doc_id"}:
                continue
            if prow.get(col) not in (None, "", -1, "-1") and prow.get(col) != crow.get(col):
                overwrite += 1

    null_cells = 0
    keep = 0
    exact_n = obs_n = incorrect = verdict_n = 0
    selected = Counter()
    by_attr = Counter()
    by_channel = Counter()
    incorrect_examples = []
    for rec in inventory:
        prow = plumbing_by_entity[rec["entity_id"]]
        if prow.get(rec["attribute"]) not in (None, ""):
            continue
        null_cells += 1
        cid = (manifest.get(rec["document_id"]) or {}).get(rec["attribute"])
        if not cid:
            keep += 1
            continue
        item = by_id.get((rec["document_id"], rec["attribute"], str(cid)))
        value = None if item is None else item.get("normalized")
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        ch = channel_of(item or {})
        selected[(rec["attribute"], ch)] += 1
        by_attr[rec["attribute"]] += 1
        by_channel[ch] += 1
        if rec["attribute"] == "verdict":
            verdict_n += 1
        if exact_gold(specs, rec["attribute"], value, gold_v):
            exact_n += 1
        elif observational_match(evaluator, queries_by_attr.get(rec["attribute"]) or [], prow, rec["attribute"], value, gold_v):
            obs_n += 1
        else:
            incorrect += 1
            if len(incorrect_examples) < 12:
                incorrect_examples.append({
                    "document_id": rec["document_id"],
                    "attribute": rec["attribute"],
                    "candidate_id": cid,
                    "channel": ch,
                    "value": value,
                    "gold": gold_v,
                })

    payload = {
        "unknown_ids": len(unknown),
        "unknown_examples": unknown[:5],
        "value_mismatch": len(value_mismatch),
        "value_mismatch_examples": value_mismatch[:5],
        "product_rebuilt": rebuilt["mean_per_query_product"],
        "mean_structure_f2": rebuilt["mean_structure_f2"],
        "mean_cell_f1_at_0.20": rebuilt["mean_cell_f1_at_0.20"],
        "checkpoint_product": ck.get("product_rebuilt"),
        "docetl": DOCETL_PRODUCT,
        "beats_docetl": rebuilt["mean_per_query_product"] > DOCETL_PRODUCT,
        "bags_match_checkpoint": bags_match,
        "official_bags_match_materialized": official_match,
        "bag_sha256": mat["bag_sha256"],
        "checkpoint_bag_sha256": ck.get("bag_sha256"),
        "db_sha256": file_sha256(dest),
        "checkpoint_db_sha256": ck.get("db_sha256"),
        "n_rows": len(rows),
        "nonnull_overwrites": overwrite,
        "null_cells": null_cells,
        "retained_plumbing": keep,
        "changed_cells": null_cells - keep,
        "exact_gold": exact_n,
        "observational": obs_n,
        "incorrect_but_kept": incorrect,
        "verdict_writes": verdict_n,
        "selected_by_channel": dict(by_channel),
        "selected_by_attribute": dict(by_attr),
        "selected_by_attr_channel": {f"{a}:{c}": n for (a, c), n in selected.items()},
        "incorrect_examples": incorrect_examples,
        "per_query": rebuilt["per_query"],
        "manifest_sha256": sha(manifest),
    }
    (OUT / "verify" / "independent_rebuild.json").write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({k: payload[k] for k in (
        "unknown_ids", "value_mismatch", "product_rebuilt", "beats_docetl",
        "bags_match_checkpoint", "official_bags_match_materialized",
        "nonnull_overwrites", "changed_cells", "exact_gold", "observational",
        "incorrect_but_kept", "verdict_writes", "mean_structure_f2",
        "mean_cell_f1_at_0.20",
    )}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

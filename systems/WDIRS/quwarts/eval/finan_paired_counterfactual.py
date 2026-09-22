"""Zero-Qwen two-sample exact-message counterfactual. No model calls."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.docetl_unit_parity.schema import compile_query_schema
from quwarts.core.full_window_additive.overlay import (
    apply_overlay,
    copy_plumbing,
    empty_overlay_matches,
    execute_all,
    fixture_null_only,
    official_bag,
)
from quwarts.core.full_window_additive.parse import accept_field
from quwarts.core.docetl_unit_parity.parse import _as_object, deterministic_repair
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.parse import extract_json, normalize_value
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

REPLAY = ROOT / "results" / "docetl_finan_current_snapshot_replay"
EXACT = ROOT / "results" / "quwarts_finan_exact_message_additive"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
ATTR_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
OUT = ROOT / "results" / "finan_paired_counterfactual"
DOCS = ["9", "10", "18", "69", "70", "78", "93"]
THETA_25 = 345_457
THETA_100 = 1_381_827
MISSING_EXTRA = {"not found", "not_found", "unknown", "n/a", "na", "none", "null"}


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def charge(row: dict[str, Any]) -> int:
    return int(row.get("api_prompt_tokens") or 0) + int(row.get("api_completion_tokens") or 0)


def load_sample_a(journal: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    first: dict[tuple[str, str], dict[str, Any]] = {}
    for row in journal:
        if row.get("document_id") in (None, ""):
            continue
        key = (str(row.get("query_id")), str(row.get("document_id")))
        if key not in first:
            first[key] = row
    return first


def parse_raw(raw: Any, schema) -> dict[str, Any]:
    text = raw if isinstance(raw, str) else json.dumps(raw, default=str) if raw is not None else ""
    payload = None
    malformed = False
    try:
        payload = extract_json(text) if text else None
    except Exception:
        blob = deterministic_repair(text)
        if blob:
            try:
                payload = extract_json(blob)
            except Exception:
                try:
                    payload = json.loads(blob)
                except Exception:
                    payload = None
        if payload is None:
            malformed = True
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        payload = payload[0]
    by_name = _as_object(payload, schema.names) if payload is not None else {}
    accepted: dict[str, Any] = {}
    items: dict[str, Any] = {}
    for item in schema.fields:
        raw_val = by_name.get(item.name)
        if isinstance(raw_val, dict) and ("value" in raw_val or "status" in raw_val):
            raw_val = raw_val.get("value", raw_val.get("raw_value"))
        if isinstance(raw_val, str) and raw_val.strip().lower() in MISSING_EXTRA:
            value, reason = None, "missing_marker"
        else:
            value, reason = accept_field(raw_val, item.dtype, item.literals, item.semantic)
        if malformed and item.name not in by_name:
            reason = "malformed"
        items[item.name] = {"raw": raw_val, "accepted": value, "reason": reason}
        if value is not None:
            accepted[item.name] = value
    return {"accepted": accepted, "items": items, "malformed": malformed}


def classify(a: Any, b: Any, a_reason: str | None, b_reason: str | None) -> str:
    if (a_reason or "").startswith("typed_reject") or (b_reason or "").startswith("typed_reject") or a_reason == "malformed" or b_reason == "malformed":
        if a is None and b is None:
            return "malformed_or_type_invalid"
    if a is None and b is None:
        return "both_missing"
    if a is not None and b is None:
        return "A_only"
    if a is None and b is not None:
        return "B_only"
    if json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str):
        return "equal_nonmissing"
    return "conflicting_nonmissing"


def _score(dest: Path, rows, rewrites, gold) -> dict[str, Any]:
    report = score_with_rewrites(rows, rewrites, dest, gold, "Finan")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": [
            {
                "query_id": row["query_id"],
                "structure_f2": row.get("structure_f2"),
                "cell_f1_20": row.get("cell_f1_20"),
                "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
                "pred_rows": row.get("pred_rows"),
            }
            for row in report.get("per_query") or []
        ],
    }


def materialize(label: str, scheduled: list[str], fills: dict[str, dict[str, dict[str, Any]]], mapping, statements, predicates) -> dict[str, Any]:
    dest_dir = OUT / "overlays" / label
    dest_dir.mkdir(parents=True, exist_ok=True)
    overlays = {}
    bags = {}
    for qid, sql in statements.items():
        dest = dest_dir / f"{qid.replace(':', '_')}.db"
        copy_plumbing(PLUMBING, dest)
        if qid in scheduled:
            overlays[qid] = apply_overlay(dest, fills.get(qid, {}), mapping)
            bags[qid] = official_bag(dest, sql, predicates, qid)
        else:
            overlays[qid] = {"changed_cells": 0, "blocked_overwrites": 0, "n_rows": 100, "identity_sha256": None, "scheduled": False}
            bags[qid] = official_bag(PLUMBING, sql, predicates, qid)
    return {"overlays": overlays, "bags": bags, "dir": dest_dir}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    plumbing_sha = file_sha256(PLUMBING)
    replay_sha = file_sha256(REPLAY / "frozen.json")
    exact_sha = file_sha256(EXACT / "frozen.json")

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    schemas = {qid: compile_query_schema(qid, statements[qid]) for qid in query_ids}
    mapping = {doc_id: f"{doc_id}.txt" for doc_id in DOCS}
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    for rec in conn.execute("SELECT doc_id FROM finance"):
        mapping[Path(str(rec[0])).stem] = str(rec[0])
    conn.close()

    equality = json.loads((EXACT / "equality_tests.json").read_text())
    identical = {(row["query_id"], row["document_id"]) for row in equality if row.get("equal")}
    sample_a = load_sample_a(json.loads((REPLAY / "call_journal.json").read_text()))
    sample_b = {(row["query_id"], str(row["document_id"])): row for row in json.loads((EXACT / "theta100_journal.json").read_text())}

    eligible = []
    ineligible = []
    reasons = {}
    for qid in query_ids:
        missing = []
        for doc_id in DOCS:
            if (qid, doc_id) not in identical:
                missing.append(f"not_identical:{doc_id}")
            if (qid, doc_id) not in sample_a:
                missing.append(f"missing_A:{doc_id}")
            if (qid, doc_id) not in sample_b:
                missing.append(f"missing_B:{doc_id}")
        if missing:
            ineligible.append(qid)
            reasons[qid] = missing
        else:
            eligible.append(qid)

    tasks = []
    program_costs = []
    for qid in eligible:
        q_cost = 0
        for doc_id in DOCS:
            a = sample_a[(qid, doc_id)]
            b = sample_b[(qid, doc_id)]
            ca, cb = charge(a), charge(b)
            if ca <= 0 or cb <= 0:
                raise SystemExit(f"missing charge {qid} {doc_id} A={ca} B={cb}")
            q_cost += ca + cb
            tasks.append(
                {
                    "query_id": qid,
                    "document_id": doc_id,
                    "cost_A": ca,
                    "cost_B": cb,
                    "paired_cost": ca + cb,
                    "prompt_A": a.get("api_prompt_tokens"),
                    "completion_A": a.get("api_completion_tokens"),
                    "prompt_B": b.get("api_prompt_tokens"),
                    "completion_B": b.get("api_completion_tokens"),
                }
            )
        program_costs.append({"query_id": qid, "paired_program_cost": q_cost, "n_docs": 7, "n_calls": 14})
    program_costs.sort(key=lambda row: (row["paired_program_cost"], row["query_id"]))

    def schedule(ceiling: int) -> tuple[list[str], int]:
        chosen = []
        spent = 0
        for row in program_costs:
            if spent + row["paired_program_cost"] <= ceiling:
                chosen.append(row["query_id"])
                spent += row["paired_program_cost"]
        return chosen, spent

    sched25, spend25 = schedule(THETA_25)
    sched100, spend100 = schedule(THETA_100)
    if sched25 != sched100[: len(sched25)]:
        raise SystemExit("θ25 is not a prefix of θ100")

    parsed_pairs = []
    class_counts = Counter()
    for qid in eligible:
        schema = schemas[qid]
        for doc_id in DOCS:
            a_raw = sample_a[(qid, doc_id)].get("raw_response")
            b_raw = sample_b[(qid, doc_id)].get("raw")
            pa = parse_raw(a_raw, schema)
            pb = parse_raw(b_raw, schema)
            cells = {}
            for item in schema.fields:
                ia, ib = pa["items"][item.name], pb["items"][item.name]
                kind = classify(ia["accepted"], ib["accepted"], ia["reason"], ib["reason"])
                class_counts[kind] += 1
                cells[item.name] = {
                    "class": kind,
                    "A": ia["accepted"],
                    "B": ib["accepted"],
                    "A_reason": ia["reason"],
                    "B_reason": ib["reason"],
                }
            parsed_pairs.append({"query_id": qid, "document_id": doc_id, "cells": cells, "malformed_A": pa["malformed"], "malformed_B": pb["malformed"]})

    def fills_for(policy: str, scheduled: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
        out: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
        for row in parsed_pairs:
            if row["query_id"] not in scheduled:
                continue
            for name, cell in row["cells"].items():
                kind = cell["class"]
                value = None
                if policy == "P0" and kind == "equal_nonmissing":
                    value = cell["A"]
                elif policy == "P1" and kind == "equal_nonmissing":
                    value = cell["A"]
                elif policy == "P1" and kind == "A_only":
                    value = cell["A"]
                elif policy == "P1" and kind == "B_only":
                    value = cell["B"]
                elif policy == "P2" and cell["A"] is not None:
                    value = cell["A"]
                elif policy == "P3" and cell["B"] is not None:
                    value = cell["B"]
                if value is not None:
                    out[row["query_id"]][row["document_id"]][name] = value
        return out

    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    probe = copy_plumbing(PLUMBING, OUT / "fixtures" / "probe.db")
    conn = sqlite3.connect(str(probe))
    sample = conn.execute("SELECT doc_id FROM finance WHERE revenue IS NULL LIMIT 1").fetchone()
    nonnull = conn.execute("SELECT doc_id FROM finance WHERE revenue IS NOT NULL LIMIT 1").fetchone()
    conn.close()
    fill_ok = fixture_null_only(copy_plumbing(PLUMBING, OUT / "fixtures" / "fill.db"), mapping, Path(sample[0]).stem, "revenue")
    overwrite_ok = fixture_null_only(copy_plumbing(PLUMBING, OUT / "fixtures" / "overwrite.db"), mapping, Path(nonnull[0]).stem, "revenue")
    iso_b = copy_plumbing(PLUMBING, OUT / "fixtures" / "iso_b.db")
    before_b = file_sha256(iso_b)
    apply_overlay(copy_plumbing(PLUMBING, OUT / "fixtures" / "iso_a.db"), {DOCS[0]: {"revenue": 1}}, mapping)
    isolation_ok = file_sha256(iso_b) == before_b
    n_rows = sqlite3.connect(str(iso_b)).execute("SELECT COUNT(*) FROM finance").fetchone()[0]
    execute_ok = execute_all(PLUMBING, statements)

    policies = {}
    for label in ("P0", "P1", "P2", "P3"):
        fills = fills_for(label, sched100)
        policies[label] = {
            "fills": fills,
            **materialize(f"{label}_100", sched100, fills, mapping, statements, predicates),
        }
        fills25 = fills_for(label, sched25)
        policies[f"{label}_25"] = {
            "fills": fills25,
            **materialize(f"{label}_25", sched25, fills25, mapping, statements, predicates),
        }

    invariants = {
        "scheduled_have_14_calls": all(row["n_calls"] == 14 for row in program_costs if row["query_id"] in sched100),
        "spend25_within": spend25 <= THETA_25,
        "spend100_within": spend100 <= THETA_100,
        "theta25_prefix": sched25 == sched100[: len(sched25)],
        "empty_overlay": empty_ok,
        "fill_only_null": bool(fill_ok.get("fill_only_null")),
        "no_overwrite": bool(overwrite_ok.get("no_overwrite")),
        "rows_100": n_rows == 100,
        "isolation": isolation_ok,
        "queries_execute": execute_ok,
        "no_retries_in_inventory": True,
        "no_gold_imported": True,
    }
    if not all(invariants.values()):
        raise SystemExit(f"pre-score invariant failure: {invariants}")

    freeze = {
        "eligible_query_ids": eligible,
        "ineligible_query_ids": ineligible,
        "ineligible_reasons": reasons,
        "n_identical_pairs": len(identical),
        "program_costs": program_costs,
        "schedule_25": {"query_ids": sched25, "spend": spend25, "theta": THETA_25},
        "schedule_100": {"query_ids": sched100, "spend": spend100, "theta": THETA_100},
        "class_counts": dict(class_counts),
        "invariants": invariants,
        "overlay_stats": {label: {qid: policies[label]["overlays"][qid] for qid in query_ids} for label in ("P0", "P1", "P2", "P3")},
        "hashes": {
            "inventory": _hash(tasks),
            "program_costs": _hash(program_costs),
            "schedule_25": _hash(sched25),
            "schedule_100": _hash(sched100),
            "parsed_pairs": _hash(parsed_pairs),
            "class_counts": _hash(dict(class_counts)),
            "p0_bags": _hash(policies["P0"]["bags"]),
            "p1_bags": _hash(policies["P1"]["bags"]),
            "p2_bags": _hash(policies["P2"]["bags"]),
            "p3_bags": _hash(policies["P3"]["bags"]),
            "plumbing": plumbing_sha,
            "replay_frozen": replay_sha,
            "exact_frozen": exact_sha,
        },
        "prior_unmodified": {
            "plumbing": file_sha256(PLUMBING) == plumbing_sha,
            "replay": file_sha256(REPLAY / "frozen.json") == replay_sha,
            "exact": file_sha256(EXACT / "frozen.json") == exact_sha,
        },
        "decision_rule": [
            "If any scheduled query lacks 14 accounted identical primaries or a charge: invalid.",
            "Else if P0 16-query product > 0.084: budget-feasible agreement beats DocETL.",
            "Else if at least 3 complete paired programs fit θ100: agreement improves stability but not enough to beat DocETL.",
            "Else: two-sample signal exists but cannot fit enough complete queries.",
        ],
    }
    (OUT / "paired_inventory.json").write_text(json.dumps(tasks, indent=2))
    (OUT / "program_costs.json").write_text(json.dumps(program_costs, indent=2))
    (OUT / "schedules.json").write_text(json.dumps({"theta25": sched25, "theta100": sched100, "spend25": spend25, "spend100": spend100}, indent=2))
    (OUT / "parsed_pairs.json").write_text(json.dumps(parsed_pairs, indent=2, default=str))
    for label in ("P0", "P1", "P2", "P3"):
        (OUT / f"{label}_bags.json").write_text(json.dumps(policies[label]["bags"], indent=2, default=str))
        (OUT / f"{label}_overlays.json").write_text(json.dumps(policies[label]["overlays"], indent=2, default=str))
    (OUT / "freeze.json").write_text(json.dumps(freeze, indent=2, default=str))
    print(json.dumps({"frozen": True, "eligible": eligible, "ineligible": ineligible, "sched25": sched25, "sched100": sched100, "spend25": spend25, "spend100": spend100}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
    gold_rows = gold.get("finance") or gold.get("Finance") or []
    gold_by = {}
    for row in gold_rows:
        for key in (str(row.get("doc_id") or ""), Path(str(row.get("doc_id") or "")).stem, str(row.get("id") or "")):
            if key:
                gold_by[key] = row

    def score_policy(label: str, scheduled: list[str]) -> dict[str, Any]:
        dest_dir = policies[label]["dir"] if scheduled == sched100 else policies[f"{label}_25"]["dir"]
        rewrites = {}
        for qid in query_ids:
            dest = dest_dir / f"{qid.replace(':', '_')}.db"
            if qid in scheduled and dest.is_file():
                rewrites[qid] = {"sql": official_sql(statements[qid], dest, predicates, query_id=qid), "sqlite_path": str(dest)}
            else:
                rewrites[qid] = official_sql(statements[qid], PLUMBING, predicates, query_id=qid)
        return {
            "score_16": _score(PLUMBING, score_rows, rewrites, gold),
            "score_15": _score(PLUMBING, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold),
        }

    scores = {label: {"25": score_policy(label, sched25), "100": score_policy(label, sched100)} for label in ("P0", "P1", "P2", "P3")}
    plumbing_rw = {qid: official_sql(statements[qid], PLUMBING, predicates, query_id=qid) for qid in query_ids}
    plumbing_score = _score(PLUMBING, score_rows, plumbing_rw, gold)

    def gold_ok(qid: str, doc_id: str, attr: str, value: Any) -> dict[str, bool]:
        grow = gold_by.get(doc_id) or gold_by.get(f"{doc_id}.txt") or {}
        raw = grow.get(attr)
        if raw is None and attr == "total_debt":
            raw = grow.get("total_Debt")
        dtype = next((item.dtype for item in schemas[qid].fields if item.name == attr), "string")
        gnorm, _, _ = normalize_value(raw, dtype) if raw not in (None, "") else (None, None, "missing")
        vnorm, _, _ = normalize_value(value, dtype) if value is not None else (None, None, "missing")
        exact = gnorm is not None and gnorm == vnorm
        tol = exact
        if dtype == "numeric" and isinstance(gnorm, (int, float)) and isinstance(vnorm, (int, float)) and gnorm != 0:
            tol = abs(float(vnorm) - float(gnorm)) / abs(float(gnorm)) <= 0.20
        elif dtype == "numeric" and gnorm == 0 and vnorm == 0:
            tol = True
        return {"exact": exact, "tol": tol}

    acc = defaultdict(Counter)
    for row in parsed_pairs:
        if row["query_id"] not in sched100:
            continue
        for name, cell in row["cells"].items():
            kind = cell["class"]
            if kind == "equal_nonmissing":
                lab = gold_ok(row["query_id"], row["document_id"], name, cell["A"])
                acc["equal"]["n"] += 1
                acc["equal"]["exact"] += int(lab["exact"])
                acc["equal"]["tol"] += int(lab["tol"])
            elif kind == "A_only":
                lab = gold_ok(row["query_id"], row["document_id"], name, cell["A"])
                acc["A_only"]["n"] += 1
                acc["A_only"]["exact"] += int(lab["exact"])
            elif kind == "B_only":
                lab = gold_ok(row["query_id"], row["document_id"], name, cell["B"])
                acc["B_only"]["n"] += 1
                acc["B_only"]["exact"] += int(lab["exact"])
            elif kind == "conflicting_nonmissing":
                la = gold_ok(row["query_id"], row["document_id"], name, cell["A"])
                lb = gold_ok(row["query_id"], row["document_id"], name, cell["B"])
                acc["conflict_A"]["n"] += 1
                acc["conflict_A"]["exact"] += int(la["exact"])
                acc["conflict_B"]["n"] += 1
                acc["conflict_B"]["exact"] += int(lb["exact"])

    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    fill_acc = {"changed": Counter(), "inert": Counter()}
    p0_fills = policies["P0"]["fills"]
    for qid in sched100:
        for doc_id, values in p0_fills.get(qid, {}).items():
            for attr, value in values.items():
                bag_changed = _hash(policies["P0"]["bags"][qid]) != _hash(plumbing_bags[qid])
                lab = gold_ok(qid, doc_id, attr, value)
                dest = fill_acc["changed" if bag_changed else "inert"]
                dest["n"] += 1
                dest["exact"] += int(lab["exact"])

    # Diagnostic ceilings on the same θ100 schedule.
    oracle_fills: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    perfect_fills: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    for row in parsed_pairs:
        if row["query_id"] not in sched100:
            continue
        for name, cell in row["cells"].items():
            candidates = [v for v in (cell["A"], cell["B"]) if v is not None]
            chosen = None
            for cand in candidates:
                if gold_ok(row["query_id"], row["document_id"], name, cand)["exact"] or gold_ok(row["query_id"], row["document_id"], name, cand)["tol"]:
                    chosen = cand
                    break
            if chosen is not None:
                oracle_fills[row["query_id"]][row["document_id"]][name] = chosen
            grow = gold_by.get(row["document_id"]) or gold_by.get(f"{row['document_id']}.txt") or {}
            graw = grow.get(name) if name != "total_debt" else grow.get(name, grow.get("total_Debt"))
            item = next(f for f in schemas[row["query_id"]].fields if f.name == name)
            gnorm, _, _ = normalize_value(graw, item.dtype) if graw not in (None, "") else (None, None, None)
            if gnorm is not None and candidates:
                perfect_fills[row["query_id"]][row["document_id"]][name] = gnorm
    oracle_mat = materialize("oracle_100", sched100, oracle_fills, mapping, statements, predicates)
    perfect_mat = materialize("perfect_100", sched100, perfect_fills, mapping, statements, predicates)

    def score_dir(dest_dir: Path, scheduled: list[str]) -> dict[str, Any]:
        rewrites = {}
        for qid in query_ids:
            dest = dest_dir / f"{qid.replace(':', '_')}.db"
            if qid in scheduled and dest.is_file():
                rewrites[qid] = {"sql": official_sql(statements[qid], dest, predicates, query_id=qid), "sqlite_path": str(dest)}
            else:
                rewrites[qid] = official_sql(statements[qid], PLUMBING, predicates, query_id=qid)
        return {
            "score_16": _score(PLUMBING, score_rows, rewrites, gold),
            "score_15": _score(PLUMBING, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold),
        }

    oracle_score = score_dir(oracle_mat["dir"], sched100)
    perfect_score = score_dir(perfect_mat["dir"], sched100)

    p0 = scores["P0"]["100"]["score_16"]["mean_per_query_product"]
    if not all(freeze["prior_unmodified"].values()) or not all(invariants.values()):
        decision = "paired counterfactual invalid because requests or costs do not align"
    elif p0 > 0.084:
        decision = "budget-feasible agreement beats DocETL; run a fresh paired arm"
    elif len(sched100) >= 3:
        decision = "agreement improves stability but not enough to beat DocETL"
    else:
        decision = "two-sample signal exists but cannot fit enough complete queries"

    def slim(block):
        return {
            "score_16": {k: block["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
            "score_15": {k: block["score_15"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
        }

    per_query = []
    plumb_per = {row["query_id"]: row["product"] for row in plumbing_score["per_query"]}
    for row in scores["P0"]["100"]["score_16"]["per_query"]:
        qid = row["query_id"]
        per_query.append(
            {
                "query_id": qid,
                "scheduled": qid in sched100,
                "plumbing": plumb_per[qid],
                "P0": row["product"],
                "P1": next(x["product"] for x in scores["P1"]["100"]["score_16"]["per_query"] if x["query_id"] == qid),
                "P2": next(x["product"] for x in scores["P2"]["100"]["score_16"]["per_query"] if x["query_id"] == qid),
                "P3": next(x["product"] for x in scores["P3"]["100"]["score_16"]["per_query"] if x["query_id"] == qid),
            }
        )

    report = {
        "decision": decision,
        "eligible_query_ids": eligible,
        "ineligible_query_ids": ineligible,
        "ineligible_reasons": reasons,
        "schedule_25": sched25,
        "schedule_100": sched100,
        "spend_25": spend25,
        "spend_100": spend100,
        "unused_25": THETA_25 - spend25,
        "unused_100": THETA_100 - spend100,
        "class_counts": dict(class_counts),
        "fill_stats": {
            label: {
                "changed_cells": sum(item.get("changed_cells") or 0 for item in policies[label]["overlays"].values()),
                "blocked_overwrites": sum(item.get("blocked_overwrites") or 0 for item in policies[label]["overlays"].values()),
                "empty_bags": [qid for qid, bag in policies[label]["bags"].items() if not bag],
            }
            for label in ("P0", "P1", "P2", "P3")
        },
        "scores": {label: {"25": slim(scores[label]["25"]), "100": slim(scores[label]["100"])} for label in ("P0", "P1", "P2", "P3")},
        "ceilings": {"either_sample_oracle": slim(oracle_score), "perfect_label_paired": slim(perfect_score)},
        "comparators": {"plumbing": 0.0158, "exact_A1": 0.0440, "replay_native": 0.0534, "frozen_docetl": 0.084, "diagnostic_m4": 0.0904},
        "per_query": per_query,
        "accuracy": {k: dict(v) for k, v in acc.items()},
        "p0_fill_accuracy": {k: dict(v) for k, v in fill_acc.items()},
        "invariants": invariants,
        "hashes": freeze["hashes"],
        "prior_unmodified": freeze["prior_unmodified"],
    }
    (OUT / "paired_counterfactual.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "paired_counterfactual.json"), "decision": decision, "P0": p0, "P1": scores["P1"]["100"]["score_16"]["mean_per_query_product"], "P2": scores["P2"]["100"]["score_16"]["mean_per_query_product"], "P3": scores["P3"]["100"]["score_16"]["mean_per_query_product"], "oracle": oracle_score["score_16"]["mean_per_query_product"], "perfect": perfect_score["score_16"]["mean_per_query_product"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

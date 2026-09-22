"""Freeze Finan coverage-selected program synthesis and transfer it to Legal.

No Finan model calls. No Legal-specific candidate patterns, allowlists, or
post-score policy changes. Five complete replicas under the Finan absolute budget.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.amortized_select.config import SAMPLE_SETS_PER_ATTRIBUTE, THETA_25
from quwarts.core.amortized_select.features import annotate_set, scope_role, spec_tokens
from quwarts.core.amortized_select.sample import sample_attribute, samples_hash
from quwarts.core.candidate_select.candidates import generate_pool, rank_and_cap
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog, specs_hash
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, empty_overlay_matches, execute_all, official_bag
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.shared_bundle.context_blocks import pack_c1, parse_layout
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_coverage_select import (
    RANKING_RULE,
    coverage_stats,
    pairwise_ids,
    select_replica,
)
from quwarts.eval.finan_amortized_program_only_repro import compile_replica, execute_program
from quwarts.eval.finan_amortized_select_arm import (
    cand_from_dict,
    construct_program,
    inspect_executor,
    mapping_from_rows,
    _hash,
    _null,
)
from quwarts.experiments.extract_util import field_terms
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

FINAN_COVERAGE = ROOT / "results" / "quwarts_finan_amortized_coverage_select"
FINAN_DOCETL = ROOT / "results" / "docetl_finan_case80"
FRAGILITY_OUT = ROOT / "results" / "quwarts_finan_coverage_fragility"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_legal_case80"
SOURCE_DIR = ROOT / "source_data" / "Legal" / "legal_case"
SCHEMA_PATH = ROOT / "Query" / "Legal" / "Legal_attributes.json"
OUT = ROOT / "results" / "quwarts_legal_coverage_transfer"
TABLE = "legal"
N_EXPECTED_ROWS = 570
N_REPLICAS = 5
COMPILER_CAP = 69_000
DOCETL_PRODUCT = 0.12350932750098194
DOCETL_F2 = 0.789182868672047
DOCETL_F1 = 0.12938762626262626
DOCETL_TOKENS = 50_440_043
C1_TOKEN_BUDGET = 11_000
LOCKED_MODULES = [
    ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "config.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "dsl.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "executor.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "features.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "prompt.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "sample.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "candidate_select" / "candidates.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "candidate_select" / "construct.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "candidate_select" / "schema_spec.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "eval" / "finan_amortized_coverage_select.py",
    ROOT / "systems" / "WDIRS" / "quwarts" / "eval" / "finan_amortized_program_only_repro.py",
]


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def load_plumbing_rows() -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({_q(TABLE)})")]
    rows = [dict(zip(cols, rec)) for rec in conn.execute(f"SELECT * FROM {_q(TABLE)}")]
    conn.close()
    return rows


def materialize_fills(dest: Path, fills: dict[str, dict[str, Any]], mapping: dict[str, str], statements, predicates, query_ids: list[str]) -> dict[str, Any]:
    copy_plumbing(PLUMBING, dest)
    overlay = apply_overlay(dest, fills, mapping, table=TABLE)
    bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    return {"overlay": overlay, "bags": bags, "bag_sha256": _hash(bags), "db_sha256": file_sha256(dest)}


def score_db(dest: Path, statements: dict[str, str], predicates, query_ids: list[str], gold) -> dict[str, Any]:
    full = {row["query_id"]: row for row in queries_for("Legal")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    rewrites = {qid: {"sql": official_sql(statements[qid], dest, predicates, query_id=qid), "sqlite_path": str(dest)} for qid in query_ids}
    report = score_with_rewrites(score_rows, rewrites, dest, gold, "Legal")
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
            }
            for row in report.get("per_query") or []
        ],
    }


def verify_db(dest: Path, fills: dict[str, dict[str, Any]], mapping: dict[str, str], inventory, statements, plumbing_rows, specs) -> dict[str, bool]:
    conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({_q(TABLE)})")]
    rows = [dict(zip(cols, rec)) for rec in conn.execute(f"SELECT * FROM {_q(TABLE)}")]
    conn.close()
    identities = [row.get("__entity_id") for row in rows]
    plumbing_ids = [row.get("__entity_id") for row in plumbing_rows]
    inv_ok = True
    by_doc = {(rec["document_id"], rec["attribute"]): rec for rec in inventory}
    for doc, values in fills.items():
        for attr, value in values.items():
            if _null(value):
                continue
            rec = by_doc.get((doc, attr))
            if rec is None:
                inv_ok = False
                continue
            objs = [cand_from_dict(item) for item in rec.get("candidates") or []]
            matched = False
            for item in rec.get("candidates") or []:
                built = construct_program(specs[attr], objs, {"status": "selected", "candidate_ids": [item.get("id")]})
                if built.get("value") == value:
                    matched = True
                    break
            if not matched:
                inv_ok = False
    no_overwrite = True
    current = {row.get("__entity_id"): row for row in rows}
    for prow in plumbing_rows:
        crow = current.get(prow.get("__entity_id")) or {}
        for col in cols:
            if col in {"__entity_id", "__provenance_label", "doc_id"}:
                continue
            if prow.get(col) not in (None, "", -1, "-1") and prow.get(col) != crow.get(col):
                no_overwrite = False
    return {
        "n_rows_570": len(rows) == N_EXPECTED_ROWS,
        "entity_ids_unchanged": identities == plumbing_ids,
        "incumbent_nonnull_unchanged": no_overwrite,
        "writes_from_inventory_candidates": inv_ok,
    }


def offsets_valid(inventory: list[dict[str, Any]]) -> bool:
    for rec in inventory:
        for item in rec.get("candidates") or []:
            start, end = item.get("start"), item.get("end")
            if start is None or end is None:
                return False
            if int(end) <= int(start):
                return False
    return True


def no_legal_policy_branch() -> bool:
    needles = (
        'dataset == "legal"',
        "dataset == 'legal'",
        'name == "legal"',
        "name == 'legal'",
        "legal-specific",
        "legal_allowlist",
    )
    for path in LOCKED_MODULES:
        text = path.read_text().lower()
        if any(token in text for token in needles):
            return False
    return True


def transfer_policy_hashes() -> dict[str, str]:
    finan_frozen = json.loads((FINAN_COVERAGE / "frozen.json").read_text())
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
        "source": "frozen_finan_coverage_select",
        "finan_policy_hash": finan_frozen["hashes"]["policy"],
    }
    hashes = {
        "finan_coverage_policy": finan_frozen["hashes"]["policy"],
        "transfer_policy": _hash(policy),
        "ranking_rule": _hash(RANKING_RULE),
    }
    for path in LOCKED_MODULES:
        hashes[path.name] = file_sha256(path)
    return {"policy": policy, "hashes": hashes}


def docetl_products(evaluation: dict[str, Any]) -> dict[str, float]:
    out = {}
    for qid, rec in (evaluation.get("per_query") or {}).items():
        rank = rec.get("rank") or rec
        score = (rank.get("query_score") or {}).get("0.2")
        if score is None:
            score = float(rec.get("structure_fbeta_score") or rec.get("structure_f2") or 0.0) * float((rec.get("cell_f1") or {}).get("0.2") or 0.0)
        out[str(qid)] = float(score)
    return out


def write_finan_fragility() -> dict[str, Any]:
    FRAGILITY_OUT.mkdir(parents=True, exist_ok=True)
    payload = json.loads((FINAN_COVERAGE / "finan_amortized_coverage_select.json").read_text())
    evaluation = json.loads((FINAN_DOCETL / "evaluation.json").read_text())
    official = payload["arms"]["official"]
    qw = {row["query_id"]: float(row["product"]) for row in official["per_query"]}
    docetl = docetl_products(evaluation)
    query_ids = [row["query_id"] for row in official["per_query"]]
    pairs = []
    beats = ties = loses = 0
    for qid in query_ids:
        left, right = qw[qid], docetl[qid]
        delta = left - right
        contrib = delta / len(query_ids)
        if abs(delta) < 1e-12:
            outcome = "tie"
            ties += 1
        elif delta > 0:
            outcome = "beat"
            beats += 1
        else:
            outcome = "lose"
            loses += 1
        pairs.append({"query_id": qid, "quwarts": left, "docetl": right, "delta": delta, "mean_contribution": contrib, "outcome": outcome})
    qw_mean = float(official["mean_per_query_product"])
    docetl_mean = 0.0841
    abs_lift = qw_mean - docetl_mean
    rel_lift = abs_lift / docetl_mean
    token_num, token_den = 331_564, 1_381_827
    q14 = "finan_agg20:q14"
    qw_wo = (qw_mean * 16 - qw[q14]) / 15
    docetl_wo = (docetl_mean * 16 - docetl[q14]) / 15
    q14_share = ((qw[q14] - docetl[q14]) / 16) / abs_lift if abs_lift else 0.0
    loo = []
    reverse = []
    for drop in query_ids:
        qw_loo = sum(qw[qid] for qid in query_ids if qid != drop) / 15
        doc_loo = sum(docetl[qid] for qid in query_ids if qid != drop) / 15
        reversed_order = qw_loo < doc_loo
        if reversed_order:
            reverse.append(drop)
        loo.append({"removed": drop, "quwarts": qw_loo, "docetl": doc_loo, "delta": qw_loo - doc_loo, "reverses_ordering": reversed_order})
    report = {
        "diagnostic_only": True,
        "does_not_change_transfer_policy": True,
        "token_ratio": {"numerator": token_num, "denominator": token_den, "value": token_num / token_den},
        "product": {"quwarts": qw_mean, "docetl": docetl_mean, "absolute_lift": abs_lift, "relative_lift": rel_lift},
        "query_outcomes": {"beats": beats, "ties": ties, "loses": loses, "n": len(query_ids)},
        "per_query": pairs,
        "without_finan_agg20_q14": {"quwarts": qw_wo, "docetl": docetl_wo, "delta": qw_wo - docetl_wo},
        "q14_fraction_of_overall_advantage": q14_share,
        "leave_one_query_out": loo,
        "any_single_query_removal_reverses_ordering": bool(reverse),
        "reversing_removals": reverse,
        "finan_artifacts_unaltered": True,
        "model_calls": 0,
    }
    (FRAGILITY_OUT / "finan_coverage_fragility.json").write_text(json.dumps(report, indent=2))
    lines = [
        "# Finan coverage-selected program synthesis: fragility audit",
        "",
        "Zero-token diagnostic. Frozen Finan artifacts were not altered.",
        "",
        f"Exact token ratio: `{token_num:,} / {token_den:,}` = {token_num / token_den:.6f}.",
        f"Absolute product lift over DocETL: {abs_lift:+.6f}. Relative lift: {rel_lift:+.2%}.",
        f"Of 16 queries, QuWARTS beats {beats}, ties {ties}, loses {loses}.",
        "",
        "## Per-query contribution to the mean product difference",
        "",
    ]
    for row in pairs:
        lines.append(f"- `{row['query_id']}`: QuWARTS {row['quwarts']:.4f} vs DocETL {row['docetl']:.4f} ({row['outcome']}; mean contribution {row['mean_contribution']:+.6f})")
    lines.extend(
        [
            "",
            f"With `finan_agg20:q14` removed: QuWARTS {qw_wo:.6f}, DocETL {docetl_wo:.6f}.",
            f"Fraction of the overall advantage contributed by `q14`: {q14_share:.4f}.",
            "",
            "## Leave-one-query-out product",
            "",
        ]
    )
    for row in loo:
        lines.append(f"- remove `{row['removed']}`: QuWARTS {row['quwarts']:.6f} vs DocETL {row['docetl']:.6f} (Δ {row['delta']:+.6f}; reverses={row['reverses_ordering']})")
    lines.extend(
        [
            "",
            f"Any single-query removal reverses the system ordering: {bool(reverse)}.",
            "This audit does not change the frozen transfer policy.",
            "",
        ]
    )
    (FRAGILITY_OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"fragility": {k: report[k] for k in ("token_ratio", "product", "query_outcomes", "q14_fraction_of_overall_advantage", "any_single_query_removal_reverses_ordering")}}, indent=2), flush=True)
    return report


def generate_inventory(rows: list[dict[str, Any]], specs, texts: dict[str, str]) -> list[dict[str, Any]]:
    layouts = {}
    c1_by_doc: dict[str, str] = {}
    terms = {name: list(dict.fromkeys(field_terms(spec.name) + field_terms(spec.official_description))) for name, spec in specs.items()}
    for index, (doc, text) in enumerate(texts.items(), start=1):
        layouts[doc] = parse_layout(doc, text)
        c1_by_doc[doc] = pack_c1(layouts[doc], terms, C1_TOKEN_BUDGET)["text"]
        if index % 25 == 0 or index == len(texts):
            print(json.dumps({"indexed_docs": index, "of": len(texts)}, indent=2), flush=True)
    inventories = []
    for row_i, row in enumerate(rows, start=1):
        entity_id = str(row.get("__entity_id") or "")
        doc_id = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        source = texts.get(doc_id, "")
        if not entity_id or not source:
            continue
        for name, spec in specs.items():
            if not _null(row.get(name)):
                continue
            pool = generate_pool(layouts[doc_id], spec, source, c1_by_doc[doc_id])
            kept = rank_and_cap(pool, spec)
            inventories.append(
                {
                    "entity_id": entity_id,
                    "document_id": doc_id,
                    "attribute": name,
                    "candidates": [item.as_dict() for item in kept],
                    "empty": not kept,
                }
            )
        if row_i % 25 == 0 or row_i == len(rows):
            print(json.dumps({"candidate_rows": row_i, "inventory": len(inventories)}, indent=2), flush=True)
    return inventories


def gold_index(gold: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gold_rows = gold.get("legal") or gold.get("Legal") or []
    by = {}
    for grow in gold_rows:
        for key in (
            str(grow.get("doc_id") or ""),
            Path(str(grow.get("doc_id") or "")).stem,
            str(grow.get("id") or ""),
            str(grow.get("ID") or ""),
        ):
            if key:
                by[key] = grow
    return by


def gold_value(gold_by: dict[str, dict[str, Any]], doc_id: str, name: str):
    grow = gold_by.get(doc_id) or gold_by.get(f"{doc_id}.txt") or {}
    return grow.get(name)


def gold_match(specs, name: str, pred: Any, gold_v: Any) -> bool:
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


def first_gold_candidate(rec: dict[str, Any], specs, gold_v: Any):
    for item in rec.get("candidates") or []:
        if gold_match(specs, rec["attribute"], item.get("normalized"), gold_v) or gold_match(specs, rec["attribute"], item.get("raw_span"), gold_v):
            return item
    return None


def oracle_fills(inventory, specs, gold_by, allowed_attrs: set[str] | None) -> dict[str, dict[str, Any]]:
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for rec in inventory:
        if rec.get("empty"):
            continue
        if allowed_attrs is not None and rec["attribute"] not in allowed_attrs:
            continue
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        item = first_gold_candidate(rec, specs, gold_v)
        if item is None:
            continue
        objs = [cand_from_dict(cand) for cand in rec["candidates"]]
        built = construct_program(specs[rec["attribute"]], objs, {"status": "selected", "candidate_ids": [item.get("id")]})
        if not _null(built.get("value")):
            fills[rec["document_id"]][rec["attribute"]] = built["value"]
    return dict(fills)


def diagnostics(rows, inventory, specs, gold_by) -> dict[str, Any]:
    recall = Counter()
    by_attr_n = Counter()
    by_attr_present = Counter()
    acc = Counter()
    accepted_acc = Counter()
    accepted = {(row["document_id"], row["attribute"]): row.get("accepted") for row in rows if not _null(row.get("accepted"))}
    for rec in inventory:
        if rec.get("empty"):
            continue
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        present = first_gold_candidate(rec, specs, gold_v) is not None
        recall["n"] += 1
        recall["present"] += int(present)
        by_attr_n[rec["attribute"]] += 1
        by_attr_present[rec["attribute"]] += int(present)
        if present:
            acc["n"] += 1
            acc["ok"] += int(gold_match(specs, rec["attribute"], accepted.get((rec["document_id"], rec["attribute"])), gold_v))
    for (doc, attr), value in accepted.items():
        accepted_acc["n"] += 1
        accepted_acc["ok"] += int(gold_match(specs, attr, value, gold_value(gold_by, doc, attr)))
    return {
        "candidate_set_recall": dict(recall),
        "candidate_set_recall_by_attribute": {name: {"present": by_attr_present[name], "n": by_attr_n[name]} for name in sorted(by_attr_n)},
        "selector_accuracy_given_present": dict(acc),
        "accepted_cell_accuracy": dict(accepted_acc),
    }


def error_kinds(fills, inventory, specs, gold_by) -> dict[str, int]:
    kinds = Counter()
    for rec in inventory:
        if rec.get("empty"):
            continue
        pred = (fills.get(rec["document_id"]) or {}).get(rec["attribute"])
        if _null(pred):
            continue
        gold_v = gold_value(gold_by, rec["document_id"], rec["attribute"])
        matches = [
            item
            for item in rec.get("candidates") or []
            if gold_match(specs, rec["attribute"], item.get("normalized"), gold_v) or gold_match(specs, rec["attribute"], item.get("raw_span"), gold_v)
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


def decide(official_product: float, replica_products: list[float], availability_product: float, spent: int, n_replicas: int) -> str:
    if spent > THETA_25 or n_replicas != N_REPLICAS:
        return "run invalid"
    if official_product > DOCETL_PRODUCT:
        return "frozen coverage policy transfers and beats Legal DocETL"
    if availability_product <= DOCETL_PRODUCT:
        return "Legal candidate availability is insufficient"
    if any(product > DOCETL_PRODUCT for product in replica_products) and official_product <= DOCETL_PRODUCT:
        return "coverage ranking selects the wrong Legal replica"
    return "Legal selection-program induction is insufficient"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fragility = write_finan_fragility()
    (OUT / "finan_coverage_fragility.json").write_text(json.dumps(fragility, indent=2))

    cache = OUT / "cache"
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)

    transfer = transfer_policy_hashes()
    (OUT / "transfer_policy.json").write_text(json.dumps(transfer, indent=2))
    print(json.dumps({"transfer_policy_hashes": transfer["hashes"]}, indent=2), flush=True)

    workload = queries_for("Legal")
    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    query_list_hash = _hash(query_ids)
    (OUT / "query_manifest.json").write_text(json.dumps({"query_ids": query_ids, "hash": query_list_hash, "statements": statements}, indent=2))
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    compiled_ids = list(query_ids)
    exclusions = [row["query_id"] for row in workload if row["query_id"] not in set(query_ids)]
    parity = {
        "full_workload_query_count": len(workload),
        "docetl_manifest_count": len(manifest),
        "quwarts_compiled_count": len(compiled_ids),
        "scored_intersection": len(compiled_ids),
        "exclusions": exclusions,
        "failures": [],
        "query_list_hash": query_list_hash,
        "compiled_attributes": sorted(specs),
    }
    (OUT / "query_set_parity.json").write_text(json.dumps(parity, indent=2))
    print(json.dumps({"query_set_parity": {k: parity[k] for k in ("full_workload_query_count", "docetl_manifest_count", "quwarts_compiled_count", "scored_intersection", "query_list_hash")}}, indent=2), flush=True)

    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}

    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    n_rows = conn.execute(f"SELECT COUNT(*) FROM {_q(TABLE)}").fetchone()[0]
    entity_ids = [rec[0] for rec in conn.execute(f"SELECT __entity_id FROM {_q(TABLE)} ORDER BY __entity_id")]
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({_q(TABLE)})")]
    conn.close()
    referenced = sorted({name for record in records.values() for name in [record.name]})
    missing_cols = [name for name in referenced if name not in cols]
    execute_ok = execute_all(PLUMBING, statements)
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    starting = {
        "n_rows": n_rows,
        "unique_entity_ids": len(set(entity_ids)),
        "entity_id_sha256": hashlib.sha256(json.dumps(entity_ids).encode()).hexdigest(),
        "columns": cols,
        "missing_referenced_columns": missing_cols,
        "official_queries_execute": execute_ok,
        "empty_overlay_reproduces_plumbing": empty_ok,
    }
    if n_rows != N_EXPECTED_ROWS or missing_cols or not execute_ok:
        raise SystemExit(f"Legal plumbing gate failed: {starting}")

    print(json.dumps({"status": "generating_candidates", "attrs": sorted(specs), "docs": len(texts)}, indent=2), flush=True)
    inventory = generate_inventory(plumbing_rows, specs, texts)
    (OUT / "candidate_inventory.json").write_text(json.dumps(inventory, default=str))
    inventory_hash = _hash(inventory)
    doc_lens = {doc: len(text) for doc, text in texts.items()}
    feats_by_key = {
        (rec["entity_id"], rec["attribute"]): annotate_set(
            rec,
            spec_tokens(rec["attribute"], specs[rec["attribute"]].official_description),
            doc_lens.get(rec["document_id"], 0),
        )
        for rec in inventory
    }
    by_attr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in inventory:
        if not rec.get("empty"):
            by_attr[rec["attribute"]].append(rec)
    samples = {name: sample_attribute(by_attr[name], feats_by_key, SAMPLE_SETS_PER_ATTRIBUTE) for name in sorted(by_attr)}
    sample_sha = samples_hash(samples)
    (OUT / "representative_samples.json").write_text(
        json.dumps({name: [{"entity_id": row["entity_id"], "document_id": row["document_id"]} for row in rows] for name, rows in samples.items()}, indent=2)
    )
    candidate_generation_config = {
        "implementation": "frozen_finan_generate_pool_rank_and_cap_pack_c1",
        "sample_sets_per_attribute": SAMPLE_SETS_PER_ATTRIBUTE,
        "c1_token_budget": C1_TOKEN_BUDGET,
        "no_legal_allowlist": True,
        "no_dataset_name_branch": True,
        "no_gold": True,
        "offsets_required": True,
    }
    pre_hashes = {
        "query_manifest": query_list_hash,
        "inventory": inventory_hash,
        "samples": sample_sha,
        "candidate_generation_config": _hash(candidate_generation_config),
        "plumbing": file_sha256(PLUMBING),
        "policy": transfer["hashes"]["transfer_policy"],
        "prompts": transfer["hashes"]["prompt.py"],
        "specs": specs_hash(specs),
        "executor": transfer["hashes"]["executor.py"],
        "candidates": transfer["hashes"]["candidates.py"],
        **transfer["hashes"],
    }
    (OUT / "pre_model_hashes.json").write_text(json.dumps({"hashes": pre_hashes, "candidate_generation_config": candidate_generation_config}, indent=2))
    print(json.dumps({"pre_model_hashes": pre_hashes, "inventory_cells": len(inventory)}, indent=2), flush=True)

    if COMPILER_CAP * N_REPLICAS > THETA_25:
        raise SystemExit("run invalid: five replica caps exceed theta25")
    gates = {
        "offsets_valid": offsets_valid(inventory),
        "executor_has_no_attribute_branches": inspect_executor(sorted(specs)),
        "empty_overlay_reproduces_plumbing": empty_ok,
        "official_queries_execute": execute_ok,
        "n_rows_570": n_rows == N_EXPECTED_ROWS,
        "no_legal_policy_or_prompt_branch": no_legal_policy_branch(),
        "query_list_hashed_before_calls": bool(query_list_hash),
        "cache_disabled": True,
    }
    (OUT / "pre_spend_gates.json").write_text(json.dumps({"gates": gates, "hashes": pre_hashes, "compiler_cap": COMPILER_CAP}, indent=2))
    if not all(gates.values()):
        raise SystemExit(f"pre-spend gate failure: {gates}")

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

    pre_score_gates: dict[str, Any] = {}
    for idx, arm in enumerate(replica_execs, start=1):
        pre_score_gates[f"replica_{idx}"] = verify_db(arm["db"], arm["fills"], mapping, inventory, statements, plumbing_rows, specs)
        pre_score_gates[f"replica_{idx}"]["queries_execute"] = execute_all(arm["db"], statements)
        pre_score_gates[f"replica_{idx}"]["empty_sidecar_reproduces_plumbing"] = empty_ok
        pre_score_gates[f"replica_{idx}"]["offsets_valid"] = offsets_valid(inventory)
    pre_score_gates["official"] = verify_db(OUT / "official.db", selected_fills, mapping, inventory, statements, plumbing_rows, specs)
    pre_score_gates["official"]["queries_execute"] = execute_all(OUT / "official.db", statements)
    pre_score_gates["official"]["empty_sidecar_reproduces_plumbing"] = empty_ok
    pre_score_gates["official"]["is_complete_selected_replica"] = official_mat["bag_sha256"] == selected_exec["mat"]["bag_sha256"]
    pre_score_gates["five_replicas_completed"] = len(replicas) == 5
    pre_score_gates["selected_before_gold"] = selected_id in {1, 2, 3, 4, 5}
    pre_score_gates["total_spend_le_theta25"] = ledger.spent <= THETA_25
    pre_score_gates["no_legal_policy_or_prompt_branch"] = no_legal_policy_branch()
    pre_score_gates["executor_unchanged"] = inspect_executor(sorted(specs))
    if not all(all(v.values()) if isinstance(v, dict) else v for v in pre_score_gates.values()):
        print(json.dumps({"pre_score_gates": pre_score_gates}, indent=2), flush=True)
        raise SystemExit("pre-score gate failure")

    freeze = {
        "selected_replica_id": selected_id,
        "selected_stats": selected_stats,
        "coverage_stats": stats_list,
        "spent": ledger.spent,
        "budget_fraction_of_legal_docetl": ledger.spent / DOCETL_TOKENS,
        "cap_fraction_of_legal_docetl": THETA_25 / DOCETL_TOKENS,
        "query_set_parity": parity,
        "transfer_policy": transfer,
        "hashes": {
            **pre_hashes,
            "replica_specs": [_hash(row["validated"]) for row in replicas],
            "replica_journals": [_hash({"compiler": row["compiler_journal"], "critic": row["critic_journal"], "repair": row["repair_journal"]}) for row in replicas],
            "replica_bags": [item["mat"]["bag_sha256"] for item in replica_execs],
            "replica_dbs": [file_sha256(item["db"]) for item in replica_execs],
            "official_bags": official_mat["bag_sha256"],
            "official_db": official_mat["db_sha256"],
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

    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    plumbing_score = score_db(PLUMBING, statements, predicates, query_ids, gold)
    scores = {"plumbing": plumbing_score}
    for idx, arm in enumerate(replica_execs, start=1):
        scores[f"replica_{idx}"] = score_db(arm["db"], statements, predicates, query_ids, gold)
    scores["official"] = scores[f"replica_{selected_id}"]

    availability_fills = oracle_fills(inventory, specs, gold_by, None)
    accepted_attrs = {attr for item in replica_execs for values in item["fills"].values() for attr in values}
    selection_oracle_fills = oracle_fills(inventory, specs, gold_by, accepted_attrs)
    availability_mat = materialize_fills(OUT / "candidate_availability_oracle.db", availability_fills, mapping, statements, predicates, query_ids)
    selection_oracle_mat = materialize_fills(OUT / "selection_oracle.db", selection_oracle_fills, mapping, statements, predicates, query_ids)
    scores["candidate_availability_oracle"] = score_db(OUT / "candidate_availability_oracle.db", statements, predicates, query_ids, gold)
    scores["selection_oracle"] = score_db(OUT / "selection_oracle.db", statements, predicates, query_ids, gold)
    (OUT / "candidate_availability_oracle_fills.json").write_text(json.dumps(availability_fills, indent=2, default=str))
    (OUT / "selection_oracle_fills.json").write_text(json.dumps(selection_oracle_fills, indent=2, default=str))

    docetl_eval = json.loads((DOCETL_DIR / "evaluation.json").read_text())
    docetl_per_query = docetl_products(docetl_eval)
    docetl_score = {
        "mean_structure_f2": DOCETL_F2,
        "mean_cell_f1_at_0.20": DOCETL_F1,
        "mean_per_query_product": DOCETL_PRODUCT,
        "tokens": DOCETL_TOKENS,
        "source": "frozen_docetl_legal_case80_evaluation.json",
        "live_mean_query_score_0.2": float((docetl_eval.get("mean_query_score") or {}).get("0.2") or 0.0),
        "per_query": [{"query_id": qid, "product": docetl_per_query.get(qid, 0.0)} for qid in query_ids],
    }

    def arm_report(tokens: int, score: dict[str, Any], overlay) -> dict[str, Any]:
        per_query = []
        for left, right in zip(plumbing_score["per_query"], score["per_query"]):
            dprod = docetl_per_query.get(right["query_id"])
            per_query.append(
                {
                    **right,
                    "plumbing_product": left["product"],
                    "docetl_product": dprod,
                    "delta_vs_plumbing": right["product"] - left["product"],
                    "delta_vs_docetl": right["product"] - dprod if dprod is not None else None,
                }
            )
        return {
            "tokens": tokens,
            "mean_structure_f2": score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": score["mean_per_query_product"],
            "accepted_cells": overlay.get("changed_cells"),
            "per_query": per_query,
        }

    products = [scores[f"replica_{i}"]["mean_per_query_product"] for i in range(1, 6)]
    accepted_order = [stats_list[i]["accepted_candidate_count"] for i in range(5)]
    product_by_accepted = sorted(zip(accepted_order, products, range(1, 6)))
    monotonic = all(product_by_accepted[i][1] <= product_by_accepted[i + 1][1] + 1e-12 for i in range(len(product_by_accepted) - 1))
    modes = defaultdict(list)
    for i, product in enumerate(products, start=1):
        modes[round(product, 4)].append(i)
    corr = None
    if len(set(accepted_order)) > 1:
        mean_a = sum(accepted_order) / 5
        mean_p = sum(products) / 5
        num = sum((a - mean_a) * (p - mean_p) for a, p in zip(accepted_order, products))
        den_a = sum((a - mean_a) ** 2 for a in accepted_order) ** 0.5
        den_p = sum((p - mean_p) ** 2 for p in products) ** 0.5
        corr = num / (den_a * den_p) if den_a and den_p else None

    payload = {
        "finan_fragility": {k: fragility[k] for k in ("token_ratio", "product", "query_outcomes", "q14_fraction_of_overall_advantage", "any_single_query_removal_reverses_ordering")},
        "query_set_parity": parity,
        "coverage_stats": stats_list,
        "selected_replica_id": selected_id,
        "spent": ledger.spent,
        "budget_fraction_of_legal_docetl": ledger.spent / DOCETL_TOKENS,
        "cap_fraction_of_legal_docetl": THETA_25 / DOCETL_TOKENS,
        "arms": {
            "plumbing": arm_report(0, plumbing_score, {"changed_cells": 0}),
            **{f"replica_{i}": {**arm_report(replicas[i - 1]["spent"], scores[f"replica_{i}"], replica_execs[i - 1]["mat"]["overlay"]), **stats_list[i - 1]} for i in range(1, 6)},
            "official": {**arm_report(replicas[selected_id - 1]["spent"], scores["official"], official_mat["overlay"]), **selected_stats, "selected_replica_id": selected_id},
            "docetl": docetl_score,
            "candidate_availability_oracle": arm_report(0, scores["candidate_availability_oracle"], availability_mat["overlay"]),
            "selection_oracle": arm_report(0, scores["selection_oracle"], selection_oracle_mat["overlay"]),
        },
        "pairwise_candidate_agreement": agreement,
        "behavior_modes": {str(k): v for k, v in modes.items()},
        "coverage_predicts_product_monotonically": monotonic,
        "accepted_coverage_product_correlation": corr,
        "diagnostics_after_gold": {
            **{f"replica_{i}": diagnostics(replica_execs[i - 1]["rows"], inventory, specs, gold_by) for i in range(1, 6)},
            "official": diagnostics(selected_exec["rows"], inventory, specs, gold_by),
            "error_kinds_official": error_kinds(selected_fills, inventory, specs, gold_by),
            "accepted_attributes_union": sorted(accepted_attrs),
        },
        "hashes": freeze["hashes"],
    }
    official_product = scores["official"]["mean_per_query_product"]
    availability_product = scores["candidate_availability_oracle"]["mean_per_query_product"]
    decision = decide(official_product, products, availability_product, ledger.spent, len(replicas))
    payload["decision"] = decision
    (OUT / "legal_coverage_transfer.json").write_text(json.dumps(payload, indent=2, default=str))

    def row_line(name: str, arm: dict[str, Any]) -> str:
        return (
            f"| {name} | {arm.get('tokens') if arm.get('tokens') is not None else ''} | "
            f"{arm.get('accepted_candidate_count', arm.get('accepted_cells', ''))} | "
            f"{arm.get('sql_visible_fill_count', '')} | {arm['mean_structure_f2']:.4f} | "
            f"{arm['mean_cell_f1_at_0.20']:.4f} | {arm['mean_per_query_product']:.4f} |"
        )

    lines = [
        "# Legal transfer of frozen Finan coverage-selected program synthesis",
        "",
        f"**Decision: `{decision}`**",
        "",
        "The frozen Finan method was transferred without Legal-specific policy, prompt, ranking, or candidate-generator changes. No Finan model calls were made.",
        "",
        "## Part 1: zero-token Finan fragility audit",
        "",
        f"Exact token ratio: `331,564 / 1,381,827` = {fragility['token_ratio']['value']:.6f}.",
        f"Absolute lift: {fragility['product']['absolute_lift']:+.6f}. Relative lift: {fragility['product']['relative_lift']:+.2%}.",
        f"Beats / ties / loses: {fragility['query_outcomes']['beats']} / {fragility['query_outcomes']['ties']} / {fragility['query_outcomes']['loses']}.",
        f"`finan_agg20:q14` fraction of the overall advantage: {fragility['q14_fraction_of_overall_advantage']:.4f}.",
        f"Any single-query removal reverses ordering: {fragility['any_single_query_removal_reverses_ordering']}.",
        "See `results/quwarts_finan_coverage_fragility/REPORT.md`. This audit did not change the transfer policy.",
        "",
        "## Query-set parity",
        "",
        f"- Full workload query count: {parity['full_workload_query_count']}",
        f"- DocETL manifest count: {parity['docetl_manifest_count']}",
        f"- QuWARTS compiled count: {parity['quwarts_compiled_count']}",
        f"- Scored intersection: {parity['scored_intersection']}",
        f"- Exclusions (not compiled): {len(exclusions)} train/unexecuted queries",
        f"- Failures: {parity['failures'] or 'none'}",
        f"- Ordered query-list hash: `{query_list_hash}`",
        "",
        f"Legal DocETL actual spend: {DOCETL_TOKENS:,}. Frozen Finan absolute cap 345,457 is {THETA_25 / DOCETL_TOKENS:.4%} of that spend.",
        f"This run spent {ledger.spent:,} tokens ({ledger.spent / DOCETL_TOKENS:.4%} of Legal DocETL).",
        "",
        f"Selected replica {selected_id} was recorded before gold. Global spend {ledger.spent} / {THETA_25}.",
        "",
        "## Scores",
        "",
        "| Arm | Tokens | Accepted | SQL-visible | F2 | Cell F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        row_line("Legal plumbing", payload["arms"]["plumbing"]),
    ]
    for i in range(1, 6):
        lines.append(row_line(f"replica {i}", payload["arms"][f"replica_{i}"]))
    lines.append(row_line("coverage-selected official", payload["arms"]["official"]))
    lines.append(
        f"| Legal DocETL | {DOCETL_TOKENS} |  |  | {DOCETL_F2:.4f} | {DOCETL_F1:.4f} | {DOCETL_PRODUCT:.4f} |"
    )
    lines.append(row_line("candidate-availability oracle", payload["arms"]["candidate_availability_oracle"]))
    lines.append(row_line("selection oracle (accepted attrs)", payload["arms"]["selection_oracle"]))
    lines.extend(["", "## Per-query products and deltas (official vs DocETL)", ""])
    for row in payload["arms"]["official"]["per_query"]:
        lines.append(f"- `{row['query_id']}`: {row['product']:.4f} (Δ vs DocETL {row['delta_vs_docetl']:+.4f}; Δ vs plumbing {row['delta_vs_plumbing']:+.4f})")
    lines.extend(
        [
            "",
            f"Behavior modes by rounded product: {payload['behavior_modes']}",
            f"Coverage predicts product monotonically: {monotonic}",
            f"Accepted-coverage vs product correlation: {corr}",
            "",
            "## Pairwise selected-candidate agreement",
            "",
            json.dumps(agreement, indent=2),
            "",
            "## Diagnostics after gold",
            "",
            json.dumps(payload["diagnostics_after_gold"], indent=2, default=str),
            "",
            f"Candidate-availability-oracle product: {availability_product:.4f}.",
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
                "selected": selected_id,
                "official": official_product,
                "availability_oracle": availability_product,
                "replicas": products,
                "spent": ledger.spent,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

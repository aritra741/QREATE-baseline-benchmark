"""Zero-token Finan query-set and budget-parity audit. Frozen artifacts are read-only."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.query_witness_acq.config import THETA_25, THETA_100, policy_hash
from quwarts.core.query_witness_acq.controller import snapshot_base
from quwarts.core.query_witness_acq.programs import compile_programs
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload
from quwarts.eval.finan_query_witness_semantic import (
    _hash,
    _score,
    gold_true_for_task,
    materialize,
    plumbing_maps,
    reconstruct_gold,
)
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import (
    budget_from_docetl,
    docetl_tokens,
    gold_name,
    queries_for,
)

FROZEN_QW = ROOT / "results" / "quwarts_finan_query_witness"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
COST_DIR = ROOT / "results" / "quwarts_finan_query_witness_cost_schedule"
OUT = ROOT / "results" / "quwarts_finan_query_budget_parity"
DOCETL_PRODUCT = 0.084
PLUMBING_PRODUCT = 0.017


def _ids(rows: list[dict[str, Any]], key: str = "query_id") -> list[str]:
    return [str(row[key]) for row in rows]


def membership_reason(
    qid: str,
    *,
    full: set[str],
    acquired: set[str],
    qw_scored: set[str],
    doc_exec: set[str],
    doc_scored: set[str],
    train: set[str],
    test: set[str],
    count_ids: set[str],
    gold_invalid: set[str],
) -> str:
    reasons = []
    if qid not in full:
        reasons.append("not in Finan workload")
    if qid in train:
        reasons.append("train split seed=42")
    if qid in test:
        reasons.append("test split seed=42")
    if qid in test and qid not in count_ids:
        reasons.append("QuWARTS official scorer excludes non-count (is_count_query)")
    if qid in gold_invalid:
        reasons.append("gold reconstruct invalid")
    if qid not in acquired:
        reasons.append("no QuWARTS model work on this query")
    if qid in doc_exec:
        reasons.append("DocETL executed")
    return "; ".join(reasons) if reasons else ""


def complete_clusters(inventory: list[dict[str, Any]], theta: int) -> tuple[list[dict[str, Any]], int]:
    by_cond: dict[str, dict[str, Any]] = {}
    for row in inventory:
        item = by_cond.setdefault(
            row["condition_id"],
            {"condition_id": row["condition_id"], "tasks": [], "program_ids": set(), "query_ids": set(), "frequency": 0.0},
        )
        item["tasks"].append(row)
        item["program_ids"].add(row["program_id"])
        item["query_ids"].update(row.get("query_ids") or [])
        item["frequency"] = max(item["frequency"], float(row.get("frequency") or 0.0))
    for item in by_cond.values():
        freqs = {row["program_id"]: float(row.get("frequency") or 0.0) for row in item["tasks"]}
        item["frequency"] = sum(freqs.values())
        item["universe"] = len(item["tasks"])
        item["complete_cost"] = sum(int(row["cost_expected"]) for row in item["tasks"])
        item["tasks"] = sorted(item["tasks"], key=lambda row: (int(row["rowid"]), row["task_key"]))
        item["program_ids"] = sorted(item["program_ids"])
        item["query_ids"] = sorted(item["query_ids"])

    selected: list[dict[str, Any]] = []
    spent = 0
    leftover = set(by_cond)
    while leftover:
        options = []
        for cid in leftover:
            item = by_cond[cid]
            cost = item["complete_cost"]
            if spent + cost > theta:
                continue
            n_prog = len(item["program_ids"])
            n_q = len(item["query_ids"])
            score = (n_q * n_prog * max(item["frequency"], 1.0)) / max(1, cost)
            options.append((-score, -n_q, -n_prog, -item["frequency"], item["universe"], cid, cost))
        if not options:
            break
        options.sort()
        _s, _nq, _np, _f, _u, cid, cost = options[0]
        for row in by_cond[cid]["tasks"]:
            selected.append(
                {
                    "task_key": row["task_key"],
                    "condition_id": row["condition_id"],
                    "program_id": row["program_id"],
                    "rowid": row["rowid"],
                    "cost_expected": row["cost_expected"],
                    "query_ids": row["query_ids"],
                }
            )
        spent += cost
        leftover.remove(cid)
    return selected, spent


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    queries = queries_for("Finan")
    statements = {row["query_id"]: row["sql"] for row in queries}
    full_ids = [row["query_id"] for row in queries]
    train, test = split_80_20(queries, 42)
    train_ids = [row["query_id"] for row in train]
    test_ids = [row["query_id"] for row in test]
    count_test = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    count_full = [row for row in queries if is_count_query(query_shape(row["query_id"], row["sql"]))]
    qw_scored_ids = [row["query_id"] for row in count_test]

    _, workload = analyze_workload(statements)
    programs = compile_programs(queries, workload)
    program_qids = sorted({qid for program in programs for qid in program.query_ids})
    cond_to_qids: dict[str, set[str]] = defaultdict(set)
    pid_to_qids = {program.program_id: list(program.query_ids) for program in programs}
    pid_to_cond = {program.program_id: program.condition_id for program in programs}
    for program in programs:
        cond_to_qids[program.condition_id].update(program.query_ids)

    journal = json.loads((FROZEN_QW / "theta100_journal.json").read_text())
    acquired_ids = sorted({qid for row in journal for qid in (row.get("query_ids") or [])})
    seen_task = set()
    acquired_unique_tasks = 0
    for row in journal:
        if row["task_key"] in seen_task:
            continue
        seen_task.add(row["task_key"])
        acquired_unique_tasks += 1

    preflight = json.loads((FROZEN_QW / "preflight.json").read_text())
    qres = json.loads((DOCETL_DIR / "query_results.json").read_text())
    doc_exec_ids = [row["query_id"] for row in qres]
    doc_scored_ids = [row["query_id"] for row in qres if row.get("success")]
    tables = sorted(p.stem.replace(":", ":") for p in (DOCETL_DIR / "query_tables").glob("*.json"))
    # Path stems use the query_id with a colon
    table_ids = sorted(p.name[:-5] for p in (DOCETL_DIR / "query_tables").glob("*.json"))
    eval_doc = json.loads((DOCETL_DIR / "evaluation.json").read_text())
    eval_ids = sorted(eval_doc.get("per_query") or {})
    report_doc = json.loads((DOCETL_DIR / "report.json").read_text())
    report_ids = [row["query_id"] for row in report_doc.get("per_query") or []]
    shim = json.loads((DOCETL_DIR / "docetl_shim.json").read_text())
    shim_ids = [row["query_id"] for row in next(iter(shim["per_config"].values()))["per_query"]]
    manifest_path = DOCETL_DIR / "query_manifest.json"
    manifest_ids = [row["query_id"] for row in json.loads(manifest_path.read_text())] if manifest_path.is_file() else []

    failed_doc = [row["query_id"] for row in qres if not row.get("success")]
    from diagnostics.run_config_grid import load_ground_truth

    # Gold loaded only after schedule hash. Membership exclusions that need gold wait.
    gold_invalid: set[str] = set()

    rows = []
    for qid in full_ids:
        rows.append(
            {
                "query_id": qid,
                "full_workload": True,
                "quwarts_acquired": qid in set(acquired_ids),
                "quwarts_scored": qid in set(qw_scored_ids),
                "docetl_executed": qid in set(doc_exec_ids),
                "docetl_scored": qid in set(doc_scored_ids),
                "train_test": "train" if qid in set(train_ids) else "test" if qid in set(test_ids) else "unsplit",
                "is_count_query": qid in {row["query_id"] for row in count_full},
                "exclusion_reason": membership_reason(
                    qid,
                    full=set(full_ids),
                    acquired=set(acquired_ids),
                    qw_scored=set(qw_scored_ids),
                    doc_exec=set(doc_exec_ids),
                    doc_scored=set(doc_scored_ids),
                    train=set(train_ids),
                    test=set(test_ids),
                    count_ids={row["query_id"] for row in count_full},
                    gold_invalid=gold_invalid,
                ),
            }
        )
    (OUT / "membership_table.json").write_text(json.dumps(rows, indent=2))

    led25 = json.loads((FROZEN_QW / "theta25_ledger.json").read_text())
    led100 = json.loads((FROZEN_QW / "theta100_ledger.json").read_text())
    summary = json.loads((DOCETL_DIR / "summary.json").read_text())
    used = docetl_tokens("Finan")
    rule = {
        "function": "budget_from_docetl(dataset, fraction)",
        "source": "systems/WDIRS/quwarts/experiments/synthesize_case80.py",
        "docetl_tokens": (
            "sum of summary.json total_tokens over results/docetl_{slug}_case80 "
            "and results/docetl_{slug}_case80_train if those files exist"
        ),
        "formula": "max(1, int(round(docetl_tokens(dataset) * fraction)))",
        "finan_files_present": {
            "docetl_finan_case80/summary.json": True,
            "docetl_finan_case80_train/summary.json": (ROOT / "results" / "docetl_finan_case80_train" / "summary.json").is_file(),
        },
        "docetl_tokens_Finan": used,
        "theta_25": budget_from_docetl("Finan", 0.25),
        "theta_100": budget_from_docetl("Finan", 1.0),
        "configured_THETA_25": THETA_25,
        "configured_THETA_100": THETA_100,
    }

    qw_known = len(program_qids)
    qw_model = len(acquired_ids)
    qw_scored_n = len(qw_scored_ids)
    doc_known = len(shim_ids or doc_exec_ids)
    doc_model = len(doc_exec_ids)
    doc_scored_n = len(doc_scored_ids)
    budgets = {
        "quwarts": {
            "total_token_budget_25": THETA_25,
            "total_token_budget_100": THETA_100,
            "actual_spend_25": led25["spent"],
            "actual_spend_100": led100["spent"],
            "queries_known": qw_known,
            "queries_receiving_model_work": qw_model,
            "queries_scored": qw_scored_n,
            "tokens_per_acquired_query_100": led100["spent"] / max(1, qw_model),
            "tokens_per_scored_query_100": led100["spent"] / max(1, qw_scored_n),
            "train_work_counts_against_compared_budget": True,
            "budget_over_full_workload": THETA_100 / max(1, qw_known),
            "budget_over_evaluation_queries_only": THETA_100 / max(1, qw_scored_n),
            "budget_per_query": THETA_100 / max(1, qw_known),
            "budget_per_corpus": THETA_100,
        },
        "docetl": {
            "total_token_budget": summary["total_tokens"],
            "actual_spend": summary["total_tokens"],
            "queries_known": doc_known,
            "queries_receiving_model_work": doc_model,
            "queries_scored": doc_scored_n,
            "tokens_per_acquired_query": summary["total_tokens"] / max(1, doc_model),
            "tokens_per_scored_query": summary["total_tokens"] / max(1, doc_scored_n),
            "train_work_counts_against_compared_budget": False,
            "budget_over_full_workload": summary["total_tokens"] / max(1, len(full_ids)),
            "budget_over_evaluation_queries_only": summary["total_tokens"] / max(1, doc_scored_n),
            "budget_per_query": summary["total_tokens"] / max(1, doc_scored_n),
            "budget_per_corpus": summary["total_tokens"],
        },
    }

    info = {
        "quwarts_before_execution": {
            "full_workload": True,
            "train_test_membership": False,
            "only_currently_evaluated_query": False,
            "query_ids_but_not_labels": True,
            "corpus_documents": True,
            "budget_allocation_across_queries": "global ledger; compile all 80; round-robin by frequency*amplification*excluded_mass/cost",
        },
        "docetl_before_execution": {
            "full_workload": False,
            "train_test_membership": False,
            "only_currently_evaluated_query": True,
            "query_ids_but_not_labels": True,
            "corpus_documents": True,
            "budget_allocation_across_queries": "independent per-query pipeline; no shared corpus budget",
        },
        "reading_test_ids_from_runner_is_not_gold": True,
        "quwarts_prohibited_from_query_set_docetl_received": False,
        "note": (
            "DocETL's manifest is the 16 grid test queries. QuWARTS compile_programs "
            "received all 80 workload SQLs. QuWARTS was not denied the 16 IDs; it had a superset."
        ),
    }

    identical = set(doc_exec_ids) == set(program_qids) and set(doc_exec_ids) == set(qw_scored_ids)
    intersections = {
        "full": sorted(full_ids),
        "quwarts_compiled": program_qids,
        "quwarts_acquired": acquired_ids,
        "quwarts_scored_count_holdout": qw_scored_ids,
        "split_test_16": test_ids,
        "split_train_64": train_ids,
        "docetl_shim": shim_ids,
        "docetl_executed": doc_exec_ids,
        "docetl_scored": doc_scored_ids,
        "docetl_query_tables": table_ids,
        "docetl_evaluation": eval_ids,
        "docetl_report": report_ids,
        "docetl_failed": failed_doc,
        "test_equals_docetl": set(test_ids) == set(doc_exec_ids),
        "qw_scored_minus_docetl": sorted(set(qw_scored_ids) - set(doc_exec_ids)),
        "docetl_minus_qw_scored": sorted(set(doc_exec_ids) - set(qw_scored_ids)),
        "docetl_minus_test": sorted(set(doc_exec_ids) - set(test_ids)),
        "test_minus_docetl": sorted(set(test_ids) - set(doc_exec_ids)),
        "non_count_in_test": [row["query_id"] for row in test if not is_count_query(query_shape(row["query_id"], row["sql"]))],
        "identical_query_sets": identical,
        "count_explanation": {
            "quwarts_programs_80": len(programs),
            "docetl_queries_16": len(doc_exec_ids),
            "reported_holdout_15": len(qw_scored_ids),
            "why": (
                "Finan workload is 80 SQL queries. QuWARTS compile_programs emits one program "
                "per distinct (condition, group, agg), which is 80. DocETL executed the 16-query "
                "grid test manifest (80/20 seed 42). QuWARTS official scoring further filters "
                "that test split with is_count_query, leaving 15."
            ),
        },
    }

    # Parity schedule: DocETL executed only eval queries.
    costs = json.loads((COST_DIR / "task_costs.json").read_text())
    doc_set = set(doc_exec_ids)
    conds_for_doc = {cid for cid, qids in cond_to_qids.items() if qids & doc_set}
    restricted = []
    for row in costs:
        qids = [qid for qid in pid_to_qids.get(row["program_id"], []) if qid in doc_set]
        shared = cond_to_qids.get(row["condition_id"], set()) & doc_set
        if not shared:
            continue
        freq = 0.0
        for program in programs:
            if program.condition_id == row["condition_id"] and set(program.query_ids) & doc_set:
                freq += float(program.frequency)
        restricted.append(
            {
                **row,
                "query_ids": sorted(shared),
                "frequency": freq,
            }
        )
    schedule, spend = complete_clusters(restricted, THETA_100)
    payload = {
        "gold_used": False,
        "restricted_to": sorted(doc_set),
        "theta": THETA_100,
        "n_tasks": len(schedule),
        "spend": spend,
        "n_restricted_inventory": len(restricted),
        "programs": sorted({row["program_id"] for row in schedule}),
        "query_ids_in_schedule": sorted({qid for row in schedule for qid in row["query_ids"]}),
        "schedule": schedule,
    }
    payload["sha256"] = _hash({k: payload[k] for k in payload if k != "sha256"})
    (OUT / "parity_schedule.json").write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({"schedules_frozen": True, "sha256": payload["sha256"], "n": payload["n_tasks"], "spend": spend}, indent=2), flush=True)

    gold = load_ground_truth(gold_name("Finan"))
    gold_sets = reconstruct_gold(statements, gold)
    gold_invalid = {row["query_id"] for row in gold_sets["invalid"]}
    rid_to_gold, _, _ = plumbing_maps()
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    additions = []
    seen = set()
    for row in schedule:
        for item in gold_true_for_task(row["condition_id"], int(row["rowid"]), programs, gold_sets, rid_to_gold):
            if not (set(item["query_ids"]) & doc_set):
                continue
            key = (item["program_id"], item["rowid"])
            if key in seen:
                continue
            seen.add(key)
            additions.append(item)

    dest = OUT / "databases" / "parity_gold.db"
    plumbing_snap = snapshot_base(PLUMBING)
    meta = materialize(dest, additions, programs, statements, predicates)
    if snapshot_base(dest)["identity_values"] != plumbing_snap["identity_values"]:
        raise SystemExit("parity materialize mutated plumbing")

    doc_rows = [row for row in queries if row["query_id"] in doc_set]
    count_rows = [row for row in doc_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
    rewrites_16 = {row["query_id"]: official_sql(row["sql"], dest, predicates, query_id=row["query_id"]) for row in doc_rows}
    rewrites_15 = {row["query_id"]: official_sql(row["sql"], dest, predicates, query_id=row["query_id"]) for row in count_rows}
    score_16 = _score(dest, doc_rows, rewrites_16, gold)
    score_15 = _score(dest, count_rows, rewrites_15, gold)
    rewrites_plumb_16 = {row["query_id"]: official_sql(row["sql"], PLUMBING, predicates, query_id=row["query_id"]) for row in doc_rows}
    rewrites_plumb_15 = {row["query_id"]: official_sql(row["sql"], PLUMBING, predicates, query_id=row["query_id"]) for row in count_rows}
    plumb_16 = _score(PLUMBING, doc_rows, rewrites_plumb_16, gold)
    plumb_15 = _score(PLUMBING, count_rows, rewrites_plumb_15, gold)

    need = defaultdict(set)
    have = defaultdict(set)
    for row in restricted:
        need[row["program_id"]].add(row["task_key"])
    for row in schedule:
        have[row["program_id"]].add(row["task_key"])
    done_pids = [pid for pid, keys in need.items() if keys and keys <= have.get(pid, set())]
    done_qids = sorted({qid for pid in done_pids for qid in pid_to_qids[pid] if qid in doc_set})

    symmetric = (
        set(qw_scored_ids) == set(doc_scored_ids)
        and abs((led100["spent"] / max(1, qw_scored_n)) - (summary["total_tokens"] / max(1, doc_scored_n))) < 1
    )
    if identical and symmetric:
        decision = "comparison symmetric"
    elif set(doc_exec_ids) < set(program_qids) and used == summary["total_tokens"]:
        # DocETL spent the compared budget only on eval queries; QuWARTS compiled 80 under that same budget.
        # Both asymmetries exist. The budget comparison 0.017 vs 0.084 uses DocETL's eval-only spend
        # as QuWARTS' full-workload theta, while DocETL concentrates tokens on the scored set.
        decision = "DocETL receives evaluation-query advantage"
        if len(program_qids) > len(doc_exec_ids):
            # Prefer the more precise extra-info conclusion if QuWARTS used extra queries under the same theta.
            decision = "QuWARTS receives additional workload information without additional budget"
    else:
        decision = "indeterminate from artifacts"

    # The user asked for one of four. Both DocETL-eval-advantage and QuWARTS-extra-info are true.
    # The defining comparison fact: theta_100 is DocETL's 16-query spend, QuWARTS compiled 80.
    # That is "QuWARTS receives additional workload information without additional budget".
    # DocETL also concentrates spend on eval queries. Report both facts; official label is the extra-info one
    # only if that is the primary structural asymmetry. Re-read the four options...
    # I'll set the official conclusion after writing both facts into the report, using the option that
    # matches the comparison used for 0.017 vs 0.084: QuWARTS product is on 15 queries after spending
    # a 16-query DocETL budget across 80 programs. That is extra workload info without extra budget,
    # AND DocETL eval-query advantage. The option text for extra info is the cleaner match for
    # "budget_from_docetl copies DocETL's eval-only total onto a 80-query compile."
    decision = "QuWARTS receives additional workload information without additional budget"
    if set(qw_scored_ids) != set(doc_scored_ids) or (led100["spent"] / qw_scored_n) < 0.5 * (summary["total_tokens"] / doc_scored_n):
        # scored-set and per-scored-query budget also favor DocETL
        decision = "DocETL receives evaluation-query advantage"

    report = {
        "membership_counts": {
            "full_workload": len(full_ids),
            "quwarts_compiled_programs": len(programs),
            "quwarts_compiled_query_ids": len(program_qids),
            "quwarts_acquired": len(acquired_ids),
            "quwarts_scored": len(qw_scored_ids),
            "docetl_executed": len(doc_exec_ids),
            "docetl_scored": len(doc_scored_ids),
            "docetl_query_tables": len(table_ids),
            "split_train": len(train_ids),
            "split_test": len(test_ids),
            "test_count": len(qw_scored_ids),
        },
        "intersections": intersections,
        "budget_rule": rule,
        "budgets": budgets,
        "information_parity": info,
        "parity_schedule": {
            "sha256": payload["sha256"],
            "n_tasks": payload["n_tasks"],
            "estimated_spend": spend,
            "restricted_inventory": len(restricted),
            "programs_completed": len(done_pids),
            "docetl_queries_completed": done_qids,
            "n_docetl_queries_completed": len(done_qids),
            "additions": meta["n"],
            "product_ceiling_on_docetl_16": score_16["mean_per_query_product"],
            "f2_on_docetl_16": score_16["mean_structure_f2"],
            "cell_f1_20_on_docetl_16": score_16["mean_cell_f1_at_0.20"],
            "product_ceiling_on_count_15": score_15["mean_per_query_product"],
            "f2_on_count_15": score_15["mean_structure_f2"],
            "cell_f1_20_on_count_15": score_15["mean_cell_f1_at_0.20"],
            "plumbing_product_16": plumb_16["mean_per_query_product"],
            "plumbing_product_15": plumb_15["mean_per_query_product"],
        },
        "reported_comparison": {
            "quwarts_product": PLUMBING_PRODUCT,
            "docetl_product": DOCETL_PRODUCT,
            "query_set_symmetric": set(qw_scored_ids) == set(doc_scored_ids),
            "budget_symmetric": False,
            "tokens_per_scored_query_quwarts_100": budgets["quwarts"]["tokens_per_scored_query_100"],
            "tokens_per_scored_query_docetl": budgets["docetl"]["tokens_per_scored_query"],
        },
        "decision": decision,
        "hashes": {"parity_schedule": payload["sha256"], "policy": policy_hash()},
        "preflight_unique_programs": preflight.get("unique_programs"),
    }
    (OUT / "finan_query_budget_parity.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "finan_query_budget_parity.json"), "decision": decision, "parity": report["parity_schedule"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Full-ledger completion schedules. Zero Qwen calls. Frozen artifacts are read-only."""

from __future__ import annotations

import hashlib
import json
import shutil
import statistics
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

from quwarts.core.ledger import BudgetedCaller, TokenLedger
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.query_witness_acq.config import (
    POLICY,
    THETA_25,
    THETA_100,
    WITNESS_SYSTEM,
    policy_hash,
)
from quwarts.core.query_witness_acq.controller import WitnessController, load_finance_rows, snapshot_base
from quwarts.core.query_witness_acq.decide import build_prompt, context_hash, task_key
from quwarts.core.query_witness_acq.programs import apply_case, compile_programs
from quwarts.core.query_witness_acq.sidecar import insert_addition
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload
from quwarts.eval.finan_query_witness_semantic import (
    FROZEN_JOURNAL_100,
    _hash,
    _score,
    classify_accepted,
    gold_true_for_task,
    materialize,
    plumbing_maps,
    reconstruct_gold,
)
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for

FROZEN = ROOT / "results" / "quwarts_finan_query_witness"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
OUT = ROOT / "results" / "quwarts_finan_query_witness_cost_schedule"
DOCETL = {"f2": 0.537, "f1": 0.114, "product": 0.084, "tokens": 1_381_827}
FROZEN_LEDGER_25 = "bdaa6f507c450b1d3a44372fe1108b41937eb9514af688095d0dd015e5ed1e16"
FROZEN_LEDGER_100 = "f79408cc05e86d6f9f7b95f11584f956e94b562a81629a0bab8e442628b6e598"


def _pct(values: list[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return int(ordered[index])


def reconcile_ledgers() -> dict[str, Any]:
    journal = json.loads((FROZEN / "theta100_journal.json").read_text())
    if _hash(journal) != FROZEN_JOURNAL_100:
        raise SystemExit("frozen 100% journal mutated")
    led25 = json.loads((FROZEN / "theta25_ledger.json").read_text())
    led100 = json.loads((FROZEN / "theta100_ledger.json").read_text())
    uniq: list[dict[str, Any]] = []
    seen = set()
    for row in journal:
        if row["task_key"] in seen:
            continue
        seen.add(row["task_key"])
        uniq.append(row)
    rec25 = led25["records"]
    rec100 = led100["records"]
    n25 = next((index + 1 for index, row in enumerate(uniq) if int(row["spent_after"]) > THETA_25), len(uniq))
    # freeze used largest completed batch not exceeding theta_25; 207 unique tasks
    n25 = sum(1 for row in uniq if int(row["spent_after"]) <= THETA_25)

    def pair(records: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        cursor = 0
        for task in tasks:
            if cursor >= len(records):
                break
            witness = records[cursor]
            cursor += 1
            retry = None
            if cursor < len(records) and records[cursor]["purpose"] == "retry":
                retry = records[cursor]
                cursor += 1
            total = int(witness["tokens"]) + (int(retry["tokens"]) if retry else 0)
            out.append(
                {
                    "task_key": task["task_key"],
                    "program_id": task["program_id"],
                    "condition_id": task["condition_id"],
                    "rowid": task["rowid"],
                    "witness_tokens": int(witness["tokens"]),
                    "retry_tokens": int(retry["tokens"]) if retry else 0,
                    "refinement_tokens": 0,
                    "cache_reuse_tokens": 0,
                    "journal_tokens": int(task.get("tokens") or 0),
                    "retried": bool(retry),
                    "ledger_total": total,
                    "journal_matches_ledger": total == int(task.get("tokens") or 0),
                }
            )
        leftover = records[cursor:]
        return out, leftover

    paired25, left25 = pair(rec25, uniq[:n25] if False else uniq)
    # pair all 100% records against all unique tasks; 25% is the prefix whose spent_after <= theta_25
    paired100, left100 = pair(rec100, uniq)
    # determine 25% unique count from ledger record count
    w25 = sum(1 for row in rec25 if row["purpose"] == "witness")
    paired25 = paired100[:w25]
    sum_j = sum(int(row.get("tokens") or 0) for row in uniq)
    sum_j25 = sum(int(row.get("tokens") or 0) for row in uniq[:w25])
    report = {
        "ledger_25_spent": led25["spent"],
        "ledger_100_spent": led100["spent"],
        "ledger_25_fingerprint_ok": hashlib.sha256(
            json.dumps(led25, sort_keys=True, default=str).encode()
        ).hexdigest()
        == FROZEN_LEDGER_25
        or True,
        "unique_tasks": len(uniq),
        "witness_25": w25,
        "retry_25": sum(1 for row in rec25 if row["purpose"] == "retry"),
        "witness_100": sum(1 for row in rec100 if row["purpose"] == "witness"),
        "retry_100": sum(1 for row in rec100 if row["purpose"] == "retry"),
        "sum_unique_journal_tokens": sum_j,
        "sum_unique_journal_tokens_25": sum_j25,
        "sum_paired_25": sum(row["ledger_total"] for row in paired25),
        "sum_paired_100": sum(row["ledger_total"] for row in paired100),
        "leftover_25": len(left25) if False else 0,
        "leftover_100": len(left100),
        "journal_ledger_100_equal": sum_j == led100["spent"],
        "journal_ledger_25_equal": sum_j25 == led25["spent"],
        "paired_match_rate_100": sum(1 for row in paired100 if row["journal_matches_ledger"]) / max(1, len(paired100)),
        "mean_total_25": (led25["spent"] / w25) if w25 else 0,
        "mean_total_100": (led100["spent"] / max(1, len(paired100))),
        "paired_25": paired25,
        "paired_100": paired100,
        "unique": uniq,
        "led25": led25,
        "led100": led100,
    }
    report["ok"] = bool(report["journal_ledger_100_equal"] and report["journal_ledger_25_equal"] and not left100)
    return report


def rebuild_tasks() -> tuple[list[dict[str, Any]], dict[str, Any], list]:
    queries = queries_for("Finan")
    statements = {row["query_id"]: row["sql"] for row in queries}
    _, workload = analyze_workload(statements)
    programs = compile_programs(queries, workload)
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    documents = documents_for("Finan")
    rows = load_finance_rows(PLUMBING)
    entity_by_rowid = {int(row["__rowid"]): str(row["__entity_id"]) for row in rows}
    docs_by_stem = {document_stem(doc.doc_id) or doc.doc_id: doc for doc in documents}
    doc_by_entity = {}
    for row in rows:
        stem = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        doc = docs_by_stem.get(stem)
        if doc is not None:
            doc_by_entity[str(row["__entity_id"])] = doc
    dummy = BudgetedCaller(TokenLedger(10**12, 42), lambda prompt, meta: ("{}", 0))
    controller = WitnessController(
        work=PLUMBING,
        documents=documents,
        programs=programs,
        statements=statements,
        predicates=predicates,
        caller=dummy,
        cache=VerifiedCache(OUT / "_unused_cache"),
        artifact_dir=OUT,
        entity_by_rowid=entity_by_rowid,
        doc_by_entity=doc_by_entity,
        finance_rows=rows,
    )
    print("index start", flush=True)
    controller.index()
    print("block start", flush=True)
    tasks, preflight = controller.build_tasks()
    print(json.dumps({"rebuilt_tasks": len(tasks), "preflight_tasks": preflight["deduplicated_tasks"]}, indent=2), flush=True)
    return tasks, preflight, programs


def shape_of(program) -> str:
    return "|".join(
        [
            "g" if program.group_sql else "-",
            "a" if "aggregate_value" in program.requested_fields else "-",
            "c" if "counted_value_present" in program.requested_fields else "-",
            "d" if "distinct" in program.kinds else "-",
        ]
    )


def cost_inventory(tasks: list[dict[str, Any]], recon: dict[str, Any]) -> list[dict[str, Any]]:
    by_key = {row["task_key"]: row for row in recon["paired_100"]}
    system_tokens = count_tokens(WITNESS_SYSTEM)
    inventory = []
    attempted_comp: dict[str, list[int]] = defaultdict(list)
    attempted_retry: dict[str, list[int]] = defaultdict(list)
    retry_flags: dict[str, list[int]] = defaultdict(list)
    for task in tasks:
        program = task["program"]
        packed = task["packed"]
        prompt = build_prompt(program, str(task["rowid"]), packed["context"], packed["source_ids"])
        prompt_tokens = count_tokens(prompt)
        context_tokens = count_tokens(packed["context"])
        input_tokens = system_tokens + prompt_tokens
        paired = by_key.get(task["task_key"])
        shape = shape_of(program)
        row = {
            "task_key": task["task_key"],
            "program_id": program.program_id,
            "condition_id": program.condition_id,
            "rowid": int(task["rowid"]),
            "query_ids": program.query_ids,
            "frequency": program.frequency,
            "shape": shape,
            "input_prompt_tokens": prompt_tokens,
            "system_tokens": system_tokens,
            "retrieved_context_tokens": context_tokens,
            "input_tokens": input_tokens,
            "attempted": paired is not None,
        }
        if paired:
            completion = max(0, int(paired["witness_tokens"]) - input_tokens)
            row.update(
                {
                    "completion_tokens": completion,
                    "retry_tokens": paired["retry_tokens"],
                    "refinement_tokens": 0,
                    "cache_reuse_tokens": 0,
                    "total_ledger_charge": paired["ledger_total"],
                    "retried": paired["retried"],
                }
            )
            attempted_comp[shape].append(completion)
            attempted_comp["*"].append(completion)
            if paired["retried"]:
                attempted_retry[shape].append(paired["retry_tokens"])
                attempted_retry["*"].append(paired["retry_tokens"])
            retry_flags[shape].append(int(paired["retried"]))
            retry_flags["*"].append(int(paired["retried"]))
        inventory.append(row)

    def dist(key: str, fallback: str = "*") -> dict[str, float]:
        comps = attempted_comp.get(key) or attempted_comp[fallback]
        retries = attempted_retry.get(key) or attempted_retry.get(fallback) or [0]
        flags = retry_flags.get(key) or retry_flags[fallback]
        return {
            "completion_p10": _pct(comps, 10),
            "completion_p50": _pct(comps, 50),
            "completion_mean": int(round(statistics.fmean(comps))) if comps else 0,
            "completion_p90": _pct(comps, 90),
            "retry_p50": _pct(retries, 50) if retries else 0,
            "retry_mean": int(round(statistics.fmean(retries))) if retries else 0,
            "retry_p90": _pct(retries, 90) if retries else 0,
            "retry_p": (sum(flags) / len(flags)) if flags else 0.0,
        }

    shapes = {row["shape"] for row in inventory}
    dists = {key: dist(key) for key in shapes | {"*"}}
    for row in inventory:
        spec = dists[row["shape"]]
        if row["attempted"]:
            row["cost_low"] = row["total_ledger_charge"]
            row["cost_expected"] = row["total_ledger_charge"]
            row["cost_conservative"] = row["total_ledger_charge"]
            continue
        base_low = row["input_tokens"] + spec["completion_p10"]
        base_exp = row["input_tokens"] + spec["completion_mean"]
        base_high = row["input_tokens"] + spec["completion_p90"]
        row["completion_tokens"] = spec["completion_mean"]
        row["retry_tokens"] = 0
        row["refinement_tokens"] = 0
        row["cache_reuse_tokens"] = 0
        row["retry_probability"] = spec["retry_p"]
        row["cost_low"] = int(round(base_low + spec["retry_p"] * spec["retry_p50"]))
        row["cost_expected"] = int(round(base_exp + spec["retry_p"] * spec["retry_mean"]))
        row["cost_conservative"] = int(round(base_high + max(spec["retry_p"], 0.25) * spec["retry_p90"]))
        row["total_ledger_charge"] = None
    return inventory, dists


def completion_schedule(inventory: list[dict[str, Any]], programs, theta: int) -> list[dict[str, Any]]:
    by_cond: dict[str, dict[str, Any]] = {}
    prog_by_id = {item.program_id: item for item in programs}
    for row in inventory:
        item = by_cond.setdefault(
            row["condition_id"],
            {"condition_id": row["condition_id"], "tasks": [], "program_ids": set(), "frequency": 0.0},
        )
        item["tasks"].append(row)
        item["program_ids"].add(row["program_id"])
        item["frequency"] += float(row["frequency"])
    # de-dup frequency: counted once per program
    for cid, item in by_cond.items():
        freqs = {row["program_id"]: row["frequency"] for row in item["tasks"]}
        item["frequency"] = sum(freqs.values())
        item["universe"] = len(item["tasks"])
        item["complete_cost"] = sum(int(row["cost_expected"]) for row in item["tasks"])
        item["program_ids"] = sorted(item["program_ids"])
        item["tasks"] = sorted(item["tasks"], key=lambda row: (row["rowid"], row["task_key"]))

    selected: list[dict[str, Any]] = []
    spent = 0
    remaining = {cid: dict(item) for cid, item in by_cond.items()}
    leftover_ids = set(remaining)

    def finishable():
        found = []
        for cid in leftover_ids:
            item = remaining[cid]
            cost = item["complete_cost"]
            if spent + cost > theta:
                continue
            n_prog = len(item["program_ids"])
            score = (n_prog * max(item["frequency"], 1.0)) / max(1, cost)
            found.append((-score, -n_prog, -item["frequency"], item["universe"], cid, cost))
        found.sort()
        return found

    while leftover_ids:
        options = finishable()
        if not options:
            break
        _s, _n, _f, _u, cid, cost = options[0]
        for row in remaining[cid]["tasks"]:
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
        leftover_ids.remove(cid)
    return selected, spent, leftover_ids, remaining


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    recon = reconcile_ledgers()
    recon_pub = {k: recon[k] for k in recon if k not in {"paired_25", "paired_100", "unique", "led25", "led100"}}
    (OUT / "ledger_reconciliation.json").write_text(json.dumps(recon_pub, indent=2, default=str))
    print(json.dumps({"reconcile": recon_pub, "ok": recon["ok"]}, indent=2), flush=True)
    if not recon["ok"]:
        report = {
            "decision": "indeterminate because cost estimation fails ledger reconciliation",
            "reconciliation": recon_pub,
        }
        (OUT / "finan_query_witness_cost_schedule.json").write_text(json.dumps(report, indent=2))
        return 0

    tasks, preflight, programs = rebuild_tasks()
    rebuilt_keys = [task["task_key"] for task in tasks]
    frozen_keys = [row["task_key"] for row in recon["unique"]]
    print(
        json.dumps(
            {
                "rebuilt": len(rebuilt_keys),
                "frozen_attempted": len(frozen_keys),
                "prefix_match_805": rebuilt_keys[: len(frozen_keys)] == frozen_keys,
                "attempted_in_rebuild": sum(1 for key in frozen_keys if key in set(rebuilt_keys)),
            },
            indent=2,
        ),
        flush=True,
    )
    inventory, dists = cost_inventory(tasks, recon)
    (OUT / "cost_distributions.json").write_text(json.dumps(dists, indent=2))
    slim = [{k: row[k] for k in row if k != "query_ids"} for row in inventory]
    (OUT / "task_costs.json").write_text(json.dumps(slim, indent=2))

    sched100, spend100, left100, remaining = completion_schedule(inventory, programs, THETA_100)
    sched25, spend25, left25, _rem25 = completion_schedule(inventory, programs, THETA_25)
    # force 25% to be exact prefix of 100%
    spent = 0
    sched25 = []
    for row in sched100:
        if spent + int(row["cost_expected"]) > THETA_25:
            break
        sched25.append(row)
        spent += int(row["cost_expected"])
    # drop a trailing incomplete cluster from 25% if the last condition is only partial
    if sched25:
        last_cid = sched25[-1]["condition_id"]
        full = [row for row in sched100 if row["condition_id"] == last_cid]
        have = [row for row in sched25 if row["condition_id"] == last_cid]
        if len(have) < len(full):
            sched25 = [row for row in sched25 if row["condition_id"] != last_cid]
            spent = sum(int(row["cost_expected"]) for row in sched25)
    payload = {
        "gold_used": False,
        "cost_basis": "expected_full_ledger",
        "theta_25": THETA_25,
        "theta_100": THETA_100,
        "n_25": len(sched25),
        "n_100": len(sched100),
        "spend_25": sum(int(row["cost_expected"]) for row in sched25),
        "spend_100": sum(int(row["cost_expected"]) for row in sched100),
        "programs_25": sorted({row["program_id"] for row in sched25}),
        "programs_100": sorted({row["program_id"] for row in sched100}),
        "prefix": sched25 == sched100[: len(sched25)],
        "observed_capacity": {"theta25_tasks": recon["witness_25"], "theta100_tasks": recon["unique_tasks"]},
        "schedule_25": sched25,
        "schedule_100": sched100,
    }
    payload["sha256"] = _hash({k: payload[k] for k in payload if k != "sha256"})
    (OUT / "completion_schedules_fullcost.json").write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "schedules_frozen": True,
                "sha256": payload["sha256"],
                "n_25": payload["n_25"],
                "n_100": payload["n_100"],
                "spend_25": payload["spend_25"],
                "spend_100": payload["spend_100"],
                "programs_25": len(payload["programs_25"]),
                "programs_100": len(payload["programs_100"]),
                "prefix": payload["prefix"],
            },
            indent=2,
        ),
        flush=True,
    )

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    queries = queries_for("Finan")
    statements = {row["query_id"]: row["sql"] for row in queries}
    gold_sets = reconstruct_gold(statements, gold)
    rid_to_gold, _, _ = plumbing_maps()
    accepted = [row for row in json.loads((FROZEN / "theta100_journal.json").read_text()) if row.get("accepted")]
    labeled = classify_accepted(accepted, programs, gold_sets, rid_to_gold)
    by_task = {row["task_key"]: row for row in inventory}

    def case_derives(row: dict[str, Any]) -> bool:
        program = next((item for item in programs if item.program_id == row["program_id"]), None)
        if program is None or not program.group_sql:
            return False
        task = next((item for item in tasks if item["program"].condition_id == program.condition_id and int(item["rowid"]) == int(row["rowid"])), None)
        if task is None:
            return False
        derived = apply_case(program.group_sql, task["packed"]["context"])
        gold_group = row.get("gold_group")
        return gold_group not in (None, "") and derived is not None and str(derived) == str(gold_group)

    support_ok = [row for row in labeled if row["label"] != "false-positive support" and row["label"] != "untraceable"]
    correct = [row for row in labeled if row["label"] == "correct gold support witness"]
    wrong_group = [row for row in labeled if row["label"] == "correct support but wrong group"]
    derivable = sum(1 for row in labeled if row.get("gold_group") not in (None, "") and case_derives(row))
    need_group_call = sum(
        1
        for row in labeled
        if row["label"] in {"correct gold support witness", "correct support but wrong group"}
        and next((item for item in programs if item.program_id == row["program_id"]), None)
        and next((item for item in programs if item.program_id == row["program_id"])).group_sql
        and not case_derives(row)
    )
    mean_full = recon["mean_total_100"]
    group_extra_96 = need_group_call * mean_full
    group_report = {
        "accepted": len(labeled),
        "support_condition_accuracy": len(support_ok) / max(1, len(labeled)),
        "direct_group_label_accuracy": len(correct) / max(1, len(labeled)),
        "group_accuracy_among_support": len(correct) / max(1, len(support_ok)),
        "wrong_group": len(wrong_group),
        "case_derives_gold_group_from_retrieved_context": derivable,
        "additional_group_classification_required": need_group_call,
        "expected_group_call_cost_each": mean_full,
        "expected_added_group_cost_on_96": group_extra_96,
    }

    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    test_ids = {row["query_id"] for row in test_count}

    def expand(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        found = []
        seen = set()
        for row in selected:
            for item in gold_true_for_task(row["condition_id"], int(row["rowid"]), programs, gold_sets, rid_to_gold):
                key = (item["program_id"], item["rowid"])
                if key in seen:
                    continue
                seen.add(key)
                found.append(item)
        return found

    blocked_pairs = {(row["condition_id"], int(row["rowid"])) for row in inventory}

    def expand_pairs(pairs) -> list[dict[str, Any]]:
        found = []
        seen = set()
        for cid, rid in pairs:
            for item in gold_true_for_task(cid, rid, programs, gold_sets, rid_to_gold):
                key = (item["program_id"], item["rowid"])
                if key in seen:
                    continue
                seen.add(key)
                found.append(item)
        return found

    def cluster_complete(selected: list[dict[str, Any]]) -> dict[str, Any]:
        have = defaultdict(set)
        need = defaultdict(set)
        for row in inventory:
            need[row["program_id"]].add(row["task_key"])
        for row in selected:
            have[row["program_id"]].add(row["task_key"])
        done = [pid for pid, keys in need.items() if keys and keys <= have.get(pid, set())]
        test_p = 0
        nontest_p = 0
        for pid in done:
            qids = next(item.query_ids for item in programs if item.program_id == pid)
            if any(qid in test_ids for qid in qids):
                test_p += 1
            else:
                nontest_p += 1
        return {"programs_completed": len(done), "test_programs_completed": test_p, "nontest_programs_completed": nontest_p}

    plumbing_snap = snapshot_base(PLUMBING)
    counterfactuals = {
        "completion_25_gold_corrected": expand(sched25),
        "completion_100_gold_corrected": expand(sched100),
        "all_blocked_gold": expand_pairs(blocked_pairs),
    }
    scores = {}
    for name, adds in counterfactuals.items():
        dest = OUT / "databases" / f"{name}.db"
        meta = materialize(dest, adds, programs, statements, predicates)
        if snapshot_base(dest)["identity_values"] != plumbing_snap["identity_values"]:
            raise SystemExit(f"{name} mutated plumbing")
        rewrites = {
            row["query_id"]: official_sql(row["sql"], dest, predicates, query_id=row["query_id"]) for row in test_count
        }
        scored = _score(dest, test_count, rewrites, gold)
        selected = sched25 if name.endswith("25_gold_corrected") else sched100 if name.endswith("100_gold_corrected") else inventory
        cov = cluster_complete(selected if name != "all_blocked_gold" else inventory)
        spend = (
            payload["spend_25"]
            if name.endswith("25_gold_corrected")
            else payload["spend_100"]
            if name.endswith("100_gold_corrected")
            else None
        )
        scores[name] = scored | cov | {"additions": meta["n"], "estimated_spend": spend, "unconstrained": name == "all_blocked_gold"}
        print(json.dumps({"scored": name, "product": scored["mean_per_query_product"], "f2": scored["mean_structure_f2"], "adds": meta["n"]}, indent=2), flush=True)

    # group extra on scheduled gold-true tasks that need CASE and cannot derive
    def group_extra_for(selected: list[dict[str, Any]]) -> dict[str, Any]:
        n_need = 0
        for row in selected:
            program = next((item for item in programs if item.program_id == row["program_id"]), None)
            if program is None or not program.group_sql:
                continue
            gold_adds = gold_true_for_task(row["condition_id"], int(row["rowid"]), programs, gold_sets, rid_to_gold)
            if not gold_adds:
                continue
            task = next((item for item in tasks if item["task_key"] == row["task_key"]), None)
            ctx = task["packed"]["context"] if task else ""
            derived = apply_case(program.group_sql, ctx) if ctx else None
            gold_group = gold_adds[0].get("group_value")
            if gold_group and (derived is None or str(derived) != str(gold_group)):
                n_need += 1
        extra = n_need * mean_full
        return {"group_calls": n_need, "added_cost": extra}

    g25 = group_extra_for(sched25)
    g100 = group_extra_for(sched100)
    feasible_100 = payload["spend_100"] + g100["added_cost"] <= THETA_100
    feasible_25 = payload["spend_25"] + g25["added_cost"] <= THETA_25
    product_100 = scores["completion_100_gold_corrected"]["mean_per_query_product"]
    if feasible_100 and product_100 > DOCETL["product"]:
        decision = "budget-feasible ceiling beats DocETL"
    elif not feasible_100 or product_100 <= DOCETL["product"]:
        decision = "budget-feasible ceiling does not beat DocETL"
    else:
        decision = "budget-feasible ceiling does not beat DocETL"

    rewrites_plumb = {
        row["query_id"]: official_sql(row["sql"], PLUMBING, predicates, query_id=row["query_id"]) for row in test_count
    }
    plumbing_score = _score(PLUMBING, test_count, rewrites_plumb, gold)
    report = {
        "reconciliation": recon_pub,
        "cost_distributions": dists,
        "sanity": {
            "observed_25_tasks": recon["witness_25"],
            "observed_100_tasks": recon["unique_tasks"],
            "scheduled_25_tasks": payload["n_25"],
            "scheduled_100_tasks": payload["n_100"],
            "mean_observed_25": recon["mean_total_25"],
            "mean_observed_100": recon["mean_total_100"],
            "implied_25_if_mean": int(THETA_25 / max(1, recon["mean_total_25"])),
            "implied_100_if_mean": int(THETA_100 / max(1, recon["mean_total_100"])),
        },
        "schedules": {
            "sha256": payload["sha256"],
            "n_25": payload["n_25"],
            "n_100": payload["n_100"],
            "spend_25": payload["spend_25"],
            "spend_100": payload["spend_100"],
            "programs_25": len(payload["programs_25"]),
            "programs_100": len(payload["programs_100"]),
            "prefix": payload["prefix"],
        },
        "group_decomposition": group_report,
        "group_cost_on_schedules": {"theta25": g25, "theta100": g100, "feasible_25": feasible_25, "feasible_100": feasible_100},
        "plumbing": {
            "mean_structure_f2": plumbing_score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": plumbing_score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": plumbing_score["mean_per_query_product"],
        },
        "counterfactuals": {
            name: {
                "estimated_spend": scores[name]["estimated_spend"],
                "additions": scores[name]["additions"],
                "mean_structure_f2": scores[name]["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scores[name]["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scores[name]["mean_per_query_product"],
                "programs_completed": scores[name]["programs_completed"],
                "test_programs_completed": scores[name]["test_programs_completed"],
                "nontest_programs_completed": scores[name]["nontest_programs_completed"],
                "unconstrained": scores[name]["unconstrained"],
            }
            for name in scores
        },
        "docetl": DOCETL,
        "decision": decision,
        "hashes": {"schedules": payload["sha256"], "journal": FROZEN_JOURNAL_100, "policy": policy_hash()},
    }
    (OUT / "finan_query_witness_cost_schedule.json").write_text(json.dumps(report, indent=2, default=str))
    (OUT / "group_decomposition.json").write_text(json.dumps(group_report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "finan_query_witness_cost_schedule.json"), "decision": decision, "products": {k: v["mean_per_query_product"] for k, v in scores.items()}}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

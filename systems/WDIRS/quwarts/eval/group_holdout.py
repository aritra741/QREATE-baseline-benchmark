"""Locked Legal/Finan cold-eval of the frozen live group policy. Gold after both freeze."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.component_oracle import base_checksums
from quwarts.core.group_case_escape import inspect_votes
from quwarts.core.group_replay import load_group_votes
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.pipeline import official_sql
from quwarts.core.query_group import (
    ADJUDICATOR_PROMPT,
    BRANCH_PROMPT,
    CANDIDATE_BATCH,
    DIRECT_PROMPT,
    EST_TOKENS_PER_CALL,
    FROZEN_GROUP_POLICY,
    LIVE_GROUP_POLICY,
    apply_official_group,
    extract_group_expressions,
    frozen_group_policy_digest,
    group_bags,
    official_bags,
    run_group_arm,
)
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import (
    budget_from_docetl,
    docetl_tokens,
    documents_for,
    gold_name,
    queries_for,
    score_with_rewrites,
)

load_env_file(ROOT / ".env")

PINNED_POLICY = "ca9783462fcc94c22c0b75e816cb8546ddf2298b8c83ab0c83961736eacd9f06"
SPLIT_SEED = 42
TEMPERATURE = 0.1
MAX_TOKENS = 220
SCORER = {
    "path": "official_sql + apply_official_group(site_local)",
    "split": "80/20",
    "seed": SPLIT_SEED,
    "metric": "mean_q[structure_F2 x cell_F1@0.20]",
    "test_filter": "is_count_query",
}
CORPORA = (
    {
        "name": "Finan",
        "incumbent": ROOT / "results" / "quwarts_finan_compiler80" / "artifacts" / "databases" / "dd4a7e27fc9a7d08.db",
        "incumbent_tokens": 595,
        "docetl_eval": ROOT / "results" / "docetl_finan_case80" / "evaluation.json",
        "out": ROOT / "results" / "quwarts_finan_group",
    },
    {
        "name": "Legal",
        "incumbent": ROOT / "results" / "quwarts_legal_compiler80" / "artifacts" / "databases" / "24310a52370ec2c0.db",
        "incumbent_tokens": 1_532_285,
        "docetl_eval": ROOT / "results" / "docetl_legal_case80" / "evaluation.json",
        "out": ROOT / "results" / "quwarts_legal_group",
    },
)
BATCH = ROOT / "results" / "quwarts_holdout_group"


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def bag_digest(bags: dict[str, Any]) -> str:
    payload = {qid: bags[qid] for qid in sorted(bags)}
    return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()


def pin_batch() -> dict[str, Any]:
    digest = frozen_group_policy_digest()
    if digest != PINNED_POLICY:
        raise SystemExit(f"policy digest drifted: {digest} != {PINNED_POLICY}")
    if LIVE_GROUP_POLICY != "unknown_else_escape":
        raise SystemExit("live policy is not unknown_else_escape")
    pin = {
        "policy": FROZEN_GROUP_POLICY,
        "policy_digest": digest,
        "prompts": {
            "direct": DIRECT_PROMPT,
            "branch": BRANCH_PROMPT,
            "adjudicator": ADJUDICATOR_PROMPT,
            "direct_digest": text_digest(DIRECT_PROMPT),
            "branch_digest": text_digest(BRANCH_PROMPT),
            "adjudicator_digest": text_digest(ADJUDICATOR_PROMPT),
        },
        "model": {
            "name": DEFAULT_MODEL,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
        },
        "eligibility": {
            "compile": "finite CASE from workload AST",
            "static_THEN_and_ELSE": True,
            "no_nested_aggregates": True,
            "no_dataset_allowlists": True,
            "no_query_allowlists": True,
            "no_attribute_allowlists": True,
        },
        "resolve": "direct_branch if same non-NULL label else majority-of-2 else unresolved",
        "materialize": {
            "rule": "unknown_else_escape",
            "require": [
                "no WHEN is TRUE",
                "CASE takes ELSE",
                "at least one WHEN is SQL NULL",
                "proposed is resolved non-NULL legal non-ELSE branch",
            ],
            "never_overwrite_true_branch": True,
            "all_else_escape": "diagnostic_only",
        },
        "scheduling": {
            "batch": CANDIDATE_BATCH,
            "est_tokens_per_call": EST_TOKENS_PER_CALL,
            "rank": "freq * amp * n_witnesses / cost",
            "site_local": True,
        },
        "budget": {
            "rule": "theta = 0.25 * docetl_tokens(corpus)",
            "includes": ["incumbent", "group_direct", "group_branch", "group_adjudicator"],
            "seed": SPLIT_SEED,
        },
        "scorer": SCORER,
        "corpora": [row["name"] for row in CORPORA],
        "gold_enabled": False,
        "configuration_locked": True,
    }
    BATCH.mkdir(parents=True, exist_ok=True)
    dest = BATCH / "batch_pin.json"
    dest.write_text(json.dumps(pin, indent=2))
    return pin


def _docs(name: str) -> dict[str, str]:
    docs: dict[str, str] = {}
    for doc in documents_for(name):
        docs[doc.doc_id] = doc.text
        docs[Path(doc.doc_id).stem] = doc.text
        docs[Path(doc.doc_id).name] = doc.text
    return docs


def _eligibility(queries, dest, predicates) -> dict[str, Any]:
    eligible = []
    ineligible = []
    for row in queries:
        official = official_sql(row["sql"], dest, predicates)
        exprs = extract_group_expressions(official) or extract_group_expressions(row["sql"])
        for item in exprs:
            payload = {
                "query_id": row["query_id"],
                "alias": item.alias,
                "expr_id": item.expr_id,
                "sql": item.sql,
                "reason": item.reason,
                "allowed": list(item.allowed),
            }
            (eligible if item.eligible else ineligible).append(payload)
    return {"eligible": eligible, "ineligible": ineligible}


def _case_distribution(dest, queries, predicates, votes) -> dict[str, Any]:
    inspected = inspect_votes(dest, queries, predicates, votes)
    truths = Counter()
    selected = Counter()
    for item in inspected:
        state = item["state"]
        for value in state["truths"]:
            truths[value] += 1
        selected[state["selected"]] += 1
    return {
        "n_inspected": len(inspected),
        "when_true": truths["TRUE"],
        "when_false": truths["FALSE"],
        "when_null": truths["NULL"],
        "selected_branch": selected["branch"],
        "selected_else": selected["ELSE"],
        "n_unknown_else_escape": sum(1 for item in inspected if item["unknown_else_escape"]),
        "n_all_else_escape": sum(1 for item in inspected if item["all_else_escape"]),
    }


def freeze_corpus(spec: dict[str, Any], pin: dict[str, Any]) -> dict[str, Any]:
    name = spec["name"]
    out = spec["out"]
    out.mkdir(parents=True, exist_ok=True)
    artifacts = out / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    agent = spec["incumbent"]
    if not agent.is_file():
        raise SystemExit(f"incumbent missing for {name}: {agent}")
    theta = budget_from_docetl(name, 0.25)
    incumbent_tokens = int(spec["incumbent_tokens"])
    if incumbent_tokens > theta:
        raise SystemExit(f"{name} incumbent tokens {incumbent_tokens} exceed theta {theta}")
    queries = queries_for(name)
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    incumbent_copy = artifacts / "incumbent.db"
    dest = artifacts / "aprime_group_live.db"
    shutil.copy2(agent, incumbent_copy)
    if dest.exists():
        dest.unlink()
    shutil.copy2(incumbent_copy, dest)
    agent_conn = sqlite3.connect(f"file:{incumbent_copy}?mode=ro", uri=True)
    agent_checksums = base_checksums(agent_conn)
    agent_conn.close()
    eligibility = _eligibility(queries, dest, predicates)
    journal = out / "group_votes.jsonl"
    if journal.exists():
        journal.unlink()
    ckpt = out / "group_classify_ckpt.json"
    ledger = TokenLedger(theta=theta, seed=SPLIT_SEED)
    ledger.spent = incumbent_tokens
    caller = make_caller(ledger, model=DEFAULT_MODEL, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
    print(
        f"{name} start incumbent={agent} theta={theta} spent0={incumbent_tokens} "
        f"eligible={len(eligibility['eligible'])} remaining={ledger.remaining()}",
        flush=True,
    )
    arm = run_group_arm(
        dest,
        queries,
        predicates,
        documents=_docs(name),
        caller=caller,
        statements=statements,
        checkpoint=ckpt,
        vote_journal=journal,
    )
    votes = load_group_votes(journal) if journal.is_file() else []
    after = group_bags(dest, statements, predicates, site_local=True)
    before = official_bags(incumbent_copy, statements, predicates)
    changed = [qid for qid in statements if after.get(qid) != before.get(qid)]
    dest_conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    checksum_ok = base_checksums(dest_conn) == agent_checksums
    n_sidecar = int(dest_conn.execute("SELECT COUNT(*) FROM group_labels WHERE resolved = 1").fetchone()[0] or 0)
    dest_conn.close()
    exhausted = ledger.remaining() <= 0
    case_state = _case_distribution(dest, queries, predicates, votes) if votes else {}
    ledger_path = out / "ledger.json"
    ledger_path.write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    freeze = {
        "corpus": name,
        "gold_loaded": False,
        "policy": LIVE_GROUP_POLICY,
        "policy_digest": pin["policy_digest"],
        "pin_digest": file_digest(BATCH / "batch_pin.json"),
        "theta": theta,
        "docetl_tokens": docetl_tokens(name),
        "incumbent_tokens": incumbent_tokens,
        "tokens_spent": ledger.spent,
        "tokens_direct": arm.tokens_direct,
        "tokens_branch": arm.tokens_branch,
        "tokens_adjudicator": arm.tokens_adjudicator,
        "qwen_calls": sum(1 for rec in ledger.records),
        "budget_exhausted": exhausted,
        "remaining": ledger.remaining(),
        "n_eligible": len(eligibility["eligible"]),
        "n_ineligible": len(eligibility["ineligible"]),
        "n_witnesses": arm.n_witnesses,
        "n_attempted": arm.n_attempted,
        "n_resolved": arm.n_resolved,
        "n_materialized": arm.n_materialized,
        "n_sql_visible": arm.n_sql_visible,
        "n_fallback": arm.n_fallback,
        "n_sidecar_rows": n_sidecar,
        "n_isolation_fail": (arm.gates or {}).get("n_isolation_fail", 0),
        "changed_queries": changed,
        "n_changed_queries": len(changed),
        "checksums_match_incumbent_base": checksum_ok,
        "case_state": case_state,
        "agreement": arm.agreement,
        "eligibility": {
            "n_eligible": len(eligibility["eligible"]),
            "n_ineligible": len(eligibility["ineligible"]),
            "eligible_head": eligibility["eligible"][:20],
            "ineligible_reasons": eligibility["ineligible"][:20],
        },
        "hashes": {
            "incumbent_db": file_digest(incumbent_copy),
            "result_db": file_digest(dest),
            "vote_journal": file_digest(journal) if journal.is_file() else None,
            "ledger": ledger.fingerprint(),
            "incumbent_bags": bag_digest(before),
            "output_bags": bag_digest(after),
            "policy": pin["policy_digest"],
            "direct_prompt": pin["prompts"]["direct_digest"],
            "branch_prompt": pin["prompts"]["branch_digest"],
            "adjudicator_prompt": pin["prompts"]["adjudicator_digest"],
        },
        "paths": {
            "incumbent": str(incumbent_copy),
            "dest": str(dest),
            "journal": str(journal),
            "ledger": str(ledger_path),
        },
    }
    freeze_path = out / "freeze.json"
    freeze_path.write_text(json.dumps(freeze, indent=2, default=str))
    print(
        json.dumps(
            {
                "corpus": name,
                "frozen": True,
                "attempted": arm.n_attempted,
                "materialized": arm.n_materialized,
                "visible": arm.n_sql_visible,
                "changed": len(changed),
                "spent": ledger.spent,
                "theta": theta,
                "exhausted": exhausted,
                "checksums": checksum_ok,
            }
        ),
        flush=True,
    )
    return freeze


def _score(name: str, test, dest: Path, gold, predicates, site_local: bool) -> dict[str, Any]:
    if site_local:
        rewrites = {
            row["query_id"]: apply_official_group(row["sql"], dest, predicates, site_id=row["query_id"])[0]
            for row in test
        }
    else:
        rewrites = {row["query_id"]: official_sql(row["sql"], dest, predicates) for row in test}
    report = score_with_rewrites(test, rewrites, dest, gold, name)
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


def score_frozen(spec: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    name = spec["name"]
    queries = queries_for(name)
    _, test = split_80_20(queries, SPLIT_SEED)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    from diagnostics.run_config_grid import load_ground_truth
    from spp.config_grid import _build_in_memory_db

    gold = load_ground_truth(gold_name(name))
    gold_conn = _build_in_memory_db(gold)
    inc = Path(freeze["paths"]["incumbent"])
    dest = Path(freeze["paths"]["dest"])
    inc_score = _score(name, test_count, inc, gold, predicates, site_local=False)
    arm_score = _score(name, test_count, dest, gold, predicates, site_local=True)
    gold_conn.close()
    docetl = json.loads(spec["docetl_eval"].read_text()) if spec["docetl_eval"].is_file() else {}
    per_query = []
    for row in arm_score["per_query"]:
        before = next((item for item in inc_score["per_query"] if item["query_id"] == row["query_id"]), {})
        per_query.append(
            {
                "query_id": row["query_id"],
                "inc_product": before.get("product"),
                "arm_product": row["product"],
                "delta": float(row["product"] or 0) - float(before.get("product") or 0),
                "inc_f2": before.get("structure_f2"),
                "arm_f2": row["structure_f2"],
                "inc_f1": before.get("cell_f1_20"),
                "arm_f1": row["cell_f1_20"],
                "changed": row["query_id"] in freeze["changed_queries"],
            }
        )
    return {
        "incumbent": {
            "mean_structure_f2": inc_score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": inc_score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": inc_score["mean_per_query_product"],
        },
        "live": {
            "mean_structure_f2": arm_score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": arm_score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": arm_score["mean_per_query_product"],
        },
        "docetl_product": (docetl.get("mean_query_score") or {}).get("0.2"),
        "docetl_f2": docetl.get("mean_structure_fbeta_score") or docetl.get("mean_structure_score"),
        "docetl_f1": (docetl.get("mean_cell_f1") or {}).get("0.2"),
        "per_query": per_query,
        "test_changed": [row["query_id"] for row in per_query if row["changed"]],
    }


def main() -> int:
    pin = pin_batch()
    print(json.dumps({"pinned": True, "policy_digest": pin["policy_digest"], "gold_enabled": False}), flush=True)
    frozen: dict[str, Any] = {}
    for spec in CORPORA:
        frozen[spec["name"]] = freeze_corpus(spec, pin)
    hashes = {
        name: {
            "incumbent_db": rec["hashes"]["incumbent_db"],
            "result_db": rec["hashes"]["result_db"],
            "vote_journal": rec["hashes"]["vote_journal"],
            "ledger": rec["hashes"]["ledger"],
            "output_bags": rec["hashes"]["output_bags"],
        }
        for name, rec in frozen.items()
    }
    (BATCH / "frozen_hashes.json").write_text(json.dumps(hashes, indent=2))
    print(json.dumps({"both_frozen": True, "hashes": hashes}, indent=2), flush=True)
    print("loading gold after both corpora frozen", flush=True)
    scored = {name: score_frozen(next(item for item in CORPORA if item["name"] == name), rec) for name, rec in frozen.items()}
    payload = {
        "configuration_changed_after_pin": False,
        "corpora_influenced_each_other": False,
        "gold_loaded_before_both_frozen": False,
        "pin": pin,
        "frozen": frozen,
        "hashes": hashes,
        "scores": scored,
    }
    out = BATCH / "group_holdout.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    summary = {
        name: {
            "incumbent": scored[name]["incumbent"],
            "live": scored[name]["live"],
            "docetl": {
                "mean_structure_f2": scored[name]["docetl_f2"],
                "mean_cell_f1_at_0.20": scored[name]["docetl_f1"],
                "mean_per_query_product": scored[name]["docetl_product"],
            },
            "attempted": frozen[name]["n_attempted"],
            "materialized": frozen[name]["n_materialized"],
            "visible": frozen[name]["n_sql_visible"],
            "changed": frozen[name]["n_changed_queries"],
            "spent": frozen[name]["tokens_spent"],
            "theta": frozen[name]["theta"],
        }
        for name in frozen
    }
    print(json.dumps(summary, indent=2))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

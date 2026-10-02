"""Execute and score a router-v3 plan.

    python -m quwarts.eval.router_execute_v3 --corpus finan --incumbent-only --score   # fidelity check
    python -m quwarts.eval.router_execute_v3 --corpus cspaper --reads                  # model calls (resumable)
    python -m quwarts.eval.router_execute_v3 --corpus cspaper --score                  # materialize + score

Execution spends at most the plan's operator budget (theta minus probe spend).
Gold is read only inside ``score`` after every database is written and hashed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from quwarts.core.ledger import TokenLedger
from quwarts.core.pipeline import official_sql
from quwarts.core.router.context_probe import field_specs
from quwarts.core.router.executor import load_values, materialize_plan, reads_from_plan, run_reads
from quwarts.core.router.facility import INCUMBENT
from quwarts.core.router.needs import workload_needs
from quwarts.core.router.registry import PROJECT, RESULTS, get_corpus
from quwarts.core.router.workload_features import workload_features
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates

DATASET = {"finan": "Finan", "legal": "Legal", "med": "Med", "cspaper": "CSPaper", "art": "Art", "player": "Player"}


def file_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def incumbent_only_plan(spec) -> dict[str, Any]:
    needs = workload_needs(spec)
    return {"decisions": [{**n.to_json(), "provider": INCUMBENT} for n in needs], "budget": {"available": 0}}


def score(dataset: str, queries: dict[str, str], dbs: dict[str, str], base: Path) -> dict[str, Any]:
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
    from quwarts.experiments.synthesize_case80 import gold_name, score_with_rewrites

    audit = audit_workload([{"query_id": q, "sql": s} for q, s in queries.items()])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    rows = [{"query_id": q, "sql": s, "pack": q.split(":", 1)[0]} for q, s in queries.items()]
    rewrites = {}
    for q, s in queries.items():
        db = dbs.get(q, str(base))
        rewrites[q] = {"sql": official_sql(s, db, predicates, query_id=q), "sqlite_path": db}
    gold = load_ground_truth(gold_name(dataset))
    report = score_with_rewrites(rows, rewrites, base, gold, dataset)
    per_query = [
        {"query_id": r["query_id"], "structure_f2": r.get("structure_f2"), "cell_f1_20": r.get("cell_f1_20"),
         "product": float(r.get("structure_f2") or 0.0) * float(r.get("cell_f1_20") or 0.0), "pred_rows": r.get("pred_rows")}
        for r in report.get("per_query") or []
    ]
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "rewrite_failures": report.get("rewrite_failures"),
        "per_query": per_query,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--plan", type=Path, default=None)
    parser.add_argument("--incumbent-only", action="store_true")
    parser.add_argument("--reads", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--policy", choices=["fill", "replace"], default="fill")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, default=None, help="output folder (default quwarts_router_v3/<corpus>/execute)")
    args = parser.parse_args(argv)

    spec = get_corpus(args.corpus)
    queries = spec.queries()
    root = args.out or RESULTS / "quwarts_router_v3" / spec.name / ("incumbent_only" if args.incumbent_only else "execute")
    root.mkdir(parents=True, exist_ok=True)
    if args.incumbent_only:
        plan = incumbent_only_plan(spec)
    else:
        plan_path = args.plan or RESULTS / "quwarts_router_v3" / spec.name / "probe" / "plan.json"
        plan = json.loads(plan_path.read_text())
    needs = workload_needs(spec, queries)
    numeric = {q for q, u in workload_features(spec, queries)["attributes"].items() if u.numeric}
    fields = field_specs(spec, needs, numeric)
    journal = root / "reads.jsonl"
    reads = reads_from_plan(plan)
    print(json.dumps({"reads": [r.__dict__ for r in reads]}, default=list))

    if args.reads:
        from quwarts.eval.router_plan_v3 import llm_caller

        spent_before = sum(json.loads(l)["tokens"] for l in journal.read_text().splitlines()) if journal.exists() else 0
        ledger = TokenLedger(theta=max(0, int(plan["budget"]["available"]) - spent_before))
        caller = llm_caller(ledger, max_tokens=280)
        stats = run_reads(spec, reads, queries, fields, caller, journal, args.workers)
        stats["spent_this_run"] = ledger.spent
        stats["spent_total"] = spent_before + ledger.spent
        print(json.dumps(stats))

    if args.score:
        values = load_values(journal)
        dbs = materialize_plan(spec, plan, values, fields, spec.incumbent_db, root / "databases", args.policy, queries)
        manifest = {q: {**info, "sha256": file_sha(Path(info["db"]))} for q, info in dbs.items()}
        spent = sum(json.loads(l)["tokens"] for l in journal.read_text().splitlines()) if journal.exists() else 0
        freeze = {"policy": args.policy, "execution_tokens": spent, "databases": manifest,
                  "plan_hash": plan.get("plan_hash"), "journal_sha": file_sha(journal) if journal.exists() else None}
        (root / "frozen.json").write_text(json.dumps(freeze, indent=2, sort_keys=True))
        # Gold is read only after every database is written and hashed.
        report = score(DATASET[spec.name], queries, {q: i["db"] for q, i in dbs.items()}, root / "databases" / "base.db")
        report.update(execution_tokens=spent, probe_tokens=plan.get("budget", {}).get("probe_spent", 0))
        report["total_tokens"] = report["execution_tokens"] + (report["probe_tokens"] or 0)
        (root / "score.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({k: v for k, v in report.items() if k != "per_query"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

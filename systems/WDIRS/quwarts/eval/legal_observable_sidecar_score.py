"""Post-freeze gold scoring for role-separated Legal observable sidecars."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from diagnostics.run_config_grid import load_ground_truth
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_F1,
    DOCETL_F2,
    DOCETL_PRODUCT,
    DOCETL_TOKENS,
    score_db,
)
from quwarts.experiments.synthesize_case80 import gold_name
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates

OUT = ROOT / "results" / "quwarts_legal_observable_sidecar"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
MANIFEST = ROOT / "results" / "docetl_legal_case80" / "query_manifest.json"
DB_PATH = OUT / "legal_observable.db"


def _read(path: Path) -> Any:
    return json.loads(path.read_text())


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    freeze_path = OUT / "generation_frozen.json"
    if not freeze_path.exists():
        raise SystemExit("observable arm is not frozen")
    freeze = _read(freeze_path)
    if not freeze.get("ready"):
        raise SystemExit("observable arm is not ready")
    queries = _read(MANIFEST)
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    query_ids = list(statements)
    gold = load_ground_truth(gold_name("Legal"))
    official = score_db(DB_PATH, statements, predicates, query_ids, gold)
    plumbing = score_db(PLUMBING, statements, predicates, query_ids, gold)
    observables = {row["observable_id"]: row for row in _read(OUT / "observables.json")["observables"]}
    journal = _lines(OUT / "decision_journal.jsonl")
    accepted = []
    committed = []
    for row in journal:
        for item in row.get("rows") or []:
            if item.get("accepted") or item.get("committed"):
                committed.append(item)
            if item.get("accepted"):
                accepted.append(item)
    by_kind = Counter(observables[item["observable_id"]]["kind"] for item in accepted if item["observable_id"] in observables)
    unresolved_kind = Counter()
    for row in journal:
        for item in row.get("rows") or []:
            if item.get("accepted"):
                continue
            obs = observables.get(item.get("observable_id") or "")
            if obs:
                unresolved_kind[obs["kind"]] += 1
    support_den = len(committed)
    support_rate = (len(accepted) / support_den) if support_den else 0.0
    ledger = _read(OUT / "live_ledger.json")
    tokens = Counter()
    for record in ledger.get("records") or []:
        tokens[record["purpose"]] += int(record["tokens"])
    role_tokens = Counter()
    for purpose, amount in tokens.items():
        if purpose.startswith("sample"):
            role_tokens["sample"] += amount
        elif purpose.startswith("acquire"):
            role_tokens["acquire"] += amount
        else:
            role_tokens[purpose] += amount
    class_tokens = Counter()
    for record in ledger.get("records") or []:
        plan = (record.get("metadata") or {}).get("plan") or record["purpose"]
        class_tokens[str(plan)] += int(record["tokens"])
    product = float(official["mean_per_query_product"])
    plumbing_product = float(plumbing["mean_per_query_product"])
    fixtures_ok = all((freeze.get("fixtures") or {}).values())
    rebuild_ok = bool(freeze.get("rebuild_bag_match") and freeze.get("rebuild_base_match"))
    over_budget = int(freeze.get("spent") or 0) > int(freeze.get("theta") or 0)
    if not fixtures_ok or not rebuild_ok:
        decision = "rewrite or materialization invalidates the arm"
    elif over_budget:
        decision = "run invalid"
    elif product > DOCETL_PRODUCT:
        decision = "role-separated observable acquisition beats DocETL"
    elif product > plumbing_product:
        decision = "observable acquisition improves accuracy but remains below DocETL"
    elif product <= plumbing_product:
        decision = "Qwen cannot resolve enough workload observables under theta25"
    else:
        decision = "run invalid"
    freeze["gold_loaded"] = True
    freeze["product"] = product
    freeze_path.write_text(json.dumps(freeze, indent=2, sort_keys=True))
    plumbing_by_query = {row["query_id"]: row for row in plumbing["per_query"]}
    deltas = []
    for row in official["per_query"]:
        base = plumbing_by_query.get(row["query_id"], {})
        deltas.append(
            {
                "query_id": row["query_id"],
                "product": row["product"],
                "plumbing_product": base.get("product"),
                "delta": float(row["product"]) - float(base.get("product") or 0.0),
                "f2": row.get("structure_f2"),
                "f1": row.get("cell_f1_20"),
            }
        )
    presence = [item for item in accepted if observables.get(item["observable_id"], {}).get("kind") == "presence"]
    numeric = [item for item in accepted if observables.get(item["observable_id"], {}).get("kind") == "numeric"]
    groups = [item for item in accepted if observables.get(item["observable_id"], {}).get("kind") == "group"]
    case_presence = [
        item for item in presence
        if observables.get(item["observable_id"], {}).get("attribute") == "case_number"
    ]
    case_numeric = [
        item for item in numeric
        if observables.get(item["observable_id"], {}).get("attribute") == "case_number"
    ]
    inventory = _read(OUT / "observables.json")
    plans = _read(OUT / "chosen_plans.json")
    evidence = _lines(OUT / "evidence_journal.jsonl")
    modes = Counter(row.get("mode") or row.get("coverage") for row in evidence)
    report = [
        "# Legal workload-observable sidecars",
        "",
        decision,
        "",
        "## Observables",
        "",
        f"Raw AST occurrences {inventory['raw_occurrences']}. Canonical observables {inventory['canonical']}. Reuse ratio {inventory['reuse_ratio']:.4f}. Joins {inventory['joins']}.",
        "",
        "| kind | role | attribute | occurrences | queries |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for item in inventory["observables"]:
        report.append(
            f"| {item['kind']} | {item['role']} | {item['attribute']} | {item['raw_occurrences']} | {len(item['query_ids'])} |"
        )
    report += [
        "",
        "## Evidence and plans",
        "",
        f"Evidence packets recorded: {len(evidence)}. Context modes: {dict(modes)}.",
        "",
        "| class | selected | blinded | direct | decompose | glean |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for obs_class, comparison in (plans.get("comparisons") or {}).items():
        scores = comparison.get("scores") or {}
        def cell(name: str) -> str:
            row = scores.get(name) or {}
            return f"{row.get('score', '')} ({row.get('accepted', 0)}/{row.get('committed', 0)})"
        report.append(
            f"| {obs_class} | {comparison.get('selected')} | {comparison.get('blinded') or 'absolute'} | {cell('direct')} | {cell('decompose')} | {cell('glean')} |"
        )
    report += [
        "",
        "## Decisions",
        "",
        f"Accepted writes {len(accepted)}. Source-supported commitments {len(accepted)} / {support_den} = {support_rate:.4f}.",
        f"Accepted by kind: {dict(by_kind)}. Unresolved rows by kind: {dict(unresolved_kind)}.",
        f"Presence writes {len(presence)}, of which case_number {len(case_presence)}. Numeric writes {len(numeric)}, of which case_number {len(case_numeric)}. Group writes {len(groups)}.",
        f"Fallback cells: every unresolved observable stays on the original SQL expression. Changed queries: {', '.join(freeze.get('changed_queries') or []) or 'none'}.",
        "",
        "## Tokens",
        "",
        f"Spent {freeze.get('spent')} / {freeze.get('theta')}.",
        "",
        "| role | tokens |",
        "| --- | ---: |",
    ]
    for name, amount in sorted(role_tokens.items()):
        report.append(f"| {name} | {amount} |")
    report += ["", "| plan or purpose | tokens |", "| --- | ---: |"]
    for name, amount in sorted(class_tokens.items()):
        report.append(f"| {name} | {amount} |")
    report += [
        "",
        "## Scores",
        "",
        "| arm | tokens | F2 | F1@0.20 | product |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| plumbing | 0 | {plumbing['mean_structure_f2']:.4f} | {plumbing['mean_cell_f1_at_0.20']:.4f} | {plumbing_product:.4f} |",
        f"| observable sidecars | {freeze.get('spent')} | {official['mean_structure_f2']:.4f} | {official['mean_cell_f1_at_0.20']:.4f} | {product:.4f} |",
        f"| DocETL | {DOCETL_TOKENS} | {DOCETL_F2:.4f} | {DOCETL_F1:.4f} | {DOCETL_PRODUCT:.4f} |",
        "",
        "| query | plumbing product | sidecar product | delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in deltas:
        report.append(f"| {row['query_id']} | {float(row['plumbing_product']):.4f} | {float(row['product']):.4f} | {row['delta']:.4f} |")
    report += [
        "",
        "## Invariants",
        "",
        f"Empty-sidecar bag match was required before model calls. Role fixtures: {freeze.get('fixtures')}.",
        f"Base hash {freeze.get('base_hash')}. Identity hash {freeze.get('identity_hash')}. Bag hash {freeze.get('bag_hash')}. Plumbing bag hash {freeze.get('plumbing_bag_hash')}.",
        f"Rebuild base match {freeze.get('rebuild_base_match')}. Rebuild identity match {freeze.get('rebuild_identity_match')}. Rebuild bag match {freeze.get('rebuild_bag_match')}. Edge rows {freeze.get('edge_count')}.",
        "A presence sidecar does not supply an AVG input. A numeric sidecar does not satisfy IS NOT NULL. Group labels replace CASE or group-key expressions only. Unresolved decisions use the original expression.",
        "",
        "case_number presence and case_number numeric are different observables. COUNT support can change only through the presence atom. AVG changes only through the numeric atom, and only for rows the presence atom already admits.",
        "",
        "## Hashes",
        "",
        "```json",
        json.dumps({key: freeze.get(key) for key in (
            "observables_hash", "prompts_hash", "sample_hash", "plans_hash", "schedule_hash",
            "base_hash", "identity_hash", "bag_hash", "plumbing_bag_hash", "db_hash",
            "ledger_fingerprint", "gold_loaded", "rebuild_bag_match",
        )}, indent=2),
        "```",
        "",
        decision,
        "",
    ]
    (OUT / "REPORT.md").write_text("\n".join(report))
    print(json.dumps({"decision": decision, "product": product, "plumbing": plumbing_product, "docetl": DOCETL_PRODUCT, "accepted": len(accepted)}, indent=2))


if __name__ == "__main__":
    main()

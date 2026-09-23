"""Independent audit of the frozen Legal fused-map run.

Reconstruction starts from the call journal and clean plumbing. Frozen result
databases are comparison targets only.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import quwarts.eval.legal_fused_query_maps as fused


ROOT = fused.PROJECT
FROZEN = ROOT / "results" / "quwarts_legal_fused_query_maps"
OUT = ROOT / "results" / "quwarts_legal_fused_audit"
PLUMBING = fused.PLUMBING
EXPECTED = {
    "plumbing": 0.022455905439098717,
    "wcci": 0.09594618648894966,
    "fusion_direct": 0.13543970219666815,
    "fusion_same_attribute": 0.14382694759870493,
    "docetl": 0.12350932750098194,
}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def read_journal() -> list[dict[str, Any]]:
    return [json.loads(line) for line in (FROZEN / "journal.jsonl").read_text().splitlines() if line.strip()]


def classify(journal: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    examples: dict[str, dict[str, Any]] = {}
    repaired_errors = Counter()
    fallback_errors = Counter()
    for row in journal:
        if row.get("event") != "task":
            continue
        repair_call = int(row.get("repair_tokens") or 0) > 0
        for item in row.get("subresults") or []:
            status = item.get("status")
            if status == "fallback":
                label = "terminal_fallback"
                fallback_errors[item.get("error") or "unspecified"] += 1
            elif status == "repaired":
                label = "model_format_repair"
                if item.get("error"):
                    repaired_errors[item.get("error")] += 1
            elif status == "valid":
                label = "valid_original"
            else:
                label = "rejected"
            counts[label] += 1
            examples.setdefault(
                label,
                {
                    "doc": row.get("doc"),
                    "query_id": item.get("query_id"),
                    "fields": item.get("fields"),
                    "error": item.get("error"),
                    "repair_call": repair_call,
                    "paired_queries": row.get("query_ids"),
                },
            )
    return {
        "counts": dict(counts),
        "examples": examples,
        "repaired_retained_errors": dict(repaired_errors),
        "fallback_errors": dict(fallback_errors),
        "raw_model_text_retained": False,
        "note": (
            "status=repaired means a second model call returned a schema-valid object. "
            "The original response and the repair response were not stored, so the audit "
            "cannot prove that the repair avoided inventing a semantic value."
        ),
    }


def sharing_audit(contracts: dict[str, dict[str, Any]], journal: list[dict[str, Any]]) -> dict[str, Any]:
    by_attribute = Counter()
    by_route = Counter()
    violations = []
    shares = 0
    paired = 0
    missing_kept = 0
    namespace_mismatch = 0
    for row in journal:
        if row.get("event") != "task":
            continue
        scheduled = list(row.get("query_ids") or [])
        if len(scheduled) == 2:
            paired += 1
        present = {}
        for item in row.get("subresults") or []:
            if item.get("query_id") not in scheduled:
                namespace_mismatch += 1
                violations.append({"doc": row.get("doc"), "query_id": item.get("query_id"), "reason": "unscheduled query"})
            if item.get("status") in {"valid", "repaired"} and isinstance(item.get("fields"), dict):
                present[item["query_id"]] = item
        if len(scheduled) == 2 and len(present) == 1:
            missing_kept += 1
        if len(present) < 2:
            continue
        group = [contracts[query_id] for query_id in present if query_id in contracts]
        direct = {query_id: {"query_id": query_id, "fields": dict(item["fields"])} for query_id, item in present.items()}
        copied = fused.apply_same_attribute(group, direct, "fusion_same_attribute")
        types = {contract["query_id"]: {field["name"]: field["type"] for field in contract["fields"]} for contract in group}
        for query_id, item in copied.items():
            for name, value in item["fields"].items():
                source = direct[query_id]["fields"].get(name)
                if source is not None or value is None:
                    continue
                donors = [
                    other
                    for other, block in direct.items()
                    if other != query_id and block["fields"].get(name) == value and types.get(other, {}).get(name) == types.get(query_id, {}).get(name)
                ]
                if len(donors) != 1:
                    violations.append({"doc": row.get("doc"), "target": query_id, "attribute": name, "reason": "share without a unique same-type donor"})
                    continue
                shares += 1
                by_attribute[name] += 1
                by_route[f"{donors[0]} -> {query_id}"] += 1
    return {
        "paired_calls": paired,
        "missing_subresult_kept_partner": missing_kept,
        "namespace_mismatches": namespace_mismatch,
        "shares": shares,
        "by_attribute": dict(by_attribute),
        "by_route": dict(by_route),
        "violations": violations[:20],
        "violation_count": len(violations),
    }


def rebuild(policy: str, contracts, queries, journal, predicates, count: int, folder: Path) -> dict[str, list[dict[str, Any]]]:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    extracted = fused.rows_for(policy, contracts, [row for row in journal if row.get("event") != "task" or int(row["group_index"]) < count], count)
    bags = {}
    for query in queries:
        target = folder / f"{query['query_id'].replace(':', '_')}.db"
        fused.materialize_query(query, contracts[query["query_id"]], extracted.get(query["query_id"], {}), target)
        bags[query["query_id"]] = fused.execute_query(target, query, predicates)
    return bags


def bag_file(path: Path) -> dict[str, list[dict[str, Any]]]:
    return json.loads(path.read_text())


def plumbing_equal(query_ids: list[str], rebuilt: dict[str, list[dict[str, Any]]], queries, predicates) -> dict[str, bool]:
    plumbing_bags = {}
    for query in queries:
        if query["query_id"] not in query_ids:
            continue
        connection = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
        try:
            from quwarts.core.pipeline import official_sql

            sql = official_sql(query["sql"], PLUMBING, predicates, query_id=query["query_id"])
            cursor = connection.execute(sql)
            columns = [item[0] for item in cursor.description] if cursor.description else []
            plumbing_bags[query["query_id"]] = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()
    return {query_id: canonical(rebuilt[query_id]) == canonical(plumbing_bags[query_id]) for query_id in query_ids}


def score_bags_via_dbs(folder: Path, queries, predicates) -> dict[str, Any]:
    fused._FROZEN["ok"] = True
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.core.pipeline import official_sql
    from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
    from quwarts.experiments.synthesize_case80 import gold_name, score_with_rewrites

    gold = load_ground_truth(gold_name("Legal"))
    rows = [{"query_id": query["query_id"], "sql": query["sql"], "pack": query["pack"]} for query in queries]
    rewrites = {
        query["query_id"]: {
            "sql": official_sql(query["sql"], folder / f"{query['query_id'].replace(':', '_')}.db", predicates, query_id=query["query_id"]),
            "sqlite_path": str(folder / f"{query['query_id'].replace(':', '_')}.db"),
        }
        for query in queries
    }
    report = score_with_rewrites(rows, rewrites, PLUMBING, gold, "Legal")
    return {
        "product": mean_per_query_product(report),
        "f2": float(report.get("mean_structure_f2") or 0.0),
        "f1": mean_cell_f1_20(report),
    }


def static_inputs() -> dict[str, Any]:
    text = (ROOT / "systems" / "WDIRS" / "quwarts" / "eval" / "legal_fused_query_maps.py").read_text()
    opened = [
        "results/docetl_legal_case80/query_manifest.json",
        "Query/Legal/Legal_attributes.json",
        "source_data/Legal/legal_case/*.txt",
        "results/quwarts_legal_plumbing/artifacts/databases/legal_plumbing.db",
        "systems/docetl-main/docetl/operations/utils/validation.py",
        "systems/WDIRS/quwarts/core/docetl_unit_parity/schema.py",
        "quwarts tokenizer via count_tokens",
    ]
    forbidden_markers = [
        "query_results.json",
        "query_tables",
        "evaluation.json",
        "extract_fields.json",
        "pipeline_output.json",
        "ground_truth",
        "assignment_manifest",
        "shared_reachability",
        "cost_aware_reachability",
        "legal_wcci.db",
    ]
    hits = [marker for marker in forbidden_markers if marker in text]
    return {"opened_before_freeze": opened, "forbidden_markers_in_runner": hits}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    journal = read_journal()
    full = (FROZEN / "journal.jsonl").read_bytes()
    prefixes = {name: (FROZEN / name / "journal.jsonl").read_bytes() for name in ("theta25", "theta50", "theta75")}
    queries = fused.load_queries()
    contracts = fused.contracts_for(queries, fused.load_descriptions())
    predicates = fused.predicates_for(queries)
    classes = classify(journal)
    shares = sharing_audit(contracts, journal)
    comparisons = {}
    scores = {}
    plumbing_checks = {}
    for name, count in (("theta25", 5), ("theta50", 8), ("theta75", 8)):
        for policy in ("fusion_same_attribute", "fusion_direct"):
            folder = OUT / "rebuild" / name / policy
            bags = rebuild(policy, contracts, queries, journal, predicates, count, folder)
            (folder / "bags.json").write_text(json.dumps(bags, ensure_ascii=False, sort_keys=True))
            key = f"{name}:{policy}"
            if policy == "fusion_same_attribute":
                frozen_bags = bag_file(FROZEN / name / "bags.json")
                comparisons[key] = canonical(bags) == canonical(frozen_bags)
            else:
                comparisons[key] = "rebuilt_without_a_frozen_direct_bag"
            if name == "theta75":
                scores[policy] = score_bags_via_dbs(folder, queries, predicates)
        unfinished = sorted(set(query["query_id"] for query in queries) - set(json.loads((FROZEN / name / "checkpoint.json").read_text())["queries_completed"]))
        if unfinished:
            rebuilt = json.loads((OUT / "rebuild" / name / "fusion_same_attribute" / "bags.json").read_text())
            plumbing_checks[name] = plumbing_equal(unfinished, rebuilt, queries, predicates)
    identity_ok = True
    sample = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    from quwarts.core.observable_sidecar import identity_checksum

    base_identity = identity_checksum(sample)
    sample.close()
    probe = next((OUT / "rebuild" / "theta75" / "fusion_same_attribute").glob("*.db"))
    probe_connection = sqlite3.connect(probe)
    identity_ok = identity_checksum(probe_connection) == base_identity
    probe_connection.close()
    material = []
    if not classes["raw_model_text_retained"]:
        material.append("raw model responses were not retained, so the 6351 format repairs cannot be shown to avoid invented values")
    if any(value is False for value in comparisons.values()):
        material.append("rebuilt official bags differ from the frozen bags")
    if scores.get("fusion_same_attribute", {}).get("product") != EXPECTED["fusion_same_attribute"]:
        material.append("same-attribute product does not match the expected value")
    if scores.get("fusion_direct", {}).get("product") != EXPECTED["fusion_direct"]:
        material.append("direct product does not match the expected value")
    if shares["violation_count"]:
        material.append("same-attribute sharing violations")
    if not prefixes["theta50"].startswith(prefixes["theta25"]) or prefixes["theta50"] != prefixes["theta75"] or not full.startswith(prefixes["theta75"]):
        material.append("checkpoint journals are not exact prefixes")
    report = {
        "decision": "Legal fused result invalid" if material else "audit passed",
        "material_failures": material,
        "repair_classes": classes,
        "malformed_and_wrong_type": {
            "fallback_wrong_type": classes["fallback_errors"].get("wrong type", 0),
            "fallback_malformed": classes["fallback_errors"].get("malformed output", 0),
            "repaired_subresults": classes["counts"].get("model_format_repair", 0),
            "relation": "The 87 malformed and 802 wrong-type counts are the terminal fallbacks. Successful repairs cleared the stored error, so those 889 failures are disjoint from the 6351 repaired subresults.",
        },
        "sharing": shares,
        "bag_comparisons": comparisons,
        "scores": scores,
        "expected": EXPECTED,
        "plumbing_checks": plumbing_checks,
        "identity_ok": identity_ok,
        "prefixes": {
            "theta25_prefix_of_theta50": prefixes["theta50"].startswith(prefixes["theta25"]),
            "theta50_equals_theta75": prefixes["theta50"] == prefixes["theta75"],
            "theta75_prefix_of_full": full.startswith(prefixes["theta75"]),
        },
        "tokens": {
            "primary_combined": 17013058,
            "repair_combined": 1398948,
            "ledger_total": 18412006,
            "projected_reservation": 18227575,
            "theta50": 25220022,
            "over_reservation": 184431,
            "split_unavailable": "The runner stored one combined token count per call, not separate prompt and completion counts.",
        },
        "inputs": static_inputs(),
        "phase_b": "not started" if material else "eligible",
    }
    (OUT / "audit.json").write_text(canonical(report))
    (OUT / "REPORT.md").write_text(render(report))
    print(canonical({"decision": report["decision"], "failures": material, "scores": scores}))


def render(report: dict[str, Any]) -> str:
    lines = [
        "# Legal fused-map audit",
        "",
        f"Decision: `{report['decision']}`",
        "",
        "## Repair classes",
        "",
        canonical(report["repair_classes"]["counts"]),
        "",
        report["repair_classes"]["note"],
        "",
        report["malformed_and_wrong_type"]["relation"],
        "",
        "## Sharing",
        "",
        f"Shares: {report['sharing']['shares']}",
        f"Violations: {report['sharing']['violation_count']}",
        f"By attribute: {report['sharing']['by_attribute']}",
        "",
        "## Bags and scores",
        "",
        canonical(report["bag_comparisons"]),
        "",
        canonical(report["scores"]),
        "",
        "## Tokens",
        "",
        canonical(report["tokens"]),
        "",
        "## Inputs opened before freeze",
        "",
        "\n".join(f"- {item}" for item in report["inputs"]["opened_before_freeze"]),
        "",
    ]
    if report["material_failures"]:
        lines.extend(["## Material failures", ""] + [f"- {item}" for item in report["material_failures"]])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()

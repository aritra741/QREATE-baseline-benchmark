"""Score already-frozen amortized sidecars. No model calls."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "systems" / "WDIRS"), str(ROOT), str(ROOT / "systems" / "docetl-main")]

from diagnostics.run_config_grid import load_ground_truth
from quwarts.core.full_window_additive.overlay import official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import _hash, _score
from quwarts.experiments.synthesize_case80 import gold_name, queries_for

AMORTIZED = ROOT / "results" / "quwarts_finan_amortized_select"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
OUT = ROOT / "results" / "quwarts_finan_amortized_program_only_repro"


def main() -> int:
    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]

    program_fills = json.loads((AMORTIZED / "program_fills.json").read_text())
    residual_fills = json.loads((AMORTIZED / "residual_fills.json").read_text())
    combined_fills = json.loads((AMORTIZED / "combined_fills.json").read_text())
    program_bags = json.loads((AMORTIZED / "program_only_bags.json").read_text())
    residual_bags = json.loads((AMORTIZED / "residual_only_bags.json").read_text())
    combined_bags = json.loads((AMORTIZED / "combined_bags.json").read_text())
    frozen = json.loads((AMORTIZED / "frozen.json").read_text())
    assert frozen["hashes"]["program_bags"] == _hash(program_bags)
    assert frozen["hashes"]["residual_bags"] == _hash(residual_bags)
    assert frozen["hashes"]["combined_bags"] == _hash(combined_bags)

    scores = {}
    for name, dest in (
        ("program_only", AMORTIZED / "program_only.db"),
        ("residual_only", AMORTIZED / "residual_only.db"),
        ("combined", AMORTIZED / "combined.db"),
    ):
        rewrites = {qid: {"sql": official_sql(statements[qid], dest, predicates, query_id=qid), "sqlite_path": str(dest)} for qid in query_ids}
        scores[name] = _score(dest, score_rows, rewrites, gold)

    prompt_hash = file_sha256(ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "prompt.py")
    spec_hash = file_sha256(ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "amortized_select" / "dsl.py")
    compiler_prompt_hash = file_sha256(AMORTIZED / "compiler_prompts.jsonl")
    critic_prompt_hash = file_sha256(AMORTIZED / "critic_prompts.jsonl")

    rows = []
    for i, qid in enumerate(query_ids):
        p = scores["program_only"]["per_query"][i]
        r = scores["residual_only"]["per_query"][i]
        c = scores["combined"]["per_query"][i]
        rows.append(
            {
                "query_id": qid,
                "program_product": p["product"],
                "residual_product": r["product"],
                "combined_product": c["product"],
                "combined_minus_program": c["product"] - p["product"],
                "combined_minus_residual": c["product"] - r["product"],
                "program_rows": len(program_bags.get(qid) or []),
                "residual_rows": len(residual_bags.get(qid) or []),
                "combined_rows": len(combined_bags.get(qid) or []),
                "program_equals_combined": _hash(program_bags.get(qid) or []) == _hash(combined_bags.get(qid) or []),
                "residual_equals_combined": _hash(residual_bags.get(qid) or []) == _hash(combined_bags.get(qid) or []),
            }
        )

    payload = {
        "scores": {
            name: {
                "mean_structure_f2": scores[name]["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scores[name]["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scores[name]["mean_per_query_product"],
                "per_query": scores[name]["per_query"],
            }
            for name in scores
        },
        "per_query_compare": rows,
        "existing_prompt_hashes": {
            "prompt_py": prompt_hash,
            "dsl_py": spec_hash,
            "compiler_prompts_jsonl": compiler_prompt_hash,
            "critic_prompts_jsonl": critic_prompt_hash,
            "official_schema": frozen["hashes"]["official_schema"],
            "policy": frozen["hashes"]["policy"],
            "validated_specs": frozen["hashes"]["validated_specs"],
            "ledger": frozen["hashes"]["ledger"],
        },
        "n_program_cells": sum(len(v) for v in program_fills.values()),
        "n_residual_cells": sum(len(v) for v in residual_fills.values()),
        "n_combined_cells": sum(len(v) for v in combined_fills.values()),
        "intersection_cells": sum(1 for doc, values in residual_fills.items() for attr in values if attr in (program_fills.get(doc) or {})),
    }
    (OUT / "existing_sidecar_scores.json").write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({"program": payload["scores"]["program_only"]["mean_per_query_product"], "residual": payload["scores"]["residual_only"]["mean_per_query_product"], "combined": payload["scores"]["combined"]["mean_per_query_product"], "prompt_py": prompt_hash}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

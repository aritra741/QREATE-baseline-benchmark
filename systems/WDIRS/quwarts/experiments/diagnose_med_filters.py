"""Run FilterFailureDiagnosis on an existing Med compile. No extra LLM spend."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.extract import EvidenceStore
from quwarts.core.repair.diagnose import diagnose_empty_queries, diagnose_filter_failures
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import queries_for


def main() -> int:
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "quwarts_med_repair80_diag"
    manifest = json.loads((run / "artifacts" / "runs" / "manifest.json").read_text())
    empty = (
        ((manifest.get("quality") or {}).get("repair") or {}).get("before") or {}
    ).get("empty_query_ids") or []
    queries = queries_for("Med")
    train, _test = split_80_20(queries, 42)
    statements = {row["query_id"]: row["sql"] for row in train}
    logical, workload = analyze_workload(statements)
    rewrites = manifest.get("rewrites") or {}
    db = next(iter((run / "artifacts" / "databases").glob("*.db")), None)
    sqlite = str(db or run / "synthesized.sqlite")
    plans = {
        stmt_id: {"sql": rewrites.get(stmt_id) or rewrites.get(stmt_id.split(":")[0]), "sqlite_path": sqlite}
        for stmt_id in empty
    }
    # fallback: template id vs statement id
    for stmt_id in empty:
        if plans[stmt_id]["sql"]:
            continue
        plans[stmt_id]["sql"] = statements.get(stmt_id)
    store = EvidenceStore(run / "artifacts" / "evidence")
    diagnoses = diagnose_empty_queries(empty, statements, plans, store=store, workload=workload)
    reports = diagnose_filter_failures(diagnoses, store, workload)
    causes = {}
    for item in diagnoses:
        causes[item.cause] = causes.get(item.cause, 0) + 1
    payload = {
        "n_empty": len(empty),
        "empty_causes": causes,
        "n_filter_columns": len(reports),
        "infeasible": [
            {"attribute": row.attribute, "n_queries": len(row.query_ids), "samples": row.samples}
            for row in reports if row.shape == "infeasible"
        ],
        "columns": [row.as_dict() for row in reports[:12]],
        "worst_three": [row.as_dict() for row in reports[:3]],
    }
    out = run / "filter_failure_diagnosis.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({
        "empty_causes": causes,
        "n_filter_columns": len(reports),
        "n_infeasible": len(payload["infeasible"]),
        "worst_three": [
            {
                "attribute": row.attribute,
                "queries": len(row.query_ids),
                "shape": row.shape,
                "expected_type": row.expected_type,
                "predicate": row.predicate,
                "literals": row.literals,
                "n_distinct": row.n_distinct,
                "n_digits": row.n_digits,
                "n_units": row.n_units,
                "n_ranges": row.n_ranges,
                "n_boolean": row.n_boolean,
                "n_absence": row.n_absence,
                "n_literal_hits": row.n_literal_hits,
                "actions": list(row.compatible_actions),
                "samples": row.samples,
            }
            for row in reports[:3]
        ],
    }, indent=2), flush=True)
    _ = logical
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

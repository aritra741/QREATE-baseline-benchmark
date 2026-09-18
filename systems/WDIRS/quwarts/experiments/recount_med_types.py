"""Rematerialize Med after SQL string-literal types. No LLM spend."""

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
from quwarts.core.ledger import TokenLedger
from quwarts.core.models import FrozenPortfolio
from quwarts.core.pipeline import rematerialize_databases, serve_plans
from quwarts.core.repair.detectors import detect_coercion, detect_empty_queries
from quwarts.core.repair.diagnose import diagnose_empty_queries, diagnose_filter_failures
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import documents_for, queries_for


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "quwarts_med_repair80_diag"
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "results" / "quwarts_med_typefix80"
    dest.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((src / "artifacts" / "runs" / "manifest.json").read_text())
    fields = {name: manifest[name] for name in FrozenPortfolio.model_fields if name in manifest}
    portfolio = FrozenPortfolio.model_validate(fields)
    queries = queries_for("Med")
    train, _test = split_80_20(queries, 42)
    statements = {row["query_id"]: row["sql"] for row in train}
    logical, workload = analyze_workload(statements, portfolio.logical_schema)
    before_empty = detect_empty_queries(portfolio, statements)
    store = EvidenceStore(src / "artifacts" / "evidence")
    before_coercion = detect_coercion(store)
    ledger = TokenLedger(theta=max(portfolio.tokens_spent, 1), seed=portfolio.seed)
    ledger.spent = min(portfolio.tokens_spent, ledger.theta)
    documents = documents_for("Med")
    db_dir = dest / "artifacts" / "databases"
    db_dir.mkdir(parents=True, exist_ok=True)
    spent_before = ledger.spent
    databases = rematerialize_databases(
        store=store,
        workload=workload,
        documents=documents,
        configs=portfolio.configurations,
        db_dir=db_dir,
        ledger=ledger,
        identity_report={},
        overwrite=True,
    )
    portfolio.databases[:] = databases
    after_empty = detect_empty_queries(portfolio, statements)
    after_coercion = detect_coercion(store)
    plans = serve_plans(portfolio, statements)
    diagnoses = diagnose_empty_queries(after_empty, statements, plans, store=store, workload=workload)
    causes: dict[str, int] = {}
    for item in diagnoses:
        causes[item.cause] = causes.get(item.cause, 0) + 1
    reports = diagnose_filter_failures(diagnoses, store, workload)
    types = {
        name: req.dtype
        for name, req in workload.requirements.items()
        if name.split(".")[-1] in {
            "disease_type", "prescription_status", "research_fields",
            "treatments", "institution_country",
        }
    }
    payload = {
        "before_empty": len(before_empty),
        "after_empty": len(after_empty),
        "moved": sorted(set(before_empty) - set(after_empty)),
        "still_empty": sorted(after_empty),
        "new_empty": sorted(set(after_empty) - set(before_empty)),
        "empty_causes": causes,
        "before_coercion": before_coercion,
        "after_coercion": after_coercion,
        "tokens_spent": ledger.spent - spent_before,
        "types": types,
        "like_tokens": {
            key: workload.like_tokens.get(key)
            for key in ("drug.prescription_status", "disease.disease_type", "institution.research_fields")
        },
        "filter_columns": [row.as_dict() for row in reports[:8]],
    }
    (dest / "typefix_recount.json").write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({
        "before_empty": payload["before_empty"],
        "after_empty": payload["after_empty"],
        "n_moved": len(payload["moved"]),
        "moved": payload["moved"],
        "empty_causes": causes,
        "before_coercion": before_coercion,
        "after_coercion": after_coercion,
        "tokens_spent": payload["tokens_spent"],
        "types": types,
        "like_tokens": payload["like_tokens"],
    }, indent=2), flush=True)
    _ = logical
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

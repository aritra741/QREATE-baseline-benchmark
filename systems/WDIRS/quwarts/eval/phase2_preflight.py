"""Free checks that shape Phase 2. Gold stays in eval."""

from __future__ import annotations

import json
import sqlite3
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

from quwarts.core.contracts import case_literals_from_sql, compile_contracts, token_hits
from quwarts.core.domain import like_tokens_from_workload
from quwarts.core.extract import EvidenceStore
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import gold_name, queries_for

SCORE_DB = next((ROOT / "results" / "quwarts_med_repair_round" / "artifacts" / "databases").glob("*.db"))
VOTE_DB = next((ROOT / "results" / "quwarts_med_cells" / "artifacts" / "databases").glob("*.db"))
EVIDENCE = ROOT / "results" / "quwarts_med_repair80_diag" / "artifacts" / "evidence"
MANIFEST = ROOT / "results" / "quwarts_med_repair80_diag" / "artifacts" / "runs" / "manifest.json"
OUT = ROOT / "results" / "quwarts_med_cells" / "phase2_preflight.json"
LIKE_ATTRS = (
    "institution.research_fields",
    "drug.prescription_status",
    "disease.disease_type",
)


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _fold(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").casefold().split())


def distinct_col(db: Path, table: str, column: str) -> tuple[list[str], int, int]:
    con = sqlite3.connect(db)
    try:
        cols = {row[1] for row in con.execute(f"PRAGMA table_info({_q(table)})")}
        if column not in cols:
            return [], 0, 0
        n = con.execute(f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0]
        filled = con.execute(
            f"SELECT COUNT(*) FROM {_q(table)} WHERE {_q(column)} IS NOT NULL "
            f"AND CAST({_q(column)} AS TEXT) <> ''"
        ).fetchone()[0]
        values = [
            str(row[0])
            for row in con.execute(
                f"SELECT DISTINCT {_q(column)} FROM {_q(table)} "
                f"WHERE {_q(column)} IS NOT NULL AND CAST({_q(column)} AS TEXT) <> ''"
            )
        ]
        return values, filled, n
    finally:
        con.close()


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth

    queries = queries_for("Med")
    train, _test = split_80_20(queries, 42)
    train_sql = {row["query_id"]: row["sql"] for row in train}
    _, workload = analyze_workload(train_sql)
    store = EvidenceStore(EVIDENCE)
    gold = load_ground_truth(gold_name("Med"))
    like = like_tokens_from_workload(workload)
    contracts = compile_contracts(workload)

    case_from_sql: dict[str, set[str]] = defaultdict(set)
    for sql in train_sql.values():
        for name, values in case_literals_from_sql(sql).items():
            case_from_sql[name].update(values)

    case_report = {}
    all_attrs = sorted({
        name for name in set(case_from_sql) | set(workload.requirements)
        if "." in name
    })
    gold_tables = set(gold)
    for name in all_attrs:
        bare = name.split(".")[-1]
        table = name.split(".", 1)[0]
        if table not in gold_tables:
            continue
        lits = sorted(case_from_sql.get(name) or case_from_sql.get(bare) or [])
        if not lits and name not in {a for a in LIKE_ATTRS}:
            continue
        surfaces = sorted({
            str(rec.surface_value).strip()
            for rec in store.for_attribute(name)
            if rec.surface_value not in (None, "")
            and str(rec.doc_id).startswith(f"{table}/")
        })
        phys, filled, n = distinct_col(SCORE_DB, table, bare)
        hits = 0
        miss = []
        for surface in phys or surfaces:
            if token_hits(surface, lits):
                hits += 1
            elif lits:
                miss.append(surface)
        case_report[name] = {
            "case_literals": lits,
            "n_literals": len(lits),
            "n_surfaces": len(phys or surfaces),
            "n_surfaces_hitting_a_literal": hits,
            "n_surfaces_outside_every_when": len(miss),
            "outside_sample": miss[:8],
            "overlap": (hits / len(phys or surfaces)) if (phys or surfaces) and lits else 0.0,
        }

    gold_section = {}
    for name in LIKE_ATTRS:
        table, bare = name.split(".", 1)
        gold_vals = sorted({
            str(row.get(bare) or "").strip()
            for row in gold.get(table, [])
            if row.get(bare) not in (None, "")
        })
        surface, filled_s, n_s = distinct_col(SCORE_DB, table, bare)
        like_vals, filled_l, n_l = distinct_col(SCORE_DB, table, f"{bare}__like")
        tokens = like.get(name) or like.get(bare) or []
        gold_section[name] = {
            "like_tokens_from_sql": tokens,
            "n_gold_distinct": len(gold_vals),
            "gold_values": gold_vals,
            "n_surface_distinct": len(surface),
            "n_like_distinct": len(like_vals),
            "like_values": like_vals,
            "like_filled": filled_l,
            "like_null": n_l - filled_l,
            "n_rows": n_l,
        }

    def table_counts(db: Path) -> dict[str, int]:
        con = sqlite3.connect(db)
        try:
            return {
                name: con.execute(f"SELECT COUNT(*) FROM {_q(name)}").fetchone()[0]
                for (name,) in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
                )
            }
        finally:
            con.close()

    gold_counts = {name: len(rows) for name, rows in gold.items()}
    pred_counts = table_counts(SCORE_DB)
    vote_counts = table_counts(VOTE_DB)
    base = {
        table: {
            "gold": gold_counts.get(table),
            "quwarts_pre_vote": pred_counts.get(table),
            "quwarts_rematerialized": vote_counts.get(table),
            "recall_pre_vote": (pred_counts.get(table) or 0) / gold_counts[table]
            if gold_counts.get(table) else None,
        }
        for table in gold_counts
    }

    vote_restored = json.loads(
        (ROOT / "results" / "quwarts_med_cells" / "after_like_restored.json").read_text()
    )
    vote_note = {
        "retired_from_0.126": True,
        "pre_vote_cell_f1_20": 0.12567460317460316,
        "rematerialized_cell_f1_20": vote_restored.get("mean_cell_f1_at_0.20"),
        "rematerialized_structure_f2": vote_restored.get("mean_structure_f2"),
        "rematerialized_product": vote_restored.get("mean_per_query_product"),
        "verdict": "vote did not move cell F1; drop the 5.52M run from the 0.126 record",
    }

    payload = {
        "case_vs_surfaces": case_report,
        "gold_three_columns": gold_section,
        "base_relation_counts": base,
        "vote": vote_note,
        "contract_kinds": {
            name: {"kind": row["kind"], "sources": row["sources"], "n_vocab": len(row["vocab"])}
            for name, row in sorted(contracts.items())
            if "." in name
        },
    }
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({
        "wrote": str(OUT),
        "case": {
            k: {kk: v[kk] for kk in (
                "n_literals", "n_surfaces", "n_surfaces_hitting_a_literal",
                "n_surfaces_outside_every_when", "overlap", "case_literals",
            )}
            for k, v in case_report.items() if v["n_literals"]
        },
        "gold": {
            k: {kk: v[kk] for kk in (
                "like_tokens_from_sql", "n_gold_distinct", "gold_values",
                "n_surface_distinct", "n_like_distinct", "like_values",
                "like_filled", "like_null",
            )}
            for k, v in gold_section.items()
        },
        "base": base,
        "vote": vote_note,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

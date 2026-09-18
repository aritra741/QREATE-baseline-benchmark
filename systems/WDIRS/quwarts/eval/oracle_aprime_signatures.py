"""Step 4. Oracle diagnostic: gold signatures on A' rows. No new rows."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.signature import (
    audit_workload,
    enumerate_predicates,
    gold_signature_sql,
    materialize_signatures,
    rewrite_sql,
)
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

APRIME = next((ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "databases").glob("*.db"))
APRIME_REPORT = ROOT / "results" / "quwarts_med_aprime" / "aprime_report.json"
OUT = ROOT / "results" / "quwarts_med_signatures"
KEY_COLS = {"doc_id", "id"}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def dump_cols(path: Path, skip: set[str]) -> str:
    con = sqlite3.connect(path)
    digest = hashlib.sha256()
    try:
        for (table,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' ORDER BY 1"
        ):
            cols = [info[1] for info in con.execute(f"PRAGMA table_info({_q(table)})")]
            keep = [col for col in cols if col not in skip and not str(col).startswith("sig_")]
            digest.update(table.encode())
            digest.update("|".join(keep).encode())
            if not keep:
                continue
            sql = f"SELECT {', '.join(_q(c) for c in keep)} FROM {_q(table)} ORDER BY 1"
            for row in con.execute(sql):
                digest.update(repr(row).encode())
    finally:
        con.close()
    return digest.hexdigest()


def table_counts(path: Path) -> dict[str, int]:
    con = sqlite3.connect(path)
    try:
        return {
            name: con.execute(f"SELECT COUNT(*) FROM {_q(name)}").fetchone()[0]
            for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
            )
        }
    finally:
        con.close()


def gold_index() -> dict[str, dict[str, dict]]:
    from diagnostics.run_config_grid import load_ground_truth

    tables = load_ground_truth(gold_name("Med"))
    index: dict[str, dict[str, dict]] = {}
    dups = []
    for table, rows in tables.items():
        by_id: dict[str, dict] = {}
        for row in rows:
            key = row.get("id")
            if key in (None, ""):
                continue
            stem = str(key).strip()
            if stem in by_id:
                dups.append((table, stem))
                continue
            by_id[stem] = row
        index[table] = by_id
    return index


def fill_aprime_signatures(dest: Path, predicates) -> dict:
    from diagnostics.run_config_grid import load_ground_truth
    from spp.config_grid import _build_in_memory_db

    gold = _build_in_memory_db(load_ground_truth(gold_name("Med")))
    materialize_signatures(gold, predicates)
    by_id: dict[str, dict[str, dict]] = {}
    dups = 0
    for table in {item.table for item in predicates}:
        cols = [info[1] for info in gold.execute(f"PRAGMA table_info({_q(table)})")]
        if "id" not in cols:
            continue
        sigs = [item.sig_name for item in predicates if item.table == table]
        select = ", ".join(["id"] + [_q(name) for name in sigs])
        mapping: dict[str, dict] = {}
        for row in gold.execute(f"SELECT {select} FROM {_q(table)}"):
            stem = str(row[0]).strip() if row[0] is not None else ""
            if not stem:
                continue
            if stem in mapping:
                dups += 1
                continue
            mapping[stem] = dict(zip(sigs, row[1:]))
        by_id[table] = mapping
    gold.close()

    con = sqlite3.connect(dest)
    aligned = {table: 0 for table in by_id}
    missing = {table: 0 for table in by_id}
    try:
        existing = {
            table: {info[1] for info in con.execute(f"PRAGMA table_info({_q(table)})")}
            for (table,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
            )
        }
        for pred in predicates:
            if pred.table not in existing:
                continue
            if pred.sig_name not in existing[pred.table]:
                con.execute(f"ALTER TABLE {_q(pred.table)} ADD COLUMN {_q(pred.sig_name)} INTEGER")
                existing[pred.table].add(pred.sig_name)
        for table, mapping in by_id.items():
            if table not in existing or "doc_id" not in existing[table]:
                continue
            sigs = [item.sig_name for item in predicates if item.table == table]
            for doc_id, in con.execute(f"SELECT doc_id FROM {_q(table)}"):
                stem = Path(str(doc_id)).stem
                values = mapping.get(stem)
                if values is None:
                    missing[table] += 1
                    continue
                aligned[table] += 1
                assignments = ", ".join(f"{_q(name)} = ?" for name in sigs)
                con.execute(
                    f"UPDATE {_q(table)} SET {assignments} WHERE doc_id = ?",
                    [values.get(name) for name in sigs] + [doc_id],
                )
        con.commit()
    finally:
        con.close()
    return {"aligned": aligned, "missing_gold": missing, "gold_id_dups_skipped": dups}


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    report = audit_workload(queries)
    predicates = enumerate_predicates(report.occurrences, report.signature_eligible)
    dest = OUT / "artifacts" / "aprime_gold_sig.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(APRIME, dest)
    before_counts = table_counts(APRIME)
    before_sha = dump_cols(APRIME, set())
    copy_sha = dump_cols(dest, set())
    fill = fill_aprime_signatures(dest, predicates)
    after_counts = table_counts(dest)
    after_nonsig = dump_cols(dest, {item.sig_name for item in predicates})
    held = {
        "row_counts_unchanged": before_counts == {k: after_counts.get(k) for k in before_counts},
        "copy_byte_identical_before_fill": before_sha == copy_sha,
        "nonsig_and_keys_byte_identical": before_sha == after_nonsig,
        "before_counts": before_counts,
        "after_counts": after_counts,
    }
    gold = load_ground_truth(gold_name("Med"))
    rewrites = {row["query_id"]: rewrite_sql(row["sql"], predicates) for row in test}
    test_report = score_with_rewrites(test, rewrites, dest, gold, "Med")
    aprime = json.loads(APRIME_REPORT.read_text()) if APRIME_REPORT.is_file() else {}
    payload = {
        "step": 4,
        "label": "oracle_diagnostic",
        "sqlite_path": str(dest),
        "held_fixed": held,
        "alignment": fill,
        "mean_structure_f2": float(test_report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(test_report),
        "mean_per_query_product": mean_per_query_product(test_report),
        "aprime": {
            "mean_structure_f2": aprime.get("mean_structure_f2"),
            "mean_cell_f1_at_0.20": aprime.get("mean_cell_f1_at_0.20"),
            "mean_per_query_product": aprime.get("mean_per_query_product"),
        },
        "delta_vs_aprime": {
            "structure_f2": float(test_report.get("mean_structure_f2") or 0.0)
            - float(aprime.get("mean_structure_f2") or 0.0),
            "cell_f1_20": mean_cell_f1_20(test_report)
            - float(aprime.get("mean_cell_f1_at_0.20") or 0.0),
            "product": mean_per_query_product(test_report)
            - float(aprime.get("mean_per_query_product") or 0.0),
        },
        "test_empty_query_count": sum(
            1 for row in test_report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0
        ),
        "scope_limit_full_value_required": report.full_value_required,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "step4_oracle_aprime.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({k: payload[k] for k in payload if k != "held_fixed"} | {"held_fixed": held}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

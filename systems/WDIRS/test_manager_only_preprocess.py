#!/usr/bin/env python3
"""
Run WDIRS preprocessing for Player.manager table only.

This script builds a manager-only workload query (no joins), runs preprocessing,
and prints a compact quality snapshot for the resulting `manager` table.

Usage:
  cd systems/WDIRS
  ../../.venv/bin/python test_manager_only_preprocess.py
  ../../.venv/bin/python test_manager_only_preprocess.py --db "./wdirs-manager-only.db" --fresh
"""

import argparse
import csv
import json
from pathlib import Path
import sys

# Local imports from systems/WDIRS
WDIRS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WDIRS_ROOT.parent.parent
if str(WDIRS_ROOT) not in sys.path:
    sys.path.insert(0, str(WDIRS_ROOT))

from wdirs_runner import WDIRSRunner


def build_manager_only_query() -> str:
    """
    Build one explicit manager-only query from GT CSV headers.
    Excludes ID so identity extraction focuses on semantic fields.
    """
    csv_path = PROJECT_ROOT / "Data" / "Player" / "manager.csv"
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)

    cols = [c.strip().strip('"') for c in header if c.strip()]
    cols = [c for c in cols if c.lower() != "id"]
    if not cols:
        cols = ["name", "age", "nationality", "nba_team", "own_year"]

    return "SELECT " + ", ".join(cols) + " FROM manager;"


def print_manager_snapshot(runner: WDIRSRunner) -> None:
    """
    Print manager table quality indicators:
    - row count + distinct name count
    - sample names
    - provenance source prefixes for name cells
    """
    if not runner.data_layer.table_exists("manager"):
        print("manager table does not exist after preprocessing.")
        return

    rows = runner.data_layer.get_all_records("manager")
    names = [str(r.get("name") or "").strip() for r in rows if str(r.get("name") or "").strip()]
    distinct_names = sorted(set(names))

    print("\n=== manager snapshot ===")
    print(f"rows: {len(rows)}")
    print(f"distinct names: {len(distinct_names)}")
    print("sample names:", distinct_names[:12])

    # Source contamination check via cell_provenance on manager.name
    q = """
    SELECT
      CASE
        WHEN instr(doc_id, '/') > 0 THEN substr(doc_id, 1, instr(doc_id, '/') - 1)
        ELSE doc_id
      END AS source_prefix,
      COUNT(*) AS cnt
    FROM cell_provenance cp
    JOIN manager m ON m.row_id = cp.row_id
    WHERE cp.column_name = 'name'
    GROUP BY source_prefix
    ORDER BY cnt DESC
    """
    pref_rows = runner.data_layer.execute_sql(q)
    print("name provenance prefixes:", pref_rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Preprocess only Player.manager table")
    ap.add_argument(
        "--dataset",
        default="Player",
        help="Dataset name (default: Player)",
    )
    ap.add_argument(
        "--db",
        default=str(WDIRS_ROOT / "wdirs-manager-only.db"),
        help="Output sqlite DB path (default: systems/WDIRS/wdirs-manager-only.db)",
    )
    ap.add_argument(
        "--fresh",
        action="store_true",
        help="Delete existing DB file before run",
    )
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    if args.fresh and db_path.exists():
        db_path.unlink()
        print(f"Deleted existing DB: {db_path}")

    workload_query = build_manager_only_query()
    print("manager-only workload query:")
    print(workload_query)

    runner = WDIRSRunner(dataset=args.dataset, postgres_uri=f"sqlite:///{db_path}")
    result = runner.preprocess(workload_queries=[workload_query])

    print("\n=== preprocess result ===")
    print(json.dumps(
        {
            "success": result.success,
            "tables_processed": result.tables_processed,
            "total_chunks": result.total_chunks,
            "total_records": result.total_records,
            "preprocessing_time_sec": round(result.preprocessing_time, 2),
            "error": result.error,
            "db_path": str(db_path),
        },
        indent=2,
    ))

    if result.success:
        print_manager_snapshot(runner)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


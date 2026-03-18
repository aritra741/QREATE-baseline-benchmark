#!/usr/bin/env python3
"""
Run a single SQL query on the ReDD-extracted DB and compare against ground truth.

Usage:
  python run_one_query.py [--query-id Q1] [--query "SELECT ..."]
  python run_one_query.py   # uses default query on Q1's extracted DB

Finds the latest ReDD DB from:
  results/player_query_awareness_trend_redd/run_*/query_eval_dbs/{query_id}.db

Ground truth: Data/Player/player.db (canonical schema).
ReDD extracts to canonical schema (player, team, city, etc.) so no rewrite needed.
"""

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REDD_ROOT = Path(__file__).resolve().parent

GROUND_TRUTH_DB = PROJECT_ROOT / "Data" / "Player" / "player.db"
RESULTS_BASE = PROJECT_ROOT / "results" / "player_query_awareness_trend_redd"
RESULTS_BASE_ENV = os.getenv("REDD_RESULTS_BASE_DIR", "")

DEFAULT_QUERY_ID = "Q1"

DEFAULT_QUERY = """
SELECT t.team_name, t.location,
       COUNT(p.name) as player_count
FROM player p
JOIN team t ON p.team = t.team_name
WHERE p.draft_year > 2000
   OR p.position = 'Frontcourt'
   OR t.founded_year < 1980
GROUP BY t.team_name, t.location, t.founded_year;
"""

KEY_COLS = ["team_name", "location"]


def _find_latest_redd_db(query_id: str) -> Optional[Path]:
    """Latest query_eval_dbs/{query_id}.db by run dir, from project or env."""
    search_dirs: List[Path] = []
    if RESULTS_BASE.exists():
        search_dirs.append(RESULTS_BASE)
    if RESULTS_BASE_ENV and Path(RESULTS_BASE_ENV).exists():
        search_dirs.append(Path(RESULTS_BASE_ENV))

    for base in search_dirs:
        runs = sorted(
            (d for d in base.glob("run_*") if d.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for run_dir in runs:
            db = run_dir / "query_eval_dbs" / f"{query_id}.db"
            if db.exists():
                return db
    return None


def _run_query(conn: sqlite3.Connection, query: str) -> Tuple[List[dict], List[str], float]:
    """Execute query, return (rows as dicts, column names, elapsed seconds)."""
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(query)
    rows = cur.fetchall()
    elapsed = time.perf_counter() - t0
    col_names = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(col_names, r)) for r in rows], col_names, elapsed


def _run_query_or_error(
    conn: sqlite3.Connection, query: str
) -> Tuple[bool, List[dict], List[str], float, Optional[str]]:
    """Run query; on error return (False, [], [], 0, error_msg)."""
    try:
        rows, cols, elapsed = _run_query(conn, query)
        return True, rows, cols, elapsed, None
    except Exception as e:
        return False, [], [], 0.0, str(e)


def _row_key(row: dict, key_cols: list) -> tuple:
    return tuple(
        "" if c not in row or row[c] is None else str(row[c]).strip().lower()
        for c in key_cols
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run one query on ReDD-extracted DB and compare to ground truth"
    )
    ap.add_argument(
        "--query-id",
        type=str,
        default=DEFAULT_QUERY_ID,
        help=f"Trend query ID (Q1..Q10) whose extracted DB to use (default: {DEFAULT_QUERY_ID})",
    )
    ap.add_argument(
        "--query", "-q",
        type=str,
        default=DEFAULT_QUERY.strip(),
        help="SQL query to run on both gold and ReDD DBs",
    )
    args = ap.parse_args()
    query_id = args.query_id.strip()
    query_sql = args.query.strip()
    if not query_sql.endswith(";"):
        query_sql += ";"

    redd_db = _find_latest_redd_db(query_id)
    if redd_db is None:
        print(
            f"No ReDD DB found for query {query_id}. Run test_player_query_awareness_trend_redd.py first.\n"
            f"Expected: {RESULTS_BASE}/run_*/query_eval_dbs/{query_id}.db"
        )
        if RESULTS_BASE_ENV:
            print(f"  or: {RESULTS_BASE_ENV}/run_*/query_eval_dbs/{query_id}.db")
        return 1

    if not GROUND_TRUTH_DB.exists():
        print(f"Gold database not found: {GROUND_TRUTH_DB}")
        return 1

    conn_gold = sqlite3.connect(str(GROUND_TRUTH_DB))
    ok_gold, gold_rows, col_names, gold_time, err_gold = _run_query_or_error(conn_gold, query_sql)
    conn_gold.close()

    conn_redd = sqlite3.connect(str(redd_db))
    ok_redd, redd_rows, redd_cols, redd_time, err_redd = _run_query_or_error(conn_redd, query_sql)
    conn_redd.close()

    print("\n" + "=" * 70)
    print("Query:")
    print(query_sql)
    print("=" * 70)
    print(f"ReDD DB: {query_id}.db from {redd_db.parent.parent.name}")
    print("=" * 70)

    if not ok_gold:
        print(f"\nGold DB error: {err_gold}")
        return 1
    if not ok_redd:
        print(f"\nReDD DB error: {err_redd}")
        return 1

    key_cols = [c for c in KEY_COLS if c in col_names] or (col_names[:2] if col_names else [])

    print("\n--- Gold (player.db) ---")
    print("  ".join(f"{c:>18}" for c in col_names))
    print("-" * 70)
    for r in gold_rows:
        print("  ".join(f"{str(r.get(c, '')):>18}" for c in col_names))
    print("-" * 70)

    print("\n--- ReDD ---")
    print("  ".join(f"{c:>18}" for c in redd_cols))
    print("-" * 70)
    for r in redd_rows:
        print("  ".join(f"{str(r.get(c, '')):>18}" for c in redd_cols))
    print("-" * 70)

    gold_map = {_row_key(r, key_cols): r for r in gold_rows}
    redd_map = {_row_key(r, key_cols): r for r in redd_rows}
    gold_keys = set(gold_map)
    redd_keys = set(redd_map)

    matched = gold_keys & redd_keys
    extra = redd_keys - gold_keys
    missed = gold_keys - redd_keys

    print("\n--- Comparison ---")
    print(f"  Matched:  {len(matched)}")
    print(f"  Extra:    {len(extra)}   (in ReDD output, not in gold)")
    print(f"  Missed:   {len(missed)}   (in gold, not in ReDD output)")
    print("\n--- Time ---")
    print(f"  Gold:  {gold_time:.4f}s")
    print(f"  ReDD:  {redd_time:.4f}s")
    print(f"\n  ReDD DB: {redd_db}")

    if extra and key_cols:
        print(f"\n  Extra rows: {[tuple(k) for k in sorted(extra)[:5]]}{'...' if len(extra) > 5 else ''}")
    if missed and key_cols:
        print(f"  Missed rows: {[tuple(k) for k in sorted(missed)[:5]]}{'...' if len(missed) > 5 else ''}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

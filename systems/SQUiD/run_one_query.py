#!/usr/bin/env python3
"""
Run a single SQL query on the SQUiD-generated DB and compare against ground truth.

Usage:
  python run_one_query.py [--query "SELECT ..."]
  python run_one_query.py   # uses default query

Finds the latest SQUiD DB from:
  - results/player_query_awareness_trend_squid/run_*/squid_single_generated.db
  - or databases/single_input/player_single/text_direct_ollama/ensemble/Player_0.db

Ground truth: Data/Player/player.db (canonical schema).
SQUiD schema differs; the query is auto-rewritten for the generated schema.
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SQUID_ROOT = Path(__file__).resolve().parent

GROUND_TRUTH_DB = PROJECT_ROOT / "Data" / "Player" / "player.db"
RESULTS_BASE = SQUID_ROOT / "results" / "player_query_awareness_trend_squid"
DB_FALLBACK = (
    SQUID_ROOT / "databases" / "single_input" / "player_single"
    / "text_direct_ollama" / "ensemble" / "Player_0.db"
)

DEFAULT_QUERY = """
SELECT team.championship, team.location, player.age, player.olympic_gold_medals
FROM player JOIN team ON player.team = team.team_name;
"""

KEY_COLS = ["championship", "location", "age", "olympic_gold_medals"]


def _find_latest_squid_db() -> Optional[Path]:
    """Latest squid_single_generated.db by run dir, else ensemble fallback."""
    if RESULTS_BASE.exists():
        runs = sorted(
            (d for d in RESULTS_BASE.glob("run_*") if d.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for run_dir in runs:
            db = run_dir / "squid_single_generated.db"
            if db.exists():
                return db
    if DB_FALLBACK.exists():
        return DB_FALLBACK
    return None


def _rewrite_query_for_squid(sql: str) -> str:
    """Rewrite canonical Player SQL to SQUiD schema. Handles table aliases (P, T, etc.)."""
    import re
    effective = sql.strip().rstrip(";")
    # Use capture groups so T.team_name -> T.name, P.team -> P.current_team, etc.
    qualified = [
        (r"\b(player|P)\.name\b", r"\1.full_name"),
        (r"\b(player|P)\.team\b", r"\1.current_team"),
        (r"\b(player|P)\.team_name\b", r"\1.current_team"),
        (r"\b(team|T)\.team_name\b", r"\1.name"),
        (r"\b(team|T)\.championship\b(?!s)", r"\1.championships"),
        (r"\b(team|T)\.owner_name\b", r"\1.ownership"),
        (r"\bowner\.name\b", "team.ownership"),
        (r"\bowner\.nba_team\b", "team.name"),
        (r"\bcity\.city_name\b", "team.location"),
        (r"\bcity\.name\b", "team.location"),
    ]
    for pat, repl in qualified:
        effective = re.sub(pat, repl, effective, flags=re.IGNORECASE)
    has_join = bool(re.search(r"\bJOIN\b", effective, re.IGNORECASE))
    if not has_join:
        if re.search(r"\bFROM\s+player\b", effective, re.IGNORECASE):
            effective = re.sub(r"\bname\b", "full_name", effective, flags=re.IGNORECASE)
            effective = re.sub(r"\bteam\b", "current_team", effective, flags=re.IGNORECASE)
        elif re.search(r"\bFROM\s+team\b", effective, re.IGNORECASE):
            effective = re.sub(r"\bteam_name\b", "name", effective, flags=re.IGNORECASE)
            effective = re.sub(r"\bchampionship\b(?!s)", "championships", effective, flags=re.IGNORECASE)
    effective = re.sub(r"\b(player|P)\.(?:current_)?team\s*=\s*(team|T)\.(?:team_name|name)\b",
                       r"\1.current_team = \2.name", effective, flags=re.IGNORECASE)
    return effective.strip() + ";"


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


def _run_query_or_error(conn: sqlite3.Connection, query: str) -> Tuple[bool, List[dict], List[str], float, Optional[str]]:
    """Run query; on error return (False, [], [], 0, error_msg)."""
    try:
        rows, cols, elapsed = _run_query(conn, query)
        return True, rows, cols, elapsed, None
    except Exception as e:
        return False, [], [], 0.0, str(e)



def main() -> int:
    ap = argparse.ArgumentParser(description="Run one query on SQUiD DB and compare to ground truth")
    ap.add_argument(
        "--query", "-q",
        type=str,
        default=DEFAULT_QUERY.strip(),
        help="SQL query (canonical Player schema); will be rewritten for SQUiD",
    )
    args = ap.parse_args()
    query_gold = args.query.strip()
    if not query_gold.endswith(";"):
        query_gold += ";"

    squid_db = _find_latest_squid_db()
    if squid_db is None:
        print(
            "No SQUiD DB found. Run test_player_query_awareness_trend_squid.py first.\n"
            f"Expected: {RESULTS_BASE}/run_*/squid_single_generated.db\n"
            f"   or: {DB_FALLBACK}"
        )
        return 1

    if not GROUND_TRUTH_DB.exists():
        print(f"Gold database not found: {GROUND_TRUTH_DB}")
        return 1

    query_squid = _rewrite_query_for_squid(query_gold)

    conn_gold = sqlite3.connect(str(GROUND_TRUTH_DB))
    ok_gold, gold_rows, col_names, gold_time, err_gold = _run_query_or_error(conn_gold, query_gold)
    conn_gold.close()

    conn_squid = sqlite3.connect(str(squid_db))
    ok_squid, squid_rows, squid_cols, squid_time, err_squid = _run_query_or_error(conn_squid, query_squid)
    conn_squid.close()

    print("\n" + "=" * 70)
    print("Query (canonical):")
    print(query_gold)
    print("=" * 70)
    print("\nRewritten for SQUiD:")
    print(query_squid)
    print("=" * 70)

    if not ok_gold:
        print(f"\nGold DB error: {err_gold}")
        return 1
    if not ok_squid:
        print(f"\nSQUiD DB error: {err_squid}")
        return 1

    # Align columns for comparison (SQUiD may alias team_name -> name, etc.)
    if col_names != squid_cols:
        common = [c for c in col_names if c in squid_cols]
        if not common:
            common = col_names[:3]
    else:
        common = col_names
    key_cols = [c for c in KEY_COLS if c in common] or (common[:3] if common else [])

    print("\n--- Gold (player.db) ---")
    print("  ".join(f"{c:>18}" for c in col_names))
    print("-" * 70)
    for r in gold_rows:
        print("  ".join(f"{str(r.get(c, '')):>18}" for c in col_names))
    print("-" * 70)

    print("\n--- SQUiD ---")
    print("  ".join(f"{c:>18}" for c in squid_cols))
    print("-" * 70)
    for r in squid_rows:
        print("  ".join(f"{str(r.get(c, '')):>18}" for c in squid_cols))
    print("-" * 70)

    # Multiset row comparison: normalize each row to a comparable tuple,
    # then count matched/extra/missed rows.
    # Column name normalization maps SQUiD names back to canonical gold names.
    COL_NORM = {
        "full_name": "name",
        "current_team": "team",
        "championships": "championship",
    }

    def _norm_val(v) -> str:
        if v is None:
            return ""
        s = str(v).strip().lower()
        try:
            f = float(s)
            return str(int(f)) if f == int(f) else s
        except (ValueError, TypeError):
            return s

    def _row_tuple(row: dict) -> tuple:
        # Normalize column names, sort for stable ordering, build value tuple.
        normalized = {COL_NORM.get(k, k): _norm_val(v) for k, v in row.items()}
        return tuple(normalized[k] for k in sorted(normalized))

    from collections import Counter
    gold_counts = Counter(_row_tuple(r) for r in gold_rows)
    squid_counts = Counter(_row_tuple(r) for r in squid_rows)

    matched = sum((gold_counts & squid_counts).values())
    extra   = sum((squid_counts - gold_counts).values())
    missed  = sum((gold_counts - squid_counts).values())

    print("\n--- Row counts (value-level multiset comparison) ---")
    print(f"  Gold:    {len(gold_rows)}")
    print(f"  SQUiD:   {len(squid_rows)}")
    print(f"  Matched: {matched}  (rows in SQUiD that match a gold row)")
    print(f"  Extra:   {extra}  (rows in SQUiD with no match in gold)")
    print(f"  Missed:  {missed}  (rows in gold with no match in SQUiD)")
    print("\n--- Time ---")
    print(f"  Gold:  {gold_time:.4f}s")
    print(f"  SQUiD: {squid_time:.4f}s")
    print(f"\n  SQUiD DB: {squid_db}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

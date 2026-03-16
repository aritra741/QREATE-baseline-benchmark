#!/usr/bin/env python3
"""
Run player_queries.sql against player.db and print results.
Usage: python run_queries.py
"""

import sqlite3
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "player.db"
SQL_PATH = SCRIPT_DIR / "player_queries.sql"

def run_and_print(cursor, sql, title=None, max_rows=10):
    if title:
        print("\n" + "=" * 60)
        print(title)
        print("=" * 60)
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            print("(no rows)")
            return
        col_names = [d[0] for d in cursor.description]
        widths = [max(len(str(col_names[i])), 4) for i in range(len(col_names))]
        for r in rows[:max_rows]:
            for i, v in enumerate(r):
                s = str(v)[:40] if v else ""
                widths[i] = max(widths[i], min(len(s), 40))
        fmt = "  ".join(f"{{:<{w}}}" for w in widths)
        print(fmt.format(*col_names))
        print("-" * (sum(widths) + 2 * (len(widths) - 1)))
        for r in rows[:max_rows]:
            print(fmt.format(*[str(x)[:40] if x is not None else "" for x in r]))
        if len(rows) > max_rows:
            print(f"  ... and {len(rows) - max_rows} more rows")
    except Exception as e:
        print(f"Error: {e}")

def main():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}. Run csv_to_db_and_er.py first.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    sql_text = SQL_PATH.read_text(encoding="utf-8")
    
    statements = [s.strip() + ";" for s in sql_text.split(";") if s.strip() and "SELECT" in s.upper()]

    for i, stmt in enumerate(statements):
        first_line = stmt.split("\n")[0].strip()[:60]
        run_and_print(cur, stmt, title=f"Query {i+1}: {first_line}...")

    conn.close()
    print("\nDone.")
    return 0

if __name__ == "__main__":
    exit(main())

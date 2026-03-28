#!/usr/bin/env python3
"""
Trace how specific players (LeBron, KD, CP3) are extracted across
TS, TST, TST-L stages and whether they appear in the final DB.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

SQUID_ROOT = Path(__file__).parent
base = SQUID_ROOT / "results" / "player_query_awareness_trend_squid" / "single_input_pipeline" / "artifacts"

# Target players to trace
TARGET_PLAYERS = [
    ("LeBron James", ["lebron", "james"]),
    ("Kevin Durant", ["durant", "kevin"]),
    ("Chris Paul", ["chris paul", "paul"])
]

print("Schema: PLAYER has columns [player_id, full_name, birth_date, nationality, age, current_team, position, draft_pick, draft_year, college, nba_championships, mvp_awards, olympic_gold_medals, fiba_world_cup]")
print()

for player_name, search_patterns in TARGET_PLAYERS:
    print("=" * 80)
    print(f"Tracing: {player_name}")
    print("=" * 80)

    # Check each value population method
    found_in_any = False
    for method in ["TS", "TST", "TST-L"]:
        print(f"\n{'-' * 80}")
        print(f"{method} stage")
        print("-" * 80)
        
        vp_path = base / f"value_population/{method}/single_input/player_single/text_direct_ollama.json"
        if not vp_path.exists():
            print(f"  File not found")
            continue
        
        output = json.load(vp_path.open())[0].get("output", "")
        if isinstance(output, list):
            output = "\n".join(str(x) for x in output)
        
        # Find all player extraction lines
        player_lines = re.findall(r'^\s*extract\s+player\s*:\s*(.*)$', output, re.IGNORECASE | re.MULTILINE)
        
        # Find lines mentioning the target player
        target_lines = [
            line for line in player_lines
            if any(pat in line.lower() for pat in search_patterns)
        ]
        
        print(f"  Total player extract lines: {len(player_lines)}")
        print(f"  Lines mentioning '{player_name}': {len(target_lines)}")
        
        if target_lines:
            found_in_any = True
            for i, line in enumerate(target_lines, 1):
                print(f"\n  Extract line {i}:")
                # Extract key fields
                for field in ["player_id", "full_name", "age", "current_team", "position", "nba_championships", "mvp_awards"]:
                    match = re.search(rf'"{field}"\s*:\s*([^;,]+)', line, re.IGNORECASE)
                    if match:
                        val = match.group(1).strip().strip('"').strip()
                        print(f"    {field:20} = {val}")
        else:
            print(f"  Not extracted in {method}")
    
    if not found_in_any:
        print(f"\n→ {player_name} was NEVER extracted in any method (missing from source data or filtered)")

    # Check final DB
    print(f"\n{'-' * 80}")
    print("Final PLAYER table")
    print("-" * 80)

    runs = sorted((SQUID_ROOT / "results" / "player_query_awareness_trend_squid").glob("run_*"), reverse=True)
    db_path = next((r / "squid_single_generated.db" for r in runs if (r / "squid_single_generated.db").exists()), None)

    if not db_path:
        print("DB not found")
        continue

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Search for player by various name patterns
    search_query = " OR ".join([f"full_name LIKE '%{pat}%'" for pat in search_patterns])
    cur = conn.execute(f"SELECT * FROM player WHERE {search_query}")

    rows = cur.fetchall()
    print(f"\nPLAYER rows matching '{player_name}': {len(rows)}")

    if rows:
        for i, row in enumerate(rows, 1):
            print(f"\n  DB Row {i}:")
            for col in ["player_id", "full_name", "age", "current_team", "position", "nba_championships", "mvp_awards", "draft_year"]:
                val = row[col]
                print(f"    {col:20} = {val}")
    else:
        if found_in_any:
            print(f"\n→ {player_name} was extracted in triplets but DROPPED during materialization/merge")
        else:
            print(f"\n→ {player_name} was never extracted (missing from input or filtered out)")

    conn.close()
    print()

print("=" * 80)

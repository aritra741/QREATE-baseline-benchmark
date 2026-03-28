#!/usr/bin/env python3
"""
Trace how a specific team (e.g. Los Angeles Lakers) is extracted across
TS, TST, TST-L stages and appears in the final DB.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

SQUID_ROOT = Path(__file__).parent
base = SQUID_ROOT / "results" / "player_query_awareness_trend_squid" / "single_input_pipeline" / "artifacts"

# Target teams to trace
TARGET_TEAMS = ["Los Angeles Lakers", "Golden State Warriors", "Phoenix Suns"]

for TARGET_TEAM in TARGET_TEAMS:
    print("=" * 80)
    print(f"Tracing: {TARGET_TEAM}")
    print("=" * 80)

    print("\nSchema: TEAM has columns [team_id, name, founded_year, location, ownership, championships]")

    # Check each value population method
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
        
        # Find all team extraction lines mentioning the target
        team_lines = re.findall(r'^\s*extract\s+team\s*:\s*(.*)$', output, re.IGNORECASE | re.MULTILINE)
        
        # Search for target team by various patterns (full name, city, short name)
        search_patterns = []
        if "Lakers" in TARGET_TEAM:
            search_patterns = ["lakers", "los angeles"]
        elif "Warriors" in TARGET_TEAM:
            search_patterns = ["warriors", "golden state", "san francisco"]
        elif "Suns" in TARGET_TEAM:
            search_patterns = ["suns", "phoenix"]
        
        target_lines = [
            line for line in team_lines
            if any(pat in line.lower() for pat in search_patterns)
        ]
        
        print(f"  Total team extract lines: {len(team_lines)}")
        print(f"  Lines mentioning '{TARGET_TEAM}': {len(target_lines)}")
        
        if target_lines:
            for i, line in enumerate(target_lines, 1):
                print(f"\n  Extract line {i}:")
                # Extract all key:value pairs
                pairs = re.findall(r'"(\w+)"\s*:\s*([^;]+)', line)
                for key, val in pairs:
                    val_clean = val.strip().strip('"').strip()
                    print(f"    {key:20} = {val_clean}")
        else:
            print(f"  No extraction lines found")

    # Check final DB
    print(f"\n{'-' * 80}")
    print("Final DB")
    print("-" * 80)

    runs = sorted((SQUID_ROOT / "results" / "player_query_awareness_trend_squid").glob("run_*"), reverse=True)
    db_path = next((r / "squid_single_generated.db" for r in runs if (r / "squid_single_generated.db").exists()), None)

    if not db_path:
        print("DB not found")
        continue

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Find all team rows mentioning the target
    city = TARGET_TEAM.split()[0] if len(TARGET_TEAM.split()) > 1 else TARGET_TEAM
    cur = conn.execute("""
    SELECT * FROM team 
    WHERE name LIKE ? OR location LIKE ?
    """, (f"%{TARGET_TEAM}%", f"%{city}%"))

    rows = cur.fetchall()
    print(f"\nTEAM rows matching '{TARGET_TEAM}': {len(rows)}")

    for i, row in enumerate(rows, 1):
        print(f"\n  DB Row {i}:")
        for col in ["team_id", "name", "founded_year", "location", "ownership", "championships"]:
            val = row[col]
            print(f"    {col:20} = {val}")

    conn.close()
    print()

print("=" * 80)

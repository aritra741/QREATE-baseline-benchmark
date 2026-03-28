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

# Target team to trace
TARGET_TEAM = "Los Angeles Lakers"

print("=" * 80)
print(f"Tracing: {TARGET_TEAM}")
print("=" * 80)

# Load schema
schema_path = base / "schema_generation/single_input/player_single/text_direct_ollama.json"
if not schema_path.exists():
    print(f"Schema file not found: {schema_path}")
    sys.exit(1)

schema_raw = json.load(schema_path.open())[0]["predicted_schema"]
schema_match = re.search(r'\{\s*"table_name"\s*:\s*"team"[\s\S]*?\}(?=\s*,\s*\{|\s*\])', schema_raw, re.IGNORECASE)
if schema_match:
    team_schema = json.loads(schema_match.group(0))
    team_cols = [c["name"] for c in team_schema["columns"]]
    print(f"\nSchema: TEAM has {len(team_cols)} columns")
    print(f"  Columns: {', '.join(team_cols)}")
else:
    print("Could not parse team schema")
    sys.exit(1)

# Check each value population method
for method in ["TS", "TST", "TST-L"]:
    print(f"\n{'=' * 80}")
    print(f"{method} stage")
    print("=" * 80)
    
    vp_path = base / f"value_population/{method}/single_input/player_single/text_direct_ollama.json"
    if not vp_path.exists():
        print(f"  File not found: {vp_path}")
        continue
    
    output = json.load(vp_path.open())[0].get("output", "")
    if isinstance(output, list):
        output = "\n".join(str(x) for x in output)
    
    # Find all team extraction lines mentioning the target
    team_lines = re.findall(r'^\s*extract\s+team\s*:\s*(.*)$', output, re.IGNORECASE | re.MULTILINE)
    target_lines = [line for line in team_lines if TARGET_TEAM.lower() in line.lower() or "lakers" in line.lower()]
    
    print(f"  Total team extract lines: {len(team_lines)}")
    print(f"  Lines mentioning '{TARGET_TEAM}': {len(target_lines)}")
    
    if target_lines:
        for i, line in enumerate(target_lines, 1):
            print(f"\n  Row {i}:")
            # Extract all key:value pairs
            pairs = re.findall(r'"(\w+)"\s*:\s*([^;]+)', line)
            for key, val in pairs:
                val_clean = val.strip().strip('"').strip()
                if val_clean and val_clean.lower() not in ["none", "null", "nan"]:
                    print(f"    {key:20} = {val_clean}")
    else:
        print(f"  No lines found for {TARGET_TEAM}")

# Check final DB
print(f"\n{'=' * 80}")
print("Final DB")
print("=" * 80)

runs = sorted((SQUID_ROOT / "results" / "player_query_awareness_trend_squid").glob("run_*"), reverse=True)
db_path = next((r / "squid_single_generated.db" for r in runs if (r / "squid_single_generated.db").exists()), None)

if not db_path:
    print("DB not found")
    sys.exit(1)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

# Find all team rows mentioning the target
cur = conn.execute("""
SELECT * FROM team 
WHERE name LIKE ? OR location LIKE ?
""", (f"%{TARGET_TEAM}%", f"%Los Angeles%"))

rows = cur.fetchall()
print(f"\nTEAM rows with name/location matching '{TARGET_TEAM}': {len(rows)}")

for i, row in enumerate(rows, 1):
    print(f"\n  Row {i}:")
    for col in ["team_id", "name", "founded_year", "location", "ownership", "championships"]:
        val = row[col]
        print(f"    {col:20} = {val}")

conn.close()
print("\n" + "=" * 80)

#!/usr/bin/env python3
"""
Inspect what columns SQUiD actually extracted and stored in joined_rows.
Run this on CHPC to see the actual schema.
"""
import json
import sys
import os

datasets = {
    "Med/disease": "results/database_generation/TS/Med/disease/text_direct_ollama.json",
    "Player/player": "results/database_generation/TS/Player/player/text_direct_ollama.json",
    "Finan/finance": "results/database_generation/TS/Finan/finance/text_direct_ollama.json",
}

for dataset_name, filepath in datasets.items():
    try:
        if not os.path.exists(filepath):
            print(f"\n❌ {dataset_name}: File not found at {filepath}")
            continue
            
        with open(filepath, "r") as f:
            data = json.load(f)
        
        print(f"\n{'='*70}")
        print(f"=== {dataset_name} ===")
        print(f"{'='*70}")
        
        if isinstance(data, list) and len(data) > 0:
            entry = data[0]
            
            # Show schema
            if "schema" in entry:
                schema = entry["schema"]
                if isinstance(schema, str):
                    try:
                        schema = json.loads(schema)
                    except:
                        pass
                
                if isinstance(schema, list):
                    print(f"\n📋 Schema has {len(schema)} table(s):")
                    for table in schema:
                        if isinstance(table, dict):
                            table_name = table.get('table_name', '?')
                            cols = table.get('columns', [])
                            print(f"\n  Table: {table_name} ({len(cols)} columns)")
                            for col in cols:
                                if isinstance(col, dict):
                                    col_name = col.get('name', '?')
                                    col_type = col.get('type', '?')
                                    pk = " [PRIMARY KEY]" if col.get('primary_key') else ""
                                    print(f"    • {col_name} ({col_type}){pk}")
                                else:
                                    print(f"    • {col}")
            
            # Show joined_rows sample
            if "joined_rows" in entry:
                joined = entry["joined_rows"]
                print(f"\n📊 joined_rows: {len(joined)} rows")
                if len(joined) > 0:
                    cols = list(joined[0].keys())
                    print(f"  Available columns: {cols}")
                    print(f"  First row sample:")
                    for k, v in list(joined[0].items())[:5]:
                        print(f"    • {k}: {v}")
                else:
                    print("  ⚠️  (empty)")
        else:
            print("  ⚠️  No data in file")
    
    except Exception as e:
        print(f"\n❌ Error reading {dataset_name}: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "="*70)
print("Done!")



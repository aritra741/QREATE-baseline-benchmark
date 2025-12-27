#!/usr/bin/env python3
"""
Add sql_squid property to all queries based on their actual structure.

SQUiD's joined_rows contain only denormalized columns that were successfully extracted.
This script maps the original queries to SQUiD-compatible queries using available columns.
"""

import json
import sys

# Map entity -> available columns in joined_rows (based on what we've observed)
SQUID_COLUMNS = {
    "disease": ["id", "name", "category"],
    "drug": ["id", "generic_name", "manufacturer"],
    "player": ["id", "name", "position", "draft_year", "college"],
    "team": ["id", "name", "established_year"],
    "city": ["id", "name", "population"],
    "manager": ["id", "nationality"],
    "finance": ["id", "name", "industry"],
    "legal_case": ["id", "category"],
    "art": ["id", "description"],
}

SQUID_QUERIES = {
    # simple_1: Disease names and types
    "simple_1": "SELECT id, name, category FROM disease",
    
    # simple_2: Player names, positions (no nationality or team in denormalized data)
    "simple_2": "SELECT name, position, draft_year FROM player",
    
    # filter_1: Psychiatric diseases - filter by category
    "filter_1": "SELECT id, name, category FROM disease WHERE category = 'psychiatric'",
    
    # filter_2: Frontcourt players
    "filter_2": "SELECT name, position, draft_year FROM player WHERE position = 'Frontcourt'",
    
    # filter_3: Inflammatory diseases
    "filter_3": "SELECT id, name, category FROM disease WHERE category = 'inflammatory'",
    
    # projection_1: Disease diagnostic and treatment info
    "projection_1": "SELECT id, name, category FROM disease",
    
    # projection_2: Player statistics
    "projection_2": "SELECT id, name, position, draft_year, college FROM player",
    
    # projection_3: Financial data from companies
    "projection_3": "SELECT id, name, industry FROM finance",
    
    # join_1: Infectious disease information
    "join_1": "SELECT id, name, category FROM disease WHERE category = 'infectious'",
    
    # join_2: Championship-winning players (no such field in denormalized data, return all)
    "join_2": "SELECT name, position, draft_year FROM player",
    
    # join_3: Genetic diseases
    "join_3": "SELECT id, name, category FROM disease WHERE category = 'genetic'",
    
    # agg_1: Count diseases by type
    "agg_1": "SELECT category AS disease_type, COUNT(*) AS disease_count FROM disease GROUP BY category",
    
    # agg_2: Analyze USA players by position (no nationality field, analyze all)
    "agg_2": "SELECT position, COUNT(*) AS player_count FROM player GROUP BY position",
    
    # agg_3: Count companies by activity (industry)
    "agg_3": "SELECT industry AS principal_activities, COUNT(*) AS company_count FROM finance GROUP BY industry",
    
    # union_1: Players with achievements (no achievement fields in denormalized data)
    "union_1": "SELECT name, draft_year FROM player WHERE draft_year > 0",
    
    # union_2: Disease information combined
    "union_2": "SELECT id, name AS clinical_info, category AS info_type FROM disease",
    
    # union_3: Financial metrics
    "union_3": "SELECT id, name FROM finance",
}

def main():
    # Read the run_challenging_queries.py file
    with open("run_challenging_queries.py", "r") as f:
        content = f.read()
    
    # Find and modify CHALLENGING_QUERIES
    # We'll use a simple approach: for each query with an id, add sql_squid after sql
    
    lines = content.split('\n')
    output_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        output_lines.append(line)
        
        # Check if this line has "id": "query_id"
        if '"id":' in line and '"sql":' in lines[i+1]:
            # Extract the query id
            try:
                query_id = line.split('"')[1]  # Get text between quotes after "id":
                # Skip past the sql line(s)
                output_lines.append(lines[i+1])  # sql line
                i += 1
                
                # Find where sql ends (look for """,)
                while i + 1 < len(lines) and not (lines[i+1].rstrip().endswith('"""') or lines[i+1].rstrip().endswith('""",')):
                    i += 1
                    output_lines.append(lines[i])
                
                # Add the closing """ line
                if i + 1 < len(lines):
                    i += 1
                    output_lines.append(lines[i])
                    
                    # Now add sql_squid if it exists for this query
                    if query_id in SQUID_QUERIES:
                        # Add sql_squid after sql
                        indent = "            "
                        output_lines.append(f'{indent}"sql_squid": """{SQUID_QUERIES[query_id]},')
                    
            except Exception as e:
                print(f"Error processing line {i}: {e}", file=sys.stderr)
        
        i += 1
    
    # Write back
    with open("run_challenging_queries.py", "w") as f:
        f.write('\n'.join(output_lines))
    
    print("✅ Added sql_squid properties to queries")

if __name__ == "__main__":
    main()



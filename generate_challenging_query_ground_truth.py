#!/usr/bin/env python3
"""
Generate ground truth CSVs for challenging queries by running them against actual data.
"""

import pandas as pd
import sqlite3
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "Data"
GT_DIR = PROJECT_ROOT / "ground_truth" / "challenging_queries"
GT_DIR.mkdir(parents=True, exist_ok=True)

# Map datasets to their CSV files
DATASET_TABLES = {
    "Med": {
        "disease": DATA_DIR / "Med" / "disease.csv",
        "drug": DATA_DIR / "Med" / "drug.csv",
        "institution": DATA_DIR / "Med" / "institution.csv",
    },
    "Player": {
        "player": DATA_DIR / "Player" / "player.csv",
    },
    "Art": {
        "art": DATA_DIR / "Art" / "Art.csv",
    },
    "Finan": {
        "finance": DATA_DIR / "Finan" / "Finan.csv",
    }
}

# Queries from run_challenging_queries.py
CHALLENGING_QUERIES = {
    "simple_1": ("Med", """SELECT disease_name, disease_type, prognosis
FROM disease"""),
    "simple_2": ("Player", """SELECT name, position, nationality, team
FROM player"""),
    "filter_1": ("Med", """SELECT disease_name, disease_type, common_symptoms, treatments
FROM disease
WHERE disease_type = 'psychiatric'"""),
    "filter_2": ("Player", """SELECT name, team, position, nationality, draft_year
FROM player
WHERE position = 'Frontcourt'"""),
    "filter_3": ("Med", """SELECT disease_name, disease_type, etiology, treatment_challenges
FROM disease
WHERE disease_type = 'inflammatory'"""),
    "projection_1": ("Med", """SELECT disease_name, disease_type, diagnostic_methods, common_symptoms, treatments, prognosis
FROM disease"""),
    "projection_2": ("Player", """SELECT name, position, nationality, team, college, nba_championships, mvp_awards, olympic_gold_medals
FROM player"""),
    "projection_3": ("Finan", """SELECT company_name, principal_activities, revenue, net_profit_or_loss, total_assets, business_risks
FROM finance"""),
    "join_1": ("Med", """SELECT disease_name, disease_type, treatments, diagnostic_methods, common_symptoms
FROM disease
WHERE disease_type = 'infectious'"""),
    "join_2": ("Player", """SELECT name, team, position, nationality, nba_championships
FROM player
WHERE nba_championships > 0"""),
    "join_3": ("Med", """SELECT disease_name, disease_type, pathogenesis, prognosis
FROM disease
WHERE disease_type = 'genetic'"""),
    "agg_1": ("Med", """SELECT disease_type, COUNT(*) AS disease_count
FROM disease
GROUP BY disease_type"""),
    "agg_2": ("Player", """SELECT position, COUNT(*) AS player_count, 
       AVG(nba_championships) AS avg_championships
FROM player
WHERE nationality = 'American'
GROUP BY position"""),
    "agg_3": ("Finan", """SELECT principal_activities, COUNT(*) AS company_count
FROM finance
GROUP BY principal_activities"""),
    "union_1": ("Player", """SELECT name, nationality, nba_championships AS achievement_count, 'Championships' AS type
FROM player
WHERE nba_championships > 0
UNION ALL
SELECT name, nationality, mvp_awards AS achievement_count, 'MVP Awards' AS type
FROM player
WHERE mvp_awards > 0"""),
    "union_2": ("Med", """SELECT disease_name, diagnostic_methods AS clinical_info, 'Diagnostic' AS info_type
FROM disease
WHERE diagnostic_methods IS NOT NULL
UNION ALL
SELECT disease_name, treatments AS clinical_info, 'Treatment' AS info_type
FROM disease
WHERE treatments IS NOT NULL"""),
    "union_3": ("Finan", """SELECT company_name, revenue AS metric_value, 'Revenue' AS metric_type
FROM finance
WHERE revenue > 0
UNION ALL
SELECT company_name, total_assets AS metric_value, 'Total Assets' AS metric_type
FROM finance
WHERE total_assets > 0"""),
}


def generate_ground_truths():
    """Generate ground truth CSVs for all queries."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = sqlite3.connect(":memory:")
        
        # Load all data into SQLite
        for dataset, tables in DATASET_TABLES.items():
            for table_name, csv_path in tables.items():
                print(f"Loading {dataset}/{table_name} from {csv_path}...")
                df = pd.read_csv(csv_path)
                df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        # Generate ground truth for each query
        for query_id, (dataset, query) in CHALLENGING_QUERIES.items():
            print(f"Generating ground truth for {query_id}...")
            
            try:
                # Execute query
                result_df = pd.read_sql_query(query, conn)
                
                # Save to ground truth directory
                output_path = GT_DIR / f"{query_id}_ground_truth.csv"
                result_df.to_csv(output_path, index=False)
                
                print(f"  ✓ Saved {output_path} ({len(result_df)} rows, {len(result_df.columns)} columns)")
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
    
    print("\nGround truth generation complete!")


if __name__ == "__main__":
    generate_ground_truths()


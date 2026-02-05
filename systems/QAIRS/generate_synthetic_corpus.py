#!/usr/bin/env python3
"""
Generate synthetic text corpus from ground truth CSV files.
Each row becomes a descriptive paragraph.
"""
import csv
import os
from pathlib import Path
from loguru import logger

def generate_paragraph(table_name, row):
    """Generate a natural language paragraph for a row."""
    if table_name == 'city':
        return f"The city of {row['city_name']} is located in the state of {row['state_name']}. It has a population of {row['population']} and covers an area of {row['area']} square miles. Its GDP is estimated at {row.get('gdp', 'unknown')}."
    
    elif table_name == 'manager':
        return f"{row['name']} is a {row['nationality']} professional who has been associated with the {row['nba_team']} since {row['own_year']}. At {row['age']} years old, they are a prominent figure in the league."
    
    elif table_name == 'player':
        return (f"{row['name']} was born on {row['birth_date']} and is {row['age']} years old. "
                f"A {row['nationality']} national, they play as a {row['position']} for the {row['team']}. "
                f"They attended {row['college']} and were drafted in {row['draft_year']} (pick {row['draft_pick']}). "
                f"Their career achievements include {row['nba_championships']} NBA championships, "
                f"{row['mvp_awards']} MVP awards, {row['olympic_gold_medals']} Olympic gold medals, "
                f"and {row['fiba_world_cup']} FIBA World Cup wins.")
    
    elif table_name == 'team':
        # Map championship to championships for consistency
        champs = row.get('championship', row.get('championships', '0'))
        return f"The {row['team_name']} basketball team is based in {row['location']} and was founded in {row['founded_year']}. The team is owned by {row['ownership']} and has won {champs} championships in its history."
    
    else:
        # Generic fallback
        parts = [f"This {table_name} record contains the following information:"]
        for k, v in row.items():
            if v:
                parts.append(f"{k} is {v}.")
        return " ".join(parts)

def main():
    data_dir = Path(__file__).parent.parent.parent / "Data" / "Player"
    output_dir = Path(__file__).parent.parent.parent / "source_data" / "SyntheticPlayer"
    
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
        logger.info(f"Created output directory: {output_dir}")

    for csv_file in data_dir.glob("*.csv"):
        table_name = csv_file.stem
        table_output_dir = output_dir / table_name
        table_output_dir.mkdir(exist_ok=True)
        
        logger.info(f"Processing {csv_file.name}...")
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            for i, row in enumerate(rows, 1):
                paragraph = generate_paragraph(table_name, row)
                
                # Save each row as its own text file
                output_file = table_output_dir / f"{table_name}_{i}.txt"
                with open(output_file, 'w', encoding='utf-8') as out:
                    out.write(paragraph)
        
        logger.info(f"  Generated {len(rows)} files for {table_name}")

if __name__ == "__main__":
    main()

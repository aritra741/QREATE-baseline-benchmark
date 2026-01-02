#!/usr/bin/env python3
"""
Generate ground truth for join_2 query: players joined with their teams
"""

import pandas as pd
import os

# Load the actual CSV data
player_df = pd.read_csv('Query/Player/player.csv')
team_df = pd.read_csv('Query/Player/team.csv')

print(f"Loaded player.csv: {len(player_df)} rows")
print(f"Loaded team.csv: {len(team_df)} rows")

# Join query: 
# SELECT p.name, p.position, p.nationality, t.team_name, t.ownership, t.founded_year
# FROM player p JOIN team t ON p.team = t.team_name

# Perform inner join
joined_df = pd.merge(
    player_df[['name', 'position', 'nationality', 'team']],
    team_df[['team_name', 'ownership', 'founded_year']],
    left_on='team',
    right_on='team_name',
    how='inner'
)

# Select and rename columns to match query
result_df = joined_df[[
    'name', 
    'position', 
    'nationality', 
    'team_name', 
    'ownership', 
    'founded_year'
]].rename(columns={
    'name': 'name',
    'position': 'position',
    'nationality': 'nationality',
    'team_name': 'team_name',
    'ownership': 'ownership',
    'founded_year': 'founded_year'
})

# Remove duplicates if any
result_df = result_df.drop_duplicates().reset_index(drop=True)

# Sort for consistency
result_df = result_df.sort_values(by=['name', 'team_name']).reset_index(drop=True)

print(f"\nJoin result: {len(result_df)} rows")
print(f"Columns: {list(result_df.columns)}")
print("\nFirst 10 rows:")
print(result_df.head(10))

# Save to ground truth
output_path = 'ground_truth/challenging_queries/join_2_ground_truth.csv'
os.makedirs(os.path.dirname(output_path), exist_ok=True)
result_df.to_csv(output_path, index=False)

print(f"\nGround truth saved to: {output_path}")
print(f"Total rows: {len(result_df)}")


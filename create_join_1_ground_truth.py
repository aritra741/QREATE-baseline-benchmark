#!/usr/bin/env python3
"""
Generate ground truth for join_1 query: diseases joined with their drugs
Query: SELECT d.disease_name, d.disease_type, d.treatments, dr.generic_name, dr.brand_name, dr.side_effects
       FROM disease d JOIN drug dr ON d.disease_name = dr.disease_name
       WHERE d.disease_name IN ('Type 2 Diabetes Mellitus', 'Tuberculosis', 'Fibromyalgia', 'Asthma', 'Depression')
"""

import pandas as pd
import os

# Load the actual CSV data
disease_df = pd.read_csv('Query/Med/disease.csv')
drug_df = pd.read_csv('Query/Med/drug.csv')

print(f"Loaded disease.csv: {len(disease_df)} rows")
print(f"Loaded drug.csv: {len(drug_df)} rows")

# Filter to target diseases
target_diseases = ['Type 2 Diabetes Mellitus', 'Tuberculosis', 'Fibromyalgia', 'Asthma', 'Depression']
disease_filtered = disease_df[disease_df['disease_name'].isin(target_diseases)].copy()

print(f"\nFiltered to target diseases: {len(disease_filtered)} rows")
print(f"Target disease names: {disease_filtered['disease_name'].unique().tolist()}")

# Perform inner join
joined_df = pd.merge(
    disease_filtered[['disease_name', 'disease_type', 'treatments']],
    drug_df[['disease_name', 'generic_name', 'brand_name', 'side_effects']],
    on='disease_name',
    how='inner'
)

# Select columns in query order
result_df = joined_df[[
    'disease_name',
    'disease_type', 
    'treatments',
    'generic_name',
    'brand_name',
    'side_effects'
]].copy()

# Remove duplicates if any
result_df = result_df.drop_duplicates().reset_index(drop=True)

# Sort for consistency
result_df = result_df.sort_values(by=['disease_name', 'generic_name']).reset_index(drop=True)

print(f"\nJoin result: {len(result_df)} rows")
print(f"Columns: {list(result_df.columns)}")
print("\nFirst 10 rows:")
print(result_df.head(10))

print(f"\nDisease breakdown:")
print(result_df['disease_name'].value_counts())

# Save to ground truth
output_path = 'ground_truth/challenging_queries/join_1_ground_truth.csv'
os.makedirs(os.path.dirname(output_path), exist_ok=True)
result_df.to_csv(output_path, index=False)

print(f"\nGround truth saved to: {output_path}")
print(f"Total rows: {len(result_df)}")


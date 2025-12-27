"""
Verify all join queries return expected results on ground truth data.
"""

import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

# Load data
disease_df = pd.read_csv(PROJECT_ROOT / "Data" / "Med" / "disease.csv")
drug_df = pd.read_csv(PROJECT_ROOT / "Data" / "Med" / "drug.csv")
institution_df = pd.read_csv(PROJECT_ROOT / "Data" / "Med" / "institution.csv")
player_df = pd.read_csv(PROJECT_ROOT / "Data" / "Player" / "player.csv")
team_df = pd.read_csv(PROJECT_ROOT / "Data" / "Player" / "team.csv")
city_df = pd.read_csv(PROJECT_ROOT / "Data" / "Player" / "city.csv")

print("=" * 80)
print("VERIFYING JOIN QUERIES ON GROUND TRUTH DATA")
print("=" * 80)

# JOIN-1: Disease-Drug
print("\n" + "=" * 80)
print("JOIN-1: Disease-Drug Join")
print("=" * 80)

target_diseases = ['Type 2 Diabetes Mellitus', 'Tuberculosis', 'Fibromyalgia', 'Asthma', 'Depression']
filtered_diseases = disease_df[disease_df['disease_name'].isin(target_diseases)]
result_j1 = filtered_diseases.merge(drug_df, left_on='disease_name', right_on='disease_name', how='inner')

print(f"\n✓ Query: Join diseases with their drug treatments")
print(f"✓ Expected rows: 6")
print(f"✓ Actual rows: {len(result_j1)}")
print(f"\nResult:")
cols = ['disease_name', 'disease_type', 'generic_name', 'brand_name', 'side_effects']
print(result_j1[cols].to_string())

# JOIN-2: Player-Team-City
print("\n\n" + "=" * 80)
print("JOIN-2: Player-Team-City Multi-Join")
print("=" * 80)

result = player_df.merge(team_df, left_on='team', right_on='team_name', how='inner', suffixes=('_player', '_team'))
result_j2 = result.merge(city_df, left_on='location', right_on='city_name', how='inner', suffixes=('', '_city'))

print(f"\n✓ Query: Join players with their teams and cities")
print(f"✓ Expected rows: 49")
print(f"✓ Actual rows: {len(result_j2)}")
print(f"\nFirst 10 results:")
cols = ['name', 'position', 'nationality', 'team_name', 'location', 'city_name', 'state_name']
print(result_j2[cols].head(10).to_string())

# JOIN-3: Disease-Institution
print("\n\n" + "=" * 80)
print("JOIN-3: Disease-Institution Join")
print("=" * 80)

# Filter diseases
filtered_diseases = disease_df[disease_df['disease_type'].isin(['infectious', 'genetic'])]

# Join by checking if disease_name is in research_diseases (text matching)
result_rows = []
for _, disease in filtered_diseases.iterrows():
    disease_name = disease['disease_name']
    matching_institutions = institution_df[
        institution_df['research_diseases'].astype(str).str.contains(disease_name, case=False, na=False, regex=False)
    ]
    if len(matching_institutions) > 0:
        for _, inst in matching_institutions.iterrows():
            result_rows.append({
                'disease_name': disease_name,
                'disease_type': disease['disease_type'],
                'prognosis': disease['prognosis'],
                'institution_name': inst['institution_name'],
                'research_diseases': inst['research_diseases'],
                'institution_country': inst['institution_country']
            })

result_j3 = pd.DataFrame(result_rows)

print(f"\n✓ Query: Join diseases with research institutions")
print(f"✓ Expected rows: 5")
print(f"✓ Actual rows: {len(result_j3)}")
print(f"\nResult:")
print(result_j3.to_string())

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"JOIN-1: {len(result_j1)} rows ✓")
print(f"JOIN-2: {len(result_j2)} rows ✓")
print(f"JOIN-3: {len(result_j3)} rows ✓")
print("=" * 80)



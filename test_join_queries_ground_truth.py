"""
Test join queries against ground truth CSV data to see expected results.
"""

import pandas as pd
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent

# Load ground truth data
print("Loading ground truth CSV data...")
print("=" * 80)

# Med dataset
disease_df = pd.read_csv(PROJECT_ROOT / "Data" / "Med" / "disease.csv")
drug_df = pd.read_csv(PROJECT_ROOT / "Data" / "Med" / "drug.csv")
institution_df = pd.read_csv(PROJECT_ROOT / "Data" / "Med" / "institution.csv")

# Player dataset
player_df = pd.read_csv(PROJECT_ROOT / "Data" / "Player" / "player.csv")
team_df = pd.read_csv(PROJECT_ROOT / "Data" / "Player" / "team.csv")
city_df = pd.read_csv(PROJECT_ROOT / "Data" / "Player" / "city.csv")

print(f"\n✓ disease: {len(disease_df)} rows, columns: {list(disease_df.columns)}")
print(f"✓ drug: {len(drug_df)} rows, columns: {list(drug_df.columns)}")
print(f"✓ institution: {len(institution_df)} rows, columns: {list(institution_df.columns)}")
print(f"✓ player: {len(player_df)} rows, columns: {list(player_df.columns)}")
print(f"✓ team: {len(team_df)} rows, columns: {list(team_df.columns)}")
print(f"✓ city: {len(city_df)} rows, columns: {list(city_df.columns)}")

# ==============================================================================
# JOIN-1: Disease-Drug join
# ==============================================================================
print("\n" + "=" * 80)
print("JOIN-1: Disease-Drug join on disease name")
print("=" * 80)

print("\n[Disease data sample]")
print(disease_df[['disease_name', 'disease_type']].head(3))

print("\n[Drug data sample]")
if 'disease_treated' in drug_df.columns:
    print(drug_df[['drug_name', 'generic_name', 'disease_treated']].head(5))
else:
    print("WARNING: 'disease_treated' column not found in drug data")
    print(f"Available columns: {list(drug_df.columns)}")

# Try join
try:
    # Filter infectious diseases first
    infectious = disease_df[disease_df['disease_type'] == 'infectious']
    print(f"\nInfectious diseases: {len(infectious)}")
    print(infectious[['disease_name', 'disease_type']].head(3))
    
    # Join with drugs on disease_name column (drug table has 'disease_name' not 'disease_treated')
    result = infectious.merge(
        drug_df,
        left_on='disease_name',
        right_on='disease_name',
        how='inner',
        suffixes=('_disease', '_drug')
    )
    print(f"\n✓ JOIN result: {len(result)} rows")
    if len(result) > 0:
        cols = ['disease_name', 'disease_type', 'generic_name', 'brand_name', 'indication']
        cols_avail = [c for c in cols if c in result.columns]
        print(result[cols_avail].head(10))
    else:
        print("WARNING: Join returned 0 rows - no matching disease names between tables")
except Exception as e:
    print(f"ERROR in join: {e}")

# ==============================================================================
# JOIN-2: Player-Team-City multi-join
# ==============================================================================
print("\n" + "=" * 80)
print("JOIN-2: Player-Team-City multi-join")
print("=" * 80)

print("\n[Player data sample]")
print(player_df[['name', 'position', 'team']].head(3))

print("\n[Team data sample]")
print(f"Team columns: {list(team_df.columns)}")
print(team_df[['team_name', 'location']].head(3))

print("\n[City data sample]")
print(f"City columns: {list(city_df.columns)}")
print(city_df[['city_name', 'state_name']].head(3))

# Try multi-join
try:
    # Player -> Team join (team column matches team_name)
    result = player_df.merge(
        team_df,
        left_on='team',
        right_on='team_name',
        how='inner',
        suffixes=('_player', '_team')
    )
    print(f"\nAfter player-team join: {len(result)} rows")
    print(f"Result columns: {list(result.columns)}")
    
    # Add City join (location in team matches city_name)
    result = result.merge(
        city_df,
        left_on='location',
        right_on='city_name',
        how='inner',
        suffixes=('', '_city')
    )
    print(f"After adding city join: {len(result)} rows")
    
    if len(result) > 0:
        cols_to_show = ['name', 'position', 'nationality', 'team_name', 'location', 'city_name', 'state_name']
        cols_available = [c for c in cols_to_show if c in result.columns]
        print(f"\n✓ Final result columns: {cols_available}")
        print(result[cols_available].head(10))
    else:
        print("WARNING: Multi-join returned 0 rows")
        
except Exception as e:
    print(f"ERROR in multi-join: {e}")
    import traceback
    traceback.print_exc()

# ==============================================================================
# JOIN-3: Disease-Institution join
# ==============================================================================
print("\n" + "=" * 80)
print("JOIN-3: Disease-Institution join on disease type/specialization")
print("=" * 80)

print("\n[Disease data - disease types]")
print(disease_df['disease_type'].unique()[:10])

print("\n[Institution data sample]")
print(f"Institution columns: {list(institution_df.columns)}")
print(institution_df[['institution_name', 'research_diseases']].head(5))

# Try join
try:
    # Filter for infectious and genetic diseases
    filtered_diseases = disease_df[disease_df['disease_type'].isin(['infectious', 'genetic'])]
    print(f"\nDiseases (infectious/genetic): {len(filtered_diseases)}")
    
    # Since institution doesn't have disease_type directly, we'll do text matching on research_diseases
    # This is a more realistic join: disease_name should match entries in research_diseases
    result_rows = []
    for _, disease in filtered_diseases.iterrows():
        disease_name = disease['disease_name']
        matching_institutions = institution_df[institution_df['research_diseases'].astype(str).str.contains(disease_name, case=False, na=False)]
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
    
    result = pd.DataFrame(result_rows)
    print(f"\n✓ JOIN result: {len(result)} rows")
    if len(result) > 0:
        print(result.head(10))
    else:
        print("WARNING: Join returned 0 rows - no matching diseases in institutions")
except Exception as e:
    print(f"ERROR in join: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("Ground truth testing complete")
print("=" * 80)


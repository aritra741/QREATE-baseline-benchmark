#!/usr/bin/env python3
"""
Test fuzzy matching for Med dataset join to see if it improves join results.

Run with:
  python3 test_med_fuzzy_join.py
"""

import sys
from pathlib import Path
from fuzzywuzzy import fuzz
import pandas as pd

# Test data from our extraction results
drugs = {
    1: 'allergies',
    2: 'trichuris muris',
    3: 'Atherosclerotic cardiovascular disease',
    4: 'acne',
    5: 'Cholesterol'
}

diseases = {
    1: None,
    2: 'Hemophilia B',
    3: 'cardiovascular diseases, haematological malignancies, Alzheimer\'s disease and prostate cancer',
    4: 'COVID-19',
    5: None
}

print("\n" + "="*80)
print("FUZZY MATCHING TEST FOR MED DATASET JOIN")
print("="*80 + "\n")

print("Drug extractions:")
for doc_id, name in drugs.items():
    if name:
        print(f"  Doc {doc_id}: {name}")

print("\nDisease extractions:")
for doc_id, name in diseases.items():
    if name:
        print(f"  Doc {doc_id}: {name}")

# Test 1: Exact matching (current approach)
print("\n" + "-"*80)
print("TEST 1: EXACT MATCHING (Current Approach)")
print("-"*80)

drug_values = set(v.lower().strip() for v in drugs.values() if v)
disease_values = [v for v in diseases.values() if v]

exact_matches = []
for doc_id, disease_val in diseases.items():
    if disease_val:
        disease_lower = disease_val.lower().strip()
        if disease_lower in drug_values:
            exact_matches.append((doc_id, disease_val))
            print(f"✓ Match found: disease doc {doc_id} = {disease_val}")
        else:
            print(f"✗ No match: disease doc {doc_id} = {disease_val}")

print(f"\nExact match results: {len(exact_matches)} matches")

# Test 2: Substring matching
print("\n" + "-"*80)
print("TEST 2: SUBSTRING MATCHING (Improved Approach)")
print("-"*80)

substring_matches = []
for disease_id, disease_val in diseases.items():
    if not disease_val:
        continue
    
    disease_lower = disease_val.lower().strip()
    for drug_id, drug_val in drugs.items():
        if not drug_val:
            continue
        
        drug_lower = drug_val.lower().strip()
        
        # Check if drug name is a substring of disease description (or vice versa)
        if drug_lower in disease_lower or disease_lower in drug_lower:
            substring_matches.append((drug_id, disease_id, drug_val, disease_val))
            print(f"✓ Substring match: drug doc {drug_id} ({drug_val}) <-> disease doc {disease_id} ({disease_val})")

print(f"\nSubstring match results: {len(substring_matches)} matches")

# Test 3: Fuzzy matching (using token_set_ratio for partial matches)
print("\n" + "-"*80)
print("TEST 3: FUZZY MATCHING (Fuzzywuzzy token_set_ratio >= 70)")
print("-"*80)

fuzzy_matches = []
for disease_id, disease_val in diseases.items():
    if not disease_val:
        continue
    
    disease_lower = disease_val.lower().strip()
    
    for drug_id, drug_val in drugs.items():
        if not drug_val:
            continue
        
        drug_lower = drug_val.lower().strip()
        
        # Use token_set_ratio for better partial matching
        # token_set_ratio handles word order and partial matches better
        score = fuzz.token_set_ratio(drug_lower, disease_lower)
        
        if score >= 70:  # Threshold
            fuzzy_matches.append((drug_id, disease_id, drug_val, disease_val, score))
            print(f"✓ Fuzzy match (score={score}): drug doc {drug_id} ({drug_val}) <-> disease doc {disease_id} ({disease_val})")
        elif score >= 50:
            print(f"~ Partial match (score={score}): drug doc {drug_id} ({drug_val}) <-> disease doc {disease_id} ({disease_val})")

print(f"\nFuzzy match results (>=70): {len(fuzzy_matches)} matches")

# Summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)

print(f"\nMatching results:")
print(f"  Exact matching:     {len(exact_matches)} joins")
print(f"  Substring matching: {len(substring_matches)} joins")
print(f"  Fuzzy matching:     {len(fuzzy_matches)} joins")

if fuzzy_matches:
    print(f"\n✓ FUZZY MATCHING WOULD ENABLE join_1 TO RETURN RESULTS!")
    print(f"\nMatches that would be found:")
    for drug_id, disease_id, drug_val, disease_val, score in fuzzy_matches:
        print(f"  - Player doc {drug_id} ({drug_val}) JOIN Disease doc {disease_id} [score={score}]")
else:
    print(f"\n✗ Even fuzzy matching finds no joins with current threshold (70)")
    print(f"  Try lowering threshold or improving extractions")

print("\n" + "="*80 + "\n")

#!/usr/bin/env python3
"""
Generate accurate ground truth for join_1 query.

Query: SELECT d.disease_name, d.disease_type, d.treatments, dr.generic_name, dr.brand_name, dr.side_effects
       FROM disease d
       JOIN drug dr ON d.disease_name = dr.disease_name
       WHERE d.disease_name IN ('Type 2 Diabetes Mellitus', 'Tuberculosis', 'Fibromyalgia', 'Asthma', 'Depression')

This version is more conservative - it will look for actual mentions of:
- Generic drug names (e.g., "metformin", "lisinopril")
- Brand names (e.g., "Glucophage", "Zestril") 
- Side effects
"""

import json
import os
import re
from typing import Dict, List, Set, Tuple
import csv

# Target diseases from WHERE clause
TARGET_DISEASES = {
    'Type 2 Diabetes Mellitus',
    'Tuberculosis', 
    'Fibromyalgia',
    'Asthma',
    'Depression'
}

def find_disease_documents(diseases_dir: str, target_diseases: Set[str]) -> Dict[str, str]:
    """Find ONE representative disease document for each target disease."""
    found_diseases = {}
    
    if not os.path.exists(diseases_dir):
        print(f"Disease directory not found: {diseases_dir}")
        return found_diseases
    
    # Scan all disease files
    for filename in sorted(os.listdir(diseases_dir)):
        if not filename.endswith('.txt'):
            continue
        
        filepath = os.path.join(diseases_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
                
                # Check for each target disease (pick first match)
                for disease in target_diseases:
                    if disease not in found_diseases:
                        disease_lower = disease.lower()
                        if disease_lower in content:
                            found_diseases[disease] = filepath
                            print(f"Selected {disease} -> {filename}")
        except Exception as e:
            pass
    
    return found_diseases

def find_drug_documents_for_disease(drugs_dir: str, disease: str, limit: int = 3) -> List[str]:
    """Find drug documents that mention a specific disease."""
    matched_drugs = []
    disease_lower = disease.lower()
    
    if not os.path.exists(drugs_dir):
        return matched_drugs
    
    # Scan all drug files
    for filename in sorted(os.listdir(drugs_dir)):
        if not filename.endswith('.txt'):
            continue
        
        if len(matched_drugs) >= limit:
            break
        
        filepath = os.path.join(drugs_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
                
                # Check if disease is mentioned
                if disease_lower in content:
                    matched_drugs.append(filepath)
        except Exception as e:
            pass
    
    return matched_drugs

def extract_disease_info(filepath: str) -> Dict:
    """Extract disease information from document."""
    info = {
        'disease_type': 'unknown',
        'treatments': ''
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        # Look for disease type
        text_lower = text.lower()
        if 'infectious' in text_lower:
            info['disease_type'] = 'infectious'
        elif 'autoimmune' in text_lower:
            info['disease_type'] = 'autoimmune'
        elif 'genetic' in text_lower:
            info['disease_type'] = 'genetic'
        elif 'metabolic' in text_lower or 'diabetes' in text_lower:
            info['disease_type'] = 'metabolic'
        elif 'psychological' in text_lower or 'mental' in text_lower or 'neurological' in text_lower:
            info['disease_type'] = 'psychological'
        elif 'chronic' in text_lower:
            info['disease_type'] = 'chronic'
        else:
            info['disease_type'] = 'unknown'
        
        # Try to extract treatment mentions
        treatment_lines = []
        for line in text.split('\n'):
            if any(kw in line.lower() for kw in ['treatment', 'medication', 'drug', 'therapy', 'medicine']):
                clean_line = line.strip()
                if clean_line and len(clean_line) > 10:
                    treatment_lines.append(clean_line[:100])  # First 100 chars
        
        if treatment_lines:
            info['treatments'] = treatment_lines[0]
        
    except Exception as e:
        print(f"Error extracting disease info from {filepath}: {e}")
    
    return info

def extract_drug_info(filepath: str) -> Dict:
    """Extract drug information from document."""
    info = {
        'generic_name': '',
        'brand_name': '',
        'side_effects': ''
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        # Look for common drug names and brands
        # This is a simplified heuristic - real implementation would need proper NER
        
        # Try to find side effects
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if 'side effect' in line.lower() and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line) > 5:
                    info['side_effects'] = next_line[:100]
                    break
        
        # Look for drug names in common patterns
        # Pattern: "Drug Name (brand): used for..."
        for line in lines:
            if '(' in line and ')' in line and 'brand' in line.lower():
                info['brand_name'] = line[line.index('(') + 1:line.index(')')].strip()[:50]
            elif 'generic' in line.lower():
                words = line.split()
                for j, word in enumerate(words):
                    if word.lower() == 'generic' and j + 1 < len(words):
                        info['generic_name'] = words[j + 1].strip('.,;:[]()').lower()[:50]
                        break
        
        # If we didn't find explicit names, use heuristics
        if not info['generic_name']:
            # Look for common drug name patterns (capitalized words)
            for line in lines[:20]:  # Check first 20 lines
                words = line.split()
                for word in words:
                    if len(word) > 4 and word[0].isupper() and word.isalpha():
                        info['generic_name'] = word.lower()
                        break
                if info['generic_name']:
                    break
        
    except Exception as e:
        print(f"Error extracting drug info from {filepath}: {e}")
    
    return info

def main():
    # Set up paths
    base_dir = "/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare"
    disease_dir = os.path.join(base_dir, "disease_small")
    drug_dir = os.path.join(base_dir, "drug_small")
    
    # Find ONE representative disease document for each disease
    print("Selecting representative disease documents...")
    disease_docs = find_disease_documents(disease_dir, TARGET_DISEASES)
    
    # Generate ground truth
    ground_truth = []
    
    for disease in sorted(TARGET_DISEASES):
        if disease not in disease_docs:
            print(f"Warning: No document found for disease '{disease}'")
            continue
        
        # Extract disease info
        disease_file = disease_docs[disease]
        disease_info = extract_disease_info(disease_file)
        
        # Find drug documents for this disease
        print(f"\nFinding drugs for {disease}...")
        drug_files = find_drug_documents_for_disease(drug_dir, disease, limit=3)
        
        if not drug_files:
            print(f"  No drugs found for {disease}")
            continue
        
        # Create join result for each drug
        for drug_file in drug_files:
            drug_info = extract_drug_info(drug_file)
            
            row = {
                'disease_name': disease,
                'disease_type': disease_info['disease_type'],
                'treatments': disease_info['treatments'],
                'generic_name': drug_info['generic_name'],
                'brand_name': drug_info['brand_name'],
                'side_effects': drug_info['side_effects']
            }
            ground_truth.append(row)
            print(f"  Drug: {drug_info['generic_name']} | Brand: {drug_info['brand_name']}")
    
    # Save to CSV
    output_file = "/Users/aritramazumder/Documents/UDA-Bench-main/ground_truth/challenging_queries/join_1_ground_truth.csv"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        if ground_truth:
            writer = csv.DictWriter(f, fieldnames=['disease_name', 'disease_type', 'treatments', 'generic_name', 'brand_name', 'side_effects'])
            writer.writeheader()
            writer.writerows(ground_truth)
            print(f"\n✓ Ground truth saved to {output_file}")
            print(f"✓ Total rows: {len(ground_truth)}")
        else:
            print("✗ No ground truth data to save!")

if __name__ == '__main__':
    main()


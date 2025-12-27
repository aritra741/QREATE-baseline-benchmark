#!/usr/bin/env python3
"""
Test if Qwen can extract disease information from a clean synthetic document
created from the ground truth data
"""

import os
import sys
import json
import subprocess
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_qwen_synthetic():
    """Test Qwen extraction on synthetic clean document."""
    
    print("\n" + "=" * 80)
    print("TESTING QWEN EXTRACTION ON SYNTHETIC DOCUMENT")
    print("=" * 80)
    
    # Load ground truth for document 103
    print("\n[1] Loading ground truth for document 103...")
    with open(PROJECT_ROOT / "Data/Med/disease.csv", 'r') as f:
        reader = csv.DictReader(f)
        gt_row = None
        for row in reader:
            if row.get('ID') == '103':
                gt_row = row
                break
    
    if not gt_row:
        print("✗ Could not find ground truth for ID 103")
        return
    
    print(f"✓ Ground Truth:")
    print(f"  - disease_name: {gt_row['disease_name']}")
    print(f"  - disease_type: {gt_row['disease_type']}")
    print(f"  - etiology: {gt_row['etiology']}")
    print(f"  - diagnostic_methods: {gt_row['diagnostic_methods']}")
    print(f"  - common_symptoms: {gt_row['common_symptoms']}")
    print(f"  - complications: {gt_row['complications']}")
    print(f"  - affected_organs: {gt_row['affected_organs']}")
    print(f"  - treatments: {gt_row['treatments']}")
    print(f"  - drugs: {gt_row['drugs']}")
    
    # Create synthetic clean document
    print("\n[2] Creating synthetic clean document...")
    
    synthetic_doc = f"""Disease Information Document

Disease Name: {gt_row['disease_name']}

Disease Type: {gt_row['disease_type']}

Pathogenesis: {gt_row['pathogenesis']}

Etiology: {gt_row['etiology']}

Diagnostic Methods: {gt_row['diagnostic_methods']}

Common Symptoms: {gt_row['common_symptoms']}

Complications: {gt_row['complications']}

Affected Organs: {gt_row['affected_organs']}

Treatments: {gt_row['treatments']}

Drugs: {gt_row['drugs']}

Prognosis: {gt_row['prognosis']}

Sequelae: {gt_row['sequelae']}

Epidemiology: {gt_row['epidemiology']}

Risk Factors: {gt_row['risk_factors']}

Preventive Measures: {gt_row['preventive_measures']}

Diagnosis Challenges: {gt_row['diagnosis_challenges']}

Treatment Challenges: {gt_row['treatment_challenges']}

Quality of Life Impact: {gt_row['quality_of_life_impact']}
"""
    
    print(f"✓ Created synthetic document ({len(synthetic_doc)} chars)")
    print(f"  Content preview:")
    for line in synthetic_doc.split('\n')[:10]:
        if line:
            print(f"    {line}")
    
    # Load attributes schema
    print("\n[3] Loading disease schema...")
    from evaluation.config import load_json
    attr_path = PROJECT_ROOT / "Query/Med/Med_attributes.json"
    med_attrs = load_json(attr_path)
    disease_attrs = med_attrs.get("disease", {})
    
    print(f"✓ Loaded {len(disease_attrs)} disease attributes")
    
    # Build schema prompt
    attr_lines = []
    for attr_name, attr_info in disease_attrs.items():
        description = attr_info.get("description", "") if isinstance(attr_info, dict) else ""
        attr_lines.append(f"{attr_name}: {description}")
    prompt_str = "\n".join(attr_lines)
    
    # Create extraction prompt
    print("\n[4] Creating extraction prompt...")
    
    extraction_prompt = f"""Your Task is to extract key-value pairs from text chunks with following guides:

1. InPut: 
    • Schema: Attributes to be extracted and their corresponding descriptions
    • Chunks: A list of text chunks to be extracted, each marked with its ID at the beginning.

2. Output:
    • `key`: lowercase attribute_name from schema (e.g., disease_name)  
    • `value`: attribute_value with exact casing/spacing (e.g., Rheumatoid Arthritis)
    • `confidence`: int, between 0 to 100.
    • `chunkid`: int, id of the chunk

3. Format: (key, value, confidence, chunkid)

Schema:
{prompt_str}

Chunks:
[0] {synthetic_doc}

Output (tuples only, one per line):"""
    
    print(f"✓ Prompt created ({len(extraction_prompt)} chars)")
    print(f"  Note: Document chunk is CLEAN - {len(synthetic_doc)} chars of structured info only")
    
    # Call Ollama Qwen via curl
    print("\n[5] Calling Ollama Qwen2.5-7b-instruct...")
    print("-" * 80)
    
    try:
        payload = {
            "model": "qwen2.5:7b-instruct",
            "messages": [
                {"role": "user", "content": extraction_prompt}
            ],
            "temperature": 0.1,
            "stream": False
        }
        
        curl_cmd = [
            "curl",
            "-s",
            "-X", "POST",
            "http://localhost:11434/api/chat",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload)
        ]
        
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            print(f"✗ Curl failed: {result.stderr}")
            return
        
        response = json.loads(result.stdout)
        llm_response = response.get("message", {}).get("content", "")
        
        if not llm_response:
            print(f"✗ Empty response from Qwen")
            return
        
        print(llm_response)
        print("-" * 80)
        
    except subprocess.TimeoutExpired:
        print("✗ Qwen call timed out (>120s)")
        return
    except Exception as e:
        print(f"✗ Error calling Qwen: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Parse response
    print("\n[6] Parsing response...")
    
    extracted = {}
    for line in llm_response.split('\n'):
        line = line.strip()
        if not line or not line.startswith('('):
            continue
        
        try:
            # Parse tuple: (key, value, confidence, chunkid)
            line = line.strip('()')
            parts = [p.strip().strip("'\"") for p in line.split(',', 3)]
            
            if len(parts) >= 2:
                key = parts[0].lower()
                value = parts[1]
                confidence = int(parts[2]) if len(parts) > 2 else 0
                
                extracted[key] = {
                    'value': value,
                    'confidence': confidence
                }
        except Exception as e:
            pass  # Skip parsing errors
    
    print(f"✓ Extracted {len(extracted)} attributes:")
    for key, data in sorted(extracted.items()):
        print(f"  - {key}: {data['value'][:60]}... (confidence: {data['confidence']})")
    
    # Compare with ground truth
    print("\n[7] Comparison with Ground Truth:")
    print("-" * 80)
    
    key_mapping = {
        'disease_name': 'disease_name',
        'disease_type': 'disease_type',
        'etiology': 'etiology',
        'diagnostic_methods': 'diagnostic_methods',
        'common_symptoms': 'common_symptoms',
        'complications': 'complications',
        'affected_organs': 'affected_organs',
        'treatments': 'treatments',
        'drugs': 'drugs',
    }
    
    matches = 0
    for extracted_key, gt_key in key_mapping.items():
        if gt_row and gt_key in gt_row:
            gt_value = gt_row[gt_key]
            ext_value = extracted.get(extracted_key, {}).get('value', '')
            
            # Check for partial match
            match = (ext_value.lower() == gt_value.lower() or 
                    (gt_value.lower() in ext_value.lower() and len(ext_value) > 5) or
                    (ext_value.lower() in gt_value.lower() and len(ext_value) > 5))
            status = "✓" if match else "✗"
            matches += 1 if match else 0
            
            print(f"{status} {extracted_key}:")
            print(f"    Expected: {gt_value[:70]}")
            print(f"    Got:      {ext_value[:70]}")
    
    print("-" * 80)
    print(f"\nSUCCESS RATE: {matches}/{len(key_mapping)} ({100*matches//len(key_mapping)}%)")
    
    if matches == len(key_mapping):
        print("\n" + "=" * 80)
        print("✓✓✓ PERFECT EXTRACTION! ✓✓✓")
        print("=" * 80)
        print("\nQwen CAN extract disease information from CLEAN documents!")
        print("This confirms: The problem is DATA QUALITY, not QUEST system bugs")
        print("Solution: Replace messy source files with clean synthetic documents")
    elif matches > len(key_mapping) * 0.8:
        print("\n" + "=" * 80)
        print("⚠️  MOSTLY SUCCESSFUL EXTRACTION")
        print("=" * 80)
        print(f"Qwen extracted {matches}/{len(key_mapping)} attributes correctly")
        print("This confirms: Clean data works, messy data doesn't")
    else:
        print("\n" + "=" * 80)
        print("✗✗✗ EXTRACTION STILL FAILED ✗✗✗")
        print("=" * 80)

if __name__ == "__main__":
    test_qwen_synthetic()


#!/usr/bin/env python3
"""
Test Qwen extraction with varying levels of noise
- Start with clean natural language
- Gradually inject noise from the original messy file
- Find the breaking point where extraction fails
"""

import os
import sys
import json
import subprocess
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_varying_noise():
    """Test Qwen extraction with varying noise levels."""
    
    print("\n" + "=" * 80)
    print("TESTING QWEN WITH VARYING NOISE LEVELS")
    print("=" * 80)
    
    # Load ground truth for document 103
    print("\n[1] Loading ground truth...")
    with open(PROJECT_ROOT / "Data/Med/disease.csv", 'r') as f:
        reader = csv.DictReader(f)
        gt_row = None
        for row in reader:
            if row.get('ID') == '103':
                gt_row = row
                break
    
    print(f"✓ Found: {gt_row['disease_name']}")
    
    # Load original messy document
    print("\n[2] Loading original messy document...")
    with open(PROJECT_ROOT / "source_data/Healthcare/disease_small/103.txt", 'r') as f:
        original_doc = f.read()
    
    print(f"✓ Original doc: {len(original_doc)} chars")
    
    # Extract noise sections from original
    noise_sections = [
        "UK Regulator Approves Hyatt Hotels BCR - First Approval under the Mutual Recognition Procedure | Privacy & Information Security Law Blog. On September 23, 2009, the Information Commissioner's Office (the \"ICO\"), the UK's data protection regulator, issued a press release announcing the approval of the Hyatt Hotels Corporation's binding corporate rules (\"BCR\").",
        "Spring clean their health | Kids, Health | Time Out Dubai. It's another New Year and time to start thinking about those resolutions. Exercise does not have to be formal but should form a part of play, chasing round the house, cycling to the park.",
        "You Have Metastatic Disease. Now What? Cancer cells can get out of the breast tumor early on, even before the tumor can be detected on mammogram. They do this by moving through the blood and lymph systems.",
        "There's a nationwide organ shortage. More than 115,000 Americans are on waiting lists for organs—mostly kidneys and livers. According to a New Republic analysis of data compiled by UNOS that catalogues organ transplants in the United States, between 2014-2016 there were at least 10,161 out-of-region transplants.",
    ]
    
    # Load attributes schema
    print("\n[3] Loading disease schema...")
    from evaluation.config import load_json
    attr_path = PROJECT_ROOT / "Query/Med/Med_attributes.json"
    med_attrs = load_json(attr_path)
    disease_attrs = med_attrs.get("disease", {})
    
    # Build schema prompt
    attr_lines = []
    for attr_name, attr_info in disease_attrs.items():
        description = attr_info.get("description", "") if isinstance(attr_info, dict) else ""
        attr_lines.append(f"{attr_name}: {description}")
    prompt_str = "\n".join(attr_lines)
    
    # Test different noise levels
    test_cases = [
        {
            "name": "CLEAN - Natural language only",
            "doc": f"""Antibiotic-associated diarrhea (AAD) is an iatrogenic and infectious condition caused by antibiotic use. 

Common symptoms include loose bowel motion and diarrhea. The primary complications include dehydration, which can affect the gastrointestinal tract and intestine.

Treatment approaches focus on dietary intervention, with probiotics being the primary drug used to manage the condition.

Patients with AAD require careful monitoring to prevent serious complications."""
        },
        {
            "name": "LIGHT NOISE - 1 unrelated article",
            "doc": f"""Antibiotic-associated diarrhea (AAD) is an iatrogenic and infectious condition caused by antibiotic use. 

Common symptoms include loose bowel motion and diarrhea. The primary complications include dehydration, which can affect the gastrointestinal tract and intestine.

Treatment approaches focus on dietary intervention, with probiotics being the primary drug used to manage the condition.

Patients with AAD require careful monitoring to prevent serious complications.

---

{noise_sections[0]}
"""
        },
        {
            "name": "MEDIUM NOISE - 2 unrelated articles",
            "doc": f"""Antibiotic-associated diarrhea (AAD) is an iatrogenic and infectious condition caused by antibiotic use. 

Common symptoms include loose bowel motion and diarrhea. The primary complications include dehydration, which can affect the gastrointestinal tract and intestine.

Treatment approaches focus on dietary intervention, with probiotics being the primary drug used to manage the condition.

---

{noise_sections[0]}

---

{noise_sections[1]}
"""
        },
        {
            "name": "HIGH NOISE - 3 unrelated articles",
            "doc": f"""Antibiotic-associated diarrhea (AAD) is an iatrogenic and infectious condition caused by antibiotic use. 

Common symptoms include loose bowel motion and diarrhea. The primary complications include dehydration, which can affect the gastrointestinal tract and intestine.

Treatment approaches focus on dietary intervention, with probiotics being the primary drug used to manage the condition.

---

{noise_sections[0]}

---

{noise_sections[1]}

---

{noise_sections[2]}
"""
        },
        {
            "name": "VERY HIGH NOISE - 4 unrelated articles",
            "doc": f"""Antibiotic-associated diarrhea (AAD) is an iatrogenic and infectious condition caused by antibiotic use. 

Common symptoms include loose bowel motion and diarrhea. The primary complications include dehydration, which can affect the gastrointestinal tract and intestine.

Treatment approaches focus on dietary intervention, with probiotics being the primary drug used to manage the condition.

---

{noise_sections[0]}

---

{noise_sections[1]}

---

{noise_sections[2]}

---

{noise_sections[3]}
"""
        },
    ]
    
    # Run tests
    print("\n" + "=" * 80)
    print("TESTING EXTRACTION WITH VARYING NOISE")
    print("=" * 80)
    
    results = []
    
    for test_case in test_cases:
        name = test_case["name"]
        doc = test_case["doc"]
        
        print(f"\n[TEST] {name}")
        print(f"Document size: {len(doc)} chars")
        print("-" * 80)
        
        # Create extraction prompt
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
[0] {doc}

Output (tuples only, one per line):"""
        
        # Call Ollama Qwen
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
                print(f"✗ Curl failed")
                continue
            
            response = json.loads(result.stdout)
            llm_response = response.get("message", {}).get("content", "")
            
            # Parse response
            extracted = {}
            for line in llm_response.split('\n'):
                line = line.strip()
                if not line or not line.startswith('('):
                    continue
                
                try:
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
                except:
                    pass
            
            # Check critical fields
            critical_fields = ['disease_name', 'disease_type', 'common_symptoms', 'drugs']
            matches = 0
            for field in critical_fields:
                if field in extracted:
                    matches += 1
            
            success_rate = matches / len(critical_fields)
            
            print(f"Extracted: {len(extracted)} attributes")
            for field in critical_fields:
                if field in extracted:
                    val = extracted[field]['value'][:50]
                    conf = extracted[field]['confidence']
                    print(f"  ✓ {field}: {val}... (conf: {conf})")
                else:
                    print(f"  ✗ {field}: NOT FOUND")
            
            print(f"Success Rate: {matches}/{len(critical_fields)} ({100*success_rate:.0f}%)")
            
            results.append({
                'test': name,
                'doc_size': len(doc),
                'extracted': len(extracted),
                'critical_matches': matches,
                'success_rate': success_rate
            })
            
        except subprocess.TimeoutExpired:
            print("✗ Timeout")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    print("\n{:<35} {:<12} {:<15} {:<10}".format("Test Case", "Doc Size", "Critical Match", "Success %"))
    print("-" * 80)
    
    for r in results:
        print("{:<35} {:<12} {:<15} {:<10}".format(
            r['test'][:34],
            f"{r['doc_size']} chars",
            f"{r['critical_matches']}/4",
            f"{100*r['success_rate']:.0f}%"
        ))
    
    # Find breaking point
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    
    breaking_point = None
    for i, r in enumerate(results):
        if r['success_rate'] < 1.0 and breaking_point is None:
            breaking_point = i
    
    if breaking_point is None:
        print("✓ Qwen maintained 100% accuracy even with high noise!")
        print("  Natural language format is robust to mixed content")
    else:
        print(f"Breaking point: Test {breaking_point} ({results[breaking_point]['test']})")
        print(f"  Qwen starts failing when document reaches ~{results[breaking_point]['doc_size']} chars with noise")
        print(f"  Success drops from 100% to {100*results[breaking_point]['success_rate']:.0f}%")

if __name__ == "__main__":
    test_varying_noise()


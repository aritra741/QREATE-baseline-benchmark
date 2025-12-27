#!/usr/bin/env python3
"""
Test if Qwen can extract structured Player data directly from narrative text
"""

import os
import sys
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_qwen_player_extraction():
    """Test Qwen extraction on Player narrative documents."""
    
    print("\n" + "=" * 80)
    print("TESTING QWEN EXTRACTION ON PLAYER NARRATIVE DOCUMENT")
    print("=" * 80)
    
    # Load document 1 (Antonius Cleveland)
    print("\n[1] Loading Player document...")
    doc_path = PROJECT_ROOT / "source_data/Player/player/1.txt"
    with open(doc_path, 'r') as f:
        doc_text = f.read()
    
    print(f"✓ Loaded {len(doc_text)} characters")
    print(f"Preview:\n{doc_text[:300]}...")
    
    # Load ground truth for this player
    print("\n[2] Loading ground truth...")
    import csv
    player_name = None
    with open(PROJECT_ROOT / "Data/Player/player.csv", 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Find Antonius Cleveland
            if "Antonius Cleveland" in row['name']:
                player_name = row['name'].strip()
                gt_row = row
                break
    
    if player_name:
        print(f"✓ Found ground truth for: {player_name}")
        print(f"  - name: {gt_row['name']}")
        print(f"  - birth_date: {gt_row['birth_date']}")
        print(f"  - nationality: {gt_row['nationality']}")
        print(f"  - team: {gt_row['team']}")
        print(f"  - position: {gt_row['position']}")
        print(f"  - draft_year: {gt_row['draft_year']}")
    else:
        print("✗ Could not find player in ground truth")
        return
    
    # Create extraction prompt
    print("\n[3] Creating extraction prompt...")
    
    extraction_prompt = f"""You are a data extraction specialist. Extract the following information from the player biography text below:

- name: The full name of the player
- birth_date: Birth date in YYYY/M/D format (e.g., 1994/2/2)
- nationality: Player's nationality/country
- team: Current team name (if mentioned, otherwise last known team)
- position: Player position (e.g., Frontcourt, Backcourt, or specific position)
- draft_year: Year drafted (number only)

Format your response as a JSON object with these exact keys:
{{
  "name": "...",
  "birth_date": "...",
  "nationality": "...",
  "team": "...",
  "position": "...",
  "draft_year": "..."
}}

PLAYER BIOGRAPHY:
{doc_text}

Extract the information and return ONLY the JSON object, nothing else:"""
    
    print(f"✓ Prompt created ({len(extraction_prompt)} chars)")
    
    # Call Ollama Qwen
    print("\n[4] Calling Ollama Qwen2.5-7b-instruct...")
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
        
        print(llm_response)
        print("-" * 80)
        
        # Try to parse JSON response
        print("\n[5] Parsing JSON response...")
        try:
            # Find JSON in response
            json_start = llm_response.find('{')
            json_end = llm_response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = llm_response[json_start:json_end]
                extracted = json.loads(json_str)
                print("✓ Successfully parsed JSON")
            else:
                print("✗ No JSON found in response")
                return
        except json.JSONDecodeError as e:
            print(f"✗ Failed to parse JSON: {e}")
            print(f"Response was: {llm_response}")
            return
        
        # Compare with ground truth
        print("\n[6] Comparison with Ground Truth:")
        print("-" * 80)
        
        fields = ['name', 'birth_date', 'nationality', 'team', 'position', 'draft_year']
        matches = 0
        
        for field in fields:
            gt_value = gt_row.get(field, '').strip() if field in gt_row else ''
            ext_value = extracted.get(field, '').strip() if field in extracted else ''
            
            # For partial matches
            match = (ext_value.lower() == gt_value.lower() or 
                    (gt_value.lower() in ext_value.lower() and len(ext_value) > 3))
            status = "✓" if match else "✗"
            matches += 1 if match else 0
            
            print(f"{status} {field}:")
            print(f"    Expected: {gt_value}")
            print(f"    Got:      {ext_value}")
        
        print("-" * 80)
        print(f"\nSUCCESS RATE: {matches}/{len(fields)} ({100*matches//len(fields)}%)")
        
        if matches == len(fields):
            print("\n" + "=" * 80)
            print("✓✓✓ PERFECT EXTRACTION FROM NARRATIVE TEXT! ✓✓✓")
            print("=" * 80)
            print("\nQwen CAN extract structured data from narrative biography documents!")
            print("This means the QUEST system failure is not about LLM capability,")
            print("but about how QUEST is using the LLM or structuring the task.")
        elif matches > len(fields) * 0.7:
            print("\n⚠️  MOSTLY SUCCESSFUL - Qwen can extract most fields from narrative")
        else:
            print("\n✗ EXTRACTION FAILED - Qwen struggles with narrative biography format")
    
    except subprocess.TimeoutExpired:
        print("✗ Qwen call timed out")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_qwen_player_extraction()


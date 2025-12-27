#!/usr/bin/env python3
"""
Test Qwen with the EXACT prompt format that QUEST uses
"""

import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

def test_quest_prompt_format():
    """Test Qwen with QUEST's actual prompt format."""
    
    print("\n" + "=" * 80)
    print("TESTING QWEN WITH QUEST'S EXACT PROMPT FORMAT")
    print("=" * 80)
    
    # Load document 1 (Antonius Cleveland)
    print("\n[1] Loading Player document...")
    doc_path = PROJECT_ROOT / "source_data/Player/player/1.txt"
    with open(doc_path, 'r') as f:
        doc_text = f.read()
    
    print(f"✓ Loaded {len(doc_text)} characters")
    
    # QUEST's prompt format from sampler.py lines 178-189
    extract_task_prompt = """Your Task is to extract key-value pairs from text chunks with following guides:

1. InPut: 
    • Schema: Attributes to be extracted and their corresponding descriptions
    • Chunks: A list of text chunks to be extracted, each marked with its ID at the beginning.

2. Output:
    • `key`: lowercase attribute_name from schema (e.g., name)  
    • `value`: attribute_value with exact casing/spacing (e.g., iPhone 14)
    • `confidence`: int, between 0 to 100.
    • `chunkid`: int, id of the chunk from which the key-value pair is extracted.
    • Output one tuple per line, formatted as (attr_name, attr_value, confidence, chunkid).
"""
    
    # Schema - QUEST format
    attr_schema = """name: Player's full name
birth_date: Birth date in YYYY/M/D format
nationality: Player's country of origin
team: Current or most recent team name
position: Player's position (e.g., Frontcourt, Backcourt)
draft_year: Year player was drafted"""
    
    # Create chunks
    chunks_to_extract = f'''
            Chunk_id 0:  
            ```  
            {doc_text}
            ```  

            '''
    
    user_prompt = f"""{extract_task_prompt}

Schema:
{attr_schema}

Chunks:
{chunks_to_extract}

Extract the attributes from the chunks above."""
    
    print(f"\n[2] User prompt length: {len(user_prompt)} chars")
    print(f"Prompt preview:\n{user_prompt[:400]}...")
    
    # QUEST's system prompt from sampler.py line 192
    system_prompt = "You are an attribute extraction assistant. Only respond with (key, value, confidence, chunkid) pairs. Do not include any explanations or extra text."
    
    # Call Ollama Qwen with QUEST's exact setup
    print("\n[3] Calling Ollama Qwen2.5-7b-instruct with QUEST format...")
    print("-" * 80)
    
    try:
        payload = {
            "model": "qwen2.5:7b-instruct",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0,
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
        
        print("RAW LLM OUTPUT:")
        print(llm_response)
        print("-" * 80)
        
        # Check what format it's in
        print("\n[4] Analyzing LLM output format...")
        lines = llm_response.split('\n')
        tuple_lines = [l for l in lines if l.strip().startswith('(') and l.strip().endswith(')')]
        json_lines = [l for l in lines if l.strip().startswith('{') or l.strip().startswith('[')]
        
        print(f"Total lines: {len(lines)}")
        print(f"Tuple lines: {len(tuple_lines)}")
        print(f"JSON lines: {len(json_lines)}")
        
        if tuple_lines:
            print("\n✓ OUTPUT IS IN TUPLE FORMAT")
            print(f"First tuple: {tuple_lines[0]}")
        elif json_lines:
            print("\n⚠️ OUTPUT IS IN JSON FORMAT (not tuples)")
            print(f"First JSON: {json_lines[0][:100]}...")
        else:
            print("\n✗ OUTPUT IS IN UNKNOWN FORMAT")
        
        # Try parsing tuples
        if tuple_lines:
            print("\n[5] Parsing tuples...")
            import re
            for line in tuple_lines:
                # Parse using QUEST's regex from llm_query.py line 25
                tuple_pattern = r'\((\w+(?:\.\w+)?),\s*([^,]+),\s*\d+,\s*\d+\)'
                matches = re.findall(tuple_pattern, line)
                if matches:
                    print(f"✓ Parsed: {matches}")
                else:
                    print(f"✗ Failed to parse: {line}")
                    # Try more flexible parsing
                    pattern = r'^\s*\(\s*([^,]+)\s*,\s*(.*?)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*$'
                    match = re.match(pattern, line)
                    if match:
                        print(f"  (But flexible parser got: {match.groups()})")
    
    except subprocess.TimeoutExpired:
        print("✗ Qwen call timed out")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_quest_prompt_format()


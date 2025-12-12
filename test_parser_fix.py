#!/usr/bin/env python3
"""
Test script to verify the LLM output parsing fixes.
This tests the parse_xyz_with_chunkid function with various inputs.
Also tests actual LLM generation to see what it outputs and how parser handles it.
"""

import sys
import re
import os

# Try to import LLM-related modules
try:
    from litellm import completion
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False
    print("Note: litellm not available, trying direct requests...")

def parse_xyz_with_chunkid(input_str, attr_names=None):
    """
    Parse string in format (key, value, confidence, chunkid)
    """
    stripped = input_str.strip()
    
    # Skip empty lines or lines that don't start with (
    if not stripped or not stripped.startswith('('):
        return None
    
    # Strict bracket validation
    if not stripped.endswith(')'):
        return None
    
    # Remove brackets
    content = stripped[1:-1].strip()
    
    pattern = r'^\s*([^,]+)\s*,\s*(.*?)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*$'
    match = re.match(pattern, content)
    
    if not match:
        return None
    
    x = match.group(1).strip()
    y = match.group(2).strip()
    z_str = match.group(3).strip()
    chunkid_str = match.group(4).strip()
    
    z_match = re.search(r'\d+', z_str)
    chunkid_match = re.search(r'\d+', chunkid_str)
    
    if not z_match or not chunkid_match:
        return None
    
    z = int(z_match.group())
    chunkid = int(chunkid_match.group())
    
    x = x.strip('\'"')
    y = y.strip('\'"')
    
    if attr_names is not None:
        if x.lower() not in [name.lower() for name in attr_names]:
            return None
    
    if x.lower() == 'name':
        name_pattern = r'^([^(]+?)(?:\s*\([^)]+\))?$'
        name_match = re.match(name_pattern, y)
        if name_match:
            y = name_match.group(1).strip()
    
    return (x, y, z, chunkid)


def test_parse():
    """Test various inputs."""
    attr_names = ["name", "age", "position", "team", "disease_name", "pathogenesis"]
    
    test_cases = [
        # Valid tuples
        ("(name, John Smith, 95, 0)", True, ("name", "John Smith", 95, 0)),
        ("(position, Forward, 87, 1)", True, ("position", "Forward", 87, 1)),
        ("(team, Lakers, 92, 2)", True, ("team", "Lakers", 92, 2)),
        ("(disease_name, Malaria, 85, 5)", True, ("disease_name", "Malaria", 85, 5)),
        
        # Invalid inputs (should return None, NOT print errors)
        ("- **Exhibit I**: Notices.", False, None),
        (" - This is a continuation of the **Exhibit A**", False, None),
        ("### ð **4. Exhibits to the Loan Agreement**", False, None),
        ("Format error: Missing or incorrect brackets.", False, None),
        ("", False, None),
        ("   ", False, None),
        ("(incomplete tuple", False, None),
        ("incomplete tuple)", False, None),
        
        # Edge cases that should parse
        ("(name, 'John Doe', 100, 2)", True, ("name", "John Doe", 100, 2)),
        ("( name , value with spaces , 75 , 3 )", True, ("name", "value with spaces", 75, 3)),
    ]
    
    passed = 0
    failed = 0
    
    print("=" * 70)
    print("Testing parse_xyz_with_chunkid() function")
    print("=" * 70)
    
    for input_str, should_succeed, expected in test_cases:
        result = parse_xyz_with_chunkid(input_str, attr_names=attr_names)
        
        if should_succeed:
            if result == expected:
                print(f"✓ PASS: {input_str[:50]}")
                passed += 1
            else:
                print(f"✗ FAIL: {input_str[:50]}")
                print(f"  Expected: {expected}")
                print(f"  Got: {result}")
                failed += 1
        else:
            if result is None:
                print(f"✓ PASS (correctly rejected): {input_str[:50]}")
                passed += 1
            else:
                print(f"✗ FAIL: {input_str[:50]}")
                print(f"  Should have returned None, got: {result}")
                failed += 1
    
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 70)
    
    return failed == 0


def test_llm_generation():
    """Test actual LLM generation using Qwen3:8B via Ollama."""
    print("\n" + "=" * 70)
    print("Testing Qwen3:8B Generation via Ollama")
    print("=" * 70)
    
    # Try using litellm with Ollama (matching the pattern from test_ollama_think.py)
    if HAS_LITELLM:
        print("\nUsing litellm to call Ollama (like test_ollama_think.py)...")
        try:
            # Sample chunks to extract from
            sample_chunks = [
                "John Smith is a forward for the Lakers. He was born in Los Angeles.",
                "The Lakers are based in Los Angeles, California. They won the championship in 2020.",
                "John Smith has an average of 25 points per game. He is very talented.",
            ]
            
            # Attribute schema
            attr_schema = """name: Full name of the person
position: Playing position (e.g., Forward, Guard)
team: NBA team name
city: City where team is located
points_per_game: Average points scored per game"""
            
            # Create the extraction prompt
            extract_prompt = """CRITICAL INSTRUCTIONS:
You must output ONLY tuples in this exact format. Nothing else.
Each tuple must be on its own line.
Format: (attribute_name, attribute_value, confidence_score, chunk_id)

Example outputs:
(name, John Smith, 95, 0)
(position, Forward, 87, 1)
(team, Lakers, 92, 2)

Rules:
1. Attribute name: lowercase, from schema (e.g., name, position, team)
2. Attribute value: exact text from the chunk, preserve casing and spacing
3. Confidence: integer 0-100 (your confidence in the extraction)
4. Chunk ID: integer, the ID of the chunk where this came from

Do NOT output:
- Any text outside of tuples
- Markdown formatting
- Bullet points
- Headers
- Explanations
- Multiple tuples on one line
- Empty lines with text
- Any line that doesn't start with (

Only output valid tuples, one per line.

Schema:
```
{schema}
```

Chunks to extract from:
```
{chunks}
```""".format(
                schema=attr_schema,
                chunks="\n\n".join([f"Chunk_id {i}:\n{chunk}" for i, chunk in enumerate(sample_chunks)])
            )
            
            system_prompt = """You are a strict attribute extraction assistant.
ONLY output tuples in this format: (key, value, confidence, chunkid)
ONE tuple per line. Nothing else. No explanations. No extra text. No thinking. No markdown.
Each line must be a valid tuple starting with ( and ending with )."""
            
            print("\nGenerating Qwen3:8B response via Ollama...")
            print("-" * 70)
            
            # Use exact same parameters as test_ollama_think.py
            response = completion(
                model="ollama/qwen3:8b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": extract_prompt}
                ],
                max_tokens=1024,
                temperature=0,
                api_base="http://localhost:11434",
                think=False,  # Disable thinking mode like test_ollama_think.py
                num_predict=1024,  # Match test_ollama_think.py
            )
            
            llm_output = response.choices[0].message.content.strip()
            
            print("Qwen3:8B Output:")
            print("-" * 70)
            print(llm_output)
            print("-" * 70)
            
            return parse_and_display_results(llm_output)
            
        except Exception as e:
            print(f"Error with litellm: {e}")
            import traceback
            traceback.print_exc()
            print("\nFalling back to direct HTTP request...")
            return try_direct_ollama_request()
    else:
        print("litellm not available, trying direct HTTP request...")
        return try_direct_ollama_request()


def try_direct_ollama_request():
    """Try direct Ollama request using urllib."""
    import json
    import urllib.request
    import urllib.error
    
    print("\nAttempting direct Ollama request using urllib...")
    print("-" * 70)
    
    try:
        # Sample chunks to extract from
        sample_chunks = [
            "John Smith is a forward for the Lakers. He was born in Los Angeles.",
            "The Lakers are based in Los Angeles, California. They won the championship in 2020.",
            "John Smith has an average of 25 points per game. He is very talented.",
        ]
        
        # Attribute schema
        attr_schema = """name: Full name of the person
position: Playing position (e.g., Forward, Guard)
team: NBA team name
city: City where team is located
points_per_game: Average points scored per game"""
        
        # Create the extraction prompt
        extract_prompt = """CRITICAL INSTRUCTIONS:
You must output ONLY tuples in this exact format. Nothing else.
Each tuple must be on its own line.
Format: (attribute_name, attribute_value, confidence_score, chunk_id)

Example outputs:
(name, John Smith, 95, 0)
(position, Forward, 87, 1)
(team, Lakers, 92, 2)

Rules:
1. Attribute name: lowercase, from schema (e.g., name, position, team)
2. Attribute value: exact text from the chunk, preserve casing and spacing
3. Confidence: integer 0-100 (your confidence in the extraction)
4. Chunk ID: integer, the ID of the chunk where this came from

Do NOT output:
- Any text outside of tuples
- Markdown formatting
- Bullet points
- Headers
- Explanations
- Multiple tuples on one line
- Empty lines with text
- Any line that doesn't start with (

Only output valid tuples, one per line.

Schema:
```
{schema}
```

Chunks to extract from:
```
{chunks}
```""".format(
            schema=attr_schema,
            chunks="\n\n".join([f"Chunk_id {i}:\n{chunk}" for i, chunk in enumerate(sample_chunks)])
        )
        
        system_prompt = """You are a strict attribute extraction assistant.
ONLY output tuples in this format: (key, value, confidence, chunkid)
ONE tuple per line. Nothing else. No explanations. No extra text. No thinking. No markdown.
Each line must be a valid tuple starting with ( and ending with )."""
        
        # Make request to Ollama
        url = "http://localhost:11434/api/chat"
        payload = {
            "model": "qwen3:8b",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": extract_prompt}
            ],
            "stream": False,
            "temperature": 0,
        }
        
        print("Sending request to http://localhost:11434/api/chat...")
        print("Model: qwen3:8b")
        print("(This may take a minute or two...)")
        print()
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.loads(response.read().decode('utf-8'))
            llm_output = result.get("message", {}).get("content", "").strip()
        
        if not llm_output:
            print("No response from Ollama")
            return False
        
        print("Qwen3:8B Output:")
        print("-" * 70)
        print(llm_output)
        print("-" * 70)
        
        return parse_and_display_results(llm_output)
        
    except urllib.error.URLError as e:
        print(f"Error: Could not connect to Ollama at http://localhost:11434")
        print(f"Details: {e}")
        print("\nMake sure Ollama is running:")
        print("  ollama serve")
        print("\nAnd qwen3:8b is pulled:")
        print("  ollama pull qwen3:8b")
        return False
    except json.JSONDecodeError as e:
        print(f"Error decoding Ollama response: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def parse_and_display_results(llm_output):
    """Parse LLM output and display results."""
    print("\nParsing LLM output...")
    print("-" * 70)
    
    attr_names = ["name", "position", "team", "city", "points_per_game"]
    lines = llm_output.split("\n")
    
    valid_tuples = []
    invalid_lines = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        parsed = parse_xyz_with_chunkid(line, attr_names=attr_names)
        
        if parsed is None:
            invalid_lines.append((i, line))
            print(f"✗ Line {i} (INVALID): {line[:70]}")
        else:
            valid_tuples.append(parsed)
            print(f"✓ Line {i} (PARSED): {parsed}")
    
    print("-" * 70)
    print(f"\nSummary:")
    print(f"  Total lines: {len([l for l in lines if l.strip()])}")
    print(f"  Valid tuples: {len(valid_tuples)}")
    print(f"  Invalid lines: {len(invalid_lines)}")
    
    if valid_tuples:
        print(f"\nExtracted attributes:")
        for attr_name, attr_value, confidence, chunk_id in valid_tuples:
            print(f"  - {attr_name}: '{attr_value}' (confidence: {confidence}, chunk: {chunk_id})")
    
    if invalid_lines:
        print(f"\nInvalid lines (showing all {len(invalid_lines)}):")
        for line_no, line in invalid_lines:
            print(f"  - Line {line_no}: {line[:70]}")
    
    return True


if __name__ == "__main__":
    print("UDA-Bench LLM Output Parser Test Suite")
    print("=" * 70)
    
    # Run unit tests
    success = test_parse()
    
    # Run LLM generation test
    if success:
        llm_success = test_llm_generation()
        sys.exit(0 if llm_success else 1)
    else:
        sys.exit(1)


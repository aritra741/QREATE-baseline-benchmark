#!/usr/bin/env python3
"""
Test script to debug LLM tuple output format.
This isolates the LLM behavior without the full QUEST pipeline.
"""

import sys
from pathlib import Path

# Add project paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

from litellm import completion
import quest.conf.settings as settings

# Test schema - use the Finance schema that's causing problems
TEST_SCHEMA = """company_name: The official name of the company
bussiness_cost: Total business operating costs
bussiness_profit: Net profit of the business
bussiness_sales: Total sales revenue
business_segments_num: Number of business segments
business_risks: Key business risks identified"""

# Test chunks - simulate Finance document content
TEST_CHUNKS = [
    "WHEELER REAL ESTATE INVESTMENT TRUST, INC. (the 'Company') is a fully-integrated, self-managed commercial real estate investment company. Common Stock trades on NASDAQ Capital Market under symbol WHLR.",
    "For the fiscal year ended December 31, 2022, the Company reported total revenues of $89.4 million and net operating income of $52.1 million. Operating expenses were $37.3 million.",
    "The Company operates in 3 primary business segments: Retail Properties, Office Properties, and Development. Key risks include interest rate fluctuations and tenant defaults.",
    "Total assets as of December 31, 2022 were $423.8 million. The company employs approximately 127 full-time employees across its properties.",
]

# Construct the prompt
SYSTEM_PROMPT = """You are a strict attribute extraction assistant.
OUTPUT FORMAT - ONLY TUPLES:
(attribute_name, attribute_value, confidence, chunk_id)

CRITICAL - CONFIDENCE AND CHUNK_ID MUST BE NUMBERS:
✓ CORRECT: (company_name, Apple Inc, 95, 0)
✗ WRONG: (company_name, Apple Inc, High, chunk_0)

✓ CORRECT: (revenue, 394000000000, 87, 1)
✗ WRONG: (revenue, 394 billion, Medium, 1)

RULES:
1. Confidence = INTEGER 0-100 (NOT "High", "Medium", "Low")
2. Chunk ID = INTEGER (NOT "chunk_id_0", just 0)
3. One tuple per line, start with (
4. Extract ONLY the attributes listed in Schema
5. Output ONLY tuples - no explanations"""

# Build chunks section
chunks_section = ""
for i, chunk in enumerate(TEST_CHUNKS):
    chunks_section += f"\nChunk {i}: {chunk}"

USER_PROMPT = f"""EXTRACT ATTRIBUTES AND OUTPUT AS TUPLES.

SCHEMA - Extract ONLY these attributes:
{TEST_SCHEMA}

CHUNKS TO ANALYZE:
{chunks_section}

OUTPUT TUPLES NOW - use format (attribute_name, value, confidence, chunk_id):"""

# Call LLM
print("=" * 80)
print("TESTING LLM OUTPUT FORMAT")
print("=" * 80)
print(f"\nPrompt length: {len(USER_PROMPT)} chars")
print(f"\nSystem prompt:\n{SYSTEM_PROMPT}\n")
print(f"User prompt:\n{USER_PROMPT}\n")
print("=" * 80)
print("LLM RESPONSE:")
print("=" * 80)

try:
    response = completion(
        model=settings.GPT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT}
        ],
        max_tokens=1024,
        temperature=0,
        api_base=settings.GPT_API_BASE,
        think=False,
        num_predict=1024,
        options={
            "num_predict": 1024,
            "temperature": 0,
        }
    )
    
    result = response.choices[0].message['content'].strip()
    print(result)
    
    print("\n" + "=" * 80)
    print("ANALYSIS:")
    print("=" * 80)
    
    lines = result.split('\n')
    print(f"Total lines: {len(lines)}")
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # Check format
        if line.startswith('(') and line.endswith(')'):
            content = line[1:-1]
            parts = content.split(',')
            print(f"Line {i}: {len(parts)} fields - {line}")
        else:
            print(f"Line {i}: NOT A TUPLE - {line[:60]}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()


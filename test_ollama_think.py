#!/usr/bin/env python3
"""Test script to verify Ollama thinking mode is disabled."""

from litellm import completion

# Test the exact same call format as QUEST uses
print("Testing Ollama with think=False...")
print("=" * 60)

prompt = [
    {
        "role": "system",
        "content": "You are an information extraction assistant. CRITICAL: Output ONLY key-value pairs in the exact format 'field: value', one per line. Do NOT use <think> tags. Do NOT add explanations. Do NOT add reasoning. Just output the data."
    },
    {
        "role": "user",
        "content": """Extract the following fields from the given document: company_name.

Instructions:
- Format your response as lines, each in the format: `field: value`
- Use the exact field names: company_name
- If a field is missing or unknown, leave its value empty (e.g., `company_name: None`)
- use the line break (`\\n`)to split the lines
- Do not add any extra text, comments, or explanations
- Do NOT use <think> tags or reasoning steps

Document:
Apple Inc. is a technology company founded in 1976. The company designs and manufactures consumer electronics.
"""
    }
]

try:
    response = completion(
        model="ollama/qwen3:8b",
        messages=prompt,
        max_tokens=128,
        stop=None,
        temperature=0,
        api_base="http://localhost:11434",
        think=False,  # Disable thinking mode
        num_predict=128,
    )
    
    print("Response received:")
    print("-" * 60)
    print(response.choices[0].message.content)
    print("-" * 60)
    
    # Check if response contains thinking tags
    content = response.choices[0].message.content
    if "<think>" in content or "<think>" in content:
        print("\n❌ FAILED: Response contains thinking tags!")
    elif ":" in content and len(content.split("\n")) <= 5:
        print("\n✅ SUCCESS: Response looks like clean key-value pairs!")
    else:
        print("\n⚠️  WARNING: Response format unclear")
        print(f"Response length: {len(content)} chars")
        print(f"Number of lines: {len(content.split(chr(10)))}")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()



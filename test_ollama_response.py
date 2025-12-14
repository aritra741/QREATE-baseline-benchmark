#!/usr/bin/env python3
"""
Test script to check what Ollama is returning for basic LLM calls.
"""
import os
import sys
from openai import OpenAI

# Setup
api_key = "EMPTY"
base_url = "http://localhost:11434/v1"
model_name = "qwen2.5:7b-instruct"

print(f"Testing Ollama connection...")
print(f"API Base: {base_url}")
print(f"Model: {model_name}")
print("-" * 60)

try:
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    # Test 1: Simple completion
    print("\nTest 1: Simple text completion")
    print("Prompt: 'Hello, who are you?'")
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": "Hello, who are you?"}],
        temperature=0.1,
        max_tokens=100
    )
    print(f"Response type: {type(response)}")
    print(f"Response object: {response}")
    if response.choices:
        content = response.choices[0].message.content
        print(f"Content type: {type(content)}")
        print(f"Content: {content}")
    else:
        print("ERROR: No choices in response!")
    
    # Test 2: JSON response
    print("\n" + "=" * 60)
    print("\nTest 2: JSON response")
    json_prompt = """
    Respond with a JSON object in this format:
    {"answer": "yes or no", "reason": "brief reason"}
    
    Question: Is 2+2 equal to 4?
    """
    print(f"Prompt: {json_prompt[:100]}...")
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": json_prompt}],
        temperature=0.1,
        max_tokens=200
    )
    if response.choices:
        content = response.choices[0].message.content
        print(f"Content: {content}")
    else:
        print("ERROR: No choices in response!")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()


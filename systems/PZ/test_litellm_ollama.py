#!/usr/bin/env python
"""Test LiteLLM with Ollama"""

import sys
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main')
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main/systems/PZ/PZ_original/palimpzest/src')

import os
os.environ["LITELLM_DISABLE_STRICT_VALIDATION"] = "true"
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"

import litellm

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is 2+2?"},
]

try:
    response = litellm.completion(
        model="openai/qwen2.5:7b-instruct",
        messages=messages,
        api_base="http://localhost:11434/v1",
        api_key="sk-dummy",
    )
    print(f"Response type: {type(response)}")
    print(f"Response: {response}")
    if hasattr(response, 'choices'):
        print(f"First choice: {response.choices[0]}")
        print(f"Message: {response.choices[0].message}")
        print(f"Content: {response.choices[0].message.content}")
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()


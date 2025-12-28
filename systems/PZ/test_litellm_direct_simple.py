#!/usr/bin/env python
"""Test direct LiteLLM call with Ollama to bypass Palimpzest"""

import os
os.environ["LITELLM_DROP_PARAMS"] = "True"
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
os.environ["OPENAI_API_KEY"] = "sk-dummy-for-ollama"

import litellm
litellm.verbose = True

messages = [
    {
        "role": "system",
        "content": "You are a helpful assistant. Extract the disease_type field from the document and respond with ONLY a valid JSON object: {\"disease_type\": \"value\"}"
    },
    {
        "role": "user",
        "content": """Disease Name: Diabetes Mellitus
Disease Type: metabolic

Extract disease_type:"""
    }
]

try:
    response = litellm.completion(
        model="openai/qwen2.5:7b-instruct",
        messages=messages,
        api_base="http://localhost:11434/v1",
        api_key="sk-local-ollama-no-validation-needed",
    )
    print(f"\n✓ Response received!")
    print(f"Content: {response.choices[0].message.content}")
except Exception as e:
    print(f"✗ Error: {e}")


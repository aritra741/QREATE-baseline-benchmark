#!/usr/bin/env python3
"""Simple test to check Ollama response"""
from openai import OpenAI

client = OpenAI(api_key="EMPTY", base_url="http://localhost:11434/v1")

print("Testing qwen2.5:7b-instruct...")
try:
    response = client.chat.completions.create(
        model="qwen2.5:7b-instruct",
        messages=[{"role": "user", "content": "Say hello"}],
        temperature=0.1,
        max_tokens=50
    )
    print(f"Success! Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"Error with qwen2.5:7b-instruct: {e}")

print("\nTesting qwen3:8b...")
try:
    response = client.chat.completions.create(
        model="qwen3:8b",
        messages=[{"role": "user", "content": "Say hello"}],
        temperature=0.1,
        max_tokens=50
    )
    print(f"Success! Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"Error with qwen3:8b: {e}")



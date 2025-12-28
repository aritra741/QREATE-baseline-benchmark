#!/usr/bin/env python
"""Test Ollama directly with a simple prompt"""

import requests
import json

# Test direct Ollama API
ollama_url = "http://localhost:11434/api/generate"

test_doc = """Disease Name: Diabetes Mellitus
Disease Type: metabolic
Pathogenesis: metabolic disorder
Etiology: obesity, increased lipid levels, inflammation, insulin resistance
"""

payload = {
    "model": "qwen2.5:7b-instruct",
    "prompt": f"""Extract the disease type from this document:
{test_doc}

Answer: """,
    "stream": False,
    "raw": True,
}

try:
    response = requests.post(ollama_url, json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {data['response']}")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Failed to reach Ollama: {e}")


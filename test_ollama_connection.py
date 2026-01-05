#!/usr/bin/env python3
"""Quick test to check Ollama connectivity"""
import sys
import socket
import time

OLLAMA_HOST = "localhost"
OLLAMA_PORT = 11434

print(f"Testing Ollama connection to {OLLAMA_HOST}:{OLLAMA_PORT}...")

# Try socket connection first (faster)
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(2)

try:
    result = sock.connect_ex((OLLAMA_HOST, OLLAMA_PORT))
    sock.close()
    
    if result == 0:
        print("✓ Port 11434 is open - Ollama appears to be running")
        
        # Try to actually connect with OpenAI client
        try:
            from openai import OpenAI
            client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
            
            print("✓ Testing LLM connection (this may take a moment)...")
            response = client.chat.completions.create(
                model="qwen2.5:7b-instruct",
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=10
            )
            print(f"✓ LLM response received: {response.choices[0].message.content}")
        except Exception as e:
            print(f"✗ LLM connection failed: {e}")
            print("  - Is qwen2.5:7b-instruct model loaded?")
            print("  - Try: ollama pull qwen2.5:7b-instruct")
            sys.exit(1)
    else:
        print(f"✗ Port 11434 is NOT open - Ollama is not running")
        print("  Start with: ollama serve")
        sys.exit(1)
        
except socket.timeout:
    print(f"✗ Connection timeout - Ollama not responding")
    print("  Start with: ollama serve")
    sys.exit(1)
except Exception as e:
    print(f"✗ Connection error: {e}")
    sys.exit(1)

"""
Quick smoke test for qwen3:8b via Ollama with streaming.

Usage:
  ./venv/bin/python qwen_smoketest.py "Your question here"

Prerequisites:
  1) Ollama is running locally on http://localhost:11434
  2) Model pulled: ollama pull qwen3:8b
"""

import sys
from openai import OpenAI

BASE_URL = "http://localhost:11434/v1"
MODEL = "qwen3:8b"


def main():
    user_prompt = sys.argv[1] if len(sys.argv) > 1 else "Tell me a fun fact about the ocean."

    client = OpenAI(api_key="ollama", base_url=BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=200,
        stream=True,
    )

    content_chunks = []
    reasoning_chunks = []
    for chunk in stream:
        delta = chunk.choices[0].delta
        if hasattr(delta, "content") and delta.content:
            content_chunks.append(delta.content)
        if hasattr(delta, "reasoning") and delta.reasoning:
            reasoning_chunks.append(delta.reasoning)

    final_content = "".join(content_chunks).strip()
    if not final_content:
        # fallback to reasoning text if no content returned
        final_content = "".join(reasoning_chunks).strip()

    print("Response:")
    print(final_content or "<empty>")


if __name__ == "__main__":
    main()


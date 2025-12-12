#!/usr/bin/env python3
"""
Simple helper script to inspect the raw output format of the configured Qwen model.

Usage examples:

    # Raw prompt test:
    python scripts/inspect_qwen_output.py \
        --prompt "When did West Francia become the Kingdom of France?"

    # Test with the actual semantic parse prompt used by Unify:
    python scripts/inspect_qwen_output.py \
        --semantic-parse "When did West Francia become the Kingdom of France?"

This will call the local Ollama/OpenAI-compatible server (default base URL
http://localhost:11434/v1) with model "qwen3:8b" and print both the raw
response object and the extracted message content so you can check for
<think> blocks or any other formatting quirks.
"""
import argparse
import json
import os
import re
from openai import OpenAI


def get_semantic_parse_prompt(question):
    """The actual prompt used by Unify for semantic parsing"""
    prompt = f"""Please parse the following question and extract the entities, conditions, attributes, actions, and return type.


            ### Example 1:
            Question: "How many documents are related to boxing?"
            Output: {{
              "Entities": ["boxing"],
              "Conditions": ["related to boxing"],
              "Attributes": [],
              "Actions": [],
              "Return Type": "number"
            }}

            ### Example 2:
            Question: "Which type of movies is most discussed among movies that involve sports, movies that involve love, and movies that involve crimes?"
            Output: {{
              "Entities": ["movies", "movies", "movies", "movies"],
              "Conditions": ["involve sports", "involve love", "involve crimes"],
              "Attributes": [],
              "Actions": ["most discussed"],
              "Return Type": "type of movie"
            }}

            ### Example 3:
            Question: "From documents with over 10,000 views, identify the ball sport with the highest ratio of injury-related to training-related documents."
            Output: {{
              "Entities": ['ball sport'],
              "Conditions": ['over 10,000 views', 'injury-related', 'training-related'],
              "Attributes": [],
              "Actions": ['highest ratio'],
              "Return Type": "ball sport"
            }}

            ### Example 4:
            Question: "Documents related to running"
            Output: {{
              "Entities": ["running"],
              "Conditions": ["related to running"],
              "Attributes": [],
              "Actions": [],
              "Return Type": "documents"
            }}

            ### Example 5:
            Question: "When did West Francia become the Kingdom of France?"
            Output: {{
              "Entities": ["West Francia", "Kingdom of France"],
              "Conditions": [],
              "Attributes": [],
              "Actions": ["become"],
              "Return Type": "time"
            }}


            Now, please process the following question like above examples. 

            Question: "{question}"

            Provide the output in JSON format as:
            {{
              "Entities": [...],
              "Conditions": [...],
              "Attributes": [...],
              "Actions": [...],
              "Return Type": "..."
            }}

            Output ONLY the JSON, no explanations or reasoning.
            Rules:
              - "documents" do not need to be parsed as "Entities".
              - "related to [xxx]" should always be parsed as "Conditions".
              - If there is "ball sport" in the question and no other specific ball sports, "ball sport" should be parsed as "Entities".
/no_think"""
    return prompt


def clean_llm_response(response):
    """Clean LLM response by removing <think>...</think> tags."""
    if response is None:
        return response
    
    # Remove complete <think>...</think> tags and their content (handles multiline)
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    
    # Also remove incomplete <think> blocks (when model runs out of tokens before closing)
    cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL)
    
    # Strip leading/trailing whitespace
    cleaned = cleaned.strip()
    
    return cleaned


def extract_json_from_response(response):
    """Extract JSON from a response that may contain extra text."""
    if not response:
        return None
    
    # Find the first { and try to match balanced braces
    start_idx = response.find('{')
    if start_idx == -1:
        return None
    
    # Find matching closing brace by counting
    brace_count = 0
    end_idx = start_idx
    for i in range(start_idx, len(response)):
        if response[i] == '{':
            brace_count += 1
        elif response[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i + 1
                break
    
    try:
        return json.loads(response[start_idx:end_idx])
    except json.JSONDecodeError:
        return None


def parse_args():
    parser = argparse.ArgumentParser(description="Inspect raw Qwen response output.")
    parser.add_argument(
        "--prompt",
        type=str,
        help="Raw prompt/question to send to the model.",
    )
    parser.add_argument(
        "--semantic-parse",
        type=str,
        help="Question to test with the actual semantic parse prompt used by Unify.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("UNIFY_LLM_MODEL", "qwen3:8b"),
        help="Model name to use (default: qwen3:8b).",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        default=os.environ.get("UNIFY_LLM_BASE_URL", "http://localhost:11434/v1"),
        help="OpenAI-compatible base URL (default: http://localhost:11434/v1).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("UNIFY_LLM_API_KEY", "EMPTY"),
        help="API key (default: EMPTY, as used by Ollama).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Sampling temperature (default: 0.1).",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=0.9,
        help="Top-p sampling value (default: 0.9).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help="Maximum tokens in the response (default: 1024).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    if not args.prompt and not args.semantic_parse:
        print("Error: Either --prompt or --semantic-parse is required")
        return

    client = OpenAI(
        api_key=args.api_key,
        base_url=args.api_base,
    )

    # Determine which prompt to use
    if args.semantic_parse:
        prompt = get_semantic_parse_prompt(args.semantic_parse)
        print("=== Testing Semantic Parse Prompt ===")
        print(f"Question: {args.semantic_parse}")
    else:
        prompt = args.prompt
        print("=== Testing Raw Prompt ===")
        print(f"Prompt: {args.prompt}")
    
    print(f"\nModel       : {args.model}")
    print(f"Base URL    : {args.api_base}")
    print(f"Temperature : {args.temperature}")
    print(f"Top-p       : {args.top_p}")
    print(f"Max tokens  : {args.max_tokens}")
    print()

    response = client.chat.completions.create(
        model=args.model,
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        messages=[
            {"role": "user", "content": prompt},
        ],
    )

    message_content = response.choices[0].message.content
    
    print("=== Raw Message Content ===")
    print(message_content)
    print()
    
    print("=== After clean_llm_response() ===")
    cleaned = clean_llm_response(message_content)
    print(cleaned)
    print()
    
    if args.semantic_parse:
        print("=== JSON Extraction Result ===")
        json_result = extract_json_from_response(cleaned)
        if json_result:
            print(json.dumps(json_result, indent=2))
        else:
            print("FAILED to extract JSON!")
            print("This is why semantic parsing returns None.")


if __name__ == "__main__":
    main()


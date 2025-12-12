import re
import json
from prompts import get_semantic_parse_prompt
from utils.llm_config import clean_llm_response


def extract_json_from_response(response):
    """
    Extract JSON from a response that may contain extra text.
    Handles cases where models output explanatory text before/after JSON.
    """
    if not response:
        return None
    
    # Try to find JSON object in the response
    # Look for content between { and }
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # Try finding JSON with arrays in values
    json_match = re.search(r'\{[\s\S]*?"Entities"[\s\S]*?\}', response, re.DOTALL)
    if json_match:
        # Find the matching closing brace
        text = json_match.group()
        brace_count = 0
        end_idx = 0
        for i, char in enumerate(text):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
        try:
            return json.loads(text[:end_idx])
        except json.JSONDecodeError:
            pass
    
    # Last resort: try parsing the whole response
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return None


def semantic_parse(question, client, chatModel):
    prompt = get_semantic_parse_prompt(question)
    # Set up the messages for the LLM
    past_messages = [{"role": "user", "content": prompt}]
    # Call the LLM
    response = chatModel.create_completion(client, messages = past_messages)
    
    # Clean the response to remove <think> tags from models like qwen3
    response = clean_llm_response(response)

    # Parse the response as JSON (with robust extraction)
    parsed_output = extract_json_from_response(response)
    
    if parsed_output:
        # if documents or document is in parsed_output["Entities"], remove it
        if "Entities" in parsed_output:
            if "documents" in parsed_output["Entities"]:
                parsed_output["Entities"].remove("documents")
            if "document" in parsed_output["Entities"]:
                parsed_output["Entities"].remove("document")
    else:
        print("Failed to parse LLM response as JSON.")
        print(f"Response was: {response[:500] if response else 'None'}...")

    return parsed_output


def semantic_parse_without_client(question, client, chatModel):
    prompt = get_semantic_parse_prompt(question)
    message = [{"role": "user", "content": prompt}]

    response = chatModel.create_completion(client, max_tokens = 4000, messages = message)
    
    # Clean the response to remove <think> tags from models like qwen3
    response = clean_llm_response(response)

    # Parse the response as JSON (with robust extraction)
    parsed_output = extract_json_from_response(response)
    
    if parsed_output:
        # if documents or document is in parsed_output["Entities"], remove it
        if "Entities" in parsed_output:
            if "documents" in parsed_output["Entities"]:
                parsed_output["Entities"].remove("documents")
            if "document" in parsed_output["Entities"]:
                parsed_output["Entities"].remove("document")
    else:
        print("Failed to parse LLM response as JSON.")
        print(f"Response was: {response[:500] if response else 'None'}...")

    return parsed_output

def replace_parsed_elements_with_identifiers(question, parsed_result):
    """
    Replace the parsed elements in the question with their respective identifiers.
    """
    if not parsed_result:
        return question  # In case parsing failed, return the original question

    # Replacements for different categories
    # IMPORTANT: Replace Conditions FIRST (longer strings) before Entities
    # Otherwise "Football" gets replaced before "related to Football" can match
    replacements = [
        ("Conditions", "[Condition]"),
        ("Entities", "[Entity]"),
    ]
    # Replace the parsed elements in the question with their identifiers
    transformed_question = question
    for category, identifier in replacements:
        if category in parsed_result:
            for element in parsed_result[category]:
                # Escape special regex characters in the entity
                escaped_element = re.escape(element)
                # Replace the element in the question, ignoring case
                transformed_question = re.sub(rf"\b{escaped_element}\b", identifier, transformed_question,
                                                flags=re.IGNORECASE)

    return transformed_question


# Example usage
if __name__ == "__main__":
    question = "Which type of sport is most discussed between sports that require a field and sports that do not require a specific field?"
import re
from utils.contextManager import LLMContextManager
from semanticParse import semantic_parse, replace_parsed_elements_with_identifiers, BQMatcher
from prompts import *
from utils.llm_config import clean_llm_response

# Number placeholders
# For example:
# Input: Which type of [Entity] is most discussed between [Entity] that [Condition] and [Entity] that [Condition]?
# Output: Which type of [Entity1] is most discussed between [Entity2] that [Condition1] and [Entity3] that [Condition2]?
def numbering_placeholders(query):
    # Use a regular expression to find all placeholders in the query
    # Define a dictionary to keep track of the counts for each placeholder category
    placeholder_counts = {} 

    # Define a function to replace each placeholder with its numbered version
    def replace_placeholder(match):
        placeholder = match.group(0)
        category = placeholder[1:-1]  # Extract the category name without the brackets
        # category = re.match(r'\[(\w+)\]', placeholder).group(1)
        if category not in placeholder_counts:
            placeholder_counts[category] = 0
        placeholder_counts[category] += 1
        return f"[{category}{placeholder_counts[category]}]"

    # Use regular expression to find and replace all placeholders
    transformed_query = re.sub(r'\[.*?\]', replace_placeholder, query)
    # transformed_query = re.sub(r'\[\w+\]', replace_placeholder, query)
    return transformed_query


# Create a query with placeholders, and map each placeholder to the original query
def map_placeholders_to_original(template_question, original_question):
    """
    Map placeholders in a template question to corresponding text in the original question.
    
    Improved robustness:
    - Handles cases where template parts don't appear in original question
    - Returns empty string instead of None for unmatched placeholders
    - Logs debugging info for troubleshooting
    """
    # Step 1: Extract placeholders from the template question
    placeholders = re.findall(r'\[([A-Za-z]+\d+)\]', template_question)
    
    # Step 2: Split both questions by placeholders
    template_parts = re.split(r'\[([A-Za-z]+\d+)\]', template_question)
    
    # The original question is split using the same template parts
    # This allows us to find the parts corresponding to each placeholder
    parts = []
    last_index = 0
    for part in template_parts:
        if part:  # Skip empty parts
            index = original_question.find(part, last_index)
            if index != -1:
                if last_index < index:
                    extracted = original_question[last_index:index].strip()
                    if extracted:  # Only add non-empty parts
                        parts.append(extracted)
                last_index = index + len(part)
    
    # Append any remaining text after the last placeholder
    if last_index < len(original_question):
        remaining = original_question[last_index:].strip()
        if remaining:
            parts.append(remaining)
    
    # Step 3: Create the mapping between placeholders and original text
    mapping = {}
    for i, placeholder in enumerate(placeholders):
        if i < len(parts):
            mapping[placeholder] = parts[i]
        else:
            # Use empty string instead of None to avoid type errors downstream
            # Add the placeholder name as fallback for debugging
            mapping[placeholder] = f"[{placeholder}]"
    
    return mapping

def check_prerequisites_with_llm(client, chatModel, original_question, parsed_question, bq):
    prompt = check_prerequisite_prompt(original_question,parsed_question, bq)
    ctxManager = LLMContextManager()
    ctxManager.add_user_message(prompt)
    response = chatModel.create_completion(
        client,
        temperature=0.1,
        top_p=0.9,
        max_tokens=500,  # Increased for reasoning models like qwen3 that output <think> blocks
        messages=ctxManager.get_messages()
    )
    # Clean the response to remove <think> tags from models like qwen3
    response = clean_llm_response(response).strip()

    return response.lower() == "true"

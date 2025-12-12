import time
from openai import OpenAI
from utils.contextManager import LLMContextManager
from semanticParse import semantic_parse, replace_parsed_elements_with_identifiers, BQMatcher
from embed import EmbedModel
import json
import copy
from PlanManager import planManager, update_current_question
from chunk import load_process_data_chunks, ChunkExtractor
import os
import re
from index import indexHNSW
from prompts import *
from utils.placeholders import *
from utils.llm_config import ModelConfig, DEBUG_MODEL_CONFIG, clean_llm_response
import argparse
import logging
from datetime import datetime

os.environ["CUDA_VISIBLE_DEVICES"] = "0"


def setup_logging(log_file=None):
    """
    Set up logging to both console and file.
    
    Args:
        log_file: Path to log file. If None, creates a timestamped log file.
    
    Returns:
        Path to the log file being used.
    """
    if log_file is None:
        # Create logs directory if it doesn't exist
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        # Generate timestamped log file name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"unify_{timestamp}.log")
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers = []
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                  datefmt='%Y-%m-%d %H:%M:%S')
    
    # File handler
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    logging.info(f"Logging initialized. Log file: {log_file}")
    return log_file


def extract_json_from_response(response):
    """
    Extract JSON object from a response that may contain extra text.
    Handles cases where reasoning models output explanatory text before/after JSON.
    """
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
        # Fallback: try to parse the whole response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None


# Use a basic question to do reduce
def apply_basic_question_reduction(original_question, parsed_question, basic_question, client, chatModel, embed_model):
    PROMPT = apply_BQ_prompt(original_question, parsed_question,  basic_question["Question"], basic_question["Return"], embed_model)

    ctxManager = LLMContextManager()
    ctxManager.add_user_message(PROMPT)

    messages=ctxManager.get_messages()
    response = chatModel.create_completion(client, messages=messages)
    
    # Clean the response to remove <think> tags from models like qwen3
    response = clean_llm_response(response)
    
    try:
        response_json = extract_json_from_response(response)
        
        if response_json is None:
            logging.error("Failed to extract JSON from LLM response.")
            logging.error("The LLM response is:")
            logging.error("#" * 50)
            logging.error(response[:1000] if response else "None")
            logging.error("#" * 50)
            return None

        if response_json.get("transformed_original_query") == original_question:
            response_json["fully_solved"] = False
            response_json["partially_solved"] = False
            response_json["transformed_original_query"] = "No"
            response_json["sub_problems"] = "No"
            response_json["transformed_parsed_query"] = "No"
        
        if response_json.get("transformed_original_query") == "sub_problems":
            assert isinstance(response_json.get("sub_problems"), list) and len(response_json["sub_problems"]) > 0
        else:
            response_json["sub_problems"] = "No"  

        return response_json
    except json.JSONDecodeError:
        logging.error("Failed to parse LLM response as JSON.")
        logging.error("The LLM response is:")
        logging.error("#" * 50)
        logging.error(response[:1000] if response else "None")
        logging.error("#" * 50)
        return None
    except Exception as e:
        logging.error(f"Unexpected error during basic question reduction: {e}")
        return None


# Determine if a question is simple
def if_simple_question(original_question, parsed_question, client, chatModel):
    """
    Use an LLM to determine if the question is simple based on its original and parsed forms.

    Args:
        original_question (str): The original user query.
        parsed_question (str): The semantically parsed query.
        client: OpenAI client for API calls.
        chatModel: Model configuration for LLM interaction.

    Returns:
        bool: True if the question is simple, False otherwise.
    """

    PROMPT = f"""
    You are tasked with determining whether a given question is simple based on its parsed form.
    A question is considered simple if its parsed form exactly matches one of the following
    return types from predefined Logical Representations (LRs):
    - [Entity] (e.g., a single entity like a sport or category)
    - [Number] (e.g., a count of documents)
    - Boolean (e.g., True/False)
    - documents (e.g., a filtered set of documents)
    - Ratio (e.g., a computed ratio)
    - ComputedValue (e.g., a computed value like a sum)
    - [Condition] (e.g., a single condition)
    - [Attribute] (e.g., a single attribute)
    - Groups (e.g., grouped data)
    - [Action] (e.g., a single action)
    - Dictionary (e.g., a dictionary of values)

    **Important**: Patterns like "Documents with [Condition]" are **not** simple because they include
    a condition that requires further processing. A question is only simple if it is fully reduced
    to a standalone type like "documents".  

    Given the original question: "{original_question}"
    And its parsed form: "{parsed_question}"

    Does the parsed question exactly match one of the listed LR return types? 
    Respond with exactly "True" or "False".
    """
    # Initialize context manager and add the prompt
    ctxManager = LLMContextManager()
    ctxManager.add_user_message(PROMPT)
    # Call the LLM
    try:
        response = chatModel.create_completion(
            client,
            temperature=0.1,
            top_p=0.9,
            max_tokens=500,  # Increased for reasoning models like qwen3 that output <think> blocks
            messages=ctxManager.get_messages()
        )
        
        # Clean the response to remove <think> tags from models like qwen3
        response = clean_llm_response(response).strip()
        
        # Parse the response
        if response.lower() == "true":
            return True
        elif response.lower() == "false":
            return False
        else:
            logging.warning(f"Invalid LLM response for simplicity check: {response}. Defaulting to False.")
            return False
    except Exception as e:
        logging.error(f"Error during LLM simplicity check: {e}. Defaulting to False.")
        return False

# Sort the results using different BQs, based on fully_solved > partially_solved > no_solution
def get_sorted_results(result_json_list):
    indexed_result_json_list = list(enumerate(result_json_list))
    indexed_result_json_list.sort(key=lambda x: (x[1]["fully_solved"], x[1]["partially_solved"]), reverse=True)
    return indexed_result_json_list

# Use a BQ to reduce a question
def process_basic_question(original_question, parsed_question, basic_question, client, chatModel, embed_model):
    return apply_basic_question_reduction(original_question, parsed_question, basic_question, client, chatModel, embed_model)


# 【new version】
def update_plan_and_lists(current_plan, use_BQ_list, partial_question_list, matchedBQ, result_json, current_question, formatted_original_question, client, chatModel):
    nxt_plan = copy.deepcopy(current_plan)
    nxt_BQ_list = copy.deepcopy(use_BQ_list)
    nxt_partial_question_list = copy.deepcopy(partial_question_list)

    current_bq = matchedBQ[result_json[0]]
    current_bq_id = current_bq["IDQuestion"]
    nxt_plan.append(matchedBQ[result_json[0]]["Plan"]) 
    nxt_BQ_list.append(matchedBQ[result_json[0]])

    nxt_partial_question_list.append(formatted_original_question)

    return nxt_plan, nxt_BQ_list, nxt_partial_question_list

def recursive_plan_generation(origin_question, question, BQMatcher, client, chatModel, embed_model, current_plan, use_BQ_list, partial_question_list, depth=0):
    """

    :param origin_question:
    :param question:
    :param BQMatcher:
    :param client:
    :param current_plan:
    :param use_BQ_list:
    :param partial_question_list:
    :param depth:
    :return:
    """
    logging.info(f"{'--' * depth}Current question: {question}  Current plan {current_plan}")
    logging.info("Current used BQ_list: ")
    for bq in use_BQ_list:
        logging.info(f"  {bq['Question']}")
    logging.info("")


    # Check if it is a simple problem
    if if_simple_question(origin_question, question, client, chatModel):
        logging.info("Simple question reached, return current plan")
        return True, current_plan, use_BQ_list, partial_question_list

    if depth >=4 :
        logging.warning("Maximum recursion depth reached, returning current plan.")
        return False, current_plan, use_BQ_list, partial_question_list

    logging.info(f"\n{'--' * depth}Processing Question at Depth {depth}: 【 {question} 】")
    # print the path till now
    logging.info("====== Current used BQ list ======")
    for bq in use_BQ_list:
        logging.info(f"  {bq['Question']}")
    logging.info("")

    matchedBQ = BQMatcher.match(question, topK=3)

    result_json_list = []

    for bq in matchedBQ:
        
        result_json = process_basic_question(origin_question, question, bq, client, chatModel, embed_model)
        if result_json:
            result_json_list.append(result_json)
    if not result_json_list:
        logging.warning("No valid reduction found, returning current plan.")
        return False, current_plan, use_BQ_list, partial_question_list

    sorted_results = get_sorted_results(result_json_list)

    # output sorted results
    logging.info("==== Sorted results ====")
    def get_solve_degree(result_json):
        if result_json[1]["fully_solved"]:
            return "fully_solved"
        elif result_json[1]["partially_solved"]:
            return "partially_solved"
        return None
    for i, result_json in enumerate(sorted_results):
        solve_degree = get_solve_degree(result_json)
        if solve_degree is not None:
            reduce_to_query = result_json[1]["transformed_original_query"]
            if result_json[1]["transformed_original_query"] == "sub_problems":
                reduce_to_query = result_json[1]["sub_problems"]
            logging.info(f"   {result_json[0]}, {solve_degree},  -- BQ : {matchedBQ[result_json[0]]['Question']},   reduce to: 【{reduce_to_query}】")
        else:
            logging.info(f"   {result_json[0]}, not able to solve,  BQ is:  {matchedBQ[result_json[0]]['Question']}")

    global_plan = copy.deepcopy(current_plan)
    global_BQ_list = copy.deepcopy(use_BQ_list)
    global_partial_question_list = copy.deepcopy(partial_question_list)

    for i, result_json in enumerate(sorted_results):
        if result_json[1]["fully_solved"] or result_json[1]["partially_solved"]:

            nxt_original_question = result_json[1]["transformed_original_query"]
            if nxt_original_question == "sub_problems":
                all_sub_success = True
                for sub_idx, sub_problem in enumerate(result_json[1]["sub_problems"]):
                    logging.info(f"\n{'  '*depth}Processing sub-problem {sub_idx+1}/{len(result_json[1]['sub_problems'])}:")
                    logging.info(f"{'  '*depth}Sub-problem: {sub_problem}")
                    parsed_result = semantic_parse(sub_problem, client, chatModel)
                    
                    nxt_question = replace_parsed_elements_with_identifiers(sub_problem, parsed_result)
                    
                    # Recursively process sub-problems
                    sub_flag, final_sub_plan, final_sub_BQ, final_sub_questions = recursive_plan_generation(
                        sub_problem, nxt_question, BQMatcher, client, chatModel, embed_model,
                        global_plan, global_BQ_list, global_partial_question_list, depth + 1
                    )
                   
                    if sub_flag:
                        # Merge the results of sub-problems
                        global_plan = final_sub_plan
                        global_BQ_list = final_sub_BQ
                        global_partial_question_list = final_sub_questions
                    else:
                        all_sub_success = False
                        logging.warning(f"{'  '*depth}Sub-problem {sub_idx+1} failed, aborting branch")
                        break  # If any sub-problem fails, terminate the current branch
                if all_sub_success:
                    # Return the merged results when all sub-problems are solved
                    logging.info(f"{'  '*depth}All sub-problems solved successfully")
                    return True, global_plan, global_BQ_list, global_partial_question_list
                else:
                    logging.warning(f"{'  '*depth}Some sub-problems failed, trying next candidate")
                    continue  # Continue to try other candidate solutions

            else:
                # nxt_question needs to be parsed by nxt_original_question
                parsed_result = semantic_parse(nxt_original_question, client, chatModel)
                nxt_question = replace_parsed_elements_with_identifiers(nxt_original_question, parsed_result)

                formatted_original_question = nxt_original_question

                # Recursively process the next question
                # The current_plan is the current plan, and the use_BQ_list is the current BQ list
                global_plan, global_BQ_list, global_partial_question_list = update_plan_and_lists(
                    current_plan, use_BQ_list, partial_question_list, matchedBQ, result_json, nxt_question, formatted_original_question, client, chatModel
                )

                flag, plan, BQ_list, question_list = recursive_plan_generation(
                    nxt_original_question, nxt_question, BQMatcher, client, chatModel, embed_model, global_plan, global_BQ_list, global_partial_question_list,  depth + 1
                )
            if flag:
                numbered_question = numbering_placeholders(question)
                mapping = map_placeholders_to_original(numbered_question, origin_question)
                logging.info(f"# Q before numbering:  {question}")
                logging.info(f"# Q after numbering:  {numbered_question}")
                logging.info(f"# Current original Q: {origin_question}")
                logging.info("### see mapping")
                logging.info(str(mapping))
                return flag, plan, BQ_list, question_list
    logging.warning("No valid reduction found, returning current plan.")
    return False, current_plan, use_BQ_list, partial_question_list

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="Unify script with dynamic path parameters")
    parser.add_argument("--llm_model_path", type=str, default="qwen3:8b", help="Ollama model name (e.g., qwen3:8b)")
    parser.add_argument("--tokenizer_path", type=str, default="/path/to/your/tokenizer", help="Path to the tokenizer model")
    parser.add_argument("--sentence_model_path", type=str, default="/path/to/your/Embedding Model", help="Path to the sentence transformer model")
    parser.add_argument("--api_key", type=str, default="EMPTY", help="Set OpenAI's API key")
    parser.add_argument("--api_base", type=str, default="http://localhost:11434/v1", help="Set OpenAI's API base URL (Ollama default)")
    parser.add_argument("--doc_path", type=str, default="/path/to/your/data/", help="Path to the document dataset")
    parser.add_argument("--query", type=str, default="your query", help="Query string")
    parser.add_argument("--log_file", type=str, default=None, help="Path to log file (default: logs/unify_TIMESTAMP.log)")

    # Parse command line arguments
    args = parser.parse_args()
    
    # Set up logging
    log_file = setup_logging(args.log_file)
    
    # Set OpenAI API key and base URL
    client = OpenAI(
        api_key=args.api_key,
        base_url=args.api_base,
    )
    # Initialize the LLM model
    chatModel = ModelConfig(args.llm_model_path)

    # Initialize the embedding model
    embedModel = EmbedModel(tokenizer_path=args.tokenizer_path, sentence_model_path=args.sentence_model_path)
    
    # Set the query and data path
    question = args.query
    doc_path = args.doc_path

    st_time = time.time()

    ##############  The following part is for parsing the query and transforming the query  ################
    # Step 1: Parse the question
    parsed_result = semantic_parse(question, client, chatModel)

    # Step 2: Replace parsed elements in the question with their identifiers
    transformed_question = replace_parsed_elements_with_identifiers(question, parsed_result)

    # Output the transformed question
    logging.info(f"### Original Question:\n{question}")
    logging.info(f"### Transformed Question:\n{transformed_question}")
    logging.info("### See parsed results")
    logging.info(str(parsed_result))
    logging.info("")

    BQMatcher = BQMatcher(embedModel)

    ##############  The following part is for generating the plan  ################

    final_flag, final_plan, final_BQ_list, partial_question_list = recursive_plan_generation(question, transformed_question, BQMatcher, client, chatModel, embedModel,
                                                                      current_plan=[],
                                                                      use_BQ_list=[],
                                                                      partial_question_list=[],
                                                                      depth=0)


    logging.info(f"Finally the plan is successfully selected: {final_flag}")
    logging.info(f"The final plan is:\n{final_plan}")
    logging.info("The final BQ list is:")
    for bq in final_BQ_list:
        logging.info(str(bq))

    logging.info("#"*50)

    ######################    The following part is for the doc related part   ######################

    # chunk, embedding, index
    chunkExtractor = ChunkExtractor()
    
    # Read data and process it into chunks
    all_file_data, all_chunks, all_ids, all_embeds, all_chunk_locs = load_process_data_chunks(embedModel,
                                                                                              chunkExtractor, doc_path)
    # Build the index
    index = indexHNSW(all_chunks, all_embeds, all_ids, all_chunk_locs)

    ######################    The following part is for parsing and executing the query (using planManager)   ######################

    PM = planManager(question, final_plan, client, chatModel, final_BQ_list, all_file_data, parsed_result, partial_question_list,
                     embedModel, index)

    logging.info("======== Plan time ========")
    planTime = time.time() - st_time
    logging.info(str(planTime))

    # Execute the query with the plan
    PM.execute_with_plan()

    logging.info("Final IDPlan:")
    if PM.BQ_list:
        logging.info(str(PM.BQ_list[0].get("IDPlan", "No IDPlan found for the first BQ.")))
    else:
        logging.info("No IDPlan generated.")

    # Use the final item in BQ_list, whose 'result' of the root node in its 'IDPlan' as the result
    logging.info("Final result:")
    if PM.BQ_list and "IDPlan" in PM.BQ_list[-1] and PM.BQ_list[-1]["IDPlan"]:
        # Check if IDPlan has content
        if PM.BQ_list[-1]["IDPlan"]:
            logging.info(str(PM.BQ_list[-1]["IDPlan"][0].get("Result", "No Result found.")))
        else:
            logging.info("IDPlan is empty.")
    else:
        logging.info("No final result available.")


    logging.info("======== Total time ========")
    logging.info(str(time.time() - st_time))
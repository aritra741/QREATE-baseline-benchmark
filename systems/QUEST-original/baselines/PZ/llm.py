import openai
import os
import random
from datetime import datetime
import time

# Function to initialize the OpenAI API
def init_chatgpt(api_key):
    openai.api_key = api_key
    openai.api_base = "https://api.xiaoai.plus/v1"

# Function to split text into smaller chunks
def split_text(text, max_chunk_size=15900):
    chunks = []
    while len(text) > max_chunk_size:
        idx = text.rfind(' ', 0, max_chunk_size)
        if idx == -1:
            idx = max_chunk_size
        chunks.append(text[:idx])
        text = text[idx:]
    chunks.append(text)
    return chunks

from openai.error import APIError, RateLimitError, ServiceUnavailableError, Timeout

def ask_completion_with_retry(messages, model, max_tokens=1000, n=1, stop=None, temperature=0, retries=3, delay=5):
    attempt = 0
    while attempt < retries:
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                n=n,
                stop=stop,
                temperature=temperature
            )
            # 返回响应结果
            return response.choices[0].message['content'].strip()
        except (APIError, RateLimitError, ServiceUnavailableError, Timeout) as e:
            print(f"Request failed: {e}. Retrying in {delay} seconds...")
            attempt += 1
            time.sleep(delay)
    raise Exception(f"Failed after {retries} retries.")

def ask_completion4filtercond(attribute, filter_cond, text):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"""
        Given the attribute: {attribute}
        Given the filter condition: {filter_cond}
        Given the text: {text}
        Task: Based on the above attribute, filter_cond and text, 
        extract the corresponding attributes from the text. 
        If an attribute is not found, leave it empty.
        And get the filter_cond's bool value with the text.
        
        ### If an attribute is not found, leave it empty.
        ### Format the output as follows:
        [true|false]
        """}
    ]
    
    return ask_completion_with_retry(messages, model="gpt-4o", max_tokens=1000)
def ask_completion4filtercondANDattr(attributes, filter_conds, text):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"""
        The current year is 2024.
        Given: 
        - Filter conditions: {filter_conds}  
        - Attributes: {attributes}  
        - Text: {text}  
        Task:
        1. Extract attributes from the text; set as 'NAN' if not found.  
        2. Evaluate each filter_cond; set as 'NAN' if it cannot be determined from the text.  
        Output Format: 
        [filter_cond1]:[true|false|NAN]##[filter_cond2]:[true|false|NAN]##...##[filter_condn]:[true|false|NAN]$$[attribute_name1]:[attribute_value]##[attribute_name2]:[attribute_value]##...##[attribute_namen]:[attribute_value]
        Instructions:  
        - Follow the output format exactly; no additional text.  
        - Use 'NAN' for missing attributes or unevaluated conditions.  
        - Evaluate filter conditions first, then extract attributes.  
        Example Output:  
        court_name = 'Federal Court':true##judgment_year >= 2009:true$$court_name:Federal Court##judge_name:Honourable Justice Collier##judgment_year:2009##plaintiff:Horizontal Falls Adventure Tours Pty Ltd (ACN 108 455 410)##defendant:Mr Troy Thomas, Mr Rhys Thomas##hearing_year:2009##charges:NAN##verdict:NAN##legal_basis:Part A para 7 of the application##appeal_information:NAN  
        Important:  
        - If the output format cannot be followed, return 'ERROR: OUTPUT NOT IN REQUIRED FORMAT'.
        """}
    ]
    
    return ask_completion_with_retry(messages, model="gpt-4o", max_tokens=1000)

def ask_completion4attribute(attribute, text):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"""
        This year is 2024.
        Given the attribute: {attribute}
        Given the text: {text}
        Task: Based on the above attribute and text, 
        extract the corresponding attributes from the text. 
        If an attribute is not found, leave it empty.
        
        ### If an attribute is not found, leave it empty.
        ### Format the output as follows, only one attribute, one value:
        [atrribute_name]:[attribute_value]
        """}
    ]
    
    return ask_completion_with_retry(messages, model="gpt-4-turbo", max_tokens=1000)

def ask_completion4Multattribute(attributes, text):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"""
        The current year is 2024.
        You are given a list of attributes: {attributes}
        You are also given the following text: {text}
        
        Task: For each attribute in the list, extract the corresponding value from the text.
        If an attribute's value cannot be found, set it as 'NAN'.
        
        Output format:
        attribute1: value1##attribute2: value2##attribute3: NAN...
        
        Ensure that each attribute and its value are seperate by '##' and if the attribute is not found in the text, output 'NAN' as the value.
        """}
    ]
    
    return ask_completion_with_retry(messages, model="gpt-4o", max_tokens=1000)


def ask_completion4tabledata(data1, data2):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"""
        Given the following two pieces of data:

        Data1: {data1}
        Data2: {data2}

        Task: Determine whether Data1 and Data2 refer to the same information. The comparison should be based on similarity, not exact matching.
                
        ### Format the output as follows, only one attribute, one value:
        [true|false]
        """}
    ]
    
    return ask_completion_with_retry(messages, model="gpt-4o", max_tokens=1000)
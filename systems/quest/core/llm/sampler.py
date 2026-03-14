import re
import pandas as pd
from litellm import completion, batch_completion
from tqdm import tqdm
import tiktoken
import os
import logging
import quest.conf.settings as settings
import copy
import random
from quest.core.llm.llm_query import LLMInfo
import numpy as np

import re

from quest.db.indexer.single_indexer import SingleIndexer, TextDocIndexer
from quest.core.nlp.text_cluster import faiss_kmeans_clustering

def extract_attr_descriptions_from_schema(attr_schema):
    # Extract attribute descriptions from schema string
    attr_descriptions = []
    lines = attr_schema.strip().split('\n')
    for line in lines:
        line = line.strip()
        if ':' in line:
            # Extract description after colon
            attr_description = line.split(':')[1].strip()
            if attr_description:
                attr_descriptions.append(attr_description)
    return attr_descriptions



def extract_attr_names_from_schema(attr_schema):
    """
    Extract attribute names from schema string
    
    Args:
        attr_schema: Format like "name: description\nage: description\n..."
        
    Returns:
        list: Attribute names like ['name', 'age', 'team', 'nba_draft_pick']
    """
    attr_names = []
    lines = attr_schema.strip().split('\n')
    for line in lines:
        line = line.strip()
        if ':' in line:
            # Extract attribute name before colon
            attr_name = line.split(':')[0].strip()
            if attr_name:
                attr_names.append(attr_name.lower())
    return attr_names

def parse_xyz(input_str):
    #  (key, value, confidence)
    # Remove leading/trailing spaces and parentheses
    stripped = input_str.strip().strip('()')
    # Define regex pattern
    pattern = r'^\s*([^,]+)\s*,\s*(.*?)\s*,\s*(\d+)\s*$'
    match = re.match(pattern, stripped)
    
    if not match:
        # print("Failed to match input string:\n", input_str)
        return None
    
    x = match.group(1).strip()
    y = match.group(2).strip()
    z = int(match.group(3))
    return (x, y, z)

def parse_xyz_with_chunkid(input_str, attr_names=None):
    """
    Parse string in format (key, value, confidence, chunkid)
    Also handles tuples without parentheses: key, value, confidence, chunkid
    
    Args:
        input_str: Input string like "(name, John Doe, 95, 123)" or "name, John Doe, 95, 123"
        attr_names: Valid attribute names for validation
        
    Returns:
        tuple: (key, value, confidence, chunkid) or None if parsing fails
    """
    # Remove leading/trailing spaces
    stripped = input_str.strip()
    
    # Skip empty lines
    if not stripped:
        return None
    
    # Handle tuples with or without parentheses
    if stripped.startswith('(') and stripped.endswith(')'):
        # Standard format: (key, value, confidence, chunkid)
        content = stripped[1:-1].strip()
    elif stripped.startswith('(') and not stripped.endswith(')'):
        # Incomplete tuple - skip
        return None
    elif ',' in stripped and not stripped.startswith('('):
        # No parentheses but has commas - try parsing as comma-separated values
        content = stripped
    else:
        return None
    
    # Quick validation: must have at least 3 commas (for 4 fields)
    # Allow more commas since value field might contain commas
    if content.count(',') < 3:
        return None
    
    # Define flexible regex that allows non-digit characters in confidence and chunkid
    # Updated: No longer requires confidence and chunkid to be pure numbers
    pattern = r'^\s*([^,]+)\s*,\s*(.*?)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*$'
    match = re.match(pattern, content)
    
    if not match:
        return None
    
    x = match.group(1).strip()
    y = match.group(2).strip()
    
    # Extract confidence and chunkid, handling quotes and decimals
    z_str = match.group(3).strip().strip('\'"')  # Strip whitespace and quotes
    chunkid_str = match.group(4).strip().strip('\'"')  # Strip whitespace and quotes
    
    # Handle confidence: can be integer (95) or decimal (0.95)
    try:
        z_float = float(z_str)
        # If value is between 0 and 1, assume it's a probability - convert to 0-100 scale
        if 0 <= z_float <= 1:
            z = int(z_float * 100)
        else:
            z = int(z_float)
    except (ValueError, TypeError):
        # If conversion fails, try extracting just the digits
        z_match = re.search(r'\d+', z_str)
        if not z_match:
            return None
        z = int(z_match.group())
    
    # Handle chunk_id: should be integer
    try:
        chunkid = int(chunkid_str)
    except (ValueError, TypeError):
        # If conversion fails, try extracting just the digits
        chunkid_match = re.search(r'\d+', chunkid_str)
        if not chunkid_match:
            return None
        chunkid = int(chunkid_match.group())
    
    # Post-processing: Remove quotes from key and value
    x = x.strip('\'"')  # Remove single or double quotes
    y = y.strip('\'"')  # Remove single or double quotes
    
    # Validate attribute name is in allowed list
    if attr_names is not None:
        allowed_lower = [name.lower() for name in attr_names]
        if x.lower() not in allowed_lower:
            # Debug: Show why it was rejected
            print(f"[DEBUG parse] Rejected attribute '{x}' - not in schema: {allowed_lower}")
            return None
    
    # Post-processing: Clean extra info from value
    if x.lower() == 'name':
        # For name attribute, remove extra info in parentheses (like birthday)
        # Match pattern: name (extra info)
        name_pattern = r'^([^(]+?)(?:\s*\([^)]+\))?$'
        name_match = re.match(name_pattern, y)
        if name_match:
            y = name_match.group(1).strip()
    
    return (x, y, z, chunkid)


class AttrSampler:

    def __init__(self, schema = "", llm = settings.GPT_MODEL, api_base= settings.GPT_API_BASE, max_tokens = 2048):
        self.api_base = settings.GPT_API_BASE # api_base
        self.llm =  settings.GPT_MODEL # llm        
        self.extract_task_prompt = """Your Task is to extract key-value pairs from text chunks with following guides:

1. InPut: 
    • Schema: Attributes to be extracted and their corresponding descriptions
    • Chunks: A list of text chunks to be extracted, each marked with its ID at the beginning.

2. Output:
    • `key`: lowercase attribute_name from schema (e.g., name)  
    • `value`: attribute_value with exact casing/spacing (e.g., iPhone 14)
    • `confidence`: int, between 0 to 100.
    • `chunkid`: int, id of the chunk from which the key-value pair is extracted.
    • Output one tuple per line, formatted as (attr_name, attr_value, confidence, chunkid).
"""

        self.system_prompt = "You are an attribute extraction assistant. Only respond with (key, value, confidence, chunkid) pairs. Do not include any explanations or extra text."
        self.sample_table = pd.DataFrame()
        self.map_attr_evidence = {}
        self.max_tokens = max_tokens
        self.schema = schema
        return

    def insert_table(self, doc_id, t):
        #  (key, value, confidence, evidence)
        key, value, confidence, evidence_text = t
        key_confidence_str = key + "_confidence"
        key_evidence_text_str = key + "_evidence"      
        
        # Check if key exists in table, if not add key column and confidence/evidence columns
        for col in [key, key_confidence_str, key_evidence_text_str]:
            if col not in self.sample_table.columns:
                self.sample_table[col] = None

        # Check if doc_id row exists, if not add a row
        if doc_id not in self.sample_table.index:
            self.sample_table.loc[doc_id] = [None] * len(self.sample_table.columns)

        # Check if value is same, if different replace based on confidence
        pre_value = self.sample_table.loc[doc_id, key]
        if pre_value is None:
            self.sample_table.loc[doc_id, key] = value
            self.sample_table.loc[doc_id, key_confidence_str] = confidence
            self.sample_table.loc[doc_id, key_evidence_text_str] = evidence_text
        elif pre_value != value:
            if confidence > self.sample_table.loc[doc_id, key_confidence_str]:
                self.sample_table.loc[doc_id, key] = value
                self.sample_table.loc[doc_id, key_confidence_str] = confidence
                self.sample_table.loc[doc_id, key_evidence_text_str] = evidence_text
        return

    def _convert_json_to_tuples(self, json_str):
        """Convert JSON output to tuple format if model outputs JSON instead of tuples."""
        try:
            import json as json_lib
            # Try to parse JSON
            data = json_lib.loads(json_str)
            
            # Flatten nested structures and convert to tuples
            tuples = []
            
            def flatten_dict(d, parent_key='', confidence=90, chunk_id=0):
                """Recursively flatten nested dictionaries."""
                for key, value in d.items():
                    if isinstance(value, dict):
                        # Recurse into nested dicts
                        flatten_dict(value, parent_key, confidence, chunk_id)
                    elif isinstance(value, list):
                        # Skip lists for now
                        pass
                    else:
                        # Create tuple: (key, value, confidence, chunk_id)
                        new_key = f"{parent_key}_{key}" if parent_key else key
                        tuples.append(f'({new_key}, {value}, {confidence}, {chunk_id})')
            
            if isinstance(data, dict):
                flatten_dict(data)
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    if isinstance(item, dict):
                        flatten_dict(item, confidence=90, chunk_id=i)
            
            if tuples:
                print(f"[DEBUG sampler] Converted JSON to {len(tuples)} tuples")
                return '\n'.join(tuples)
        except Exception as e:
            print(f"[DEBUG sampler] Failed to convert JSON: {e}")
        
        # Return original if conversion fails
        return json_str

    def response_single_doc(self, chunks, chunks_id, attr_Schema):
        
        # DEBUG: Log chunk statistics
        total_chars = sum(len(str(text)) for text in chunks)
        avg_chunk_size = total_chars / len(chunks) if chunks else 0
        print(f"[DEBUG response_single_doc] Processing {len(chunks)} chunks, total {total_chars} chars, avg {avg_chunk_size:.0f} chars/chunk")
        
        chunks_to_extract = ""
        for i, text in enumerate(chunks):
            chunks_to_extract += f'''
            Chunk_id {chunks_id[i]}:  
            ```  
            {text}
            ```  

            '''

        # CRITICAL: Put schema FIRST, chunks SECOND
        # The LLM needs to see which attributes to extract BEFORE the chunk data
        
        # Debug: Print first 200 chars of schema to verify
        print(f"[DEBUG response_single_doc] Schema being sent: {attr_Schema[:200] if len(attr_Schema) > 200 else attr_Schema}")
        
        # Simple, clean user prompt - let the LLM follow the system instructions
        user_prompt = f"""{self.extract_task_prompt}

Schema:
{attr_Schema}

Chunks:
{chunks_to_extract}

Extract the attributes from the chunks above."""
        
        # DEBUG: Log first 500 chars of prompt to verify schema is included
        print(f"[DEBUG response_single_doc] Prompt preview:\n{user_prompt[:500]}...")
        print(f"[DEBUG response_single_doc] Total prompt length: {len(user_prompt)} chars")
        
        final_prompt = [
            {"role": "system", "content": self.system_prompt}, 
            {"role": "user", "content": user_prompt}
            ]        
        
        LLMInfo.add_query_times(1)
        for talk in final_prompt:
                for v in talk.values():
                    LLMInfo.add_input_tokens(len(settings.enc.encode(v)))

        response = completion(
                model=self.llm, 
                messages=final_prompt,
                max_tokens=self.max_tokens,
                stop=None,
                temperature=0,
                api_base=self.api_base,
            )

        result = response.choices[0].message['content'].strip()     
        LLMInfo.add_output_tokens(len(settings.enc.encode(result)))
        
        # DEBUG: Show full raw response
        print(f"[DEBUG sampler] Raw response length: {len(result)} chars")
        print(f"[DEBUG sampler] Raw response first 200 chars: {result[:200]}")
        print(f"[DEBUG sampler] Raw response last 200 chars: {result[-200:]}")
        
        # Validate that output is tuples-only
        lines = result.split('\n')
        tuple_lines = [l for l in lines if l.strip().startswith('(') and l.strip().endswith(')')]
        non_tuple_lines = len(lines) - len([l for l in lines if not l.strip()]) - len(tuple_lines)
        
        if non_tuple_lines > 0:
            print(f"[WARNING sampler] LLM output contains {non_tuple_lines} non-tuple lines! Model is not following format.")
            print(f"[DEBUG sampler.response_single_doc] Raw LLM response:\n{result}\n---END RESPONSE---")
        else:
            print(f"[DEBUG sampler.response_single_doc] Good output: {len(tuple_lines)} tuples, 0 non-tuple lines")

        return result        

    def extract_doc2row(self, doc_id, chunks, attr_Schema):
        """
        Extract attributes from a sampled document
        - doc_id: Current sampled document ID
        - chunks: Document chunks list
        - attr_Schema: Attribute schema
        """
        # Extract attribute names from schema
        attr_names = extract_attr_names_from_schema(attr_Schema)
        chunks_id = list(range(len(chunks)))

        result = self.response_single_doc(chunks, chunks_id, attr_Schema= attr_Schema)
        tuples = result.split("\n")
        
        # DEBUG: Log parsing results
        parsed_count = 0
        failed_count = 0
        print(f"[DEBUG extract_doc2row] Processing {len(tuples)} lines from LLM response")

        for t in tuples:
            t = t.strip()  # Strip whitespace
            if not t:  # Skip empty lines
                continue
            
            # Skip lines that clearly aren't tuples (no commas, too short, etc.)
            if ',' not in t or len(t) < 5:
                continue
            
            # Try to parse - the parser now handles both (a,b,c,d) and a,b,c,d formats
            parsed = parse_xyz_with_chunkid(t, attr_names=attr_names)
            if parsed is None:
                failed_count += 1
                print(f"[DEBUG extract_doc2row] Failed to parse tuple: {t}")
                continue
                
            if parsed[1] is None:
                failed_count += 1
                print(f"[DEBUG extract_doc2row] Parsed but value is None: {t}")
                continue
            if parsed[2] < 50:  # Skip low confidence
                failed_count += 1
                print(f"[DEBUG extract_doc2row] Low confidence ({parsed[2]}): {t}")
                continue
            if parsed[3] >= len(chunks) or parsed[3] < 0:  # Skip invalid chunk IDs
                failed_count += 1
                print(f"[DEBUG extract_doc2row] Invalid chunk ID ({parsed[3]}, max={len(chunks)}): {t}")
                continue
            
            evidence_text = chunks[parsed[3]]
            new_tuple = (parsed[0], parsed[1], parsed[2], evidence_text)
            parsed_count += 1
        # (name, Donald Trump, 100, 91)
        # (key, value, confidence, chunksid)                
            # 以doc_id为主键
            self.insert_table(doc_id, new_tuple)
        
        print(f"[DEBUG extract_doc2row] For doc_id={doc_id}: {parsed_count} successful, {failed_count} failed")
        
        # If complete failure, log full context for debugging
        if parsed_count == 0 and failed_count > 0:
            print(f"\n{'='*80}")
            print(f"[DEBUG COMPLETE FAILURE for doc_id={doc_id} (type: {type(doc_id).__name__})]")
            print(f"{'='*80}")
            print(f"Attributes to extract: {attr_names}")
            print(f"Number of chunks: {len(chunks)}")
            if chunks:
                print(f"First chunk (first 300 chars): {chunks[0][:300]}")
            print(f"\n[RAW LLM RESPONSE (first 1500 chars)]:")
            print(f"{result[:1500]}")
            print(f"\n[RAW LLM RESPONSE (full, {len(result)} chars)]:")
            print(f"{result}")
            print(f"{'='*80}\n")

    def sample_one_doc(self, doc_id, doc_indexer : TextDocIndexer, attr_schema):
        chunks = doc_indexer.get_chunks_by_docid(doc_id)
        self.extract_doc2row(doc_id, chunks, attr_schema)
        return

    def try_sample(self, doc_indexer: TextDocIndexer, attr_schema):
        """
        Sample documents from indexer based on schema to build sample table
        """
        doc_ids = doc_indexer.get_docs_id()
        N = len(doc_ids)
        sample_num = min(N, max(settings.SAMPLE_NUM, int(N/20)))
        sampler_ids = random.sample(doc_ids, sample_num)
        for doc_id in sampler_ids:
            self.sample_one_doc(doc_id, doc_indexer, attr_schema)
        self.map_attr_evidence = self.get_evidence(attr_schema)

    def try_sample_all_docs(self, doc_indexer: TextDocIndexer, attr_schema):
        """
        DUMMY FUNCTION: Sample ALL documents from indexer to verify data completeness.
        This bypasses the random sampling and extracts from every document.
        Useful for debugging and verifying if information is actually in the dataset.
        """
        doc_ids = doc_indexer.get_docs_id()
        N = len(doc_ids)
        print(f"[DEBUG try_sample_all_docs] Sampling ALL {N} documents for exhaustive evidence collection")
        
        # Process all documents
        for i, doc_id in enumerate(doc_ids):
            if (i + 1) % 10 == 0:
                print(f"[DEBUG try_sample_all_docs] Processed {i + 1}/{N} documents")
            self.sample_one_doc(doc_id, doc_indexer, attr_schema)
        
        self.map_attr_evidence = self.get_evidence(attr_schema)
        print(f"[DEBUG try_sample_all_docs] Completed sampling all {N} documents")


    def get_evidence(self, attr_schema = ""):
        if len(attr_schema)<10:
            attr_schema = copy.copy(self.schema)
        map_attr_evidence = {} #
        attr_names = extract_attr_names_from_schema(attr_schema)
        for attr in attr_names:
            value_col = attr
            confidence_col = f"{attr}_confidence"
            evidence_col = f"{attr}_evidence"
            if (
                value_col not in self.sample_table.columns or 
                confidence_col not in self.sample_table.columns or
                evidence_col not in self.sample_table.columns
            ):
                map_attr_evidence[attr] = ""
                continue
            
            # Get rows with non-None confidence
            valid_rows = self.sample_table[self.sample_table[confidence_col].notnull()]
            if len(valid_rows) == 0:
                map_attr_evidence[attr] = ""
                continue
            # Sort by confidence and get top 2
            top2 = valid_rows.sort_values(by=confidence_col, ascending=False).head(2)
            # Concatenate evidence text (may have duplicates/None, need dedup and filter)
            evidences = [str(e) for e in top2[evidence_col].tolist() if e and str(e).strip()]

            concated_ev = "---------------------------------\n".join(evidences)
            map_attr_evidence[attr] = concated_ev
        return map_attr_evidence

    def get_attr_schema_evidence(self, attr_schema = ""):
        if len(attr_schema)<10:
            attr_schema = copy.copy(self.schema)        
        map_attr_evidence = {}

        attr_names = extract_attr_names_from_schema(attr_schema)
        attr_descriptions = extract_attr_descriptions_from_schema(attr_schema)
        for  attr, description in zip(attr_names, attr_descriptions):
            map_attr_evidence[attr] = attr + " : " + description
        return  map_attr_evidence
    
    def get_evidence_segments(self, attr_schema = ""):
        """
        Get evidence segments for each attribute (not concatenated).
        Returns dict mapping attribute -> list of evidence text segments.
        This is used for evidence-augmented retrieval with k-means clustering.
        
        According to QUEST paper Section 4.2:
        - Collect evidence segments from sampled documents
        - These will be embedded and clustered to get representative embeddings
        - The cluster centers are used to query for relevant segments
        """
        if len(attr_schema)<10:
            attr_schema = copy.copy(self.schema)
        
        map_attr_evidence_segments = {}
        attr_names = extract_attr_names_from_schema(attr_schema)
        
        # DEBUG: Log sample table info
        print(f"[DEBUG get_evidence_segments] sample_table shape: {self.sample_table.shape}")
        print(f"[DEBUG get_evidence_segments] sample_table columns: {list(self.sample_table.columns)}")
        if len(self.sample_table) > 0:
            print(f"[DEBUG get_evidence_segments] sample_table first row: {self.sample_table.iloc[0].to_dict()}")
        
        for attr in attr_names:
            value_col = attr
            confidence_col = f"{attr}_confidence"
            evidence_col = f"{attr}_evidence"
            
            if (
                value_col not in self.sample_table.columns or 
                confidence_col not in self.sample_table.columns or
                evidence_col not in self.sample_table.columns
            ):
                print(f"[DEBUG get_evidence_segments] Missing columns for {attr}: value_col={value_col in self.sample_table.columns}, confidence_col={confidence_col in self.sample_table.columns}, evidence_col={evidence_col in self.sample_table.columns}")
                map_attr_evidence_segments[attr] = []
                continue
            
            # Get rows with non-None confidence
            valid_rows = self.sample_table[self.sample_table[confidence_col].notnull()]
            print(f"[DEBUG get_evidence_segments] {attr}: {len(valid_rows)} rows with non-None confidence out of {len(self.sample_table)}")
            if len(valid_rows) == 0:
                map_attr_evidence_segments[attr] = []
                continue
            
            # Get all evidence segments (not just top 2)
            evidences = [str(e) for e in valid_rows[evidence_col].tolist() if e and str(e).strip()]
            print(f"[DEBUG get_evidence_segments] {attr}: collected {len(evidences)} evidence segments")
            map_attr_evidence_segments[attr] = evidences
        
        return map_attr_evidence_segments


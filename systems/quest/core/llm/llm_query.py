import re
import pandas as pd
from litellm import completion, batch_completion
from tqdm import tqdm
import tiktoken
import os
import logging
import quest.conf.settings as settings
from quest.utils import table_util
from quest.utils.log import print_log
import copy

def parse_result(text, doc_id, attributeList):
    """
    Parse LLM output. Supports two formats:
    1. key: value (original format)
    2. (key, value, confidence, chunk_id) (tuple format from sampler)
    """
    print(f"[DEBUG parse_result] Input text: {text[:100]}")
    
    dic = {}
    
    # Try tuple format first: (key, value, conf, idx)
    # Pattern: (word, anything, number, number)
    tuple_pattern = r'\((\w+(?:\.\w+)?),\s*([^,]+),\s*\d+,\s*\d+\)'
    tuple_matches = re.findall(tuple_pattern, text)
    
    if tuple_matches:
        print(f"[DEBUG parse_result] Found {len(tuple_matches)} tuple matches")
        for key, value in tuple_matches:
            key = key.strip()
            value = value.strip().strip("'\"")  # Remove quotes
            dic[key] = value
    else:
        # Fall back to key: value format
        print(f"[DEBUG parse_result] No tuple matches, trying colon format")
        dic = dict(re.findall(r"(\w+(?:\.\w+)?):([^:\n]*)", text))
    
    print(f"[DEBUG parse_result] Extracted dict: {dic}")
    dic["doc_id"] = doc_id
    for attr in attributeList:
        dic.setdefault(attr, None)
    print(f"[DEBUG parse_result] Final dict with defaults: {dic}")
    return dic

class LLMInfo(object):
    # static variables
    tot_query_times = 0
    tot_input_tokens = 0
    tot_output_tokens = 0

    @staticmethod
    def add_query_times(time):
        LLMInfo.tot_query_times += time
    
    @staticmethod
    def add_input_tokens(tokens):
        LLMInfo.tot_input_tokens += tokens

    @staticmethod
    def add_output_tokens(tokens):
        LLMInfo.tot_output_tokens += tokens

class TextLLMQuerier(object):
    """
    Used for extract attributes with LLMs.
    Configured to use Ollama with qwen3:8b (no-think mode).
    """
    def __init__(self, prompt, llm=settings.LLM_MODEL, api_base=settings.API_BASE):
        self.api_base = api_base
        self.llm = llm
        self.attr_descriptions = prompt
        self.enable_thinking = getattr(settings, 'ENABLE_THINKING', False)  # No-think mode
        print(f"[TextLLMQuerier.__init__] Model: {self.llm}, API Base: {self.api_base}, Thinking: {self.enable_thinking}")
        self.parse_attr_descriptions()
    
    def parse_attr_descriptions(self):
        # Format: one attribute per line, "attr_name: description"
        # Split only on FIRST colon to handle colons in descriptions
        self.attr_descriptions_dict = {}
        descriptions = self.attr_descriptions.split("\n")
        for line in descriptions:
            if line.strip() == "":
                continue
            # Split on first colon only (maxsplit=1)
            parts = line.split(":", 1)
            if len(parts) == 2:
                attr_name, description = parts
                self.attr_descriptions_dict[attr_name.strip()] = description.strip()
            elif len(parts) == 1:
                # No colon - use the whole line as attr name with empty description
                self.attr_descriptions_dict[parts[0].strip()] = ""
        return
    
    def build_text_list(self, textDict):
        # {doc_id1 : { column1 :[(text1, chunkid1), (text2,chunkid2), ...], } }
        doc_idList = list(textDict.keys())
        textList = [] # textList is a list of texts for the column

        print(f"[DEBUG build_text_list] Processing {len(doc_idList)} documents")
        
        for doc_id, columns in textDict.items():
            # columns is a dict, each key is a column name, and the value is a list of texts
            now_text = ""
            chunkid_set = set()
            cnt = 0

            for column, chunkList in columns.items():
                for chunk in chunkList:
                    chunkid = chunk[1]
                    if chunkid in chunkid_set:
                        continue
                    
                    chunkid_set.add(chunkid)
                    cnt += 1
                    now_text = now_text + f'''<Chunk {cnt} begin>\n\n''' +  str(chunk[0]) + f'''\n\n<Chunk {cnt}end>\n\n'''
                
            textList.append(now_text)
            
        # Debug: Check if texts are empty
        empty_count = sum(1 for t in textList if not t or not t.strip())
        if empty_count > 0:
            print(f"[DEBUG build_text_list] WARNING: {empty_count} out of {len(textList)} documents have EMPTY text!")
        
        # Show sample of first text
        if textList and textList[0]:
            sample = textList[0][:200] if len(textList[0]) > 200 else textList[0]
            print(f"[DEBUG build_text_list] Sample text from first doc: {sample}...")
        
        #print("textList:\n", textList)
        return textList, doc_idList

    def extract_attribute_from_textDict(self, textDict, attributeList):
        # {doc_id1 : { column1 :[(text1, chunkid1), (text2,chunkid2), ...], } }
        print(f"[DEBUG extract_attribute_from_textDict] Input textDict: {len(textDict)} docs")
        print(f"[DEBUG extract_attribute_from_textDict] Sample doc_id: {list(textDict.keys())[0] if textDict else 'EMPTY'}")
        if textDict:
            first_doc_id = list(textDict.keys())[0]
            first_doc = textDict[first_doc_id]
            print(f"[DEBUG extract_attribute_from_textDict] First doc structure: {list(first_doc.keys())[:3]}")
            if first_doc:
                first_col = list(first_doc.keys())[0]
                first_texts = first_doc[first_col]
                print(f"[DEBUG extract_attribute_from_textDict] First doc, first column has {len(first_texts)} text chunks")
                if first_texts:
                    print(f"[DEBUG extract_attribute_from_textDict] First text sample (first 200 chars): {first_texts[0][:200] if isinstance(first_texts[0], str) else str(first_texts[0])[:200]}")
        
        textList, doc_idList = self.build_text_list(textDict)
        print(f"[DEBUG extract_attribute_from_textDict] textList: {len(textList)} docs, {[len(t) if isinstance(t, str) else len(str(t)) for t in textList[:3]]} chars (sample)")
        print(f"[DEBUG extract_attribute_from_textDict] doc_idList: {doc_idList[:5]}")
        # print_log("textList:\n", textList, "\ndoc_idList:\n", doc_idList)
        return self.extract_attribute(textList, doc_idList, attributeList)
    
    def extract_attribute_from_textDict_semantic_fiter(self, textDict, attributeList, filterList):
        # {doc_id1 : { column1 :[(text1, chunkid1), (text2,chunkid2), ...], } }
        textList, doc_idList = self.build_text_list(textDict)
        return self.extract_attribute_and_semantic_filter(textList, doc_idList, attributeList, filterList)

    def extract_attribute_and_semantic_filter(self, textList, doc_idList, attributeList, filterList):
        """
        textList : list[str], each element is a text document, corresponding to doc_idList
        doc_idList : list[str], id of the text documents, corresponding to textList
        attributeList : list[str], attributes to extract from the text documents, form like age or Player.age !!! always input only one attribute
        filterList : list[str], filter conditions to apply on the extracted attributes

        extract the attributes from the textList, which is a list of text documents.

        output : a dataframe, columns = attributeList + ['doc_id'] + ['fcondition']
        """
        docs = copy.copy(textList)

        """
        for file in textList:
            tokens = settings.enc.encode(file)
            truncated_tokens = tokens[:4000]
            truncated_text = settings.enc.decode(truncated_tokens)
            docs.append(truncated_text)
        """

        attributes = ", ".join(attributeList)
        filters = ", ".join(filterList)
        
        related_attr_descriptions = []
        for attr in attributeList:
            related_attr_descriptions.append(f"{attr}: {self.attr_descriptions_dict.get(attr)}")
        related_attr_descriptions_str = " \n".join(related_attr_descriptions)
        prompts = [
            [
                {"role": "system", "content": "You are an information extraction and check assistant. Respond in two lines, the first line is a key-value pair using the exact field name provided; the second line is a key-value pair, and value is a boolean True or False whether the condition is met. Do not include any explanations or extra text."},
                {"role": "user", "content": f'''Extract the following field from the given document: {attributes}. Then Check if the value satisfy the condition.

                Instructions:
                - Format your response as two lines, the first line in the format: `field: value`, and the second line in the format: `fcondition: True/False`.
                - Use the exact field name: {attributes}.
                - Check the condition {filters}.
                - If the field is missing or unknown, leave its value empty (e.g., `team: None`), and leave the condition as False.
                - use the line break (`\\n`) to split the lines.
                - You should first extract the field value and then check. For example, we first do extract, and get filed is \'name\', value is \'Lee\'. Then we do check, the condition is \'name==\'Frank\' \', the value does not satisfy the condition, so the fcondtion is False.
                - The filter condition `==` or `IN` can be considered emantically for strings. For example, \'Lakers\' and \'Los Angeles Lakers\' are equal, \'fashion\' and \'Fashion || Illustration\' are also equal.
                - The filter conditioin `<`, `>`, `>=`, `<=` can be considered as numeric comparison or a date comparison, note that the eariler date is smaller.
                - For example, the filed is \'birth date\', and value is \'2001/10/6\'. Then we do check, the condition is \'birth date<\'1999/11/6\' \', the value does not satisfy the condition, so the fcondition is False, output fcondition: False.
                - For example, the filed is \'style\', and value is \'fashion\'. Then we do check, the condition is \'style == Fashion\', the value satisfy the condition, so the fcondition is True, output fcondition: True.
                - Follow the descriptions of the field:
                ``` {related_attr_descriptions_str} ```
                - Do not add any extra text, comments, quotes, or explanations.

                Document:
                {doc}
                '''
                }
            ]
            for doc in docs
        ]
        results = self.batch_llm_response(prompts=prompts) # totest

        attributeList.append('fcondition')
        json_result = [parse_result(results[i], doc_idList[i], attributeList) for i in range(len(results))]
        df = pd.DataFrame(json_result)
        df = df.fillna(" ")
        attributeList.append('doc_id')
        df = table_util.check_missing_columns(df, attributeList)
        #print("use prompt:", related_attr_descriptions_str)
        print("------------\n", df)
        return df
    
    def extract_attribute(self, textList, doc_idList, attributeList):
        """
        textList : list[str], each element is a text document, corresponding to doc_idList
        doc_idList : list[str], id of the text documents, corresponding to textList
        attributeList : list[str], attributes to extract from the text documents, form like age or Player.age

        extract the attributes from the textList, which is a list of text documents.

        output : a dataframe, columns = attributeList + ['doc_id']
        """
        docs = copy.copy(textList)

        """
        for file in textList:
            tokens = settings.enc.encode(file)
            truncated_tokens = tokens[:4000]
            truncated_text = settings.enc.decode(truncated_tokens)
            docs.append(truncated_text)
        """

        # CRITICAL FIX: Strip table prefixes from attribute names for LLM query
        # Schema knows attributes as "disease_name", not "disease.disease_name"
        # But we need to preserve the qualified names for the output DataFrame
        unqualified_attrs = []
        attr_mapping = {}  # Maps unqualified -> qualified
        for attr in attributeList:
            if '.' in attr:
                # Extract column name without table prefix
                unqualified = attr.split('.')[-1]
            else:
                unqualified = attr
            unqualified_attrs.append(unqualified)
            attr_mapping[unqualified] = attr
        
        print(f"[DEBUG extract_attribute] Unqualified attrs for LLM: {unqualified_attrs}")
        print(f"[DEBUG extract_attribute] Attr mapping: {attr_mapping}")

        attributes = ", ".join(unqualified_attrs)
        related_attr_descriptions = []
        for attr in unqualified_attrs:
            related_attr_descriptions.append(f"{attr}: {self.attr_descriptions_dict.get(attr)}")
        related_attr_descriptions_str = " \n".join(related_attr_descriptions)
        prompts = [
            [
                {"role": "system", "content": "You are a data extraction assistant. Return ONLY a single line in tuple format. No explanations, no markdown, no extra text."},
                {"role": "user", "content": f'''Extract the attribute "{unqualified_attrs[0]}" from the document.

OUTPUT FORMAT - MUST be exactly one line with this structure:
(attribute_name, extracted_value, confidence_0_to_100, section_0_to_9)

RULES:
- Return EXACTLY ONE line only
- First item in tuple MUST be: {unqualified_attrs[0]}
- Second item: the actual value you extract (or "NONE" if not found)
- Third item: confidence score 0-100 as a number
- Fourth item: section index 0-9 as a number
- Use commas to separate items
- No quotes around values
- No markdown, no bullets, no explanation

GENERIC EXAMPLES:
(city, New York, 95, 0)
(name, John Smith, 90, 1)
(year, 2023, 85, 2)

IF NOT FOUND, use:
({unqualified_attrs[0]}, NONE, 0, 0)

ATTRIBUTE DESCRIPTION:
{related_attr_descriptions_str}

DOCUMENT:
{doc}

OUTPUT (one line only, starting with parenthesis):'''
                }
            ]
            for doc in docs
        ]
        results = self.batch_llm_response(prompts=prompts) # totest

        print(f"[DEBUG extract_attribute] LLM returned {len(results)} results")
        if results:
            print(f"[DEBUG extract_attribute] First result (first 500 chars): {results[0][:500]}")

        json_result = [parse_result(results[i], doc_idList[i], unqualified_attrs) for i in range(len(results))]
        df = pd.DataFrame(json_result)
        df = df.fillna(" ")
        
        # CRITICAL FIX: Rename columns from unqualified to qualified names
        # This ensures the DataFrame has columns like "disease.disease_name" not just "disease_name"
        rename_map = {}
        for unqualified, qualified in attr_mapping.items():
            if unqualified in df.columns and unqualified != qualified:
                rename_map[unqualified] = qualified
        
        if rename_map:
            print(f"[DEBUG extract_attribute] Renaming columns: {rename_map}")
            df = df.rename(columns=rename_map)
        
        attributeList_with_doc = attributeList + ['doc_id']
        df = table_util.check_missing_columns(df, attributeList_with_doc)
        #print("use prompt:", related_attr_descriptions_str)
        print("------------\n", df)
        return df
    

    def check_filter_condition(self, docs, doc_idList, attributeList, filterList):
        """
        textList : list[str], each element is a text document, corresponding to doc_idList
        doc_idList : list[str], id of the text documents, corresponding to textList
        filterList : list[str], filter conditions to apply on the extracted attributes

        extract the attributes from the textList, which is a list of text documents.

        output : a dataframe, columns = attributeList + ['doc_id'] + ['fcondition']
        """

        filters = ", ".join(filterList)
        
        related_attr_descriptions = []
        for attr in attributeList:
            related_attr_descriptions.append(f"{attr}: {self.attr_descriptions_dict.get(attr)}")
        related_attr_descriptions_str = " \n".join(related_attr_descriptions)
        prompts = [
            [
                {"role": "system", "content": "You are an condition check assistant. Respond in a single line, includes a pair format as `fcondition: True/False`, the boolean True or False represents whether the condition is met. Do not include any explanations or extra text."},
                {"role": "user", "content": f'''Check if the value satisfy the condition or semantically similar to the condition.

                Instructions:
                - Format your response as a single line, in the format: `fcondition: True/False`.
                - Check if the value satisfies the condition {filters}.
                - The filter condition `==` or `IN` can be considered emantically for strings. For example, \'Lakers\' and \'Los Angeles Lakers\' are equal, \'fashion\' and \'Fashion || Illustration\' are also equal.
                - The filter conditioin `<`, `>`, `>=`, `<=` can be considered as numeric comparison or a date comparison, note that the eariler date is smaller.
                - For example, the filed is \'birth date\', and value is \'2001/10/6\'. Then we do check, the condition is \'birth date<\'1999/11/6\' \', the value does not satisfy the condition, so the fcondition is False, output fcondition: False.
                - For example, the filed is \'style\', and value is \'fashion\'. Then we do check, the condition is \'style == Fashion\', the value satisfy the condition, so the fcondition is True, output fcondition: True.
                - Do not add any extra text, comments, quotes, or explanations.

                Value:
                {doc}

                Condition:
                {filters}
                '''
                }
            ]
            for doc in docs
        ]
        results = self.batch_llm_response(prompts=prompts) # totest

        attributeList.append('fcondition')
        json_result = [parse_result(results[i], doc_idList[i], attributeList) for i in range(len(results))]
        df = pd.DataFrame(json_result)
        df = df.fillna(" ")
        attributeList.append('doc_id')
        df = table_util.check_missing_columns(df, attributeList)
        # check columns

        print("use prompt:", related_attr_descriptions_str)
        print("------------\n", df)
        return df

    def single_iter_llm_response(self, prompts):
        results = []
        LLMInfo.add_query_times(len(prompts))
        for prompt in tqdm(prompts):
            # Add no-think system message for qwen3
            if "qwen" in self.llm.lower():
                if prompt and prompt[0].get("role") == "system":
                    prompt[0]["content"] = prompt[0]["content"] + " Answer directly without reasoning or thinking steps. Do not use <think> tags."
                else:
                    prompt.insert(0, {"role": "system", "content": "Answer directly without reasoning or thinking steps. Do not use <think> tags."})
            
            response = completion(
                    model=self.llm, 
                    messages=prompt,
                    max_tokens=128,
                    stop=None,
                    temperature=0,
                    api_base=self.api_base,
                    # Ollama-specific parameters
                    think=False,  # Disable thinking mode
                    num_predict=128,
                )

            results.append(response.choices[0].message.content)
        
        for prompt in prompts:
            for talk in prompt:
                for v in talk.values():
                    LLMInfo.add_input_tokens(len(settings.enc.encode(v)))

        for v in results:
            LLMInfo.add_output_tokens(len(settings.enc.encode(v)))
        
        return results

    def batch_llm_response(self, prompts):
        results = []
        LLMInfo.add_query_times(len(prompts))
        
        # Add no-think system message for qwen3 models
        if "qwen" in self.llm.lower():
            for prompt in prompts:
                if prompt and prompt[0].get("role") == "system":
                    prompt[0]["content"] = prompt[0]["content"] + " Answer directly without reasoning or thinking steps. Do not use <think> tags."
                else:
                    prompt.insert(0, {"role": "system", "content": "Answer directly without reasoning or thinking steps. Do not use <think> tags."})

        batch_responses = batch_completion(
                model=self.llm, 
                messages=prompts,
                max_tokens=128,
                stop=None,
                temperature=0,
                api_base=self.api_base,
                # Ollama-specific parameters
                think=False,  # Disable thinking mode
                num_predict=128,
            )
        
        for response in batch_responses:
            results.append(response.choices[0].message.content)

        for prompt in prompts:
            for talk in prompt:
                for v in talk.values():
                    LLMInfo.add_input_tokens(len(settings.enc.encode(v)))

        for v in results:
            try:
                LLMInfo.add_output_tokens(len(settings.enc.encode(v)))
            except:
                print_log("Token count error occurred.")
                print_log(v)
        
        return results          

import re
from utils.llm_config import clean_llm_response

class extractOP:
    """
    Extract operator per paper Table 1:
    - Input: Text
    - Output: Text
    - Logical Representation: "get [Entity] from documents"
    
    Supports both pre-programmed (regex) and LLM-based implementations
    as described in the paper.
    """
    def __init__(self, data_list, extract_target=None):
        self.data_list = data_list
        if type(self.data_list) == dict:
            self.data_list = list(self.data_list.values())

        self.extract_target = extract_target
        self.opName = "Extract"
        
        # Determine if we should use regex (pre-programmed) or LLM-based extraction
        # Per paper: "Pre-programmed Implementations leverage predefined algorithms"
        # "LLM-based Implementations employ LLMs for tasks requiring deeper semantic reasoning"
        self.use_semantic = self._should_use_semantic(extract_target)

    def _should_use_semantic(self, extract_target):
        """
        Determine if semantic (LLM-based) extraction is needed.
        Use regex for simple numeric patterns, LLM for semantic extraction.
        """
        if extract_target is None:
            return True
        # Simple patterns that can be extracted with regex
        simple_patterns = ["viewcount", "views", "count", "number", "score", "rating"]
        for pattern in simple_patterns:
            if pattern.lower() in extract_target.lower():
                return False
        return True

    def execute(self, LLMclient, chatModel, ctxManager):
        if self.use_semantic:
            return self._execute_semantic(LLMclient, chatModel, ctxManager)
        else:
            return self._execute_regex(LLMclient, chatModel, ctxManager)
    
    def _execute_regex(self, LLMclient, chatModel, ctxManager):
        """Pre-programmed implementation using regex patterns"""
        # Map common targets to their regex patterns
        pattern_map = {
            "viewcount": r"(?:Question )?viewcount:\s*(\d+)",
            "views": r"views:\s*(\d+)",
            "score": r"score:\s*(\d+)",
            "count": r"count:\s*(\d+)",
        }
        
        # Find matching pattern
        pattern_str = None
        for key, pat in pattern_map.items():
            if key.lower() in (self.extract_target or "").lower():
                pattern_str = pat
                break
        
        if pattern_str is None:
            pattern_str = rf"{re.escape(self.extract_target or 'viewcount')}:\s*(\d+)"
        
        pattern = re.compile(pattern_str, re.IGNORECASE)
        extracted_values = []

        for item in self.data_list:
            match = pattern.search(item)
            if match:
                try:
                    extracted_values.append(int(match.group(1)))
                except ValueError:
                    extracted_values.append(match.group(1))

        return extracted_values, ctxManager

    def _execute_semantic(self, LLMclient, chatModel, ctxManager):
        """
        LLM-based implementation for semantic extraction.
        Per paper: "LLM-based Implementations employ LLMs for tasks requiring deeper semantic reasoning"
        """
        if not self.data_list:
            return None, ctxManager
        
        # Combine documents for context (limit to avoid token overflow)
        combined_docs = "\n\n---\n\n".join(self.data_list[:5])  # Limit to first 5 docs
        
        prompt = f"""Based on the following documents, extract the answer to: "{self.extract_target}"

Documents:
{combined_docs}

Please provide only the extracted answer without any explanation. If the information is not found in the documents, respond with "Information not found"."""

        ctxManager.add_user_message(prompt)
        
        response = chatModel.create_completion(
            LLMclient,
            temperature=0.1,
            top_p=0.9,
            max_tokens=500,
            messages=ctxManager.get_messages()
        )
        
        # Clean the response to remove <think> tags from models like qwen3
        response = clean_llm_response(response)
        
        ctxManager.add_assistant_message(response)
        
        return response.strip(), ctxManager





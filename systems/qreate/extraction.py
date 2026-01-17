import json
import ollama
from typing import List, Dict, Any, Tuple

class QREATEMiner:
    def __init__(self, model: str = "qwen2.5:7b-instruct"):
        self.model = model
        self.system_prompt = """You are a Logic Engine. Your task is to extract EVERY fact from the provided text as a JSON list of triples.

Triple Structure: {"sub": "Subject", "pred": "Predicate", "obj": "Object"}

Guidelines:
1. Extract ALL entities mentioned.
2. For every entity, extract its type: {"sub": "EntityName", "pred": "is_a", "obj": "TypeName"}.
3. Extract all attributes (price, MSRP, cost, color, weight, etc.) as triples.
4. Extract all relationships between entities.
5. If pronouns are used, resolve them using ENTITY_FOCUS_STATE.
6. MANDATORY: You must return a LIST of triples, even if there is only one fact.
7. Aim for 5-15 triples per chunk to be comprehensive.

Output format:
[
  {"sub": "...", "pred": "...", "obj": "..."},
  ...
]"""

    def extract_triples(self, chunk_text: str, focus_state: List[str]) -> Tuple[List[Dict[str, str]], List[str]]:
        prompt = f"CHUNK CONTENT:\n{chunk_text}\n\nENTITY_FOCUS_STATE: {', '.join(focus_state)}"
        
        try:
            print(f"Calling Ollama with chunk of length {len(chunk_text)}...")
            response = ollama.generate(
                model=self.model,
                system=self.system_prompt,
                prompt=prompt
            )
            raw_output = response['response']
            print(f"Ollama raw output (first 200 chars): {raw_output[:200]}...")
            
            import re
            json_match = re.search(r'\[\s*\{.*\}\s*\]', raw_output, re.DOTALL)
            if json_match:
                triples = json.loads(json_match.group(0))
            else:
                obj_match = re.search(r'\{\s*"sub":.*\}', raw_output, re.DOTALL)
                if obj_match:
                    triples = [json.loads(obj_match.group(0))]
                else:
                    data = json.loads(raw_output)
                    if isinstance(data, list):
                        triples = data
                    elif isinstance(data, dict):
                        if "sub" in data: triples = [data]
                        else: triples = []
                    else:
                        triples = []
                        
        except Exception as e:
            print(f"Extraction failed: {e}")
            triples = []
            
        if not triples:
            print("No triples found, attempting repair...")
            try:
                repair_response = ollama.generate(
                    model=self.model,
                    system="You are a JSON fixer. Convert the previous text into a valid JSON LIST of triples: [{\"sub\": \"...\", \"pred\": \"...\", \"obj\": \"...\"}]",
                    prompt=f"Text to convert:\n{raw_output if 'raw_output' in locals() else 'No output'}"
                )
                import re
                repair_match = re.search(r'\[\s*\{.*\}\s*\]', repair_response['response'], re.DOTALL)
                if repair_match:
                    triples = json.loads(repair_match.group(0))
            except:
                pass

        if not isinstance(triples, list):
            triples = []

        new_focus_state = list(set([t.get("sub") for t in triples if t.get("sub")]))
        
        return triples, new_focus_state

import json
import ollama
import re
from typing import List, Dict, Any, Tuple

class QREATEMiner:
    def __init__(self, model: str = "qwen2.5:7b-instruct"):
        self.model = model
        self.system_prompt = """You are a high-precision data extraction engine. 
Task: Extract all distinct entities and their attributes from the text.

Constraint: Entity Categorization (TYPE)
1. Every entity must be assigned a specific category label (role='TYPE').
2. FORBIDDEN LABELS: 'Entity', 'Object', 'Thing', 'Noun', 'Item', 'Miscellaneous', 'Unknown'.
3. MANDATORY: You must use the most precise noun possible that describes the entity's 
   functional class (e.g., 'Analgesic' instead of 'Drug', 'Smartphone' instead of 'Device').

Constraint: Attribution (ATTRIBUTE)
1. Every attribute must be bound to its subject via a triple.

Output Format: JSON list of triples [[Subject, Predicate, Object, Role]]
Note: Although the instruction says [[...]], please output as a list of objects with keys: "sub", "pred", "obj", "role", "object_type"."""

    def extract_triples(self, chunk_text: str, focus_state: List[str]) -> Tuple[List[Dict[str, str]], List[str]]:
        prompt = f"CHUNK CONTENT:\n{chunk_text}\n\nENTITY_FOCUS_STATE: {', '.join(focus_state)}"
        
        try:
            response = ollama.generate(
                model=self.model,
                system=self.system_prompt,
                prompt=prompt
            )
            raw_output = response['response']
            
            # Find JSON list in output
            json_match = re.search(r'\[\s*\{.*\}\s*\]', raw_output, re.DOTALL)
            if json_match:
                triples = json.loads(json_match.group(0))
            else:
                obj_match = re.search(r'\{\s*"sub":.*\}', raw_output, re.DOTALL)
                if obj_match:
                    triples = [json.loads(obj_match.group(0))]
                else:
                    triples = []
                        
        except Exception as e:
            print(f"Extraction failed: {e}")
            triples = []
            
        if not triples:
            try:
                repair_response = ollama.generate(
                    model=self.model,
                    system="You are a JSON fixer. Convert the previous text into a valid JSON LIST of triples with 'sub', 'pred', 'obj', and 'object_type'.",
                    prompt=f"Text to convert:\n{raw_output if 'raw_output' in locals() else 'No output'}"
                )
                repair_match = re.search(r'\[\s*\{.*\}\s*\]', repair_response['response'], re.DOTALL)
                if repair_match:
                    triples = json.loads(repair_match.group(0))
            except:
                pass

        if not isinstance(triples, list):
            triples = []

        # Update focus state
        new_focus_state = list(set([t.get("sub") for t in triples if t.get("sub")]))
        
        return triples, new_focus_state

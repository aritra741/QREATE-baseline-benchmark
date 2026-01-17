import json
import os
from typing import List, Dict
from ollama import Client

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"

def get_llm_client():
    return Client(host=OLLAMA_HOST)

def get_relevant_tables(chunk_text: str, schema: Dict, client: Client) -> List[str]:
    """Phase 3 Optimization: Pre-Flight check to identify relevant tables for a chunk."""
    table_names = list(schema.keys())
    prompt = f"""Identify which of these database tables are relevant to the provided text.
    
TABLES: {json.dumps(table_names)}

TEXT: {chunk_text}

Output strictly a JSON list of relevant table names. If none are relevant, output []."""
    
    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
        relevant = json.loads(response['message']['content'])
        return [t for t in relevant if t in table_names]
    except:
        return table_names



import json
import os
from typing import List, Dict
from stanza.server import CoreNLPClient

# Configuration
# CORE_NLP_HOME should point to where stanza.install_corenlp() put it
CORE_NLP_HOME = os.path.expanduser("~/stanza_corenlp")
os.environ["CORENLP_HOME"] = CORE_NLP_HOME

def extract_triples_corenlp(text: str) -> List[Dict]:
    """True OpenIE extraction using Stanford CoreNLP."""
    triples = []
    # Start the CoreNLP server for each chunk to ensure it stays in the context of this process
    with CoreNLPClient(
        annotators=['openie'],
        timeout=30000,
        memory='4G',
        be_quiet=True
    ) as client:
        ann = client.annotate(text)
        for sentence in ann.sentence:
            for triple in sentence.openieTriple:
                triples.append({
                    "subject": triple.subject,
                    "relation": triple.relation,
                    "object": triple.object
                })
    return triples

def main():
    if not os.path.exists("chunks.json"):
        print("Required file chunks.json missing.")
        return

    with open("chunks.json", 'r') as f: chunks = json.load(f)
    
    # We output raw triples. Schema binding happens in the next phase.
    with open("raw_triples.jsonl", "w") as out_f:
        for i, chunk in enumerate(chunks):
            print(f"Mining OpenIE triples from chunk {i+1}/{len(chunks)}...")
            try:
                triples = extract_triples_corenlp(chunk["text"])
                for t in triples:
                    t["chunk_id"] = chunk["id"]
                    out_f.write(json.dumps(t) + "\n")
            except Exception as e:
                print(f"Error in OpenIE extraction: {e}")

    print("OpenIE mining complete. Raw triples saved to raw_triples.jsonl")

if __name__ == "__main__":
    main()

    print("Extraction complete. Results saved to extracted_raw.jsonl")

if __name__ == "__main__":
    main()

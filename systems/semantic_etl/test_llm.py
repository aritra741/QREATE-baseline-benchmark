import json
from ollama import Client

client = Client(host="http://localhost:11434")
MODEL_NAME = "qwen2.5:7b-instruct"

with open("chunks.json", "r") as f:
    chunks = json.load(f)

chunk = chunks[0]
text = chunk["text"]

prompt_template = """Analyze the text below. Identify every distinct real-world Entity Type (e.g., 'Person', 'Organization', 'Drug', 'Country') and the specific Attributes (properties) associated with them in this specific text segment.

TEXT:
{chunk_text}

INSTRUCTIONS:
1. Ignore transient actions (e.g., "Doctor spoke to patient"). Focus on permanent database-style data.
2. Output strictly a JSON list of objects.
3. If no entities are found, output an empty list [].

JSON FORMAT:
[
  {{
    "type": "EntityTypeName",
    "attributes": ["attribute1", "attribute2"]
  }}
]"""

response = client.chat(model=MODEL_NAME, messages=[
    {'role': 'user', 'content': prompt_template.format(chunk_text=text)}
], format='json')

print(response['message']['content'])

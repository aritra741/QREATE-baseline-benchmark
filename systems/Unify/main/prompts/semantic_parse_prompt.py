def get_semantic_parse_prompt(question):
    # Note: /no_think at the end disables qwen3's thinking mode for direct JSON output
    prompt = f"""Please parse the following question and extract the entities, conditions, attributes, actions, and return type.

### Example 1:
Question: "How many documents are related to boxing?"
Output: {{
  "Entities": ["boxing"],
  "Conditions": ["related to boxing"],
  "Attributes": [],
  "Actions": [],
  "Return Type": "number"
}}

### Example 2:
Question: "Which type of movies is most discussed among movies that involve sports, movies that involve love, and movies that involve crimes?"
Output: {{
  "Entities": ["movies", "movies", "movies", "movies"],
  "Conditions": ["involve sports", "involve love", "involve crimes"],
  "Attributes": [],
  "Actions": ["most discussed"],
  "Return Type": "type of movie"
}}

### Example 3:
Question: "From documents with over 10,000 views, identify the ball sport with the highest ratio of injury-related to training-related documents."
Output: {{
  "Entities": ["ball sport"],
  "Conditions": ["over 10,000 views", "injury-related", "training-related"],
  "Attributes": [],
  "Actions": ["highest ratio"],
  "Return Type": "ball sport"
}}

### Example 4:
Question: "Documents related to running"
Output: {{
  "Entities": ["running"],
  "Conditions": ["related to running"],
  "Attributes": [],
  "Actions": [],
  "Return Type": "documents"
}}

### Example 5:
Question: "When did West Francia become the Kingdom of France?"
Output: {{
  "Entities": ["West Francia", "Kingdom of France"],
  "Conditions": [],
  "Attributes": [],
  "Actions": ["become"],
  "Return Type": "time"
}}

Now, please process the following question like above examples. 

Question: "{question}"

Provide the output in JSON format as:
{{
  "Entities": [...],
  "Conditions": [...],
  "Attributes": [...],
  "Actions": [...],
  "Return Type": "..."
}}

Output ONLY the JSON, no explanations or reasoning.
Rules:
- "documents" do not need to be parsed as "Entities".
- "related to [xxx]" should always be parsed as "Conditions".
- If there is "ball sport" in the question and no other specific ball sports, "ball sport" should be parsed as "Entities".
/no_think"""
    return prompt
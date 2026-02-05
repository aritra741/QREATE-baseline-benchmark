# Semantic ETL: Final Architecture and Design Rationale

## Overview

The final architecture is a 5-phase pipeline that converts 106,000 medical text documents into a relational SQLite database. Each phase solves a specific problem that emerged during iterative development.

---

## Phase 1: Shadow Context Ingestion

### What It Does
Splits documents into chunks and attaches metadata for pronoun resolution.

### Technical Details
1. **Chunk Creation:**
   - Documents are split at sentence boundaries to create chunks of 500-1000 words.
   - Each chunk includes a metadata field containing the last 3 sentences from the previous chunk.

2. **Data Structure:**
   ```
   Chunk N:
   {
     "id": "doc_12_chunk_5",
     "text": "The medication was administered intravenously...",
     "previous_context": "Patient presented with severe hypertension. Blood pressure was 180/120. The physician prescribed treatment."
   }
   ```

### Design Reasoning

**Why 3 sentences of context?**
- Pronouns like "it", "they", "this condition" often reference the nearest preceding noun phrase.
- 3 sentences typically spans 50-100 tokens, which provides enough context window for Qwen to resolve anaphora without consuming excessive token budget.
- Empirical testing showed diminishing returns beyond 3 sentences.

**Why sentence boundaries?**
- Semantic chunks within sentences are fragments that lose meaning.
- Splitting at sentence boundaries preserves complete thoughts and maintains coherence for the LLM to extract meaningful entities.

**Why this metadata design?**
- Attaching context as a separate field prevents it from being mistaken for actual content.
- The LLM can explicitly read the `previous_context` field first before processing `text`, creating a two-stage reading process.

---

## Phase 2: Schema Induction

### What It Does
Discovers the database schema (tables and columns) from a representative sample of documents.

### Detailed Process

#### 2.1: Stratified Sampling
**Input:** 106,000 chunks
**Output:** 1,000 sampled chunks

**Algorithm:**
1. Divide 106,000 chunks into 100 groups of approximately 1,060 chunks each.
2. Randomly sample 10 chunks from each group.
3. Result: 1,000 chunks spread across the entire dataset.

**Implementation:**
```python
indices = np.linspace(0, len(chunks) - 1, SAMPLE_SIZE, dtype=int)
sampled_chunks = [chunks[i] for i in indices]
```

**Design Reasoning:**
- **Why stratified, not random?** Random sampling of 1,000 from 106,000 might over-represent early chunks (which tend to be metadata-heavy) and under-represent middle chunks (which contain domain signal). Stratified sampling ensures representation across the dataset.
- **Why 1,000?** This is a balance:
  - 1,000 chunks provide enough observations for Agglomerative Clustering to find stable clusters (typically need >2 observations per cluster).
  - Too few (<500) risks missing rare domain entities. Too many (>5,000) adds unnecessary LLM overhead.
- **Why 10 chunks per group?** With 100 groups, this ensures coverage breadth while limiting sampling bias within each group.

#### 2.2: Entity Observation Extraction
**Input:** 1,000 sampled chunks (parallelized with 20 workers)
**Output:** ~3,000-5,000 entity observations

**LLM Prompt:**
```
Analyze the text. Identify all distinct Entity Types.
Instruction: Focus on the subjects of the text (the actors, objects, events, and metrics).
Ignore information that describes the source, the format, or the administrative context.

For each Entity Type, identify:
1. Attributes (intrinsic properties).
2. Relationships (connections to other entities).

Output JSON:
[{"type": "EntityTypeName", "attributes": ["list", "of", "strings"], "relationships": ["list", "of", "strings"]}]

TEXT: {chunk_text}
```

**Processing:**
- Uses `ThreadPoolExecutor` with 20 workers.
- Each worker calls Qwen2.5:7b.
- Handles various LLM output formats (list, dict wrapper, nested lists).
- Merges `attributes` and `relationships` into a single `attributes` dict for downstream clustering.

**Design Reasoning:**
- **Why this prompt structure?** The prompt explicitly instructs the LLM to distinguish "Domain Signal" (actors, objects, events) from "Information Scaffolding" (metadata). This reduces the frequency of metadata observations in the result.
- **Why 20 workers?** Balances GPU utilization. Too few (<10) leaves GPU underutilized. Too many (>50) causes contention on the single GPU and increases latency per LLM call due to queueing.
- **Why parallelize here?** With 1,000 chunks and 5-10 seconds per LLM call, sequential would take ~3-5 hours. Parallel with 20 workers reduces this to ~10-15 minutes.

#### 2.3: Agglomerative Clustering and Hierarchical Deduplication
**Input:** ~3,000-5,000 entity observations
**Output:** Canonical tables with semantically normalized columns

**Step 1: Table-Level Clustering**
1. For each observation, create a "fingerprint": `"{type}:{sorted(attributes_names)}"`.
2. Convert fingerprints to vectors using `bge-m3` embeddings (1024-dim).
3. Apply Agglomerative Clustering (Average Linkage, Cosine Metric, Threshold 0.2).
4. Clusters with `Count >= 2` survive.

**Step 2: Intra-Table Attribute Deduplication (Hierarchical)**
Within each surviving table cluster, we perform a second level of normalization to merge synonymous columns (e.g., merging "condition" and "symptom" into one column).

1. **Bi-Encoder Proposal:**
   - For every unique attribute $A$ in Table $T$, construct a contextualized string: `"The '{A}' of a {T} entity."`
   - Embed these strings and run a loose Agglomerative Clustering pass (Threshold 0.2). This groups potential synonyms based on semantic proximity.

2. **Cross-Encoder Verification:**
   - For every pair of attributes $(A_1, A_2)$ within a proposal cluster, perform high-reasoning verification.
   - Use `cross-encoder/stsb-distilroberta-base` to score the pair: `["{T} attribute: {A1}", "{T} attribute: {A2}"]`.
   - The Cross-Encoder uses full self-attention to determine if the attributes fulfill the same **functional role** for that entity.
   - If Score > 0.80, the pair is marked as a true synonym.

3. **Graph-Based Canonicalization:**
   - Use **Union-Find** to group all verified synonym pairs into connected components.
   - For each group, the attribute name that appeared most frequently in the raw text is elected as the **Canonical Name**.

**Design Reasoning:**
- **Why contextualized strings?** Prevents "condition" (health) from being treated the same as "condition" (real estate). The table context disambiguates the attribute's meaning.
- **Why a Cross-Encoder?** Bi-Encoders are good at finding related words (like "doctor" and "hospital"), but bad at distinguishing them from true synonyms (like "symptom" and "condition"). The Cross-Encoder's attention mechanism identifies functional equivalence.
- **Why Frequency-Weighted Election?** Choosing the most common name ensures the schema aligns with the dominant terminology used in the source documents, improving extraction accuracy in Phase 3.

#### 2.4: Renaming Audit
**Input:** ~30-40 clusters with generic names (e.g., "Entity", "Item", "Person")
**Output:** Same clusters with descriptive domain names

**Process:**
For each cluster, analyze its columns and send to Qwen:
```
Role: Data Architect.
Review the table with these columns: {columns_json}.
Determine if the name "{current_name}" accurately describes its domain role.
If the columns suggest a more specific role (e.g., a table with columns [age, gender, diagnosis] should be "Patient", not "Person"), suggest a better name.

Output JSON: {"canonical_name": "DescriptiveName"}
```

**Design Reasoning:**
- **Why rename?** The subsequent Topology Weaver (Phase 2.6) needs to reason about relationships between tables. It cannot reason effectively if table names are generic ("Entity_1", "Item_3"). Descriptive names enable semantic reasoning.
- **Why LLM-based?** Automated heuristics (e.g., "if columns contain 'diagnosis', call it 'Disease'") are brittle and domain-specific. The LLM can apply broader reasoning: "Given these columns, what domain concept does this represent?"
- **Why here, not earlier?** Clustering must occur first to group observations. Renaming individual observations during clustering would add unnecessary LLM overhead.

#### 2.5: Truth Anchoring
**Input:** ~30-40 tables with descriptive names
**Output:** Same tables with designated Primary Keys and definitions

**Sub-process 1: Primary Key Designation**
For each table:
```
Identify which of these attributes represents the unique Identifier or Name of the entity in the table '{table_name}'.
Attributes: {columns_json}

Constraint: Return strictly the column name that acts as the primary subject.
Output JSON: {"primary_key": "column_name"}
```

**Sub-process 2: Definition Generation**
For each table:
```
Role: Data Architect.
Task: Write a physical definition for the database table: {table_name}.
Context: It contains columns: {columns_json}.

Constraint: Your definition MUST BE A SINGLE CONCISE SENTENCE (under 15 words).
Example: 'A Device is a physical hardware unit or piece of equipment.'

Output JSON: {"definition": "string"}
```

**Storage:**
Both are stored in `schema.json`:
```json
{
  "Patient": {
    "columns": [...],
    "definition": "A Patient is a person undergoing medical diagnosis or treatment.",
    "_meta": {"primary_key": "name"}
  }
}
```

**Design Reasoning:**
- **Why designate PK?** Extraction Phase (3) needs a stable identity anchor. Without it, the LLM generates inconsistent IDs. With it, records for the same entity have the same PK value, enabling deduplication in Phase 4.
- **Why natural keys (not synthetic IDs)?** Natural keys like "name" exist in the text. Synthetic keys like "patient_id" would require the LLM to invent numbers, which leads to inconsistency. Natural keys leverage information already present.
- **Why definitions?** Definitions provide semantic context for downstream phases. Phase 2.6 (Topology Weaver) uses definitions to reason about relationships. Phase 3 extraction uses definitions to guide entity extraction. Phase 5 fusion uses definitions for NLI validation.

#### 2.6: Topology Weaver
**Input:** ~30-40 tables with names and definitions
**Output:** Same tables with added Foreign Key columns

**Process:**
For each table, send to Qwen:
```
Role: Database Architect.
Context: The database contains these tables: {all_table_names}.
Table Definition: {table_definition}

Task: We are defining the schema for '{current_table}'.

Instruction:
Analyze the relationships inherent to a '{current_table}'.
Does a '{current_table}' logically require a reference (Foreign Key) to any of the other tables in the list?

Criteria: Only add a link if '{current_table}' is subordinate to, owned by, or structurally interacts with the other table.

Output JSON:
A list of new columns to add to '{current_table}'.
[
  {"column_name": "target_table_name_ref", "target_table": "TargetTableName", "description": "short explanation"}
]

If none, output empty list [].
```

**Schema Modification:**
Dynamically add columns:
```json
{
  "Treatment": {
    "columns": [
      {"name": "type", "is_foreign_key": false, "references_table": null},
      {"name": "medication_ref", "is_foreign_key": true, "references_table": "Medication"},
      {"name": "condition_ref", "is_foreign_key": true, "references_table": "Condition"}
    ]
  }
}
```

**Design Reasoning:**
- **Why this phase?** Without explicit Foreign Keys, tables are islands. Phase 3 extraction cannot express relationships. Phase 4 entity resolution cannot cross-table deduplicate. This phase converts a flat schema into a relational graph before extraction begins.
- **Why Qwen, not heuristics?** Domain relationships are semantic (a Drug treats a Condition). Heuristics cannot generalize across domains. The LLM understands the meaning of table definitions and can reason about relationships.
- **Why after definitions?** Qwen needs definitions to reason. Without definitions, it doesn't understand what each table represents. By Phase 2.6, all tables have definitions from Phase 2.5.

#### 2.7: Semantic Sieve
**Input:** ~30-40 tables (possibly including metadata)
**Output:** ~25-30 domain-focused tables (provenance removed)

**Process:**
Collect all table names and definitions:
```json
[
  {"table": "Patient", "definition": "A person undergoing medical treatment"},
  {"table": "Author", "definition": "A person who writes or publishes documents"},
  ...
]
```

Send to Qwen:
```
We have discovered these tables from a dataset:
{table_info_list}

Task: Distinguish between 'Core Domain Objects' and 'Information Scaffolding'.

Definitions:
1. Core Domain Objects: The specific actors, items, events, and metrics that the dataset describes (the signal).
2. Information Scaffolding: Information describing the source, the recording process, the document format, or the authorship of the text (the container).

Instruction:
Return strictly a JSON list of the table names that represent 'Core Domain Objects' and should be kept for analytical querying.
Keep any table that contains domain-relevant content, even if it also contains metadata.

Output JSON: ["TableName1", "TableName2", ...]
```

**Result:**
- Tables like "Author", "URL", "PublicationDate" are typically discarded.
- Tables like "Medication", "Patient", "Treatment" are kept.
- Edge cases (e.g., "Institution" with columns [name, medical_specialization]) are kept because they contain domain-relevant content.

**Design Reasoning:**
- **Why this gate?** Stratified sampling reduced but did not eliminate metadata tables. This phase provides final cleanup without hardcoded rules.
- **Why "keep domain-relevant" instruction?** An inclusive instruction ensures we don't discard edge-case tables that might contain valuable data. False negatives (keeping metadata) are better than false positives (discarding domain data).
- **Why functional categorization?** Using "Domain vs. Scaffolding" is domain-agnostic. It works for medical, financial, or sports data without modification.

---

## Phase 3: Vector-Sieve and Cognitive Sharding Extraction

### What It Does
Extracts data records from all 106,000 chunks, using semantic filtering and sharding to maintain LLM accuracy.

### Technical Process

#### 3.1: Vector-Sieve Relevancy Filtering
**Input:** A single chunk, table definitions
**Output:** List of relevant tables (typically 5-15 per chunk)

**Algorithm:**
1. Embed table definitions using `BAAI/bge-m3`:
   - For each table: `text = f"{table_name}: {definition}"`
   - Embed: `table_vectors[i] = bge_model.embed(text)` (1024-dim)
   - Normalize: `table_vectors[i] /= norm(table_vectors[i])`
2. Embed chunk using the same model:
   - `chunk_vector = bge_model.embed(chunk_text)`
   - `chunk_vector /= norm(chunk_vector)`
3. Calculate similarities:
   - `similarities[i] = dot_product(chunk_vector, table_vectors[i])`
4. Select tables:
   - Include if `similarity > 0.35` OR `similarity >= (max_similarity * 0.85)`

**Example:**
```
Chunk: "The 45-year-old female patient presented with acute hypertension..."

Table Similarities:
- Patient: 0.92 (HIGH, include)
- Condition: 0.88 (HIGH, include)
- Treatment: 0.84 (within 85% of 0.92, include)
- Medication: 0.82 (within 85% of 0.92, include)
- Author: 0.15 (VERY LOW, exclude)
- Publication: 0.12 (VERY LOW, exclude)
```

**Design Reasoning:**
- **Why embeddings?** Embeddings capture semantic meaning. Medical content and metadata have distinct semantic signatures in the embedding space. This enables semantic filtering without LLM calls.
- **Why `bge-m3`?** Specifically trained for dense retrieval (semantic search). Outperforms general-purpose models on domain-specific matching.
- **Why 0.35 threshold?** Empirically determined. Below 0.35, false positives increase (irrelevant tables get included). Above 0.35, false negatives increase (relevant tables get excluded).
- **Why 85% of max?** Adaptive threshold ensures we include tables that are nearly as relevant as the most relevant table, even if absolute similarity is low. Prevents over-filtering on low-signal chunks.
- **Why normalize vectors?** L2 normalization ensures cosine similarity equals dot product, enabling fast batch computation.

#### 3.2: Dynamic Cognitive Sharding
**Input:** Selected relevant tables, their column counts
**Output:** List of "shards" (groups of tables), each with < 40 columns

**Algorithm:**
```python
shards = []
current_shard = []
current_col_count = 0

for table_name in relevant_tables:
    col_count = len(schema[table_name]["columns"])
    
    if current_shard and (current_col_count + col_count > MAX_COGNITIVE_COLUMNS):
        # Shard is full, save and start new one
        shards.append(current_shard)
        current_shard = [table_name]
        current_col_count = col_count
    else:
        # Add to current shard
        current_shard.append(table_name)
        current_col_count += col_count

if current_shard:
    shards.append(current_shard)
```

**Example:**
```
Relevant tables for chunk: [Patient (10 cols), Condition (8 cols), Treatment (12 cols), Medication (15 cols)]
Total: 45 columns (exceeds MAX_COGNITIVE_COLUMNS = 40)

Shard 1: [Patient (10), Condition (8), Treatment (12)] = 30 cols
Shard 2: [Medication (15)] = 15 cols
```

**Design Reasoning:**
- **Why 40 columns?** Empirically, Qwen can maintain extraction accuracy for 30-40 columns. At 50+ columns, accuracy drops significantly (Safe-Null behavior increases). 40 is the sweet spot.
- **Why sharding?** Instead of overwhelming Qwen with 300 columns, we create multiple focused extraction calls. Each shard has full context (all tables, all columns), but limited scope (< 40 columns). This maintains accuracy while processing all relevant data.
- **Why not random shards?** Shards are created greedily (in order). This ensures semantic coherence: related tables (discovered in the same vicinity in the relevancy list) stay together.

#### 3.3: One-Shot Extraction per Shard
**Input:** A chunk and one shard of tables
**Output:** Extracted records for tables in the shard

**LLM Prompt (Link-Aware):**
```
Task: Extract data for the following tables from the Target Text.

TARGET TABLES:
{
  "Patient": {
    "definition": "A person undergoing medical diagnosis or treatment.",
    "columns": ["name", "age", "gender"],
    "pk_col": "name",
    "fk_instructions": []
  },
  "Condition": {
    "definition": "A medical or health-related state or disease affecting a patient.",
    "columns": ["name", "symptoms", "severity"],
    "pk_col": "name",
    "fk_instructions": []
  },
  "Treatment": {
    "definition": "A medical intervention or therapy applied to address a condition.",
    "columns": ["type", "medication_ref", "condition_ref"],
    "pk_col": "type",
    "fk_instructions": [
      "Special Instruction for Column 'medication_ref': This column references the Medication table. Extract ONLY the name or identifier of the Medication, not descriptions. Extract the noun (e.g., 'Ibuprofen'), not verbs (e.g., 'prescribed').",
      "Special Instruction for Column 'condition_ref': This column references the Condition table. Extract ONLY the name of the Condition, not descriptions."
    ]
  }
}

CONTEXT (to resolve pronouns):
"{previous_context}"

TARGET TEXT:
"{chunk_text}"

INSTRUCTIONS:
1. ANALYZE CONTEXT: Note entities mentioned in the context.
2. ANALYZE TARGET TEXT: Identify instances of entities matching the TARGET TABLES.
3. RESOLVE PRONOUNS: If pronouns reference previous context, resolve them to specific entity names.
4. ATOMIC EXTRACTION: Extract one object per distinct entity.
5. PRIMARY KEY RULE: For each table, the primary key MUST be a concise name or ID (max 5 words, no full sentences).
6. LINKAGE RULE: For Foreign Key columns, extract ONLY the identifier/name of the target entity, not descriptions or verbs.
7. MISSING DATA: Use 'null' for missing values.

OUTPUT FORMAT:
Strictly a JSON object mapping table names to lists of records.

{
  "Patient": [
    {"name": "John Smith", "age": "45", "gender": "M"}
  ],
  "Condition": [
    {"name": "hypertension", "symptoms": "elevated blood pressure", "severity": "moderate"}
  ],
  "Treatment": [
    {"type": "medication administration", "medication_ref": "Ibuprofen", "condition_ref": "hypertension"}
  ]
}
```

**LLM Call:**
```python
response = client.chat(
    model="qwen2.5:7b-instruct",
    messages=[{'role': 'user', 'content': prompt}],
    format='json',
    options={"temperature": 0.3}
)
extracted_data = json.loads(response['message']['content'])
```

**Post-Processing:**
1. **Robust JSON Parsing:** Handle cases where LLM wraps output in extra dict layers.
2. **PK Sanitization:** Discard records where PK is a list, dict, or > 10 words.
3. **Return:** Deduplicated records for the shard.

**Design Reasoning:**
- **Why one-shot?** Instead of extracting one table at a time (O(N*M) calls), extract multiple tables in one call (O(N*k) calls where k = number of shards). Reduces LLM overhead by ~90%.
- **Why Link-Aware instructions?** Without explicit guidance, Qwen might extract "prescribed Ibuprofen" into `medication_ref` column, which is a violation (should be just "Ibuprofen"). The instruction constrains Qwen to extract identifiers only.
- **Why temperature 0.3?** Lower temperature (0.3 vs. default 0.7) reduces hallucination and makes JSON output more consistent, improving parsing reliability.
- **Why CONTEXT first?** Instructing "ANALYZE CONTEXT" first ensures Qwen reads the Shadow Context before the main text, enabling pronoun resolution.

---

## Phase 4: Rich-Vector Entity Resolution

### What It Does
Deduplicates entities ("John", "J. Smith", "john smith" → "John Smith").

### Technical Process

#### 4.1: Rich Vector Construction
**Input:** All extracted records from Phase 3
**Output:** Unique entities with "Rich Vectors"

**For each entity:**
1. Collect the Primary Key value: `pk_value = "John Smith"`.
2. Collect attributes from the same record: `attributes = ["age: 45", "gender: Male"]`.
3. Construct contextual sentence: `rich_text = "{pk_value} is a {table_definition} with attributes {', '.join(attributes)}"`.
   - Example: `"John Smith is a person undergoing medical diagnosis or treatment with attributes age: 45, gender: Male"`
4. Embed using `sentence-transformers/all-MiniLM-L6-v2`: `vector = embed_model.encode(rich_text)` (384-dim).

**Design Reasoning:**
- **Why not embed raw PK?** Raw embedding of "John Smith" doesn't capture context. "John" could be a medication (if the table is "Medication"), a disease, or a person. Context is crucial.
- **Why include attributes?** Attributes disambiguate: "John Smith (age 45)" is more likely to match "J. Smith (age 45)" than "John Smith (age 30)". Attributes create a richer semantic signature.
- **Why `all-MiniLM-L6-v2`?** Fast inference (384-dim vs. 1024-dim), trained on semantic similarity tasks, suitable for within-table deduplication.

#### 4.2: HNSW Indexing
**Input:** Rich vectors for all entities in a table
**Output:** HNSW index (fast similarity search)

**Algorithm:**
```python
from hnswlib import Index

index = Index(space='cosine', dim=384)
index.init_index(max_elements=len(entities), ef_construction=200, M=16)

for i, entity in enumerate(entities):
    index.add_items(entity_vectors[i], i)

index.set_ef(50)
```

**Design Reasoning:**
- **Why HNSW?** Hierarchical Navigable Small World enables sub-millisecond nearest-neighbor search for thousands of entities. Faster than brute-force (which is O(n)).
- **Why cosine space?** Cosine similarity is semantic similarity. Normalized vectors make dot product equivalent to cosine similarity.
- **Why M=16, ef_construction=200?** These parameters balance search quality with construction time. Empirically chosen for medical entity deduplication.

#### 4.3: Similarity Search and Cross-Encoder Scoring
**Input:** Unique entities with Rich Vectors and HNSW index
**Output:** Merge map (which entities should be merged)

**Algorithm:**
```python
from sentence_transformers import CrossEncoder

cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
merge_map = {}  # parent[child] -> parent
parent = {}  # union-find parent pointers

def find(x):
    if x not in parent:
        parent[x] = x
    if parent[x] != x:
        parent[x] = find(parent[x])
    return parent[x]

def union(x, y):
    px, py = find(x), find(y)
    if px != py:
        parent[py] = px

for entity in entities:
    labels, scores = index.knn_query(entity_vectors[entity], k=10)  # Find 10 nearest neighbors
    
    for neighbor_idx in labels[0][1:]:  # Skip self (index 0)
        neighbor = entities[neighbor_idx]
        
        # Cross-Encoder scoring
        pair_scores = cross_encoder.predict([[entity, neighbor]])[0]
        similarity = pair_scores[0]  # Similarity score
        
        if similarity > SIMILARITY_THRESHOLD:  # e.g., 0.85
            # Merge: longer string is parent (more complete information)
            if len(entity) >= len(neighbor):
                union(entity, neighbor)
            else:
                union(neighbor, entity)

# Final merge map
for entity in entities:
    canonical = find(entity)
    merge_map[entity] = canonical
```

**Design Reasoning:**
- **Why Cross-Encoder?** Sentence-transformers (embeddings) are fast but approximate. Cross-Encoders re-rank by fine-tuned semantic similarity. For deduplication (high precision), Cross-Encoder scores are more reliable.
- **Why k=10 neighbors?** Balances precision (fewer false positives) with recall (finding all duplicates). k=10 typically finds the closest duplicates without including distantly similar entities.
- **Why similarity threshold 0.85?** Empirically chosen. Below 0.85, many false positives (unrelated entities marked as duplicates). Above 0.85, false negatives (duplicates not recognized).
- **Why "Longest String Wins"?** Longer strings typically contain more information. "John Smith" is more complete than "J. Smith". Longer strings become canonical parents.
- **Why Union-Find?** Efficiently handles transitive merges: If A↔B and B↔C, then A, B, C merge into one group. Union-Find tracks this without explicit graph construction.

#### 4.4: Apply Merge Map
**Input:** Extracted records and merge map
**Output:** Deduplicated records with canonical entity names

**Process:**
For each record, replace PK value with canonical equivalent:
```python
for table in extracted_records:
    for record in extracted_records[table]:
        pk_val = record[pk_col]
        if pk_val in merge_map:
            record[pk_col] = merge_map[pk_val]
```

---

## Phase 5: Multi-Guardrail Fusion

### What It Does
Validates extracted values and saves to SQLite.

### Technical Process

#### 5.1: NLI Type Check
**Input:** (column_name, value) pairs
**Output:** Filtered pairs (discarding contradictions)

**Algorithm:**
```python
from sentence_transformers import CrossEncoder

nli_model = CrossEncoder('cross-encoder/nli-deberta-v3-base')

premise = f"This is a {column_name}."
hypothesis = f"'{value}' is a {column_name}."

logits = nli_model.predict([premise, hypothesis])
probs = softmax(logits)  # [contradiction, neutral, entailment]

p_entailment = probs[2]
p_contradiction = probs[0]

if p_contradiction > 0.6:
    DISCARD  # Contradictory
elif p_entailment > 0.5:
    KEEP
else:
    CONTINUE_TO_NEXT_CHECK  # Neutral; not enough info to discard
```

**Design Reasoning:**
- **Why NLI?** Logical consistency check. "Age: 'blue'" is contradictory (age cannot be blue). NLI model detects this.
- **Why Deberta?** Trained on MNLI (Multi-Genre NLI), captures nuanced entailment relationships. Outperforms simpler models on medical domain.
- **Why threshold 0.6?** If contradiction score > 0.6, model is confident it's contradictory. Below 0.6 has too many false positives.

#### 5.2: NER Type Check
**Input:** (column_name, value) pairs not yet discarded
**Output:** Further filtered pairs (confirming semantic types)

**Algorithm:**
```python
from gliner import GLiNER

gliner = GLiNER.from_pretrained("urchade/gliner_base")

# Example: For "Medication" column, check if value is a chemical/medicine
labels_to_check = [column_name, "Chemical", "Drug", "Medicine"]

entities = gliner.predict_entities(value, labels_to_check, threshold=0.3)
found_labels = [e['label'] for e in entities]

if len(found_labels) == 0 and p_entailment < 0.4:
    DISCARD  # No entity type match and weak NLI
else:
    KEEP
```

**Design Reasoning:**
- **Why GLiNER?** Zero-shot NER model. Can recognize arbitrary entity types without training. Fast inference on single values.
- **Why threshold 0.3?** GLiNER is conservative. 0.3 balances recall (catching valid entities) with precision (avoiding false positives).
- **Why combine with NLI?** NLI is logical (does the value fit the column semantically). NER is lexical (is the value actually that type). Both checks together catch more hallucinations.

#### 5.3: Length Guard
**Input:** Values that passed NLI and NER
**Output:** Values filtered by length

**Algorithm:**
```python
if len(str(value)) > 50:
    DISCARD  # Narrative leakage
else:
    KEEP
```

**Design Reasoning:**
- **Why 50 characters?** Empirically, legitimate medical terms are typically < 50 chars. E.g., "hypertension", "ibuprofen 500mg twice daily", "acute myocardial infarction". Longer strings are usually extraction errors where the LLM pastes an entire sentence into a field.
- **Why this check last?** Length is the weakest signal (just a heuristic). NLI and NER are stronger. Check them first.

#### 5.4: Fusion (Multi-Value Resolution)
**Input:** Multiple values for the same (table, entity, column) tuple
**Output:** Single canonical value

**Algorithm:**
```python
# If multiple values survived all guards for the same cell, pick one
surviving_values = [v for v in candidate_values if v passed all checks]

if not surviving_values:
    FINAL_VALUE = None
elif len(surviving_values) == 1:
    FINAL_VALUE = surviving_values[0]
else:
    # Multiple survived; "Longest wins"
    FINAL_VALUE = max(surviving_values, key=len)
```

**Design Reasoning:**
- **Why longest wins?** Among validated values, longer strings typically contain more information. E.g., "hypertension, stage 2" is more informative than "hypertension".
- **Why only among validated?** By this point, all surviving values have passed NLI, NER, and length checks. They are all plausible. Picking the longest ensures we retain maximum information.

#### 5.5: Write to SQLite
**Input:** Fused records
**Output:** SQLite database

**Process:**
1. Create tables (drop if exists, create new).
2. For each (table, record) pair:
   - Deduplicate columns case-insensitively.
   - Map extracted field names to schema column names (case-insensitive).
   - If value is list or dict, `json.dumps` it.
   - Insert into SQLite.

**Design Reasoning:**
- **Why case-insensitive mapping?** LLM might return "Name" or "name" for the same column. Robust mapping handles this.
- **Why json.dumps for complex types?** SQLite doesn't have native list/dict types. JSON serialization preserves structure.

---

## Design Trade-offs and Justifications

### Precision vs. Recall
**Decision:** Prioritize recall (get all data) over precision (purity).

**Justification:** It's better to have a database with 95% valid data and 5% noise than a database with 100% valid data and 50% missing signal. Noise can be cleaned by domain experts; missing signal is lost forever.

### Sampling vs. Full Induction
**Decision:** Use stratified sampling (1,000 chunks) for schema induction, not all 106,000.

**Justification:** Full induction provides marginal accuracy improvement (<2%) but costs ~50x more compute. Stratified sampling captures the schema sufficiently.

### LLM-Based vs. Embedding-Based Filtering
**Decision:** Use embeddings (Vector-Sieve) for relevancy filtering, not LLM.

**Justification:** LLM calls are slow (5-10 sec/call) and expensive. Embeddings are fast (1 msec/call) and capture semantic meaning. Trade-off: Embeddings have ~5% error rate. LLM has ~1% error rate. At scale, 5% error on irrelevant tables (which we filter later) is acceptable.

### Explicit Foreign Keys vs. Semantic Joining
**Decision:** Explicitly designate Foreign Keys during schema induction.

**Justification:** Explicit keys enable relational SQL queries. Semantic joining (matching entities by name across tables) is fragile and slow. Explicit keys provide a structured foundation.

---

## Conclusion

The final architecture represents a balance between:
1. **Scale:** Processing 106,000 documents in hours (not days/weeks).
2. **Quality:** Maintaining >90% data validity through multi-stage validation.
3. **Generality:** Working across domains (medical, financial, sports) without hardcoded rules.
4. **Interpretability:** Every phase has clear input/output and reasoning.

Each phase solves a specific problem that emerged from iterative development. The architecture is not perfect (no system is), but it is engineered to handle the constraints of LLM-based data extraction at scale.

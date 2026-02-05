# Semantic ETL: Technical Evolution and Final Architecture

## Problem Statement

We have 106,000 medical text documents that contain unstructured information. We want to convert this into a structured relational database (SQLite) with tables and relationships, enabling SQL queries.

Example: If a document says "Patient John was treated with Aspirin for headache," we want:
- A `Patient` table with row: name="John"
- A `Treatment` table with row: medication="Aspirin"
- A `Condition` table with row: name="headache"
- Foreign keys linking them to express the relationships

The fundamental constraint: Qwen2.5-7b (our LLM) cannot process 106,000 documents in one pass. We need a phased approach.

---

## Initial Architecture (Before Any Iterations)

### Phase 1: Shadow Context Ingestion
Input: Raw medical documents.
Output: Chunks with metadata.

**Process:**
1. Split each document into 500-1000 word chunks using sentence boundaries.
2. For each chunk, prepend the last 3 sentences from the previous chunk as metadata.

**Why:** Pronouns ("it", "they") often reference entities from adjacent text. This lookback enables resolution.

### Phase 2: Schema Induction
Input: ALL 106,000 chunks.
Output: Discovered database schema (list of tables with columns).

**Process:**
1. **Entity Observation:** For each chunk, send to Qwen: "Extract entity types and their attributes from this text."
   - Chunk: "The 45-year-old female patient presented with hypertension and diabetes."
   - Qwen response: `[{"type": "Patient", "attributes": ["age", "gender", "conditions"]}]`
2. **Clustering:** Collect all observations (potentially thousands). Group them using **Agglomerative Clustering**.
   - Algorithm: Average Linkage, Cosine Distance metric.
   - Fingerprint: `"{type}:{sorted_attributes}"` (e.g., "Patient:age,gender,conditions").
   - Similarity: If two fingerprints have high cosine similarity between their attribute embeddings, merge them.
   - Survival: Clusters with `Count >= 3` become canonical tables.

### Phase 3: Extraction
Input: ALL 106,000 chunks and the discovered schema.
Output: Extracted records for every chunk.

**Process:**
For each chunk, send to Qwen: "Extract records matching this schema: {schema_json}."
- Qwen responds: `{"Patient": [{"age": 45, "gender": "F", ...}], "Condition": [{"name": "hypertension"}, ...]}`.

**Key Issue:** If the schema has 30 tables × 10 columns = 300 columns in a single prompt, Qwen becomes confused and defaults to returning empty lists.

### Phase 4: Entity Resolution
Input: All extracted records from Phase 3 (potentially duplicates: "John", "J. Smith", "john smith" all refer to the same person).
Output: Deduplicated entity map.

**Process:**
1. For each table, collect all unique values in the Primary Key column.
2. Use `sentence-transformers/all-MiniLM-L6-v2` embeddings to convert each value into a 384-dimensional vector.
3. Build an **HNSW** (Hierarchical Navigable Small World) index for fast nearest-neighbor search.
4. For each entity, find similar entities and use a **Cross-Encoder** (`ms-marco-MiniLM-L-6-v2`) to score pairs.
5. If similarity > threshold, merge them (union-find data structure).

### Phase 5: Fusion and Guardrails
Input: Deduplicated records.
Output: Final SQLite database.

**Process:**
1. **NLI Validation:** For each (column, value) pair, check if value logically fits the column.
   - Premise: "This is a {column_type}."
   - Hypothesis: "{value} is a {column_type}."
   - Use `deberta-v3-base` NLI model to check entailment. If contradiction score > 0.6, discard.
2. **NER Validation:** Use GLiNER to confirm semantic type.
3. **Length Guard:** Discard values > 50 characters (narrative leakage).
4. **Fusion:** For multiple values in the same cell, keep the longest that passed all guards.
5. Save to SQLite.

---

## Version 1 → Version 2: Cognitive Overload and Sequential Processing

### What Happened

Running Phase 2 on all 106,000 chunks sequentially took ~6 days. Phase 3 returned almost no data.

### Root Cause Analysis

**Speed Issue:**
- Each LLM request to Qwen took 5-10 seconds.
- Sequential processing: 106,000 chunks × 7 seconds = 742,000 seconds ≈ 8.6 days.

**Empty Extraction:**
- Phase 2 discovers ~30 tables.
- In Phase 3, we send all 30 table definitions (~250 columns total) to Qwen in a single prompt.
- Qwen's attention mechanism (transformer) has a maximum effective context window for task-specific focus.
- With 250 columns, Qwen cannot maintain consistent output patterns and defaults to empty lists.
- We call this **"Safe-Null behavior"** — the model returns `{"Table1": [], "Table2": [], ...}` to avoid extracting incorrect data.

### The Fix

**For Speed:**
- Introduce `ThreadPoolExecutor` with `max_workers=50` to process chunks in parallel.
- Instead of 8.6 days, process ~50 chunks simultaneously on GPU.
- Theoretical speedup: ~50x (practical: ~40x due to I/O contention).

**For Empty Extraction:**
- Implement **Dynamic Cognitive Sharding**.
- Logic: If a chunk is relevant to multiple tables with combined columns > 40, split into multiple LLM calls.
- Initially, use LLM itself to determine relevancy: "Which of these tables appear in this text?" (This was slow and addressed in V4).
- Create shards: If chunk is relevant to tables with [30 cols, 35 cols, 25 cols] = 90 total, create 3 shards:
  - Shard 1: [30 + 10 from second table] = 40 cols
  - Shard 2: [25 from second table + 25 from third table] = 40 cols
  - Shard 3: [remaining] = 10 cols
- Send each shard separately to Qwen.

### Result

Processing time reduced to ~1-2 days. But database was still mostly empty. Sharding helped, but the fundamental problem remained: the schema itself was a problem.

---

## Version 2 → Version 3: Primary Key and Identity Crisis

### What Happened

Some data appeared, but SQLite insertion failed with `UNIQUE constraint failed` errors. Deduplication was impossible.

### Root Cause

Phase 3 extraction had no constraint on which attribute should be the unique identifier.

Example:
- Chunk 1: Qwen extracts `{"Patient": [{"id": 1, "name": "John Smith", "age": 45}]}`
- Chunk 5: Qwen extracts `{"Patient": [{"id": 5, "name": "John Smith", "age": 45}]}`

Both rows have `name = "John Smith"`, but different `id` values. In Phase 4, when deduplicating, we cannot determine if these are the same patient (no clear identity anchor).

### The Fix

Added **Phase 2.5: Truth Anchoring**.

**Sub-phase 1: Primary Key Designation**
- For each discovered canonical table, send to Qwen:
  - "These are the attributes: {attributes_list}. Which attribute represents the unique identifier or name of the entity?"
  - Qwen responds: `{"primary_key": "name"}`
- Store this in `schema.json` under `_meta.primary_key`.
- Fallback: If Qwen fails, use the first column.

**Sub-phase 2: Definition Generation**
- For each table, send to Qwen:
  - "Write a 1-sentence physical definition for a table with columns: {attributes}."
  - Qwen responds: "A Patient is a person undergoing medical diagnosis or treatment."
- Store in `schema.json` under `definition`.

**Constraint in Phase 3:**
- Modify extraction prompt: "The Primary Key for {table} is {pk_col}. Every extracted record MUST have a non-null value in this column."
- Qwen now uses consistent logic for identity: "name" is always the unique identifier for Patient.

### Result

Data had consistent identity. But schema contained tables like "Author", "Publication Date", "Blog Category" — administrative metadata, not medical signal.

---

## Version 3 → Version 4: Metadata Trap and Vector-Sieve

### What Happened

Schema contained 30+ tables; the top 15 were all administrative metadata. Medical tables were buried.

### Root Cause

**Why Metadata Dominated:**
- Medical article structure: Header (2 pages of metadata) → Content (48 pages of medical data) → Footer (metadata).
- Phase 2 processes all 106,000 chunks sequentially.
- Chunk 1-2: Author observations. Chunk 3-48: Medical observations.
- Agglomerative Clustering groups observations by fingerprint similarity.
- "Author" observations appear consistently (every document has an author). "Patient" observations appear in diverse forms ("Patient", "Individual", "Person") scattered across different chunks.
- Result: "Author" forms one massive, tight cluster. "Patient" fragments into multiple small clusters. Clustering algorithm prioritizes the tight "Author" cluster.

### The Fix

**Fix 1: Stratified Sampling**
- Instead of processing all 106,000 chunks in Phase 2, sample only 1,000 chunks.
- Use stratified (not random) sampling: Divide 106,000 chunks into 100 groups of 1,000. Sample 10 chunks from each group.
- Result: Sampled chunks are spread across different parts of different documents, reducing the proportion of pure metadata chunks.

**Fix 2: Vector-Sieve for Relevancy Filtering in Phase 3**
- Problem with LLM-based relevancy check: For each chunk, asking Qwen "Which tables are relevant?" takes 2-5 seconds. For 106,000 chunks, this adds weeks to total runtime.

**Vector-Sieve Process:**
1. Use `BAAI/bge-m3` embedding model (1024-dimensional vectors).
2. Embed each table definition: `"{table_name}: {definition}"`.
3. For each chunk, embed the text.
4. For each (chunk, table) pair, calculate **Cosine Similarity**: `dot_product(chunk_vector, table_vector) / (norm(chunk_vector) * norm(table_vector))`.
5. Threshold: Include table if similarity > 0.35 OR similarity >= (max_similarity × 0.85).

**Example:**
- Chunk: "Patient received Ibuprofen for headache"
  - Chunk vector: [0.1, 0.95, 0.05, 0.6, 0.2, ...]
- Medication table: "A Medication is a chemical compound used for treatment"
  - Table vector: [0.05, 0.9, 0.1, 0.55, 0.25, ...]
  - Cosine Similarity: 0.98 (HIGH) → Include
- Author table: "An Author is a person who writes documents"
  - Table vector: [0.8, 0.1, 0.05, 0.2, 0.9, ...]
  - Cosine Similarity: 0.15 (LOW) → Exclude

**Why This Works:**
- Embedding captures semantic meaning. Medical content and Author metadata have different semantic spaces.
- Dot product is O(d) where d=1024 (fast).
- No LLM calls needed → ~1000x faster than LLM-based relevancy.

### Result

Medical tables (Medication, Disease, Treatment) appeared in the schema. But they were structurally isolated — no Foreign Keys linking them.

---

## Version 4 → Version 5: Relational Island Problem

### What Happened

Schema had:
- `Medication` table: [name, dosage, form]
- `Condition` table: [name, symptoms]
- `Treatment` table: [type, duration]

But no way to express "This treatment uses this medication to treat this condition."

### Root Cause

Phase 2 discovers objects (entities) but not relationships (connections).

When Qwen processes "The patient was treated with Ibuprofen for headache," it extracts:
- Entity observation 1: `{"type": "Medication", "attributes": ["name"]}`
- Entity observation 2: `{"type": "Condition", "attributes": ["name"]}`

It never says: "Medication references Condition."

### The Fix

Added **Phase 2.6: Topology Weaver**.

**Process:**
1. After Phase 2.5 (Truth Anchoring), we have all canonical table definitions.
2. For each table, send to Qwen:
   - "You have these tables in your database: {list_of_all_tables_with_definitions}. For the {current_table} table, does it logically need to reference any other table via a Foreign Key? If yes, add them."
   - Qwen responds: `[{"column_name": "condition_ref", "target_table": "Condition", "description": "The condition this treatment addresses"}]`
3. Modify schema.json to add new columns: `{"name": "condition_ref", "is_foreign_key": true, "references_table": "Condition"}`

**Constraint in Phase 3:**
- Modify extraction prompt: "For Foreign Key column {fk_col}, extract ONLY the identifier (noun) of the {target_table}, not descriptions."
- Qwen extracts: `{"Treatment": [{"type": "Drug Administration", "condition_ref": "hypertension"}]}` (not "treating the patient's hypertension").

### Result

Schema became relational. But Weaver failed because table names were still generic ("Entity_1", "Item_47"). Qwen didn't understand what to link.

---

## Version 5 → Version 6: Generic Names Problem

### What Happened

Topology Weaver couldn't find relationships because table names were nonsensical.

### Root Cause

Agglomerative Clustering names tables by the most common type name in the cluster. If a cluster mixed observations, it might get a generic name.

### The Fix

Added **Phase 2.4: Renaming Audit** (runs before Topology Weaver).

**Process:**
1. For each discovered cluster (table), analyze its attributes.
2. Send to Qwen:
   - "A table has these columns: {columns}. What domain concept does this represent?"
   - Qwen responds: `{"canonical_name": "Patient"}`
3. Rename the table.

**Result:**
- "Entity_1" with columns [age, gender, diagnosis] → renamed to "Patient"
- "Item_47" with columns [name, dosage] → renamed to "Medication"

Now Topology Weaver can reason: "Should Medication link to Condition? Yes, medications treat conditions."

---

## Version 6 → Version 7: Over-Pruning and Balance

### What Happened

Attempted to discard non-domain tables, but also lost rare domain entities.

### Root Cause

Agglomerative Clustering survival threshold was `Count >= 3`. Rare but important domain entities (appearing only 2 times in 1,000 sampled chunks) were discarded.

### The Fix

Two changes:

**Change 1: Lower Threshold**
- Threshold: `Count >= 3` → `Count >= 2`.
- Rare entities now survive.

**Change 2: Semantic Sieve (Phase 2.7)**
- For each table, send to Qwen:
  - "Is this table a 'Core Domain Entity' (the main subjects of analysis) or 'Provenance Information' (administrative context)? Keep if domain-relevant."
  - Inclusive instruction: Keep any table with domain content.
- Qwen categorizes and returns list of tables to keep.

### Result

Schema now contains 29 domain-specific tables with 10+ Foreign Keys. Clean, relational, domain-focused.

---

## Final Architecture (V7)

### Phase 1: Shadow Context Ingestion
- Split documents into 500-1000 word chunks.
- Prepend last 3 sentences from previous chunk as metadata for pronoun resolution.

### Phase 2: Schema Induction
**2.1: Stratified Sampling**
- Sample 1,000 chunks spread across dataset.

**2.2: Entity Observation**
- Qwen extracts entity types and attributes from sampled chunks.

**2.3: Agglomerative Clustering**
- Group observations by attribute fingerprint similarity (cosine metric).
- Survival threshold: `Count >= 2`.

**2.4: Renaming Audit**
- Qwen renames generic cluster names to descriptive domain roles.

**2.5: Truth Anchoring**
- Qwen designates Primary Key and generates 1-sentence definition per table.

**2.6: Topology Weaver**
- Qwen identifies logical Foreign Key relationships between tables.

**2.7: Semantic Sieve**
- Qwen categorizes tables as domain or provenance.
- Keep domain-relevant tables; discard pure provenance.

### Phase 3: Vector-Sieve and Cognitive Sharding Extraction
- For each chunk:
  1. Embed chunk with `bge-m3`.
  2. Calculate cosine similarity to all table definitions.
  3. Select tables with similarity > 0.35 or within 85% of max.
  4. If selected tables have > 40 combined columns, split into shards (each < 40 columns).
  5. Send each shard to Qwen with "Link-Aware" prompt: Foreign Key columns = identifier only.

### Phase 4: Rich-Vector Entity Resolution
- Embed each extracted entity as: `"{pk_value} is a {table_definition} with attributes {attrs}"`.
- Use HNSW index for similarity search.
- Cross-Encoder scores pairs; merge if similarity > threshold.

### Phase 5: Multi-Guardrail Fusion
1. **NLI Check (Deberta-v3):** Verify entailment. Discard contradictions.
2. **NER Check (GLiNER):** Confirm semantic types.
3. **Length Guard:** Discard strings > 50 chars.
4. **Fusion:** Select highest-quality surviving value.
5. Write to SQLite.

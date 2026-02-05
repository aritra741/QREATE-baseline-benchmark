# QAIRS Architecture Documentation

## System Overview

QAIRS (Query-Aware Incremental Relational Synthesis) is a workload-driven text-to-database extraction system that minimizes LLM calls through intelligent preprocessing and query optimization.

## Core Components

### 1. The Sieve (`sieve.py`)

**Purpose:** Fast chunk filtering without LLM calls

**Data Structure:**
```python
{
  "chunk_id": {
    "dict_tags": ["USA", "Denied"],
    "type_mask": {"has_date": true, "has_money": true},
    "entities": {"PERSON": ["John Doe"]}
  }
}
```

**Operations:**
- Dictionary matching via FlashText (Aho-Corasick algorithm)
- Type detection via compiled regex patterns
- Optional NER via spacy/GLiNER
- Query interface for candidate chunk retrieval

**Performance:** O(n) build time, O(log n) query time

### 2. Metadata Registry (`registry.py`)

**Purpose:** Track materialization state and enable subsumption logic

**Schema:**
```sql
CREATE TABLE metadata_registry (
  id SERIAL PRIMARY KEY,
  table_name VARCHAR(255),
  predicate_scope TEXT,  -- SQL WHERE clause
  status ENUM('pending', 'partial', 'materialized', 'failed'),
  chunks_processed INT,
  rows_extracted INT,
  last_updated TIMESTAMP
);
```

**Key Operations:**
- `check_predicate()`: Query materialization status
- `register_predicate()`: Add new predicate to track
- `update_status()`: Update after extraction
- `find_subsumption()`: Check if predicate is subsumed by existing

### 3. LLM Client (`llm_client.py`)

**Purpose:** Interface with Ollama for Qwen 2.5

**Features:**
- JSON mode with retry logic
- Fallback JSON extraction from malformed responses
- Connection validation
- Timeout handling

**API:**
```python
client.generate(prompt, system_prompt, json_mode=True)
client.generate_json(prompt, max_retries=3)
```

### 4. Extractor (`extractor.py`)

**Purpose:** LLM-based structured data extraction

**Prompt Structure:**
```
TASK: Extract structured data
SCHEMA: [Table definition]
DICTIONARY MAPPING: [Synonym mappings]
FILTER: [WHERE clause]
OUTPUT FORMAT: [JSON schema]
CONSTRAINTS: [Extraction rules]
INPUT TEXT: [Chunk content]
```

**View Synthesis:** Supports extracting denormalized views for joins

### 5. Workload Planner (`planner.py`)

**Purpose:** Multi-Query Optimization (MQO) using Predicate Lattice

**Components:**
- `SQLParser`: Parse SQL using `sqlglot`, extract predicates
- `PredicateLattice`: Build subsumption DAG using `networkx`
- `WorkloadPlanner`: Generate optimized execution plan

**Algorithm:**
1. **Parse**: Convert SQL to AST, extract predicates in DNF
2. **Normalize**: Convert WHERE clauses to comparable form
3. **Build Lattice**: Create DAG where edge A→B means A subsumes B
4. **Find Siblings**: Identify queries with no subsumption (merge candidates)
5. **Merge**: Combine categorical predicates on same column (key optimization)
6. **Generate Plan**: Create minimal set of extraction tasks

**Key Insight:** "The cost of asking Qwen for 'Denied' is nearly identical to asking for 'Denied OR Paid'"

**Optimization:** Minimizes LLM invocations per chunk (not disk I/O)

### 6. Query Engine (`query_engine.py`)

**Purpose:** Main query execution interface

**Workflow:**
```
SQL Query
  ↓
Parse → Extract (table, predicate)
  ↓
Check Registry
  ↓
├─ MATERIALIZED → Execute SQL directly
├─ PENDING/NULL → Trigger extraction
│    ↓
│    Query Sieve → Get candidate chunks
│    ↓
│    Extract via LLM
│    ↓
│    Insert into DB
│    ↓
│    Update Registry
│    ↓
└─── Execute SQL
```

## Data Flow

### Phase 1: Preprocessing (Build)

```
Corpus → Chunking → Sieve Construction
                      ↓
                   Dictionary (LLM once)
                      ↓
                   FlashText Index
                      ↓
                   Regex Patterns
                      ↓
                   Save to Disk
```

### Phase 2: Query Planning (Offline)

```
SQL Workload
  ↓
Parse (sqlglot) → Extract Predicates → Normalize to DNF
  ↓
Build Lattice (networkx)
  ↓
Subsumption Analysis → Find Siblings
  ↓
Sibling Merging (Categorical OR)
  ↓
Sieve Query (Union of Terms)
  ↓
Optimized Task List → Save to JSON
```

### Phase 3: Runtime Execution

```
SQL Query → Parse → Registry Check
                        ↓
                    Not Materialized
                        ↓
                    Sieve Pruning
                        ↓
                    LLM Extraction (batched)
                        ↓
                    Schema Validation
                        ↓
                    DB Insert
                        ↓
                    Registry Update
                        ↓
                    Execute SQL
```

## Key Algorithms

### Subsumption Logic (Implemented)

**Problem:** Determine if one predicate subsumes another

**Implementation:**
```python
def subsumes(p1: NormalizedPredicate, p2: NormalizedPredicate) -> bool:
    """
    Check if p1 subsumes p2 (p1 is more general).
    
    Examples:
    - Empty predicate subsumes all
    - "cost > 500" subsumes "cost > 1000"
    - "status IN ('A', 'B', 'C')" subsumes "status = 'A'"
    """
    # Group conditions by column
    # Check set containment for categorical
    # Check range containment for numeric
```

**DAG Structure:**
- Nodes = Queries
- Edge A → B = A subsumes B
- Siblings = No edge in either direction (merge candidates)

### Sibling Merging (The Key Optimization)

**Problem:** Minimize LLM calls for related queries

**Heuristic:**
```
Q1: SELECT * FROM claims WHERE status = 'Denied'
Q2: SELECT * FROM claims WHERE status = 'Paid'

Analysis:
- Same table ✓
- Same column (status) ✓
- Categorical predicates (EQ) ✓
- No subsumption (siblings) ✓

Action: Merge into synthetic parent
Merged: SELECT * FROM claims WHERE status IN ('Denied', 'Paid')

Benefit: Process each chunk ONCE for both queries
Cost Savings: ~50% fewer LLM calls
```

### Dictionary Expansion

**One-time LLM call to generate synonyms:**
```
Input: ["Denied", "Paid", "USA"]
LLM Prompt: "Generate synonyms for: Denied"
Output: ["Rejected", "Declined", "Refused"]
Build Map: {"Rejected" → "Denied", "Declined" → "Denied"}
```

### View Synthesis

**Extract denormalized views to ensure referential integrity:**
```python
# Instead of:
Claims: {id, patient_id, status}
Patients: {id, name}

# Extract:
ClaimsView: {claim_id, patient_id, patient_name, status}
```

## Performance Characteristics

### Time Complexity
- **Sieve Build:** O(n × m) where n = chunks, m = avg chunk length
- **Sieve Query:** O(log n) with indexed lookups
- **Extraction:** O(k × t) where k = candidate chunks, t = LLM latency

### Space Complexity
- **Sieve:** O(n) for index storage
- **Registry:** O(p) where p = number of predicates
- **Corpus:** O(n × m) in memory (can be disk-backed)

### Optimization Opportunities
1. **Parallel Extraction:** Process chunks concurrently
2. **Caching:** Cache LLM responses for identical chunks
3. **Incremental Updates:** Only re-process changed chunks
4. **Adaptive Batching:** Adjust batch size based on LLM latency

## Configuration

See `config.yaml` for all tunable parameters:
- LLM settings (model, temperature, timeout)
- Database connection
- Sieve parameters (regex patterns, dictionary expansion)
- Extraction settings (batch size, retries)

## Testing

Run test suite:
```bash
python test_system.py
```

Tests cover:
- Sieve construction and querying
- Registry operations
- LLM extraction (requires Ollama)
- End-to-end query execution

## Future Enhancements

1. **Advanced Subsumption:** Implement logical predicate subsumption
2. **Incremental Maintenance:** Handle corpus updates efficiently
3. **Query Optimization:** Cost-based query planning
4. **Distributed Execution:** Scale to large corpora with distributed processing
5. **Schema Learning:** Automatic schema inference from queries
6. **Active Learning:** Use user feedback to improve extraction

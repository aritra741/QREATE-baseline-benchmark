# Quick Start Guide: HNSW-Union-Find Integration

## TL;DR

The GEM system now uses **streaming HNSW-Union-Find blocking** with **discriminative LLM resolution** to prevent over-merging distinct entities while consolidating synonyms.

```python
# Old way (batch blocking)
mentions = extract_all_mentions(records)
blocks = blocker.block_entities(records, key_attrs)

# New way (streaming with integrated clustering)
for mention in stream_mentions(records, key_attrs):
    blocker.add_and_link(mention)  # Incremental HNSW + Union-Find

blocks = blocker.get_blocks()  # Connected components
```

---

## Running Tests

### 1. Integrated HNSW-Union-Find Test

```bash
cd /Users/aritramazumder/Documents/UDA-Bench-main

# Clear cache
rm -rf systems/GEM/.cache

# Run test
python systems/GEM/test_hnsw_union_find.py
```

**Expected Output:**
```
✓ TEST 1 PASS: Found all 3 iPhone 15 variants
✓ TEST 2 PASS: Found 2 Galaxy variants  
✓ TEST 3 PASS: Synonyms consolidated
```

### 2. Run with Real Data

```bash
python run_challenging_queries.py --systems gem --dataset Med --query-id join_1
```

---

## Code Examples

### Example 1: Using SemanticBlocker

```python
from GEM.blocking import SemanticBlocker

# Initialize
blocker = SemanticBlocker(blocking_threshold=0.85)
blocker.load_embedding_model()

# Stream mentions through integrated HNSW-Union-Find
mentions = ["iPhone 15", "iphone 15", "Apple iPhone 15", 
            "iPhone 15 Pro", "iphone 15 pro", "15 Pro",
            "iPhone 15 Pro Max", "iphone 15 pro max"]

for mention in mentions:
    idx = blocker.add_and_link(mention)  # O(d) per mention
    print(f"Added mention #{idx}: '{mention}'")

# Get blocks (connected components)
blocks = blocker.get_blocks()
for representative, synonyms in blocks.items():
    print(f"{representative}:")
    for syn in synonyms:
        print(f"  - {syn}")
```

**Output:**
```
iPhone 15:
  - iPhone 15
  - iphone 15
  - Apple iPhone 15
iPhone 15 Pro:
  - iPhone 15 Pro
  - iphone 15 pro
  - 15 Pro
iPhone 15 Pro Max:
  - iPhone 15 Pro Max
  - iphone 15 pro max
```

### Example 2: Using LLMClient

```python
from GEM.llm import LLMClient

llm = LLMClient()

# Resolve a candidate block
mentions = ["iPhone 15 Pro", "iphone 15 pro", "15 Pro", 
            "iPhone 15 Pro Max"]  # Mixed block

resolution = llm.resolve_block(mentions)
print(json.dumps(resolution, indent=2))
```

**Output:**
```json
{
  "iPhone 15 Pro": ["iPhone 15 Pro", "iphone 15 pro", "15 Pro"],
  "iPhone 15 Pro Max": ["iPhone 15 Pro Max"]
}
```

### Example 3: Full Pipeline

```python
from GEM.blocking import SemanticBlocker
from GEM.ingest import InlineDeduplicator
from GEM.db_engine import DBEngine

# Initialize
blocker = SemanticBlocker()
db_engine = DBEngine()

# Ingest with streaming HNSW-Union-Find
deduplicator = InlineDeduplicator(blocker, resolver, db_engine, schema)
final_records, canonical_map = deduplicator.ingest_batch(
    records, 
    key_attributes=["product_name"]
)

# canonical_map now contains:
# {"iphone 15": "iPhone 15", "iphone 15 pro": "iPhone 15 Pro", ...}

# Insert to database
db_engine.insert_records("products", final_records)

# Query (uses semantic shim for canonical rewriting)
result = db_engine.execute_query("SELECT * FROM products WHERE name = 'iphone 15'")
# Rewritten as: SELECT * FROM products WHERE name = 'iPhone 15'
```

---

## Key Classes and Methods

### SemanticBlocker

```python
class SemanticBlocker:
    # Initialize with streaming state
    def __init__(blocking_threshold=0.85)
    
    # Add mention incrementally with K=1 search and union
    def add_and_link(mention_text: str) -> int
    
    # Get all connected components
    def get_blocks() -> Dict[str, List[str]]
    
    # Encode texts (unchanged from before)
    def encode_texts(texts: List[str]) -> np.ndarray
```

### LLMClient

```python
class LLMClient:
    # Resolve a block using discriminative LLM
    def resolve_block(mentions: List[str]) -> Dict[str, List[str]]
    
    # Resolve multiple blocks
    def resolve_blocks(blocks: Dict[str, List[str]]) -> Dict
```

### InlineDeduplicator

```python
class InlineDeduplicator:
    # Phase 1 + 2: Streaming blocking + LLM resolution
    def ingest_batch(records: List[Dict], 
                     key_attributes: List[str]) -> (List[Dict], Dict)
    
    # Phase 3: Canonical normalization
    def finalize() -> List[Dict]
```

### DBEngine

```python
class DBEngine:
    # Type cleaning for numerics
    def _clean_numeric_value(value: str, target_type: str) -> Any
    
    # Safe SQL rewriting with word boundaries
    def _safe_replace_mention(mention: str, canonical: str, sql: str) -> str
    
    # Execute query with semantic shim
    def execute_query(sql: str) -> DataFrame
```

---

## Configuration

### `systems/GEM/config.py`

```python
# Blocking threshold (0-1, higher = stricter)
BLOCKING_THRESHOLD = 0.85

# LLM configuration
OLLAMA_MODEL = "qwen2.5:7b-instruct"  # Must support JSON output
RESOLUTION_TIMEOUT = 30
RESOLUTION_MAX_RETRIES = 3

# Storage
DB_PATH = Path.cwd() / ".cache" / "gem.sqlite"
```

---

## Behavior Changes

### Old Behavior
```
Input: 13 product mentions with variants
Blocking: All 13 mentions clustered together
Output: 1 mega-block
Risk: Over-merging (Pro merged with Pro Max)
```

### New Behavior
```
Input: 13 product mentions with variants
Phase 1: Streaming HNSW-Union-Find creates smart blocks
  - iPhone 15 group (base, iphone 15, Apple iPhone 15)
  - iPhone 15 Pro group (Pro, iphone 15 pro, 15 Pro)
  - iPhone 15 Pro Max group (Pro Max, iphone 15 pro max)
Phase 2: Discriminative LLM resolution
  - Confirms: iPhone 15, Pro, and Pro Max are DISTINCT
Output: 3 separate canonical entities
Result: ✓ No over-merging, ✓ Synonyms consolidated
```

---

## Verification Checklist

When testing, ensure:

- [ ] iPhone 15 (base), Pro, and Pro Max are **3 distinct rows**
- [ ] Galaxy S24 and S24 Ultra are **2 distinct rows**
- [ ] Synonyms like "iphone 15" consolidated under "iPhone 15"
- [ ] `WHERE price > 1000` works without type errors
- [ ] Query for "iPhone 15" doesn't match "iPhone 15 Pro"

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Over-merged entities | Blocking threshold too low | Increase BLOCKING_THRESHOLD to 0.90+ |
| Under-merged synonyms | Blocking threshold too high | Decrease BLOCKING_THRESHOLD to 0.80 |
| Type conversion errors | Schema mismatch | Check schema has correct type mappings |
| LLM returns free text | Model doesn't support JSON | Use qwen2.5:7b-instruct or compatible |
| Slow processing | Sequential LLM calls | Use async (future enhancement) |

---

## Performance Tips

1. **Batch multiple datasets** - Process in parallel
2. **Cache embeddings** - Reuse encoder outputs
3. **Use smaller LLM** - For fast resolution
4. **Adjust thresholds** - Balance precision vs recall

---

## File Reference

| File | Purpose | Status |
|------|---------|--------|
| `blocking.py` | HNSW-Union-Find integration | ✅ Refactored |
| `llm.py` | Discriminative resolution | ✅ Created |
| `ingest.py` | Streaming pipeline | ✅ Refactored |
| `db_engine.py` | Type cleaning + safe SQL | ✅ Enhanced |
| `resolver.py` | Entity resolver | ✅ Enhanced |
| `test_hnsw_union_find.py` | Test suite | ✅ Created |
| `IMPLEMENTATION_COMPLETE.md` | Full docs | ✅ Created |

---

## Next Steps

1. **Run tests:** `python systems/GEM/test_hnsw_union_find.py`
2. **Check output:** Verify 3 iPhone variants and 2 Galaxy variants
3. **Run with real data:** `python run_challenging_queries.py --systems gem`
4. **Inspect database:** Check canonical mappings and distinct entities

---

## Questions?

Refer to:
- `IMPLEMENTATION_COMPLETE.md` - Full system overview
- `REFACTORING_HNSW_UNION_FIND.md` - Technical details
- Code comments in `blocking.py`, `llm.py`, `ingest.py`


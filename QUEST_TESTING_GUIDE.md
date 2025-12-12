# QUEST Testing Guide - How to Test QUEST Like UQE

## Overview

This guide shows you how to set up QUEST for testing in `run_challenging_queries.py`, mirroring the UQE implementation pattern.

---

## 1. Current Testing Architecture (UQE Example)

### How UQE is Tested

In `run_challenging_queries.py`, the **UQERunner** class follows this pattern:

```python
class UQERunner(SystemRunner):
    # Schema mapping: (dataset, entity) → (module, class, data_path, table_name)
    SCHEMA_MAP = {
        ("Med", "disease"): ("schema.disease", "DiseaseData", "disease", "disease"),
        ("Player", "player"): ("schema.nba", "NBAData", "nba", "player"),
        # ...
    }
    
    def run_query(self, query):
        # 1. Parse SQL
        # 2. Load schema class (e.g., DiseaseData)
        # 3. Create planner with source_data
        # 4. Execute plan
        # 5. Return result DataFrame
```

**Key Steps:**
1. **Initialization**: Load system modules dynamically
2. **Schema Loading**: Map datasets to schema classes
3. **Query Execution**: Parse → Plan → Optimize → Execute
4. **Result Handling**: Convert to DataFrame for comparison

---

## 2. Setting Up QUEST Testing

### Step 1: Understand QUEST Architecture

From `/systems/quest/tests/sf1.py` and `sfw1.py`, QUEST follows this pipeline:

```
SQL Query
    ↓
Parse (sqlparser.parse_sql)
    ↓
Logical Planning (LogicalPlanner.build_logical_plan)
    ↓
Load Indexer + Sampler (load_all_indexer, AttrSampler)
    ↓
Physical Planning (TextPhysicalPlanner.build)
    ↓
Process (Processer().process)
    ↓
Result DataFrame
```

### Step 2: Key QUEST Modules to Import

```python
from quest.sql.parser import sqlparser
from quest.sql.planner.logical import LogicalPlanner
from quest.sql.planner.physical import TextPhysicalPlanner
from quest.sql.processer.processer import Processer
from quest.db.indexer.indexer import load_all_indexer
from quest.core.llm.sampler import AttrSampler
from quest.core.llm.llm_query import TextLLMQuerier
```

### Step 3: Prepare Attribute Schemas

QUEST needs attribute definitions in the format:
```
attr_name: description
attr_name2: description2
...
```

These come from `/Query/{Dataset}/{Dataset}_attributes.json`.

---

## 3. Implementation: QuestRunner Class

### Current Issue

The **QuestRunner** in `run_challenging_queries.py` (lines 386-660) is partially implemented but has issues:
- ✅ Loads indexer
- ✅ Builds attribute schema
- ✅ Handles SPJ queries
- ⚠️ May not properly handle result conversion
- ⚠️ Needs verification with actual data

### Complete Implementation Steps

#### A. Create Query Attribute Schema Mapping

```python
# Similar to UQE's SCHEMA_MAP
# Map dataset → attribute file path

QUEST_ATTRIBUTE_FILES = {
    "Med": PROJECT_ROOT / "Query" / "Med" / "Med_attributes.json",
    "Player": PROJECT_ROOT / "Query" / "Player" / "Player_attributes.json",
    "Art": PROJECT_ROOT / "Query" / "Art" / "Art_attributes.json",
    "Legal": PROJECT_ROOT / "Query" / "Legal" / "Legal_attributes.json",
    "Finan": PROJECT_ROOT / "Query" / "Finan" / "Finan_attributes.json",
}
```

#### B. Load and Format Attributes

```python
def load_attributes(dataset: str, entity: str) -> str:
    """
    Load attributes from JSON and format as:
    attr_name: description
    attr_name2: description2
    """
    attr_file = QUEST_ATTRIBUTE_FILES.get(dataset)
    if not attr_file or not attr_file.exists():
        return None
    
    attributes = load_json(attr_file)
    
    # Get attributes for this entity
    entity_attrs = attributes.get(entity, {})
    
    # Format as "attr_name: description" (one per line)
    attr_lines = []
    for attr_name, attr_info in entity_attrs.items():
        description = attr_info.get("description", "")
        attr_lines.append(f"{attr_name}: {description}")
    
    return "\n".join(attr_lines)
```

#### C. Updated QuestRunner.run_query()

Key changes to the current implementation:

```python
def run_query(self, query: Dict) -> Tuple[Optional[pd.DataFrame], Dict]:
    self._ensure_init()
    
    query_id = query["id"]
    sql = query["sql"]
    dataset = query["dataset"]
    entity = query.get("entity", "").lower()
    query_type = query.get("type", "unknown")
    
    # 1. Skip unsupported query types
    if query_type in ["aggregation", "union"]:
        # QUEST only supports SPJ (Selection-Projection-Join)
        return None, metadata_unsupported
    
    try:
        start_time = time.time()
        
        # 2. Parse SQL
        ast = self.sqlparser.parse_sql(sql)
        
        # 3. Build Logical Plan
        logical_planner = self.LogicalPlanner()
        logical_plan = logical_planner.build_logical_plan(ast)
        
        # 4. Load Indexer
        # CRITICAL: Pass table_to_type=None to load ALL pre-built indexes
        gb_indexer = self.load_all_indexer(table_to_type=None)
        
        # 5. Build Attribute Schema
        prompt_str = load_attributes_formatted(dataset, entity)
        
        # 6. Create Sampler & Querier
        gb_sampler = self.AttrSampler(schema=prompt_str)
        gb_querier = self.TextLLMQuerier(prompt=prompt_str)
        
        # 7. Initialize Sampler with Evidence
        indexer_obj, _ = gb_indexer.get_indexer(entity)
        gb_sampler.try_sample(indexer_obj, prompt_str)
        
        # 8. Build Physical Plan
        physical_planner = self.TextPhysicalPlanner(
            gb_indexer, gb_querier, sampler=gb_sampler
        )
        physical_plan = physical_planner.build(logical_plan)
        
        # 9. Execute
        processer = self.Processer()
        result = processer.process(physical_plan)
        
        # 10. Convert Result to DataFrame
        result_df = self._convert_result_to_dataframe(result)
        
        metadata["status"] = "completed"
        metadata["total_time"] = time.time() - start_time
        metadata["result_count"] = len(result_df) if result_df else 0
        
    except Exception as e:
        metadata["status"] = "failed"
        metadata["error"] = str(e)
    
    return result_df, metadata


def _convert_result_to_dataframe(self, result):
    """Convert QUEST result to pandas DataFrame."""
    if result is None:
        return None
    
    if isinstance(result, pd.DataFrame):
        return result
    elif isinstance(result, list):
        return pd.DataFrame(result)
    elif hasattr(result, 'to_dataframe'):
        return result.to_dataframe()
    else:
        # Try to wrap in DataFrame
        try:
            return pd.DataFrame([result])
        except:
            return None
```

---

## 4. Prerequisites for QUEST Testing

### Required Setup

1. **Index Building**
   ```bash
   # Build QUEST indexes for all datasets
   cd systems/quest
   python -c "from quest.db.indexer.indexer import build_all_indexer; build_all_indexer()"
   ```

2. **Ollama Server Running**
   ```bash
   ollama pull qwen2.5:7b-instruct
   ollama serve  # In one terminal
   ```

3. **QUEST Configuration** (`systems/quest/conf/settings.py`)
   ```python
   LLM_MODEL = 'ollama/qwen2.5:7b-instruct'
   API_BASE = 'http://localhost:11434'
   ```

4. **Embedding Models**
   ```bash
   ollama pull nomic-embed-text
   ```

### Dependencies
```bash
pip install -r systems/quest/requirements.txt
```

---

## 5. Testing QUEST vs UQE

### Quick Test

```bash
# Test only QUEST on specific query types
python run_challenging_queries.py --systems quest --query-types filter projection simple

# Compare with UQE
python run_challenging_queries.py --systems uqe --query-types filter projection simple
```

### Check Results

```bash
# View detailed results
cat results/challenging_queries/*/detailed_report.json | jq '.systems.quest'
cat results/challenging_queries/*/detailed_report.json | jq '.systems.uqe'

# Compare F1 scores by query type
cat results/challenging_queries/*/detailed_report.json | jq '.by_query_type'
```

---

## 6. Key Differences: QUEST vs UQE

| Aspect | QUEST | UQE |
|--------|-------|-----|
| **Query Types** | SPJ only (no aggregation, union) | Selection-Projection-Join |
| **Index** | Two-level (document + segment) | Single-level document index |
| **LLM Cost** | Minimized via evidence-augmented retrieval | Standard RAG approach |
| **Optimization** | Instance-optimized (per-document) | Uniform planning |
| **Data Path** | Uses built CSV files | Custom schema classes |
| **Sampling** | Automatic evidence collection | Configurable |

---

## 7. Expected Query Support

Based on QUEST paper (Section 2.1 "Supported Queries"):

✅ **Supported:**
- Selections with filters (WHERE clauses)
- Projections (SELECT columns)
- Joins (multi-table queries)
- Filter combinations (AND, OR, ranges)

❌ **Not Supported:**
- Aggregations (GROUP BY, COUNT, SUM, etc.)
- Unions (UNION, UNION ALL)
- Complex subqueries

---

## 8. Modifications Needed to run_challenging_queries.py

### Current Implementation (Lines 386-660)

The QuestRunner is mostly there but needs:

1. **Fix attribute loading** - Currently just creates empty schema
2. **Fix result conversion** - Currently may not convert properly to DataFrame
3. **Add evidence sampling** - Currently tries to sample but may need tuning
4. **Error handling** - Needs better error messages

### Recommended Changes

```python
# In QuestRunner._ensure_init()
# Add this after importing modules:

self.logger.info("[QUEST] Loading from:", PROJECT_ROOT / "systems" / "quest")
self.logger.info("[QUEST] Using Ollama at: http://localhost:11434")
self.logger.info("[QUEST] LLM Model: qwen2.5:7b-instruct")

# In QuestRunner.run_query()
# After loading indexer, add validation:
if not gb_indexer.table_to_indexer:
    metadata["status"] = "requires_index"
    metadata["error"] = "No indexes loaded. Run: python build_quest_indexes.py"
    return None, metadata
```

---

## 9. Debugging & Troubleshooting

### Common Issues

1. **"No module named 'quest'"**
   - Add to sys.path: `sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))`

2. **Index not found**
   - Run: `python build_quest_indexes.py` or `build_all_indexer()`

3. **Ollama connection failed**
   - Ensure Ollama is running: `ollama serve`
   - Check endpoint: `curl http://localhost:11434/api/tags`

4. **Empty results**
   - Check if sampler initialized: `gb_sampler.map_attr_evidence`
   - Verify schema format: attribute descriptions needed

5. **Attribute not in schema**
   - Verify `/Query/{Dataset}/{Dataset}_attributes.json` exists
   - Check entity name matches (case-sensitive)

---

## 10. Next Steps

1. **Immediate**: Verify indexer is built and Ollama is running
2. **Test**: Run a simple filter query manually
   ```bash
   python run_challenging_queries.py --systems quest --query-types filter
   ```
3. **Validate**: Check results and compare with UQE
4. **Iterate**: Add to full test suite once working

---

## References

- **QUEST Paper**: `systems/quest/quest.pdf.md`
- **QUEST Tests**: `systems/quest/tests/sf1.py`, `sfw1.py`
- **UQE Implementation**: `run_challenging_queries.py` lines 662-915
- **Current QUEST Implementation**: `run_challenging_queries.py` lines 386-660

---

## Research Context

This is for your research comparing LLM-powered query systems on unstructured data:
- **QUEST**: Query optimization focused on minimizing LLM cost
- **UQE**: Unstructured query execution engine
- **Baseline**: For comprehensive evaluation of text-to-data extraction

Track these metrics:
- **Accuracy**: Precision, Recall, F1-score
- **Efficiency**: Token count, execution time
- **Correctness**: Row/attribute matching


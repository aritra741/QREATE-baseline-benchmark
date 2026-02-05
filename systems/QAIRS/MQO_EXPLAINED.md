# Multi-Query Optimization (MQO) in QAIRS

## The Problem

Given a workload of SQL queries, how do we minimize expensive LLM calls?

**Example Workload:**
```sql
Q1: SELECT * FROM claims WHERE status = 'Denied'
Q2: SELECT * FROM claims WHERE status = 'Paid'
Q3: SELECT * FROM claims WHERE cost > 1000
Q4: SELECT * FROM claims WHERE status IN ('Denied', 'Paid')
Q5: SELECT * FROM claims
```

**Naive Approach:**
- Execute 5 separate extraction passes
- Scan corpus 5 times
- Make 5N LLM calls (where N = number of chunks)

**QAIRS Approach:**
- Analyze relationships between queries
- Merge overlapping queries
- Execute minimal set of extraction tasks

---

## The Solution: Predicate Lattice

### Step 1: Parse & Normalize

Using `sqlglot`, we parse each query into a normalized predicate:

```
Q1: (table=claims, conditions=[(status, EQ, 'Denied')])
Q2: (table=claims, conditions=[(status, EQ, 'Paid')])
Q3: (table=claims, conditions=[(cost, GT, 1000)])
Q4: (table=claims, conditions=[(status, IN, ['Denied', 'Paid'])])
Q5: (table=claims, conditions=[])  # No filter
```

### Step 2: Build Subsumption DAG

Using `networkx`, we build a directed graph where edge A → B means "A subsumes B":

```
        Q5 (no filter)
       / | \
      /  |  \
     /   |   \
    Q4   |    Q3
   / \   |
  /   \  |
 Q1   Q2 |
```

**Relationships:**
- Q5 subsumes everything (no filter = all rows)
- Q4 subsumes Q1 and Q2 (IN clause covers both)
- Q3 is independent

### Step 3: Find Siblings

Siblings are queries with **no subsumption relationship**. These are candidates for merging.

**Sibling Groups:**
- Group 1: {Q1, Q2} - Both filter on `status` with EQ
- (Q3 is alone - different column)

### Step 4: Merge Siblings (The Key Optimization)

For sibling group {Q1, Q2}:

**Analysis:**
- Same table: ✓
- Same column: `status` ✓
- Categorical predicates: EQ ✓
- Disjoint values: 'Denied' vs 'Paid' ✓

**Action:** Create synthetic parent query
```sql
Q_merged: SELECT * FROM claims WHERE status IN ('Denied', 'Paid')
```

**Why This Works:**
The cost of asking Qwen 2.5:
> "Extract rows where status is 'Denied'"

is nearly identical to:
> "Extract rows where status is 'Denied' OR 'Paid'"

Both fit in the same prompt. The LLM processes the chunk once and extracts both types.

### Step 5: Generate Execution Plan

**Optimized Plan:**
```json
{
  "tasks": [
    {
      "task_id": "task_merged_Q1_Q2",
      "table": "claims",
      "predicate": "status IN ('Denied', 'Paid')",
      "trigger_queries": ["Q1", "Q2"],
      "sieve_filter": {
        "dict_keys": ["Denied", "Paid"],
        "types": ["has_money"]
      }
    },
    {
      "task_id": "task_Q3",
      "table": "claims",
      "predicate": "cost > 1000",
      "trigger_queries": ["Q3"],
      "sieve_filter": {
        "types": ["has_money"]
      }
    }
  ]
}
```

**Result:**
- Original: 5 queries → 5 extraction passes
- Optimized: 5 queries → 2 extraction passes
- Savings: 60% fewer LLM calls

---

## Runtime Behavior

### When Q1 Arrives

1. **Router checks Registry:** Is `status='Denied'` materialized?
2. **No** → Check execution plan
3. **Plan says:** Q1 belongs to `task_merged_Q1_Q2`
4. **Execute merged task:** Extract both 'Denied' AND 'Paid'
5. **Update Registry:**
   - `status='Denied'` → MATERIALIZED
   - `status='Paid'` → MATERIALIZED
6. **Return results** for Q1

### When Q2 Arrives (Later)

1. **Router checks Registry:** Is `status='Paid'` materialized?
2. **Yes** → Execute SQL directly from database
3. **No LLM call needed!**

---

## Technical Implementation

### SQL Parsing (sqlglot)

```python
import sqlglot
from sqlglot import exp, parse_one

sql = "SELECT * FROM claims WHERE status = 'Denied'"
parsed = parse_one(sql, read="postgres")

# Extract table
table = parsed.find(exp.Table).name  # "claims"

# Extract WHERE clause
where = parsed.find(exp.Where)

# Normalize to DNF
from sqlglot.optimizer.normalize import normalize
normalized = normalize(where.this)

# Extract conditions
# Result: [("status", EQ, "Denied")]
```

### Subsumption Check

```python
def subsumes(p1: NormalizedPredicate, p2: NormalizedPredicate) -> bool:
    """Check if p1 is more general than p2."""
    
    # Empty predicate subsumes all
    if not p1.conditions:
        return True
    
    # Group by column
    p1_vals = p1.get_categorical_values("status")  # {'Denied', 'Paid'}
    p2_vals = p2.get_categorical_values("status")  # {'Denied'}
    
    # Check set containment
    return p2_vals.issubset(p1_vals)  # True
```

### Lattice Construction (networkx)

```python
import networkx as nx

graph = nx.DiGraph()

# Add nodes
for query_id, predicate in predicates.items():
    graph.add_node(query_id, predicate=predicate)

# Add edges (subsumption)
for q1, q2 in combinations(query_ids, 2):
    if subsumes(predicates[q1], predicates[q2]):
        graph.add_edge(q1, q2)  # q1 → q2
```

### Sibling Detection

```python
def find_siblings(graph: nx.DiGraph) -> list[list[str]]:
    """Find nodes with no edges between them."""
    siblings = []
    
    for q1, q2 in combinations(graph.nodes(), 2):
        # No edge in either direction = siblings
        if not graph.has_edge(q1, q2) and not graph.has_edge(q2, q1):
            # Check if they can be merged
            if can_merge(q1, q2):
                siblings.append([q1, q2])
    
    return siblings
```

---

## Comparison with Standard MQO

| Aspect | Database MQO | QAIRS MQO |
|--------|--------------|-----------|
| **Optimization Target** | Minimize disk I/O | Minimize LLM calls |
| **Cost Model** | Disk seeks, block reads | Token count, latency |
| **Merging Strategy** | Shared table scans | Shared chunk processing |
| **Subsumption** | Index usage | Predicate containment |
| **Output** | Query execution plan | Extraction task plan |

**Key Difference:** Database MQO optimizes for physical access patterns. QAIRS MQO optimizes for **semantic extraction batching**.

---

## Example: Real-World Savings

**Scenario:** Medical claims analysis workload
- 100 queries on `claims` table
- 50 queries filter on `status` (10 unique values)
- 30 queries filter on `cost` (various ranges)
- 20 queries filter on `insurer` (5 unique values)

**Without MQO:**
- 100 extraction passes
- 100N LLM calls

**With QAIRS MQO:**
- Merge 50 status queries → 1 task: `status IN (v1, v2, ..., v10)`
- Merge 20 insurer queries → 1 task: `insurer IN (i1, i2, ..., i5)`
- Keep 30 cost queries separate (range predicates)
- **Total: 32 extraction passes**
- **Savings: 68% fewer LLM calls**

At $0.10 per 1M tokens and 1000 tokens/chunk:
- Without MQO: $10,000
- With MQO: $3,200
- **Savings: $6,800**

---

## Future Enhancements

1. **Range Merging:** Merge `cost > 1000` and `cost > 500` into `cost > 500`
2. **Multi-Column Merging:** Handle predicates on multiple columns
3. **Cost-Based Selection:** Choose merging strategy based on estimated savings
4. **Adaptive Planning:** Re-plan based on actual extraction costs
5. **Incremental Maintenance:** Update plan as new queries arrive

---

## References

- **Harinarayan et al.** "Implementing Data Cubes Efficiently" (SIGMOD 1996)
- **Sellis, T.** "Multiple-Query Optimization" (TODS 1988)
- **sqlglot Documentation:** https://github.com/tobymao/sqlglot
- **NetworkX Documentation:** https://networkx.org/

# UQE Run Analysis (20251210_223238)

## Summary
**Total Queries:** 17  
**Completed:** 3 (18%)  
**Failed:** 8 (47%)  
**Unsupported:** 6 (35%)  

### Results by Query Type

| Type | Total | Completed | Failed | Unsupported | Notes |
|------|-------|-----------|--------|-------------|-------|
| Simple | 2 | 1 | 1 | - | Basic projection query works |
| Filter | 3 | 0 | 3 | - | **All failed** - schema attribute issues |
| Projection | 3 | 2 | 1 | - | 2 art/medical queries succeeded |
| Join | 3 | - | - | 3 | **Not supported by UQE** (as designed) |
| Aggregation | 3 | 0 | 3 | - | **All failed** - not implemented in UQE |
| Union | 3 | - | - | 3 | **Not supported by UQE** (as designed) |

---

## Key Findings

### 1. **Unsupported Query Types (Expected)**
As documented in the UQE paper (Section 3, UQL Semantics), UQE currently has limitations:

- **JOIN queries:** The paper explicitly states "we limit our attention to sourcing from a single table in this paper" (page 3)
- **UNION queries:** Not mentioned as supported in the UQL grammar (Appendix B.2)

These 6 queries are correctly marked as `unsupported` - this is **expected behavior**.

---

## 2. **Schema Attribute Mismatch** 🔴 (Main Issue - Explains All Failures)

The UQE schema files have a **critical disconnect** between what they define and what the executor tries to use.

### Visual Breakdown:

**What UQE Schema ACTUALLY Defines:**
```python
# File: systems/UQE/schema/disease.py (lines 19-27)
disease_schema = {
    "id": "varchar",
    "description": "text",     # ← ONLY 2 COLUMNS!
}

disease_columns = [
    "id",
    "description",
]
```

**What Queries Request:**
```sql
-- filter_1 query trying to use:
SELECT disease_name, pathogenesis, prognosis, quality_of_life_impact, treatment_challenges
FROM disease
WHERE pathogenesis = 'autoimmune' ...
-- ↑ Asking for 5 attributes
```

**But Wait - The Attributes ARE Defined Elsewhere:**
```python
# File: systems/UQE/schema/disease.py (lines 156-178)
def columns_with_attr_type_init(self):
    columns_with_attr_type["description"] = {
        "disease_name": "varchar",           # ← Defined here!
        "disease_type": "varchar",
        "pathogenesis": "varchar",          # ← Defined here!
        "etiology": "varchar",
        "diagnostic_methods": "varchar",
        ...
        "treatment_challenges": "varchar",  # ← Defined here!
        "quality_of_life_impact": "varchar" # ← Defined here!
    }
```

**And They're Fully Described in the Data Schema:**
```python
# File: Query/Med/Med_attributes.json
{
  "disease": {
    "disease_name": {...},
    "disease_type": {...},
    "pathogenesis": {...},
    "etiology": {...},
    ...
    "treatment_challenges": {...},
    "quality_of_life_impact": {...}
  }
}
```

### The Error Chain:

1. Query asks for `pathogenesis` column
2. Executor calls `get_col_type('pathogenesis')` (line 147 of disease.py)
3. Code looks in `self.schema[table_name]['schema'][col_name]`
4. But `schema` only has `{'id', 'description'}` → **KeyError!**
5. Never checked `columns_with_attr_type` which HAS the attribute

### Why This Happened:

The `disease_schema` dict (lines 19-27) should have ALL 18 attributes, not just 2:

```python
# WRONG (current):
disease_schema = {
    "id": "varchar",
    "description": "text",
}

# RIGHT (should be):
disease_schema = {
    "id": "varchar",
    "description": "text",
    "disease_name": "varchar",
    "disease_type": "varchar",
    "pathogenesis": "varchar",
    "etiology": "varchar",
    # ... all 18 attributes
}
```

This is a **schema initialization bug** - the schema dict was never properly populated with the attribute list.

---

## 3. **Successful Queries**

✅ **simple_1:** "Simple projection query on disease"
- Duration: 176.7s
- Only selects `disease_name, disease_type` 
- Both happen to be defined in `columns_with_attr_type`

✅ **projection_2:** "Inference-heavy medical attributes" 
- Duration: 383.3s
- Med dataset, disease entity

✅ **projection_3:** "Multi-modal image attributes"
- Duration: 2129.9s (35+ minutes!)
- Art dataset - this is why it took so long

**Observation:** Simpler queries that use fewer attributes are more likely to succeed (by chance if attributes are in the list).

### 4. **Aggregation Failures**
All 3 aggregation queries failed. According to the UQE paper:

> "Extension: The above estimator can be used for other aggregation operations such as SUM and AVERAGE, including GROUP BY, and allowing concrete columns as operands as well. However, some aggregations such as MAX does not admit such an estimator." (Section 4.1.1, page 4)

The UQE implementation in `systems/UQE/` appears incomplete for aggregation queries.

---

## Root Cause Analysis Summary

### Primary Issue: Schema Definition Incomplete
- **File:** `systems/UQE/schema/disease.py` (and similarly for other schemas)
- **Problem:** `disease_schema` dict only contains 2 columns instead of all 18
- **Impact:** Any query asking for attributes beyond these 2 fails with `KeyError`

### Secondary Issue: Incomplete Aggregation Implementation
The UQE codebase doesn't fully implement aggregation support despite the paper describing it.

### Design Limitations (Expected)
Per the UQE paper, UQE is intentionally limited to:
- ✅ Single-table queries (no JOIN)
- ✅ Selection-Projection-Filter operations
- ⚠️ Aggregation (theoretical support, implementation incomplete)
- ❌ UNION operations (out of scope)

---

## How to Fix This

### Quick Fix: Update Schema Dicts

For `systems/UQE/schema/disease.py`, lines 19-27:

```python
disease_schema = {
    "id": "varchar",
    "description": "text",
    "disease_name": "varchar",
    "disease_type": "varchar",
    "pathogenesis": "varchar",
    "etiology": "varchar",
    "diagnostic_methods": "varchar",
    "common_symptoms": "varchar",
    "complications": "varchar",
    "affected_organs": "varchar",
    "treatments": "varchar",
    "drugs": "varchar",
    "prognosis": "varchar",
    "sequelae": "varchar",
    "epidemiology": "varchar",
    "risk_factors": "varchar",
    "preventive_measures": "varchar",
    "diagnosis_challenges": "varchar",
    "treatment_challenges": "varchar",
    "quality_of_life_impact": "varchar"
}

disease_columns = [
    "id", "description", "disease_name", "disease_type", "pathogenesis",
    "etiology", "diagnostic_methods", "common_symptoms", "complications",
    "affected_organs", "treatments", "drugs", "prognosis", "sequelae",
    "epidemiology", "risk_factors", "preventive_measures", 
    "diagnosis_challenges", "treatment_challenges", "quality_of_life_impact"
]
```

Similar fixes needed for:
- `systems/UQE/schema/art.py`
- `systems/UQE/schema/drug.py`
- `systems/UQE/schema/institutes.py`
- `systems/UQE/schema/lcr.py`
- `systems/UQE/schema/fin.py`
- `systems/UQE/schema/nba.py`

### Medium Fix: Implement/Fix Aggregation
- Check `systems/UQE/execute.py` and related files
- Verify aggregation operators (COUNT, SUM, AVG) are fully implemented

---

## Paper vs. Implementation Gap

The UQE paper describes **theoretical capabilities** for:
- Stratified sampling for aggregation (Algorithm 1)
- Online learning for retrieval (Algorithm 2)
- Semantic GROUP BY (Section 4.2.2)

But the actual implementation in `systems/UQE/` appears to be a **simplified version** that:
1. Has incomplete schema definitions
2. Doesn't fully implement aggregation features

**This is common in research code** - the paper shows the full vision, but the implementation may be partial or research-grade.

---

## Performance Notes

- **Simple projection:** ~3 minutes
- **Complex projection (images):** ~35+ minutes
- **Consistent failure:** Schema-dependent, not random

The long runtime for image-based queries suggests LLM calls for vision understanding are expensive.

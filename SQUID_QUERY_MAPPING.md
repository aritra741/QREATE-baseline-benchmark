# SQUiD Query Mapping

This document maps the original challenging queries to SQUiD-compatible SQL queries.

**Key Points:**
1. Original queries use generic table names (disease, player, finance)
2. SQUiD creates separate tables for each document: disease_0, disease_1, ... disease_N
3. We UNION ALL these tables to query across all documents
4. Table structures are IDENTICAL across all documents, so UNION works perfectly

---

## Med/disease Queries

### simple_1: List all diseases with their types
**Original Intent**: Get disease names, types, and prognosis

**Original SQL**:
```sql
SELECT disease_name, disease_type, prognosis
FROM disease
```

**SQUiD SQL** (UNION ALL pattern):
```sql
SELECT id, name AS disease_name, category AS disease_type
FROM disease_0
UNION ALL
SELECT id, name, category
FROM disease_1
UNION ALL
...
LIMIT 50
```

**Notes:**
- `disease_name` maps to `name` column
- `disease_type` maps to `category` column
- `prognosis` is not in the denormalized `joined_rows` (would need to join with treatment/causes)
- For simplicity, return id, name, category

---

## Player/player Queries

### simple_2: List all NBA players with their positions and nationalities
**Original Intent**: Get names, positions, nationalities, and teams

**Original SQL**:
```sql
SELECT name, position, nationality, team
FROM player
```

**SQUiD SQL** (UNION ALL pattern):
```sql
SELECT name, position
FROM player_0
UNION ALL
SELECT name, position
FROM player_1
UNION ALL
...
LIMIT 50
```

**Notes:**
- `nationality` is not in player table (it's in the achievement table which tracks nba_championships, mvp_awards, olympic_gold_medals)
- `team` is in a separate team table
- SQUiD's denormalized `joined_rows` would have already joined these if the schema extraction was complete
- Return: name, position (core player attributes)

---

## Finan/finance Queries

### projection_3: Extract financial and operational data from companies
**Original Intent**: Get company names, activities, revenue, net profit, total assets, risks

**Original SQL**:
```sql
SELECT company_name, principal_activities, revenue, 
       net_profit_or_loss, total_assets, business_risks
FROM finance
```

**SQUiD SQL** (UNION ALL pattern):
```sql
SELECT c.id, c.name AS company_name, c.industry,
       CAST(SUM(r.amount) AS REAL) AS total_revenue,
       CAST(SUM(np.amount) AS REAL) AS total_net_profit,
       CAST(SUM(a.amount) AS REAL) AS total_assets
FROM company_0 c
LEFT JOIN revenue_0 r ON c.id = r.company_id
LEFT JOIN net_profit_0 np ON c.id = np.company_id
LEFT JOIN assets_0 a ON c.id = a.company_id
GROUP BY c.id, c.name, c.industry
UNION ALL
SELECT c.id, c.name, c.industry,
       CAST(SUM(r.amount) AS REAL),
       CAST(SUM(np.amount) AS REAL),
       CAST(SUM(a.amount) AS REAL)
FROM company_1 c
LEFT JOIN revenue_1 r ON c.id = r.company_id
LEFT JOIN net_profit_1 np ON c.id = np.company_id
LEFT JOIN assets_1 a ON c.id = a.company_id
GROUP BY c.id, c.name, c.industry
...
LIMIT 50
```

---

## Strategy for run_challenging_queries.py

Modify `SQUiDRunner._rewrite_sql_for_squid_tables()` to:

1. **Detect all available document IDs** from `ensemble_data` by counting unique indices
2. **Build UNION ALL queries** instead of just replacing table names
3. **Handle JOIN operations** within each document's tables
4. **Maintain query intent** while working with actual schema

Example for simple query:
```python
# Old: SELECT * FROM disease
# New: SELECT * FROM disease_0 UNION ALL SELECT * FROM disease_1 UNION ALL ...
```

Example for complex query:
```python
# Old: SELECT c.name, SUM(r.amount) FROM company JOIN revenue ...
# New: (SELECT c.name, SUM(r.amount) FROM company_0 c JOIN revenue_0 r ...)
#      UNION ALL
#      (SELECT c.name, SUM(r.amount) FROM company_1 c JOIN revenue_1 r ...)
#      ...
```



# UQE Test Queries

This directory contains UQL (Unstructured Query Language) test queries for the UQE optimization system.

## Query Structure

Queries are organized by dataset and query type:
```
query/
  ├── disease/
  │   ├── SF/          (Select-Filter: simple WHERE clauses)
  │   └── SFW/         (Select-Filter-Where: complex predicates)
  └── player/
      ├── SF/          (Select-Filter)
      └── SFW/         (Select-Filter-Where)
```

## Query Format

All queries follow UQL syntax (a dialect of SQL for unstructured data):

```sql
SELECT * FROM table WHERE "natural language condition"
```

**Examples:**
- `SELECT * FROM disease WHERE "discusses pain relief"`
- `SELECT * FROM player WHERE "player plays guard position"`

## Testing

### Run with Optimizations Enabled
```bash
cd systems/UQE
python main.py --dataset disease --query-type SF --optimize
```

### Run without Optimizations (Baseline)
```bash
python main.py --dataset disease --query-type SF --baseline
```

### Compare Results
Results are saved to:
- `result/disease/SF_optimized/TIMESTAMP/` (with optimizations)
- `result/disease/SF_baseline/TIMESTAMP/` (without optimizations)

## Supported Query Types

- **SF** (Select-Filter): Simple semantic filtering queries
- **SFW** (Select-Filter-Where): Complex queries with multiple conditions
- **JOIN**: Multi-table queries (not yet supported in UQE - future work)

## Current Queries

### Disease Dataset (Healthcare)
1. `query_pain_relief.sql` - Documents discussing pain management
2. `query_surgery.sql` - Documents discussing surgical procedures
3. `query_medication.sql` - Documents discussing medications/drugs
4. `query_hospital.sql` - Documents discussing hospitals/medical centers
5. `query_mental_health.sql` - Documents discussing mental health conditions

### Player Dataset (NBA)
1. `query_guards.sql` - Players who play guard position
2. `query_usa_players.sql` - Players from USA
3. `query_mvp_winners.sql` - Players with MVP or championship history
4. `query_college_players.sql` - Players who attended college

## Adding New Queries

To add a new query:

1. Create a `.sql` file in the appropriate directory
2. Use UQL syntax: `SELECT * FROM table WHERE "condition"`
3. Run the query through UQE

Example:
```bash
cat > systems/UQE/query/disease/SF/query_new.sql << 'EOF'
SELECT * FROM disease WHERE "discusses cancer treatment"
EOF
```

Then run:
```bash
python main.py --dataset disease --query-type SF --optimize
```

## Notes

- Queries use natural language conditions that are evaluated by LLMs
- Optimizations include stratified sampling and active learning
- Results are approximate due to sampling - this is expected behavior
- For research: compare optimized vs baseline to measure improvement

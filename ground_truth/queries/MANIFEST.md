# Ground Truth Manifest for UDA-Bench Challenging Queries

**Generated**: Query execution against raw data (independent of any specific system run)

## Summary

- **Total Queries**: 17
- **Ground Truth Files Generated**: 8
- **Requires Manual Creation**: 9

### Breakdown by Query Type

| Type | Total | Generated | Manual |
|------|-------|-----------|--------|
| Simple | 2 | 2 | 0 |
| Filter | 3 | 3 | 0 |
| Projection | 3 | 3 | 0 |
| Join | 3 | 0 | 3 |
| Aggregation | 3 | 0 | 3 |
| Union | 3 | 0 | 3 |

## Generated Ground Truth Files (8)

### Simple Queries (2/2) ✓

#### simple_1.csv
- **Type**: Simple Projection
- **Dataset**: Med (disease)
- **SQL**: `SELECT disease_name, disease_type FROM disease`
- **Rows**: 100
- **Columns**: 2 (disease_name, disease_type)
- **Status**: Complete

#### simple_2.csv
- **Type**: Simple Projection
- **Dataset**: Player
- **SQL**: `SELECT name, nationality, position FROM player`
- **Rows**: 141
- **Columns**: 3 (name, nationality, position)
- **Status**: Complete

### Filter Queries (3/3) ✓

#### filter_1.csv
- **Type**: Multi-attribute filtering
- **Dataset**: Med (disease)
- **Conditions**: 
  - pathogenesis = 'autoimmune'
  - prognosis = 'chronic_condition'
  - quality_of_life_impact = 'work_disability'
  - treatment_challenges != 'drug resistance'
- **Rows**: 0 (no exact matches in dataset)
- **Columns**: 5 (disease_name, pathogenesis, prognosis, quality_of_life_impact, treatment_challenges)
- **Status**: Complete (correctly empty)

#### filter_2.csv
- **Type**: Legal case filtering
- **Dataset**: Legal (legal_case)
- **Conditions**:
  - first_judge = '1'
  - case_type = 'Commercial Case'
  - case_number >= 10
  - fine_amount != '20000.00'
- **Rows**: 13
- **Columns**: 7 (judge_name, plaintiff, defendant, charges, first_judge, case_number, verdict)
- **Status**: Complete

#### filter_3.csv
- **Type**: Art entity filtering
- **Dataset**: Art (Wikiart)
- **Conditions**:
  - marriage = 'Divorced'
  - century = '20th'
- **Rows**: 2
- **Columns**: 4 (name, art_movement, birth_country, birth_city)
- **Note**: Virtual columns (style, composition, tone, image_genre) from Art dataset are not included in this ground truth
- **Status**: Complete (physical columns only)

### Projection Queries (3/3) ✓

#### projection_1.csv
- **Type**: Financial data extraction
- **Dataset**: Finan (financial_record)
- **SQL**: `SELECT principal_activities, revenue, net_profit_or_loss FROM financial_record`
- **Rows**: 100
- **Columns**: 3 (principal_activities, revenue, net_profit_or_loss)
- **Status**: Complete

#### projection_2.csv
- **Type**: Medical attributes extraction
- **Dataset**: Med (disease)
- **SQL**: `SELECT disease_name, pathogenesis, prognosis FROM disease`
- **Rows**: 100
- **Columns**: 3 (disease_name, pathogenesis, prognosis)
- **Status**: Complete

#### projection_3.csv
- **Type**: Art entity attributes
- **Dataset**: Art (Wikiart)
- **SQL**: `SELECT name, nationality, birth_date, field, genre FROM art`
- **Rows**: 1000
- **Columns**: 5 (name, nationality, birth_date, field, genre)
- **Note**: Virtual columns (style, theme, object, color, tone, composition, image_genre) not included
- **Status**: Complete (physical columns only)

## Manual Creation Required (9)

### Join Queries (3)

#### join_1.csv
- **Type**: Three-way join
- **Dataset**: Med
- **Tables**: disease, drug, institution
- **Status**: ⚠️ Requires manual creation
- **Note**: Complex multi-table join with semantic matching

#### join_2.csv
- **Type**: Four-way join
- **Dataset**: Player
- **Tables**: player, team, manager, city
- **Status**: ⚠️ Requires manual creation
- **Note**: Complex NBA entity relationships

#### join_3.csv
- **Type**: Two-way join with filtering
- **Dataset**: Med
- **Tables**: disease, drug
- **Status**: ⚠️ Requires manual creation
- **Note**: Join with complex WHERE clause

### Aggregation Queries (3)

#### agg_1.csv
- **Type**: Disease type grouping
- **Dataset**: Med
- **SQL Pattern**: `SELECT disease_type, COUNT(disease_name) AS disease_count FROM disease GROUP BY disease_type`
- **Status**: ⚠️ Requires manual creation
- **Note**: GROUP BY with COUNT aggregation

#### agg_2.csv
- **Type**: Financial aggregation
- **Dataset**: Finan
- **SQL Pattern**: `SELECT principal_activities, AVG(revenue), SUM(net_profit_or_loss) FROM financial_record GROUP BY principal_activities`
- **Status**: ⚠️ Requires manual creation
- **Note**: GROUP BY with multiple aggregation functions

#### agg_3.csv
- **Type**: Player statistics grouping
- **Dataset**: Player
- **SQL Pattern**: `SELECT position, nationality, COUNT(name), AVG(mvp_awards) FROM player GROUP BY position, nationality`
- **Status**: ⚠️ Requires manual creation
- **Note**: Multi-column GROUP BY with multiple aggregations

### Union Queries (3)

#### union_1.csv
- **Type**: Cross-dataset union
- **Dataset**: Med
- **Tables**: disease, drug
- **Status**: ⚠️ Requires manual creation
- **Note**: UNION of different entity types

#### union_2.csv
- **Type**: Conditional union
- **Dataset**: Player
- **SQL Pattern**: Multiple SELECT statements with UNION
- **Status**: ⚠️ Requires manual creation
- **Note**: UNION with different filtering criteria

#### union_3.csv
- **Type**: Case-based union
- **Dataset**: Legal
- **SQL Pattern**: UNION by verdict types
- **Status**: ⚠️ Requires manual creation
- **Note**: UNION of filtered legal cases

## Usage

### For System Evaluation

To evaluate a system against these ground truth files:

```python
import pandas as pd

# Load system result
result_df = pd.read_csv('system_result.csv')

# Load ground truth
gt_df = pd.read_csv('ground_truth/queries/filter_1.csv')

# Calculate metrics
from sklearn.metrics import precision_score, recall_score, f1_score

# ... evaluate result_df against gt_df
```

### Notes on Ground Truth Generation

1. **Simple & Filter Queries**: Generated by executing SQL WHERE clauses against raw CSV data
2. **Projection Queries**: Generated by column selection from raw data
3. **Join/Union/Aggregation**: Require manual creation due to complexity (multi-table operations)
4. **Virtual Columns**: Some queries expect AI-generated attributes (style, theme, etc.) which are not in raw data
   - Ground truth includes only physically stored columns
   - Systems are expected to extract virtual columns from unstructured data

## Data Quality Notes

- All ground truth files use the raw data as source of truth
- No data cleaning or transformation applied beyond SQL query execution
- Empty results (e.g., filter_1.csv) are correct and represent queries with no matching records
- Column name matching is case-insensitive during execution


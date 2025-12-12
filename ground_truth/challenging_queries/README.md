# Ground Truth Files for Challenging Queries

## agg_1
- Type: AGGREGATION
- Status: Requires manual calculation
- SQL: `SELECT disease_type, 
       COUNT(disease_name) AS disease_count
FROM disease
GROUP BY disease_type...`

## agg_2
- Type: AGGREGATION
- Status: Requires manual calculation
- SQL: `SELECT principal_activities,
       AVG(revenue) AS avg_revenue,
       SUM(net_profit_or_loss) AS t...`

## agg_3
- Type: AGGREGATION
- Status: Requires manual calculation
- SQL: `SELECT position, nationality,
       COUNT(name) AS player_count,
       AVG(mvp_awards) AS avg_mvp,...`

## filter_1
- Type: FILTER
- Status: ✓ Complete
- Rows: 0

## filter_2
- Type: FILTER
- Status: ✓ Complete
- Rows: 13

## filter_3
- Type: FILTER
- Status: Contains virtual columns: ['style', 'composition', 'tone', 'image_genre']
- Note: Ground truth only includes physical columns

## join_1
- Type: JOIN
- Status: Requires manual creation (multi-table)

## join_2
- Type: JOIN
- Status: Requires manual creation (multi-table)

## join_3
- Type: JOIN
- Status: Requires manual creation (multi-table)

## projection_1
- Type: PROJECTION
- Status: ✓ Complete
- Rows: 100

## projection_2
- Type: PROJECTION
- Status: ✓ Complete
- Rows: 100

## projection_3
- Type: PROJECTION
- Status: Contains virtual columns: ['style', 'theme', 'object', 'color', 'tone', 'composition', 'image_genre']
- Note: Ground truth only includes physical columns

## simple_1
- Type: SIMPLE
- Status: ✓ Complete
- Rows: 100

## simple_2
- Type: SIMPLE
- Status: ✓ Complete
- Rows: 141

## union_1
- Type: UNION
- Status: Requires manual creation

## union_2
- Type: UNION
- Status: Requires manual creation

## union_3
- Type: UNION
- Status: Requires manual creation


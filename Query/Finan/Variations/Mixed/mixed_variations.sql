-- Inspiration: Query 1 (mixed_queries.sql)
-- Variation: Average revenue instead of business profit, filtered by 'Fixed' remuneration.
SELECT auditor, AVG(revenue) AS avg_revenue FROM finance WHERE remuneration_policy = 'Fixed' GROUP BY auditor;

-- Inspiration: Query 2 (mixed_queries.sql)
-- Variation: Max business sales for companies with positive earnings and high revenue.
SELECT remuneration_policy, MAX(bussiness_sales) AS max_sales FROM finance WHERE dividend_per_share >= 0.00 AND revenue > 100000000 GROUP BY remuneration_policy;

-- Inspiration: Query 3 (mixed_queries.sql)
-- Variation: Count of companies grouped by principal activities for those with low net assets.
SELECT principal_activities, COUNT(company_name) AS company_count FROM finance WHERE net_assets < 100000000 GROUP BY principal_activities;

-- Inspiration: Query 4 (mixed_queries.sql)
-- Variation: Minimum dividend per share grouped by auditor, excluding specific major events.
SELECT auditor, MIN(dividend_per_share) AS min_dividend FROM finance WHERE major_events != 'Litigation' AND major_events != 'Restructuring' GROUP BY auditor;

-- Inspiration: Query 6 (mixed_queries.sql)
-- Variation: Total revenue for companies with specific profiles or sales figures.
SELECT major_equity_changes, SUM(revenue) AS total_revenue FROM finance WHERE (executive_profiles != 'John Doe' AND net_assets > 0) OR (bussiness_sales > 1000000) GROUP BY major_equity_changes;

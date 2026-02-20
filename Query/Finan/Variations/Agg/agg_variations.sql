-- Inspiration: Query 1 (agg_queries_finance.sql)
-- Variation: Changed MIN to MAX and kept the grouping by auditor.
SELECT auditor, MAX(business_segments_num) AS max_business_segments_num FROM finance GROUP BY auditor;

-- Inspiration: Query 2 & Query 4 (agg_queries_finance.sql)
-- Variation: Combined counting companies and finding max revenue per exchange_code.
SELECT exchange_code, COUNT(company_name) AS company_count, MAX(revenue) AS max_revenue FROM finance GROUP BY exchange_code;

-- Inspiration: Query 3 (agg_queries_finance.sql)
-- Variation: Instead of AVG business_segments_num, calculate SUM of revenue for each remuneration policy.
SELECT remuneration_policy, SUM(revenue) AS total_revenue FROM finance GROUP BY remuneration_policy;

-- Inspiration: Query 8 (agg_queries_finance.sql)
-- Variation: Changed SUM(revenue) to AVG(net_profit_or_loss) grouped by major_equity_changes.
SELECT major_equity_changes, AVG(net_profit_or_loss) AS avg_net_profit FROM finance GROUP BY major_equity_changes;

-- Inspiration: Query 6 & Query 9 (agg_queries_finance.sql)
-- Variation: Group by principal_activities (new) and count auditors and find min revenue.
SELECT principal_activities, COUNT(auditor) AS auditor_count, MIN(revenue) AS min_revenue FROM finance GROUP BY principal_activities;

-- Inspiration: Query 1 (filter_queries_Finan.sql)
-- Variation: Filtered by 'KPMG' instead of 'PKF Littlejohn LLP' and selected different financial metrics.
SELECT company_name, revenue, net_assets FROM Finance WHERE auditor = 'KPMG';

-- Inspiration: Query 2 (filter_queries_Finan.sql)
-- Variation: Filtered for companies with losses (net_profit_or_loss < 0) instead of high profits.
SELECT company_name, registered_office, net_profit_or_loss FROM Finance WHERE net_profit_or_loss < 0;

-- Inspiration: Query 6 (filter_queries_Finan.sql)
-- Variation: Changed exchange_code filter to 'ASX' and included board member info.
SELECT company_name, board_members, the_highest_ownership_stake FROM Finance WHERE exchange_code = 'ASX';

-- Inspiration: Query 11 (filter_queries_Finan.sql)
-- Variation: Used different business_risks and excluded a different shareholder.
SELECT company_name, auditor, principal_activities FROM Finance WHERE largest_shareholder != 'BlackRock' AND business_risks = 'Market Risk';

-- Inspiration: Query 13 (filter_queries_Finan.sql)
-- Variation: Swapped the comparison values for dividend and earnings per share.
SELECT company_name, bussiness_profit, total_Debt FROM Finance WHERE dividend_per_share >= 0.50 AND earnings_per_share < 0.30;

-- Inspiration: Query 21 (filter_queries_Finan.sql)
-- Variation: Used OR condition with revenue and total_assets instead of bussiness_cost and total_Debt.
SELECT company_name, board_members, revenue FROM Finance WHERE revenue > 1000000000 OR total_assets < 500000000;

-- Inspiration: Query 31 (filter_queries_Finan.sql)
-- Variation: A complex AND filter involving multiple financial thresholds.
SELECT company_name, business_risks, net_profit_or_loss FROM Finance WHERE dividend_per_share > 0.10 AND net_profit_or_loss > 0 AND earnings_per_share > 0.10 AND net_assets > 100000000;

-- Inspiration: Query 33 (filter_queries_Finan.sql)
-- Variation: Filtered by 'Market Risk' and 'Performance-based' remuneration.
SELECT company_name, business_risks, business_segments_num FROM Finance WHERE business_risks = 'Market Risk' AND earnings_per_share > 0.20 AND remuneration_policy = 'Performance-based';

-- Inspiration: Query 42 (filter_queries_Finan.sql)
-- Variation: A multi-column OR filter for high-level visibility.
SELECT company_name, revenue, auditor FROM Finance WHERE revenue > 5000000000 OR auditor = 'PricewaterhouseCoopers LLP' OR exchange_code = 'NYSE';

-- Inspiration: Query 53 (filter_queries_Finan.sql)
-- Variation: Complex nested logic for profitability and industry classification.
SELECT company_name, principal_activities, net_profit_or_loss FROM Finance WHERE (net_profit_or_loss > 0 AND revenue > 1000000) OR (principal_activities = 'Technology' AND cash_reserves > 500000);

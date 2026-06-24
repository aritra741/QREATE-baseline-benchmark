-- Query 1: train (agg_only) id=agg_only_finan_gen_338
SELECT auditor, MAX(cash_reserves) AS max_cash_reserves FROM finance GROUP BY auditor;

-- Query 2: train (agg_only) id=agg_only_finan_gen_153
SELECT major_equity_changes, MIN(bussiness_cost) AS min_bussiness_cost FROM finance GROUP BY major_equity_changes;

-- Query 3: train (agg_only) id=agg_only_finan_gen_53
SELECT principal_activities, COUNT(company_name) AS count_companies FROM finance GROUP BY principal_activities;

-- Query 4: train (agg_only) id=agg_queries_finance_5
SELECT exchange_code, COUNT(major_equity_changes) AS count_major_equity_changes FROM finance GROUP BY exchange_code;

-- Query 5: train (agg_only) id=agg_only_finan_gen_73
SELECT principal_activities, MAX(cash_reserves) AS max_cash_reserves FROM finance GROUP BY principal_activities;

-- Query 6: train (agg_only) id=agg_only_finan_gen_318
SELECT auditor, COUNT(company_name) AS count_companies FROM finance GROUP BY auditor;

-- Query 7: train (agg_only) id=agg_queries_finance_8
SELECT major_equity_changes, SUM(revenue) AS sum_revenue FROM finance GROUP BY major_equity_changes;

-- Query 8: train (agg_only) id=agg_only_finan_gen_164
SELECT major_events, SUM(net_profit_or_loss) AS sum_net_profit_or_loss FROM finance GROUP BY major_events;

-- Query 9: train (agg_only) id=agg_only_finan_gen_10
SELECT exchange_code, AVG(total_Debt) AS avg_total_Debt FROM finance GROUP BY exchange_code;

-- Query 10: train (agg_only) id=agg_only_finan_gen_219
SELECT business_risks, MIN(net_profit_or_loss) AS min_net_profit_or_loss FROM finance GROUP BY business_risks;

-- Query 11: train (agg_only) id=agg_only_finan_gen_23
SELECT exchange_code, MIN(net_assets) AS min_net_assets FROM finance GROUP BY exchange_code;

-- Query 12: train (agg_only) id=agg_only_finan_gen_40
SELECT exchange_code, MAX(bussiness_sales) AS max_bussiness_sales FROM finance GROUP BY exchange_code;

-- Query 13: train (agg_only) id=agg_only_finan_gen_166
SELECT major_events, MIN(net_profit_or_loss) AS min_net_profit_or_loss FROM finance GROUP BY major_events;

-- Query 14: train (agg_only) id=agg_only_finan_gen_106
SELECT major_equity_changes, COUNT(company_name) AS count_companies FROM finance GROUP BY major_equity_changes;

-- Query 15: train (agg_only) id=agg_only_finan_gen_159
SELECT major_events, COUNT(company_name) AS count_companies FROM finance GROUP BY major_events;

-- Query 16: train (agg_only) id=agg_only_finan_gen_218
SELECT business_risks, AVG(net_profit_or_loss) AS avg_net_profit_or_loss FROM finance GROUP BY business_risks;

-- Query 17: train (agg_only) id=agg_only_finan_gen_360
SELECT auditor, AVG(bussiness_profit) AS avg_bussiness_profit FROM finance GROUP BY auditor;

-- Query 18: train (agg_only) id=agg_only_finan_gen_63
SELECT principal_activities, AVG(total_Debt) AS avg_total_Debt FROM finance GROUP BY principal_activities;

-- Query 19: train (agg_only) id=agg_only_finan_gen_68
SELECT principal_activities, MIN(total_assets) AS min_total_assets FROM finance GROUP BY principal_activities;

-- Query 20: train (agg_only) id=agg_only_finan_gen_212
SELECT business_risks, COUNT(company_name) AS count_companies FROM finance GROUP BY business_risks;

-- Query 21: train (agg_filter) id=mixed_queries_3
SELECT remuneration_policy, AVG(the_highest_ownership_stake) AS avg_the_highest_ownership_stake FROM finance WHERE net_assets <= 249398000 OR total_assets < 1358991000 GROUP BY remuneration_policy;

-- Query 22: train (agg_filter) id=agg_filter_finan_gen_1139
SELECT exchange_code, SUM(the_highest_ownership_stake) AS sum_the_highest_ownership_stake FROM finance WHERE major_equity_changes = 'Yes' GROUP BY exchange_code;

-- Query 23: train (agg_filter) id=agg_filter_finan_gen_1860
SELECT principal_activities, MIN(total_Debt) AS min_total_Debt FROM finance WHERE the_highest_ownership_stake > 50 GROUP BY principal_activities;

-- Query 24: train (agg_filter) id=agg_filter_finan_gen_3588
SELECT major_equity_changes, AVG(the_highest_ownership_stake) AS avg_the_highest_ownership_stake FROM finance WHERE exchange_code = 'ASX' GROUP BY major_equity_changes;

-- Query 25: train (agg_filter) id=agg_filter_finan_gen_4560
SELECT major_events, SUM(net_assets) AS sum_net_assets FROM finance WHERE net_profit_or_loss > 0 GROUP BY major_events;

-- Query 26: train (agg_filter) id=agg_filter_finan_gen_6569
SELECT remuneration_policy, SUM(revenue) AS sum_revenue FROM finance WHERE major_events LIKE '%M&A%' GROUP BY remuneration_policy;

-- Query 27: train (agg_filter) id=agg_filter_finan_gen_5722
SELECT business_risks, AVG(cash_reserves) AS avg_cash_reserves FROM finance WHERE major_equity_changes = 'Yes' GROUP BY business_risks;

-- Query 28: train (agg_filter) id=agg_filter_finan_gen_1869
SELECT principal_activities, MAX(total_Debt) AS max_total_Debt FROM finance WHERE major_events LIKE '%M&A%' GROUP BY principal_activities;

-- Query 29: train (agg_filter) id=mixed_variations_1
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

-- Query 30: train (agg_filter) id=agg_filter_finan_gen_2306
SELECT principal_activities, MAX(dividend_per_share) AS max_dividend_per_share FROM finance WHERE remuneration_policy = 'Fixed' GROUP BY principal_activities;

-- Query 31: train (agg_filter) id=agg_filter_finan_gen_5759
SELECT business_risks, MIN(cash_reserves) AS min_cash_reserves FROM finance WHERE revenue > 0 GROUP BY business_risks;

-- Query 32: train (agg_filter) id=agg_filter_finan_gen_1588
SELECT exchange_code, MIN(business_segments_num) AS min_business_segments_num FROM finance WHERE net_profit_or_loss > 0 GROUP BY exchange_code;

-- Query 33: train (agg_filter) id=agg_filter_finan_gen_4556
SELECT major_events, SUM(net_assets) AS sum_net_assets FROM finance WHERE business_risks LIKE '%Market Risk%' GROUP BY major_events;

-- Query 34: train (agg_filter) id=mixed_queries_2
SELECT remuneration_policy, MIN(bussiness_profit) AS min_bussiness_profit FROM finance WHERE dividend_per_share > 0.00 AND revenue <= 12857200000 GROUP BY remuneration_policy;

-- Query 35: train (agg_filter) id=agg_filter_finan_gen_2824
SELECT major_equity_changes, MIN(revenue) AS min_revenue FROM finance WHERE major_events LIKE '%M&A%' GROUP BY major_equity_changes;

-- Query 36: train (agg_filter) id=agg_filter_finan_gen_1378
SELECT exchange_code, AVG(bussiness_profit) AS avg_bussiness_profit FROM finance WHERE the_highest_ownership_stake > 50 GROUP BY exchange_code;

-- Query 37: train (agg_filter) id=agg_filter_finan_gen_2882
SELECT major_equity_changes, SUM(net_profit_or_loss) AS sum_net_profit_or_loss FROM finance WHERE net_profit_or_loss < 0 GROUP BY major_equity_changes;

-- Query 38: train (agg_filter) id=agg_filter_finan_gen_2062
SELECT principal_activities, SUM(net_assets) AS sum_net_assets FROM finance WHERE major_equity_changes = 'Yes' GROUP BY principal_activities;

-- Query 39: train (agg_filter) id=agg_filter_finan_gen_611
SELECT exchange_code, MIN(total_Debt) AS min_total_Debt FROM finance WHERE major_equity_changes = 'Yes' GROUP BY exchange_code;

-- Query 40: train (agg_filter) id=agg_filter_finan_gen_923
SELECT exchange_code, MAX(net_assets) AS max_net_assets FROM finance WHERE major_equity_changes = 'Yes' GROUP BY exchange_code;

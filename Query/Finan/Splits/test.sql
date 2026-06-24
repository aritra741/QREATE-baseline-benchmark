-- Query 1: test (agg_only) id=agg_only_finan_gen_1
SELECT exchange_code, SUM(revenue) AS sum_revenue FROM finance GROUP BY exchange_code;

-- Query 2: test (agg_only) id=agg_only_finan_gen_66
SELECT principal_activities, SUM(total_assets) AS sum_total_assets FROM finance GROUP BY principal_activities;

-- Query 3: test (agg_only) id=agg_only_finan_gen_213
SELECT business_risks, SUM(revenue) AS sum_revenue FROM finance GROUP BY business_risks;

-- Query 4: test (agg_only) id=agg_only_finan_gen_134
SELECT major_equity_changes, MAX(earnings_per_share) AS max_earnings_per_share FROM finance GROUP BY major_equity_changes;

-- Query 5: test (agg_only) id=agg_only_finan_gen_161
SELECT major_events, AVG(revenue) AS avg_revenue FROM finance GROUP BY major_events;

-- Query 6: test (agg_filter) id=agg_filter_finan_gen_8747
SELECT auditor, MIN(the_highest_ownership_stake) AS min_the_highest_ownership_stake FROM finance WHERE total_assets > 0 GROUP BY auditor;

-- Query 7: test (agg_filter) id=agg_filter_finan_gen_1982
SELECT principal_activities, SUM(cash_reserves) AS sum_cash_reserves FROM finance WHERE business_risks LIKE '%Market Risk%' GROUP BY principal_activities;

-- Query 8: test (agg_filter) id=agg_filter_finan_gen_8684
SELECT auditor, SUM(the_highest_ownership_stake) AS sum_the_highest_ownership_stake FROM finance WHERE major_events LIKE '%M&A%' GROUP BY auditor;

-- Query 9: test (agg_filter) id=agg_filter_finan_gen_7140
SELECT remuneration_policy, SUM(earnings_per_share) AS sum_earnings_per_share FROM finance WHERE principal_activities LIKE '%Mining%' GROUP BY remuneration_policy;

-- Query 10: test (agg_filter) id=agg_filter_finan_gen_3013
SELECT major_equity_changes, MIN(total_Debt) AS min_total_Debt FROM finance WHERE exchange_code = 'ASX' GROUP BY major_equity_changes;

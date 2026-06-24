-- Query 1: dev (agg_only) id=agg_only_finan_gen_240
SELECT business_risks, MAX(earnings_per_share) AS max_earnings_per_share FROM finance GROUP BY business_risks;

-- Query 2: dev (agg_only) id=agg_only_finan_gen_171
SELECT major_events, MAX(total_Debt) AS max_total_Debt FROM finance GROUP BY major_events;

-- Query 3: dev (agg_only) id=agg_only_finan_gen_140
SELECT major_equity_changes, AVG(the_highest_ownership_stake) AS avg_the_highest_ownership_stake FROM finance GROUP BY major_equity_changes;

-- Query 4: dev (agg_only) id=agg_only_finan_gen_355
SELECT auditor, SUM(bussiness_sales) AS sum_bussiness_sales FROM finance GROUP BY auditor;

-- Query 5: dev (agg_only) id=agg_only_finan_gen_337
SELECT auditor, MIN(cash_reserves) AS min_cash_reserves FROM finance GROUP BY auditor;

-- Query 6: dev (agg_filter) id=agg_filter_finan_gen_6802
SELECT remuneration_policy, MIN(total_Debt) AS min_total_Debt FROM finance WHERE major_equity_changes = 'Yes' GROUP BY remuneration_policy;

-- Query 7: dev (agg_filter) id=agg_filter_finan_gen_5799
SELECT business_risks, SUM(net_assets) AS sum_net_assets FROM finance WHERE principal_activities LIKE '%Mining%' GROUP BY business_risks;

-- Query 8: dev (agg_filter) id=agg_filter_finan_gen_7492
SELECT remuneration_policy, MIN(bussiness_sales) AS min_bussiness_sales FROM finance WHERE business_segments_num > 1 GROUP BY remuneration_policy;

-- Query 9: dev (agg_filter) id=agg_filter_finan_gen_3084
SELECT major_equity_changes, SUM(total_assets) AS sum_total_assets FROM finance WHERE earnings_per_share > 0 GROUP BY major_equity_changes;

-- Query 10: dev (agg_filter) id=agg_filter_finan_gen_9119
SELECT auditor, SUM(business_segments_num) AS sum_business_segments_num FROM finance WHERE business_risks LIKE '%Market Risk%' GROUP BY auditor;

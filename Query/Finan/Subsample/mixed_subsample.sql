-- Query 1: filter1_agg1 (finance)
SELECT auditor, AVG(bussiness_profit) AS avg_bussiness_profit FROM finance WHERE remuneration_policy = 'Performance-based' GROUP BY auditor;

-- Query 2: filter2_agg1 (finance)
SELECT remuneration_policy, MIN(bussiness_profit) AS min_bussiness_profit FROM finance WHERE dividend_per_share > 0.00 AND revenue <= 12857200000 GROUP BY remuneration_policy;

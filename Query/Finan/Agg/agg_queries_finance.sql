-- Query 1: aggregation (finance)
SELECT auditor, MIN(business_segments_num) AS min_business_segments_num FROM finance GROUP BY auditor;

-- Query 2: aggregation (finance)
SELECT exchange_code, COUNT(company_name) AS count_company_name FROM finance GROUP BY exchange_code;

-- Query 3: aggregation (finance)
SELECT remuneration_policy, AVG(business_segments_num) AS avg_business_segments_num FROM finance GROUP BY remuneration_policy;

-- Query 4: aggregation (finance)
SELECT exchange_code, MAX(revenue) AS max_revenue FROM finance GROUP BY exchange_code;

-- Query 5: aggregation (finance)
SELECT exchange_code, COUNT(major_equity_changes) AS count_major_equity_changes FROM finance GROUP BY exchange_code;

-- Query 6: aggregation (finance)
SELECT auditor, MIN(revenue) AS min_revenue FROM finance GROUP BY auditor;

-- Query 7: aggregation (finance)
SELECT exchange_code, MAX(revenue) AS max_revenue FROM finance GROUP BY exchange_code;

-- Query 8: aggregation (finance)
SELECT major_equity_changes, SUM(revenue) AS sum_revenue FROM finance GROUP BY major_equity_changes;

-- Query 9: aggregation (finance)
SELECT exchange_code, COUNT(auditor) AS count_auditor FROM finance GROUP BY exchange_code;

-- Query 10: aggregation (finance)
SELECT exchange_code, COUNT(total_assets) AS count_total_assets FROM finance GROUP BY exchange_code;


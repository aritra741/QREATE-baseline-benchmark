-- Query 1: aggregation (finance)
SELECT auditor, MIN(business_segments_num) AS min_business_segments_num FROM finance GROUP BY auditor;

-- Query 2: aggregation (finance)
SELECT exchange_code, COUNT(company_name) AS count_company_name FROM finance GROUP BY exchange_code;

-- Query 3: aggregation (finance)
SELECT remuneration_policy, AVG(business_segments_num) AS avg_business_segments_num FROM finance GROUP BY remuneration_policy;

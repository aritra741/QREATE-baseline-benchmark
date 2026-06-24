-- Query 1: dev (agg_only) id=agg_only_cspaper_gen_6
SELECT application_domain, COUNT(paper_name) AS count_papers FROM cspaper GROUP BY application_domain;

-- Query 2: dev (agg_only) id=agg_queries_CSPaper_10
SELECT topic, COUNT(evaluation_metric) AS count_evaluation_metric FROM cspaper GROUP BY topic;

-- Query 3: dev (agg_only) id=agg_only_cspaper_gen_3
SELECT retrieval_method, COUNT(paper_name) AS count_papers FROM cspaper GROUP BY retrieval_method;

-- Query 4: dev (agg_filter) id=agg_filter_cspaper_gen_98
SELECT uses_reranker, COUNT(paper_name) AS count_papers FROM cspaper WHERE data_modality = 'Text' GROUP BY uses_reranker;

-- Query 5: dev (agg_filter) id=agg_filter_cspaper_gen_127
SELECT application_domain, COUNT(paper_name) AS count_papers FROM cspaper WHERE reasoning_depth = 'single-hop' GROUP BY application_domain;

-- Query 6: dev (agg_filter) id=agg_filter_cspaper_gen_90
SELECT uses_reranker, COUNT(paper_name) AS count_papers FROM cspaper WHERE use_agent = 'Yes' GROUP BY uses_reranker;

-- Query 7: dev (agg_filter) id=mixed_queries_3
SELECT data_modality, AVG(baseline_amount) AS avg_baseline_amount FROM cspaper WHERE application_domain != 'Education' OR use_agent = 'Yes' GROUP BY data_modality;

-- Query 8: dev (agg_filter) id=agg_filter_cspaper_gen_150
SELECT use_agent, COUNT(paper_name) AS count_papers FROM cspaper WHERE application_domain = 'General' GROUP BY use_agent;

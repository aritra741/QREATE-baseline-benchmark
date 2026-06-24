-- Query 1: test (agg_only) id=agg_queries_CSPaper_2
SELECT uses_knowledge_graph, COUNT(topic) AS count_topic FROM cspaper GROUP BY uses_knowledge_graph;

-- Query 2: test (agg_only) id=agg_only_cspaper_gen_7
SELECT use_agent, COUNT(paper_name) AS count_papers FROM cspaper GROUP BY use_agent;

-- Query 3: test (agg_only) id=agg_only_cspaper_gen_1
SELECT uses_knowledge_graph, COUNT(paper_name) AS count_papers FROM cspaper GROUP BY uses_knowledge_graph;

-- Query 4: test (agg_filter) id=agg_filter_cspaper_gen_53
SELECT reasoning_depth, COUNT(paper_name) AS count_papers FROM cspaper WHERE use_agent = 'Yes' GROUP BY reasoning_depth;

-- Query 5: test (agg_filter) id=agg_filter_cspaper_gen_38
SELECT uses_knowledge_graph, COUNT(paper_name) AS count_papers FROM cspaper WHERE application_domain = 'General' GROUP BY uses_knowledge_graph;

-- Query 6: test (agg_filter) id=agg_filter_cspaper_gen_167
SELECT multi_turn_retrieval, COUNT(paper_name) AS count_papers FROM cspaper WHERE use_agent = 'Yes' GROUP BY multi_turn_retrieval;

-- Query 7: test (agg_filter) id=agg_filter_cspaper_gen_55
SELECT reasoning_depth, COUNT(paper_name) AS count_papers FROM cspaper WHERE multi_turn_retrieval = 'Yes' GROUP BY reasoning_depth;

-- Query 8: test (agg_filter) id=agg_filter_cspaper_gen_19
SELECT topic, COUNT(paper_name) AS count_papers FROM cspaper WHERE application_domain = 'General' GROUP BY topic;

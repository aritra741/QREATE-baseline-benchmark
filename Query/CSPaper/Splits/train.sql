-- Query 1: train (agg_only) id=agg_queries_CSPaper_4
SELECT topic, MAX(baseline_amount) AS max_baseline_amount FROM cspaper GROUP BY topic;

-- Query 2: train (agg_only) id=agg_queries_CSPaper_8
SELECT reasoning_depth, SUM(baseline_amount) AS sum_baseline_amount FROM cspaper GROUP BY reasoning_depth;

-- Query 3: train (agg_only) id=agg_queries_CSPaper_5
SELECT uses_knowledge_graph, COUNT(baseline_amount) AS count_baseline_amount FROM cspaper GROUP BY uses_knowledge_graph;

-- Query 4: train (agg_only) id=agg_only_cspaper_gen_5
SELECT data_modality, COUNT(paper_name) AS count_papers FROM cspaper GROUP BY data_modality;

-- Query 5: train (agg_only) id=agg_only_cspaper_gen_8
SELECT multi_turn_retrieval, COUNT(paper_name) AS count_papers FROM cspaper GROUP BY multi_turn_retrieval;

-- Query 6: train (agg_only) id=agg_only_cspaper_gen_4
SELECT uses_reranker, COUNT(paper_name) AS count_papers FROM cspaper GROUP BY uses_reranker;

-- Query 7: train (agg_only) id=agg_only_cspaper_gen_0
SELECT topic, COUNT(paper_name) AS count_papers FROM cspaper GROUP BY topic;

-- Query 8: train (agg_only) id=agg_only_cspaper_gen_2
SELECT reasoning_depth, COUNT(paper_name) AS count_papers FROM cspaper GROUP BY reasoning_depth;

-- Query 9: train (agg_only) id=agg_queries_CSPaper_3
SELECT uses_reranker, AVG(baseline_amount) AS avg_baseline_amount FROM cspaper GROUP BY uses_reranker;

-- Query 10: train (agg_only) id=agg_queries_CSPaper_1
SELECT use_agent, MIN(baseline_amount) AS min_baseline_amount FROM cspaper GROUP BY use_agent;

-- Query 11: train (agg_only) id=agg_queries_CSPaper_9
SELECT topic, COUNT(uses_reranker) AS count_uses_reranker FROM cspaper GROUP BY topic;

-- Query 12: train (agg_filter) id=agg_filter_cspaper_gen_83
SELECT uses_reranker, COUNT(paper_name) AS count_papers FROM cspaper WHERE topic = 'Retrieval-Augmented Generation' GROUP BY uses_reranker;

-- Query 13: train (agg_filter) id=agg_filter_cspaper_gen_46
SELECT reasoning_depth, COUNT(paper_name) AS count_papers FROM cspaper WHERE topic = 'Retrieval-Augmented Generation' GROUP BY reasoning_depth;

-- Query 14: train (agg_filter) id=agg_filter_cspaper_gen_57
SELECT reasoning_depth, COUNT(paper_name) AS count_papers FROM cspaper WHERE application_domain = 'General' GROUP BY reasoning_depth;

-- Query 15: train (agg_filter) id=agg_filter_cspaper_gen_27
SELECT uses_knowledge_graph, COUNT(paper_name) AS count_papers FROM cspaper WHERE topic = 'Retrieval-Augmented Generation' GROUP BY uses_knowledge_graph;

-- Query 16: train (agg_filter) id=agg_filter_cspaper_gen_82
SELECT retrieval_method, COUNT(paper_name) AS count_papers FROM cspaper WHERE data_modality = 'Text' GROUP BY retrieval_method;

-- Query 17: train (agg_filter) id=agg_filter_cspaper_gen_86
SELECT uses_reranker, COUNT(paper_name) AS count_papers FROM cspaper WHERE uses_knowledge_graph = 'Yes' GROUP BY uses_reranker;

-- Query 18: train (agg_filter) id=agg_filter_cspaper_gen_148
SELECT use_agent, COUNT(paper_name) AS count_papers FROM cspaper WHERE multi_turn_retrieval = 'Yes' GROUP BY use_agent;

-- Query 19: train (agg_filter) id=agg_filter_cspaper_gen_105
SELECT data_modality, COUNT(paper_name) AS count_papers FROM cspaper WHERE uses_knowledge_graph = 'Yes' GROUP BY data_modality;

-- Query 20: train (agg_filter) id=agg_filter_cspaper_gen_15
SELECT topic, COUNT(paper_name) AS count_papers FROM cspaper WHERE use_agent = 'Yes' GROUP BY topic;

-- Query 21: train (agg_filter) id=agg_filter_cspaper_gen_146
SELECT use_agent, COUNT(paper_name) AS count_papers FROM cspaper WHERE uses_reranker = 'Yes' GROUP BY use_agent;

-- Query 22: train (agg_filter) id=agg_filter_cspaper_gen_51
SELECT reasoning_depth, COUNT(paper_name) AS count_papers FROM cspaper WHERE uses_reranker = 'Yes' GROUP BY reasoning_depth;

-- Query 23: train (agg_filter) id=agg_filter_cspaper_gen_107
SELECT data_modality, COUNT(paper_name) AS count_papers FROM cspaper WHERE reasoning_depth = 'single-hop' GROUP BY data_modality;

-- Query 24: train (agg_filter) id=agg_filter_cspaper_gen_23
SELECT topic, COUNT(paper_name) AS count_papers FROM cspaper WHERE data_modality = 'Text' GROUP BY topic;

-- Query 25: train (agg_filter) id=agg_filter_cspaper_gen_72
SELECT retrieval_method, COUNT(paper_name) AS count_papers FROM cspaper WHERE uses_reranker = 'Yes' GROUP BY retrieval_method;

-- Query 26: train (agg_filter) id=agg_filter_cspaper_gen_102
SELECT data_modality, COUNT(paper_name) AS count_papers FROM cspaper WHERE topic = 'Retrieval-Augmented Generation' GROUP BY data_modality;

-- Query 27: train (agg_filter) id=agg_filter_cspaper_gen_42
SELECT uses_knowledge_graph, COUNT(paper_name) AS count_papers FROM cspaper WHERE data_modality = 'Text' GROUP BY uses_knowledge_graph;

-- Query 28: train (agg_filter) id=agg_filter_cspaper_gen_144
SELECT use_agent, COUNT(paper_name) AS count_papers FROM cspaper WHERE reasoning_depth = 'single-hop' GROUP BY use_agent;

-- Query 29: train (agg_filter) id=agg_filter_cspaper_gen_109
SELECT data_modality, COUNT(paper_name) AS count_papers FROM cspaper WHERE uses_reranker = 'Yes' GROUP BY data_modality;

-- Query 30: train (agg_filter) id=agg_filter_cspaper_gen_142
SELECT use_agent, COUNT(paper_name) AS count_papers FROM cspaper WHERE uses_knowledge_graph = 'Yes' GROUP BY use_agent;

-- Query 31: train (agg_filter) id=agg_filter_cspaper_gen_88
SELECT uses_reranker, COUNT(paper_name) AS count_papers FROM cspaper WHERE reasoning_depth = 'single-hop' GROUP BY uses_reranker;

-- Realistic aggregate questions over research papers on retrieval-augmented generation (2026-10-12).
-- Q1: How many papers use each retrieval method?
SELECT retrieval_method, COUNT(*) AS papers FROM cspaper GROUP BY retrieval_method;
-- Q2: Among papers that use agents, how many use each agent framework?
SELECT agent_framework, COUNT(*) AS papers FROM cspaper WHERE use_agent = 'Yes' GROUP BY agent_framework;
-- Q3: How many papers study multi-hop versus single-hop reasoning?
SELECT reasoning_depth, COUNT(*) AS papers FROM cspaper GROUP BY reasoning_depth;
-- Q4: Among papers that use a reranker, how many study multi-hop reasoning?
SELECT reasoning_depth, COUNT(*) AS papers FROM cspaper WHERE uses_reranker = 'Yes' GROUP BY reasoning_depth;
-- Q5: What is the average number of baselines compared, per retrieval method?
SELECT retrieval_method, AVG(baseline_amount) AS average_baselines FROM cspaper GROUP BY retrieval_method;
-- Q6: How many papers use GPT-4o as the generator?
SELECT COUNT(*) AS papers FROM cspaper WHERE generator_model LIKE '%GPT-4o%';
-- Q7: How many papers evaluate on HotpotQA?
SELECT COUNT(*) AS papers FROM cspaper WHERE evaluation_dataset LIKE '%HotpotQA%';
-- Q8: How many papers evaluate on Natural Questions, by reasoning depth?
SELECT reasoning_depth, COUNT(*) AS papers FROM cspaper WHERE evaluation_dataset LIKE '%Natural Questions%' GROUP BY reasoning_depth;
-- Q9: How many papers report F1 as an evaluation metric?
SELECT COUNT(*) AS papers FROM cspaper WHERE evaluation_metric LIKE '%F1%';
-- Q10: How many papers use a knowledge graph, by application domain?
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' ELSE 'Other' END AS domain, COUNT(*) AS papers FROM cspaper WHERE uses_knowledge_graph = 'Yes' GROUP BY domain;
-- Q11: For each retrieval method, how many papers use an agent?
SELECT retrieval_method, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS agent_papers, COUNT(*) AS papers FROM cspaper GROUP BY retrieval_method;
-- Q12: How many papers that work with images study multi-hop reasoning?
SELECT reasoning_depth, COUNT(*) AS papers FROM cspaper WHERE data_modality LIKE '%Image%' GROUP BY reasoning_depth;
-- Q13: Do papers with agents compare against more baselines?
SELECT use_agent, AVG(baseline_amount) AS average_baselines FROM cspaper GROUP BY use_agent;
-- Q14: What is the largest number of baselines in one paper, by reasoning depth?
SELECT reasoning_depth, MAX(baseline_amount) AS most_baselines FROM cspaper GROUP BY reasoning_depth;
-- Q15: How many papers do multi-turn retrieval, by whether they use an agent?
SELECT use_agent, COUNT(*) AS papers FROM cspaper WHERE multi_turn_retrieval = 'Yes' GROUP BY use_agent;
-- Q16: How many papers compare against GPT-4 as a baseline?
SELECT COUNT(*) AS papers FROM cspaper WHERE baseline LIKE '%GPT-4%';
-- Q17: Which retrieval methods do medical papers use?
SELECT retrieval_method, COUNT(*) AS papers FROM cspaper WHERE application_domain LIKE '%Medical%' GROUP BY retrieval_method;
-- Q18: Among multi-hop papers, how many use each agent framework?
SELECT agent_framework, COUNT(*) AS papers FROM cspaper WHERE reasoning_depth = 'multi-hop' AND agent_framework IS NOT NULL GROUP BY agent_framework;
-- Q19: How many papers use a Llama model as the generator?
SELECT COUNT(*) AS papers FROM cspaper WHERE generator_model LIKE '%Llama%';
-- Q20: Do papers with a reranker compare against more baselines?
SELECT uses_reranker, AVG(baseline_amount) AS average_baselines FROM cspaper GROUP BY uses_reranker;
-- Q21: How many papers report results on HotpotQA, by retrieval method?
SELECT retrieval_method, COUNT(*) AS papers FROM cspaper WHERE performance_on_hotpotqa IS NOT NULL GROUP BY retrieval_method;
-- Q22: How many papers use both a reranker and a knowledge graph?
SELECT COUNT(*) AS papers FROM cspaper WHERE uses_reranker = 'Yes' AND uses_knowledge_graph = 'Yes';

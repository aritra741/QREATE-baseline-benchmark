# Realistic workload v3: questions for review (gate 1)

Build questions: asked before the table was built; only columns the initial build reads. Test questions: scored for both systems; most need columns the build lacks.
Each entry: the question, its SQL, and the first rows of the correct answer. All passed the checker (runs, non-empty, no empty or NULL values, realism rules, the correct answer scores 1.0 against itself; build questions use only initial columns).

## Research papers on RAG (cspaper): test questions (30)

**Q2.** How many papers are there for each combination of reasoning depth and agent use?
```sql
SELECT reasoning_depth, use_agent, COUNT(*) AS papers FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth, use_agent
```
Correct answer: multi-hop, No, 74; multi-hop, Yes, 35; single-hop, No, 77; single-hop, Yes, 11

**Q14.** Among multi-hop papers, what is the largest number of baselines per retrieval method?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, MAX(baseline_amount) AS most_baselines FROM cspaper WHERE reasoning_depth = 'multi-hop' GROUP BY retrieval_family
```
Correct answer: Dense, 14; Graph-based, 10; Hybrid, 14; Other, 22; ... (6 rows)

**Q18.** For each retrieval method, how many papers use a GPT model and how many a Llama model as the generator?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, SUM(CASE WHEN generator_model LIKE '%GPT%' THEN 1 ELSE 0 END) AS gpt, SUM(CASE WHEN generator_model LIKE '%Llama%' THEN 1 ELSE 0 END) AS llama FROM cspaper GROUP BY retrieval_family
```
Correct answer: Dense, 45, 60; Graph-based, 10, 7; Hybrid, 12, 13; Other, 7, 4; ... (6 rows)

**Q20.** For medical, finance and education papers, which retrieval methods do they use?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' ELSE 'Education' END AS domain, CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers FROM cspaper WHERE application_domain LIKE '%Medical%' OR application_domain LIKE '%Finance%' OR application_domain LIKE '%Education%' GROUP BY domain, retrieval_family
```
Correct answer: Education, Dense, 11; Education, Hybrid, 3; Education, Sparse, 1; Finance, Dense, 9; ... (10 rows)

**QX1.** For each application domain, how many papers use an agent and how many study multi-hop reasoning?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' ELSE 'General or other' END AS domain, COUNT(*) AS papers, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS with_agent, SUM(CASE WHEN reasoning_depth LIKE '%multi-hop%' THEN 1 ELSE 0 END) AS multi_hop FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain
```
Correct answer: Education, 15, 2, 7; Finance, 13, 6, 10; General or other, 136, 28, 74; Legal, 4, 0, 1; ... (5 rows)

**QX2.** Do papers built on a GPT generator compare against more baselines than papers built on open models (Llama, Qwen or Mistral, with no GPT model)? Papers and average baselines for these two groups and for all other generators.
```sql
SELECT CASE WHEN generator_model LIKE '%GPT%' THEN 'uses GPT' WHEN generator_model LIKE '%Llama%' OR generator_model LIKE '%Qwen%' OR generator_model LIKE '%Mistral%' THEN 'Llama, Qwen or Mistral, no GPT' ELSE 'other models' END AS generator_group, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE generator_model IS NOT NULL AND generator_model <> '' GROUP BY generator_group
```
Correct answer: Llama, Qwen or Mistral, no GPT, 86, 4.917; other models, 18, 3.375; uses GPT, 81, 3.961

**QX3.** For each retrieval method, how many papers evaluate on TriviaQA, 2WikiMultihopQA and MuSiQue?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, SUM(CASE WHEN evaluation_dataset LIKE '%Trivia%QA%' THEN 1 ELSE 0 END) AS on_triviaqa, SUM(CASE WHEN evaluation_dataset LIKE '%2Wiki%' THEN 1 ELSE 0 END) AS on_2wikimultihopqa, SUM(CASE WHEN evaluation_dataset LIKE '%MuSiQue%' THEN 1 ELSE 0 END) AS on_musique FROM cspaper WHERE retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_family
```
Correct answer: Dense, 22, 8, 7; Graph-based, 0, 0, 1; Hybrid, 3, 5, 4; Other, 0, 1, 0; ... (6 rows)

**QX4.** For papers with and without a reranker, how many report F1, exact match, accuracy and ROUGE?
```sql
SELECT uses_reranker, SUM(CASE WHEN evaluation_metric LIKE '%F1%' THEN 1 ELSE 0 END) AS report_f1, SUM(CASE WHEN instr(evaluation_metric, 'EM') > 0 OR evaluation_metric LIKE '%Exact Match%' THEN 1 ELSE 0 END) AS report_exact_match, SUM(CASE WHEN evaluation_metric LIKE '%Accuracy%' THEN 1 ELSE 0 END) AS report_accuracy, SUM(CASE WHEN evaluation_metric LIKE '%ROUGE%' THEN 1 ELSE 0 END) AS report_rouge FROM cspaper WHERE uses_reranker IN ('Yes', 'No') GROUP BY uses_reranker
```
Correct answer: No, 42, 16, 56, 12; Yes, 22, 14, 23, 11

**QX5.** How many papers, and how many baselines on average, for each combination of reasoning depth and knowledge graph use?
```sql
SELECT reasoning_depth, uses_knowledge_graph, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') AND uses_knowledge_graph IN ('Yes', 'No') GROUP BY reasoning_depth, uses_knowledge_graph
```
Correct answer: multi-hop, No, 85, 4.866; multi-hop, Yes, 24, 5.0; single-hop, No, 78, 3.479; single-hop, Yes, 8, 4.625

**QX6.** Which three application domains with at least 5 papers have the largest share of agent papers?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' WHEN application_domain LIKE '%Academic%' THEN 'Academic' WHEN application_domain LIKE '%General%' THEN 'General' ELSE 'Other' END AS domain, COUNT(*) AS papers, AVG(CASE WHEN use_agent = 'Yes' THEN 1.0 ELSE 0.0 END) AS agent_share FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain HAVING COUNT(*) >= 5 ORDER BY agent_share DESC, domain LIMIT 3
```
Correct answer: Finance, 13, 0.462; Medical, 31, 0.355; General, 97, 0.227

**QX7.** For each reasoning depth, how many papers compare against a GPT-4 model (including GPT-4o) or ChatGPT as a baseline, out of how many papers?
```sql
SELECT reasoning_depth, SUM(CASE WHEN baseline LIKE '%GPT-4%' OR baseline LIKE '%GPT4%' OR baseline LIKE '%ChatGPT%' THEN 1 ELSE 0 END) AS against_gpt4_or_chatgpt, COUNT(*) AS papers FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth
```
Correct answer: multi-hop, 19, 109; single-hop, 13, 88

**QX8.** For each agent framework, how many papers support multi-turn retrieval and how many use a knowledge graph?
```sql
SELECT agent_framework, COUNT(*) AS papers, SUM(CASE WHEN multi_turn_retrieval = 'Yes' THEN 1 ELSE 0 END) AS multi_turn, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS with_knowledge_graph FROM cspaper WHERE agent_framework IN ('CoT', 'ToT', 'Multi-Agent Collaboration', 'Other') GROUP BY agent_framework
```
Correct answer: CoT, 8, 6, 4; Multi-Agent Collaboration, 12, 6, 3; Other, 27, 20, 7; ToT, 2, 1, 0

**QX9.** For each kind of input data, how many papers are there and how many use an agent?
```sql
SELECT CASE WHEN data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' THEN 'multimodal' WHEN data_modality LIKE '%Table%' OR data_modality LIKE '%Code%' THEN 'text with tables or code' ELSE 'text only' END AS modality, COUNT(*) AS papers, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS with_agent FROM cspaper WHERE (data_modality LIKE '%Text%' OR data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' OR data_modality LIKE '%Table%' OR data_modality LIKE '%Code%') GROUP BY modality
```
Correct answer: multimodal, 35, 8; text only, 138, 31; text with tables or code, 18, 5

**QX10.** Among multi-hop papers, which retrieval methods compare against more baselines on average than papers overall?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE reasoning_depth = 'multi-hop' GROUP BY retrieval_family HAVING AVG(baseline_amount) > (SELECT AVG(baseline_amount) FROM cspaper)
```
Correct answer: Graph-based, 14, 4.786; Hybrid, 28, 5.731; Other, 9, 7.0

**QX12.** For each retrieval method, how many papers evaluate on HotpotQA and how many report a HotpotQA result?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, SUM(CASE WHEN evaluation_dataset LIKE '%HotpotQA%' THEN 1 ELSE 0 END) AS on_hotpotqa, SUM(CASE WHEN performance_on_hotpotqa IS NOT NULL AND performance_on_hotpotqa <> '' THEN 1 ELSE 0 END) AS report_hotpotqa FROM cspaper GROUP BY retrieval_family
```
Correct answer: Dense, 20, 16; Graph-based, 2, 0; Hybrid, 7, 6; Other, 3, 3; ... (6 rows)

**QF1.** For each retrieval method: how many papers, how many baselines on average, and how many use a reranker?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker FROM cspaper WHERE retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_family
```
Correct answer: Dense, 116, 3.907, 34; Graph-based, 21, 4.524, 5; Hybrid, 34, 5.0, 20; Other, 13, 6.154, 1; ... (6 rows)

**QF3.** Among agent papers, which frameworks appear at least twice, with their average number of baselines, most used first?
```sql
SELECT agent_framework, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE use_agent = 'Yes' AND agent_framework IN ('CoT', 'ToT', 'Multi-Agent Collaboration', 'Other') GROUP BY agent_framework HAVING COUNT(*) >= 2 ORDER BY papers DESC, agent_framework
```
Correct answer: Other, 26, 4.826; Multi-Agent Collaboration, 12, 4.0; CoT, 7, 6.143; ToT, 2, 3.5

**QF4.** Which retrieval methods are used by at least 10 papers, ordered by how many baselines they compare on average?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_family HAVING COUNT(*) >= 10 ORDER BY average_baselines DESC, retrieval_family
```
Correct answer: Other, 13, 6.154; Hybrid, 34, 5.0; Graph-based, 21, 4.524; Dense, 116, 3.907

**QF5.** Per application domain: how many papers, how many use a knowledge graph, and how many baselines on average?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' ELSE 'General or other' END AS domain, COUNT(*) AS papers, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS with_knowledge_graph, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain
```
Correct answer: Education, 15, 3, 2.455; Finance, 13, 4, 4.0; General or other, 136, 18, 4.398; Legal, 4, 0, 2.25; ... (5 rows)

**QF7.** For each reasoning depth, how many papers evaluate on HotpotQA and how many on Natural Questions?
```sql
SELECT reasoning_depth, SUM(CASE WHEN evaluation_dataset LIKE '%HotpotQA%' THEN 1 ELSE 0 END) AS on_hotpotqa, SUM(CASE WHEN evaluation_dataset LIKE '%Natural%Q%' OR ('||' || REPLACE(evaluation_dataset, ' ', '') || '||') LIKE '%||NQ||%' OR evaluation_dataset LIKE '%KILT NQ%' THEN 1 ELSE 0 END) AS on_natural_questions FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth
```
Correct answer: multi-hop, 36, 20; single-hop, 1, 12

**QF8.** For each retrieval method, how many papers study multi-hop and how many single-hop reasoning?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, SUM(CASE WHEN reasoning_depth LIKE '%multi-hop%' THEN 1 ELSE 0 END) AS multi_hop, SUM(CASE WHEN reasoning_depth LIKE '%single-hop%' THEN 1 ELSE 0 END) AS single_hop FROM cspaper WHERE retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_family
```
Correct answer: Dense, 48, 68; Graph-based, 14, 7; Hybrid, 28, 6; Other, 9, 3; ... (6 rows)

**QF9.** How many papers, and how many baselines on average, for each combination of reranker and knowledge graph use?
```sql
SELECT uses_reranker, uses_knowledge_graph, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND uses_knowledge_graph IN ('Yes', 'No') GROUP BY uses_reranker, uses_knowledge_graph
```
Correct answer: No, No, 114, 4.259; No, Yes, 17, 4.706; Yes, No, 49, 4.304; Yes, Yes, 13, 5.0

**QF10.** Papers that handle images or audio against papers that do not: how many of each, and how many study multi-hop reasoning?
```sql
SELECT CASE WHEN data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' THEN 'multimodal' ELSE 'text, tables or code' END AS modality, COUNT(*) AS papers, SUM(CASE WHEN reasoning_depth LIKE '%multi-hop%' THEN 1 ELSE 0 END) AS multi_hop FROM cspaper WHERE (data_modality LIKE '%Text%' OR data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' OR data_modality LIKE '%Table%' OR data_modality LIKE '%Code%') GROUP BY modality
```
Correct answer: multimodal, 35, 12; text, tables or code, 156, 94

**QF11.** Which retrieval methods do agent papers with multi-turn retrieval use, most common first?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers FROM cspaper WHERE multi_turn_retrieval = 'Yes' AND use_agent = 'Yes' AND retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_family ORDER BY papers DESC, retrieval_family
```
Correct answer: Dense, 15; Hybrid, 12; Sparse, 3; Graph-based, 1; ... (5 rows)

**QF12.** For each reasoning depth, how many papers report exact match, F1 and accuracy, out of how many papers?
```sql
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN instr(evaluation_metric, 'EM') > 0 OR evaluation_metric LIKE '%Exact Match%' THEN 1 ELSE 0 END) AS report_exact_match, SUM(CASE WHEN evaluation_metric LIKE '%F1%' THEN 1 ELSE 0 END) AS report_f1, SUM(CASE WHEN evaluation_metric LIKE '%Accuracy%' THEN 1 ELSE 0 END) AS report_accuracy FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth
```
Correct answer: multi-hop, 109, 23, 48, 47; single-hop, 88, 6, 17, 35

**QF13.** For agent frameworks with at least three papers, how many papers are there, and what is the average and the largest number of baselines?
```sql
SELECT agent_framework, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines, MAX(baseline_amount) AS most_baselines FROM cspaper WHERE agent_framework IN ('CoT', 'ToT', 'Multi-Agent Collaboration', 'Other') GROUP BY agent_framework HAVING COUNT(*) >= 3
```
Correct answer: CoT, 8, 5.875, 10; Multi-Agent Collaboration, 12, 4.0, 8; Other, 27, 4.958, 14

**QF15.** For each application domain, how many papers compare against more baselines than the average paper, out of how many?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' ELSE 'General or other' END AS domain, COUNT(*) AS papers, SUM(CASE WHEN baseline_amount > (SELECT AVG(baseline_amount) FROM cspaper) THEN 1 ELSE 0 END) AS above_average FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain
```
Correct answer: Education, 15, 2; Finance, 13, 4; General or other, 136, 51; Legal, 4, 0; ... (5 rows)

**QF16.** For papers with and without agents, how many report HotpotQA results, out of how many papers?
```sql
SELECT use_agent, SUM(CASE WHEN performance_on_hotpotqa IS NOT NULL AND performance_on_hotpotqa <> '' THEN 1 ELSE 0 END) AS report_hotpotqa, COUNT(*) AS papers FROM cspaper GROUP BY use_agent
```
Correct answer: No, 22, 153; Yes, 9, 47

**QF17.** How many papers use GPT-4o or GPT-4o-mini as a generator?
```sql
SELECT COUNT(*) AS papers FROM cspaper WHERE generator_model LIKE '%GPT-4o%' OR generator_model LIKE '%GPT4-o%'
```
Correct answer: 38

**QF19.** For single-hop and multi-hop papers, how many papers are there, and what is the average and the largest number of baselines, highest average first?
```sql
SELECT reasoning_depth, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines, MAX(baseline_amount) AS most_baselines FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth ORDER BY average_baselines DESC, reasoning_depth
```
Correct answer: multi-hop, 109, 4.893, 22; single-hop, 88, 3.554, 11

## Research papers on RAG (cspaper): build questions (30)

**QB1.** For each retrieval method, how many papers are there, how many support multi-turn retrieval and how many use a knowledge graph?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers, SUM(CASE WHEN multi_turn_retrieval = 'Yes' THEN 1 ELSE 0 END) AS multi_turn, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS with_knowledge_graph FROM cspaper WHERE retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_family
```
Correct answer: Dense, 116, 32, 8; Graph-based, 21, 4, 14; Hybrid, 34, 16, 10; Other, 13, 3, 0; ... (6 rows)

**QB2.** For each kind of input data (images or audio, tables or code, text only), how many papers are there, and what is the average and largest number of baselines they compare against?
```sql
SELECT CASE WHEN data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' THEN 'multimodal' WHEN data_modality LIKE '%Table%' OR data_modality LIKE '%Code%' THEN 'text with tables or code' ELSE 'text only' END AS modality, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines, MAX(baseline_amount) AS most_baselines FROM cspaper WHERE (data_modality LIKE '%Text%' OR data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' OR data_modality LIKE '%Table%' OR data_modality LIKE '%Code%') GROUP BY modality
```
Correct answer: multimodal, 35, 4.969, 22; text only, 138, 4.038, 14; text with tables or code, 18, 5.529, 14

**QB3.** How many papers, and how many baselines on average, for each combination of reranker use and multi-turn retrieval?
```sql
SELECT uses_reranker, multi_turn_retrieval, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND multi_turn_retrieval IN ('Yes', 'No') GROUP BY uses_reranker, multi_turn_retrieval
```
Correct answer: No, No, 97, 4.086; No, Yes, 35, 4.909; Yes, No, 42, 4.5; Yes, Yes, 20, 4.25

**QB4.** How many papers are there for each combination of knowledge graph use and multi-turn retrieval?
```sql
SELECT uses_knowledge_graph, multi_turn_retrieval, COUNT(*) AS papers FROM cspaper WHERE uses_knowledge_graph IN ('Yes', 'No') AND multi_turn_retrieval IN ('Yes', 'No') GROUP BY uses_knowledge_graph, multi_turn_retrieval
```
Correct answer: No, No, 121; No, Yes, 45; Yes, No, 19; Yes, Yes, 13

**QB5.** Which application domains have at least 10 papers, and how many of those papers use a reranker, largest domain first?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' WHEN application_domain LIKE '%Academic%' THEN 'Academic' WHEN application_domain LIKE '%General%' THEN 'General' ELSE 'Other' END AS domain, COUNT(*) AS papers, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain HAVING COUNT(*) >= 10 ORDER BY papers DESC, domain
```
Correct answer: General, 97, 28; Medical, 31, 14; Other, 25, 4; Education, 15, 3; ... (6 rows)

**QB6.** Which three retrieval methods most often come with a reranker, as a share of their papers?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, AVG(CASE WHEN uses_reranker = 'Yes' THEN 1.0 ELSE 0.0 END) AS reranker_share, COUNT(*) AS papers FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_family ORDER BY reranker_share DESC, retrieval_family LIMIT 3
```
Correct answer: Hybrid, 0.606, 33; Dense, 0.301, 113; Graph-based, 0.263, 19

**QB7.** How many papers compare against 1-2, 3-5 and 6 or more baselines, and how many in each group use a reranker?
```sql
SELECT CASE WHEN baseline_amount <= 2 THEN '1-2' WHEN baseline_amount <= 5 THEN '3-5' ELSE '6 or more' END AS baseline_bucket, COUNT(*) AS papers, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker FROM cspaper WHERE baseline_amount IS NOT NULL GROUP BY baseline_bucket
```
Correct answer: 1-2, 72, 20; 3-5, 60, 17; 6 or more, 56, 19

**QB9.** Do papers with 'graph' in the title actually use a knowledge graph? Count papers and knowledge graph users for titles with and without it.
```sql
SELECT CASE WHEN paper_name LIKE '%graph%' THEN 'graph in title' ELSE 'no graph in title' END AS title_group, COUNT(*) AS papers, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS with_knowledge_graph FROM cspaper GROUP BY title_group
```
Correct answer: graph in title, 19, 14; no graph in title, 181, 18

**QB11.** Among papers that use a reranker, which retrieval methods have at least 5 papers, with their average and largest number of baselines?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines, MAX(baseline_amount) AS most_baselines FROM cspaper WHERE uses_reranker = 'Yes' GROUP BY retrieval_family HAVING COUNT(*) >= 5
```
Correct answer: Dense, 34, 4.433, 10; Graph-based, 5, 4.4, 9; Hybrid, 20, 4.167, 14

**QB12.** For each application domain, how many papers work on text only and how many on multimodal data?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' ELSE 'General or other' END AS domain, SUM(CASE WHEN data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' THEN 1 ELSE 0 END) AS multimodal, SUM(CASE WHEN data_modality = 'Text' THEN 1 ELSE 0 END) AS text_only FROM cspaper GROUP BY domain
```
Correct answer: Education, 2, 11; Finance, 3, 7; General or other, 25, 94; Legal, 0, 4; ... (5 rows)

**QB13.** How many papers are there for each combination of text-only versus multimodal input and reranker use?
```sql
SELECT CASE WHEN data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' THEN 'multimodal' ELSE 'text or structured' END AS modality, uses_reranker, COUNT(*) AS papers FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND (data_modality LIKE '%Text%' OR data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' OR data_modality LIKE '%Table%' OR data_modality LIKE '%Code%') GROUP BY modality, uses_reranker
```
Correct answer: multimodal, No, 24; multimodal, Yes, 9; text or structured, No, 104; text or structured, Yes, 49

**QB14.** Which retrieval methods compare against more baselines on average than papers overall?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, AVG(baseline_amount) AS average_baselines FROM cspaper GROUP BY retrieval_family HAVING AVG(baseline_amount) > (SELECT AVG(baseline_amount) FROM cspaper)
```
Correct answer: Graph-based, 4.524; Hybrid, 5.0; Other, 6.154

**QB15.** For each application domain, how many papers compare against only one baseline, and what is the largest number of baselines compared?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' ELSE 'General or other' END AS domain, COUNT(*) AS papers, SUM(CASE WHEN baseline_amount = 1 THEN 1 ELSE 0 END) AS one_baseline, MAX(baseline_amount) AS most_baselines FROM cspaper WHERE baseline_amount IS NOT NULL AND application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain
```
Correct answer: Education, 11, 4, 6; Finance, 12, 2, 10; General or other, 133, 19, 22; Legal, 4, 1, 3; ... (5 rows)

**QB16.** For each retrieval method, how many papers use both a reranker and a knowledge graph?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers, SUM(CASE WHEN uses_reranker = 'Yes' AND uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS reranker_and_graph FROM cspaper WHERE retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_family
```
Correct answer: Dense, 116, 2; Graph-based, 21, 4; Hybrid, 34, 7; Other, 13, 0; ... (6 rows)

**QB17.** How many papers use a knowledge graph and also support multi-turn retrieval?
```sql
SELECT COUNT(*) AS papers FROM cspaper WHERE uses_knowledge_graph = 'Yes' AND multi_turn_retrieval = 'Yes'
```
Correct answer: 13

**QB18.** Which application domains with at least 5 papers compare against the most baselines on average? Top three.
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' WHEN application_domain LIKE '%Academic%' THEN 'Academic' WHEN application_domain LIKE '%General%' THEN 'General' ELSE 'Other' END AS domain, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain HAVING COUNT(*) >= 5 ORDER BY average_baselines DESC, domain LIMIT 3
```
Correct answer: Medical, 31, 5.143; General, 97, 4.8; Academic, 14, 4.769

**QB19.** For each kind of input data, what share of papers support multi-turn retrieval?
```sql
SELECT CASE WHEN data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' THEN 'multimodal' WHEN data_modality LIKE '%Table%' OR data_modality LIKE '%Code%' THEN 'text with tables or code' ELSE 'text only' END AS modality, COUNT(*) AS papers, AVG(CASE WHEN multi_turn_retrieval = 'Yes' THEN 1.0 ELSE 0.0 END) AS multi_turn_share FROM cspaper WHERE (data_modality LIKE '%Text%' OR data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' OR data_modality LIKE '%Table%' OR data_modality LIKE '%Code%') AND multi_turn_retrieval IN ('Yes', 'No') GROUP BY modality
```
Correct answer: multimodal, 35, 0.171; text only, 138, 0.275; text with tables or code, 18, 0.5

**QB20.** For each retrieval method, how many papers compare against at least 5 baselines and how many against fewer?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, SUM(CASE WHEN baseline_amount >= 5 THEN 1 ELSE 0 END) AS five_or_more, SUM(CASE WHEN baseline_amount < 5 THEN 1 ELSE 0 END) AS fewer_than_five FROM cspaper GROUP BY retrieval_family
```
Correct answer: Dense, 33, 74; Graph-based, 8, 13; Hybrid, 16, 16; Other, 7, 6; ... (6 rows)

**QB21.** How many papers target a single application domain and how many several, and how many baselines do they compare on average?
```sql
SELECT CASE WHEN application_domain LIKE '%||%' THEN 'several domains' ELSE 'one domain' END AS domain_count, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain_count
```
Correct answer: one domain, 160, 4.052; several domains, 39, 5.514

**QB22.** Papers that combine several retrieval methods against papers with one: how many of each, and how many use a reranker?
```sql
SELECT CASE WHEN retrieval_method LIKE '%||%' OR retrieval_method LIKE '%Hybrid%' THEN 'combined retrieval' ELSE 'single retrieval' END AS retrieval_mix, COUNT(*) AS papers, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker FROM cspaper WHERE retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_mix
```
Correct answer: combined retrieval, 58, 29; single retrieval, 141, 33

**QB23.** How many papers are there for each combination of knowledge graph use and retrieval method?
```sql
SELECT uses_knowledge_graph, CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers FROM cspaper WHERE uses_knowledge_graph IN ('Yes', 'No') AND retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY uses_knowledge_graph, retrieval_family
```
Correct answer: No, Dense, 106; No, Graph-based, 7; No, Hybrid, 24; No, Other, 13; ... (9 rows)

**QB24.** How many papers are there for each combination of application domain and multi-turn retrieval?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' ELSE 'General or other' END AS domain, multi_turn_retrieval, COUNT(*) AS papers FROM cspaper WHERE multi_turn_retrieval IN ('Yes', 'No') AND application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain, multi_turn_retrieval
```
Correct answer: Education, No, 12; Education, Yes, 3; Finance, No, 6; Finance, Yes, 7; ... (10 rows)

**QB25.** For papers with and without a reranker, how many handle tables, images and code?
```sql
SELECT uses_reranker, SUM(CASE WHEN data_modality LIKE '%Table%' THEN 1 ELSE 0 END) AS with_tables, SUM(CASE WHEN data_modality LIKE '%Image%' THEN 1 ELSE 0 END) AS with_images, SUM(CASE WHEN data_modality LIKE '%Code%' THEN 1 ELSE 0 END) AS with_code FROM cspaper WHERE uses_reranker IN ('Yes', 'No') GROUP BY uses_reranker
```
Correct answer: No, 9, 18, 8; Yes, 6, 8, 3

**QB26.** For each retrieval method, how many papers are there and how many baseline comparisons do they report in total?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers, SUM(baseline_amount) AS total_baselines FROM cspaper WHERE retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY retrieval_family
```
Correct answer: Dense, 116, 418; Graph-based, 21, 95; Hybrid, 34, 160; Other, 13, 80; ... (6 rows)

**QB27.** Which application domains have at least 3 papers that use a knowledge graph, and how many papers do they have overall?
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' WHEN application_domain LIKE '%Academic%' THEN 'Academic' WHEN application_domain LIKE '%General%' THEN 'General' ELSE 'Other' END AS domain, COUNT(*) AS papers, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS with_knowledge_graph FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain HAVING SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) >= 3
```
Correct answer: Academic, 14, 5; Education, 15, 3; Finance, 13, 4; General, 97, 9; ... (6 rows)

**QB28.** What are the three most common retrieval methods among papers with multi-turn retrieval?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers FROM cspaper WHERE multi_turn_retrieval = 'Yes' GROUP BY retrieval_family ORDER BY papers DESC, retrieval_family LIMIT 3
```
Correct answer: Dense, 32; Hybrid, 16; Graph-based, 4

**QB29.** Do benchmark and evaluation papers compare against fewer baselines than method papers? Papers and average baselines for titles with and without 'benchmark' or 'evaluat'.
```sql
SELECT CASE WHEN paper_name LIKE '%benchmark%' OR paper_name LIKE '%evaluat%' THEN 'benchmark or evaluation' ELSE 'method' END AS paper_kind, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE baseline_amount IS NOT NULL GROUP BY paper_kind
```
Correct answer: benchmark or evaluation, 5, 2.4; method, 183, 4.377

**QB30.** Among medical papers, how many use each retrieval method, and how many of those use a knowledge graph?
```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web%' THEN 'Web search' ELSE 'Other' END AS retrieval_family, COUNT(*) AS papers, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS with_knowledge_graph FROM cspaper WHERE application_domain LIKE '%Medical%' GROUP BY retrieval_family
```
Correct answer: Dense, 14, 1; Graph-based, 3, 3; Hybrid, 12, 3; Other, 2, 0

**QB31.** Which application domains use a reranker more often than the papers as a whole? Papers and reranker share for each.
```sql
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' WHEN application_domain LIKE '%Academic%' THEN 'Academic' WHEN application_domain LIKE '%General%' THEN 'General' ELSE 'Other' END AS domain, COUNT(*) AS papers, AVG(CASE WHEN uses_reranker = 'Yes' THEN 1.0 ELSE 0.0 END) AS reranker_share FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain HAVING AVG(CASE WHEN uses_reranker = 'Yes' THEN 1.0 ELSE 0.0 END) > (SELECT AVG(CASE WHEN uses_reranker = 'Yes' THEN 1.0 ELSE 0.0 END) FROM cspaper WHERE uses_reranker IN ('Yes', 'No'))
```
Correct answer: Academic, 14, 0.571; Finance, 12, 0.333; Medical, 31, 0.452

**QB32.** Do papers with multi-turn retrieval compare against more baselines? For papers with and without it: how many papers, the average number of baselines, how many compare against only one, and how many against six or more.
```sql
SELECT multi_turn_retrieval, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines, SUM(CASE WHEN baseline_amount = 1 THEN 1 ELSE 0 END) AS one_baseline, SUM(CASE WHEN baseline_amount >= 6 THEN 1 ELSE 0 END) AS six_or_more FROM cspaper WHERE multi_turn_retrieval IN ('Yes', 'No') GROUP BY multi_turn_retrieval
```
Correct answer: No, 141, 4.185, 18, 36; Yes, 58, 4.731, 11, 20

## Artist biographies (art): test questions (31)

**Q19.** How many artists were born in Paris?
```sql
SELECT COUNT(*) AS artists FROM art WHERE birth_city LIKE '%Paris%'
```
Correct answer: 31

**QX1.** For painters, sculptors, photographers, printmakers and others: how many were born in Europe and how many in North America?
```sql
SELECT CASE WHEN field LIKE '%Painting%' THEN 'Painting' WHEN field LIKE '%Sculpture%' THEN 'Sculpture' WHEN field LIKE '%Photography%' THEN 'Photography' WHEN field LIKE '%Printmaking%' THEN 'Printmaking' ELSE 'Other' END AS main_field, COUNT(*) AS artists, SUM(CASE WHEN birth_continent = 'Europe' THEN 1 ELSE 0 END) AS born_in_europe, SUM(CASE WHEN birth_continent = 'North America' THEN 1 ELSE 0 END) AS born_in_north_america FROM art WHERE field IS NOT NULL AND field <> '' GROUP BY main_field
```
Correct answer: Other, 96, 50, 26; Painting, 781, 425, 229; Photography, 37, 20, 13; Printmaking, 4, 1, 1; ... (5 rows)

**QX2.** In which cities did at least six artists die (New York, New York City and Manhattan counted as one): how many died there, and how many of them were also born there?
```sql
SELECT CASE WHEN death_city IN ('New York', 'New York City', 'Manhattan') THEN 'New York City' ELSE death_city END AS city, COUNT(*) AS artists, SUM(CASE WHEN birth_city = death_city OR (death_city IN ('New York', 'New York City', 'Manhattan') AND birth_city IN ('New York', 'New York City', 'Manhattan')) THEN 1 ELSE 0 END) AS born_there_too FROM art WHERE death_city IS NOT NULL AND death_city <> '' GROUP BY city HAVING COUNT(*) >= 6
```
Correct answer: London, 33, 7; Los Angeles, 7, 1; Mexico City, 11, 3; New York City, 66, 5; ... (9 rows)

**QX3.** Among artists with a known age, did those born in the 1700s, 1800s and 1900s differ in how long they lived and how often they taught?
```sql
SELECT CASE WHEN birth_date LIKE '17%' THEN '1700s' WHEN birth_date LIKE '18%' THEN '1800s' ELSE '1900s' END AS birth_century, COUNT(*) AS artists, AVG(age) AS average_age, AVG(teaching) AS share_who_taught FROM art WHERE (birth_date LIKE '17%' OR birth_date LIKE '18%' OR birth_date LIKE '19%') AND age IS NOT NULL AND age <> '' GROUP BY birth_century
```
Correct answer: 1700s, 42, 69.857, 0.143; 1800s, 376, 69.269, 0.144; 1900s, 333, 66.889, 0.279

**QX4.** Per century of activity: how many artists' featured images show people, geometric shapes, landscape elements (trees, mountains, sky, water, rivers, lakes) or buildings?
```sql
SELECT century, COUNT(*) AS artists, SUM(CASE WHEN object LIKE '%Human%' OR object LIKE '%Person%' OR object LIKE '%People%' OR object LIKE '%Figure%' OR object LIKE '%Woman%' OR object LIKE '%Women%' THEN 1 ELSE 0 END) AS people, SUM(CASE WHEN object LIKE '%Geometric%' OR object LIKE '%Shape%' THEN 1 ELSE 0 END) AS geometric_shapes, SUM(CASE WHEN object GLOB '*Tree*' OR object LIKE '%Mountain%' OR object LIKE '%Sky%' OR object LIKE '%Water%' OR object LIKE '%River%' OR object LIKE '%Lake%' THEN 1 ELSE 0 END) AS landscape_elements, SUM(CASE WHEN object LIKE '%Building%' OR object LIKE '%City%' OR object LIKE '%Architecture%' OR object LIKE '%Street%' THEN 1 ELSE 0 END) AS buildings FROM art WHERE century IS NOT NULL AND century <> '' AND object IS NOT NULL AND object <> '' GROUP BY century
```
Correct answer: 19th, 44, 25, 0, 12, 3; 19th-20th, 319, 155, 20, 71, 28; 20th, 149, 58, 25, 11, 3; 20th-21st, 153, 49, 30, 12, 8

**QX5.** For portraits, landscapes, still lifes, abstract and other images: how many have a balanced, an asymmetrical, a centred or a dynamic composition?
```sql
SELECT CASE WHEN image_genre LIKE '%Portrait%' THEN 'Portrait' WHEN image_genre LIKE '%Landscape%' THEN 'Landscape' WHEN image_genre LIKE '%Still Life%' THEN 'Still life' WHEN image_genre LIKE '%Abstract%' THEN 'Abstract' ELSE 'Other' END AS genre_group, COUNT(*) AS artists, SUM(CASE WHEN composition LIKE '%Balanced%' THEN 1 ELSE 0 END) AS balanced, SUM(CASE WHEN composition LIKE '%Asymmetr%' THEN 1 ELSE 0 END) AS asymmetrical, SUM(CASE WHEN composition LIKE '%Cent%' THEN 1 ELSE 0 END) AS centred, SUM(CASE WHEN composition LIKE '%Dynamic%' THEN 1 ELSE 0 END) AS dynamic FROM art WHERE image_genre IS NOT NULL AND image_genre <> '' AND composition IS NOT NULL AND composition <> '' GROUP BY genre_group
```
Correct answer: Abstract, 80, 3, 17, 3, 16; Landscape, 159, 60, 10, 22, 14; Other, 322, 49, 32, 70, 51; Portrait, 226, 30, 11, 126, 11; ... (5 rows)

**QX6.** Which five nationalities won the most awards in total, and how many of their artists won at least one?
```sql
SELECT nationality, SUM(awards) AS total_awards, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE nationality IS NOT NULL AND nationality <> '' AND nationality NOT LIKE '%||%' GROUP BY nationality ORDER BY total_awards DESC, nationality LIMIT 5
```
Correct answer: American, 142, 47; British, 62, 14; French, 29, 15; Mexican, 15, 5; ... (5 rows)

**QX7.** How many artists died in the 1800s, the 1900s, the 2000s, or have no recorded death, and how many awards did each group win on average?
```sql
SELECT CASE WHEN death_date LIKE '18%' THEN 'died 1800s' WHEN death_date LIKE '19%' THEN 'died 1900s' WHEN death_date LIKE '20%' THEN 'died 2000s' ELSE 'no recorded death' END AS death_period, COUNT(*) AS artists, AVG(awards) AS average_awards FROM art WHERE awards IS NOT NULL AND awards <> '' GROUP BY death_period
```
Correct answer: died 1800s, 92, 0.141; died 1900s, 503, 0.344; died 2000s, 166, 0.843; no recorded death, 239, 0.305

**QX8.** Which birth cities produced at least eight artists (New York, New York City and Manhattan counted as one), and how many of those artists won an award?
```sql
SELECT CASE WHEN birth_city IN ('New York', 'New York City', 'Manhattan') THEN 'New York City' ELSE birth_city END AS city, COUNT(*) AS artists, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE birth_city IS NOT NULL AND birth_city <> '' AND birth_city NOT LIKE '%||%' GROUP BY city HAVING COUNT(*) >= 8
```
Correct answer: Berlin, 9, 1; Boston, 8, 1; Chicago, 10, 1; London, 23, 3; ... (7 rows)

**QX9.** For American, French, British, German, Italian and Japanese artists (English, Scottish and Welsh counted as British), how many awards did teachers and non-teachers win on average?
```sql
SELECT CASE WHEN nationality IN ('English', 'Scottish', 'Welsh') THEN 'British' ELSE nationality END AS nation, teaching, COUNT(*) AS artists, AVG(awards) AS average_awards FROM art WHERE nationality IN ('American', 'French', 'British', 'English', 'Scottish', 'Welsh', 'German', 'Italian', 'Japanese') GROUP BY nation, teaching
```
Correct answer: American, 0, 198, 0.475; American, 1, 56, 0.857; British, 0, 75, 0.72; British, 1, 20, 0.4; ... (12 rows)

**QX10.** Among artists who have died: how many painters, sculptors, photographers and others were there, what was their average lifespan, and how many lived longer than the average deceased artist?
```sql
SELECT CASE WHEN field LIKE '%Painting%' THEN 'Painting' WHEN field LIKE '%Sculpture%' THEN 'Sculpture' WHEN field LIKE '%Photography%' THEN 'Photography' ELSE 'Other' END AS main_field, COUNT(*) AS artists, AVG(age) AS average_lifespan, SUM(CASE WHEN CAST(age AS INTEGER) > (SELECT AVG(CAST(age AS INTEGER)) FROM art WHERE age IS NOT NULL AND age <> '' AND death_date IS NOT NULL AND death_date <> '') THEN 1 ELSE 0 END) AS longer_than_average FROM art WHERE age IS NOT NULL AND age <> '' AND death_date IS NOT NULL AND death_date <> '' GROUP BY main_field
```
Correct answer: Other, 62, 65.403, 35; Painting, 621, 68.14, 381; Photography, 25, 71.44, 19; Sculpture, 43, 72.023, 30

**QX11.** For artists affiliated with an academy, a school or college, or something else: how many, how many awards in total, and how many won at least one?
```sql
SELECT CASE WHEN art_institution LIKE '%Academ%' OR art_institution LIKE '%Akadem%' THEN 'Academy' WHEN art_institution LIKE '%School%' OR art_institution LIKE '%College%' OR art_institution LIKE '%Schule%' THEN 'School or college' ELSE 'Other' END AS institution_group, COUNT(*) AS artists, SUM(awards) AS total_awards, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE art_institution IS NOT NULL AND art_institution <> '' GROUP BY institution_group
```
Correct answer: Academy, 245, 73, 40; Other, 200, 70, 38; School or college, 264, 140, 43

**QX12.** Per century of activity: how many artists, how many awards did they win in total, and how many won at least one?
```sql
SELECT century, COUNT(*) AS artists, SUM(CAST(awards AS INTEGER)) AS total_awards, SUM(CASE WHEN CAST(awards AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE century IS NOT NULL AND century <> '' AND awards IS NOT NULL AND awards <> '' GROUP BY century
```
Correct answer: 19th, 44, 6, 4; 19th-20th, 332, 144, 58; 20th, 167, 28, 16; 20th-21st, 166, 140, 48

**QF1.** Per birth continent (Australia counted with Oceania), among artists with a known age: how many artists, their average age, their total awards, and how many taught?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, COUNT(*) AS artists, AVG(age) AS average_age, SUM(awards) AS total_awards, SUM(teaching) AS teachers FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND age IS NOT NULL AND age <> '' GROUP BY continent
```
Correct answer: Africa, 12, 68.667, 9, 5; Asia, 47, 55.957, 17, 12; Europe, 437, 68.616, 141, 80; North America, 208, 70.558, 145, 51; ... (6 rows)

**QF2.** How many artists are there for each birth continent (Australia counted with Oceania) and century of activity?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, century, COUNT(*) AS artists FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND century IS NOT NULL AND century <> '' GROUP BY continent, century
```
Correct answer: Africa, 19th-20th, 2; Africa, 20th, 3; Africa, 20th-21st, 7; Asia, 19th, 1; ... (21 rows)

**QF3.** Which ten birth countries have the most award-winning artists (spelling variants of the United States, the United Kingdom and Russia merged)?
```sql
SELECT CASE WHEN birth_country IN ('United States', 'USA', 'America') THEN 'United States' WHEN birth_country IN ('United Kingdom', 'England', 'Scotland', 'Britain') THEN 'United Kingdom' WHEN birth_country IN ('Russia', 'Russian', 'Russian Federation', 'Russian Empire', 'Soviet Union', 'USSR') THEN 'Russia' ELSE birth_country END AS country, COUNT(*) AS award_winners FROM art WHERE awards <> '' AND CAST(awards AS INTEGER) >= 1 AND birth_country IS NOT NULL AND birth_country <> '' AND birth_country NOT LIKE '%||%' GROUP BY country ORDER BY award_winners DESC, country LIMIT 10
```
Correct answer: United States, 47; France, 16; United Kingdom, 14; Italy, 8; ... (10 rows)

**QF4.** For nationalities with at least 20 artists, how many awards does an artist win on average?
```sql
SELECT nationality, COUNT(*) AS artists, AVG(awards) AS average_awards FROM art WHERE nationality IS NOT NULL AND nationality <> '' AND nationality NOT LIKE '%||%' GROUP BY nationality HAVING COUNT(*) >= 20
```
Correct answer: American, 254, 0.559; British, 80, 0.775; French, 86, 0.337; German, 48, 0.229; ... (7 rows)

**QF5.** Among artists with a known age, painters, sculptors, photographers and others: how many, how many awards on average, and how old on average?
```sql
SELECT CASE WHEN field LIKE '%Painting%' THEN 'Painting' WHEN field LIKE '%Sculpture%' THEN 'Sculpture' WHEN field LIKE '%Photography%' THEN 'Photography' ELSE 'Other' END AS main_field, COUNT(*) AS artists, AVG(awards) AS average_awards, AVG(age) AS average_age FROM art WHERE field IS NOT NULL AND field <> '' AND age IS NOT NULL AND age <> '' GROUP BY main_field
```
Correct answer: Other, 62, 1.774, 65.403; Painting, 621, 0.295, 68.14; Photography, 25, 0.24, 71.44; Sculpture, 43, 0.605, 72.023

**QF6.** Per century of activity, among artists with a known age: how many artists, what share taught, and how old did they get on average?
```sql
SELECT century, COUNT(*) AS artists, AVG(teaching) AS share_who_taught, AVG(age) AS average_age FROM art WHERE century IS NOT NULL AND century <> '' AND age IS NOT NULL AND age <> '' GROUP BY century
```
Correct answer: 19th, 44, 0.023, 56.409; 19th-20th, 332, 0.16, 70.973; 20th, 167, 0.18, 51.689; 20th-21st, 166, 0.38, 82.181

**QF7.** From which birth countries did more than ten artists die abroad (spelling variants of the United States, the United Kingdom and Russia counted as the same country)?
```sql
SELECT CASE WHEN birth_country IN ('United States', 'USA', 'America') THEN 'United States' WHEN birth_country IN ('United Kingdom', 'England', 'Scotland', 'Britain') THEN 'United Kingdom' WHEN birth_country IN ('Russia', 'Russian', 'Russian Federation', 'Russian Empire', 'Soviet Union', 'USSR') THEN 'Russia' ELSE birth_country END AS country, COUNT(*) AS died_abroad FROM art WHERE birth_country IS NOT NULL AND birth_country <> '' AND birth_country NOT LIKE '%||%' AND death_country IS NOT NULL AND death_country <> '' AND (CASE WHEN death_country IN ('United States', 'America', 'California') THEN 'United States' WHEN death_country IN ('United Kingdom', 'England', 'Scotland', 'London') THEN 'United Kingdom' WHEN death_country IN ('Russia', 'Russian', 'Russian Federation', 'Federation', 'Soviet Union') THEN 'Russia' ELSE death_country END) <> (CASE WHEN birth_country IN ('United States', 'USA', 'America') THEN 'United States' WHEN birth_country IN ('United Kingdom', 'England', 'Scotland', 'Britain') THEN 'United Kingdom' WHEN birth_country IN ('Russia', 'Russian', 'Russian Federation', 'Russian Empire', 'Soviet Union', 'USSR') THEN 'Russia' ELSE birth_country END) GROUP BY country HAVING COUNT(*) > 10
```
Correct answer: France, 12; Germany, 20; Russia, 11; United Kingdom, 18; ... (5 rows)

**QF8.** Among artists with a known age, Abstract Expressionists, Impressionists, Expressionists, Surrealists and others (by style): how many, how old on average, and how many awards on average?
```sql
SELECT CASE WHEN style LIKE '%Abstract Expressionism%' THEN 'Abstract Expressionism' WHEN style LIKE '%Impressionism%' THEN 'Impressionism' WHEN style LIKE '%Expressionism%' THEN 'Expressionism' WHEN style LIKE '%Surrealism%' THEN 'Surrealism' ELSE 'Other' END AS movement, COUNT(*) AS artists, AVG(age) AS average_age, AVG(awards) AS average_awards FROM art WHERE style IS NOT NULL AND style <> '' AND age IS NOT NULL AND age <> '' GROUP BY movement
```
Correct answer: Abstract Expressionism, 38, 78.316, 0.447; Expressionism, 72, 72.986, 0.847; Impressionism, 71, 68.423, 0.296; Other, 507, 66.341, 0.418; ... (5 rows)

**QF9.** By marital status, among artists with a known age: how many, how old did they get, and how many awards did they win on average?
```sql
SELECT marriage, COUNT(*) AS artists, AVG(age) AS average_age, AVG(awards) AS average_awards FROM art WHERE marriage IS NOT NULL AND marriage <> '' AND age IS NOT NULL AND age <> '' GROUP BY marriage
```
Correct answer: Cohabiting, 1, 69.0, 0.0; Divorced, 7, 65.714, 0.286; Married, 181, 71.149, 0.702; Remarried, 22, 77.955, 2.364; ... (7 rows)

**QF10.** Which five cities were the most artists born in (New York, New York City and Manhattan counted as one)?
```sql
SELECT CASE WHEN birth_city IN ('New York', 'New York City', 'Manhattan') THEN 'New York City' ELSE birth_city END AS city, COUNT(*) AS artists FROM art WHERE birth_city IS NOT NULL AND birth_city <> '' AND birth_city NOT LIKE '%||%' GROUP BY city ORDER BY artists DESC, city LIMIT 5
```
Correct answer: Paris, 30; New York City, 29; London, 23; Philadelphia, 12; ... (5 rows)

**QF11.** Per birth continent (Australia counted with Oceania): how many artists, and how many of them were born in the 1800s and in the 1900s?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, COUNT(*) AS artists, SUM(CASE WHEN birth_date LIKE '18%' THEN 1 ELSE 0 END) AS born_1800s, SUM(CASE WHEN birth_date LIKE '19%' THEN 1 ELSE 0 END) AS born_1900s FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' GROUP BY continent
```
Correct answer: Africa, 19, 2, 15; Asia, 79, 15, 55; Europe, 529, 274, 220; North America, 303, 69, 221; ... (6 rows)

**QF12.** For each century of activity and main field: how many artists, and how many awards does an artist win on average?
```sql
SELECT century, CASE WHEN field LIKE '%Painting%' THEN 'Painting' WHEN field LIKE '%Sculpture%' THEN 'Sculpture' ELSE 'Other' END AS main_field, COUNT(*) AS artists, AVG(awards) AS average_awards FROM art WHERE century IS NOT NULL AND century <> '' AND field IS NOT NULL AND field <> '' GROUP BY century, main_field
```
Correct answer: 19th, Other, 7, 0.0; 19th, Painting, 36, 0.167; 19th, Sculpture, 1, 0.0; 19th-20th, Other, 36, 1.694; ... (12 rows)

**QF13.** In which ten cities did the most European-born artists die (New York, New York City and Manhattan counted as one)?
```sql
SELECT CASE WHEN death_city IN ('New York', 'New York City', 'Manhattan') THEN 'New York City' ELSE death_city END AS city, COUNT(*) AS artists FROM art WHERE birth_continent = 'Europe' AND death_city IS NOT NULL AND death_city <> '' GROUP BY city ORDER BY artists DESC, city LIMIT 10
```
Correct answer: Paris, 54; London, 28; New York City, 23; Rome, 6; ... (10 rows)

**QF15.** How many portrait, landscape, still-life and other artists come from each birth continent (Australia counted with Oceania)?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, CASE WHEN image_genre LIKE '%Portrait%' THEN 'Portrait' WHEN image_genre LIKE '%Landscape%' THEN 'Landscape' WHEN image_genre LIKE '%Still Life%' THEN 'Still life' ELSE 'Other' END AS genre_group, COUNT(*) AS artists FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND image_genre IS NOT NULL AND image_genre <> '' GROUP BY continent, genre_group
```
Correct answer: Africa, Landscape, 2; Africa, Other, 7; Africa, Portrait, 7; Africa, Still life, 1; ... (23 rows)

**QF16.** Per birth continent (Australia counted with Oceania): how many artists, and how many won more awards than the average artist?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, COUNT(*) AS artists, SUM(CASE WHEN CAST(awards AS INTEGER) > (SELECT AVG(CAST(awards AS INTEGER)) FROM art WHERE awards IS NOT NULL AND awards <> '') THEN 1 ELSE 0 END) AS above_average_awards FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND awards IS NOT NULL AND awards <> '' GROUP BY continent
```
Correct answer: Africa, 19, 4; Asia, 79, 9; Europe, 529, 79; North America, 303, 58; ... (6 rows)

**QF17.** For the ten nationalities with the most artists: how many artists, and the most awards won by one of them?
```sql
SELECT nationality, COUNT(*) AS artists, MAX(CAST(awards AS INTEGER)) AS most_awards FROM art WHERE nationality IS NOT NULL AND nationality <> '' AND nationality NOT LIKE '%||%' GROUP BY nationality ORDER BY artists DESC, nationality LIMIT 10
```
Correct answer: American, 254, 50; French, 86, 6; British, 80, 43; German, 48, 4; ... (10 rows)

**QF18.** Per century of activity, how many artists' featured images have a balanced, asymmetrical, centred or other composition?
```sql
SELECT century, CASE WHEN composition LIKE '%Balanced%' THEN 'Balanced' WHEN composition LIKE '%Asymmetr%' THEN 'Asymmetrical' WHEN composition LIKE '%Cent%' THEN 'Centred' ELSE 'Other' END AS composition_group, COUNT(*) AS artists FROM art WHERE century IS NOT NULL AND century <> '' AND composition IS NOT NULL AND composition <> '' GROUP BY century, composition_group
```
Correct answer: 19th, Asymmetrical, 3; 19th, Balanced, 14; 19th, Centred, 11; 19th, Other, 16; ... (16 rows)

**QF20.** Among artists with a known age, how old did artists of each zodiac sign get on average?
```sql
SELECT zodiac, COUNT(*) AS artists, AVG(age) AS average_age FROM art WHERE zodiac IS NOT NULL AND zodiac <> '' AND age IS NOT NULL AND age <> '' GROUP BY zodiac
```
Correct answer: Aquarius, 62, 67.645; Aries, 81, 69.37; Cancer, 47, 65.043; Gemini, 66, 70.545; ... (11 rows)

## Artist biographies (art): build questions (40)

**QB1.** Per birth continent (Australia counted with Oceania): how many artists are there, how many of them taught at an institution, and what share taught?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, COUNT(*) AS artists, SUM(teaching) AS teachers, AVG(teaching) AS share_who_taught FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' GROUP BY continent
```
Correct answer: Africa, 19, 5, 0.263; Asia, 79, 14, 0.177; Europe, 529, 91, 0.172; North America, 303, 67, 0.221; ... (6 rows)

**QB2.** For the ten birth countries with the most artists (spelling variants of the United States, the United Kingdom and Russia merged): how many artists, and how many of them taught?
```sql
SELECT CASE WHEN birth_country IN ('United States', 'USA', 'America') THEN 'United States' WHEN birth_country IN ('United Kingdom', 'England', 'Scotland', 'Britain') THEN 'United Kingdom' WHEN birth_country IN ('Russia', 'Russian', 'Russian Federation', 'Russian Empire', 'Soviet Union', 'USSR') THEN 'Russia' ELSE birth_country END AS country, COUNT(*) AS artists, SUM(teaching) AS teachers FROM art WHERE birth_country IS NOT NULL AND birth_country <> '' AND birth_country NOT LIKE '%||%' GROUP BY country ORDER BY artists DESC, country LIMIT 10
```
Correct answer: United States, 260, 57; United Kingdom, 100, 21; France, 94, 11; Germany, 66, 17; ... (10 rows)

**QB3.** Among artists with a known age, how old did teachers and non-teachers get on average on each birth continent (Australia counted with Oceania)?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, teaching, COUNT(*) AS artists, AVG(age) AS average_age FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND age IS NOT NULL AND age <> '' GROUP BY continent, teaching
```
Correct answer: Africa, 0, 7, 63.143; Africa, 1, 5, 76.4; Asia, 0, 35, 58.057; Asia, 1, 12, 49.833; ... (12 rows)

**QB4.** In which countries did at least ten artists with a known age die (spelling variants of the United States, the United Kingdom and Russia merged), and how old were they on average?
```sql
SELECT CASE WHEN death_country IN ('United States', 'America', 'California') THEN 'United States' WHEN death_country IN ('United Kingdom', 'England', 'Scotland', 'London') THEN 'United Kingdom' WHEN death_country IN ('Russia', 'Russian', 'Russian Federation', 'Federation', 'Soviet Union') THEN 'Russia' ELSE death_country END AS country, COUNT(*) AS artists, AVG(age) AS average_age FROM art WHERE death_country IS NOT NULL AND death_country <> '' AND age IS NOT NULL AND age <> '' GROUP BY country HAVING COUNT(*) >= 10
```
Correct answer: Australia, 13, 67.154; Canada, 11, 77.636; France, 102, 68.069; Germany, 27, 71.556; ... (11 rows)

**QB5.** How many artists were born under each zodiac sign?
```sql
SELECT zodiac, COUNT(*) AS artists FROM art WHERE zodiac IS NOT NULL AND zodiac <> '' GROUP BY zodiac
```
Correct answer: Aquarius, 77; Aries, 105; Cancer, 59; Gemini, 85; ... (11 rows)

**QB6.** Per marital status: how many artists, and what share of them taught?
```sql
SELECT marriage, COUNT(*) AS artists, AVG(teaching) AS share_who_taught FROM art WHERE marriage IS NOT NULL AND marriage <> '' GROUP BY marriage
```
Correct answer: Cohabiting, 2, 0.5; Divorced, 13, 0.077; Married, 196, 0.327; Remarried, 28, 0.25; ... (7 rows)

**QB7.** On each birth continent (Australia counted with Oceania), how many artists make bright, dark, neutral or otherwise toned images?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, CASE WHEN tone LIKE '%Bright%' THEN 'Bright' WHEN tone LIKE '%Dark%' THEN 'Dark' WHEN tone LIKE '%Neutral%' THEN 'Neutral' ELSE 'Other' END AS tone_group, COUNT(*) AS artists FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND tone IS NOT NULL AND tone <> '' GROUP BY continent, tone_group
```
Correct answer: Africa, Bright, 5; Africa, Dark, 1; Africa, Neutral, 10; Africa, Other, 3; ... (23 rows)

**QB8.** For Surrealists, Abstract Expressionists, Impressionists, Pop artists, Realists and others (by art movement): how many artists, and how many taught?
```sql
SELECT CASE WHEN art_movement LIKE '%Abstract Expressionism%' THEN 'Abstract Expressionism' WHEN art_movement LIKE '%Surrealism%' THEN 'Surrealism' WHEN art_movement LIKE '%Impressionism%' THEN 'Impressionism' WHEN art_movement LIKE '%Pop Art%' THEN 'Pop Art' WHEN art_movement LIKE '%Realism%' THEN 'Realism' ELSE 'Other' END AS movement, COUNT(*) AS artists, SUM(teaching) AS teachers FROM art WHERE art_movement IS NOT NULL AND art_movement <> '' GROUP BY movement
```
Correct answer: Abstract Expressionism, 54, 12; Impressionism, 62, 11; Other, 537, 112; Pop Art, 26, 6; ... (6 rows)

**QB9.** How many European-born and North American-born artists belong to each major art movement?
```sql
SELECT birth_continent, CASE WHEN art_movement LIKE '%Abstract Expressionism%' THEN 'Abstract Expressionism' WHEN art_movement LIKE '%Surrealism%' THEN 'Surrealism' WHEN art_movement LIKE '%Impressionism%' THEN 'Impressionism' WHEN art_movement LIKE '%Pop Art%' THEN 'Pop Art' WHEN art_movement LIKE '%Realism%' THEN 'Realism' ELSE 'Other' END AS movement, COUNT(*) AS artists FROM art WHERE birth_continent IN ('Europe', 'North America') AND art_movement IS NOT NULL AND art_movement <> '' GROUP BY birth_continent, movement
```
Correct answer: Europe, Abstract Expressionism, 8; Europe, Impressionism, 44; Europe, Other, 294; Europe, Pop Art, 14; ... (12 rows)

**QB10.** Among artists with a known age, how many make portraits, landscapes, still lifes, abstract or other images, and how old did they get on average?
```sql
SELECT CASE WHEN image_genre LIKE '%Portrait%' THEN 'Portrait' WHEN image_genre LIKE '%Landscape%' THEN 'Landscape' WHEN image_genre LIKE '%Still Life%' THEN 'Still life' WHEN image_genre LIKE '%Abstract%' THEN 'Abstract' ELSE 'Other' END AS genre_group, COUNT(*) AS artists, AVG(age) AS average_age FROM art WHERE image_genre IS NOT NULL AND image_genre <> '' AND age IS NOT NULL AND age <> '' GROUP BY genre_group
```
Correct answer: Abstract, 56, 75.125; Landscape, 138, 69.862; Other, 240, 67.475; Portrait, 185, 63.47; ... (5 rows)

**QB11.** For the five countries where the most artists died (spelling variants of the United States, the United Kingdom and Russia merged): how many died there, and how many of them were born in Europe and in North America?
```sql
SELECT CASE WHEN death_country IN ('United States', 'America', 'California') THEN 'United States' WHEN death_country IN ('United Kingdom', 'England', 'Scotland', 'London') THEN 'United Kingdom' WHEN death_country IN ('Russia', 'Russian', 'Russian Federation', 'Federation', 'Soviet Union') THEN 'Russia' ELSE death_country END AS country, COUNT(*) AS artists, SUM(CASE WHEN birth_continent = 'Europe' THEN 1 ELSE 0 END) AS born_in_europe, SUM(CASE WHEN birth_continent = 'North America' THEN 1 ELSE 0 END) AS born_in_north_america FROM art WHERE death_country IS NOT NULL AND death_country <> '' GROUP BY country ORDER BY artists DESC, country LIMIT 5
```
Correct answer: United States, 183, 45, 130; France, 103, 95, 5; United Kingdom, 72, 63, 7; Italy, 32, 26, 2; ... (5 rows)

**QB12.** Per birth continent (Australia counted with Oceania), among artists whose birth and death countries are known: how many died in their birth country and how many elsewhere (spelling variants of a country counted as the same country)?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, COUNT(*) AS artists, SUM(CASE WHEN (CASE WHEN death_country IN ('United States', 'America', 'California') THEN 'United States' WHEN death_country IN ('United Kingdom', 'England', 'Scotland', 'London') THEN 'United Kingdom' WHEN death_country IN ('Russia', 'Russian', 'Russian Federation', 'Federation', 'Soviet Union') THEN 'Russia' ELSE death_country END) = (CASE WHEN birth_country IN ('United States', 'USA', 'America') THEN 'United States' WHEN birth_country IN ('United Kingdom', 'England', 'Scotland', 'Britain') THEN 'United Kingdom' WHEN birth_country IN ('Russia', 'Russian', 'Russian Federation', 'Russian Empire', 'Soviet Union', 'USSR') THEN 'Russia' ELSE birth_country END) THEN 1 ELSE 0 END) AS died_in_birth_country, SUM(CASE WHEN (CASE WHEN death_country IN ('United States', 'America', 'California') THEN 'United States' WHEN death_country IN ('United Kingdom', 'England', 'Scotland', 'London') THEN 'United Kingdom' WHEN death_country IN ('Russia', 'Russian', 'Russian Federation', 'Federation', 'Soviet Union') THEN 'Russia' ELSE death_country END) = (CASE WHEN birth_country IN ('United States', 'USA', 'America') THEN 'United States' WHEN birth_country IN ('United Kingdom', 'England', 'Scotland', 'Britain') THEN 'United Kingdom' WHEN birth_country IN ('Russia', 'Russian', 'Russian Federation', 'Russian Empire', 'Soviet Union', 'USSR') THEN 'Russia' ELSE birth_country END) THEN 0 ELSE 1 END) AS died_elsewhere FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND birth_country IS NOT NULL AND birth_country <> '' AND birth_country NOT LIKE '%||%' AND death_country IS NOT NULL AND death_country <> '' GROUP BY continent
```
Correct answer: Africa, 11, 8, 3; Asia, 39, 21, 18; Europe, 374, 228, 146; North America, 166, 136, 30; ... (6 rows)

**QB14.** Which ten single styles have the most artists, and what share of those artists taught?
```sql
SELECT style, COUNT(*) AS artists, AVG(teaching) AS share_who_taught FROM art WHERE style IS NOT NULL AND style <> '' AND style NOT LIKE '%||%' GROUP BY style ORDER BY artists DESC, style LIMIT 10
```
Correct answer: Expressionism, 70, 0.171; Romanticism, 62, 0.177; Conceptual Art, 52, 0.212; Abstract Expressionism, 49, 0.143; ... (10 rows)

**QB15.** Among artists with a known age, how many work in portrait, landscape, abstract, figurative or other genres, and how old did they get on average?
```sql
SELECT CASE WHEN genre LIKE '%Portrait%' THEN 'Portrait' WHEN genre LIKE '%Landscape%' THEN 'Landscape' WHEN genre LIKE '%Abstract%' THEN 'Abstract' WHEN genre LIKE '%Figurative%' THEN 'Figurative' ELSE 'Other' END AS genre_group, COUNT(*) AS artists, AVG(age) AS average_age FROM art WHERE genre IS NOT NULL AND genre <> '' AND age IS NOT NULL AND age <> '' GROUP BY genre_group
```
Correct answer: Abstract, 90, 72.211; Figurative, 12, 69.25; Landscape, 93, 70.978; Other, 185, 67.968; ... (5 rows)

**QB16.** How many artists were self-taught, or affiliated with a Royal Academy (in any country), an Ecole des Beaux-Arts, the Art Students League, another academy or something else, and what share of each group taught?
```sql
SELECT CASE WHEN art_institution LIKE '%Self-taught%' THEN 'Self-taught' WHEN art_institution LIKE '%Royal Academy%' THEN 'Royal Academy' WHEN art_institution LIKE '%Beaux-Arts%' THEN 'Beaux-Arts' WHEN art_institution LIKE '%Art Students League%' THEN 'Art Students League' WHEN art_institution LIKE '%Academ%' OR art_institution LIKE '%Akadem%' THEN 'Other academy' ELSE 'Other' END AS institution_group, COUNT(*) AS artists, AVG(teaching) AS share_who_taught FROM art WHERE art_institution IS NOT NULL AND art_institution <> '' GROUP BY institution_group
```
Correct answer: Art Students League, 34, 0.235; Beaux-Arts, 46, 0.196; Other, 403, 0.206; Other academy, 185, 0.227; ... (6 rows)

**QB18.** Among artists with a plausible recorded age (15 to 110), how many reached under 50, 50 to 69, 70 to 89, and 90 or more years, and what share of each age group taught?
```sql
SELECT CASE WHEN CAST(age AS INTEGER) < 50 THEN 'under 50' WHEN CAST(age AS INTEGER) < 70 THEN '50-69' WHEN CAST(age AS INTEGER) < 90 THEN '70-89' ELSE '90 and over' END AS age_group, COUNT(*) AS artists, AVG(teaching) AS share_who_taught FROM art WHERE age IS NOT NULL AND age <> '' AND CAST(age AS INTEGER) BETWEEN 15 AND 110 GROUP BY age_group
```
Correct answer: 50-69, 193, 0.161; 70-89, 369, 0.217; 90 and over, 80, 0.287; under 50, 74, 0.122

**QB19.** For birth countries with at least 20 artists of known age (spelling variants of the United States, the United Kingdom and Russia merged): how old did their artists get on average, and what share taught?
```sql
SELECT CASE WHEN birth_country IN ('United States', 'USA', 'America') THEN 'United States' WHEN birth_country IN ('United Kingdom', 'England', 'Scotland', 'Britain') THEN 'United Kingdom' WHEN birth_country IN ('Russia', 'Russian', 'Russian Federation', 'Russian Empire', 'Soviet Union', 'USSR') THEN 'Russia' ELSE birth_country END AS country, COUNT(*) AS artists, AVG(age) AS average_age, AVG(teaching) AS share_who_taught FROM art WHERE birth_country IS NOT NULL AND birth_country <> '' AND birth_country NOT LIKE '%||%' AND age IS NOT NULL AND age <> '' GROUP BY country HAVING COUNT(*) >= 20
```
Correct answer: France, 87, 67.759, 0.115; Germany, 49, 67.653, 0.265; Italy, 27, 71.296, 0.222; Russia, 26, 61.038, 0.308; ... (6 rows)

**QB20.** Per marital status, among artists with a known age: how many artists, and how many lived longer than the average artist?
```sql
SELECT marriage, COUNT(*) AS artists, SUM(CASE WHEN CAST(age AS INTEGER) > (SELECT AVG(CAST(age AS INTEGER)) FROM art WHERE age IS NOT NULL AND age <> '') THEN 1 ELSE 0 END) AS lived_longer_than_average FROM art WHERE marriage IS NOT NULL AND marriage <> '' AND age IS NOT NULL AND age <> '' GROUP BY marriage
```
Correct answer: Cohabiting, 1, 1; Divorced, 7, 4; Married, 181, 124; Remarried, 22, 18; ... (7 rows)

**QB21.** What is the average age reached by artists who taught at an institution?
```sql
SELECT AVG(age) AS average_age FROM art WHERE teaching = 1 AND age IS NOT NULL AND age <> ''
```
Correct answer: 69.471

**QB22.** Among portrait, landscape and still-life artists, how many make bright, dark, neutral or otherwise toned images?
```sql
SELECT CASE WHEN image_genre LIKE '%Portrait%' THEN 'Portrait' WHEN image_genre LIKE '%Landscape%' THEN 'Landscape' ELSE 'Still life' END AS genre_group, CASE WHEN tone LIKE '%Bright%' THEN 'Bright' WHEN tone LIKE '%Dark%' THEN 'Dark' WHEN tone LIKE '%Neutral%' THEN 'Neutral' ELSE 'Other' END AS tone_group, COUNT(*) AS artists FROM art WHERE (image_genre LIKE '%Portrait%' OR image_genre LIKE '%Landscape%' OR image_genre LIKE '%Still Life%') AND tone IS NOT NULL AND tone <> '' GROUP BY genre_group, tone_group
```
Correct answer: Landscape, Bright, 40; Landscape, Dark, 36; Landscape, Neutral, 70; Landscape, Other, 13; ... (12 rows)

**QB23.** Per birth continent (Australia counted with Oceania), how many artists work in an abstract, a realist (not surrealist), an expressionist or an impressionist style?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, COUNT(*) AS artists, SUM(CASE WHEN style LIKE '%Abstract%' THEN 1 ELSE 0 END) AS abstract_style, SUM(CASE WHEN REPLACE(style, 'Surrealis', '') LIKE '%Realis%' THEN 1 ELSE 0 END) AS realist_style, SUM(CASE WHEN style LIKE '%Expressionism%' THEN 1 ELSE 0 END) AS expressionist_style, SUM(CASE WHEN style LIKE '%Impressionism%' THEN 1 ELSE 0 END) AS impressionist_style FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' GROUP BY continent
```
Correct answer: Africa, 19, 2, 1, 4, 2; Asia, 79, 5, 1, 10, 1; Europe, 529, 29, 47, 66, 48; North America, 303, 37, 36, 51, 17; ... (6 rows)

**QB24.** What are the five most common single colors among landscape artists?
```sql
SELECT color, COUNT(*) AS artists FROM art WHERE image_genre LIKE '%Landscape%' AND color IS NOT NULL AND color <> '' AND color NOT LIKE '%||%' GROUP BY color ORDER BY artists DESC, color LIMIT 5
```
Correct answer: Green, 37; Blue, 30; Earth Tones, 29; Sepia, 5; ... (5 rows)

**QB25.** For portrait, landscape, still-life, abstract and other images: how many use earth tones, blue, or black and white?
```sql
SELECT CASE WHEN image_genre LIKE '%Portrait%' THEN 'Portrait' WHEN image_genre LIKE '%Landscape%' THEN 'Landscape' WHEN image_genre LIKE '%Still Life%' THEN 'Still life' WHEN image_genre LIKE '%Abstract%' THEN 'Abstract' ELSE 'Other' END AS genre_group, COUNT(*) AS artists, SUM(CASE WHEN color LIKE '%Earth%' THEN 1 ELSE 0 END) AS earth_tones, SUM(CASE WHEN color LIKE '%Blue%' THEN 1 ELSE 0 END) AS blue, SUM(CASE WHEN color LIKE '%Black And White%' OR color LIKE '%Monochrome%' THEN 1 ELSE 0 END) AS black_and_white FROM art WHERE image_genre IS NOT NULL AND image_genre <> '' GROUP BY genre_group
```
Correct answer: Abstract, 80, 9, 18, 4; Landscape, 159, 47, 48, 3; Other, 322, 81, 45, 32; Portrait, 226, 55, 36, 24; ... (5 rows)

**QB26.** Which ten single art movements have the most artists, and how many of those artists taught?
```sql
SELECT art_movement, COUNT(*) AS artists, SUM(teaching) AS teachers FROM art WHERE art_movement IS NOT NULL AND art_movement <> '' AND art_movement NOT LIKE '%||%' GROUP BY art_movement ORDER BY artists DESC, art_movement LIMIT 10
```
Correct answer: Surrealism, 30, 1; Abstract Expressionism, 28, 4; Realism, 22, 4; Pop Art, 18, 4; ... (10 rows)

**QB27.** How many married, unmarried, remarried, divorced and widowed artists come from each birth continent (Australia counted with Oceania)?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, marriage, COUNT(*) AS artists FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND marriage IN ('Married', 'Unmarried', 'Remarried', 'Divorced', 'Widowed') GROUP BY continent, marriage
```
Correct answer: Africa, Divorced, 2; Africa, Married, 3; Asia, Married, 5; Asia, Remarried, 4; ... (22 rows)

**QB30.** For European-born and North American-born artists, what share of expressionist, realist (not surrealist), abstract and other-style artists taught?
```sql
SELECT birth_continent, CASE WHEN style LIKE '%Expressionism%' THEN 'Expressionist' WHEN REPLACE(style, 'Surrealis', '') LIKE '%Realis%' THEN 'Realist' WHEN style LIKE '%Abstract%' THEN 'Abstract' ELSE 'Other' END AS style_group, COUNT(*) AS artists, AVG(teaching) AS share_who_taught FROM art WHERE birth_continent IN ('Europe', 'North America') AND style IS NOT NULL AND style <> '' GROUP BY birth_continent, style_group
```
Correct answer: Europe, Abstract, 15, 0.467; Europe, Expressionist, 66, 0.152; Europe, Other, 381, 0.168; Europe, Realist, 47, 0.128; ... (8 rows)

**QB32.** In which five countries did the most artists born outside Europe die?
```sql
SELECT death_country, COUNT(*) AS artists FROM art WHERE birth_continent <> 'Europe' AND birth_continent <> '' AND death_country IS NOT NULL AND death_country <> '' GROUP BY death_country ORDER BY artists DESC, death_country LIMIT 5
```
Correct answer: United States, 135; Japan, 13; Australia, 11; Mexico, 9; ... (5 rows)

**QB33.** For portrait, landscape, abstract, figurative, still-life and other genres: how many artists, and how many taught?
```sql
SELECT CASE WHEN genre LIKE '%Portrait%' THEN 'Portrait' WHEN genre LIKE '%Landscape%' THEN 'Landscape' WHEN genre LIKE '%Abstract%' THEN 'Abstract' WHEN genre LIKE '%Figurative%' THEN 'Figurative' WHEN genre LIKE '%Still Life%' THEN 'Still life' ELSE 'Other' END AS genre_group, COUNT(*) AS artists, SUM(teaching) AS teachers FROM art WHERE genre IS NOT NULL AND genre <> '' GROUP BY genre_group
```
Correct answer: Abstract, 125, 36; Figurative, 22, 7; Landscape, 105, 11; Other, 246, 40; ... (6 rows)

**QB34.** How many European-born and North American-born artists were affiliated with an academy, a school or college, or something else?
```sql
SELECT birth_continent, CASE WHEN art_institution LIKE '%Academ%' OR art_institution LIKE '%Akadem%' THEN 'Academy' WHEN art_institution LIKE '%School%' OR art_institution LIKE '%College%' OR art_institution LIKE '%Schule%' THEN 'School or college' ELSE 'Other' END AS institution_group, COUNT(*) AS artists FROM art WHERE birth_continent IN ('Europe', 'North America') AND art_institution IS NOT NULL AND art_institution <> '' GROUP BY birth_continent, institution_group
```
Correct answer: Europe, Academy, 164; Europe, Other, 91; Europe, School or college, 95; North America, Academy, 57; ... (6 rows)

**QB37.** Among single styles with at least 15 artists of known age, which five have the oldest artists on average?
```sql
SELECT style, COUNT(*) AS artists, AVG(age) AS average_age FROM art WHERE style IS NOT NULL AND style <> '' AND style NOT LIKE '%||%' AND age IS NOT NULL AND age <> '' GROUP BY style HAVING COUNT(*) >= 15 ORDER BY average_age DESC, style LIMIT 5
```
Correct answer: Abstract Expressionism, 38, 78.316; Abstract Art, 16, 77.938; Expressionism, 64, 73.047; Surrealism, 34, 72.471; ... (5 rows)

**QB38.** Per birth continent (Australia counted with Oceania): how many artists' images are black and white or monochrome, and how many are multicolored or vibrant?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, COUNT(*) AS artists, SUM(CASE WHEN color LIKE '%Black And White%' OR color LIKE '%Monochrome%' THEN 1 ELSE 0 END) AS black_and_white, SUM(CASE WHEN color LIKE '%Multicolor%' OR color LIKE '%Vibrant%' THEN 1 ELSE 0 END) AS multicolored FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' GROUP BY continent
```
Correct answer: Africa, 19, 0, 3; Asia, 79, 4, 0; Europe, 529, 40, 18; North America, 303, 28, 20; ... (6 rows)

**QB40.** For artists born in the United States (incl. USA, America), France, the United Kingdom (incl. England, Scotland, Britain), Germany, Italy and Japan: how many have a recorded institutional affiliation, and what share taught?
```sql
SELECT CASE WHEN birth_country IN ('United States', 'USA', 'America') THEN 'United States' WHEN birth_country IN ('United Kingdom', 'England', 'Scotland', 'Britain') THEN 'United Kingdom' ELSE birth_country END AS country, COUNT(*) AS artists, SUM(CASE WHEN art_institution IS NOT NULL AND art_institution <> '' THEN 1 ELSE 0 END) AS with_affiliation, AVG(teaching) AS share_who_taught FROM art WHERE birth_country IN ('United States', 'USA', 'America', 'France', 'United Kingdom', 'England', 'Scotland', 'Britain', 'Germany', 'Italy', 'Japan') GROUP BY country
```
Correct answer: France, 94, 51, 0.117; Germany, 66, 53, 0.258; Italy, 39, 18, 0.179; Japan, 25, 13, 0.24; ... (6 rows)

**QB41.** Among artists with a known age, how many Surrealists, Abstract Expressionists, Impressionists, Pop artists, Realists and others (by art movement) were there, and how old did they get on average?
```sql
SELECT CASE WHEN art_movement LIKE '%Abstract Expressionism%' THEN 'Abstract Expressionism' WHEN art_movement LIKE '%Surrealism%' THEN 'Surrealism' WHEN art_movement LIKE '%Impressionism%' THEN 'Impressionism' WHEN art_movement LIKE '%Pop Art%' THEN 'Pop Art' WHEN art_movement LIKE '%Realism%' THEN 'Realism' ELSE 'Other' END AS movement, COUNT(*) AS artists, AVG(age) AS average_age FROM art WHERE art_movement IS NOT NULL AND art_movement <> '' AND age IS NOT NULL AND age <> '' GROUP BY movement
```
Correct answer: Abstract Expressionism, 41, 77.78; Impressionism, 60, 68.767; Other, 400, 67.145; Pop Art, 15, 70.0; ... (6 rows)

**QB42.** Which birth countries outside Europe and North America have at least ten artists, and how many of those artists died in another country?
```sql
SELECT birth_country, COUNT(*) AS artists, SUM(CASE WHEN death_country IS NOT NULL AND death_country <> '' AND death_country <> birth_country THEN 1 ELSE 0 END) AS died_abroad FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND birth_continent NOT IN ('Europe', 'North America') AND birth_country IS NOT NULL AND birth_country <> '' AND birth_country NOT LIKE '%||%' GROUP BY birth_country HAVING COUNT(*) >= 10
```
Correct answer: Australia, 13, 1; Brazil, 13, 0; China, 12, 4; Japan, 25, 3

**QB43.** How many portrait, landscape, still-life and abstract images are in an impressionist, expressionist, realist (not surrealist) or other style?
```sql
SELECT CASE WHEN image_genre LIKE '%Portrait%' THEN 'Portrait' WHEN image_genre LIKE '%Landscape%' THEN 'Landscape' WHEN image_genre LIKE '%Still Life%' THEN 'Still life' ELSE 'Abstract' END AS genre_group, CASE WHEN style LIKE '%Impressionism%' THEN 'Impressionist' WHEN style LIKE '%Expressionism%' THEN 'Expressionist' WHEN REPLACE(style, 'Surrealis', '') LIKE '%Realis%' THEN 'Realist' ELSE 'Other' END AS style_group, COUNT(*) AS artists FROM art WHERE (image_genre LIKE '%Portrait%' OR image_genre LIKE '%Landscape%' OR image_genre LIKE '%Still Life%' OR image_genre LIKE '%Abstract%') AND style IS NOT NULL AND style <> '' GROUP BY genre_group, style_group
```
Correct answer: Abstract, Expressionist, 13; Abstract, Other, 65; Abstract, Realist, 1; Landscape, Expressionist, 20; ... (15 rows)

**QB44.** For impressionist, expressionist, realist (not surrealist), abstract and other styles: how many artists, and how many of their images are in earth tones, in blue, or in black and white?
```sql
SELECT CASE WHEN style LIKE '%Impressionism%' THEN 'Impressionist' WHEN style LIKE '%Expressionism%' THEN 'Expressionist' WHEN REPLACE(style, 'Surrealis', '') LIKE '%Realis%' THEN 'Realist' WHEN style LIKE '%Abstract%' THEN 'Abstract' ELSE 'Other' END AS style_group, COUNT(*) AS artists, SUM(CASE WHEN color LIKE '%Earth%' THEN 1 ELSE 0 END) AS earth_tones, SUM(CASE WHEN color LIKE '%Blue%' THEN 1 ELSE 0 END) AS blue, SUM(CASE WHEN color LIKE '%Black And White%' OR color LIKE '%Monochrome%' THEN 1 ELSE 0 END) AS black_and_white FROM art WHERE style IS NOT NULL AND style <> '' AND color IS NOT NULL AND color <> '' GROUP BY style_group
```
Correct answer: Abstract, 28, 5, 6, 0; Expressionist, 135, 26, 36, 6; Impressionist, 71, 26, 13, 0; Other, 595, 114, 101, 50; ... (5 rows)

**QB45.** Per birth continent (Australia counted with Oceania), among artists with a recorded genre: how many artists, and how many work in abstract, landscape and portrait genres?
```sql
SELECT CASE WHEN birth_continent = 'Australia' THEN 'Oceania' ELSE birth_continent END AS continent, COUNT(*) AS artists, SUM(CASE WHEN genre LIKE '%Abstract%' THEN 1 ELSE 0 END) AS abstract_genre, SUM(CASE WHEN genre LIKE '%Landscape%' THEN 1 ELSE 0 END) AS landscape_genre, SUM(CASE WHEN genre LIKE '%Portrait%' THEN 1 ELSE 0 END) AS portrait_genre FROM art WHERE birth_continent IS NOT NULL AND birth_continent <> '' AND genre IS NOT NULL AND genre <> '' GROUP BY continent
```
Correct answer: Africa, 9, 3, 3, 3; Asia, 51, 8, 15, 8; Europe, 378, 59, 107, 108; North America, 203, 63, 41, 45; ... (6 rows)

**QB46.** Which single art movements with at least ten artists of known age have artists who lived longer on average than all artists with a known age?
```sql
SELECT art_movement, COUNT(*) AS artists, AVG(CAST(age AS INTEGER)) AS average_age FROM art WHERE art_movement IS NOT NULL AND art_movement <> '' AND art_movement NOT LIKE '%||%' AND age IS NOT NULL AND age <> '' GROUP BY art_movement HAVING COUNT(*) >= 10 AND AVG(CAST(age AS INTEGER)) > (SELECT AVG(CAST(age AS INTEGER)) FROM art WHERE age IS NOT NULL AND age <> '')
```
Correct answer: Abstract Expressionism, 24, 74.25; Impressionism, 14, 71.429; Realism, 19, 69.526; Surrealism, 27, 72.222

**QB47.** For artists born in France, Germany, Italy, the United Kingdom (incl. England, Scotland, Britain) and the United States (incl. USA, America): how many belong to Surrealism, Abstract Expressionism, Impressionism, Pop Art, Realism or another art movement?
```sql
SELECT CASE WHEN birth_country IN ('United States', 'USA', 'America') THEN 'United States' WHEN birth_country IN ('United Kingdom', 'England', 'Scotland', 'Britain') THEN 'United Kingdom' ELSE birth_country END AS country, CASE WHEN art_movement LIKE '%Abstract Expressionism%' THEN 'Abstract Expressionism' WHEN art_movement LIKE '%Surrealism%' THEN 'Surrealism' WHEN art_movement LIKE '%Impressionism%' THEN 'Impressionism' WHEN art_movement LIKE '%Pop Art%' THEN 'Pop Art' WHEN art_movement LIKE '%Realism%' THEN 'Realism' ELSE 'Other' END AS movement, COUNT(*) AS artists FROM art WHERE birth_country IN ('United States', 'USA', 'America', 'France', 'United Kingdom', 'England', 'Scotland', 'Britain', 'Germany', 'Italy') AND art_movement IS NOT NULL AND art_movement <> '' GROUP BY country, movement
```
Correct answer: France, Abstract Expressionism, 1; France, Impressionism, 15; France, Other, 45; France, Pop Art, 1; ... (26 rows)

**QB48.** For Surrealists, Abstract Expressionists, Impressionists, Pop artists, Realists and others (by art movement): how many artists, and how many make bright images and how many dark ones?
```sql
SELECT CASE WHEN art_movement LIKE '%Abstract Expressionism%' THEN 'Abstract Expressionism' WHEN art_movement LIKE '%Surrealism%' THEN 'Surrealism' WHEN art_movement LIKE '%Impressionism%' THEN 'Impressionism' WHEN art_movement LIKE '%Pop Art%' THEN 'Pop Art' WHEN art_movement LIKE '%Realism%' THEN 'Realism' ELSE 'Other' END AS movement, COUNT(*) AS artists, SUM(CASE WHEN tone LIKE '%Bright%' THEN 1 ELSE 0 END) AS bright_tone, SUM(CASE WHEN tone LIKE '%Dark%' THEN 1 ELSE 0 END) AS dark_tone FROM art WHERE art_movement IS NOT NULL AND art_movement <> '' AND tone IS NOT NULL AND tone <> '' GROUP BY movement
```
Correct answer: Abstract Expressionism, 52, 17, 10; Impressionism, 62, 26, 5; Other, 510, 109, 102; Pop Art, 26, 10, 3; ... (6 rows)

## Court judgments (legal): test questions (28)

**Q1.** How are the cases of each type decided?
```sql
SELECT case_type, verdict, COUNT(*) AS cases FROM legal GROUP BY case_type, verdict
```
Correct answer: Administrative Case, Approved, 49; Administrative Case, Dismissed, 280; Administrative Case, Not Guilty, 1; Administrative Case, Others, 14; ... (16 rows)

**Q5.** For defendant types with at least five cases: how many cases, and how many were approved?
```sql
SELECT defendant_current_status, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved FROM legal WHERE defendant_current_status <> '' GROUP BY defendant_current_status HAVING COUNT(*) >= 5
```
Correct answer: Company, 129, 38; Employee, 5, 2; Government, 295, 32; Organization, 48, 8

**Q8.** When a company, an organization or a government is the plaintiff, how are cases decided?
```sql
SELECT plaintiff_current_status, verdict, COUNT(*) AS cases FROM legal WHERE plaintiff_current_status IN ('Company', 'Organization', 'Government') GROUP BY plaintiff_current_status, verdict
```
Correct answer: Company, Approved, 29; Company, Dismissed, 55; Company, Others, 31; Government, Approved, 9; ... (11 rows)

**Q10.** Which judges with at least five cases dismissed more than 70% of them?
```sql
SELECT judge_name, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal GROUP BY judge_name HAVING COUNT(*) >= 5 AND AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) > 0.7
```
Correct answer: Barker, 7, 0.857; Besanko, 15, 0.733; Branson, 7, 0.857; Buchanan, 14, 0.857; ... (17 rows)

**Q12.** Per case type, how many cases cite more statutes than the average case?
```sql
SELECT case_type, COUNT(*) AS cases FROM legal WHERE legal_basis_num > (SELECT AVG(legal_basis_num) FROM legal) GROUP BY case_type
```
Correct answer: Administrative Case, 92; Civil Case, 64; Commercial Case, 17; Criminal Case, 4; ... (5 rows)

**QX1.** For judges with at least fifteen cases: how many cases, how many were first judgments, and how many had evidence, busiest first?
```sql
SELECT judge_name, COUNT(*) AS cases, SUM(CASE WHEN first_judge = 1 THEN 1 ELSE 0 END) AS first_judgments, SUM(evidence) AS with_evidence FROM legal WHERE judge_name IS NOT NULL AND judge_name <> '' GROUP BY judge_name HAVING COUNT(*) >= 15 ORDER BY cases DESC, judge_name
```
Correct answer: Flick, 29, 15, 23; Tracey, 29, 13, 22; Greenwood, 25, 15, 19; Heerey, 17, 8, 11; ... (11 rows)

**QX2.** Per case type, for applicants represented by named counsel versus applicants with no counsel named or representing themselves: how many cases, and what share were dismissed?
```sql
SELECT case_type, CASE WHEN counsel_for_applicant IS NULL OR counsel_for_applicant = '' OR counsel_for_applicant LIKE '%in person%' OR counsel_for_applicant LIKE '%self%represent%' THEN 'no counsel named' ELSE 'counsel named' END AS applicant_counsel, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal GROUP BY case_type, applicant_counsel
```
Correct answer: Administrative Case, counsel named, 141, 0.652; Administrative Case, no counsel named, 203, 0.926; Civil Case, counsel named, 114, 0.456; Civil Case, no counsel named, 42, 0.786; ... (8 rows)

**QX3.** Do applicants with senior counsel (SC or QC) win more often than applicants with other named counsel?
```sql
SELECT CASE WHEN counsel_for_applicant GLOB '* SC*' OR counsel_for_applicant GLOB '* QC*' THEN 'senior counsel' ELSE 'other counsel' END AS applicant_counsel, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved, AVG(CASE WHEN verdict = 'Approved' THEN 1.0 ELSE 0.0 END) AS approval_rate FROM legal WHERE counsel_for_applicant IS NOT NULL AND counsel_for_applicant <> '' AND counsel_for_applicant NOT LIKE '%in person%' AND counsel_for_applicant NOT LIKE '%self%represent%' GROUP BY applicant_counsel
```
Correct answer: other counsel, 206, 50, 0.243; senior counsel, 109, 30, 0.275

**QX4.** When a company, an organization or a government is the plaintiff, what kinds of defendant (company, organization, government) do they sue, and how many cases each?
```sql
SELECT plaintiff_current_status, defendant_current_status, COUNT(*) AS cases FROM legal WHERE plaintiff_current_status IN ('Company', 'Organization', 'Government') AND defendant_current_status IN ('Company', 'Organization', 'Government') GROUP BY plaintiff_current_status, defendant_current_status
```
Correct answer: Company, Company, 63; Company, Government, 19; Company, Organization, 10; Government, Company, 6; ... (7 rows)

**QX5.** Per judgment year: in how many cases was a fine imposed, and what were the total and the largest fine?
```sql
SELECT judgment_year, COUNT(*) AS fined_cases, SUM(CAST(fine_amount AS REAL)) AS total_fines, MAX(CAST(fine_amount AS REAL)) AS largest_fine FROM legal WHERE CAST(fine_amount AS REAL) > 0 AND judgment_year IS NOT NULL AND judgment_year <> '' GROUP BY judgment_year
```
Correct answer: 2006, 10, 16565226.1, 9953426.1; 2007, 6, 3535524.0, 2137000.0; 2008, 10, 285311.72, 70000.0; 2009, 13, 8822079.79, 6500000.0

**QX6.** Grouping cases by what their charges mention (refugee, visa or migration; misleading or deceptive conduct; tax; patent, copyright or trade mark; bankruptcy or insolvency; anything else): how many cases, and how many statutes and precedents are cited on average?
```sql
SELECT CASE WHEN charges LIKE '%refugee%' OR charges LIKE '%visa%' OR charges LIKE '%migration%' THEN 'migration' WHEN charges LIKE '%misleading%' OR charges LIKE '%deceptive%' THEN 'misleading conduct' WHEN charges LIKE '%tax%' THEN 'tax' WHEN charges LIKE '%patent%' OR charges LIKE '%copyright%' OR charges LIKE '%trade mark%' OR charges LIKE '%trademark%' THEN 'intellectual property' WHEN charges LIKE '%bankrupt%' OR charges LIKE '%insolven%' THEN 'insolvency' ELSE 'other' END AS area, COUNT(*) AS cases, AVG(legal_basis_num) AS average_statutes, AVG(NULLIF(case_number, '')) AS average_precedents FROM legal WHERE charges IS NOT NULL AND charges <> '' GROUP BY area
```
Correct answer: insolvency, 26, 2.462, 6.68; intellectual property, 32, 2.688, 10.0; migration, 113, 1.513, 5.018; misleading conduct, 34, 2.353, 7.441; ... (6 rows)

**QX7.** For government, company and organization defendants: how many cases, how many statutes and precedents are cited on average, and what share had evidence?
```sql
SELECT defendant_current_status, COUNT(*) AS cases, AVG(legal_basis_num) AS average_statutes, AVG(NULLIF(case_number, '')) AS average_precedents, AVG(CASE WHEN evidence = 1 THEN 1.0 ELSE 0.0 END) AS evidence_rate FROM legal WHERE defendant_current_status IN ('Government', 'Company', 'Organization') GROUP BY defendant_current_status
```
Correct answer: Company, 129, 2.279, 8.938, 0.876; Government, 295, 1.847, 5.532, 0.725; Organization, 48, 3.25, 7.688, 0.812

**QX8.** Which five judges heard the most cases against an immigration minister, and how many of those did they dismiss?
```sql
SELECT judge_name, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed FROM legal WHERE defendant LIKE '%Immigration%' AND judge_name IS NOT NULL AND judge_name <> '' GROUP BY judge_name ORDER BY cases DESC, judge_name LIMIT 5
```
Correct answer: Flick, 23, 22; Tracey, 17, 15; Middleton, 13, 13; Greenwood, 11, 11; ... (5 rows)

**QX9.** Per judgment year: how many judgments were delivered in the year the hearing began, and how many in a later year?
```sql
SELECT judgment_year, SUM(CASE WHEN CAST(judgment_year AS INTEGER) = CAST(hearing_year AS INTEGER) THEN 1 ELSE 0 END) AS same_year, SUM(CASE WHEN CAST(judgment_year AS INTEGER) > CAST(hearing_year AS INTEGER) THEN 1 ELSE 0 END) AS later_year FROM legal WHERE judgment_year IS NOT NULL AND judgment_year <> '' AND hearing_year IS NOT NULL AND hearing_year <> '' GROUP BY judgment_year
```
Correct answer: 2006, 156, 15; 2007, 131, 16; 2008, 116, 19; 2009, 93, 15

**QX10.** Which judges with at least ten cases cite more precedents on average than the average case?
```sql
SELECT judge_name, COUNT(*) AS cases, AVG(NULLIF(case_number, '')) AS average_precedents FROM legal WHERE judge_name IS NOT NULL AND judge_name <> '' GROUP BY judge_name HAVING COUNT(*) >= 10 AND AVG(NULLIF(case_number, '')) > (SELECT AVG(NULLIF(case_number, '')) FROM legal) ORDER BY average_precedents DESC, judge_name
```
Correct answer: Gordon, 11, 14.727; Flick, 29, 13.966; Gilmour, 12, 12.583; Cowdroy, 12, 10.0; ... (13 rows)

**QX11.** For cases brought by the competition regulator (ACCC) and the securities regulator (ASIC): how many cases, how many approved, in how many was a fine imposed, and how much in fines in total?
```sql
SELECT CASE WHEN plaintiff LIKE '%Competition and Consumer Commission%' THEN 'ACCC' ELSE 'ASIC' END AS regulator, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved, SUM(CASE WHEN CAST(fine_amount AS REAL) > 0 THEN 1 ELSE 0 END) AS fined_cases, SUM(CASE WHEN CAST(fine_amount AS REAL) > 0 THEN CAST(fine_amount AS REAL) ELSE 0 END) AS total_fines FROM legal WHERE plaintiff LIKE '%Competition and Consumer Commission%' OR plaintiff LIKE '%Securities and Investments Commission%' GROUP BY regulator
```
Correct answer: ACCC, 15, 5, 9, 1733000.0; ASIC, 6, 2, 0, 0

**QX12.** For government, company and organization defendants with named counsel: how many cases, in how many did the respondent brief senior counsel (SC or QC), and what share were dismissed?
```sql
SELECT defendant_current_status, COUNT(*) AS cases, SUM(CASE WHEN counsel_for_respondent GLOB '* SC*' OR counsel_for_respondent GLOB '* QC*' THEN 1 ELSE 0 END) AS with_senior_counsel, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal WHERE defendant_current_status IN ('Government', 'Company', 'Organization') AND counsel_for_respondent IS NOT NULL AND counsel_for_respondent <> '' GROUP BY defendant_current_status
```
Correct answer: Company, 110, 44, 0.445; Government, 238, 25, 0.836; Organization, 45, 11, 0.6

**QX13.** By kind of plaintiff (company, organization, government, other): how many cases, how many approved, and what share approved?
```sql
SELECT CASE WHEN plaintiff_current_status IN ('Company', 'Organization', 'Government') THEN plaintiff_current_status ELSE 'other' END AS plaintiff_kind, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved, AVG(CASE WHEN verdict = 'Approved' THEN 1.0 ELSE 0.0 END) AS approval_rate FROM legal WHERE plaintiff_current_status IS NOT NULL AND plaintiff_current_status <> '' GROUP BY plaintiff_kind
```
Correct answer: Company, 115, 29, 0.252; Government, 19, 9, 0.474; Organization, 32, 10, 0.312; other, 148, 23, 0.155

**QX14.** By which sides had named counsel (both sides, respondent only, applicant only, neither): how many cases, and what share were dismissed?
```sql
SELECT CASE WHEN NOT (counsel_for_applicant IS NULL OR counsel_for_applicant = '' OR counsel_for_applicant LIKE '%in person%' OR counsel_for_applicant LIKE '%self%represent%') AND NOT (counsel_for_respondent IS NULL OR counsel_for_respondent = '' OR counsel_for_respondent LIKE '%in person%' OR counsel_for_respondent LIKE '%self%represent%') THEN 'both sides' WHEN NOT (counsel_for_respondent IS NULL OR counsel_for_respondent = '' OR counsel_for_respondent LIKE '%in person%' OR counsel_for_respondent LIKE '%self%represent%') THEN 'respondent only' WHEN NOT (counsel_for_applicant IS NULL OR counsel_for_applicant = '' OR counsel_for_applicant LIKE '%in person%' OR counsel_for_applicant LIKE '%self%represent%') THEN 'applicant only' ELSE 'neither' END AS represented, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal GROUP BY represented
```
Correct answer: applicant only, 33, 0.364; both sides, 282, 0.528; neither, 71, 0.873; respondent only, 184, 0.875

**QF1.** For judges with at least ten cases: how many cases, how many dismissed, and how many statutes cited on average, busiest first?
```sql
SELECT judge_name, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed, AVG(legal_basis_num) AS average_statutes FROM legal WHERE judge_name IS NOT NULL AND judge_name <> '' GROUP BY judge_name HAVING COUNT(*) >= 10 ORDER BY cases DESC, judge_name
```
Correct answer: Flick, 29, 25, 1.931; Tracey, 29, 20, 1.897; Greenwood, 25, 16, 2.72; Heerey, 17, 8, 1.647; ... (31 rows)

**QF2.** Per judgment year: how many cases, what share dismissed, and how many precedents cited on average?
```sql
SELECT judgment_year, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate, AVG(NULLIF(case_number, '')) AS average_precedents FROM legal WHERE judgment_year IS NOT NULL AND judgment_year <> '' GROUP BY judgment_year
```
Correct answer: 2006, 172, 0.68, 5.82; 2007, 151, 0.715, 6.53; 2008, 136, 0.676, 8.699; 2009, 109, 0.615, 7.972

**QF3.** Per case type: average statutes, average precedents, and how many cases had evidence?
```sql
SELECT case_type, AVG(legal_basis_num) AS average_statutes, AVG(NULLIF(case_number, '')) AS average_precedents, SUM(evidence) AS with_evidence FROM legal GROUP BY case_type
```
Correct answer: Administrative Case, 1.994, 5.799, 251; Civil Case, 2.853, 8.538, 132; Commercial Case, 2.085, 11.0, 52; Criminal Case, 2.9, 5.6, 9; ... (5 rows)

**QF4.** Which ten applicant nationalities bring the most cases, and how many of their cases are dismissed?
```sql
SELECT nationality_for_applicant, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed FROM legal WHERE nationality_for_applicant IS NOT NULL AND nationality_for_applicant <> '' GROUP BY nationality_for_applicant ORDER BY cases DESC, nationality_for_applicant LIMIT 10
```
Correct answer: Australia, 83, 35; China, 63, 54; India, 48, 43; Bangladesh, 26, 24; ... (10 rows)

**QF5.** Per verdict: how many statutes and precedents are cited on average?
```sql
SELECT verdict, AVG(legal_basis_num) AS average_statutes, AVG(NULLIF(case_number, '')) AS average_precedents FROM legal GROUP BY verdict
```
Correct answer: Approved, 2.086, 7.615; Dismissed, 2.193, 6.542; Guilty, 2.429, 6.571; Not Guilty, 5.0, 6.0; ... (5 rows)

**QF6.** How many cases of each type were decided each year?
```sql
SELECT judgment_year, case_type, COUNT(*) AS cases FROM legal WHERE judgment_year IS NOT NULL AND judgment_year <> '' GROUP BY judgment_year, case_type
```
Correct answer: 2006, Administrative Case, 113; 2006, Civil Case, 37; 2006, Commercial Case, 20; 2006, Criminal Case, 2; ... (17 rows)

**QF7.** For defendant types fined at least twice, how many fines were there and how large is the average fine?
```sql
SELECT defendant_current_status, COUNT(*) AS fined_cases, AVG(CAST(fine_amount AS REAL)) AS average_fine FROM legal WHERE CAST(fine_amount AS REAL) > 0 AND defendant_current_status IS NOT NULL AND defendant_current_status <> '' GROUP BY defendant_current_status HAVING COUNT(*) >= 2
```
Correct answer: Company, 17, 1017413.045; Employee, 2, 537150.0; Government, 3, 7917.0; Organization, 10, 1036382.61

**QF8.** For patent, copyright and trade mark cases: how many cases, how many dismissed and how many approved?
```sql
SELECT CASE WHEN charges LIKE '%patent%' THEN 'patent' WHEN charges LIKE '%copyright%' THEN 'copyright' ELSE 'trade mark' END AS area, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved FROM legal WHERE charges LIKE '%patent%' OR charges LIKE '%copyright%' OR charges LIKE '%trade mark%' OR charges LIKE '%trademark%' GROUP BY area
```
Correct answer: copyright, 12, 3, 3; patent, 11, 2, 2; trade mark, 11, 3, 4

**QF9.** How many cases involve a patent?
```sql
SELECT COUNT(*) AS cases FROM legal WHERE charges LIKE '%patent%'
```
Correct answer: 11

## Court judgments (legal): build questions (30)

**QB1.** Per hearing year: how many cases were heard, how many of them were first judgments, and how many statutes were cited on average?
```sql
SELECT hearing_year, COUNT(*) AS cases, SUM(CASE WHEN first_judge = 1 THEN 1 ELSE 0 END) AS first_judgments, AVG(legal_basis_num) AS average_statutes FROM legal WHERE hearing_year IS NOT NULL AND hearing_year <> '' GROUP BY hearing_year
```
Correct answer: 2005, 17, 5, 2.647; 2006, 171, 78, 1.912; 2007, 150, 71, 2.34; 2008, 131, 66, 2.435; ... (7 rows)

**QB2.** For each case type: how many cases, what share had evidence, and what share were dismissed?
```sql
SELECT case_type, COUNT(*) AS cases, AVG(CASE WHEN evidence = 1 THEN 1.0 ELSE 0.0 END) AS evidence_rate, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal GROUP BY case_type
```
Correct answer: Administrative Case, 344, 0.73, 0.814; Civil Case, 156, 0.846, 0.545; Commercial Case, 59, 0.881, 0.271; Criminal Case, 10, 0.9, 0.3; ... (5 rows)

**QB3.** How are cases decided when evidence was provided, compared with when it was not?
```sql
SELECT evidence, verdict, COUNT(*) AS cases FROM legal GROUP BY evidence, verdict
```
Correct answer: 0, Approved, 15; 0, Dismissed, 102; 0, Others, 9; 1, Approved, 90; ... (8 rows)

**QB4.** How are first judgments decided, compared with later judgments in the same matter?
```sql
SELECT first_judge, verdict, COUNT(*) AS cases FROM legal GROUP BY first_judge, verdict
```
Correct answer: 0, Approved, 51; 0, Dismissed, 216; 0, Guilty, 3; 0, Others, 33; ... (9 rows)

**QB5.** Among applicant nationalities with at least five cases, which have the highest dismissal rate?
```sql
SELECT nationality_for_applicant, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal WHERE nationality_for_applicant IS NOT NULL AND nationality_for_applicant <> '' GROUP BY nationality_for_applicant HAVING COUNT(*) >= 5 ORDER BY dismissal_rate DESC, nationality_for_applicant
```
Correct answer: Bangladesh, 26, 0.923; Sri Lanka, 11, 0.909; Fiji, 10, 0.9; India, 48, 0.896; ... (7 rows)

**QB6.** For applicants from Australia, China, India and Bangladesh, how many cases of each type are there?
```sql
SELECT nationality_for_applicant, case_type, COUNT(*) AS cases FROM legal WHERE nationality_for_applicant IN ('Australia', 'China', 'India', 'Bangladesh') GROUP BY nationality_for_applicant, case_type
```
Correct answer: Australia, Administrative Case, 30; Australia, Civil Case, 35; Australia, Commercial Case, 16; Australia, Criminal Case, 2; ... (9 rows)

**QB7.** By kind of defendant (immigration minister, tax commissioner, company, other public body, other): how many cases, and how many were approved?
```sql
SELECT CASE WHEN defendant LIKE '%Immigration%' THEN 'immigration minister' WHEN defendant LIKE '%Taxation%' THEN 'tax commissioner' WHEN defendant LIKE '%Pty Ltd%' OR defendant LIKE '%Limited%' OR defendant LIKE '% Ltd%' THEN 'company' WHEN defendant LIKE '%Commission%' OR defendant LIKE '%Tribunal%' OR defendant LIKE '%Authority%' OR defendant LIKE '%Department%' OR defendant LIKE '%State of%' OR defendant LIKE '%Commonwealth%' THEN 'other public body' ELSE 'other' END AS defendant_kind, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved FROM legal WHERE defendant IS NOT NULL AND defendant <> '' GROUP BY defendant_kind
```
Correct answer: company, 126, 32; immigration minister, 237, 23; other, 135, 39; other public body, 49, 8; ... (5 rows)

**QB8.** For cases against an immigration minister, per hearing year: how many cases and how many were dismissed?
```sql
SELECT hearing_year, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed FROM legal WHERE defendant LIKE '%Immigration%' AND hearing_year IS NOT NULL AND hearing_year <> '' GROUP BY hearing_year
```
Correct answer: 2005, 3, 3; 2006, 78, 74; 2007, 71, 60; 2008, 51, 44; ... (6 rows)

**QB9.** For the tax commissioner (Commissioner or Deputy Commissioner of Taxation), the Repatriation Commission and the Refugee Review Tribunal as defendant: how many cases, how many dismissed, and how many statutes cited on average?
```sql
SELECT CASE WHEN defendant LIKE '%Commissioner of Taxation%' THEN 'Commissioner of Taxation' WHEN defendant LIKE '%Repatriation Commission%' THEN 'Repatriation Commission' ELSE 'Refugee Review Tribunal' END AS defendant_body, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed, AVG(legal_basis_num) AS average_statutes FROM legal WHERE defendant LIKE '%Commissioner of Taxation%' OR defendant LIKE '%Repatriation Commission%' OR defendant LIKE 'Refugee Review Tribunal%' GROUP BY defendant_body
```
Correct answer: Commissioner of Taxation, 18, 17, 3.5; Refugee Review Tribunal, 4, 4, 0.75; Repatriation Commission, 7, 5, 2.0

**QB10.** Per case type: the average and the largest number of precedents cited, and how many cases cite no precedent at all?
```sql
SELECT case_type, AVG(case_number) AS average_precedents, MAX(CAST(case_number AS INTEGER)) AS most_precedents, SUM(CASE WHEN CAST(case_number AS INTEGER) = 0 THEN 1 ELSE 0 END) AS without_precedents FROM legal WHERE case_number IS NOT NULL AND case_number <> '' GROUP BY case_type
```
Correct answer: Administrative Case, 5.799, 48, 41; Civil Case, 8.538, 93, 19; Commercial Case, 11.0, 48, 4; Criminal Case, 5.6, 21, 2; ... (5 rows)

**QB11.** By number of statutes cited (none, one, two or three, four or more): how many cases, and what share were dismissed?
```sql
SELECT CASE WHEN CAST(legal_basis_num AS INTEGER) = 0 THEN 'none' WHEN CAST(legal_basis_num AS INTEGER) = 1 THEN 'one' WHEN CAST(legal_basis_num AS INTEGER) <= 3 THEN 'two or three' ELSE 'four or more' END AS statutes_cited, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal WHERE legal_basis_num IS NOT NULL AND legal_basis_num <> '' GROUP BY statutes_cited
```
Correct answer: four or more, 96, 0.646; none, 43, 0.791; one, 204, 0.706; two or three, 227, 0.634

**QB12.** By number of precedents cited (none, 1 to 5, 6 to 15, more than 15): how many cases, how many had evidence, and how many statutes were cited on average?
```sql
SELECT CASE WHEN CAST(case_number AS INTEGER) = 0 THEN 'none' WHEN CAST(case_number AS INTEGER) <= 5 THEN '1 to 5' WHEN CAST(case_number AS INTEGER) <= 15 THEN '6 to 15' ELSE 'more than 15' END AS precedents_cited, COUNT(*) AS cases, SUM(evidence) AS with_evidence, AVG(legal_basis_num) AS average_statutes FROM legal WHERE case_number IS NOT NULL AND case_number <> '' GROUP BY precedents_cited
```
Correct answer: 1 to 5, 260, 193, 1.788; 6 to 15, 178, 145, 2.747; more than 15, 65, 57, 3.754; none, 66, 48, 1.318

**QB13.** Per case type: in how many cases were legal fees awarded, and what were the total and the average amount?
```sql
SELECT case_type, COUNT(*) AS cases_with_fees, SUM(CAST(legal_fees AS REAL)) AS total_fees, AVG(CAST(legal_fees AS REAL)) AS average_fees FROM legal WHERE legal_fees <> '' AND legal_fees NOT GLOB '*[^0-9.]*' GROUP BY case_type
```
Correct answer: Administrative Case, 52, 331953.0, 6383.712; Civil Case, 9, 431137.0, 47904.111; Commercial Case, 5, 323741.34, 64748.268; Criminal Case, 1, 40000.0, 40000.0

**QB14.** Per verdict: in how many cases were legal fees awarded, and what were the largest and the average amount?
```sql
SELECT verdict, COUNT(*) AS cases_with_fees, MAX(CAST(legal_fees AS REAL)) AS largest_fees, AVG(CAST(legal_fees AS REAL)) AS average_fees FROM legal WHERE legal_fees <> '' AND legal_fees NOT GLOB '*[^0-9.]*' GROUP BY verdict
```
Correct answer: Approved, 8, 10000.0, 5102.589; Dismissed, 52, 185000.0, 9709.346; Others, 7, 200000.0, 83017.804

**QB15.** Per hearing year: in how many cases were legal fees awarded, and how much in total?
```sql
SELECT hearing_year, COUNT(*) AS cases_with_fees, SUM(CAST(legal_fees AS REAL)) AS total_fees FROM legal WHERE legal_fees <> '' AND legal_fees NOT GLOB '*[^0-9.]*' AND hearing_year IS NOT NULL AND hearing_year <> '' GROUP BY hearing_year
```
Correct answer: 2006, 22, 139049.4; 2007, 18, 362220.63; 2008, 17, 332885.0; 2009, 10, 292676.31

**QB16.** Which case type and verdict combinations with at least five cases cite the most statutes on average?
```sql
SELECT case_type, verdict, COUNT(*) AS cases, AVG(legal_basis_num) AS average_statutes FROM legal GROUP BY case_type, verdict HAVING COUNT(*) >= 5 ORDER BY average_statutes DESC, case_type, verdict
```
Correct answer: Administrative Case, Others, 14, 3.857; Civil Case, Dismissed, 85, 3.424; Civil Case, Others, 33, 2.667; Commercial Case, Others, 23, 2.391; ... (9 rows)

**QB17.** Per hearing year and case type, how many cases were decided without evidence?
```sql
SELECT hearing_year, case_type, COUNT(*) AS cases_without_evidence FROM legal WHERE evidence = 0 AND hearing_year IS NOT NULL AND hearing_year <> '' GROUP BY hearing_year, case_type
```
Correct answer: 2005, Administrative Case, 1; 2005, Civil Case, 2; 2006, Administrative Case, 37; 2006, Civil Case, 6; ... (15 rows)

**QB18.** Per hearing year, how many cases cite more precedents than the average case?
```sql
SELECT hearing_year, COUNT(*) AS cases FROM legal WHERE case_number IS NOT NULL AND case_number <> '' AND CAST(case_number AS INTEGER) > (SELECT AVG(CAST(case_number AS INTEGER)) FROM legal WHERE case_number IS NOT NULL AND case_number <> '') AND hearing_year IS NOT NULL AND hearing_year <> '' GROUP BY hearing_year
```
Correct answer: 2005, 5; 2006, 46; 2007, 46; 2008, 49; ... (5 rows)

**QB19.** For applicant nationalities with at least eight cases: how many cases, and how many statutes and precedents are cited on average?
```sql
SELECT nationality_for_applicant, COUNT(*) AS cases, AVG(legal_basis_num) AS average_statutes, AVG(NULLIF(case_number, '')) AS average_precedents FROM legal WHERE nationality_for_applicant IS NOT NULL AND nationality_for_applicant <> '' GROUP BY nationality_for_applicant HAVING COUNT(*) >= 8 ORDER BY cases DESC, nationality_for_applicant
```
Correct answer: Australia, 83, 2.892, 8.524; China, 63, 1.54, 6.254; India, 48, 1.354, 6.104; Bangladesh, 26, 1.308, 4.615; ... (7 rows)

**QB20.** Do Australian applicants fare differently from foreign applicants: how many cases, what share dismissed, and what share with evidence?
```sql
SELECT CASE WHEN nationality_for_applicant = 'Australia' THEN 'Australian' ELSE 'foreign' END AS applicant_origin, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate, AVG(CASE WHEN evidence = 1 THEN 1.0 ELSE 0.0 END) AS evidence_rate FROM legal WHERE nationality_for_applicant IS NOT NULL AND nationality_for_applicant <> '' GROUP BY applicant_origin
```
Correct answer: Australian, 83, 0.422, 0.88; foreign, 220, 0.864, 0.741

**QB21.** In cases against an immigration minister, for applicant nationalities with at least five such cases: how many cases, how many dismissed and how many approved?
```sql
SELECT nationality_for_applicant, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved FROM legal WHERE defendant LIKE '%Immigration%' AND nationality_for_applicant IS NOT NULL AND nationality_for_applicant <> '' GROUP BY nationality_for_applicant HAVING COUNT(*) >= 5
```
Correct answer: Bangladesh, 24, 22, 2; China, 59, 52, 6; Fiji, 10, 9, 1; India, 47, 43, 4; ... (6 rows)

**QB22.** Which case types are dismissed more often than cases overall?
```sql
SELECT case_type, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal GROUP BY case_type HAVING AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) > (SELECT AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) FROM legal)
```
Correct answer: Administrative Case, 344, 0.814

**QB23.** Per case type, for first judgments and for later judgments: how many cases, and how many precedents are cited on average?
```sql
SELECT case_type, first_judge, COUNT(*) AS cases, AVG(NULLIF(case_number, '')) AS average_precedents FROM legal GROUP BY case_type, first_judge
```
Correct answer: Administrative Case, 0, 190, 6.45; Administrative Case, 1, 154, 5.0; Civil Case, 0, 78, 9.974; Civil Case, 1, 78, 7.103; ... (9 rows)

**QB24.** Among hearing years with at least ten cases, in which were more than 60% of the cases dismissed?
```sql
SELECT hearing_year, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal WHERE hearing_year IS NOT NULL AND hearing_year <> '' GROUP BY hearing_year HAVING COUNT(*) >= 10 AND AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) > 0.6
```
Correct answer: 2006, 171, 0.69; 2007, 150, 0.707; 2008, 131, 0.679; 2009, 94, 0.617

**QB25.** Per verdict: how many cases, and what is the largest number of statutes and of precedents cited in one case?
```sql
SELECT verdict, COUNT(*) AS cases, MAX(CAST(legal_basis_num AS INTEGER)) AS most_statutes, MAX(CAST(case_number AS INTEGER)) AS most_precedents FROM legal WHERE case_number IS NOT NULL AND case_number <> '' GROUP BY verdict
```
Correct answer: Approved, 104, 16, 54; Dismissed, 384, 24, 93; Guilty, 7, 4, 21; Not Guilty, 1, 5, 6; ... (5 rows)

**QB26.** In which three hearing years were the most cases approved, and how many cases were heard in those years?
```sql
SELECT hearing_year, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved, COUNT(*) AS cases FROM legal WHERE hearing_year IS NOT NULL AND hearing_year <> '' GROUP BY hearing_year ORDER BY approved DESC, hearing_year LIMIT 3
```
Correct answer: 2007, 29, 150; 2006, 28, 171; 2008, 25, 131

**QB27.** How many cases of each type are brought against an immigration minister, a company, or another defendant?
```sql
SELECT CASE WHEN defendant LIKE '%Immigration%' THEN 'immigration minister' WHEN defendant LIKE '%Pty Ltd%' OR defendant LIKE '%Limited%' OR defendant LIKE '% Ltd%' THEN 'company' ELSE 'other' END AS defendant_kind, case_type, COUNT(*) AS cases FROM legal WHERE defendant IS NOT NULL AND defendant <> '' GROUP BY defendant_kind, case_type
```
Correct answer: company, Administrative Case, 12; company, Civil Case, 66; company, Commercial Case, 45; company, Criminal Case, 2; ... (11 rows)

**QB28.** Per case type: in how many cases is the applicant's nationality known, and in how many of those is the applicant Australian?
```sql
SELECT case_type, COUNT(*) AS cases_with_nationality, SUM(CASE WHEN nationality_for_applicant = 'Australia' THEN 1 ELSE 0 END) AS australian_applicants FROM legal WHERE nationality_for_applicant IS NOT NULL AND nationality_for_applicant <> '' GROUP BY case_type
```
Correct answer: Administrative Case, 239, 30; Civil Case, 43, 35; Commercial Case, 19, 16; Criminal Case, 2, 2

**QB29.** For cases citing at least five statutes, per case type: how many cases, how many dismissed, and how many precedents cited on average?
```sql
SELECT case_type, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed, AVG(NULLIF(case_number, '')) AS average_precedents FROM legal WHERE CAST(legal_basis_num AS INTEGER) >= 5 GROUP BY case_type
```
Correct answer: Administrative Case, 27, 20, 11.815; Civil Case, 25, 18, 15.36; Commercial Case, 2, 0, 22.0; Criminal Case, 1, 1, 5.0

**QB30.** By applicant region (Australia, South Asia, East and Southeast Asia, Pacific, elsewhere): how many cases, what share dismissed, and how many statutes cited on average?
```sql
SELECT CASE WHEN nationality_for_applicant = 'Australia' THEN 'Australia' WHEN nationality_for_applicant IN ('India', 'Bangladesh', 'Sri Lanka', 'Pakistan', 'Nepal') THEN 'South Asia' WHEN nationality_for_applicant IN ('China', 'Korea', 'South Korea', 'Vietnam', 'Indonesia', 'Republic of Indonesia', 'Malaysia', 'Philippines', 'Thai', 'Mongolia') THEN 'East and Southeast Asia' WHEN nationality_for_applicant IN ('Fiji', 'Tonga', 'Papua New Guinea', 'New Zealand') THEN 'Pacific' ELSE 'elsewhere' END AS region, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate, AVG(legal_basis_num) AS average_statutes FROM legal WHERE nationality_for_applicant IS NOT NULL AND nationality_for_applicant <> '' GROUP BY region
```
Correct answer: Australia, 83, 0.422, 2.892; East and Southeast Asia, 81, 0.877, 1.568; Pacific, 14, 0.929, 1.786; South Asia, 94, 0.894, 1.404; ... (5 rows)

## NBA players, teams, cities, owners (player): test questions (30)

**Q6.** Per team: how many players, their average age, and how many NBA titles they have won?
```sql
SELECT team.team_name, COUNT(*) AS players, AVG(player.age) AS average_age, SUM(player.nba_championships) AS titles_won_by_players FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name
```
Correct answer: Boston Celtics, 7, 52.571, 9; Brooklyn Nets, 2, 38.5, 0; Chicago Bulls, 3, 41.0, 1; Cleveland Cavaliers, 1, 58.0, 0; ... (24 rows)

**Q7.** Which teams have at least three players, ordered by their players' average age?
```sql
SELECT team.team_name, COUNT(*) AS players, AVG(player.age) AS average_age FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 3 ORDER BY average_age DESC
```
Correct answer: New York Knicks, 7, 62.429; Milwaukee Bucks, 3, 57.333; Houston Rockets, 3, 56.0; Dallas Mavericks, 3, 53.333; ... (13 rows)

**Q12.** For California and Texas teams: how many frontcourt and backcourt players are there?
```sql
SELECT city.state_name, player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IN ('California', 'Texas') AND player.position IN ('Frontcourt', 'Backcourt') GROUP BY city.state_name, player.position
```
Correct answer: California, Backcourt, 4; California, Frontcourt, 12; Texas, Backcourt, 2; Texas, Frontcourt, 4

**Q13.** Do players on franchises founded before 1970 differ in age and titles?
```sql
SELECT CASE WHEN team.founded_year < 1970 THEN 'founded before 1970' ELSE 'founded 1970 or later' END AS franchise_age, COUNT(*) AS players, AVG(player.age) AS average_age, SUM(player.nba_championships) AS titles FROM player JOIN team ON player.team = team.team_name GROUP BY franchise_age
```
Correct answer: founded 1970 or later, 18, 42.889, 4.0; founded before 1970, 70, 46.471, 75

**Q15.** Which teams' players have won more NBA titles than the team itself?
```sql
SELECT team.team_name, SUM(player.nba_championships) AS titles_won_by_players, MAX(CAST(team.championship AS INTEGER)) AS team_titles FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING SUM(player.nba_championships) > MAX(CAST(team.championship AS INTEGER))
```
Correct answer: Dallas Mavericks, 3, 1; Golden State Warriors, 22, 7; Los Angeles Lakers, 28, 17; Phoenix Suns, 3, 0; ... (5 rows)

**Q19.** Per owner nationality: how many teams, and how many championships have they won?
```sql
SELECT owner.nationality, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS championships FROM team JOIN owner ON team.ownership = owner.name GROUP BY owner.nationality
```
Correct answer: American, 14, 29; Israeli-American, 1, 3; Taiwanese-Canadian, 1, 0

**Q20.** Per owner nationality: how many players do their teams have, and how old are they on average?
```sql
SELECT owner.nationality, COUNT(*) AS players, AVG(player.age) AS average_age FROM player JOIN team ON player.team = team.team_name JOIN owner ON team.ownership = owner.name GROUP BY owner.nationality
```
Correct answer: American, 46, 47.043; Israeli-American, 6, 30.167; Taiwanese-Canadian, 2, 38.5

**Q21.** How many players were first overall picks?
```sql
SELECT COUNT(*) AS first_picks FROM player WHERE draft_pick = 1
```
Correct answer: 15

**QX1.** By draft pick (picks 1 to 14, picks 15 to 30, pick 31 or later, undrafted): how many players, how old on average, and how many MVP awards and NBA championships?
```sql
SELECT CASE WHEN CAST(draft_pick AS INTEGER) = 0 THEN 'undrafted' WHEN CAST(draft_pick AS INTEGER) <= 14 THEN 'picks 1 to 14' WHEN CAST(draft_pick AS INTEGER) <= 30 THEN 'picks 15 to 30' ELSE 'pick 31 or later' END AS draft_slot, COUNT(*) AS players, AVG(age) AS average_age, SUM(mvp_awards) AS mvp_awards, SUM(nba_championships) AS nba_championships FROM player WHERE draft_pick IS NOT NULL AND draft_pick <> '' GROUP BY draft_slot
```
Correct answer: pick 31 or later, 18, 47.667, 0, 14; picks 1 to 14, 66, 51.152, 25, 65; picks 15 to 30, 23, 48.522, 3, 8; undrafted, 32, 58.344, 1, 1.0

**QX2.** Per position: how many NBA championships and FIBA World Cup titles have the players won, and what is the most championships won by one player?
```sql
SELECT position, SUM(nba_championships) AS nba_championships, SUM(fiba_world_cup) AS fiba_world_cup_titles, MAX(CAST(nba_championships AS INTEGER)) AS most_nba_championships FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position
```
Correct answer: Backcourt, 29, 4, 6; Frontcourt, 46.0, 8.0, 13

**QX3.** For UCLA, Kentucky, Michigan State, Indiana, Florida and Duke against all other colleges: how many players, NBA championships and MVP winners?
```sql
SELECT CASE WHEN college LIKE '%UCLA%' OR college LIKE '%California, Los Angeles%' THEN 'UCLA' WHEN college LIKE '%Kentucky%' THEN 'Kentucky' WHEN college LIKE '%Michigan State%' THEN 'Michigan State' WHEN college LIKE '%Indiana%' THEN 'Indiana' WHEN college LIKE '%University of Florida%' THEN 'Florida' WHEN college LIKE '%Duke%' THEN 'Duke' ELSE 'any other school' END AS college_group, COUNT(*) AS players, SUM(nba_championships) AS nba_championships, SUM(CASE WHEN mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners FROM player WHERE college IS NOT NULL AND college <> '' GROUP BY college_group
```
Correct answer: Duke, 3, 3, 1; Florida, 4, 3, 0; Indiana, 5, 3, 1; Kentucky, 6, 1, 1; ... (7 rows)

**QX4.** By birth decade (before 1960, 1960 to 1979, 1980s, 1990 or later): how many players, and how many NBA championships, MVP awards and FIBA World Cup titles?
```sql
SELECT CASE WHEN birth_date < '1960' THEN 'born before 1960' WHEN birth_date < '1980' THEN 'born 1960 to 1979' WHEN birth_date < '1990' THEN 'born in the 1980s' ELSE 'born 1990 or later' END AS birth_period, COUNT(*) AS players, SUM(nba_championships) AS nba_championships, SUM(mvp_awards) AS mvp_awards, SUM(fiba_world_cup) AS fiba_world_cup_titles FROM player WHERE birth_date IS NOT NULL AND birth_date <> '' GROUP BY birth_period
```
Correct answer: born 1960 to 1979, 32, 37.0, 11, 7.0; born 1990 or later, 51, 19, 7, 8; born before 1960, 39, 19, 3, 1; born in the 1980s, 19, 13, 8, 4

**QX5.** By founding era (before 1950, 1950 to 1969, 1970 or later): how many teams, how many championships in total, and the most won by one team?
```sql
SELECT CASE WHEN founded_year < 1950 THEN 'founded before 1950' WHEN founded_year < 1970 THEN 'founded 1950 to 1969' ELSE 'founded 1970 or later' END AS founding_era, COUNT(*) AS teams, SUM(CAST(championship AS INTEGER)) AS championships, MAX(CAST(championship AS INTEGER)) AS most_by_one_team FROM team GROUP BY founding_era
```
Correct answer: founded 1950 to 1969, 10, 20, 6; founded 1970 or later, 12, 7, 3; founded before 1950, 8, 52, 18

**QX6.** By population density of the team city (under 2,000, 2,000 to 5,000, over 5,000 people per square km): how many teams, and how many championships?
```sql
SELECT CASE WHEN city.population / CAST(city.area AS REAL) < 2000 THEN 'under 2000 per km2' WHEN city.population / CAST(city.area AS REAL) <= 5000 THEN '2000 to 5000 per km2' ELSE 'over 5000 per km2' END AS density, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS championships FROM team JOIN city ON team.location = city.city_name WHERE CAST(city.area AS REAL) > 0 GROUP BY density
```
Correct answer: 2000 to 5000 per km2, 6, 21; over 5000 per km2, 3, 27; under 2000 per km2, 13, 18

**QX7.** Do teams whose owners are 70 or older have more championships than teams with younger owners?
```sql
SELECT CASE WHEN owner.age >= 70 THEN 'owner 70 or older' ELSE 'owner under 70' END AS owner_age_group, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS championships, AVG(owner.age) AS average_owner_age FROM team JOIN owner ON team.ownership = owner.name GROUP BY owner_age_group
```
Correct answer: owner 70 or older, 8, 22, 78.5; owner under 70, 8, 10, 65.125

**QX8.** Per position, among drafted players: how many were drafted, what was their average pick, and how many were top-3 picks?
```sql
SELECT position, COUNT(*) AS drafted_players, AVG(CAST(draft_pick AS INTEGER)) AS average_pick, SUM(CASE WHEN CAST(draft_pick AS INTEGER) <= 3 THEN 1 ELSE 0 END) AS top_3_picks FROM player WHERE position IN ('Frontcourt', 'Backcourt') AND CAST(draft_pick AS INTEGER) > 0 GROUP BY position
```
Correct answer: Backcourt, 23, 19.217, 9; Frontcourt, 35, 14.486, 11

**QX9.** American versus international players: how many have won an NBA championship, and how many FIBA World Cup titles and Olympic gold medals have they won?
```sql
SELECT CASE WHEN nationality = 'American' THEN 'American' ELSE 'international' END AS origin, COUNT(*) AS players, SUM(CASE WHEN CAST(nba_championships AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS nba_champions, SUM(fiba_world_cup) AS fiba_world_cup_titles, SUM(olympic_gold_medals) AS olympic_gold_medals FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY origin
```
Correct answer: American, 116, 27, 16.0, 39.0; international, 23, 6, 4, 1

**QX10.** Per NBA team: how many players, and how many of them were drafted with a better (lower) pick than the average drafted player?
```sql
SELECT team.team_name, COUNT(*) AS players, SUM(CASE WHEN CAST(player.draft_pick AS INTEGER) > 0 AND CAST(player.draft_pick AS INTEGER) < (SELECT AVG(CAST(draft_pick AS INTEGER)) FROM player WHERE CAST(draft_pick AS INTEGER) > 0) THEN 1 ELSE 0 END) AS better_than_average_picks FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name
```
Correct answer: Boston Celtics, 7, 5; Brooklyn Nets, 2, 1; Chicago Bulls, 3, 3; Cleveland Cavaliers, 1, 1; ... (24 rows)

**QX11.** Per draft era (drafted before 2000, or 2000 or later) and position: how many drafted players, and how old on average?
```sql
SELECT CASE WHEN CAST(draft_year AS INTEGER) < 2000 THEN 'drafted before 2000' ELSE 'drafted 2000 or later' END AS draft_era, position, COUNT(*) AS players, AVG(age) AS average_age FROM player WHERE CAST(draft_year AS INTEGER) > 0 AND position IN ('Frontcourt', 'Backcourt') GROUP BY draft_era, position
```
Correct answer: drafted 2000 or later, Backcourt, 15, 32.867; drafted 2000 or later, Frontcourt, 13, 32.615; drafted before 2000, Backcourt, 10, 65.4; drafted before 2000, Frontcourt, 25, 69.76

**QX12.** By the team's championship record (no titles or at least one) and the player's origin (American or international): how many players?
```sql
SELECT CASE WHEN CAST(team.championship AS INTEGER) = 0 THEN 'no titles' ELSE 'at least one title' END AS team_record, CASE WHEN player.nationality = 'American' THEN 'American' ELSE 'international' END AS origin, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name WHERE player.nationality IS NOT NULL AND player.nationality <> '' GROUP BY team_record, origin
```
Correct answer: at least one title, American, 66; at least one title, international, 11; no titles, American, 8; no titles, international, 2

**QF1.** Per origin (American or international) and position: how many players, and how old on average?
```sql
SELECT CASE WHEN nationality = 'American' THEN 'American' ELSE 'international' END AS origin, position, COUNT(*) AS players, AVG(age) AS average_age FROM player WHERE position IN ('Frontcourt', 'Backcourt') AND nationality IS NOT NULL AND nationality <> '' GROUP BY origin, position
```
Correct answer: American, Backcourt, 26, 49.923; American, Frontcourt, 36, 62.722; international, Backcourt, 4, 37.75; international, Frontcourt, 9, 42.333

**QF2.** Per position: how many players, MVP winners and NBA champions?
```sql
SELECT position, COUNT(*) AS players, SUM(CASE WHEN mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(CASE WHEN CAST(nba_championships AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS champions FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position
```
Correct answer: Backcourt, 31, 7, 11; Frontcourt, 45, 5, 13

**QF3.** Per draft decade: how many players, and how many were top-10 picks?
```sql
SELECT CASE WHEN CAST(draft_year AS INTEGER) >= 2010 THEN '2010 or later' WHEN CAST(draft_year AS INTEGER) >= 2000 THEN '2000s' WHEN CAST(draft_year AS INTEGER) >= 1990 THEN '1990s' WHEN CAST(draft_year AS INTEGER) > 0 THEN 'before 1990' ELSE 'undrafted' END AS draft_decade, COUNT(*) AS players, SUM(CASE WHEN CAST(draft_pick AS INTEGER) BETWEEN 1 AND 10 THEN 1 ELSE 0 END) AS top_10_picks FROM player WHERE draft_year IS NOT NULL AND draft_year <> '' GROUP BY draft_decade
```
Correct answer: 1990s, 11, 5; 2000s, 15, 9; 2010 or later, 46, 20; before 1990, 42, 22; ... (5 rows)

**QF4.** Per team: how many MVP winners and international players?
```sql
SELECT team.team_name, SUM(CASE WHEN player.mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(CASE WHEN player.nationality NOT IN ('', 'American') THEN 1 ELSE 0 END) AS international FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name
```
Correct answer: Boston Celtics, 4, 1; Brooklyn Nets, 0, 1; Chicago Bulls, 0, 0; Cleveland Cavaliers, 0, 0; ... (24 rows)

**QF5.** Per team: what is the best draft pick among its drafted players, and how many were drafted?
```sql
SELECT team.team_name, MIN(CAST(player.draft_pick AS INTEGER)) AS best_pick, COUNT(*) AS drafted FROM player JOIN team ON player.team = team.team_name WHERE CAST(player.draft_pick AS INTEGER) > 0 GROUP BY team.team_name
```
Correct answer: Boston Celtics, 1, 6; Brooklyn Nets, 8, 2; Chicago Bulls, 2, 3; Cleveland Cavaliers, 16, 1; ... (19 rows)

**QF6.** Per state: how many players, MVP winners and Olympic gold medals?
```sql
SELECT city.state_name, COUNT(*) AS players, SUM(CASE WHEN player.mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(player.olympic_gold_medals) AS olympic_golds FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name
```
Correct answer: Arizona, 3, 1, 6; California, 22, 5, 12.0; Florida, 7, 0, 4; Illinois, 3, 0, 1; ... (17 rows)

**QF7.** Which five states have the most NBA championships won by the players of their teams?
```sql
SELECT city.state_name, SUM(CAST(player.nba_championships AS INTEGER)) AS player_titles FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name ORDER BY player_titles DESC, city.state_name LIMIT 5
```
Correct answer: California, 50; Massachusetts, 9; Texas, 9; Arizona, 3; ... (5 rows)

**QF8.** Per team: how many players, and how many of them are older than the league's average age?
```sql
SELECT team.team_name, COUNT(*) AS players, SUM(CASE WHEN player.age > (SELECT AVG(age) FROM player) THEN 1 ELSE 0 END) AS older_players FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name
```
Correct answer: Boston Celtics, 7, 3; Brooklyn Nets, 2, 0; Chicago Bulls, 3, 1; Cleveland Cavaliers, 1, 1; ... (24 rows)

**QF9.** Per state: how many teams, their total championships, and their oldest founding year?
```sql
SELECT city.state_name, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS championships, MIN(team.founded_year) AS oldest_founding FROM team JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name
```
Correct answer: Arizona, 1, 0, 1968; California, 4, 25, 1923; Colorado, 1, 1, 1967; Florida, 2, 3, 1988; ... (22 rows)

**QF10.** Which states host teams in cities of more than a million people, how many such teams, and what is the average population of those teams' cities?
```sql
SELECT city.state_name, COUNT(*) AS teams, AVG(city.population) AS average_population FROM team JOIN city ON team.location = city.city_name WHERE city.population > 1000000 AND city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name
```
Correct answer: Arizona, 1, 1662607.0; California, 2, 3820914.0; Illinois, 1, 2746388.0; New York, 1, 8258035.0; ... (7 rows)

## NBA players, teams, cities, owners (player): build questions (40)

**QB1.** Per position: how many players, how old are they on average, and how old are the youngest and the oldest?
```sql
SELECT position, COUNT(*) AS players, AVG(age) AS average_age, MIN(age) AS youngest_age, MAX(age) AS oldest_age FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position
```
Correct answer: Backcourt, 31, 49.097, 24, 106; Frontcourt, 45, 58.644, 21, 98

**QB2.** Per position: how many MVP awards and Olympic gold medals have the players won in total?
```sql
SELECT position, SUM(mvp_awards) AS mvp_awards, SUM(olympic_gold_medals) AS olympic_gold_medals FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position
```
Correct answer: Backcourt, 14, 13; Frontcourt, 7, 11.0

**QB3.** Per age bracket: how many players, how many MVP winners and how many Olympic gold medalists?
```sql
SELECT CASE WHEN age < 25 THEN 'under 25' WHEN age < 30 THEN '25 to 29' WHEN age < 35 THEN '30 to 34' WHEN age < 50 THEN '35 to 49' ELSE '50 or older' END AS age_bracket, COUNT(*) AS players, SUM(CASE WHEN mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(CASE WHEN CAST(olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS olympic_gold_medalists FROM player GROUP BY age_bracket
```
Correct answer: 25 to 29, 17, 2, 3; 30 to 34, 20, 3, 5; 35 to 49, 26, 6, 11; 50 or older, 69, 6, 6; ... (5 rows)

**QB4.** American versus international players: how many players, how many have an Olympic gold medal, and how many gold medals in total?
```sql
SELECT CASE WHEN nationality = 'American' THEN 'American' ELSE 'international' END AS origin, COUNT(*) AS players, SUM(CASE WHEN CAST(olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS gold_medalists, SUM(olympic_gold_medals) AS olympic_gold_medals FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY origin
```
Correct answer: American, 116, 25, 39.0; international, 23, 1, 1

**QB5.** By number of Olympic gold medals (none, one, two or more): how many players, how old on average, and how many MVP awards?
```sql
SELECT CASE WHEN CAST(olympic_gold_medals AS INTEGER) = 0 THEN 'none' WHEN CAST(olympic_gold_medals AS INTEGER) = 1 THEN 'one' ELSE 'two or more' END AS olympic_golds, COUNT(*) AS players, AVG(age) AS average_age, SUM(mvp_awards) AS mvp_awards FROM player WHERE olympic_gold_medals IS NOT NULL AND olympic_gold_medals <> '' GROUP BY olympic_golds
```
Correct answer: none, 114, 53.93, 7; one, 15, 44.333, 7; two or more, 11, 37.364, 15

**QB6.** By number of MVP awards (none, one, several): how many players, how old on average, and how many Olympic gold medals?
```sql
SELECT CASE WHEN mvp_awards = 0 THEN 'none' WHEN mvp_awards = 1 THEN 'one' ELSE 'several' END AS mvp_count, COUNT(*) AS players, AVG(age) AS average_age, SUM(olympic_gold_medals) AS olympic_gold_medals FROM player GROUP BY mvp_count
```
Correct answer: none, 124, 52.798, 17.0; one, 11, 40.455, 16; several, 6, 47.667, 7

**QB7.** Per origin (American or international) and age group (under 30, 30 or older): how many players?
```sql
SELECT CASE WHEN nationality = 'American' THEN 'American' ELSE 'international' END AS origin, CASE WHEN age < 30 THEN 'under 30' ELSE '30 or older' END AS age_group, COUNT(*) AS players FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY origin, age_group
```
Correct answer: American, 30 or older, 95; American, under 30, 21; international, 30 or older, 18; international, under 30, 5

**QB8.** Per position and MVP status: how many players, and how old are they on average?
```sql
SELECT position, CASE WHEN mvp_awards >= 1 THEN 'MVP winner' ELSE 'no MVP' END AS mvp_status, COUNT(*) AS players, AVG(age) AS average_age FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position, mvp_status
```
Correct answer: Backcourt, MVP winner, 7, 49.286; Backcourt, no MVP, 24, 49.042; Frontcourt, MVP winner, 5, 40.6; Frontcourt, no MVP, 40, 60.9

**QB9.** Per nationality group (only American, dual nationality including American, European, rest of the world): how many players, how old on average, and how many Olympic gold medals?
```sql
SELECT CASE WHEN nationality = 'American' THEN 'USA only' WHEN nationality LIKE '%American%' THEN 'dual nationality' WHEN nationality LIKE '%French%' OR nationality LIKE '%Greek%' OR nationality LIKE '%Serbian%' OR nationality LIKE '%Slovenian%' OR nationality LIKE '%Croatian%' OR nationality LIKE '%German%' OR nationality LIKE '%Dutch%' OR nationality LIKE '%British%' THEN 'Europe' ELSE 'rest of world' END AS region, COUNT(*) AS players, AVG(age) AS average_age, SUM(olympic_gold_medals) AS olympic_gold_medals FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY region
```
Correct answer: Europe, 10, 36.7, 0; USA only, 116, 53.793, 39.0; dual nationality, 8, 36.75, 1; rest of world, 5, 39.8, 0

**QB10.** Per position: how many players are older than the average player?
```sql
SELECT position, COUNT(*) AS older_than_average FROM player WHERE position IN ('Frontcourt', 'Backcourt') AND age > (SELECT AVG(age) FROM player) GROUP BY position
```
Correct answer: Backcourt, 12; Frontcourt, 29

**QB11.** Which three states' teams have players with the most MVP awards, and how many players do those teams have?
```sql
SELECT city.state_name, COUNT(*) AS players, SUM(player.mvp_awards) AS mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name ORDER BY mvp_awards DESC, city.state_name LIMIT 3
```
Correct answer: California, 22, 11; Massachusetts, 7, 4; Texas, 11, 3

**QB12.** Per position: how many players have won both an MVP award and an Olympic gold medal?
```sql
SELECT position, COUNT(*) AS players, SUM(CASE WHEN mvp_awards >= 1 AND CAST(olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS mvp_and_olympic_gold FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position
```
Correct answer: Backcourt, 31, 5; Frontcourt, 45, 3

**QB13.** What is the average age of players who have won an MVP award?
```sql
SELECT AVG(age) AS average_age_of_mvp_winners FROM player WHERE mvp_awards >= 1
```
Correct answer: 43.0

**QB14.** Per position and Olympic status (gold medalist or not): how many players, and how old on average?
```sql
SELECT position, CASE WHEN CAST(olympic_gold_medals AS INTEGER) >= 1 THEN 'gold medalist' ELSE 'no gold' END AS olympic_status, COUNT(*) AS players, AVG(age) AS average_age FROM player WHERE position IN ('Frontcourt', 'Backcourt') AND olympic_gold_medals IS NOT NULL AND olympic_gold_medals <> '' GROUP BY position, olympic_status
```
Correct answer: Backcourt, gold medalist, 9, 44.333; Backcourt, no gold, 22, 51.045; Frontcourt, gold medalist, 6, 52.0; Frontcourt, no gold, 38, 59.816

**QB15.** For the Lakers, Celtics, Warriors and Knicks: how many players, MVP awards and Olympic gold medals?
```sql
SELECT team, COUNT(*) AS players, SUM(mvp_awards) AS mvp_awards, SUM(olympic_gold_medals) AS olympic_gold_medals FROM player WHERE team IN ('Los Angeles Lakers', 'Boston Celtics', 'Golden State Warriors', 'New York Knicks') GROUP BY team
```
Correct answer: Boston Celtics, 7, 4, 5; Golden State Warriors, 11, 2, 4; Los Angeles Lakers, 9, 9, 8; New York Knicks, 7, 0, 0

**QB16.** Which teams have at least five players, and how old are their players on average?
```sql
SELECT team, COUNT(*) AS players, AVG(age) AS average_age FROM player WHERE team IS NOT NULL AND team <> '' GROUP BY team HAVING COUNT(*) >= 5
```
Correct answer: Boston Celtics, 7, 52.571; Detroit Pistons, 6, 45.333; Golden State Warriors, 11, 41.364; Los Angeles Lakers, 9, 52.0; ... (8 rows)

**QB17.** Which five NBA teams have players with the most MVP awards, and how many players and Olympic gold medals do they have?
```sql
SELECT team.team_name, COUNT(*) AS players, SUM(player.mvp_awards) AS mvp_awards, SUM(player.olympic_gold_medals) AS olympic_gold_medals FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name ORDER BY mvp_awards DESC, team.team_name LIMIT 5
```
Correct answer: Los Angeles Lakers, 9, 9, 8; Boston Celtics, 7, 4, 5; San Antonio Spurs, 5, 3, 3; Golden State Warriors, 11, 2, 4; ... (5 rows)

**QB18.** For NBA teams with at least four players: how many players, and how many championships has the team won?
```sql
SELECT team.team_name, COUNT(*) AS players, MAX(CAST(team.championship AS INTEGER)) AS team_championships FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 4
```
Correct answer: Boston Celtics, 7, 18; Detroit Pistons, 6, 3; Golden State Warriors, 11, 7; Los Angeles Lakers, 9, 17; ... (8 rows)

**QB19.** By the team's championship record (none, one to three, four or more): how many players, how old on average, and how many MVP awards?
```sql
SELECT CASE WHEN CAST(team.championship AS INTEGER) = 0 THEN 'no titles' WHEN CAST(team.championship AS INTEGER) <= 3 THEN '1 to 3 titles' ELSE '4 or more titles' END AS team_record, COUNT(*) AS players, AVG(player.age) AS average_age, SUM(player.mvp_awards) AS mvp_awards FROM player JOIN team ON player.team = team.team_name GROUP BY team_record
```
Correct answer: 1 to 3 titles, 43, 47.023, 5; 4 or more titles, 35, 45.314, 18; no titles, 10, 41.7, 1

**QB20.** Which NBA teams have players who are older on average than the average player, and how many players do they have?
```sql
SELECT team.team_name, COUNT(*) AS players, AVG(player.age) AS average_age FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING AVG(player.age) > (SELECT AVG(age) FROM player)
```
Correct answer: Boston Celtics, 7, 52.571; Cleveland Cavaliers, 1, 58.0; Dallas Mavericks, 3, 53.333; Houston Rockets, 3, 56.0; ... (11 rows)

**QB21.** For NBA teams with at least three players: how old are their youngest and oldest players?
```sql
SELECT team.team_name, COUNT(*) AS players, MIN(player.age) AS youngest_age, MAX(player.age) AS oldest_age FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 3
```
Correct answer: Boston Celtics, 7, 27, 105; Chicago Bulls, 3, 28, 65; Dallas Mavericks, 3, 33, 67; Detroit Pistons, 6, 22, 98; ... (13 rows)

**QB22.** Which NBA teams have at least one player with both an MVP award and an Olympic gold medal, and how many such players?
```sql
SELECT team.team_name, SUM(CASE WHEN player.mvp_awards >= 1 AND CAST(player.olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS mvp_and_olympic_gold FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING SUM(CASE WHEN player.mvp_awards >= 1 AND CAST(player.olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) >= 1
```
Correct answer: Boston Celtics, 3; Golden State Warriors, 1; Los Angeles Lakers, 4; Philadelphia 76ers, 1; ... (6 rows)

**QB23.** For NBA teams with at least three players: how many frontcourt and how many backcourt players?
```sql
SELECT team.team_name, COUNT(*) AS players, SUM(CASE WHEN player.position = 'Frontcourt' THEN 1 ELSE 0 END) AS frontcourt, SUM(CASE WHEN player.position = 'Backcourt' THEN 1 ELSE 0 END) AS backcourt FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 3
```
Correct answer: Boston Celtics, 7, 2, 1; Chicago Bulls, 3, 0, 2; Dallas Mavericks, 3, 1, 1; Detroit Pistons, 6, 1, 1; ... (13 rows)

**QB24.** Per team city: how many players play there, and how many Olympic gold medals do they hold?
```sql
SELECT team.location, COUNT(*) AS players, SUM(player.olympic_gold_medals) AS olympic_gold_medals FROM player JOIN team ON player.team = team.team_name GROUP BY team.location
```
Correct answer: Boston, 7, 5; Brooklyn, 2, 0; Chicago, 3, 1; Cleveland, 1, 0; ... (23 rows)

**QB25.** Which three NBA teams have players with the most Olympic gold medals?
```sql
SELECT team.team_name, SUM(player.olympic_gold_medals) AS olympic_gold_medals, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name ORDER BY olympic_gold_medals DESC, team.team_name LIMIT 3
```
Correct answer: Los Angeles Lakers, 8, 9; Phoenix Suns, 6, 3; Boston Celtics, 5, 7

**QB26.** By the team's championship record (no titles or at least one) and position: how many players?
```sql
SELECT CASE WHEN CAST(team.championship AS INTEGER) = 0 THEN 'no titles' ELSE 'at least one title' END AS team_record, player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name WHERE player.position IN ('Frontcourt', 'Backcourt') GROUP BY team_record, player.position
```
Correct answer: at least one title, Backcourt, 12; at least one title, Frontcourt, 28; no titles, Backcourt, 4; no titles, Frontcourt, 2

**QB27.** Per NBA team with at least three players: how many players are under 30 and how many are 30 or older?
```sql
SELECT team.team_name, SUM(CASE WHEN player.age < 30 THEN 1 ELSE 0 END) AS under_30, SUM(CASE WHEN player.age >= 30 THEN 1 ELSE 0 END) AS age_30_or_older FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 3
```
Correct answer: Boston Celtics, 2, 5; Chicago Bulls, 1, 2; Dallas Mavericks, 0, 3; Detroit Pistons, 3, 3; ... (13 rows)

**QB28.** By championship record (none, one to three, four or more): how many teams, and how many championships in total?
```sql
SELECT CASE WHEN CAST(championship AS INTEGER) = 0 THEN 'no titles' WHEN CAST(championship AS INTEGER) <= 3 THEN '1 to 3 titles' ELSE '4 or more titles' END AS team_record, COUNT(*) AS teams, SUM(CAST(championship AS INTEGER)) AS championships FROM team GROUP BY team_record
```
Correct answer: 1 to 3 titles, 15, 26; 4 or more titles, 5, 53; no titles, 10, 0

**QB29.** Per state: how many teams, and how large is the biggest team city?
```sql
SELECT city.state_name, COUNT(*) AS teams, MAX(city.population) AS largest_city_population FROM team JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name
```
Correct answer: Arizona, 1, 1662607; California, 4, 3820914; Colorado, 1, 715522; Florida, 2, 442241; ... (22 rows)

**QB30.** Per state: how many teams, and how many of them have won more championships than the average team?
```sql
SELECT city.state_name, COUNT(*) AS teams, SUM(CASE WHEN CAST(team.championship AS INTEGER) > (SELECT AVG(CAST(championship AS INTEGER)) FROM team) THEN 1 ELSE 0 END) AS teams_above_average FROM team JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name
```
Correct answer: Arizona, 1, 0; California, 4, 2; Colorado, 1, 0; Florida, 2, 1; ... (22 rows)

**QB31.** By city size (under 500,000, 500,000 to 1 million, over 1 million people): how many teams, and how many championships in total and per team?
```sql
SELECT CASE WHEN city.population < 500000 THEN 'under 500k' WHEN city.population <= 1000000 THEN '500k to 1M' ELSE 'over 1M' END AS city_size, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS championships, AVG(CAST(team.championship AS INTEGER)) AS championships_per_team FROM team JOIN city ON team.location = city.city_name GROUP BY city_size
```
Correct answer: 500k to 1M, 12, 37, 3.083; over 1M, 10, 37, 3.7; under 500k, 6, 4, 0.667

**QB32.** For states with at least two teams: how many championships in total, and the most won by one team?
```sql
SELECT city.state_name, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS championships, MAX(CAST(team.championship AS INTEGER)) AS most_by_one_team FROM team JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name HAVING COUNT(*) >= 2
```
Correct answer: California, 4, 25, 17; Florida, 2, 3, 3; Texas, 3, 8, 5

**QB33.** By city size (under 500,000, 500,000 to 1 million, over 1 million people): how many players, how old on average, and how many MVP awards?
```sql
SELECT CASE WHEN city.population < 500000 THEN 'under 500k' WHEN city.population <= 1000000 THEN '500k to 1M' ELSE 'over 1M' END AS city_size, COUNT(*) AS players, AVG(player.age) AS average_age, SUM(player.mvp_awards) AS mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city_size
```
Correct answer: 500k to 1M, 33, 47.242, 9; over 1M, 43, 46.651, 15; under 500k, 10, 38.3, 0

**QB34.** Which five team cities have the most players, and how many people live there?
```sql
SELECT city.city_name, COUNT(*) AS players, MAX(city.population) AS population FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.city_name ORDER BY players DESC, city.city_name LIMIT 5
```
Correct answer: San Francisco, 11, 808988; Los Angeles, 10, 3820914; Philadelphia, 8, 1603797; Boston, 7, 675647; ... (5 rows)

**QB35.** Per state: how many frontcourt and how many backcourt players play for its teams?
```sql
SELECT city.state_name, SUM(CASE WHEN player.position = 'Frontcourt' THEN 1 ELSE 0 END) AS frontcourt, SUM(CASE WHEN player.position = 'Backcourt' THEN 1 ELSE 0 END) AS backcourt FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name
```
Correct answer: Arizona, 1, 2; California, 12, 4; Florida, 0, 2; Illinois, 0, 2; ... (17 rows)

**QB36.** For states whose teams have at least three players: how old are the players on average, and how old is the oldest?
```sql
SELECT city.state_name, COUNT(*) AS players, AVG(player.age) AS average_age, MAX(player.age) AS oldest_age FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name HAVING COUNT(*) >= 3
```
Correct answer: Arizona, 3, 38.0, 49; California, 22, 46.727, 81; Florida, 7, 34.571, 61; Illinois, 3, 41.0, 65; ... (10 rows)

**QB37.** By city size (over or under 1 million people) and position: how many players?
```sql
SELECT CASE WHEN city.population > 1000000 THEN 'over 1M' ELSE '1M or less' END AS city_size, player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE player.position IN ('Frontcourt', 'Backcourt') GROUP BY city_size, player.position
```
Correct answer: 1M or less, Backcourt, 6; 1M or less, Frontcourt, 14; over 1M, Backcourt, 10; over 1M, Frontcourt, 16

**QB38.** Per position: how many players play in a city larger than the average team city?
```sql
SELECT player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE player.position IN ('Frontcourt', 'Backcourt') AND city.population > (SELECT AVG(population) FROM city WHERE city_name IN (SELECT location FROM team)) GROUP BY player.position
```
Correct answer: Backcourt, 9; Frontcourt, 15

**QB39.** Per state: how many international players play for its teams, and how many players in total?
```sql
SELECT city.state_name, COUNT(*) AS players, SUM(CASE WHEN player.nationality = 'American' THEN 0 ELSE 1 END) AS international_players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' AND player.nationality IS NOT NULL AND player.nationality <> '' GROUP BY city.state_name
```
Correct answer: Arizona, 3, 0; California, 22, 4; Florida, 7, 1; Illinois, 3, 0; ... (17 rows)

**QB40.** For the three states whose most successful team has won the most championships: how many players do the state's teams have, how many Olympic gold medals do those players hold, and how many titles has that top team won?
```sql
SELECT city.state_name, COUNT(*) AS players, SUM(player.olympic_gold_medals) AS olympic_gold_medals, MAX(CAST(team.championship AS INTEGER)) AS most_titles_of_one_team FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name ORDER BY most_titles_of_one_team DESC, city.state_name LIMIT 3
```
Correct answer: Massachusetts, 7, 5, 18; California, 22, 12.0, 17; Illinois, 3, 1, 6

## Drugs and diseases (med): test questions (32)

**Q16.** How many drugs must be refrigerated?
```sql
SELECT COUNT(*) AS drugs FROM drug WHERE storage_conditions LIKE '%refrigerat%'
```
Correct answer: 3

**QX1.** Per disease mechanism: how many diseases list a genetic or family risk, a lifestyle risk (smoking, alcohol, obesity, diet, inactivity), or age as a risk factor?
```sql
SELECT CASE WHEN pathogenesis LIKE '%infectious%' THEN 'infectious' WHEN pathogenesis LIKE '%genetic%' THEN 'genetic' WHEN pathogenesis LIKE '%neoplastic%' THEN 'neoplastic' WHEN pathogenesis LIKE '%inflammatory%' OR pathogenesis LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS mechanism, COUNT(*) AS diseases, SUM(CASE WHEN risk_factors LIKE '%genetic%' OR risk_factors LIKE '%family_history%' THEN 1 ELSE 0 END) AS genetic_or_family, SUM(CASE WHEN risk_factors LIKE '%smok%' OR risk_factors LIKE '%alcohol%' OR risk_factors LIKE '%obes%' OR risk_factors LIKE '%diet%' OR risk_factors LIKE '%sedentary%' THEN 1 ELSE 0 END) AS lifestyle, SUM(CASE WHEN '||' || REPLACE(risk_factors, ' || ', '||') || '||' LIKE '%||age||%' THEN 1 ELSE 0 END) AS age FROM disease WHERE pathogenesis <> '' AND risk_factors <> '' GROUP BY mechanism
```
Correct answer: genetic, 6, 5, 3, 3; infectious, 15, 2, 1, 5; inflammatory or autoimmune, 12, 4, 10, 5; neoplastic, 3, 0, 2, 3; ... (5 rows)

**QX2.** How many infectious and non-infectious diseases affect each body system?
```sql
SELECT CASE WHEN affected_organs LIKE '%lung%' OR affected_organs LIKE '%respirat%' THEN 'lungs and airways' WHEN affected_organs LIKE '%heart%' OR affected_organs LIKE '%arter%' OR affected_organs LIKE '%blood vessel%' OR affected_organs LIKE '%vascular%' THEN 'heart and vessels' WHEN affected_organs LIKE '%brain%' OR affected_organs LIKE '%nerv%' THEN 'nervous system' WHEN affected_organs LIKE '%gut%' OR affected_organs LIKE '%gastro%' OR affected_organs LIKE '%intestin%' OR affected_organs LIKE '%bowel%' OR affected_organs LIKE '%esophag%' OR affected_organs LIKE '%stomach%' OR affected_organs LIKE '%liver%' OR affected_organs LIKE '%abdom%' THEN 'digestive system' WHEN affected_organs LIKE '%skin%' THEN 'skin' WHEN affected_organs LIKE '%joint%' OR affected_organs LIKE '%bone%' OR affected_organs LIKE '%muscle%' THEN 'bones, joints and muscles' ELSE 'other' END AS body_system, CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' ELSE 'not infectious' END AS kind, COUNT(*) AS diseases FROM disease WHERE affected_organs <> '' AND disease_type <> '' GROUP BY body_system, kind
```
Correct answer: bones, joints and muscles, infectious, 1; bones, joints and muscles, not infectious, 7; digestive system, infectious, 4; digestive system, not infectious, 10; ... (14 rows)

**QX3.** Per administration route: how many drugs should be avoided in pregnancy, by children, by the elderly, and by patients with liver or kidney problems?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 'injected' ELSE 'other' END AS route, COUNT(*) AS drugs, SUM(CASE WHEN unsuitable_population LIKE '%pregnan%' THEN 1 ELSE 0 END) AS pregnancy, SUM(CASE WHEN unsuitable_population LIKE '%child%' OR unsuitable_population LIKE '%pediatric%' OR unsuitable_population LIKE '%infant%' THEN 1 ELSE 0 END) AS children, SUM(CASE WHEN unsuitable_population LIKE '%elderly%' OR unsuitable_population LIKE '%older adult%' THEN 1 ELSE 0 END) AS elderly, SUM(CASE WHEN unsuitable_population LIKE '%liver%' OR unsuitable_population LIKE '%hepatic%' OR unsuitable_population LIKE '%kidney%' OR unsuitable_population LIKE '%renal%' THEN 1 ELSE 0 END) AS liver_or_kidney FROM drug WHERE administration_route <> '' GROUP BY route
```
Correct answer: injected, 11, 2, 2, 0, 2; oral, 57, 26, 20, 4, 16; other, 11, 2, 2, 0, 2

**QX4.** Per instruction on how to take the drug: how many drugs, how many are taken once a day, and how many need a prescription?
```sql
SELECT CASE WHEN recommended_usage LIKE '%with or without food%' THEN 'with or without food' WHEN recommended_usage LIKE '%with food%' OR recommended_usage LIKE '%after meals%' THEN 'with food' WHEN recommended_usage LIKE '%without food%' OR recommended_usage LIKE '%before meals%' THEN 'on an empty stomach' WHEN recommended_usage LIKE '%fixed time%' THEN 'at a fixed time' ELSE 'other' END AS instruction, COUNT(*) AS drugs, SUM(CASE WHEN dosage_frequency LIKE '%once daily%' OR dosage_frequency LIKE '%once a day%' THEN 1 ELSE 0 END) AS once_a_day, SUM(CASE WHEN prescription_status LIKE '%prescription_only%' THEN 1 ELSE 0 END) AS prescription_only FROM drug WHERE recommended_usage <> '' GROUP BY instruction
```
Correct answer: at a fixed time, 6, 5, 2; on an empty stomach, 3, 1, 2; other, 24, 2, 9; with food, 7, 2, 3; ... (5 rows)

**QX5.** Per disease mechanism: how many diseases list fever, pain, fatigue or cough among their common symptoms?
```sql
SELECT CASE WHEN pathogenesis LIKE '%infectious%' THEN 'infectious' WHEN pathogenesis LIKE '%genetic%' THEN 'genetic' WHEN pathogenesis LIKE '%inflammatory%' OR pathogenesis LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS mechanism, SUM(CASE WHEN common_symptoms LIKE '%fever%' THEN 1 ELSE 0 END) AS fever, SUM(CASE WHEN common_symptoms LIKE '%pain%' THEN 1 ELSE 0 END) AS pain, SUM(CASE WHEN common_symptoms LIKE '%fatigue%' OR common_symptoms LIKE '%tired%' THEN 1 ELSE 0 END) AS fatigue, SUM(CASE WHEN common_symptoms LIKE '%cough%' THEN 1 ELSE 0 END) AS cough FROM disease WHERE pathogenesis <> '' AND common_symptoms <> '' GROUP BY mechanism
```
Correct answer: genetic, 0, 3, 3, 1; infectious, 10, 14, 1, 2; inflammatory or autoimmune, 2, 12, 3, 2; other, 0, 7, 2, 1

**QX6.** Per expected outcome: how many diseases have known complications, how many of them can lead to death, and how many complications are listed on average?
```sql
SELECT CASE WHEN prognosis LIKE '%high_mortality%' THEN 'high mortality' WHEN prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'other' END AS outlook, COUNT(*) AS diseases, SUM(CASE WHEN complications LIKE '%death%' THEN 1 ELSE 0 END) AS can_be_fatal, ROUND(AVG(CASE WHEN complications = '' THEN 0 ELSE (LENGTH(complications) - LENGTH(REPLACE(complications, '||', ''))) / 2 + 1 END), 2) AS avg_complications FROM disease WHERE prognosis <> '' AND complications <> '' GROUP BY outlook
```
Correct answer: chronic, 16, 3, 4.5; high mortality, 14, 8, 3.57; other, 12, 1, 2.83

**QX7.** Per kind of disease: how many diseases list drugs, how many drugs does such a disease list on average, and how many list an antibiotic?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease_type LIKE '%neoplastic%' THEN 'neoplastic' WHEN disease_type LIKE '%inflammatory%' OR disease_type LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS kind, COUNT(*) AS diseases, ROUND(AVG(CASE WHEN drugs = '' THEN 0 ELSE (LENGTH(drugs) - LENGTH(REPLACE(drugs, '||', ''))) / 2 + 1 END), 2) AS avg_drugs_listed, SUM(CASE WHEN drugs LIKE '%antibiotic%' OR drugs LIKE '%cillin%' OR drugs LIKE '%mycin%' OR drugs LIKE '%cycline%' OR drugs LIKE '%floxacin%' OR drugs LIKE '%cef%' THEN 1 ELSE 0 END) AS antibiotics FROM disease WHERE disease_type <> '' AND drugs <> '' GROUP BY kind
```
Correct answer: infectious, 27, 2.67, 13; inflammatory or autoimmune, 16, 3.5, 2; neoplastic, 6, 2.0, 0; other, 21, 5.05, 1; ... (5 rows)

**QX8.** Per body system affected by the disease: how many drug-disease treatment pairs are there, and in how many is the drug taken by mouth?
```sql
SELECT CASE WHEN disease.affected_organs LIKE '%lung%' OR disease.affected_organs LIKE '%respirat%' THEN 'lungs and airways' WHEN disease.affected_organs LIKE '%brain%' OR disease.affected_organs LIKE '%nerv%' THEN 'nervous system' WHEN disease.affected_organs LIKE '%heart%' OR disease.affected_organs LIKE '%arter%' OR disease.affected_organs LIKE '%vascular%' THEN 'heart and vessels' ELSE 'other' END AS body_system, COUNT(*) AS pairs, SUM(CASE WHEN drug.administration_route LIKE '%oral%' THEN 1 ELSE 0 END) AS oral FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.affected_organs <> '' GROUP BY body_system
```
Correct answer: heart and vessels, 7, 5; lungs and airways, 7, 3; nervous system, 2, 2; other, 7, 2

**QX9.** Per kind of disease with at least eight drug-disease treatment pairs: in how many of those pairs should the drug be avoided in pregnancy, and in how many by children?
```sql
SELECT CASE WHEN disease.disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease.disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease.disease_type LIKE '%metabolic%' OR disease.disease_type LIKE '%endocrine%' THEN 'metabolic or endocrine' ELSE 'other' END AS kind, COUNT(*) AS pairs, SUM(CASE WHEN drug.unsuitable_population LIKE '%pregnan%' THEN 1 ELSE 0 END) AS not_in_pregnancy, SUM(CASE WHEN drug.unsuitable_population LIKE '%child%' OR drug.unsuitable_population LIKE '%pediatric%' THEN 1 ELSE 0 END) AS not_for_children FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.disease_type <> '' GROUP BY kind HAVING COUNT(*) >= 8
```
Correct answer: other, 11, 2, 4; psychiatric, 9, 2, 2

**QX10.** Per main difficulty in diagnosing the disease: how many diseases, and how many of them are diagnosed with laboratory tests or imaging?
```sql
SELECT CASE WHEN diagnosis_challenges LIKE '%nonspecific%' THEN 'nonspecific symptoms' WHEN diagnosis_challenges LIKE '%mimic%' OR diagnosis_challenges LIKE '%misdiagnos%' THEN 'confused with similar diseases' WHEN diagnosis_challenges LIKE '%test%' OR diagnosis_challenges LIKE '%biomarker%' OR diagnosis_challenges LIKE '%imaging%' THEN 'no reliable test' ELSE 'other' END AS difficulty, COUNT(*) AS diseases, SUM(CASE WHEN diagnostic_methods LIKE '%laboratory_test%' OR diagnostic_methods LIKE '%imaging%' THEN 1 ELSE 0 END) AS lab_or_imaging FROM disease WHERE diagnosis_challenges <> '' GROUP BY difficulty
```
Correct answer: confused with similar diseases, 1, 0; no reliable test, 3, 1; nonspecific symptoms, 22, 15; other, 5, 2

**QX11.** Which three kinds of underlying cause (other than unclassified ones) account for the most diseases, and how many of those diseases are chronic?
```sql
SELECT CASE WHEN etiology LIKE '%infect%' OR etiology LIKE '%bacteri%' OR etiology LIKE '%virus%' OR etiology LIKE '%viral%' OR etiology LIKE '%parasit%' THEN 'infection' WHEN etiology LIKE '%gene%' OR etiology LIKE '%mutation%' OR etiology LIKE '%inherit%' OR etiology LIKE '%hereditary%' THEN 'genetic' WHEN etiology LIKE '%smok%' OR etiology LIKE '%alcohol%' OR etiology LIKE '%diet%' OR etiology LIKE '%obes%' THEN 'lifestyle' WHEN etiology LIKE '%drug%' OR etiology LIKE '%medication%' OR etiology LIKE '%antibiotic%' OR etiology LIKE '%opioid%' THEN 'medication or drug use' ELSE 'other' END AS cause, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic FROM disease WHERE etiology <> '' GROUP BY cause HAVING cause <> 'other' ORDER BY diseases DESC, cause LIMIT 3
```
Correct answer: infection, 25, 7; genetic, 6, 1; lifestyle, 6, 2

**QX12.** Which disease mechanisms affect more areas of daily life on average than diseases overall?
```sql
SELECT CASE WHEN pathogenesis LIKE '%infectious%' THEN 'infectious' WHEN pathogenesis LIKE '%genetic%' THEN 'genetic' WHEN pathogenesis LIKE '%neoplastic%' THEN 'neoplastic' WHEN pathogenesis LIKE '%inflammatory%' OR pathogenesis LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS mechanism, COUNT(*) AS diseases, ROUND(AVG(CASE WHEN quality_of_life_impact = '' THEN 0 ELSE (LENGTH(quality_of_life_impact) - LENGTH(REPLACE(quality_of_life_impact, '||', ''))) / 2 + 1 END), 2) AS avg_impacts FROM disease WHERE pathogenesis <> '' AND quality_of_life_impact <> '' GROUP BY mechanism HAVING AVG(CASE WHEN quality_of_life_impact = '' THEN 0 ELSE (LENGTH(quality_of_life_impact) - LENGTH(REPLACE(quality_of_life_impact, '||', ''))) / 2 + 1 END) > (SELECT AVG(CASE WHEN quality_of_life_impact = '' THEN 0 ELSE (LENGTH(quality_of_life_impact) - LENGTH(REPLACE(quality_of_life_impact, '||', ''))) / 2 + 1 END) FROM disease WHERE quality_of_life_impact <> '')
```
Correct answer: genetic, 7, 4.29; inflammatory or autoimmune, 11, 3.0; other, 11, 3.36

**QX13.** Per administration route: how many drugs have a stated indication, and how many are indicated for pain, for infections, and for blood pressure, blood sugar or cholesterol?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 'injected' ELSE 'other' END AS route, COUNT(*) AS drugs, SUM(CASE WHEN indication LIKE '%pain%' THEN 1 ELSE 0 END) AS for_pain, SUM(CASE WHEN indication LIKE '%infect%' THEN 1 ELSE 0 END) AS for_infection, SUM(CASE WHEN indication LIKE '%blood pressure%' OR indication LIKE '%hypertension%' OR indication LIKE '%glucose%' OR indication LIKE '%diabet%' OR indication LIKE '%cholesterol%' THEN 1 ELSE 0 END) AS cardiometabolic FROM drug WHERE administration_route <> '' AND indication <> '' GROUP BY route
```
Correct answer: injected, 10, 2, 1, 1; oral, 56, 10, 11, 8; other, 11, 1, 3, 0

**QX14.** Which body systems have diseases with more listed complications on average than diseases overall?
```sql
SELECT CASE WHEN affected_organs LIKE '%lung%' OR affected_organs LIKE '%respirat%' THEN 'lungs and airways' WHEN affected_organs LIKE '%heart%' OR affected_organs LIKE '%arter%' OR affected_organs LIKE '%blood vessel%' OR affected_organs LIKE '%vascular%' THEN 'heart and vessels' WHEN affected_organs LIKE '%brain%' OR affected_organs LIKE '%nerv%' THEN 'nervous system' WHEN affected_organs LIKE '%gut%' OR affected_organs LIKE '%gastro%' OR affected_organs LIKE '%intestin%' OR affected_organs LIKE '%bowel%' OR affected_organs LIKE '%esophag%' OR affected_organs LIKE '%stomach%' OR affected_organs LIKE '%liver%' OR affected_organs LIKE '%abdom%' THEN 'digestive system' ELSE 'other' END AS body_system, COUNT(*) AS diseases, ROUND(AVG(CASE WHEN complications = '' THEN 0 ELSE (LENGTH(complications) - LENGTH(REPLACE(complications, '||', ''))) / 2 + 1 END), 2) AS avg_complications FROM disease WHERE affected_organs <> '' AND complications <> '' GROUP BY body_system HAVING AVG(CASE WHEN complications = '' THEN 0 ELSE (LENGTH(complications) - LENGTH(REPLACE(complications, '||', ''))) / 2 + 1 END) > (SELECT AVG(CASE WHEN complications = '' THEN 0 ELSE (LENGTH(complications) - LENGTH(REPLACE(complications, '||', ''))) / 2 + 1 END) FROM disease WHERE affected_organs <> '' AND complications <> '')
```
Correct answer: heart and vessels, 8, 3.63; lungs and airways, 7, 3.71; nervous system, 11, 4.09

**QX15.** Which three drug forms have the most drugs that patients with liver or kidney problems should avoid?
```sql
SELECT CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' ELSE 'other' END AS form, COUNT(*) AS drugs, SUM(CASE WHEN unsuitable_population LIKE '%liver%' OR unsuitable_population LIKE '%hepat%' OR unsuitable_population LIKE '%kidney%' OR unsuitable_population LIKE '%renal%' THEN 1 ELSE 0 END) AS avoid_liver_kidney FROM drug WHERE pharmaceutical_form <> '' GROUP BY form ORDER BY avoid_liver_kidney DESC, form LIMIT 3
```
Correct answer: tablet, 44, 13; capsule, 8, 4; other, 13, 2

**QX16.** Per kind of disease: how many diseases have epidemiology data, and in how many does it mention women, children, or older people?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease_type LIKE '%neoplastic%' THEN 'neoplastic' ELSE 'other' END AS kind, COUNT(*) AS diseases, SUM(CASE WHEN epidemiology LIKE '%women%' OR epidemiology LIKE '%female%' THEN 1 ELSE 0 END) AS mentions_women, SUM(CASE WHEN epidemiology LIKE '%child%' THEN 1 ELSE 0 END) AS mentions_children, SUM(CASE WHEN epidemiology LIKE '%elderly%' OR epidemiology LIKE '%older%' THEN 1 ELSE 0 END) AS mentions_older FROM disease WHERE disease_type <> '' AND epidemiology <> '' GROUP BY kind
```
Correct answer: infectious, 16, 2, 3, 1; neoplastic, 4, 1, 0, 3; other, 31, 8, 3, 3; psychiatric, 8, 5, 2, 1

**QX17.** Among diseases with known complications: how many of each kind (infectious, neoplastic, other) can and cannot be fatal?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%neoplastic%' THEN 'neoplastic' ELSE 'other' END AS kind, CASE WHEN complications LIKE '%death%' OR complications LIKE '%fatal%' THEN 'can be fatal' ELSE 'not fatal' END AS fatal, COUNT(*) AS diseases FROM disease WHERE disease_type <> '' AND complications <> '' GROUP BY kind, fatal
```
Correct answer: infectious, can be fatal, 2; infectious, not fatal, 11; neoplastic, not fatal, 4; other, can be fatal, 10; ... (5 rows)

**QF1.** How many drugs of each form are prescription-only, and how many are over the counter?
```sql
SELECT CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' ELSE 'other' END AS form, prescription_status, COUNT(*) AS drugs FROM drug WHERE pharmaceutical_form <> '' AND prescription_status IN ('prescription_only', 'over_the_counter') GROUP BY form, prescription_status
```
Correct answer: capsule, over_the_counter, 1; capsule, prescription_only, 4; injection, prescription_only, 5; other, over_the_counter, 1; ... (7 rows)

**QF2.** Per route of administration: how many drugs, and how many need a prescription?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 'injected' WHEN administration_route LIKE '%topical%' OR administration_route LIKE '%transdermal%' THEN 'topical' WHEN administration_route LIKE '%inhal%' OR administration_route LIKE '%nasal%' THEN 'inhaled' ELSE 'other' END AS route, COUNT(*) AS drugs, SUM(CASE WHEN prescription_status LIKE '%prescription_only%' THEN 1 ELSE 0 END) AS prescription_only FROM drug WHERE administration_route <> '' GROUP BY route
```
Correct answer: inhaled, 4, 2; injected, 11, 5; oral, 57, 30; other, 3, 1; ... (5 rows)

**QF3.** Per form: how many drugs, and how many must be refrigerated, should be taken with food, or are unsuitable in pregnancy?
```sql
SELECT CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' ELSE 'other' END AS form, COUNT(*) AS drugs, SUM(CASE WHEN storage_conditions LIKE '%refrigerat%' THEN 1 ELSE 0 END) AS refrigerated, SUM(CASE WHEN recommended_usage LIKE '%with food%' THEN 1 ELSE 0 END) AS with_food, SUM(CASE WHEN unsuitable_population LIKE '%pregnan%' THEN 1 ELSE 0 END) AS not_in_pregnancy FROM drug WHERE pharmaceutical_form <> '' GROUP BY form
```
Correct answer: capsule, 8, 1, 1, 4; injection, 11, 1, 0, 2; other, 13, 0, 1, 2; tablet, 44, 1, 4, 19

**QF4.** Per kind of disease: how many diseases, how many chronic, and how many treated with surgery?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%autoimmune%' THEN 'autoimmune' WHEN disease_type LIKE '%genetic%' THEN 'genetic' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease_type LIKE '%neoplastic%' THEN 'neoplastic' ELSE 'other' END AS kind, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic, SUM(CASE WHEN treatments LIKE '%surgery%' THEN 1 ELSE 0 END) AS surgery FROM disease WHERE disease_type <> '' GROUP BY kind
```
Correct answer: autoimmune, 5, 3, 1; genetic, 7, 2, 3; infectious, 29, 5, 3; neoplastic, 8, 0, 3; ... (6 rows)

**QF5.** Per affected organ: how many diseases, and how many of them are chronic?
```sql
SELECT CASE WHEN affected_organs LIKE '%lung%' OR affected_organs LIKE '%respirat%' THEN 'lungs' WHEN affected_organs LIKE '%skin%' THEN 'skin' WHEN affected_organs LIKE '%heart%' OR affected_organs LIKE '%cardio%' THEN 'heart' WHEN affected_organs LIKE '%brain%' OR affected_organs LIKE '%nerv%' THEN 'nervous system' ELSE 'other' END AS organ, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic FROM disease WHERE affected_organs <> '' GROUP BY organ
```
Correct answer: heart, 6, 0; lungs, 15, 1; nervous system, 17, 8; other, 32, 9; ... (5 rows)

**QF6.** Per expected outcome: how many diseases, how many have a genetic or family risk factor, and how many have any known way of prevention?
```sql
SELECT CASE WHEN prognosis LIKE '%high_mortality%' THEN 'high mortality' WHEN prognosis LIKE '%chronic%' THEN 'chronic' WHEN prognosis LIKE '%recovery%' THEN 'recovery' ELSE 'other' END AS outlook, COUNT(*) AS diseases, SUM(CASE WHEN risk_factors LIKE '%genetic%' OR risk_factors LIKE '%family_history%' THEN 1 ELSE 0 END) AS genetic_risk, SUM(CASE WHEN preventive_measures <> '' THEN 1 ELSE 0 END) AS preventable FROM disease WHERE prognosis <> '' GROUP BY outlook
```
Correct answer: chronic, 23, 5, 7; high mortality, 17, 1, 6; other, 10, 3, 6; recovery, 6, 1, 3

**QF7.** Per main treatment: how many diseases, and how many list fever as a symptom?
```sql
SELECT CASE WHEN treatments LIKE '%surgery%' THEN 'surgery' WHEN treatments LIKE '%injection%' THEN 'injection' WHEN treatments LIKE '%oral%' THEN 'oral medication' ELSE 'other' END AS treatment, COUNT(*) AS diseases, SUM(CASE WHEN common_symptoms LIKE '%fever%' THEN 1 ELSE 0 END) AS with_fever FROM disease WHERE treatments <> '' GROUP BY treatment
```
Correct answer: injection, 16, 4; oral medication, 44, 7; other, 8, 0; surgery, 21, 1

**QF8.** Per kind of disease: how many drug-disease treatment pairs are there, and in how many does the drug need a prescription?
```sql
SELECT CASE WHEN disease.disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease.disease_type LIKE '%autoimmune%' THEN 'autoimmune' WHEN disease.disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease.disease_type LIKE '%neoplastic%' THEN 'neoplastic' ELSE 'other' END AS kind, COUNT(*) AS pairs, SUM(CASE WHEN drug.prescription_status LIKE '%prescription_only%' THEN 1 ELSE 0 END) AS prescription_only FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.disease_type <> '' GROUP BY kind
```
Correct answer: autoimmune, 3, 1; infectious, 6, 3; neoplastic, 3, 0; other, 12, 8; ... (5 rows)

**QF9.** Which diseases have at least two drugs, most drugs first?
```sql
SELECT disease.disease_name, COUNT(*) AS drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' GROUP BY disease.disease_name HAVING COUNT(*) >= 2 ORDER BY drugs DESC, disease.disease_name
```
Correct answer: Depression, 4; Hypertension, 4; Asthma, 3; Diabetes Mellitus, 3; ... (9 rows)

**QF10.** How many different diseases do prescription-only and over-the-counter drugs treat?
```sql
SELECT drug.prescription_status, COUNT(DISTINCT disease.disease_name) AS diseases_treated FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE drug.prescription_status IN ('prescription_only', 'over_the_counter') GROUP BY drug.prescription_status
```
Correct answer: over_the_counter, 2; prescription_only, 9

**QF11.** Per disease prognosis: how many drug-disease treatment pairs are there, and in how many is the drug taken by mouth?
```sql
SELECT CASE WHEN disease.prognosis LIKE '%chronic%' THEN 'chronic' WHEN disease.prognosis LIKE '%high_mortality%' THEN 'high mortality' ELSE 'other' END AS outlook, COUNT(*) AS pairs, SUM(CASE WHEN drug.administration_route LIKE '%oral%' THEN 1 ELSE 0 END) AS oral_drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.prognosis <> '' GROUP BY outlook
```
Correct answer: chronic, 7, 6; high mortality, 2, 0; other, 3, 1

**QF12.** Per drug form: how many drug-disease treatment pairs involve an infectious disease, and how many another disease?
```sql
SELECT CASE WHEN drug.pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN drug.pharmaceutical_form LIKE '%injection%' THEN 'injection' ELSE 'other' END AS form, SUM(CASE WHEN disease.disease_type LIKE '%infectious%' THEN 1 ELSE 0 END) AS for_infections, SUM(CASE WHEN disease.disease_type LIKE '%infectious%' THEN 0 ELSE 1 END) AS for_other FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE drug.pharmaceutical_form <> '' AND disease.disease_type <> '' GROUP BY form
```
Correct answer: injection, 0, 3; other, 3, 4; tablet, 3, 12

**QF14.** Per dosing frequency (once, twice or three times a day): how many drugs, and how many need a prescription?
```sql
SELECT CASE WHEN dosage_frequency LIKE '%once daily%' OR dosage_frequency LIKE '%once a day%' THEN 'once a day' WHEN dosage_frequency LIKE '%twice%' THEN 'twice a day' WHEN dosage_frequency LIKE '%three times%' OR dosage_frequency LIKE '%thrice%' THEN 'three times a day' ELSE 'other' END AS frequency, COUNT(*) AS drugs, SUM(CASE WHEN prescription_status LIKE '%prescription_only%' THEN 1 ELSE 0 END) AS prescription_only FROM drug WHERE dosage_frequency <> '' GROUP BY frequency
```
Correct answer: once a day, 22, 14; other, 17, 6; three times a day, 4, 0; twice a day, 14, 8

**QF15.** Per kind of disease: how many diseases have a known diagnostic method, and how many of them are diagnosed by imaging and by laboratory tests?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%neoplastic%' THEN 'neoplastic' WHEN disease_type LIKE '%genetic%' THEN 'genetic' ELSE 'other' END AS kind, COUNT(*) AS diseases, SUM(CASE WHEN diagnostic_methods LIKE '%imaging%' THEN 1 ELSE 0 END) AS by_imaging, SUM(CASE WHEN diagnostic_methods LIKE '%laborat%' THEN 1 ELSE 0 END) AS by_lab_test FROM disease WHERE disease_type <> '' AND diagnostic_methods <> '' GROUP BY kind
```
Correct answer: genetic, 4, 0, 2; infectious, 18, 6, 11; neoplastic, 4, 3, 2; other, 28, 10, 8

## Drugs and diseases (med): build questions (40)

**QB1.** How many drugs are there for each combination of administration route and pharmaceutical form?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 'injected' WHEN administration_route LIKE '%topical%' OR administration_route LIKE '%transdermal%' THEN 'skin' WHEN administration_route LIKE '%inhal%' OR administration_route LIKE '%nasal%' THEN 'airway' ELSE 'other' END AS route, CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' WHEN pharmaceutical_form LIKE '%solution%' OR pharmaceutical_form LIKE '%suspension%' OR pharmaceutical_form LIKE '%syrup%' OR pharmaceutical_form LIKE '%liquid%' OR pharmaceutical_form LIKE '%drop%' THEN 'liquid' ELSE 'other' END AS form, COUNT(*) AS drugs FROM drug WHERE administration_route <> '' AND pharmaceutical_form <> '' GROUP BY route, form
```
Correct answer: airway, capsule, 1; airway, other, 3; injected, injection, 9; injected, liquid, 1; ... (11 rows)

**QB2.** Per dosing frequency: how many drugs, how many are taken by mouth, and how many are injected?
```sql
SELECT CASE WHEN dosage_frequency LIKE '%once daily%' OR dosage_frequency LIKE '%once a day%' THEN 'once a day' WHEN dosage_frequency LIKE '%twice%' THEN 'twice a day' WHEN dosage_frequency LIKE '%three%' OR dosage_frequency LIKE '%thrice%' OR dosage_frequency LIKE '%3%' THEN 'three or more times a day' WHEN dosage_frequency LIKE '%hour%' THEN 'every few hours' ELSE 'other' END AS frequency, COUNT(*) AS drugs, SUM(CASE WHEN administration_route LIKE '%oral%' THEN 1 ELSE 0 END) AS oral, SUM(CASE WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 1 ELSE 0 END) AS injected FROM drug WHERE dosage_frequency <> '' GROUP BY frequency
```
Correct answer: every few hours, 10, 9, 1; once a day, 22, 20, 0; other, 4, 1, 2; three or more times a day, 7, 5, 0; ... (5 rows)

**QB3.** Per pharmaceutical form: how many drugs list side effects, and how many side effects does such a drug list on average and at most?
```sql
SELECT CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' ELSE 'other' END AS form, COUNT(*) AS drugs, ROUND(AVG(CASE WHEN side_effects = '' THEN 0 ELSE (LENGTH(side_effects) - LENGTH(REPLACE(side_effects, '||', ''))) / 2 + 1 END), 2) AS avg_side_effects, MAX(CASE WHEN side_effects = '' THEN 0 ELSE (LENGTH(side_effects) - LENGTH(REPLACE(side_effects, '||', ''))) / 2 + 1 END) AS max_side_effects FROM drug WHERE pharmaceutical_form <> '' AND side_effects <> '' GROUP BY form
```
Correct answer: capsule, 7, 13.57, 21; injection, 7, 19.71, 54; other, 8, 6.75, 20; tablet, 38, 14.11, 51

**QB4.** Per administration route: how many drugs list nausea, dizziness, headache or drowsiness as a side effect?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 'injected' ELSE 'other' END AS route, SUM(CASE WHEN side_effects LIKE '%nausea%' THEN 1 ELSE 0 END) AS nausea, SUM(CASE WHEN side_effects LIKE '%dizziness%' THEN 1 ELSE 0 END) AS dizziness, SUM(CASE WHEN side_effects LIKE '%headache%' THEN 1 ELSE 0 END) AS headache, SUM(CASE WHEN side_effects LIKE '%drowsiness%' THEN 1 ELSE 0 END) AS drowsiness FROM drug WHERE administration_route <> '' GROUP BY route
```
Correct answer: injected, 1, 1, 1, 0; oral, 22, 26, 23, 11; other, 2, 3, 5, 0

**QB5.** For prescription-only and over-the-counter drugs: how many are there, how many list nausea, and how many list a rash or itching?
```sql
SELECT prescription_status, COUNT(*) AS drugs, SUM(CASE WHEN side_effects LIKE '%nausea%' THEN 1 ELSE 0 END) AS nausea, SUM(CASE WHEN side_effects LIKE '%rash%' OR side_effects LIKE '%itch%' THEN 1 ELSE 0 END) AS rash_or_itching FROM drug WHERE prescription_status IN ('prescription_only', 'over_the_counter') GROUP BY prescription_status
```
Correct answer: over_the_counter, 4, 2, 1; prescription_only, 40, 13, 12

**QB6.** Which pharmaceutical forms cover at least ten drugs, and how many of those drugs need a prescription?
```sql
SELECT CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' WHEN pharmaceutical_form LIKE '%solution%' OR pharmaceutical_form LIKE '%suspension%' THEN 'liquid' ELSE 'other' END AS form, COUNT(*) AS drugs, SUM(CASE WHEN prescription_status LIKE '%prescription_only%' THEN 1 ELSE 0 END) AS prescription_only FROM drug WHERE pharmaceutical_form <> '' GROUP BY form HAVING COUNT(*) >= 10
```
Correct answer: injection, 11, 6; other, 10, 3; tablet, 44, 25

**QB7.** Per administration route: how many drugs are there, and how many of them list nausea as a side effect?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' THEN 'intravenous' WHEN administration_route LIKE '%subcutaneous%' THEN 'subcutaneous' WHEN administration_route LIKE '%topical%' THEN 'topical' WHEN administration_route LIKE '%inhal%' THEN 'inhalation' ELSE 'other' END AS route, COUNT(*) AS drugs, SUM(CASE WHEN side_effects LIKE '%nausea%' THEN 1 ELSE 0 END) AS drugs_with_nausea FROM drug WHERE administration_route <> '' GROUP BY route
```
Correct answer: inhalation, 3, 0; intravenous, 6, 1; oral, 57, 22; other, 5, 1; ... (6 rows)

**QB8.** Per administration route: how many drugs come in more than one pharmaceutical form?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 'injected' ELSE 'other' END AS route, COUNT(*) AS drugs, SUM(CASE WHEN pharmaceutical_form LIKE '%||%' THEN 1 ELSE 0 END) AS several_forms FROM drug WHERE administration_route <> '' AND pharmaceutical_form <> '' GROUP BY route
```
Correct answer: injected, 11, 2; oral, 52, 17; other, 11, 3

**QB9.** How many prescription-only drugs are taken once a day?
```sql
SELECT COUNT(*) AS drugs FROM drug WHERE prescription_status LIKE '%prescription_only%' AND (dosage_frequency LIKE '%once daily%' OR dosage_frequency LIKE '%once a day%')
```
Correct answer: 14

**QB10.** Per disease area a drug is meant for: how many drugs, how many are taken by mouth, and how many need a prescription?
```sql
SELECT CASE WHEN disease_name LIKE '%cancer%' OR disease_name LIKE '%tumo%' OR disease_name LIKE '%lymphoma%' OR disease_name LIKE '%leukemia%' OR disease_name LIKE '%myeloma%' THEN 'cancer' WHEN disease_name LIKE '%infect%' OR disease_name LIKE '%pneumonia%' OR disease_name LIKE '%tuberculosis%' OR disease_name LIKE '%bronchitis%' OR disease_name LIKE '%hepatitis%' OR disease_name LIKE '%herpes%' OR disease_name LIKE '%HIV%' THEN 'infection' WHEN disease_name LIKE '%depress%' OR disease_name LIKE '%anxiety%' OR disease_name LIKE '%panic%' OR disease_name LIKE '%attention deficit%' THEN 'mental health' WHEN disease_name LIKE '%diabet%' THEN 'diabetes' WHEN disease_name LIKE '%hypertension%' OR disease_name LIKE '%heart%' OR disease_name LIKE '%cardio%' OR disease_name LIKE '%angina%' THEN 'heart and blood pressure' ELSE 'other' END AS area, COUNT(*) AS drugs, SUM(CASE WHEN administration_route LIKE '%oral%' THEN 1 ELSE 0 END) AS oral, SUM(CASE WHEN prescription_status LIKE '%prescription_only%' THEN 1 ELSE 0 END) AS prescription_only FROM drug WHERE disease_name <> '' GROUP BY area
```
Correct answer: cancer, 11, 3, 2; diabetes, 5, 3, 4; heart and blood pressure, 8, 6, 6; infection, 19, 15, 8; ... (6 rows)

**QB11.** Per disease area a drug is meant for: how many side effects does a drug list on average?
```sql
SELECT CASE WHEN disease_name LIKE '%cancer%' OR disease_name LIKE '%tumo%' OR disease_name LIKE '%lymphoma%' OR disease_name LIKE '%leukemia%' OR disease_name LIKE '%myeloma%' THEN 'cancer' WHEN disease_name LIKE '%infect%' OR disease_name LIKE '%pneumonia%' OR disease_name LIKE '%tuberculosis%' OR disease_name LIKE '%bronchitis%' OR disease_name LIKE '%hepatitis%' OR disease_name LIKE '%herpes%' OR disease_name LIKE '%HIV%' THEN 'infection' WHEN disease_name LIKE '%depress%' OR disease_name LIKE '%anxiety%' OR disease_name LIKE '%panic%' OR disease_name LIKE '%attention deficit%' THEN 'mental health' ELSE 'other' END AS area, COUNT(*) AS drugs, ROUND(AVG(CASE WHEN side_effects = '' THEN 0 ELSE (LENGTH(side_effects) - LENGTH(REPLACE(side_effects, '||', ''))) / 2 + 1 END), 2) AS avg_side_effects FROM drug WHERE disease_name <> '' AND side_effects <> '' GROUP BY area
```
Correct answer: cancer, 8, 10.75; infection, 17, 14.29; mental health, 8, 15.13; other, 41, 12.15

**QB12.** Which disease areas have at least ten drugs, and how many of them are tablets?
```sql
SELECT CASE WHEN disease_name LIKE '%cancer%' OR disease_name LIKE '%tumo%' OR disease_name LIKE '%lymphoma%' OR disease_name LIKE '%leukemia%' OR disease_name LIKE '%myeloma%' THEN 'cancer' WHEN disease_name LIKE '%infect%' OR disease_name LIKE '%pneumonia%' OR disease_name LIKE '%tuberculosis%' OR disease_name LIKE '%bronchitis%' OR disease_name LIKE '%hepatitis%' OR disease_name LIKE '%herpes%' OR disease_name LIKE '%HIV%' THEN 'infection' WHEN disease_name LIKE '%depress%' OR disease_name LIKE '%anxiety%' OR disease_name LIKE '%panic%' OR disease_name LIKE '%attention deficit%' THEN 'mental health' WHEN disease_name LIKE '%diabet%' THEN 'diabetes' WHEN disease_name LIKE '%hypertension%' OR disease_name LIKE '%heart%' OR disease_name LIKE '%cardio%' OR disease_name LIKE '%angina%' THEN 'heart and blood pressure' ELSE 'other' END AS area, COUNT(*) AS drugs, SUM(CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 1 ELSE 0 END) AS tablets FROM drug WHERE disease_name <> '' GROUP BY area HAVING COUNT(*) >= 10
```
Correct answer: cancer, 11, 3; infection, 19, 13; other, 44, 15

**QB13.** Per disease area a drug is meant for: how many drugs are taken once a day and how many more often?
```sql
SELECT CASE WHEN disease_name LIKE '%infect%' OR disease_name LIKE '%pneumonia%' OR disease_name LIKE '%tuberculosis%' OR disease_name LIKE '%bronchitis%' OR disease_name LIKE '%hepatitis%' OR disease_name LIKE '%herpes%' OR disease_name LIKE '%HIV%' THEN 'infection' WHEN disease_name LIKE '%depress%' OR disease_name LIKE '%anxiety%' OR disease_name LIKE '%panic%' OR disease_name LIKE '%attention deficit%' THEN 'mental health' ELSE 'other' END AS area, SUM(CASE WHEN dosage_frequency LIKE '%once daily%' OR dosage_frequency LIKE '%once a day%' THEN 1 ELSE 0 END) AS once_a_day, SUM(CASE WHEN dosage_frequency LIKE '%twice%' OR dosage_frequency LIKE '%three%' OR dosage_frequency LIKE '%hours%' THEN 1 ELSE 0 END) AS more_often FROM drug WHERE disease_name <> '' AND dosage_frequency <> '' GROUP BY area
```
Correct answer: infection, 4, 12; mental health, 3, 1; other, 15, 19

**QB14.** For prescription-only and over-the-counter drugs: how many are sold under a brand name and how many only under a generic name?
```sql
SELECT prescription_status, SUM(CASE WHEN brand_name <> '' THEN 1 ELSE 0 END) AS branded, SUM(CASE WHEN brand_name = '' AND generic_name <> '' THEN 1 ELSE 0 END) AS generic_only FROM drug WHERE prescription_status IN ('prescription_only', 'over_the_counter') GROUP BY prescription_status
```
Correct answer: over_the_counter, 4, 0; prescription_only, 35, 5

**QB15.** Per drug class recognisable from the generic name (antibiotics, antibodies, acid reducers, heart and cholesterol drugs): how many drugs are there, and how many are taken by mouth?
```sql
SELECT CASE WHEN generic_name LIKE '%cillin%' OR generic_name LIKE '%mycin%' OR generic_name LIKE '%cycline%' OR generic_name LIKE '%floxacin%' OR generic_name LIKE '%sulfa%' THEN 'antibiotic' WHEN generic_name LIKE '%mab%' OR generic_name LIKE '%cept%' THEN 'antibody' WHEN generic_name LIKE '%prazole%' OR generic_name LIKE '%tidine%' THEN 'acid reducer' WHEN generic_name LIKE '%olol%' OR generic_name LIKE '%dipine%' OR generic_name LIKE '%pril%' OR generic_name LIKE '%sartan%' OR generic_name LIKE '%statin%' THEN 'heart and cholesterol' ELSE 'other' END AS drug_class, COUNT(*) AS drugs, SUM(CASE WHEN administration_route LIKE '%oral%' THEN 1 ELSE 0 END) AS oral FROM drug WHERE generic_name <> '' GROUP BY drug_class
```
Correct answer: acid reducer, 4, 4; antibiotic, 7, 4; antibody, 3, 0; heart and cholesterol, 3, 3; ... (5 rows)

**QB16.** Per administration route: how many drugs are there, how many have a brand name, and how many are known only by a generic name?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 'injected' ELSE 'other' END AS route, COUNT(*) AS drugs, SUM(CASE WHEN brand_name <> '' THEN 1 ELSE 0 END) AS branded, SUM(CASE WHEN brand_name = '' AND generic_name <> '' THEN 1 ELSE 0 END) AS generic_only FROM drug WHERE administration_route <> '' GROUP BY route
```
Correct answer: injected, 11, 5, 6; oral, 57, 45, 12; other, 11, 9, 2

**QB17.** Per administration route: how many drugs list a serious side effect (bleeding, seizures, liver or kidney damage, or anaphylaxis)?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 'injected' ELSE 'other' END AS route, COUNT(*) AS drugs, SUM(CASE WHEN side_effects LIKE '%bleed%' OR side_effects LIKE '%seizure%' OR side_effects LIKE '%hepat%' OR side_effects LIKE '%liver%' OR side_effects LIKE '%renal%' OR side_effects LIKE '%kidney%' OR side_effects LIKE '%anaphyla%' THEN 1 ELSE 0 END) AS serious FROM drug WHERE administration_route <> '' GROUP BY route
```
Correct answer: injected, 11, 2; oral, 57, 19; other, 11, 0

**QB19.** Which administration routes list more side effects per drug on average than drugs overall?
```sql
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'oral' WHEN administration_route LIKE '%intravenous%' OR administration_route LIKE '%subcutaneous%' OR administration_route LIKE '%intramuscular%' OR administration_route LIKE '%injection%' THEN 'injected' ELSE 'other' END AS route, COUNT(*) AS drugs, ROUND(AVG(CASE WHEN side_effects = '' THEN 0 ELSE (LENGTH(side_effects) - LENGTH(REPLACE(side_effects, '||', ''))) / 2 + 1 END), 2) AS avg_side_effects FROM drug WHERE administration_route <> '' AND side_effects <> '' GROUP BY route HAVING AVG(CASE WHEN side_effects = '' THEN 0 ELSE (LENGTH(side_effects) - LENGTH(REPLACE(side_effects, '||', ''))) / 2 + 1 END) > (SELECT AVG(CASE WHEN side_effects = '' THEN 0 ELSE (LENGTH(side_effects) - LENGTH(REPLACE(side_effects, '||', ''))) / 2 + 1 END) FROM drug WHERE side_effects <> '')
```
Correct answer: injected, 7, 18.29; oral, 48, 14.17

**QB20.** Per pharmaceutical form: how many drugs list gastrointestinal side effects (nausea, vomiting, diarrhea or constipation) and how many list sleep-related ones (drowsiness, insomnia or fatigue)?
```sql
SELECT CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' ELSE 'other' END AS form, SUM(CASE WHEN side_effects LIKE '%nausea%' OR side_effects LIKE '%vomit%' OR side_effects LIKE '%diarrh%' OR side_effects LIKE '%constipation%' THEN 1 ELSE 0 END) AS gastrointestinal, SUM(CASE WHEN side_effects LIKE '%drows%' OR side_effects LIKE '%insomnia%' OR side_effects LIKE '%fatigue%' THEN 1 ELSE 0 END) AS sleep_related FROM drug WHERE pharmaceutical_form <> '' GROUP BY form
```
Correct answer: capsule, 4, 1; injection, 1, 2; other, 3, 2; tablet, 23, 17

**QB21.** Per disease mechanism: how many diseases, how many are treated with oral medication, and how many with surgery?
```sql
SELECT CASE WHEN pathogenesis LIKE '%infectious_bacterial%' THEN 'bacterial' WHEN pathogenesis LIKE '%infectious_viral%' THEN 'viral' WHEN pathogenesis LIKE '%infectious_parasitic%' OR pathogenesis LIKE '%infectious_fungal%' THEN 'parasitic or fungal' WHEN pathogenesis LIKE '%genetic%' THEN 'genetic' WHEN pathogenesis LIKE '%autoimmune%' THEN 'autoimmune' WHEN pathogenesis LIKE '%neoplastic%' THEN 'neoplastic' WHEN pathogenesis LIKE '%inflammatory%' THEN 'inflammatory' ELSE 'other' END AS mechanism, COUNT(*) AS diseases, SUM(CASE WHEN treatments LIKE '%oral_medication%' THEN 1 ELSE 0 END) AS oral_medication, SUM(CASE WHEN treatments LIKE '%surgery%' THEN 1 ELSE 0 END) AS surgery FROM disease WHERE pathogenesis <> '' GROUP BY mechanism
```
Correct answer: autoimmune, 5, 4, 2; bacterial, 17, 14, 2; genetic, 9, 6, 4; inflammatory, 13, 9, 3; ... (8 rows)

**QB22.** Per disease mechanism: how many diseases are diagnosed by clinical evaluation, by laboratory tests, and by imaging?
```sql
SELECT CASE WHEN pathogenesis LIKE '%infectious%' THEN 'infectious' WHEN pathogenesis LIKE '%genetic%' THEN 'genetic' WHEN pathogenesis LIKE '%neoplastic%' THEN 'neoplastic' WHEN pathogenesis LIKE '%inflammatory%' OR pathogenesis LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS mechanism, SUM(CASE WHEN diagnostic_methods LIKE '%clinical_evaluation%' THEN 1 ELSE 0 END) AS clinical_evaluation, SUM(CASE WHEN diagnostic_methods LIKE '%laboratory_test%' THEN 1 ELSE 0 END) AS laboratory_test, SUM(CASE WHEN diagnostic_methods LIKE '%imaging%' THEN 1 ELSE 0 END) AS imaging FROM disease WHERE pathogenesis <> '' GROUP BY mechanism
```
Correct answer: genetic, 4, 2, 0; infectious, 13, 11, 6; inflammatory or autoimmune, 11, 4, 4; neoplastic, 2, 2, 3; ... (5 rows)

**QB23.** Per main diagnostic approach: how many diseases, how many are chronic, and how many carry a high mortality?
```sql
SELECT CASE WHEN diagnostic_methods LIKE '%biopsy%' OR diagnostic_methods LIKE '%endoscopy%' OR diagnostic_methods LIKE '%pathology%' THEN 'biopsy or endoscopy' WHEN diagnostic_methods LIKE '%imaging%' THEN 'imaging' WHEN diagnostic_methods LIKE '%laboratory_test%' THEN 'laboratory test' ELSE 'clinical evaluation or other' END AS approach, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic, SUM(CASE WHEN prognosis LIKE '%high_mortality%' THEN 1 ELSE 0 END) AS high_mortality FROM disease WHERE diagnostic_methods <> '' GROUP BY approach
```
Correct answer: biopsy or endoscopy, 5, 1, 1; clinical evaluation or other, 21, 8, 2; imaging, 17, 7, 5; laboratory test, 13, 3, 3

**QB24.** Per expected outcome: how many diseases, and how many treatment modalities does such a disease have on average?
```sql
SELECT CASE WHEN prognosis LIKE '%high_mortality%' THEN 'high mortality' WHEN prognosis LIKE '%chronic%' THEN 'chronic' WHEN prognosis LIKE '%recovery%' THEN 'recovery' ELSE 'other' END AS outlook, COUNT(*) AS diseases, ROUND(AVG(CASE WHEN treatments = '' THEN 0 ELSE (LENGTH(treatments) - LENGTH(REPLACE(treatments, '||', ''))) / 2 + 1 END), 2) AS avg_treatments FROM disease WHERE prognosis <> '' AND treatments <> '' GROUP BY outlook
```
Correct answer: chronic, 23, 3.17; high mortality, 15, 2.13; other, 10, 2.0; recovery, 6, 2.33

**QB25.** Per kind of disease: how many diseases report an impact on quality of life, how many cause chronic pain, and how many cause fatigue?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease_type LIKE '%neoplastic%' THEN 'neoplastic' WHEN disease_type LIKE '%autoimmune%' OR disease_type LIKE '%inflammatory%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS kind, COUNT(*) AS diseases, SUM(CASE WHEN quality_of_life_impact LIKE '%chronic_pain%' THEN 1 ELSE 0 END) AS chronic_pain, SUM(CASE WHEN quality_of_life_impact LIKE '%fatigue%' THEN 1 ELSE 0 END) AS fatigue FROM disease WHERE disease_type <> '' AND quality_of_life_impact <> '' GROUP BY kind
```
Correct answer: infectious, 11, 2, 1; inflammatory or autoimmune, 12, 5, 4; neoplastic, 5, 0, 1; other, 13, 7, 1; ... (5 rows)

**QB26.** Per main effect on daily life: how many diseases, and how many of them are chronic?
```sql
SELECT CASE WHEN quality_of_life_impact LIKE '%pain%' THEN 'pain' WHEN quality_of_life_impact LIKE '%anxiety%' OR quality_of_life_impact LIKE '%depression%' OR quality_of_life_impact LIKE '%emotional%' THEN 'emotional' WHEN quality_of_life_impact LIKE '%social%' OR quality_of_life_impact LIKE '%stigma%' THEN 'social' WHEN quality_of_life_impact LIKE '%fatigue%' THEN 'fatigue' WHEN quality_of_life_impact LIKE '%diet%' THEN 'diet' ELSE 'general decline or other' END AS effect, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic FROM disease WHERE quality_of_life_impact <> '' GROUP BY effect
```
Correct answer: diet, 2, 0; emotional, 10, 3; fatigue, 4, 2; general decline or other, 18, 6; ... (6 rows)

**QB27.** Per kind of prevention: how many diseases, and how many of them are infectious?
```sql
SELECT CASE WHEN preventive_measures LIKE '%vaccin%' THEN 'vaccination' WHEN preventive_measures LIKE '%screening%' OR preventive_measures LIKE '%early_detection%' THEN 'screening' WHEN preventive_measures LIKE '%lifestyle%' OR preventive_measures LIKE '%diet%' OR preventive_measures LIKE '%exercise%' THEN 'lifestyle and diet' ELSE 'other' END AS prevention, COUNT(*) AS diseases, SUM(CASE WHEN disease_type LIKE '%infectious%' THEN 1 ELSE 0 END) AS infectious FROM disease WHERE preventive_measures <> '' GROUP BY prevention
```
Correct answer: lifestyle and diet, 15, 3; other, 4, 2; screening, 9, 1; vaccination, 4, 4

**QB28.** Per kind of disease: how many diseases, and how many have any known way of prevention?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease_type LIKE '%neoplastic%' THEN 'neoplastic' WHEN disease_type LIKE '%metabolic%' OR disease_type LIKE '%endocrine%' THEN 'metabolic or endocrine' WHEN disease_type LIKE '%vascular%' THEN 'vascular' ELSE 'other' END AS kind, COUNT(*) AS diseases, SUM(CASE WHEN preventive_measures <> '' THEN 1 ELSE 0 END) AS preventable FROM disease WHERE disease_type <> '' GROUP BY kind
```
Correct answer: infectious, 29, 10; metabolic or endocrine, 9, 5; neoplastic, 8, 1; other, 25, 6; ... (6 rows)

**QB29.** Grouping each disease by its main treatment (cancer therapy first, then surgery, injection, oral medication, lifestyle and diet), which groups contain at least ten diseases, and how many of those diseases are chronic?
```sql
SELECT CASE WHEN treatments LIKE '%chemotherapy%' OR treatments LIKE '%radiotherapy%' THEN 'cancer therapy' WHEN treatments LIKE '%surgery%' THEN 'surgery' WHEN treatments LIKE '%injection%' THEN 'injection' WHEN treatments LIKE '%oral_medication%' THEN 'oral medication' WHEN treatments LIKE '%lifestyle%' OR treatments LIKE '%diet%' THEN 'lifestyle and diet' ELSE 'other' END AS treatment, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic FROM disease WHERE treatments <> '' GROUP BY treatment HAVING COUNT(*) >= 10
```
Correct answer: injection, 15, 4; oral medication, 43, 8; surgery, 18, 9

**QB30.** Per main treatment challenge: how many diseases, and how many of them are infectious?
```sql
SELECT CASE WHEN treatment_challenges LIKE '%resist%' THEN 'drug resistance' WHEN treatment_challenges LIKE '%side%effect%' THEN 'side effects' WHEN treatment_challenges LIKE '%relapse%' OR treatment_challenges LIKE '%adherence%' OR treatment_challenges LIKE '%recurrence%' THEN 'relapse or adherence' WHEN treatment_challenges LIKE '%cost%' OR treatment_challenges LIKE '%insurance%' OR treatment_challenges LIKE '%access%' OR treatment_challenges LIKE '%financial%' THEN 'cost or access' ELSE 'other' END AS challenge, COUNT(*) AS diseases, SUM(CASE WHEN disease_type LIKE '%infectious%' THEN 1 ELSE 0 END) AS infectious FROM disease WHERE treatment_challenges <> '' GROUP BY challenge
```
Correct answer: cost or access, 6, 1; drug resistance, 4, 3; other, 16, 4; relapse or adherence, 7, 1; ... (5 rows)

**QB31.** Per disease mechanism: how many diseases mention drug resistance and how many mention side effects as a treatment challenge?
```sql
SELECT CASE WHEN pathogenesis LIKE '%infectious%' THEN 'infectious' WHEN pathogenesis LIKE '%inflammatory%' OR pathogenesis LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS mechanism, COUNT(*) AS diseases, SUM(CASE WHEN treatment_challenges LIKE '%resist%' THEN 1 ELSE 0 END) AS drug_resistance, SUM(CASE WHEN treatment_challenges LIKE '%side%effect%' THEN 1 ELSE 0 END) AS side_effects FROM disease WHERE pathogenesis <> '' GROUP BY mechanism
```
Correct answer: infectious, 27, 3, 3; inflammatory or autoimmune, 21, 1, 5; other, 32, 0, 4

**QB32.** Per disease group by name (cancers, diabetes, infections, mental health): how many diseases, how many carry a high mortality, and how many are treated with chemotherapy?
```sql
SELECT CASE WHEN disease_name LIKE '%cancer%' OR disease_name LIKE '%myeloma%' OR disease_name LIKE '%tumo%' THEN 'cancer' WHEN disease_name LIKE '%diabet%' THEN 'diabetes' WHEN disease_name LIKE '%infection%' OR disease_name LIKE '%tuberculosis%' OR disease_name LIKE '%influenza%' OR disease_name LIKE '%COVID%' OR disease_name LIKE '%HIV%' OR disease_name LIKE '%chlamydia%' THEN 'infection' WHEN disease_name LIKE '%depress%' OR disease_name LIKE '%anxiety%' OR disease_name LIKE '%panic%' OR disease_name LIKE '%addiction%' OR disease_name LIKE '%opioid%' THEN 'mental health and addiction' ELSE 'other' END AS disease_group, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%high_mortality%' THEN 1 ELSE 0 END) AS high_mortality, SUM(CASE WHEN treatments LIKE '%chemotherapy%' THEN 1 ELSE 0 END) AS chemotherapy FROM disease GROUP BY disease_group
```
Correct answer: cancer, 8, 4, 7; diabetes, 4, 0, 0; infection, 11, 1, 0; mental health and addiction, 9, 0, 0; ... (5 rows)

**QB33.** Which three disease mechanisms (other than unclassified ones) account for the most chronic diseases?
```sql
SELECT CASE WHEN pathogenesis LIKE '%infectious%' THEN 'infectious' WHEN pathogenesis LIKE '%genetic%' THEN 'genetic' WHEN pathogenesis LIKE '%autoimmune%' THEN 'autoimmune' WHEN pathogenesis LIKE '%neoplastic%' THEN 'neoplastic' WHEN pathogenesis LIKE '%inflammatory%' THEN 'inflammatory' WHEN pathogenesis LIKE '%degenerative%' THEN 'degenerative' ELSE 'other' END AS mechanism, COUNT(*) AS chronic_diseases FROM disease WHERE pathogenesis <> '' AND prognosis LIKE '%chronic%' GROUP BY mechanism HAVING mechanism <> 'other' ORDER BY chronic_diseases DESC, mechanism LIMIT 3
```
Correct answer: infectious, 5; autoimmune, 4; inflammatory, 4

**QB34.** How many infectious and non-infectious diseases are treated mainly with surgery, injections, or oral medication?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' ELSE 'not infectious' END AS kind, CASE WHEN treatments LIKE '%surgery%' THEN 'surgery' WHEN treatments LIKE '%injection%' THEN 'injection' WHEN treatments LIKE '%oral_medication%' THEN 'oral medication' ELSE 'other' END AS treatment, COUNT(*) AS diseases FROM disease WHERE disease_type <> '' AND treatments <> '' GROUP BY kind, treatment
```
Correct answer: infectious, injection, 6; infectious, oral medication, 15; infectious, other, 3; infectious, surgery, 3; ... (8 rows)

**QB35.** Which kinds of disease have more treatment modalities on average than diseases overall?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease_type LIKE '%neoplastic%' THEN 'neoplastic' WHEN disease_type LIKE '%metabolic%' OR disease_type LIKE '%endocrine%' THEN 'metabolic or endocrine' WHEN disease_type LIKE '%vascular%' THEN 'vascular' ELSE 'other' END AS kind, COUNT(*) AS diseases, ROUND(AVG(CASE WHEN treatments = '' THEN 0 ELSE (LENGTH(treatments) - LENGTH(REPLACE(treatments, '||', ''))) / 2 + 1 END), 2) AS avg_treatments FROM disease WHERE disease_type <> '' AND treatments <> '' GROUP BY kind HAVING AVG(CASE WHEN treatments = '' THEN 0 ELSE (LENGTH(treatments) - LENGTH(REPLACE(treatments, '||', ''))) / 2 + 1 END) > (SELECT AVG(CASE WHEN treatments = '' THEN 0 ELSE (LENGTH(treatments) - LENGTH(REPLACE(treatments, '||', ''))) / 2 + 1 END) FROM disease WHERE treatments <> '')
```
Correct answer: metabolic or endocrine, 9, 3.56; neoplastic, 8, 2.63; psychiatric, 8, 2.75; vascular, 7, 2.86

**QB36.** Per expected outcome: how many diseases can be prevented by lifestyle or diet changes, and how many are treated with a dietary intervention?
```sql
SELECT CASE WHEN prognosis LIKE '%high_mortality%' THEN 'high mortality' WHEN prognosis LIKE '%chronic%' THEN 'chronic' WHEN prognosis LIKE '%recovery%' THEN 'recovery' ELSE 'other' END AS outlook, COUNT(*) AS diseases, SUM(CASE WHEN preventive_measures LIKE '%lifestyle%' OR preventive_measures LIKE '%diet%' THEN 1 ELSE 0 END) AS lifestyle_prevention, SUM(CASE WHEN treatments LIKE '%dietary_intervention%' THEN 1 ELSE 0 END) AS dietary_treatment FROM disease WHERE prognosis <> '' GROUP BY outlook
```
Correct answer: chronic, 23, 7, 9; high mortality, 17, 2, 1; other, 10, 4, 3; recovery, 6, 1, 1

**QB37.** Per disease mechanism: how many drug-disease treatment pairs are there, and in how many of them is the drug a tablet?
```sql
SELECT CASE WHEN disease.pathogenesis LIKE '%infectious%' THEN 'infectious' WHEN disease.pathogenesis LIKE '%inflammatory%' OR disease.pathogenesis LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS mechanism, COUNT(*) AS pairs, SUM(CASE WHEN drug.pharmaceutical_form LIKE '%tablet%' THEN 1 ELSE 0 END) AS tablets FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.pathogenesis <> '' GROUP BY mechanism
```
Correct answer: infectious, 6, 3; inflammatory or autoimmune, 6, 2; other, 14, 7

**QB38.** For oral drugs and drugs given another way: how many different diseases do they treat, and how many drug-disease treatment pairs are there?
```sql
SELECT CASE WHEN drug.administration_route LIKE '%oral%' THEN 'oral' ELSE 'not oral' END AS route, COUNT(DISTINCT disease.disease_name) AS diseases, COUNT(*) AS pairs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE drug.administration_route <> '' GROUP BY route
```
Correct answer: not oral, 7, 9; oral, 12, 19

**QB39.** For chronic and non-chronic diseases (with a known outlook): how many drug-disease treatment pairs are there, and how many side effects do those drugs list on average?
```sql
SELECT CASE WHEN disease.prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'not chronic' END AS course, COUNT(*) AS pairs, ROUND(AVG(CASE WHEN drug.side_effects = '' THEN 0 ELSE (LENGTH(drug.side_effects) - LENGTH(REPLACE(drug.side_effects, '||', ''))) / 2 + 1 END), 2) AS avg_side_effects FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.prognosis <> '' AND drug.side_effects <> '' GROUP BY course
```
Correct answer: chronic, 7, 6.71; not chronic, 3, 3.33

**QB40.** Per main treatment of the disease: how many drug-disease treatment pairs are there, and in how many is the drug taken once a day?
```sql
SELECT CASE WHEN disease.treatments LIKE '%injection%' THEN 'injection' WHEN disease.treatments LIKE '%oral_medication%' THEN 'oral medication' ELSE 'other' END AS treatment, COUNT(*) AS pairs, SUM(CASE WHEN drug.dosage_frequency LIKE '%once daily%' OR drug.dosage_frequency LIKE '%once a day%' THEN 1 ELSE 0 END) AS once_a_day FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.treatments <> '' GROUP BY treatment
```
Correct answer: injection, 3, 1; oral medication, 14, 3; other, 7, 2

**QB41.** How many infectious and non-infectious diseases are there for each expected outcome (high mortality, chronic, or other)?
```sql
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' ELSE 'not infectious' END AS kind, CASE WHEN prognosis LIKE '%high_mortality%' THEN 'high mortality' WHEN prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'other' END AS outlook, COUNT(*) AS diseases FROM disease WHERE disease_type <> '' AND prognosis <> '' GROUP BY kind, outlook
```
Correct answer: infectious, chronic, 5; infectious, high mortality, 4; infectious, other, 6; not infectious, chronic, 18; ... (6 rows)

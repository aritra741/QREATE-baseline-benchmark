"""CSPaper contrast workloads: realistic IR / RAG researcher questions."""

from .common import q

DATASET = "CSPaper"
JOIN_NOTES = None
BASELINE = "cspaper_agg20"

RETRIEVAL_FAMILY = """
CASE
  WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid'
  WHEN retrieval_method LIKE '%Graph-based%' THEN 'Graph-based'
  WHEN retrieval_method LIKE '%Dense%' THEN 'Dense'
  WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse'
  WHEN retrieval_method LIKE '%Web Search%' THEN 'Web Search'
  WHEN retrieval_method != '' THEN 'Other'
END
""".strip()

DOMAIN_FAMILY = """
CASE
  WHEN application_domain LIKE '%Medical%' THEN 'Medical'
  WHEN application_domain LIKE '%Education%' THEN 'Education'
  WHEN application_domain LIKE '%Finance%' THEN 'Finance'
  WHEN application_domain LIKE '%Academic%' THEN 'Academic'
  WHEN application_domain LIKE '%General%' THEN 'General'
  WHEN application_domain != '' THEN 'Other'
END
""".strip()

MODALITY_FAMILY = """
CASE
  WHEN data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' OR data_modality LIKE '%Table%' OR data_modality LIKE '%Code%' THEN 'multimodal_or_structured'
  WHEN data_modality LIKE '%Text%' THEN 'text_only'
  WHEN data_modality != '' THEN 'Other'
END
""".strip()

WORKLOADS = {
    "cspaper_agg20": {
        "title": "Simple aggregation workload",
        "focus": "Single-table GROUP BY with one aggregate",
        "kind": "baseline",
        "queries": [
            q("q0", "SELECT reasoning_depth, COUNT(*) AS paper_count FROM cspaper WHERE reasoning_depth IN ('single-hop', 'multi-hop') GROUP BY reasoning_depth", "How many papers target single-hop versus multi-hop reasoning?"),
            q("q1", "SELECT uses_reranker, COUNT(*) AS paper_count FROM cspaper WHERE uses_reranker IN ('Yes', 'No') GROUP BY uses_reranker", "How many papers use an explicit reranker versus not?"),
            q("q2", "SELECT use_agent, COUNT(*) AS paper_count FROM cspaper WHERE use_agent IN ('Yes', 'No') GROUP BY use_agent", "How many papers use an agent-style architecture versus not?"),
            q("q3", "SELECT multi_turn_retrieval, COUNT(*) AS paper_count FROM cspaper WHERE multi_turn_retrieval IN ('Yes', 'No') GROUP BY multi_turn_retrieval", "How many papers support multi-turn retrieval versus not?"),
            q("q4", "SELECT uses_knowledge_graph, COUNT(*) AS paper_count FROM cspaper WHERE uses_knowledge_graph IN ('Yes', 'No') GROUP BY uses_knowledge_graph", "How many papers incorporate a knowledge graph versus not?"),
            q("q5", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method != '' GROUP BY retrieval_family", "How many papers use each family of retrieval method?"),
            q("q6", f"SELECT {DOMAIN_FAMILY} AS domain_family, COUNT(*) AS paper_count FROM cspaper WHERE application_domain != '' GROUP BY domain_family", "How many papers target each application-domain family?"),
            q("q7", f"SELECT {MODALITY_FAMILY} AS modality_family, COUNT(*) AS paper_count FROM cspaper WHERE data_modality != '' GROUP BY modality_family", "How many papers handle text-only inputs versus multimodal or structured inputs?"),
            q("q8", "SELECT reasoning_depth, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE reasoning_depth IN ('single-hop', 'multi-hop') AND baseline_amount IS NOT NULL GROUP BY reasoning_depth", "What is the average number of baselines compared in single-hop versus multi-hop papers?"),
            q("q9", "SELECT use_agent, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE use_agent IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY use_agent", "What is the average number of baselines in agent-based versus non-agent papers?"),
            q("q10", "SELECT uses_reranker, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY uses_reranker", "What is the average number of baselines in papers that use a reranker versus those that do not?"),
            q("q11", "SELECT agent_framework, COUNT(*) AS paper_count FROM cspaper WHERE agent_framework IN ('CoT', 'ToT', 'Multi-Agent Collaboration', 'Other') GROUP BY agent_framework", "Among papers that name an agent framework, how many use each framework?"),
            q("q12", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE retrieval_method != '' AND baseline_amount IS NOT NULL GROUP BY retrieval_family", "What is the average number of baselines for each retrieval-method family?"),
            q("q13", "SELECT multi_turn_retrieval, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE multi_turn_retrieval IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY multi_turn_retrieval", "What is the largest number of baselines reported among multi-turn versus single-turn retrieval papers?"),
            q("q14", f"SELECT {DOMAIN_FAMILY} AS domain_family, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE application_domain != '' AND baseline_amount IS NOT NULL GROUP BY domain_family", "What is the average number of baselines for papers in each application-domain family?"),
            q("q15", "SELECT uses_knowledge_graph, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE uses_knowledge_graph IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY uses_knowledge_graph", "What is the largest baseline count among papers that use a knowledge graph versus those that do not?"),
            q("q16", "SELECT topic, COUNT(*) AS paper_count FROM cspaper WHERE topic != '' GROUP BY topic", "How many papers are labeled with each research topic?"),
            q("q17", f"SELECT {MODALITY_FAMILY} AS modality_family, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE data_modality != '' AND baseline_amount IS NOT NULL GROUP BY modality_family", "What is the average number of baselines in text-only versus multimodal or structured papers?"),
            q("q18", "SELECT use_agent, SUM(baseline_amount) AS total_baselines FROM cspaper WHERE use_agent IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY use_agent", "What is the total number of baselines compared across agent-based versus non-agent papers?"),
            q("q19", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE retrieval_method != '' AND baseline_amount IS NOT NULL GROUP BY retrieval_family", "What is the largest baseline count reported for each retrieval-method family?"),
        ],
    },
    "cspaper_filter20": {
        "title": "Selective-filter workload",
        "focus": "Selective WHERE predicates with simple aggregates",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", "SELECT use_agent, COUNT(*) AS paper_count FROM cspaper WHERE reasoning_depth = 'multi-hop' AND uses_reranker IN ('Yes', 'No') AND use_agent IN ('Yes', 'No') GROUP BY use_agent", "Among multi-hop papers, how many use an agent-style architecture versus not?"),
            q("q1", "SELECT uses_reranker, COUNT(*) AS paper_count FROM cspaper WHERE uses_knowledge_graph = 'Yes' AND uses_reranker IN ('Yes', 'No') GROUP BY uses_reranker", "Among papers that use a knowledge graph, how many also use a reranker?"),
            q("q2", "SELECT multi_turn_retrieval, COUNT(*) AS paper_count FROM cspaper WHERE use_agent = 'Yes' AND multi_turn_retrieval IN ('Yes', 'No') GROUP BY multi_turn_retrieval", "Among agent-based papers, how many support multi-turn retrieval versus not?"),
            q("q3", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, COUNT(*) AS paper_count FROM cspaper WHERE reasoning_depth = 'multi-hop' AND retrieval_method != '' GROUP BY retrieval_family", "Among multi-hop papers, how many use each retrieval-method family?"),
            q("q4", "SELECT reasoning_depth, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE baseline_amount >= 4 AND reasoning_depth IN ('single-hop', 'multi-hop') GROUP BY reasoning_depth", "Among papers that compare at least four baselines, what is the average baseline count for single-hop versus multi-hop work?"),
            q("q5", f"SELECT {DOMAIN_FAMILY} AS domain_family, COUNT(*) AS paper_count FROM cspaper WHERE uses_reranker = 'Yes' AND application_domain != '' GROUP BY domain_family", "Among papers that use a reranker, how many target each application-domain family?"),
            q("q6", "SELECT uses_knowledge_graph, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method LIKE '%Graph-based%' AND uses_knowledge_graph IN ('Yes', 'No') GROUP BY uses_knowledge_graph", "Among papers that use graph-based retrieval, how many also say they use a knowledge graph?"),
            q("q7", f"SELECT {MODALITY_FAMILY} AS modality_family, COUNT(*) AS paper_count FROM cspaper WHERE use_agent = 'Yes' AND data_modality != '' GROUP BY modality_family", "Among agent-based papers, how many are text-only versus multimodal or structured?"),
            q("q8", "SELECT reasoning_depth, COUNT(*) AS paper_count FROM cspaper WHERE application_domain LIKE '%Medical%' AND reasoning_depth IN ('single-hop', 'multi-hop') GROUP BY reasoning_depth", "Among medical-domain papers, how many are single-hop versus multi-hop?"),
            q("q9", "SELECT use_agent, COUNT(*) AS paper_count FROM cspaper WHERE multi_turn_retrieval = 'Yes' AND use_agent IN ('Yes', 'No') GROUP BY use_agent", "Among papers that support multi-turn retrieval, how many are agent-based versus not?"),
            q("q10", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE uses_reranker = 'No' AND baseline_amount IS NOT NULL AND retrieval_method != '' GROUP BY retrieval_family", "Among papers that do not use a reranker, what is the average number of baselines for each retrieval-method family?"),
            q("q11", "SELECT agent_framework, COUNT(*) AS paper_count FROM cspaper WHERE use_agent = 'Yes' AND agent_framework IN ('CoT', 'ToT', 'Multi-Agent Collaboration', 'Other') GROUP BY agent_framework", "Among agent-based papers, how many use each named agent framework?"),
            q("q12", "SELECT uses_reranker, COUNT(*) AS paper_count FROM cspaper WHERE data_modality LIKE '%Image%' AND uses_reranker IN ('Yes', 'No') GROUP BY uses_reranker", "Among papers that handle image input, how many use a reranker?"),
            q("q13", f"SELECT {DOMAIN_FAMILY} AS domain_family, COUNT(*) AS paper_count FROM cspaper WHERE baseline_amount BETWEEN 2 AND 6 AND application_domain != '' GROUP BY domain_family", "Among papers that compare two to six baselines, how many target each application-domain family?"),
            q("q14", "SELECT reasoning_depth, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method LIKE '%Dense%' AND uses_knowledge_graph = 'No' AND reasoning_depth IN ('single-hop', 'multi-hop') GROUP BY reasoning_depth", "Among dense-retrieval papers that do not use a knowledge graph, how many are single-hop versus multi-hop?"),
            q("q15", "SELECT multi_turn_retrieval, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE use_agent = 'No' AND multi_turn_retrieval IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY multi_turn_retrieval", "Among non-agent papers, what is the average number of baselines for multi-turn versus single-turn retrieval?"),
            q("q16", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, COUNT(*) AS paper_count FROM cspaper WHERE application_domain LIKE '%General%' AND retrieval_method != '' GROUP BY retrieval_family", "Among general-domain papers, how many use each retrieval-method family?"),
            q("q17", "SELECT uses_knowledge_graph, COUNT(*) AS paper_count FROM cspaper WHERE reasoning_depth = 'multi-hop' AND use_agent = 'Yes' AND uses_knowledge_graph IN ('Yes', 'No') GROUP BY uses_knowledge_graph", "Among multi-hop agent-based papers, how many use a knowledge graph?"),
            q("q18", "SELECT uses_reranker, COUNT(*) AS paper_count FROM cspaper WHERE baseline_amount >= 5 AND uses_reranker IN ('Yes', 'No') GROUP BY uses_reranker", "Among papers that compare at least five baselines, how many use a reranker?"),
            q("q19", f"SELECT {MODALITY_FAMILY} AS modality_family, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method LIKE '%Hybrid%' AND data_modality != '' GROUP BY modality_family", "Among hybrid-retrieval papers, how many are text-only versus multimodal or structured?"),
        ],
    },
    "cspaper_groupby20": {
        "title": "Group-by variety workload",
        "focus": "Diverse GROUP BY keys, including multi-column and family groupings",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", "SELECT reasoning_depth, use_agent, COUNT(*) AS paper_count FROM cspaper WHERE reasoning_depth IN ('single-hop', 'multi-hop') AND use_agent IN ('Yes', 'No') GROUP BY reasoning_depth, use_agent", "For single-hop and multi-hop papers separately, how many use an agent-style architecture versus not?"),
            q("q1", "SELECT uses_reranker, multi_turn_retrieval, COUNT(*) AS paper_count FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND multi_turn_retrieval IN ('Yes', 'No') GROUP BY uses_reranker, multi_turn_retrieval", "For papers with and without a reranker, how many support multi-turn retrieval versus not?"),
            q("q2", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, reasoning_depth, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method != '' AND reasoning_depth IN ('single-hop', 'multi-hop') GROUP BY retrieval_family, reasoning_depth", "For each retrieval-method family, how many papers are single-hop versus multi-hop?"),
            q("q3", f"SELECT {DOMAIN_FAMILY} AS domain_family, use_agent, COUNT(*) AS paper_count FROM cspaper WHERE application_domain != '' AND use_agent IN ('Yes', 'No') GROUP BY domain_family, use_agent", "For each application-domain family, how many papers are agent-based versus not?"),
            q("q4", "SELECT uses_knowledge_graph, uses_reranker, COUNT(*) AS paper_count FROM cspaper WHERE uses_knowledge_graph IN ('Yes', 'No') AND uses_reranker IN ('Yes', 'No') GROUP BY uses_knowledge_graph, uses_reranker", "For papers with and without a knowledge graph, how many also use a reranker?"),
            q("q5", f"SELECT {MODALITY_FAMILY} AS modality_family, reasoning_depth, COUNT(*) AS paper_count FROM cspaper WHERE data_modality != '' AND reasoning_depth IN ('single-hop', 'multi-hop') GROUP BY modality_family, reasoning_depth", "For text-only versus multimodal or structured papers, how many are single-hop versus multi-hop?"),
            q("q6", "SELECT use_agent, multi_turn_retrieval, COUNT(*) AS paper_count FROM cspaper WHERE use_agent IN ('Yes', 'No') AND multi_turn_retrieval IN ('Yes', 'No') GROUP BY use_agent, multi_turn_retrieval", "For agent-based and non-agent papers, how many support multi-turn retrieval?"),
            q("q7", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, uses_reranker, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method != '' AND uses_reranker IN ('Yes', 'No') GROUP BY retrieval_family, uses_reranker", "For each retrieval-method family, how many papers use a reranker versus not?"),
            q("q8", "SELECT CASE WHEN baseline_amount <= 2 THEN '1_to_2' WHEN baseline_amount <= 5 THEN '3_to_5' ELSE '6_or_more' END AS baseline_band, reasoning_depth, COUNT(*) AS paper_count FROM cspaper WHERE baseline_amount IS NOT NULL AND reasoning_depth IN ('single-hop', 'multi-hop') GROUP BY baseline_band, reasoning_depth", "For papers with 1–2, 3–5, or 6 or more baselines, how many are single-hop versus multi-hop?"),
            q("q9", f"SELECT {DOMAIN_FAMILY} AS domain_family, uses_knowledge_graph, COUNT(*) AS paper_count FROM cspaper WHERE application_domain != '' AND uses_knowledge_graph IN ('Yes', 'No') GROUP BY domain_family, uses_knowledge_graph", "For each application-domain family, how many papers use a knowledge graph?"),
            q("q10", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, {MODALITY_FAMILY} AS modality_family, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method != '' AND data_modality != '' GROUP BY retrieval_family, modality_family", "For each retrieval-method family, how many papers are text-only versus multimodal or structured?"),
            q("q11", "SELECT agent_framework, reasoning_depth, COUNT(*) AS paper_count FROM cspaper WHERE agent_framework IN ('CoT', 'ToT', 'Multi-Agent Collaboration', 'Other') AND reasoning_depth IN ('single-hop', 'multi-hop') GROUP BY agent_framework, reasoning_depth", "For each named agent framework, how many papers are single-hop versus multi-hop?"),
            q("q12", "SELECT uses_reranker, use_agent, COUNT(*) AS paper_count FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND use_agent IN ('Yes', 'No') GROUP BY uses_reranker, use_agent", "For papers with and without a reranker, how many use an agent-style architecture?"),
            q("q13", f"SELECT {DOMAIN_FAMILY} AS domain_family, multi_turn_retrieval, COUNT(*) AS paper_count FROM cspaper WHERE application_domain != '' AND multi_turn_retrieval IN ('Yes', 'No') GROUP BY domain_family, multi_turn_retrieval", "For each application-domain family, how many papers support multi-turn retrieval?"),
            q("q14", "SELECT CASE WHEN baseline_amount <= 2 THEN '1_to_2' WHEN baseline_amount <= 5 THEN '3_to_5' ELSE '6_or_more' END AS baseline_band, use_agent, COUNT(*) AS paper_count FROM cspaper WHERE baseline_amount IS NOT NULL AND use_agent IN ('Yes', 'No') GROUP BY baseline_band, use_agent", "For each baseline-count band, how many papers are agent-based versus not?"),
            q("q15", f"SELECT {MODALITY_FAMILY} AS modality_family, uses_reranker, COUNT(*) AS paper_count FROM cspaper WHERE data_modality != '' AND uses_reranker IN ('Yes', 'No') GROUP BY modality_family, uses_reranker", "For text-only versus multimodal or structured papers, how many use a reranker?"),
            q("q16", "SELECT uses_knowledge_graph, reasoning_depth, COUNT(*) AS paper_count FROM cspaper WHERE uses_knowledge_graph IN ('Yes', 'No') AND reasoning_depth IN ('single-hop', 'multi-hop') GROUP BY uses_knowledge_graph, reasoning_depth", "For papers with and without a knowledge graph, how many are single-hop versus multi-hop?"),
            q("q17", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, use_agent, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method != '' AND use_agent IN ('Yes', 'No') GROUP BY retrieval_family, use_agent", "For each retrieval-method family, how many papers are agent-based versus not?"),
            q("q18", f"SELECT {DOMAIN_FAMILY} AS domain_family, {MODALITY_FAMILY} AS modality_family, COUNT(*) AS paper_count FROM cspaper WHERE application_domain != '' AND data_modality != '' GROUP BY domain_family, modality_family", "For each application-domain family, how many papers are text-only versus multimodal or structured?"),
            q("q19", "SELECT CASE WHEN baseline_amount <= 3 THEN 'few_baselines' ELSE 'many_baselines' END AS baseline_band, uses_reranker, multi_turn_retrieval, COUNT(*) AS paper_count FROM cspaper WHERE baseline_amount IS NOT NULL AND uses_reranker IN ('Yes', 'No') AND multi_turn_retrieval IN ('Yes', 'No') GROUP BY baseline_band, uses_reranker, multi_turn_retrieval", "For papers with few versus many baselines, how many use a reranker and how many support multi-turn retrieval?"),
        ],
    },
    "cspaper_multiagg20": {
        "title": "Multi-aggregation workload",
        "focus": "Several aggregates, often with HAVING, in the same query",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", "SELECT reasoning_depth, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE reasoning_depth IN ('single-hop', 'multi-hop') AND baseline_amount IS NOT NULL GROUP BY reasoning_depth", "For single-hop and multi-hop papers, what are the paper count and the average and maximum number of baselines?"),
            q("q1", "SELECT use_agent, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS reranker_count FROM cspaper WHERE use_agent IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY use_agent", "For agent-based versus non-agent papers, what are the count, average baselines, and number that use a reranker?"),
            q("q2", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE retrieval_method != '' AND baseline_amount IS NOT NULL GROUP BY retrieval_family HAVING COUNT(*) >= 5", "For retrieval-method families with at least five papers, what are the count and the average and maximum baseline totals?"),
            q("q3", f"SELECT {DOMAIN_FAMILY} AS domain_family, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS agent_count FROM cspaper WHERE application_domain != '' AND baseline_amount IS NOT NULL GROUP BY domain_family", "For each application-domain family, what are the paper count, average baselines, and number of agent-based papers?"),
            q("q4", "SELECT uses_reranker, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, SUM(CASE WHEN multi_turn_retrieval = 'Yes' THEN 1 ELSE 0 END) AS multi_turn_count FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY uses_reranker", "For papers with and without a reranker, what are the count, average baselines, and number that support multi-turn retrieval?"),
            q("q5", "SELECT uses_knowledge_graph, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE uses_knowledge_graph IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY uses_knowledge_graph", "For papers with and without a knowledge graph, what are the count and the average and maximum number of baselines?"),
            q("q6", f"SELECT {MODALITY_FAMILY} AS modality_family, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS reranker_count FROM cspaper WHERE data_modality != '' AND baseline_amount IS NOT NULL GROUP BY modality_family", "For text-only versus multimodal or structured papers, what are the count, average baselines, and number that use a reranker?"),
            q("q7", "SELECT multi_turn_retrieval, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS agent_count FROM cspaper WHERE multi_turn_retrieval IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY multi_turn_retrieval", "For multi-turn versus single-turn retrieval papers, what are the count, average baselines, and number of agent-based systems?"),
            q("q8", "SELECT agent_framework, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE agent_framework IN ('CoT', 'ToT', 'Multi-Agent Collaboration', 'Other') AND baseline_amount IS NOT NULL GROUP BY agent_framework", "For each named agent framework, what are the paper count and the average and maximum number of baselines?"),
            q("q9", "SELECT reasoning_depth, COUNT(*) AS paper_count, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS kg_count, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS reranker_count, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE reasoning_depth IN ('single-hop', 'multi-hop') AND baseline_amount IS NOT NULL GROUP BY reasoning_depth", "For single-hop and multi-hop papers, how many use a knowledge graph, how many use a reranker, and what is the average baseline count?"),
            q("q10", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, COUNT(*) AS paper_count, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS agent_count, SUM(CASE WHEN multi_turn_retrieval = 'Yes' THEN 1 ELSE 0 END) AS multi_turn_count FROM cspaper WHERE retrieval_method != '' GROUP BY retrieval_family HAVING COUNT(*) >= 5", "For retrieval-method families with at least five papers, how many are agent-based and how many support multi-turn retrieval?"),
            q("q11", f"SELECT {DOMAIN_FAMILY} AS domain_family, COUNT(*) AS paper_count, MIN(baseline_amount) AS min_baselines, MAX(baseline_amount) AS max_baselines, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE application_domain != '' AND baseline_amount IS NOT NULL GROUP BY domain_family HAVING COUNT(*) >= 5", "For application-domain families with at least five papers, what are the count and the minimum, maximum, and average baseline totals?"),
            q("q12", "SELECT CASE WHEN baseline_amount <= 2 THEN '1_to_2' WHEN baseline_amount <= 5 THEN '3_to_5' ELSE '6_or_more' END AS baseline_band, COUNT(*) AS paper_count, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS agent_count, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS reranker_count FROM cspaper WHERE baseline_amount IS NOT NULL GROUP BY baseline_band", "For each baseline-count band, how many papers are there, how many are agent-based, and how many use a reranker?"),
            q("q13", "SELECT use_agent, reasoning_depth, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE use_agent IN ('Yes', 'No') AND reasoning_depth IN ('single-hop', 'multi-hop') AND baseline_amount IS NOT NULL GROUP BY use_agent, reasoning_depth", "For each combination of agent use and reasoning depth, what are the paper count and the average and maximum baseline totals?"),
            q("q14", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS kg_count FROM cspaper WHERE retrieval_method != '' AND baseline_amount IS NOT NULL GROUP BY retrieval_family HAVING COUNT(*) >= 5", "For retrieval-method families with at least five papers, what are the count, average baselines, and number that use a knowledge graph?"),
            q("q15", f"SELECT {MODALITY_FAMILY} AS modality_family, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, SUM(CASE WHEN multi_turn_retrieval = 'Yes' THEN 1 ELSE 0 END) AS multi_turn_count FROM cspaper WHERE data_modality != '' AND baseline_amount IS NOT NULL GROUP BY modality_family", "For text-only versus multimodal or structured papers, what are the count, average baselines, and number that support multi-turn retrieval?"),
            q("q16", "SELECT uses_reranker, uses_knowledge_graph, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND uses_knowledge_graph IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY uses_reranker, uses_knowledge_graph HAVING COUNT(*) >= 3", "For each reranker and knowledge-graph combination with at least three papers, what are the count and the average and maximum baseline totals?"),
            q("q17", f"SELECT {DOMAIN_FAMILY} AS domain_family, COUNT(*) AS paper_count, SUM(CASE WHEN reasoning_depth = 'multi-hop' THEN 1 ELSE 0 END) AS multi_hop_count, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS agent_count, AVG(baseline_amount) AS avg_baselines FROM cspaper WHERE application_domain != '' AND baseline_amount IS NOT NULL GROUP BY domain_family", "For each application-domain family, how many papers are multi-hop, how many are agent-based, and what is the average baseline count?"),
            q("q18", "SELECT multi_turn_retrieval, use_agent, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE multi_turn_retrieval IN ('Yes', 'No') AND use_agent IN ('Yes', 'No') AND baseline_amount IS NOT NULL GROUP BY multi_turn_retrieval, use_agent", "For each combination of multi-turn retrieval and agent use, what are the paper count and the average and maximum baseline totals?"),
            q("q19", f"SELECT {RETRIEVAL_FAMILY} AS retrieval_family, reasoning_depth, COUNT(*) AS paper_count, AVG(baseline_amount) AS avg_baselines, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS reranker_count FROM cspaper WHERE retrieval_method != '' AND reasoning_depth IN ('single-hop', 'multi-hop') AND baseline_amount IS NOT NULL GROUP BY retrieval_family, reasoning_depth HAVING COUNT(*) >= 3", "For each retrieval family and reasoning depth with at least three papers, what are the count, average baselines, and number that use a reranker?"),
        ],
    },
}

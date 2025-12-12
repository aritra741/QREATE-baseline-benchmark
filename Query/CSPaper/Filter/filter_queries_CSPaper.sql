-- Query 1: 1 (cspaper)
SELECT uses_reranker, performance_on_hotpotqa, baseline FROM cspaper WHERE performance_on_hotpotqa != 'KILT-EM: 27.3 (T5-Base); KILT-EM: 31.1 (T5-XL)';

-- Query 2: 1 (cspaper)
SELECT generator_model, retrieval_method, data_modality FROM cspaper WHERE data_modality = 'Text,Image';

-- Query 3: 1 (cspaper)
SELECT uses_reranker, uses_knowledge_graph, performance_on_hotpotqa FROM cspaper WHERE uses_knowledge_graph != 'Yes';

-- Query 4: 1 (cspaper)
SELECT baseline, reasoning_depth, evaluation_dataset FROM cspaper WHERE evaluation_dataset = 'MufassirQAS';

-- Query 5: 1 (cspaper)
SELECT data_modality, baseline, evaluation_metric FROM cspaper WHERE baseline = 'Zero-Shot; Few-Shot; Dynamic Few-Shot';

-- Query 6: 1 (cspaper)
SELECT multi_turn_retrieval, evaluation_metric, reasoning_depth FROM cspaper WHERE reasoning_depth = 'multi-hop';

-- Query 7: 1 (cspaper)
SELECT evaluation_metric, multi_turn_retrieval, topic FROM cspaper WHERE evaluation_metric = 'Accuracy; Succinctness; Correctness; Recall';

-- Query 8: 1 (cspaper)
SELECT data_modality, use_agent, topic FROM cspaper WHERE use_agent = 'No';

-- Query 9: 1 (cspaper)
SELECT baseline, retrieval_method, baseline_amount FROM cspaper WHERE baseline_amount < 10;

-- Query 10: 1 (cspaper)
SELECT data_modality, topic, generator_model FROM cspaper WHERE topic != 'SFT';

-- Query 11: 2 (cspaper)
SELECT performance_on_NQ, agent_framework, uses_knowledge_graph FROM cspaper WHERE performance_on_NQ != 'Llama-3.1-8B-Instruct-4K: Hit@1: 61.75, EM: 45.90; Llama-3.1-70B-Instruct-4K: Hit@1: 60.50, EM: 45.26' AND generator_model != 'gpt-3.5-turbo-16k-0613';

-- Query 12: 2 (cspaper)
SELECT evaluation_dataset, data_modality, application_domain FROM cspaper WHERE application_domain = 'Education' AND evaluation_metric = 'recall@k; Preprocessing Time; Query processing time';

-- Query 13: 2 (cspaper)
SELECT performance_on_hotpotqa, evaluation_metric, evaluation_dataset FROM cspaper WHERE performance_on_hotpotqa != 'Clean ACC: Mistral-7B 51.0, Llama2-C 46.0, GPT-4o 47.6; Robust RACC/ASR (PIA Attack, AVF α=5): Mistral-7B 53.0/8.0, Llama2-C 34.0/11.4, GPT-4o 42.6/9.8' AND agent_framework != 'Multi-Agent Collaboration';

-- Query 14: 2 (cspaper)
SELECT data_modality, baseline, evaluation_dataset FROM cspaper WHERE data_modality != 'Table; Text' AND agent_framework != 'Other';

-- Query 15: 2 (cspaper)
SELECT retrieval_method, baseline_amount, baseline FROM cspaper WHERE baseline != 'GPT-3; GPT-4;LLaMA2; LAMBADA; PALM' AND reasoning_depth != 'multi-hop';

-- Query 16: 2 (cspaper)
SELECT baseline, uses_reranker, use_agent FROM cspaper WHERE baseline != 'VanillaRAG; GraphRAG; Long-Context LLM; Normal SFT' AND use_agent = 'Yes';

-- Query 17: 2 (cspaper)
SELECT retrieval_method, baseline, application_domain FROM cspaper WHERE retrieval_method != 'Web Search; Dense Retrieval' AND evaluation_metric = 'Accuracy; match score; F1 score';

-- Query 18: 2 (cspaper)
SELECT uses_reranker, multi_turn_retrieval, data_modality FROM cspaper WHERE data_modality = 'Text; Image; Audio' AND evaluation_metric != 'AUROC; AUPRC; min(+P, Se); F1';

-- Query 19: 2 (cspaper)
SELECT performance_on_NQ, baseline_amount, evaluation_dataset FROM cspaper WHERE performance_on_NQ != 'Retrieval Acc@5: 80.5; Retrieval Acc@20: 88.0; Generation ExactMatch: 56.2' AND use_agent = 'Yes';

-- Query 20: 2 (cspaper)
SELECT uses_reranker, application_domain, baseline FROM cspaper WHERE baseline = 'Direct; DSP; Self-RAG; ReAct; Self-Ask' AND multi_turn_retrieval != 'No';

-- Query 21: 3 (cspaper)
SELECT retrieval_method, uses_knowledge_graph, evaluation_metric FROM cspaper WHERE retrieval_method != 'Web Search; Dense Retrieval' OR evaluation_metric != 'recall@1; recall@5; recall@20; BLEU-4; BERTScore; Inform Rate';

-- Query 22: 3 (cspaper)
SELECT multi_turn_retrieval, data_modality, baseline_amount FROM cspaper WHERE multi_turn_retrieval != 'Yes' OR baseline_amount = 6;

-- Query 23: 3 (cspaper)
SELECT uses_knowledge_graph, generator_model, retrieval_method FROM cspaper WHERE retrieval_method = 'Web Search; Other' OR performance_on_hotpotqa != 'Accuracy: ~0.62';

-- Query 24: 3 (cspaper)
SELECT baseline, performance_on_NQ, reasoning_depth FROM cspaper WHERE reasoning_depth = 'single-hop' OR use_agent != 'No';

-- Query 25: 3 (cspaper)
SELECT evaluation_dataset, agent_framework, performance_on_hotpotqa FROM cspaper WHERE performance_on_hotpotqa = 'F1: 40.8' OR use_agent != 'No';

-- Query 26: 3 (cspaper)
SELECT use_agent, uses_reranker, retrieval_method FROM cspaper WHERE uses_reranker != 'Yes' OR topic != 'Data Selection';

-- Query 27: 3 (cspaper)
SELECT data_modality, uses_reranker, performance_on_NQ FROM cspaper WHERE data_modality != 'Text; Code; Audio' OR agent_framework = 'ToT';

-- Query 28: 3 (cspaper)
SELECT use_agent, reasoning_depth, multi_turn_retrieval FROM cspaper WHERE reasoning_depth = 'single-hop' OR data_modality != 'Text; Table; Image';

-- Query 29: 3 (cspaper)
SELECT data_modality, agent_framework, generator_model FROM cspaper WHERE data_modality != 'Text,Image' OR evaluation_metric = 'relevance; readability; informativeness; Response time';

-- Query 30: 3 (cspaper)
SELECT application_domain, use_agent, generator_model FROM cspaper WHERE use_agent = 'Yes' OR baseline = 'OpenAI models';

-- Query 31: 4 (cspaper)
SELECT performance_on_NQ, performance_on_hotpotqa, baseline_amount FROM cspaper WHERE performance_on_hotpotqa = 'EM:0.667;F1：0.795' AND baseline_amount >= 3 AND performance_on_NQ = 'Accuracy: 0.6294; Accuracy: 0.6033' AND use_agent = 'Yes';

-- Query 32: 4 (cspaper)
SELECT reasoning_depth, generator_model, uses_knowledge_graph FROM cspaper WHERE uses_knowledge_graph = 'No' AND topic = 'SFT' AND reasoning_depth != 'multi-hop' AND baseline != 'LLaMa3.1-8b; Qwen2.5-7b; Longcite; RAG-Ex';

-- Query 33: 4 (cspaper)
SELECT use_agent, retrieval_method, data_modality FROM cspaper WHERE data_modality = 'Text; Image; Audio' AND uses_reranker != 'Yes' AND use_agent != 'No' AND data_modality != 'Text';

-- Query 34: 4 (cspaper)
SELECT evaluation_metric, use_agent, agent_framework FROM cspaper WHERE agent_framework != 'Other' AND uses_knowledge_graph != 'No' AND agent_framework = 'ToT' AND uses_knowledge_graph != 'No';

-- Query 35: 4 (cspaper)
SELECT uses_knowledge_graph, baseline, agent_framework FROM cspaper WHERE baseline != 'RAG; DPR + FiD; KGI; Re2G; Hindsight; SEAL + FiD; Re3val; GripRank; PLATO; FiD-Light (T5-Base, k = 64); FiD-Light (T5-XL, k = 8)' AND baseline_amount < 10 AND generator_model = 'Mistral-7B-Instruct; Llama2-7B-Chat; GPT-3.5-turbo' AND topic = 'Information Retrieval';

-- Query 36: 4 (cspaper)
SELECT generator_model, uses_reranker, evaluation_metric FROM cspaper WHERE generator_model != 'Phi-3.5-mini-instruct' AND agent_framework != 'ToT' AND baseline = 'RAG' AND performance_on_NQ = 'RE-RAGbase: EM: 49.9, Acc: 53.1, F1: 56.9; RE-RAGFlan-base: EM: 51.9, Acc: 55.2, F1: 58.9; RE-RAGlarge: EM: 54.0, Acc: 56.7, F1: 61.0; RE-RAGFlan-large: EM: 55.4, Acc: 58.3, F1: 62.5; Llama27b + RE: EM: 45.7, Acc: 48.4, F1: 54.3; Llama213b + RE: EM: 46.6, Acc: 49.8, F1: 55.6; Llama3gb +RE: EM: 49.6, Acc: 54.5, F1: 59.0; Llama270b + RE: EM: 48.0, Acc: 52.0, F1: 57.6; Llama370b + RE: EM: 50.8, Acc: 54.8, F1: 60.1; ChatGPT+RE: EM: 49.3, Acc: 55.2, F1: 59.6';

-- Query 37: 4 (cspaper)
SELECT uses_reranker, performance_on_hotpotqa, use_agent FROM cspaper WHERE uses_reranker != 'Yes' AND multi_turn_retrieval != 'Yes' AND baseline_amount <= 1 AND generator_model = 'GPT-4';

-- Query 38: 4 (cspaper)
SELECT topic, application_domain, reasoning_depth FROM cspaper WHERE topic != 'SFT' AND generator_model != 'Mistral-7B-Instruct; Llama2-7B-Chat; GPT-3.5-turbo' AND multi_turn_retrieval != 'Yes' AND topic != 'SFT';

-- Query 39: 4 (cspaper)
SELECT baseline, data_modality, evaluation_metric FROM cspaper WHERE evaluation_metric = 'AUROC; AUPRC; min(+P, Se); F1' AND agent_framework != 'ToT' AND evaluation_dataset = 'FAQ dataset' AND evaluation_metric != 'AUROC; AUPRC; min(+P, Se); F1';

-- Query 40: 4 (cspaper)
SELECT performance_on_hotpotqa, evaluation_dataset, multi_turn_retrieval FROM cspaper WHERE evaluation_dataset != 'Custom Agriculture Dataset (USA, Brazil, India); Washington state benchmark dataset' AND uses_knowledge_graph != 'Yes' AND agent_framework = 'CoT' AND generator_model = 'Llama2-13B-Chat';

-- Query 41: 5 (cspaper)
SELECT data_modality, agent_framework, use_agent FROM cspaper WHERE data_modality != 'Text; Image; Audio' OR baseline = 'M3Care; MPIM; UMM; VecoCare; GRAM; KAME; CGL; KerPrint' OR baseline_amount > 6 OR evaluation_dataset = 'Natural Questions; TriviaQA';

-- Query 42: 5 (cspaper)
SELECT uses_knowledge_graph, uses_reranker, reasoning_depth FROM cspaper WHERE uses_reranker = 'No' OR baseline != 'e5-base-v2; gpt-2' OR evaluation_dataset = 'Custom Korean Medicine (KM) questions' OR application_domain != 'Other; Other; Finance';

-- Query 43: 5 (cspaper)
SELECT uses_knowledge_graph, evaluation_metric, retrieval_method FROM cspaper WHERE uses_knowledge_graph != 'Yes' OR retrieval_method = 'Sparse Retrieval; Dense Retrieval' OR evaluation_metric != 'top-1 accuracy; top-3 accuracy;Accuracy' OR performance_on_NQ = 'Ideal Setting (4√+1x): Qwen1.5-7B (EM: 29.10, F1 score: 41.02); Llama2-13B (EM: 33.60, F1 score: 44.62); Llama3-8B (EM: 36.90, F1 score: 48.45). GPT Setting (4√+1x): Qwen1.5-7B (EM: 23.10, F1 score: 34.84); Llama2-13B (EM: 25.10, F1 score: 35.56); Llama3-8B (EM: 30.70, F1 score: 41.71).';

-- Query 44: 5 (cspaper)
SELECT data_modality, uses_reranker, retrieval_method FROM cspaper WHERE uses_reranker != 'Yes' OR topic != 'Data Selection' OR baseline_amount >= 1 OR uses_knowledge_graph = 'No';

-- Query 45: 5 (cspaper)
SELECT evaluation_metric, data_modality, multi_turn_retrieval FROM cspaper WHERE data_modality = 'Text; Code' OR multi_turn_retrieval = 'Yes' OR multi_turn_retrieval != 'Yes' OR use_agent != 'Yes';

-- Query 46: 5 (cspaper)
SELECT use_agent, multi_turn_retrieval, generator_model FROM cspaper WHERE use_agent != 'No' OR performance_on_hotpotqa != 'Gemma-2b: EM 21.8, ACC 39.4; Mistral-7b: EM 22.4, ACC 38.6' OR uses_knowledge_graph != 'No' OR data_modality = 'Code';

-- Query 47: 5 (cspaper)
SELECT agent_framework, topic, performance_on_hotpotqa FROM cspaper WHERE performance_on_hotpotqa != 'F1: 57.59; Hit Rate: 50.00' OR evaluation_metric = 'Accuracy' OR uses_knowledge_graph != 'Yes' OR data_modality != 'Text; Image; Audio';

-- Query 48: 5 (cspaper)
SELECT baseline, topic, performance_on_hotpotqa FROM cspaper WHERE baseline != 'Zero-Shot; Few-Shot; Dynamic Few-Shot' OR uses_knowledge_graph != 'Yes' OR evaluation_metric != 'Hallucination Count; Incompleteness Count' OR generator_model = 'Llama2-13B-chat; Vicuna-13B-v1.5-16k; GPT-4; Llama2 13B';

-- Query 49: 5 (cspaper)
SELECT use_agent, evaluation_metric, agent_framework FROM cspaper WHERE evaluation_metric = 'precision; α-nDCG; Citation Support; Nugget Coverage; Sentence Support; recall' OR multi_turn_retrieval != 'No' OR uses_reranker = 'No' OR evaluation_dataset = 'Coffee Leaf Diseases YOLO';

-- Query 50: 5 (cspaper)
SELECT performance_on_hotpotqa, topic, multi_turn_retrieval FROM cspaper WHERE multi_turn_retrieval != 'No' OR performance_on_hotpotqa = 'F1: 62.6' OR reasoning_depth = 'multi-hop' OR performance_on_hotpotqa = 'R-1: 64.98; R-L: 64.95; B-1: 68.42; Met.: 57.74';

-- Query 51: 6 (cspaper)
SELECT evaluation_dataset, generator_model, reasoning_depth FROM cspaper WHERE (generator_model = 'Qwen-32B' AND application_domain = 'Medical') OR (agent_framework != 'Multi-Agent Collaboration' AND performance_on_hotpotqa != 'Accuracy: 52.29');

-- Query 52: 6 (cspaper)
SELECT evaluation_dataset, generator_model, topic FROM cspaper WHERE (generator_model != 'GPT-4 Turbo 1106-Preview' AND uses_reranker != 'Yes') OR (uses_knowledge_graph = 'No' AND uses_knowledge_graph = 'Yes');

-- Query 53: 6 (cspaper)
SELECT multi_turn_retrieval, use_agent, data_modality FROM cspaper WHERE (data_modality = 'Audio; Text' AND performance_on_hotpotqa = 'Clean ACC (AVF α=∞): Mistral-7B 51.0, Llama2-C 46.0, GPT-4o 47.6; Robust RACC/ASR (PIA Attack, AVF α=5): Mistral-7B 53.0/8.0, Llama2-C 34.0/11.4, GPT-4o 42.6/9.8') OR (evaluation_dataset != 'FAQ dataset' AND agent_framework != 'ToT');

-- Query 54: 6 (cspaper)
SELECT reasoning_depth, uses_knowledge_graph, multi_turn_retrieval FROM cspaper WHERE (multi_turn_retrieval = 'No' AND application_domain = 'General; Medical') OR (performance_on_hotpotqa != 'EM: 48.58; F1: 62.87; Acc: 55.68' AND retrieval_method = 'Dense Retrieval; Hybrid Retrieval; Sparse Retrieval');

-- Query 55: 6 (cspaper)
SELECT baseline, performance_on_NQ, baseline_amount FROM cspaper WHERE (baseline = 'Llama2-7b-Chat; GPT-3.5-turbo' AND performance_on_NQ = 'EM: 36.48; F1: 49.81') OR (evaluation_dataset = 'Custom Agriculture Dataset (USA, Brazil, India); Washington state benchmark dataset' AND generator_model = 'LLama 3.1 8B; Phi-3.5 mini; LLama 3.2 3B; LLaMA 3.2 1B; GPT-4o-mini');

-- Query 56: 6 (cspaper)
SELECT reasoning_depth, baseline, uses_reranker FROM cspaper WHERE (baseline != 'ChatGPT' AND retrieval_method = 'Hybrid Retrieval; Dense Retrieval') OR (baseline = 'RAPTOR; Embed' AND baseline != 'Llama2-7B; Llama2-13B; SAIL-7B; Alpaca-7B; Alpaca-13B; ChatGPT; CoVE65B; RAG-ChatGPT; RAG 2.0; RAG-Command R+; RQ-RAG7B(ToT); Perplexity.ai; Self-RAG-7B; Self-RAG-13B; LongChat-13B');

-- Query 57: 6 (cspaper)
SELECT performance_on_hotpotqa, agent_framework, evaluation_dataset FROM cspaper WHERE (performance_on_hotpotqa = 'Clean ACC (AVF α=∞): Mistral-7B 51.0, Llama2-C 46.0, GPT-4o 47.6; Robust RACC/ASR (PIA Attack, AVF α=5): Mistral-7B 53.0/8.0, Llama2-C 34.0/11.4, GPT-4o 42.6/9.8' AND evaluation_dataset != 'Enron Email; HealthcareMagic-101;') OR (topic = 'Information Retrieval' AND uses_knowledge_graph != 'Yes');

-- Query 58: 6 (cspaper)
SELECT reasoning_depth, evaluation_dataset, generator_model FROM cspaper WHERE (reasoning_depth != 'multi-hop' AND multi_turn_retrieval = 'Yes') OR (performance_on_NQ = 'Ideal Setting (4√+1x): Qwen1.5-7B (EM: 29.10, F1 score: 41.02); Llama2-13B (EM: 33.60, F1 score: 44.62); Llama3-8B (EM: 36.90, F1 score: 48.45). GPT Setting (4√+1x): Qwen1.5-7B (EM: 23.10, F1 score: 34.84); Llama2-13B (EM: 25.10, F1 score: 35.56); Llama3-8B (EM: 30.70, F1 score: 41.71).' AND performance_on_NQ = 'TeaRAG-8B: EM: 50.06; F1: 59.71; TeaRAG-14B: EM: 50.33; F1: 60.31');

-- Query 59: 6 (cspaper)
SELECT application_domain, uses_knowledge_graph, performance_on_hotpotqa FROM cspaper WHERE (performance_on_hotpotqa != 'EM: 63.3; F1: 76.9' AND evaluation_metric = 'F1') OR (baseline_amount <= 3 AND data_modality != 'Text; Image; Audio');

-- Query 60: 6 (cspaper)
SELECT evaluation_metric, performance_on_hotpotqa, performance_on_NQ FROM cspaper WHERE (performance_on_hotpotqa = 'EM (x4 compression): 0.430; EM (x16 compression): 0.426; EM (x128 compression): 0.378' AND uses_knowledge_graph != 'Yes') OR (retrieval_method = 'Hybrid Retrieval; Dense Retrieval' AND evaluation_dataset != 'MMCU-Medical; CMB-Exam; CMB-Clin');


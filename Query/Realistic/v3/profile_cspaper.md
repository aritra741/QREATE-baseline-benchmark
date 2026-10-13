# Data profile: cspaper

Tables (rows = documents): cspaper (200)

Columns marked INITIAL are read by the initial build; build questions may use ONLY those. Test questions may use any column.

Value statistics are from the correct data (what a perfect extraction would hold). Values containing '||' are lists.

## cspaper.agent_framework  [new; category; filled 49/200; distinct 4]
description: main agent-style reasoning framework used by the system, choose one from ['CoT', 'ToT', 'Multi-Agent Collaboration', 'Other'], if the system does not use agent, leave it empty.
most common values: 'Other' x27; 'Multi-Agent Collaboration' x12; 'CoT' x8; 'ToT' x2

## cspaper.application_domain  [INITIAL; list; filled 199/200; distinct 36]
description: primary real-world domain or application scenario targeted by the paper, choose one or more from ['General', 'Education', 'Finance', 'Sports', 'Government', 'Legal', 'Medical', 'Academic', 'Art', 'Other'], e.g. Education; Finance
most common values: 'General' x94; 'Other' x24; 'Medical' x15; 'Education' x12; 'General|| Academic' x7; 'Finance' x6; 'Academic' x6; 'Medical|| General' x3; 'Education|| Academic' x2; 'General|| Medical|| Academic' x2

## cspaper.baseline  [new; free text; filled 188/200; distinct 187]
description: baseline model or system used for comparison in the experiments, list all the baselines mentioned in the text.
most common values: 'RAG' x2; 'GPT-3|| GPT-4|| LLaMA2|| LAMBADA|| PALM' x1; 'e5-base-v2|| gpt-2' x1; 'Llama2-13B-chat|| Vicuna-13B-v1.5-16k|| GPT-4' x1; 'ChatGPT-3.5|| ChatGPT-4|| C50-V300|| C100-V150' x1; 'ChatGPT' x1; 'M3Care|| MPIM|| UMM|| VecoCare|| GRAM|| KAME|| CGL|| KerPrin' x1; 'None (LLM alone)|| Random Noise+prompt|| System Prompt+promp' x1; 'Standard LLM (without context)' x1; 'Zero-Shot|| Few-Shot|| Dynamic Few-Shot' x1

## cspaper.baseline_amount  [INITIAL; number; filled 188/200; distinct 15]
description: the number of baselines in this paper.
most common values: '2' x43; '1' x29; '3' x27; '4' x18; '6' x17; '5' x15; '8' x9; '7' x9; '9' x8; '10' x5

## cspaper.data_modality  [INITIAL; list; filled 192/200; distinct 19]
description: all modality of the input data handled by the system, choose one or more from ['Audio', 'Image', 'Table', 'Text', 'Code'], e.g. Text; Table; Image.
most common values: 'Text' x138; 'Image|| Text' x11; 'Text|| Table' x8; 'Text|| Image' x7; 'Text|| Code' x6; 'Audio|| Text' x5; 'Code' x2; 'Text|| Image|| Table' x2; 'Text|| Table|| Image' x2; 'Text|| Image|| Audio' x2

## cspaper.evaluation_dataset  [new; free text; filled 193/200; distinct 184]
description: name of the dataset(s) used for evaluation in the experiments, list all the datasets mentioned in the text.
most common values: 'Natural Questions|| TriviaQA' x4; 'HotpotQA' x4; 'MIMIC-III' x2; 'TeleQnA' x2; 'Natural Questions|| TriviaQA|| HotpotQA|| 2WikiMultihopQA' x2; 'Internal HR and QA documents' x1; 'FAQ dataset' x1; 'Washington state dataset' x1; "Custom QA dataset based on 'Introduction to Current Korean M" x1; 'MufassirQAS' x1

## cspaper.evaluation_metric  [new; free text; filled 193/200; distinct 176]
description: all the evaluation metric(s) reported in the experiments (e.g.,  Perplexity; BLEU; ROUGE; F1; recall@1).
most common values: 'Accuracy' x10; 'EM|| F1' x4; 'EM|| F1|| Accuracy' x2; 'Accuracy|| Precision|| Recall|| F1-score' x2; 'Recall' x2; 'Accuracy|| Precision|| Recall|| F1 Score' x2; 'F1' x2; 'Context Retention|| Coherence|| Accuracy (%)|| Processing Ti' x1; 'top-1 accuracy|| top-3 accuracy|| Accuracy' x1; 'Accuracy|| Succinctness|| Correctness' x1

## cspaper.generator_model  [new; free text; filled 185/200; distinct 164]
description: name of the generation models used in the system (e.g., GPT-4o-mini, LLaMa2-7B-Chat), list all the baselines mentioned in the text.
most common values: 'GPT-4o' x13; 'GPT-4' x5; 'gpt-3.5-turbo-16k-0613' x2; 'gpt-3.5-turbo' x2; 'GPT-3.5' x2; 'LLaMA-2-7B' x2; 'Qwen2.5-7B-Instruct' x2; 'GPT-3|| GPT-4|| LLaMA2|| LAMBADA|| PALM' x1; 'GPT-4|| Llama2-13B' x1; 'GPT-4|| GPT-3.5-turbo' x1

## cspaper.multi_turn_retrieval  [INITIAL; yes/no; filled 199/200; distinct 2]
description: whether the method explicitly supports multi-turn retrieval. Only choose one from ['Yes', 'No'].
most common values: 'No' x141; 'Yes' x58

## cspaper.paper_name  [INITIAL; free text; filled 200/200; distinct 200]
description: 
most common values: 'Enhancing Multilingual Information Retrieval in Mixed Human ' x1; 'Reinforcement Learning for Optimizing RAG for Domain Chatbot' x1; 'RAG-vs-Fine-tuning-Pipelines-Tradeoffs-and-a-Case-Study-on-A' x1; 'Prompt-RAG: Pioneering Vector Embedding-Free Retrieval-Augme' x1; 'Improving LLM Reliability with RAG in Religious Question-Ans' x1; 'REALM: RAG-Driven Enhancement of Multimodal Electronic Healt' x1; 'The Good and The Bad: Exploring Privacy Issues in Retrieval-' x1; 'RAGged Edges: The Double-Edged Sword of Retrieval-Augmented ' x1; 'Dynamic Contexts for Generating Suggestion Questions in RAG ' x1; 'FIT-RAG: Black-Box RAG with Factual Information and Token Re' x1

## cspaper.performance_on_NQ  [new; free text; filled 0/200; distinct 0]
description: the result or performance of the method on the Natural Questions (NQ) benchmark. Extract any reported metric(s) or qualitative descriptions. Use short free-form text if no specific numbers are given.
most common values: 

## cspaper.performance_on_hotpotqa  [new; list; filled 31/200; distinct 31]
description: the result or performance of the method on the HotpotQA benchmark. Extract any reported metric(s) such as F1, EM, accuracy, or other values. If multiple metrics are provided, separate them with `||`. If only qualitative descriptions are given (e.g., 'outperforms baseline'), extract them in short free text.
most common values: 'F1: 62.6' x1; 'KILT-EM: 27.3 (T5-Base)|| KILT-EM: 31.1 (T5-XL)' x1; 'EM: 0.303|| F1: 0.3066' x1; 'EM: 48.58|| F1: 62.87|| Acc: 55.68' x1; 'EM (x4 compression): 0.430|| EM (x16 compression): 0.426|| E' x1; 'F1: 57.59|| Hit Rate: 50.00' x1; 'F1: 40.8' x1; 'EM: 63.3|| F1: 76.9' x1; 'Accuracy: ~0.62' x1; 'Gemma-2b: EM 21.8, ACC 39.4|| Mistral-7b: EM 22.4, ACC 38.6' x1

## cspaper.reasoning_depth  [new; category; filled 198/200; distinct 3]
description: reasoning path length in the application scenarios of the method by the main task or benchmark, choose one from ['single-hop', 'multi-hop'].
most common values: 'multi-hop' x109; 'single-hop' x88; 'single-hop|| multi-hop' x1

## cspaper.retrieval_method  [INITIAL; category; filled 199/200; distinct 26]
description: primary retrieval method used to obtain supporting information, choose one from ['Dense Retrieval', 'Graph-based Retrieval', 'Hybrid Retrieval', 'Sparse Retrieval', 'Web Search', 'other'].
most common values: 'Dense Retrieval' x101; 'Hybrid Retrieval' x23; 'Other' x13; 'Graph-based Retrieval' x12; 'Sparse Retrieval' x9; 'Web Search' x6; 'Dense Retrieval|| Sparse Retrieval' x6; 'Dense Retrieval|| Graph-based Retrieval' x5; 'Graph-based Retrieval|| Dense Retrieval' x4; 'Sparse Retrieval|| Dense Retrieval' x2

## cspaper.topic  [INITIAL; category; filled 200/200; distinct 5]
description: the main research area or technique discussed in the paper, choose one from ['Information Retrieval', 'Retrieval-Augmented Generation', 'Data Selection', 'SFT'].
most common values: 'Retrieval-Augmented Generation' x193; 'Data Selection' x3; 'Information Retrieval' x2; 'No' x1; 'SFT|| LLM' x1

## cspaper.use_agent  [new; yes/no; filled 200/200; distinct 2]
description: whether the system explicitly adopts an agent-style architecture (e.g., tool-calling or multi-step planning) rather than a single forward pass, choose one from ['Yes', 'No'].
most common values: 'No' x153; 'Yes' x47

## cspaper.uses_knowledge_graph  [INITIAL; yes/no; filled 199/200; distinct 3]
description: whether the method explicitly incorporates a knowledge graph as part of retrieval or reasoning choose one from ['Yes', 'No'].
most common values: 'No' x166; 'Yes' x32; 'single-hop' x1

## cspaper.uses_reranker  [INITIAL; yes/no; filled 195/200; distinct 3]
description: whether the system uses an explicit reranker stage to re-score retrieved candidates before generation, choose one from ['Yes', 'No'].
most common values: 'No' x132; 'Yes' x62; 'Text' x1

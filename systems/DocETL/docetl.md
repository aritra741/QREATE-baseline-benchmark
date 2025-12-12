# DocETL: Agentic Query Rewriting and Evaluation for Complex Document Processing

Shreya Shankar<sup>1</sup>, Tristan Chambers<sup>2</sup>, Tarak Shah<sup>2</sup>, Aditya G. Parameswaran<sup>1</sup>, Eugene Wu<sup>3</sup>

<sup>1</sup>UC Berkeley EECS, <sup>2</sup>BIDS Police Records Access Project, <sup>3</sup>Columbia University

{shreyashankar,tristan.chambers,tarak_shah,adityagp} @berkeley.edu, ewu@cs.columbia.edu

# Abstract

Analyzing unstructured data has been a persistent challenge in data processing. Large Language Models (LLMs) have shown promise in this regard, leading to recent proposals for declarative frameworks for LLM-powered processing of unstructured data. However, these frameworks focus on reducing cost when executing user-specified operations using LLMs, rather than improving accuracy, executing most operations as-is (in a single LLM call). This is problematic for complex tasks and data, where LLM outputs for user-defined operations are often inaccurate, even with optimized prompts. For example, an LLM may struggle to identify all instances of specific clauses, like force majeure or indemnification, in lengthy legal documents, requiring decomposition of the data, the task, or both.

We present DocETL, a system that optimizes complex document processing pipelines, while accounting for LLM shortcomings. DocETL offers a declarative interface for users to define such pipelines and uses an agent-based approach to automatically optimize them, leveraging novel agent-based rewrites (that we call rewrite directives), as well as an optimization and evaluation framework. We introduce (i) logical rewriting of pipelines, tailored for LLM-based tasks, (ii) an agent-guided plan evaluation mechanism that synthesizes and orchestrates task-specific validation prompts, and (iii) an optimization algorithm that efficiently finds promising plans, considering the latencies of agent-based plan generation and evaluation. Our evaluation on four different unstructured document analysis tasks demonstrates that DocETL finds plans with outputs that are 21 to  $80\%$  more accurate than well-engineered baselines. DocETL is open-source at docetl.org, and as of March 2025, has amassed over 1.7k GitHub Stars, with users spanning a variety of domains.

# 1 Introduction

Large Language Models (LLMs) have taken the world of data management by storm, with applications ranging from data integration, to tuning, to query optimization, to data cleaning [13]. There has also been an interest, all in the last few months, in declarative approaches to process unstructured data using LLMs [1, 28, 29, 37]. These systems, instrumented as extensions to the relational model for processing textual columns, typically assume the text snippets per row are small and easy to process. They therefore focus on reducing cost, while keeping accuracy almost the same. However, for many real-world tasks, that we refer to as complex document processing tasks, accuracy can be a significant bottleneck, limiting practical utility. Here, complexity can stem from the documents or the nature of the processing task, or both. Consider this scenario from our collaborators on the Police Records Access Project<sup>1</sup>:

Example 1.1 (Police Misconduct Identification). Journalists at Berkeley's Investigative Reporting Program want to analyze a large corpus of heterogeneous police records, obtained through records requests, to uncover patterns of misconduct and procedural violations. Records include police reports, court transcripts, internal affairs and medical examiner reports, and other case files, often spanning hundreds of pages each. Analysis involves extracting key information from long documents, aggregating information across documents to identify behavioral patterns for each officer, and generating summaries highlighting concerning trends.

Example 1.1 is representative of complex document processing tasks across domains including law, medicine, and social science. Consider a simpler version of this task, where we just want a summary of the role of each officer mentioned in each complex police record document, each with hundreds of pages. This task can be expressed as a single-step map operation applied to the OCR output per document, in one LLM call, with a user-provided prompt defining terms like "misconduct." All existing systems [1, 28, 29, 37] would simply execute the map operation, as is, with one LLM call per document. That is, they assume user-defined operations will yield sufficiently accurate results when executed by the LLM, and focus primarily on reducing cost. However, this map operation may provide poor accuracy for multiple reasons. First, the document in question may exceed the LLM's context limit. Even if it fits, outputs may omit certain instances of misconduct, or include spurious information. Recent work has shown that LLM performance degrades considerably as length increases [26], because they can be distracted [43] or selectively pay attention to certain portions [30], failing to gain a holistic understanding [4, 22, 45, 53]. Simultaneous theoretical work has shown that this degradation is due to limits in the transformer architecture [23, 38, 44]. While one could apply prompt compilation [25, 50] to identify a better prompt, this relies on examples, which are either not present or are too long to include (e.g., an example document with hundreds of pages)—but irrespective do not fix the underlying challenges with LLMs performing a complex task on complex documents.

Our key insight is that the quality of LLM outputs is often not adequate for complex data processing—we cannot simply treat the existing user-provided operators as fixed. Instead, we need to consider novel rewrites that decompose complex but error-prone operation(s) into a sequence of simpler and more accurate operations. For our map example, a different sequence of operations may increase accuracy. One such example is  $map \rightarrow map$ , where the first map is tasked with removing all portions of each input document that do not pertain to misconduct (e.g., medical reports), while the second map is the single-step map above. Or we could replace the first map with one that summarizes each sequence of  $k$  paragraphs into one, keeping the second map as is. Yet another

![](images/7c47cc2fe8308fb1d66a617b09f2fefbe70534573fcf031f8ed79cf4efc94bc1.jpg)  
Figure 1: Optimization for a pipeline designed to accomplish the task in Example 1.1. The diagram illustrates the system mid-optimization of the initial map operation. DocETL employs LLMs to synthesize new plans using novel rewrite directives. The process begins with an LLM verifier determining if an operation is sufficiently optimized. If not, rewriting continues. Notably, when a new operation is synthesized as part of a rewrite, it undergoes immediate opportunistic optimization, as shown by the nested "Apply Rewrites (Agent)" rectangles.

option is to replace the single-step map with what we call split  $\rightarrow$  gather  $\rightarrow$  map  $\rightarrow$  reduce-a pattern that first splits the document into contiguous chunks; then, for each chunk, gathers  $k$  neighboring chunks before/after as context or background to be included into a prompt, generates per-officer summaries using its  $2k$  neighbors as background context (map); and finally, performs a global summarization across all chunks (reduce).

However, we cannot expect a user to rewrite their pipeline into multiple alternatives and determine the one with the best performance. The previous paragraph introduced three out of a multitude of potential rewrites, each of which could be recursively applied to operators in a pipeline, presenting a seemingly infinite set of options. For example, for the map  $\rightarrow$  map pipeline, there are many alternatives for what the first map could do, and many different associated prompts. Even if we decide to use the first map to summarize  $k$  chunks at a time, determining the right value for  $k$  is challenging. Likewise for split  $\rightarrow$  gather  $\rightarrow$  map  $\rightarrow$  reduce. Moreover, we're just focusing on the first step of the overall goal in Example 1.1, which is to summarize misconduct across all documents. So, we may need to apply a reduce operation across documents to group and summarize misconduct extractions by officer. However, the same officer may be extracted as "Officer Smith" in one document and "J. Smith" in another, resulting in separate, incomplete summaries for what should be a single officer [36]. It's not entirely clear how one would implement this form of entity resolution, and no current systems support it. In fact, additional context from the original document(s) may be necessary to determine if the two officers with the same name are identical. Finally, LLMs might struggle to recognize that multiple documents are from the same case, leading to overrepresentation of incidents in the misconduct summaries [48]. Overall, even an LLM expert would need extensive experimentation to design an accurate pipeline, given the dependency on the data, task, and LLM capabilities. This complexity underscores the need for a system that can automatically explore and evaluate different task decomposition strategies to find the most effective pipeline for a given task and dataset.

We present DocETL, our first attempt at developing a declarative system optimized for accurate complex document processing. DocETL provides a declarative YAML-based interface for users to author pipelines with LLM-specific operators, including two new ones: resolve for entity resolution, and gather to maintain context when processing document chunks. Users can specify their pipeline at a high level with DocETL decomposing, rewriting, and optimizing the pipeline. DocETL introduces an agent-based framework to rewrite user-specified pipelines into alternative ones, as shown in Figure 1. Rather than simply relying on agents as-is, which can be error-prone, we guide them to rewrite query plans using novel rewrite directives that we identify. We call these directives instead of rules because they are abstract guidelines interpreted by LLMs based on task and data characteristics, with infinitely many concrete instantiations. We further leverage an agentic framework to evaluate the resulting pipelines. Since evaluation can be expensive, we develop an optimization approach inspired by Cascades [16], where we use a top-down rule-based strategy to generate and evaluate a space of equivalent plans, opting to opportunistically decompose (or rewrite) complex or error-prone operations into simpler ones.

DocETL is open-source and available on GitHub<sup>2</sup>. As of March 2025, it has already amassed  $1.7\mathbf{k}+$  GitHub stars, and has been used for pipelines ranging from domain-specific analysis (e.g., legal, climate science) to enterprise and personal productivity (e.g., analyzing customer support tickets, emails); over 400 users have joined the corresponding Discord server.

Overall, finding optimal complex data processing pipelines is impossible given the infinite search space, non-determinism of LLMs, fuzziness of text, and ambiguity in task-specific success criteria. However, even in these difficult settings, DocETL is able to produce pipelines that are sufficiently accurate for practical needs, as is evidenced by our adoption across domains. DocETL is able to do so by leveraging the power of LLM agents in constrained ways, in conjunction with a powerful, but compact set of rewrite directives,

decomposition into processing units that can be validated, as well as an opportunistic top-down exploration of the search space.

We make the following contributions in this paper:

(1) Novel Rewrite Directives and Agent-Driven Rewriting: We identify 13 new rewrite directives designed for LLM-based operators, addressing challenges unique to complex document processing. Unlike traditional rewrite rules, LLM agents are used to implement these directives. When a rule applies to a portion of a pipeline, agents synthesize appropriate prompts and parameters for new operations. For example, when decomposing a "summarize instances of misconduct" operation into multiple ones, an agent might create two steps: first, "list instances of misconduct given specific types (e.g., excessive force)," followed by "summarize each listed instance," crafting suitable prompts for each new operation. (2) Agent-Driven Plan Assessment: We also use LLM agents to synthesize task-specific validation prompts for each operation, which are used to assess output quality. For instance, to verify a misconduct summary, an agent might create a prompt, "Does this summary include all instances of misconduct from the document?" Or, "Do all mentioned instances actually exist in the document?" The agents then execute plans on sample data and evaluate outputs using these custom prompts. This entire process happens without the user having to provide or manually validate examples.

(3) Opportunistic Sub-plan Optimization: Unlike traditional query optimizers that generate and evaluate a broad range of possible plans [6], we leverage an opportunistic top-down search strategy as shown in Figure 1: when we use a rewrite directive to decompose operators into new ones, we immediately optimize each new operator. We first check if each such operator is sufficiently accurate, based on the validation as described previously. If sufficiently accurate, we no longer optimize that operator, focusing instead on rewriting others. Thus, we opportunistically decompose (or apply rewrite directives to) operators that are not sufficiently accurate. Such an approach is necessary because enumerating and evaluating all theoretically-possible plans would be prohibitively time-consuming due to the inherent latencies in LLM operations.

We describe DocETL's programming model and operators in Section 2; our new LLM-centric rewrite directives in Section 3, the agentic optimizer that applies them, and evaluates the resulting plans, as well as the overall framework for optimization in Section 4. We present our initial evaluation in Section 5, where we demonstrate that across four unstructured document analysis tasks, DocETL finds plans that are 21 to  $80\%$  more accurate than baselines. We then reflect on next steps in Section 6, and discuss related work in Section 7.

# 2 DocETL DSL and Operators

This section presents DocETL's programming model and operators.

# 2.1 Programming Model

DocETL processes collections of documents. A document comprises a set (or dictionary) of key (or equivalently, attribute)-value pairs, represented as a JSON object. For example, a police record could be a set of key-value pairs, where one key corresponds to the OCR output of the PDF, while other keys could capture metadata such as agency, file name, or creation date. A collection of documents or dataset, is a JSON array. This data representation lets us handle

various data types and degrees of structure and easily reference data within operation prompts. Documents can be nested, e.g., a police record may contain an array of related_documents that each contain witness statements or evidence logs that are further nested.

DocETL DSL. DocETL employs YAML as its domain-specific language (DSL) to define data processing pipelines, for several reasons. First, YAML is flexible in accommodating complex multi-line prompts and examples, as well as output schemas and validation mechanisms, while intermixing formatting with arguments in Jinja [34]. Second, YAML is human-readable and doesn't require extensive coding expertise. Third, it is commonly used in industry for describing data pipelines (Apache Airflow, dbt, Prefect) and services (Kubernetes, Docker, Circle/Gitlab CI/CD). Finally, YAML serves as a simple intermediate format for representing the DocETL-optimized pipelines for human inspection, as well as for our no-code interface, where users will provide data and natural language descriptions, with DocETL generating optimized pipelines. That said, our optimization techniques are not dependent on YAML and are also applicable to other frameworks.

DocETL Pipelines. A DocETL pipeline, expressed in YAML, describes a sequence of operations. Each operation specifies its operator type, input source, prompt template, and output schema. The input source can be either the original dataset or the output of a previous operator. We refer to this input using pre-defined variables input or inputs depending on whether the input cardinality is one or many. A global default model can be specified, and individual operators can override this setting. The pipeline begins with dataset definitions, which serves as the initial input. As operators process data, they generate output obeying their schemas, which subsequent operators can then use. This structure allows for flexible and modular pipeline composition. DocETL supports a default model for the entire pipeline, with the option for per-operation model specifications.

Fault Tolerance. When executing an LLM-powered operator for many input documents in a pipeline, some operations may occasionally fail to adhere to the given prompt. While prior work assumes reliability in LLM outputs [1, 29, 37], DocETL explicitly addresses this variability: for each operator, users can specify validations as Python statements that evaluate to true or false, referencing document and output attributes. If any validation fails, the operation retries, using context from the failure to improve the likelihood of success in subsequent attempts.

# 2.2 LLM-Powered Operators

Here, we describe the LLM-powered operators in DocETL and any specific implementation details for executing them with LLMs. Table 1 summarizes our operators; detailed syntax can be found in our documentation<sup>3</sup>. Most operators are LLM-versions of classic data processing operators, however, we introduce a new resolve operator, used to canonicalize variations in specific attribute values. In the following, for succinctness of description, we often conflate a document—a JSON object comprising key-value pairs and the basic unit of processing in a dataset with its textual content, typically a value for a specific key within the JSON object.

Table 1: DocETL's operator suite, divided into operators that leverage LLMs for semantic processing and auxiliary operators (*) that handle data manipulation. For each operator, we show the required user configuration and a high-level description of its functionality.  

<table><tr><td>Operator</td><td>User Configuration</td><td>Description</td></tr><tr><td>Map</td><td>Prompt, output schema</td><td>Uses an LLM to execute a transformation per document, adding resulting new keys to the schema (and optionally omitting existing ones).</td></tr><tr><td>Parallel Map</td><td>Multiple prompts, output schemas</td><td>Uses an LLM to execute multiple independent transformations on each document in parallel, adding the new keys to the schema.</td></tr><tr><td>Reduce</td><td>Group-by keys, prompt, output schema</td><td>Uses an LLM to aggregate groups of documents sharing the same key values into one new document per distinct value.</td></tr><tr><td>Filter</td><td>Prompt returning boolean</td><td>Uses an LLM to evaluate a condition per document, retaining only those where the condition is true.</td></tr><tr><td>Resolve</td><td>Comparison prompt, resolution prompt</td><td>Uses an LLM to identify values for a given key(s) that fuzzily match across documents and generate canonical versions per group of values, replacing them in-place in the documents.</td></tr><tr><td>Equijoin</td><td>Comparison prompt</td><td>Uses an LLM to determine if pairs of documents from two datasets should be joined based on fuzzy/semantic matching of the corresponding keys.</td></tr><tr><td>Unnest*</td><td>Array/dict field to unnest</td><td>Flattens nested data structures by either creating separate documents from array elements or merging nested dictionary fields into parent documents.</td></tr><tr><td>Split*</td><td>Split key, chunk size</td><td>Divides documents into smaller chunks based on token count or other criteria, creating as many new docs as there are chunks.</td></tr><tr><td>Gather*</td><td>Context window configuration</td><td>Augments each chunk with context from surrounding chunks based on specified configuration (e.g., previous and next chunk counts), keeping the set of documents the same.</td></tr></table>

2.2.1 Map The map operator applies an LLM-powered projection, also known as a semantic projection, to each document in the dataset. Let's consider an example of a map operation:

```txt
1 - name: extractofficer_misconduct   
2 type: map   
3 output: schema: misconduct:"list[{officer_name: str, misconduct_instance: str}]   
6 prompt: Analyze the following police record: {input.document}   
9 Extract any instances of officer misconduct or procedural violations. For each instance, provide the name of the officer involved and a brief description of the misconduct or violation.
```

This operation processes each document independently, using the specified prompt. The output schema is a list of key-value pairs (of officer names and misconduct instances). This flexible, semi-structured output format allows for varying numbers of misconduct instances per document. DocETL supports prompts using Jinja2 templates, where “{input.document}” allows for insertion of the current document's content. This functionality permits complex prompts with conditional logic (as we will see later). When applied, the map operation adds the new attributes specified in the output schema to the existing document. Users can override this behavior and return a subset of attributes by specifying a drop_keys list.

DocETL also supports parallel maps, where multiple independent transformations can be applied in parallel to each document. For example, one may extract misconduct while another summarizes relevant policies. Each operation enriches input documents with new attributes and can run in parallel rather than serially. While users could technically use a map to specify a parallel map, in many cases, they already have prompt templates corresponding to two or more independent tasks on the same dataset, and this allows them to not have to coalesce their prompts together.

2.2.2 Reduce The reduce operator aggregates information across multiple documents based on a set of user-specified keys, ultimately producing one output document per unique combination of attribute values. This operation is particularly useful for consolidating information spread across multiple related documents. For instance, for reducing police reports, the key set might include officer_name and incident_date, allowing for the grouping of all reports involving a specific officer on a particular date. Users can define prompt templates that access the grouped documents via {{ inputs }} (a list of documents sharing the same key values) and the specific key values for the current group via {{ reduce_key }}. By default, reduce operations are assumed to be associative, meaning that the order in which documents are processed does not affect the result. However, if the order is significant, users can specify associative: False in the operation definition.

![](images/1724b4868f22dd6fd8db9bc0895743a9e34d5f19f03a2f5d40887a80c2635c7e.jpg)  
Figure 2: Reduce's iterative folding over 3 batches of documents. Each batch takes several documents and the current scratchpad as input (left), and updates the mention counts in the scratchpad and accumulated output of entities mentioned multiple times (right).

A challenge arises when any given group of documents is too large for the LLM to correctly process. One could use folding or hierarchical merging to process the data in manageable batches [8, 17]. In folding, each input is serially processed, with an update to an accumulator (or aggregate), while hierarchical merging recursively aggregates inputs in a tree-like structure. DocETL currently implements a batched folding approach that starts with an empty accumulator and sequentially folds in batches of more than one document at a time. We chose folding because it permits non-associative reduce operations and maintains the original order of inputs. For example, when summarizing a textbook chapter, DocETL may chunk the text into sections(where a chunk is a portion of text that an LLM can reliably process), summarize each one, and then employ reduce to summarize the section summaries—a process that requires preserving the original reading order. DocETL automatically determines an optimal fold batch size when building the pipeline.

To implement folding, users can provide (or DocETL can generate) a separate fold_prompt, which references the accumulated output and a batch of new inputs to fold into that output. We enhance the system prompt to allow the LLM to write extra notes to a scratchpad [33]—a technique that has been shown to improve accuracy by allowing it to maintain state. During each LLM call, we provide the current scratchpad along with the accumulated output and new inputs. The LLM returns both the updated accumulated output and scratchpad, which are passed to the next fold operation. Figure 2 depicts folding for a task to identify names of people mentioned more than once across documents. The scratchpad tracks all mentions of names. As each batch is processed, the LLM updates the scratchpad with new mentions and adds to the accumulated output any person now mentioned more than once.

2.2.3 Resolve This operator canonicalizes one or more keys across documents that represent slight variations of the same entity. for subsequent grouping and aggregation. Here, resolve reconciles

small variations in officer names extracted as part of the map described in Section 2.2.1:

```yaml
1 - name: resolveoffsicer_names   
2 type: resolve   
3 comparison_prompt: |   
4 Compare the following two officers from police records. Officer 1: \{input1.officer_name} mentioned in:{input1_record txt} and Officer 2:{input2.officer_name} mentioned in:{input2.record txt} Are these names likely referring to the same officer?   
5 resolution_prompt: |   
6 The following names correspond to the same officer:   
7  $\{\%$  Name:{entry.officer_name}   
8  $\{\%$    
9 Provide an officer name (first and last) that best represents all the matched entries.   
11 output:   
12 schema:   
13 officer_name: string
```

The user simply specifies how to detect variations, and how to canonicalize them. For instance, "comparison_prompt" checks whether two officer names are the same, while "resolution_prompt" chooses a canonical officer name from a list. DocETL then uses these prompts to compare and resolve the officer names. After this operation, the number of documents stays the same. The output schema specifies attributes to replace or add (if new) to each document. Resolve often follows unnest (Section 2.3.1), which flattens nested data structures. For example, in our police misconduct pipeline, after unnesting, each document would have distinct officer_name and misconduct_instance keys, allowing for name resolution across all mentions in the dataset. Note that users don't need to explicitly define the resolve operation in their pipeline; DocETL will automatically synthesize them if needed to ensure consistent entity references across the dataset. We will discuss how DocETL assesses the benefit of such rewrites in Section 4.1.

2.2.4 Other Operators While expressible using map and reduce, the following operators are added for convenience. We plan to add other operators (e.g., sort) in the future. Filter retains documents based on a condition specified in an LLM prompt, which uses a Jinja2 template referencing one or more document keys. Equi-join joins two datasets by comparing documents in pairs, using a comparison_prompt designed to elicit a binary answer from the LLM, referencing the documents as left and right. The equijoin operation doesn't require an output schema, as the left and right documents are merged to produce the results.

# 2.3 Auxiliary Operators

We present three essential operators that are not powered by LLMs, used as auxiliary steps to express complex tasks.

2.3.1 Unnest Theunnest operator expands an array or dictionary into individual elements. For example, if a map extracts multiple officer names from police interrogation transcripts, each document may contain an array of names. To analyze officers individually across multiple interrogations,unnest creates a separate document for each officer name, effectively flattening the data. This operation can also elevate attributes from nested dictionaries, making them directly accessible for downstream processing.  
2.3.2 Split The split operator divides long text into smaller chunks. It requires a split key (the text attribute), a split method (token or

delimiter), and method-specific parameters (e.g., delimiter or chunk size). An example is as follows:

```yaml
1 - name: document_splitter  
2 type: split  
3 split_key: document_text  
4 method: token_count  
5 method_kwargs:  
6 num_tokens: 1000
```

The above operation splits the document_text attribute into chunks of 1000 tokens each. The split operation produces several output attributes per chunk:

(1) The <split_key>_chunk attribute contains the chunk content. Here, the chunk content is stored in document_text_chunk.  
(2) The <operation_name>_id attribute contains a unique identifier assigned to each original document (before splitting). In this case, it would be doc_splitter_id. All chunks from the same original document share the same ID.  
(3) The <operation_name>_chunk_num attribute contains the sequential number of each chunk within its original document. Here, it would be doc_splitter_chunk_num.

These additional attributes, particularly the document ID and chunk number, are used in downstream gather operations, to reassemble or process the chunks in context. New documents (the result of the split operation) inherit the other attributes from the original documents.

2.3.3 Gather The gather operation complements the split operation by augmenting individual chunks with peripheral information necessary for understanding the chunk's content. Conceptually, gather is similar to windowing in SQL, as both allow ordered access to data beyond the current row or chunk, but gather is specifically designed for LLM-based processing. For example, in a transcript split into chunks, a chunk containing pronouns (e.g., "he" or "she") may lack speaker names, making it hard to understand. Gather allows flexible configuration of which peripheral context to include with each chunk, such as:

```yaml
1 - name: context_gatherer:  
2 type: gather  
3 content_key: document_text_chunk  
4 peripheralChunks:  
5 previous:  
6 head:  
7 count: 1  
8 content_key: document_text_chunk  
9 middle:  
10 content_key: document_text_chunk_summary
```

This particular configuration includes the full content of the document's first chunk, summaries of intermediate chunks, and the current chunk itself. Figure 3 demonstrates different ways to render chunks. The gather operation is highly flexible in rendering contextual information, allowing for the inclusion of full chunks (as in (ii)), portions of chunks (as in (i)), or transformations (e.g., summaries) of chunks (as in (iii)). Importantly, there may be map operations between the split and gather steps—allowing for the generation of additional context (such as summaries) that can be used to augment each chunk, before downstream processing. The output adds a new attribute to each input document, containing the rendered chunk with its peripheral context, with special tags

![](images/7f1d8370235280535c8768034e42ebdbcbc0ee8f1cd4cab21fa9c2f7bba6718a.jpg)  
Figure 3: Split-Gather Pipeline: Illustration of processing a single long document. The split operation divides a long document into manageable chunks. The gather operation then augments each chunk with relevant context from peripheral chunks. The image demonstrates three different ways of rendering chunk 3 (i.e., three different gather configurations): (i) including fractional parts of surrounding chunks, (ii) including the full content of the first chunk, and (iii) including summaries of all previous chunks.

![](images/df35c592d9d7eb4c9bc8627ea5c8aab01a7c7510ce1ddecec8a2225d5fda89fc.jpg)

![](images/102939c6c1aeda22411a544e2dbab958e3905ea3236a5edf97e52b1ddce87c2d.jpg)

that demarcate what is the chunk and what is peripheral context. For additional details, see Appendix A.

Overall, in designing the DocETL DSL, we unified various single-document transformations (e.g., extraction, summarization) under map and filter operators, letting users express intent through prompts rather than learning multiple specialized operators. But for cross-document operations, we created distinct operators that capture specific processing patterns. For example, while resolve could theoretically be implemented using equi join, reduce, and another equi join, having a dedicated operator allows us to know that the user's intent is actually entity resolution, so we can better optimize the pipeline. Additionally, we distinguish gather from reduce because they serve different purposes: reduce performs many-to-one aggregation, whereas gather preserves cardinality while enriching documents with context—similar to SQL windowing functions.

# 3 Rewrite Directives

We now introduce the rewrite directives that DocETL currently supports. We call these directives to indicate that they are abstract frameworks, with somewhat ambiguous semantics, that can be concretely instantiated by LLM agents in a multitude of ways, as opposed to rules, which are more concrete, complete, and robust. These directives are primarily designed to optimize the quality of outputs from DocETL pipelines through logical decomposition of individual operations. We focus on rewrite directives for map, reduce, and equijoin operators, with filter operators also supported through the application of map rewrite directives. We organize our rewrite directives into three main categories: data decomposition, projection synthesis, and LLM-centric improvements.

Throughout this section, we adopt the following notation: given operators  $A$  and  $B$ , we denote their composition as  $A \rightarrow B$ , where  $(A \rightarrow B)(D) = B(A(D))$ . For independent execution of operators, we use  $A \parallel B$  to indicate that  $A$  and  $B$  are executed on the same input, independently. For readability, we may drop arguments—e.g.,  $\operatorname{Map}_x(D)$  becomes  $\operatorname{Map}_x$ . Similarly, we omit subscripts except when the same operator appears in multiple places. We further refer to the text content of the document, usually stored as one of the attributes, interchangeably with the document itself, for simplicity. The arrow  $\Rightarrow$  denotes a (semantic) rewrite of the operator (or operator sequence) on the left into the form on the right.

As mentioned previously, the actual instantiation and application of these directives are carried out by LLMs, which interpret the directives in the context of specific tasks and data. The benefits of each directive are also assessed by LLMs, as we can't know in advance if a directive will be helpful in a given situation. LLM agents evaluate the potential impact of each directive based on task requirements (i.e., prompts) and data characteristics, as we will discuss in Section 4. Next, we cover each category of directives.

# 3.1 Data Decomposition

Data decomposition is crucial when dealing with large documents, or when there are too many documents to fit in a prompt and get an accurate result for. We present two categories of rewrite directive here: document chunking and multi-level aggregation.

3.1.1 Document Chunking (Map) Large documents often exceed LLM context windows or effective reasoning capabilities, leading to incomplete or inconsistent results. Our primary rewrite directive for this case, which we call the split directive, is:

$$
\operatorname {M a p} _ {x} \Rightarrow^ {(2)} \text {S p l i t} \xrightarrow {(3)} \text {G a t h e r} \xrightarrow {(4)} \operatorname {M a p} _ {y} \xrightarrow {(5)} \text {R e d u c e} \tag {1}
$$

Ignoring the purple annotations, this directive rewrites map to: split the document into multiple chunks, gather peripheral context for each chunk, apply a modified map operation per chunk, and reduce the results. The prompt for  $\mathrm{Map}_y$  may explicitly state that only a portion of the original document is being processed. To provide more flexibility and optimization opportunities, we introduce smaller decomposition directives, for steps (2)-(5) above:

$$
\operatorname {S p l i t} \Rightarrow \operatorname {M a p} \rightarrow \operatorname {S p l i t} \tag {2}
$$

$$
\text {S p l i t} \rightarrow \text {G a t h e r} \Rightarrow \text {S p l i t} \rightarrow \left(\operatorname {M a p} _ {s} \| \operatorname {M a p} _ {h}\right)\rightarrow \text {G a t h e r} \tag {3}
$$

$$
\text {G a t h e r} \Rightarrow \text {G a t h e r} \rightarrow \text {F i l t e r} \tag {4}
$$

$$
G a t h e r \rightarrow \mathrm {M a p} \Rightarrow G a t h e r \rightarrow \mathrm {M a p} \rightarrow \text {U n n e s t} \tag {5}
$$

When splitting a document, three types of context prove particularly useful: document-level metadata, hierarchical information, and summaries of neighboring chunks. The smaller decomposition directives address these and other aspects of document processing:

- Document-Level Metadata Extraction (2): This directive introduces a map immediately prior to splitting, enabling the extraction of metadata relevant to all chunks. For example, when analyzing a legal contract, we might extract the contract date and parties involved from the first page, passing this information to every chunk to be rendered as part of a subsequent gather.  
- Header Lineage Context and Summarization (3): This directive introduces two independent map operations:  $\mathrm{Map}_h$  for extracting hierarchical information (e.g., headers), and  $\mathrm{Map}_s$  for generating summaries of chunks. This allows us to provide each chunk with its relevant hierarchical context (e.g., parent headers for headers in a chunk) and/or a summary of preceding content.  
- Chunk Filtering (4): Not all parts of a document may be relevant for processing. This directive introduces a filter step after gathering context, allowing us to exclude irrelevant chunks. This filter can be inferred; for instance, when processing a scientific paper, we might filter out acknowledgments or references sections if they're not pertinent to the analysis task; but they could still be used as context for other chunks if needed.

- Flattening Nested Results (5): When processing chunks with gathered context, map might produce nested results. This directive introduces anunnest operation to flatten these results, simplifying downstream processing. For example, if each chunk produces a list of extracted entities, unnesting would flatten these lists into a single collection of entities across all chunks.

3.1.2 Multi-Level Aggregation (Reduce) Large-scale aggregations can benefit from a hierarchical approach, aggregating data at a finer granularity before rolling up to the desired level. This decomposition is based on a semantic hierarchy in the data:

$$
\operatorname {R e d u c e} _ {K, x} \Rightarrow \operatorname {R e d u c e} _ {K \cup K ^ {\prime}, y} \rightarrow \operatorname {R e d u c e} _ {K, z} \tag {6}
$$

Here  $K$  is the reduce key, e.g.,  $K = \{\text{state}\}$ , and  $K'$  represents additional keys for finer granularity, e.g.,  $K' = \{\text{city}\}$ .  $y$  and  $z$  are LLM-powered aggregations for the sub-reduce and final reduce operations. For example, when summarizing voting patterns by state from social media posts, we might first aggregate data by state and city ( $\text{Reduce}_{\{\text{state}, \text{city}\}, y\}}$ ), then combine these city-level summaries to the state level ( $\text{Reduce}_{\{\text{state}\}, z\}}$ ). This approach can capture nuances that might be lost in a single, large-scale aggregation, and allows for intermediate validation. The effectiveness of this rewrite depends on the specific nature of the data and the aggregation task—the LLM agent must consider the appropriate granularity and design effective prompts for both aggregation steps.

# 3.2 LLM-Centric Improvements

This category addresses unique behaviors of LLMs that can be leveraged for optimization. We present two categories of rewrite directive: gleaning and duplicate resolution.

3.2.1 Cleaning (Map and Reduce) For this directive, we rely on the insight that when prompted with the previous inputs and outputs, and asked to improve the outputs, an LLM can iteratively refine the output. While iterative refinement has been implemented for knowledge graph entity extraction [11], we generalize this concept into a rewrite directive applicable to any map or reduce task. Our approach, which we call cleaning, employs separate data processing and validator LLM steps to iteratively improve output quality. We formalize the cleaning process for map operations as:

$$
\operatorname {M a p} \Rightarrow \operatorname {M a p} \rightarrow \left(\operatorname {M a p} _ {v} \rightarrow \operatorname {M a p} _ {i}\right) ^ {\leq k} \tag {7}
$$

Here,  $k$  represents the maximum number of refinement iterations,  $\mathrm{Map}_v$  is a validation operation, and  $\mathrm{Map}_i$  is a refinement operation. The process works as follows:

(1) Init: run the original map on the input document.  
(2) Eval: separate validator  $(\mathrm{Map}_v)$  checks output based on original prompt, init's output, and a task-specific validation prompt. The validator determines if refinement is needed and describes how to improve the output, if so.  
(3) Refine: we use a refinement map  $(\mathrm{Map}_i)$  to improve the previous iteration's output based on validator feedback. Importantly, this step retains the chat history, including the original prompt, its previous response, and the validator's feedback, so it can iteratively refine.  
(4) Iterate: repeat up to  $k$  times, or no further refinement is needed. A similar approach can be applied to reduce operations:

$$
\operatorname {R e d u c e} \Rightarrow \operatorname {R e d u c e} \rightarrow \left(\operatorname {M a p} _ {v} \rightarrow \operatorname {R e d u c e} _ {i}\right) ^ {\leq k} \tag {8}
$$

For reduce operations, the refinement is applied at the level of a group, not to individual documents. This enables consideration of the collective context of the grouped data.

3.2.2 Duplicate Key Resolution (Reduce) A big challenge in LLM-powered data processing is that grouping, aggregation, and summarization is difficult due to the fact that LLM outputs are not canonicalized, and may contain many semantic duplicates. To address semantic duplicates in reduce keys, especially those derived from LLM-powered operations, we introduce resolve operations:

$$
\operatorname {R e d u c e} _ {K, x} \Rightarrow \left(\operatorname {R e s o l v e} _ {k _ {1}} \| \dots \| \operatorname {R e s o l v e} _ {k _ {m}}\right)\rightarrow \operatorname {R e d u c e} _ {K, x} \tag {9}
$$

Where  $\{k_1, \ldots, k_m\} \subseteq K$  are each a disjoint subset of keys to be resolved. Each  $\mathrm{Resolve}_{k_i}$  operation consolidates semantically equivalent values for the key  $k_i$ . We introduce this rewrite directive to address the inherent variability in LLM outputs: when LLMs are used to generate keys for reduce operations, they may produce semantically equivalent but syntactically different values. For example, "New York City," "NYC," and "The Big Apple" might all refer to the same entity. Without resolution, these would be treated as separate keys, leading to inaccurate aggregations.

# 3.3 Projection Synthesis

Projection synthesis strategies are inspired by projection pushdown optimizations in database systems. While selections (and selection pushdown) can also be synthesized, we did not implement this, as we found that agents are not very effective at determining whether certain data could be relevant to the query (they are overly biased by prompt wording and tend to be overly inclusive). Moreover, since an LLM-based selection is just as costly as a map, as both require an LLM call for every document, we focused on map operations that shrink the size of documents through a form of projection. With LLM agents, we can dynamically synthesize projections to "push down" based on the specific task and data at hand. However, programming LLM agents to synthesize these effectively is not straightforward, as there are potentially infinite projections that could be synthesized without necessarily improving pipeline accuracy or output quality. We present several instances of projection synthesis directives:

$$
\operatorname {M a p} _ {x} \Rightarrow \operatorname {M a p} _ {x _ {1}} \rightarrow \operatorname {M a p} _ {x _ {2}} \rightarrow \dots \rightarrow \operatorname {M a p} _ {x _ {n}} \tag {10}
$$

$$
\operatorname {M a p} _ {y} \Rightarrow \left(\operatorname {M a p} _ {y _ {1}} \| \operatorname {M a p} _ {y _ {2}} \| \dots \| \operatorname {M a p} _ {y _ {m}}\right)\rightarrow \text {R e d u c e} \tag {11}
$$

$$
\operatorname {R e d u c e} _ {K, x} \Rightarrow \operatorname {M a p} _ {y} \rightarrow \operatorname {R e d u c e} _ {K, z} \tag {12}
$$

$$
\operatorname {E q u i j o i n} _ {x} \Rightarrow \left(\operatorname {M a p} _ {y, L} \| \operatorname {M a p} _ {z, R}\right)\rightarrow \operatorname {E q u i j o i n} _ {w} \tag {13}
$$

- Chaining (10): This directive chains simpler projections for complex map operations, useful when a map prompt contains multiple instructions. Each  $\mathrm{Map}_{x_i}$  builds on the previous result. For example, a legal document analysis could involve chained steps: extract clauses, summarize, and generate recommendations.  
- Isolating (11): For map operations with independent subtasks, this directive splits them into separate projections to run in parallel, followed by a reduce step. For instance, customer feedback analysis could involve isolated projections to classify sentiment, identify features, and flag urgent issues.  
- Pre-Aggregation (12): This directive filters and projects relevant data from each document before a reduce operation, improving both efficiency and the quality of the aggregation. For example,

![](images/dc0118c05070b2eda5dde2707049ec5aec9407b451dc6bd25bd4b703094d22ef.jpg)  
Figure 4: Gleaning process with  $k = 1$  round of refinement. An LLM initially extracts information from an input transcript, and Officer Y is missing from the output. A validation agent (LLM-powered) identifies this omission and provides feedback. The original LLM incorporates this feedback in a second pass (shown with purple arrows), resulting in a more complete final output that includes both Officer X and Officer Y.

when summarizing shipping-related feedback by product category, each detailed review could first be projected into a concise summary of shipping comments, before aggregation.

- Pre-Joining (13): For complex equijoin operations, this directive preprocesses documents before joining. It is useful when direct comparison is computationally expensive—for example, matching research papers to funding opportunities could involve projecting papers to a short list of key themes and funding descriptions to criteria before joining.

One may wonder why each operator has its own directive (e.g., map before reduce, map before equijoin). This is because the criteria for applying the directive differ by operator. For example, in prejoining, the LLM agent evaluates factors like the sufficiency of current keys and long/large attributes. If beneficial, it generates a prompt to create a new key-value pair for a more relevant data representation. Similarly, for other operators, the agent considers operator-specific factors to determine the directive's applicability.

Overall, our rewrite directives reflect our key insight: in complex document processing tasks, it is impossible to determine an optimal pipeline given the infinite search space, difficulty, and ambiguity. Rewrite directives provide a scaffold for systematically exploring this space, especially when coupled with opportunistic decomposition into problematic operations (as will be described in subsequent sections). The effectiveness of specific directives varies by context and is hard to predict. Finally, as a byproduct of this search process to find sufficiently accurate pipelines, we obtain interpretable pipelines, since the operators use natural language prompts.

# 4 Optimizer

Here, we detail DocETL's query planning and optimization process. Users define their pipeline in a pipeline.yaml file, then run docetl build pipeline.yaml to generate a new YAML file with an optimized pipeline. DocETL's optimization involves two types of agents: Generation agents, which apply logical rewrite directives to create candidate plans (see "Apply Rewrites (Agent)" boxes in Figure 1), and Validation agents, which generate custom prompts to assess the quality of these plans. Per operation or sub-pipeline, validation agents evaluate candidate sub-plans on a data sample to select the optimal one, as shown by the green (selected) and gray (evaluated but not selected) sub-plans in Figure 1; we will describe both steps next. Our framework is reminiscent of top-down approaches like Cascades [16], but differs in its expansion criterion (using directives) and sub-plan evaluation via LLM-based validation. Unlike traditional cost-based optimizers, we focus on accuracy, with cost and latency constraints to be addressed in future work.

# 4.1 Optimization Approach

DocETL employs a top-down optimization approach that considers both individual operations and sub-pipelines, as outlined in Algorithm 1 and visualized in Figure 1. We move from left to right, opting (recursively) to decompose any operations for which the

accuracy is inadequate (as determined by the LLM placeholders). We summarize the process:

(1) Pipeline Traversal and Sub-pipeline Identification: We iterate through the pipeline from input to output (left to right). For each operation, we consider whether it, along with a suffix of the already-optimized operations to its left, forms a sub-pipeline that matches any rewrite directive. If no matching sub-pipeline is found, we treat the current operation as a single-operation sub-pipeline to optimize. For each identified sub-pipeline:

- We use the validation agent to synthesize a custom validation prompt tailored to the specific task described by the sub-pipeline.  
- The validation agent examines a sample of outputs using this prompt to determine if there's room for improvement. If the agent concludes that the current implementation is satisfactory, we move on to the next operation without further optimization, as shown by the no-change ("NC") paths in Figure 1.

This process is outlined in Algorithm 1, and the initial validation step is shown in Algorithm 2 (lines 5-7).

(2) Rewrite Directive Application and Recursive Optimization: When optimization is needed, we apply matching rewrite directives to the sub-pipeline or individual operation. As illustrated in Figure 1, we explore rewrite directives from Section 3. For each applicable directive, an LLM agent synthesizes new operations and configurations (e.g., prompts, output schemas) to match the directive. On the creation of a new operation, we immediately optimize it, recursively, before continuing with the current optimization, as shown by the nested "Apply Rewrites" rectangles in the figure. This opportunistic approach allows us to explore more refined plans efficiently (Algorithm 2, lines 10-11).

(3) Plan Evaluation and Selection: Multiple candidate plans can arise from the rewrite directives, as depicted by the various branches in Figure 1. We employ a two-stage evaluation process to select the best plan, as described in Algorithm 3: First, we execute each plan on a sample of data and use the validation agent to rate the output for each document, computing an average rating per plan. We then select the top  $k$  rated plans (currently set to 6) for further comparison. Next, the agent performs pairwise comparisons between these top plans, evaluating their outputs against each other. The plan with the most "wins" in these comparisons is selected as the optimal plan for the current sub-pipeline or operation, represented by the green boxes in Figure 1. This hybrid approach balances efficiency and accuracy in plan evaluation, as pairwise comparisons are known to be ideal for assessing relative quality [31, 36], but with potentially  $100+$  candidate plans generated by various rewrite directives (each rewrite can have multiple candidate plans, e.g., different parallel projections synthesized), comparing all pairs becomes computationally infeasible.

(4) Pipeline Update: We integrate the selected optimized plan into the pipeline, replacing the original operation or sub-pipeline (Algorithm 1, lines 9-12).

Algorithm 1: Pipeline Optimization  
Input: Pipeline  $P$  (sequence of operators), Sample data  $D$   
Output: Optimized pipeline  $P_{opt}$   
1 Function OptimizePipeline  $(P, D)$ :  
2 optimized  $\leftarrow []$ ;  
3 foreach operation op  $\in P$  do  
4 if opneedsConfig then  
5 // Use LLM agent to synthesize config for new ops created by rewrite directives, including prompts, output schemas, and operator-specific parameters (e.g., reduce_key for reduce)  
6 op.config  $\leftarrow$  GenerationAgent.SynthesizeConfig(op);  
7 if ([suffix of optimized]  $\rightarrow$  op) matches a rewrite directive then  
8 subplan  $\leftarrow$  [matching suffix of optimized]  $\rightarrow$  op;  
9 optimized_sub  $\leftarrow$  OptimizeSubPipeline(subplan, D);  
10 Replace matching suffix of optimized with optimized_sub;  
11 else  
12 optimized_sub  $\leftarrow$  OptimizeSubPipeline([op], D);  
13 Append optimized_sub to optimized;  
14 end  
15 return optimized;

Algorithm 2: Sub-pipeline Optimization  
Input: Sub-pipeline  $SP$  ,Sample data  $D$    
Output: Optimized sub-pipeline  $SP_{opt}$    
1 Function OptimizeSubPipeline  $(SP,D)$  ..   
2 if  $SP$  does not match any rewrite directive then   
3 return  $SP$  .   
4 Execute  $SP$  on  $D$  to get outputs; // Synthesize a prompt for validating sub-pipeline output   
5  $V\gets$  ValidationAgent.SynthesizeValidatorPrompt(D, outputs,  $SP$  .   
6 if ValidationAgentValidateoutputs,  $V$  ) is satisfactory then   
7 return  $SP$  .   
8 candidateplans  $\leftarrow \left[\right]$  .   
9 foreach directive  $R\in$  applicable rewrite directives for  $SP$  do // R applied to SP generates a mix of old and new ops rewrittenOps  $\leftarrow R$  applied to  $SP$  plan  $\leftarrow$  OptimizePipeline(rewrittenOps,D); Append plan to candidateplans;   
13 end   
14 return PlanSelection(candidateplans,V,D,k);

Algorithm 3: Plan Selection  
Input: Candidate plans  $C$  , Validation prompt  $V$  , Sample data  $D$  , Number of top plans to compare  $k$    
Output: Best plan best計劃   
1 foreach plan  $p\in C$  do   
2 Execute  $\mathcal{P}$  on each sample in  $D$  .   
3 Use ValidationAgent to rate outputs on a scale of 1 (very bad) to 4 (no identified improvements) according to  $V$  .   
4 Compute average score for  $\mathcal{P}$  across samples;   
5 end   
6 Select top  $k$  plans based on average scores;   
7 foreach pair of plans  $(p_i,p_j)$  in top  $k$  plans do   
8 Perform pairwise comparison using ValidationAgent and  $V$  .   
9 Update comparison scores for  $p_i$  and  $p_j$  .   
10 end   
11 return plan with highest comparison score;

To execute candidate plans (so we can compare their outputs), we sample data based on document size (larger documents have higher selection probability). As we optimize each sub-pipeline, we track its selectivity ratio (output documents / input documents) and use these ratios to adjust sample sizes for later operations. For example, if the first two operations have selectivities of 0.5 and 0.3, we increase the initial sample size by  $(1/0.5/0.3) \approx 6.67$  when optimizing the third operation. This ensures sufficient data for optimization even after selective operations. However, sample

documents may not fully represent the complete dataset; e.g., if the sampled documents fit within LLM context limits but some documents in the full dataset exceed them, we may encounter errors during full execution. We are developing methods to adapt plans accordingly during pipeline execution time.

Our overall approach lends itself to a rich space of pipeline optimization techniques with operator reordering and operator fusion. While we have not implemented any in the current release of DocETL, we are actively exploring this area for future improvements.

# 4.2 Agent and System Implementation

Here, we outline our novel agent-based architecture for generation and validation. While a comprehensive analysis of our architectures is beyond the scope of this paper, we focus on critical aspects that significantly impact system performance and effectiveness.

4.2.1 Generation Agents Generation agents are responsible for applying rewrite directives to create diverse candidate plans. When presented with a directive, these agents synthesize one or more appropriate operation configurations. These configurations encompass both logical and physical choices. Logical choices include prompts, output schemas, and reduce keys, while physical choices involve parameters such as chunk sizes for document splitting and batch sizes for document reduction. The generation agent also evaluates the applicability of rewrite directives in specific contexts. For instance, the agent might determine that applying the split-map directive (Equation (2)) is not beneficial if there's no valuable document-level metadata to leverage when processing individual chunks.

For certain parameter choices, particularly those related to physical implementation, LLMs may not be well-suited to determine optimal values. For example, how would an LLM know the ideal number of documents to summarize together in a batch as part of a reduce operation? In these cases, we use heuristics to generate a range of plausible parameter values, such as different batch sizes for a reduce operation, and then compare the results of these plans to determine the most effective parameter choice for the given operation and context.

Here, we detail three examples of our generation agent's approach for parameter selection:

Chunk Sizes. Our chunking approach explores five sizes ranging from  $15\%$  to  $75\%$  of the LLM's context limit, uniformly sampled. We also explore chunk sizes based on percentages of the average document length; similarly six sizes ranging from  $15\%$  to  $100\%$ , uniformly sampled. Also For each chunk size, we generate a set of gather configurations to retain relevant context from surrounding chunks. The creation of these gather configurations is based on the ratio of chunk size to document size.

We begin with three base configurations of gather operations for each chunk size: no context, one previous chunk, and one previous plus one next chunk. We then expand this set based on the document-to-chunk size ratio. For larger ratios (indicating smaller chunks relative to the document size), we generate configurations with more peripheral context. We use a square root function to control the growth of peripheral context as the document-to-chunk ratio increases, preventing excessive context that could overwhelm

the model. The choice of square root is based on empirical observations that the benefit of additional context tends to diminish more drastically as more context is added—a detailed evaluation is left for future work. For example, if the document is significantly larger than the chunk size, our expanded set might include configurations with up to 5 previous chunks and 2 next chunks. Conversely, for ratios closer to 1 (where chunk size approaches document size), our set comprises only the base configurations.

This basic approach is a first attempt at systematically exploring various chunking and gathering strategies. We are currently developing a taxonomy of LLM-powered data processing tasks to further refine this process. Our goal is to eventually use task classification to guide the generation of more tailored chunk sizes and gather configurations, recognizing that optimal settings may vary significantly depending on the specific task at hand.

Batch Sizes. For reduce operations, optimal batch sizes (i.e., the number of documents aggregated at once, in a single prompt) are not obvious and require experimentation. Our agent tests sizes from  $20\%$ ,  $40\%$ ,  $60\%$ ,  $75\%$ , to  $90\%$  of the maximum input fitting the LLM's context window, generating and evaluating multiple fold prompts for each. Our evaluations reveal task-dependent optimal batch sizes, highlighting the need for further research in this area—some tasks perform best with the smallest batch size (e.g., extracting distinct names), while others peak at a middle batch size, as shown in Section 5.

Blocking Keys and Rules. Resolve and equijoin operators involve pairwise comparisons between entities or records, leading to quadratic complexity in LLM calls. To mitigate this, a common technique is to use blocking to filter the number of pairs [7]. DocETL offers two blocking approaches: embedding-based and code-based. Embedding-based blocking leverages an embedding model (default: OpenAI's text-embedding-3-small) to generate vector representations for each document or subset of key-value pairs in a document (i.e., blocking keys). We compute cosine similarities between these embeddings and only consider pairs whose similarity exceeds a specified threshold for full LLM-based comparison. Code-based blocking allows custom Python expressions to be specified as filters. While blocking keys and code-based blocking rules can be directly constructed by the generation agents, we employ a different approach for determining the embedding threshold. Instead of asking an LLM to arbitrarily come up with a similarity threshold, we empirically determine it: first, we sample hundreds of pairs that are likely to be duplicates based on their embedding similarity. We then execute the comparison prompt on these pairs to identify the true duplicates. Finally, we select the threshold that achieves  $95\%$  recall in duplicate identification.

4.2.2 Validation Agents Validation agents assess sub-pipeline effectiveness through a structured validation and comparison process. For each operator, they synthesize validation criteria focused on concrete properties like accuracy (correctness of extracted information), precision (avoiding hallucinated content), and recall (completeness of extracted information), rather than relying on the operation's prompt instructions. These criteria are formulated as explicit tests that can be systematically checked against operation outputs.

To evaluate operation outputs, the agents first process a sample of data and assess the outputs against the synthesized validation criteria. This assessment determines whether further optimization is needed based on concrete failures rather than subjective assessment. When comparing candidate plans, the agents employ a two-stage approach: first rating each plan's outputs on a scale from 1 (very bad) to 5 (excellent) based on how well they meet the validation criteria, then performing detailed pairwise comparisons between the top- $k$  rated plans for a more nuanced quality assessment, as described in Algorithm 3. We currently set  $k = 6$  to balance thorough evaluation with computational efficiency, though we leave a more systematic parameter selection strategy for future work.

This structured approach to validation enables us to identify specific failure modes and guide the optimization process toward concrete improvements, similar to how traditional software testing isolates bugs through specific test cases. The validation criteria serve as a consistent benchmark across different pipeline variants, allowing for reliable comparison of alternative plans.

4.2.3 Implementation Details DocETL leverages GPT-4o (OpenAI) as the default LLM for both generation and validation agents, but this can be changed by the user. Both generation and validation agents consider a variety of inputs in their prompts, including user-defined operation prompts, sample operation input data, and, when relevant (i.e., for evaluation), sample operation output data. Often, including all of this data in a single prompt exceeds the LLM's context limits. When this happens, we have to remove information from the prompt. We prioritize keeping the following types of information:

(1) Output Schema Attributes: These are given the highest priority, with all tokens included—which is feasible because LLM output limits are typically much smaller than prompt (i.e., input) limits.  
(2) Prompt-Referenced Attributes: Of next priority is input attributes explicitly referenced in the prompt template, ensuring the LLM has access to all task-critical information.  
(3) Remaining Input Attributes: For any additional attributes in the input document(s), we implement a middle truncation strategy. This method preserves both the initial and final portions of the content, which often encapsulate key information, while judiciously truncating the middle sections as necessary.

To optimize performance and resource utilization, we cache all sub-pipeline outputs. The engine and optimizer are implemented in approximately 16K lines of Python, with 2K lines in Rust for efficient resolve and equijoin execution. While blocking rules are defined in Python, so they can be easily generated by LLMs, we implement common patterns (like containment and normalized string matching) in Rust for better performance. Structured outputs for LLM calls are handled by the tool calling functionality; users can use any LLM in DocETL pipelines that supports tool calling (e.g., OpenAI, Claude, Gemini, Llama 3.1, and more).

# 5 Evaluation

The primary goal in our evaluation is show that DocETL's rewrite directives and optimization framework dramatically enhance our ability to automatically analyze complex documents—all with no training labels or developer intervention needed. While finding optimal plans is impossible, we demonstrate that DocETL's approach

of systematically decomposing tasks and documents to explore a search space of processing strategies yields plans that are sufficiently accurate. In comparison, baseline approaches often achieve such poor accuracy ( $< 40\%$ ) that they are impractical for real use.

Overall, we find that DocETL's plans yield  $21\%$  to  $80\%$  improvements in task-specific accuracy metrics such as precision, recall, and F1 score. We first consider three complex document processing tasks: legal contract analysis, declassified article analysis, and video game review analysis (Sections 5.1 to 5.3). These tasks represent different challenges: extracting structured information embedded within the semantic content of unstructured data, resolving entities and summarizing their information across documents, and reasoning about temporal consistency across long documents. For the legal contract analysis (Section 5.1), we compare against both recent LLM-powered systems (LOTUS [37], Palimpzest [29], and Aryn [1]) and traditional NLP baselines using spaCy [20] or NLTK [5]. For the video game review (Section 5.2) and declassified article (Section 5.3) tasks, we compare only against non-LLM baselines, as LOTUS, Palimpzest, and Aryn lack support for entity resolution and documents exceeding LLM context windows. For each task, our evaluation includes both task-specific metrics (customized variations of precision and recall) as well as a hallucination rate to measure factual consistency. Then, we evaluate DocETL on the challenging Biodex text classification task (LOTUS's only task with sub- $70\%$  accuracy), where our optimized pipeline achieves 33 to  $80\%$  improvements in rank precision (Section 5.4). We conclude with case studies examining DocETL's application in real-world police misconduct identification, the effectiveness of LLM agent rewrites, and insights from user adoption (Sections 5.5 to 5.7).

For all pipelines, we use the gpt-4o-mini model from OpenAI, and we run the experiments on a 2021 Macbook Pro with an M1 chip. The DocETL optimizer uses gpt-4o-mini, except in the Biodex task in Section 5.4, where we use gpt-4o.

# 5.1 Legal Contract Analysis

The Contract Understanding Atticus Dataset (CUAD) [19], includes 510 legal contracts with expert-labeled annotations across 41 categories of clauses, ranging from basic information (e.g., Document Name, Parties) to complex concepts (e.g., Most Favored Nation, IP Ownership, Post-Termination Services). The task is to extract text spans for each relevant clause type from each contract; not all contracts contain all types of clauses.

We evaluate on the first 50 contracts, comparing extractions against ground truth. An extraction is considered correct if (i) the clause type matches, and (ii) the extracted text span's Jaccard similarity with the ground truth span  $> 0.15$ . This threshold accommodates variation in LLM outputs while ensuring the model has correctly identified the clause's location; it is set fairly low because we provide no training examples, so the LLM does not know how much to extract—but large enough to ensure some match. We set other values for this and found the comparisons to be similar. We measure precision, recall, F1, and hallucination rate (proportion of extracted clauses not matching our 41 predefined categories).

# 5.1.1 Implementations We have five baselines:

(1) DocETL Baseline: Our unoptimized pipeline consists of a single map with a prompt to extract all relevant clauses, given one-sentence descriptions of the 41 clause types. The output schema specifies a list of objects with clause_type and textSpan keys.

```yaml
1 - name: extract Relevant clauses   
2 type: map   
3 output:   
4 schema:   
5 misconduct:"list[{clause_type: str,textSpan:str}]   
6 prompt:   
7 Given the following contract document:   
8 {{input.document }}   
9 Extract the text spans (if they exist) for each of the following categories:   
10 1. Document Name: The name of the contract   
11 2. Parties: The two or more parties who signed the contract   
12 3. Agreement Date: The date of the contract   
13 4. Effective Date: The date when the contract is effective   
14 ...37 more...
```

(2) LOTUS Baseline: We implement a pipeline using LOTUS's sem_map operator with the same prompt as DocETL's map operation, plus additional output structuring instructions since LOTUS does not support explicit output schema definitions. The LOTUS pipeline output is a string that we parse into JSON for evaluation. While some outputs required re-running to obtain parseable JSON, we report costs for a single run to maintain fair comparison. We expect the accuracies for the LOTUS baseline to be similar to the DocETL baseline, as the LLM calls are mostly the same; the only differences arise from discrepancies in the system prompts (part of the DocETL and LOTUS codebases; not exposed to the user), as well as the extra instruction in the LOTUS prompt to output a JSON-formatted answer matching the intended schema (which contains examples of some of the clause types).

(3) Palimpzest Baseline: We implement the extraction using Palimpzest's convert operator. In Palimpzest, rather than writing prompts directly, users provide schema descriptions from which the system generates prompts. We provided our clause type descriptions in the description of the schema.  
(4) Non-LLM Baseline: We write a program, using the spaCy library [20], to loop over all clause types and extract the most semantically similar sentence (above a threshold of 0.9). We use spaCy's sentence splitter and embedding model, tok2vec.  
(5) Aryn Baseline: We implement extraction using Aryn's 11m_query operation with the same prompt as our LOTUS baseline, and the same output normalization procedure used with LOTUS to handle parsing errors and format inconsistencies.  
(6) DocETL's Optimized Plan: DocETL's optimizer transforms the single map operation into an isolated projection decomposition with 21 independent map operations, each extracting 1-3 semantically related spans (e.g., grouping agreement and effective date extractions), followed by a reduce to combine all extracted clauses. Notably, the optimizer chose isolated projection (directive 11) over document chunking, suggesting that LLMs excel at focused extraction of small amounts of information even from lengthy documents.

5.1.2 Results The results are shown in Table 2. DocETL's optimized plan performs significantly better than all baselines, achieving a  $21.4\%$  improvement in F1 over LOTUS, the next best LLM-based plan, and a  $67\%$  improvement in recall over the unoptimized DocETL pipeline—with no hallucinations. LOTUS, Aryn, and the unoptimized DocETL pipelines achieve similar scores and

Table 2: Legal Contract Analysis Results.  

<table><tr><td>System</td><td>Avg Preci-sion</td><td>Avg Recall</td><td>Avg F1</td><td>Avg # Chars</td><td>Avg Hallucination Rate</td></tr><tr><td>DocETL (Opt.)</td><td>0.401</td><td>0.719</td><td>0.477</td><td>162.60</td><td>0.000</td></tr><tr><td>DocETL (Unopt.)</td><td>0.341</td><td>0.430</td><td>0.379</td><td>49.35</td><td>0.072</td></tr><tr><td>LOTUS</td><td>0.402</td><td>0.471</td><td>0.393</td><td>46.301</td><td>0.073</td></tr><tr><td>Palimpzest</td><td>0.059</td><td>0.013</td><td>0.022</td><td>35.10</td><td>0.000</td></tr><tr><td>Aryn</td><td>0.450</td><td>0.370</td><td>0.352</td><td>49.56</td><td>0.069</td></tr><tr><td>Non-LLM</td><td>0.224</td><td>0.219</td><td>0.190</td><td>212.73</td><td>0.000</td></tr></table>

Table 3: Runtime and Cost Analysis for Legal Task. N/A means not available, because the pipeline or system does not have an optimizer. Palimpzest runtime is single-threaded and includes optimization time.  

<table><tr><td>System</td><td>Runtime (s)</td><td>Cost ($)</td><td>Optimizer Cost ($)</td></tr><tr><td>DocETL (Opt.)</td><td>180.30</td><td>1.46</td><td>1.58</td></tr><tr><td>DocETL (Unopt.)</td><td>23.43</td><td>0.08</td><td>N/A</td></tr><tr><td>LOTUS</td><td>28.12</td><td>0.07</td><td>N/A</td></tr><tr><td>Palimpzest</td><td>84.07</td><td>Unknown*</td><td>Unknown*</td></tr><tr><td>Aryn</td><td>52.53</td><td>Unknown*</td><td>N/A</td></tr><tr><td>Non-LLM</td><td>217.99</td><td>0.00</td><td>N/A</td></tr></table>

*Costs are not reported by the system.

Table 4: Game Review Analysis Results  

<table><tr><td>Metric</td><td>DocETL (Unopt.)</td><td>DocETL (Opt.)</td><td>Non-LLM</td></tr><tr><td>Hallucination Rate (lower is better)</td><td>0.465</td><td>0.312</td><td>N/A</td></tr><tr><td>Sentiment Accuracy (higher is better)</td><td>0.664</td><td>0.650</td><td>0.605</td></tr><tr><td>Kendall&#x27;s Tau (higher is better)</td><td>0.470</td><td>0.631</td><td>N/A</td></tr></table>

hallucination rates (6.9-7.3%). The non-LLM baseline achieves much lower scores than the LLM-based methods, as well as longer text spans—because spans are forced to be at sentence-level granularity, which could be longer than necessary for short clauses like "document name" or "agreement date." Interestingly, Palimpzest's optimizer selected a code-based plan rather than an LLM-based one for this task—perhaps explaining its lower score. Palimpzest's lower performance on this specific task may be due to difficulties in configuring its schema-only approach.

While the optimized pipeline's cost and runtime are higher (Table 3), we prioritize accuracy, which often requires increased computational costs. The higher runtime and cost stems from the increased number of LLM calls in the new map operations, plus an additional reduce operation to combine their results. Further parallelism could help reduce the runtimes further, but this is not our focus. Costs will decrease as LLM pricing continues to fall—they have fallen by  $1000 \times$  in 3 years, with a predicted drop of  $10 \times$  per year [2]—and they become negligible when using open-source models. The optimization cost is only $1.58 (using gpt-4o-mini for the optimizer's agents) and does not increase with dataset size, as it is done on a sample.

# 5.2 Game Review Analysis

We evaluate DocETL on temporal analysis of video game reviews from Steam<sup>4</sup>. For each of 10 popular games (randomly sampled from the 100 games with the most reviews), we create a document with 300 customer reviews with timestamps (but omit their ratings). Each document comprises concatenated reviews in no particular order, with lengths exceeding standard LLM context windows. The task is to identify 10 positive and 10 negative reviews per game,

with their review IDs, and present these in chronological order. We evaluate the pipelines on: (i) hallucination rate, or the fraction of extracted review IDs that do not appear in the source, (ii) sentiment accuracy: whether the identified review sentiment matches the user's rating, computed only for non-hallucinated reviews, and (iii) Kendall's Tau correlation of the timestamp ordering, which measures how well the reviews are chronologically ordered.

5.2.1 Implementations Since the documents exceed context limits and require temporal reasoning, we do not compare against existing LLM-based systems, which do not support documents beyond context windows. Our baseline DocETL pipeline consists of a single map to extract positivereviews and negativereviews (both list types), with documents truncated from the middle to fit the context window—effectively randomly sampling reviews from each game's corpus. The operation looks like the following:

```txt
1 - name: getreviews   
2 type: map   
3 output:   
4 schema:   
5 positivereviews:"list{review_id: str, timestamp: str, review_summery: str}]   
6 negativereviews:"list{review_id: str, timestamp: str, review_summery: str}]   
7 prompt:   
8 Given the following reviews for the game {input.app_name}， analyze them and select 10 positive and 10 negative reviews that are evenly distributed across time:{input.coletedreviews}   
9 Return two lists:   
10 - positivereviews: List of 10 positive reviews, sorted by timestamp   
11 - negativereviews: List of 10 negative reviews, sorted by timestamp   
12 Each returned review object should contain the review ID, timestamp and a summary of the review.
```

DocETL's optimizer transforms this pipeline into: (a) A split operation that chunks input by token count (104,652 tokens per chunk): no gather operation (b) Two map operations per chunk—one each for positive/negative reviews—each incorporating one round of cleaning (directive 7) to ensure that the reviews are valid (c) A reduce operation to combine the positive and negative reviews from the chunks and present them in chronological order, matching the original getreviews operation's output schema. We added a non-LLM baseline that extracts reviews via regex, classifies sentiment with NLTK and VADER [5, 21], and selects the first 10 positive and negative reviews. Since this baseline only performs classification (i.e., it is not a generative model), hallucination rate and Kendall's Tau metrics don't apply.

5.2.2 Results As shown in Table 4, we observe a  $32.9\%$  reduction in hallucination rate (from  $46.5\%$  to  $31.2\%$ ), demonstrating more reliable review extraction. Sentiment accuracy remained stable  $(66.4\%$  vs  $65.0\%)$ , while Kendall's Tau improved by  $34.3\%$ , indicating better temporal ordering. Both LLM-based approaches outperform the non-LLM baseline in sentiment accuracy, despite having to handle complex additional tasks beyond simple sentiment classification.

The optimized pipeline costs  $1.48 (173.63s runtime) versus the baseline's$ 0.12 (29.27s). However, the baseline achieves this by truncating data to fit LLM context limits. With full data processing, the baseline would cost $0.28, making the optimized pipeline 5.3× more expensive—still less than the 10× cost gap between gpt-4o and gpt-4o-mini models. This cost increase is justified by the improved temporal reasoning accuracy, and is due to steps like

gleaning (which doubles operation cost); however, the洗净ing auditor consistently flagged temporal issues; with feedback like "The ... reviews are not sorted correctly by timestamp; they should be organized chronologically." The optimization cost was \(6.60; however, this is a one-time cost. The non-LLM baseline had a runtime of 15.89 seconds.

# 5.3 Declassified Article Analysis

We evaluate DocETL's effectiveness on resolve and reduce tasks using 733 paranormal case files from The Black Vault, a repository of declassified international government documents, averaging 700 words each. Each article documents a reported paranormal event with details such as location and witness accounts. We scraped articles from their website and used Azure Document Intelligence to convert all PDF attachments to text, and provide this data for transparency at https://osf.io/9xsbq. Our task is to determine the distinct locations for each type of paranormal event (e.g., all cities and regions where UFO sightings were reported). The task involves two challenges: (i) standardizing event types across articles, and (ii) extracting and aggregating location mentions across articles for each event type.

We evaluated precision of extracted locations by first programmatically verifying their presence in the source text and attempting to geocode them using the Nominatim API, based on OpenStreetMap. We also measured hallucination rate—a subset of precision—defined as the proportion of locations that don't exist in the source text. For locations in the text that could not be geocoded (e.g., specific rivers or mountain ranges), we performed manual verification.

5.3.1 Implementations We consider 4 pipelines. We only consider one LLM-powered baseline, written in DocETL, as other systems don't support resolve. This pipeline consists of: (i) a map to extract event type (e.g., "humanoid sighting") per article, and (ii) a reduce to collect distinct locations across all articles of each event type. DocETL's optimizer modified this pipeline in two ways. First, it synthesized a resolve between map and reduce to standardize event types (directive 9). Second, it optimized reduce by determining a fold batch size (41) to process document batches, synthesizing the corresponding fold prompts. The optimized pipeline consists of: (i) a map (as before), (ii) a resolve to standardize event types (e.g., variations of "UFO sighting"), and (iii) a reduce (as before), but using a batched fold, with batch size 41. To isolate the impact of the optimized reduce operation, we also evaluate the a version of this pipeline (+resolve only), which uses the original reduce operation without batched folding. Our 4th pipeline represents a non-LLM baseline that extracts location (LOC) entities from article text using spaCy's en_core_web-lg model [20]. This script processes the resolved results from DocETL's optimized pipeline to establish a comparison point for location precision and recall.

5.3.2 Results As shown in Table 5, the baseline DocETL pipeline extracts 233 distinct event types with many semantic duplicates (e.g., "UFO Sighting", "Category: UFO Sighting", "Event Type: UFO Sighting"), making location aggregation impractical as most event types contain only one article. Adding resolve enables meaningful aggregation by consolidating to 83 event types. The +resolve only pipeline extracts 298 locations with  $99.4\%$  precision, and the

Table 5: Declassified Article Analysis Results. Location metrics for baseline are N/A as its 233 distinct event types (mostly singleton categories) make meaningful location aggregation impossible.  

<table><tr><td>Metric</td><td>DocETL (Unopt.)</td><td>DocETL (+Re-solve Only)</td><td>DocETL (Opt.)</td><td>Non-LLM</td></tr><tr><td>Location Precision</td><td>N/A</td><td>0.994</td><td>1.000</td><td>0.6812</td></tr><tr><td>Location Recall</td><td>N/A</td><td>298</td><td>435</td><td>435</td></tr><tr><td>Distinct Event Types</td><td>164</td><td>83</td><td>83</td><td>N/A</td></tr><tr><td>Hallucination Rate</td><td>N/A</td><td>0.01</td><td>0.01</td><td>0.00</td></tr></table>

optimized pipeline further improves this to  $100\%$  precision while extracting 435 locations (46% higher recall). The non-LLM baseline matches the optimized pipeline's recall but with substantially lower precision (68.12% vs. 100%), highlighting the LLM's superior ability to accurately identify relevant locations in context. All systems exhibit low hallucination rates. This improved recall arises because batched folding allows the LLM to incrementally process and track distinct locations, rather than attempting to process all documents at once, where important details may be lost due to LLM context window overload [26, 30].

Cost Analysis. The resolve-only pipeline cost  $1.16 (307.36s)$  while the optimized version cost  $\$ 1.84 ($ 1.34 + $0.50 for optimization; 625.64s). The optimized pipeline's longer runtime results from multiple LLM calls per event type during folding, versus one call in the resolve-only version. The non-LLM baseline ran in 158.85s. For all operations, and the optimizer agents, we used gpt-4o-mini.

# 5.4 Biomedical Classification

We evaluate DocETL on the challenging Biodex biomedical drug reaction classification task from the LOTUS paper [37]. For each of 250 biomedical papers, the task involves identifying which of 24,300 adverse drug reactions (from the MedDRA list) are discussed. Performance is measured using rank-precision@k (RP@k), evaluating both accuracy and ranking of identified reactions. A higher score indicates that true positive reactions appear earlier in the list. We also evaluate the hallucination rate, measuring the proportion of identified reactions that are not present in the drug reaction list.

5.4.1 Implementations We compare against LOTUS using numbers from their preprint and our reimplementation of their pipeline using the same models (gpt-40-mini for LLM calls, text-embedding-3-small for embeddings) for fair comparison.

LOTUS Baseline. We implemented their map-search-filter pattern as a pandas dataframe accessor: first extracting reactions from each article via a map operation, then using similarity search to find candidate MedDRA labels, and finally filtering these candidates with an LLM to verify matches.

Our implementation follows their described pipeline with some necessary deviations. First, a map operation extracts drug reactions from each article (one LLM call per article). Then, for each article's extracted reactions, we find the 49 nearest neighbors in embedding space among the MedDRA labels—we chose  $k = 49$  to match our target LLM call budget ( $\sim 12k$ , equivalent to the number of LLM calls executed by DocETL). We use exact cosine similarity computation via NumPy instead of a FAISS approximate nearest neighbor index, which may slightly increase runtime but provides more precise results—though this overhead is minimal given we only search through O(10k) vectors per article on an M1 Mac.

Table 6: Biomedical Classification Results. Since most articles have fewer than 25 relevant labels, RP@25 effectively measures recall rather than ranking quality.  

<table><tr><td>System</td><td>RP@5</td><td>RP@10</td><td>RP@25</td><td>Hallucination</td></tr><tr><td>DocETL</td><td>0.281</td><td>0.313</td><td>0.371</td><td>0.001</td></tr><tr><td>LOTUS (Our reimplementation of map-search-filter)</td><td>0.213</td><td>0.207</td><td>0.206</td><td>0.000</td></tr><tr><td>LOTUS (Reported)</td><td>0.241</td><td>0.258</td><td>N/A</td><td>0.000</td></tr><tr><td>Non-LLM Baseline</td><td>0.106</td><td>0.158</td><td>0.262</td><td>0.000</td></tr></table>

To evaluate rank-precision, we post-processed the pipeline outputs into ranked lists. For each article, we ranked the matching labels based on their cosine similarity scores (obtained during the similarity search phase), taking the top k labels for RP@k computation.

DocETL Implementation. In DocETL, we implement this task as an equijoin between articles and MedDRA labels, using a comparison prompt that asks "Can the following condition be found in the article?" The prompt includes both the article text and the label, as well as an indicator of whether the condition text appears as a substring of the article (which is possible in Jinja templating). We don't evaluate an unoptimized version due to the impractical number of LLM calls required (over 6 million). DocETL optimized this into a map-equijoin pipeline, where the map extracts medical conditions per article(with a prompt designed for medical text but without demonstrations or examples), and the equijoin uses synthesized blocking rules including an embedding similarity threshold of 0.5253 and a requirement that all words in the reaction label appear in the article text. Finally, we add a reduce operation that asks the LLM to rank the identified labels for each article from most to least confident, enabling evaluation of ranking quality. We did not apply DocETL's reduce operator optimizations to this ranking step.

We also include a simple non-LLM baseline that identifies candidate labels by checking for exact substrings and ranks them by length. Given the large number of required comparisons, we opted for a keyword baseline over more complex NLP libraries (e.g., NTLK).

5.4.2 Results The two pipelines differ in how they rank identified labels for each article. DocETL uses a reduce operation that asks the LLM to rank labels from most to least confident, while for LOTUS we use semantic similarity scores from the search phase, as their semantic aggregation operator operates on entire dataframes rather than groups, making LLM-based ranking per article outside the scope of their implementation.

At RP@25, which effectively measures recall since articles contain fewer than 25 labels in the ground truth, DocETL shows an  $80\%$  improvement over reimplemented LOTUS. For RP@5 and RP@10, DocETL shows  $33\%$  and  $50\%$  improvements, respectively. The non-LLM baseline achieves lower RP@5 and RP@10 scores than the LLM-based methods, but a competitive RP@25 (still worse than the plan DocETL found). The improvement in recall likely stems from DocETL's synthesized blocking rules: while LOTUS relies purely on embedding similarity to identify candidate reactions, DocETL's rule requiring all words in the reaction label to appear in the article text may surface reactions that have low embedding similarity scores. In terms of hallucination rate, all systems perform well with essentially zero hallucinations, though DocETL has a marginally higher rate of 0.001 on average. The difference between LOTUS' reported performance and our reimplementation

may be attributed to model choices and prompting strategies, as we standardized on gpt-4o-mini without "few-shot" examples for consistency across all experiments.

Cost and Dataset Analysis. The non-LLM baseline takes 290.65 seconds to run. Our reimplemented LOTUS pipeline costs  $0.47 and takes 925 seconds to run. The DocETL pipeline costs$ 3.65 and takes 463.28 seconds, with an additional optimization cost of $2.37. We believe this additional cost is an acceptable tradeoff because of the between 30-80% improvement in RP; moreover, these costs would be insignificant with open-source LLMs. The runtime can be highly variable; as LLMs can have high tail latencies, and LOTUS and DocETL may implement LLM retry logic differently.

Manual inspection of the results reveals inherent challenges with the task and dataset quality. We found numerous cases where ground truth labels were not actually discussed in the article text, as well as instances where DocETL correctly identified adverse reactions present in the text but missing from the ground truth annotations. This suggests that dataset quality may be the primary factor limiting performance scores across all approaches, rather than limitations of the systems themselves.

# 5.5 Case Study: Police Misconduct

We conducted an case study on police misconduct identification (Example 1.1) using a dataset of 227 documents from various California police departments. This is only a sample of the hundreds of thousands of documents collected by our collaborators at the California Police Records Access Project<sup>5</sup>. This dataset presented several challenges: documents averaged 12,500 tokens, with  $2\%$  exceeding the 128,000 token context window limit. The corpus had an unknown number of cases and several hundred police officers mentioned<sup>6</sup>.

The task was to generate detailed misconduct summaries for each officer who exhibited misconduct, including the officer's name, misconduct types, and a comprehensive summary. We implemented an initial pipeline in DocETL consisting of a map operation to extract officers who exhibited misconduct from each document, followed by anunnest operation to flatten this list of officers, and a reduce operation to summarize misconduct across relevant documents for each officer. For documents exceeding the context limit, we truncated tokens from the middle until they fit within the LLM's context window. Prompts for this pipeline define "misconduct" and are written by engineers and journalists employed full-time by the Police Records Access Project.

Running this pipeline as-is led to very incorrect outputs, as police officer names need to undergo entity resolution prior to the reduce operation. In practice, the team runs a domain-specific clustering algorithm, followed by human annotation, to de-duplicate police officer names. As such, our initial pipeline (denoted Baseline) therefore also includes a resolve operation before the reduce operation, as per the rewrite directive, Equation (9). This resolve operation was synthesized by DocETL (i.e., comparison prompt, resolution prompt, and embedding thresholds for blocking).

![](images/e82163967150f10d5afcb4c09178e985fe5b5d6f872b9a7c2c0ea74999deb2f8.jpg)  
Figure 5: Cost vs. metrics (precision, recall, and F1) for 30 different LLM-generated implementations of rewrite directives applied to the legal contract analysis task. Each point represents a distinct plan implementation, colored by directive type; isolated projections (Equation (11), chaining projections (Equation (10), or gleaning (Equation (7)). The DocETL unoptimized baseline and optimized plan from Section 5.1 are shown with dashed lines for reference, though not generated in this experiment. Due to the optimizer's nondeterministic nature, some plans in this experiment achieved higher metrics than the original optimized plan.

![](images/214637f6c6c1f4faa54fd289645708254d6044839fbb2af534b19a1e51a00bac.jpg)

![](images/bf6ad0c6e5f0b7cf18046f02402ce8a50617babc2dcd380be5371f8736f0cae9.jpg)

We evaluated two other pipeline variants, each of which were considered by the optimizer, as well as the final one chosen by the optimizer, all using GPT-4o-mini. It is not obvious which pipeline will be most accurate. The pipelines are as follows:

(1) DocETL₅: This pipeline applies Equation (12)—a projection synthesis rewrite—to extract misconduct summaries for identified officers in addition to the officer name before the resolve step. The reduce operation then only summarizes these extracted summaries, as opposed to processing the entire documents.  
(2) DocETL: This pipeline builds upon DocETLs by extracting both misconduct summaries and types from each document. It then incorporates both the summaries and types in the reduce step, providing more structured information for aggregation.  
(3) DocETL<sub>O</sub>: This pipeline, selected by the optimizer, extends DocETL<sub>T</sub> by chunking documents into 12,840 token segments. It includes metadata extraction and a peripheral context configuration of two previous chunks in full and a summary of earlier content. The map operation is applied to each chunk, followed by a synthesized operation to reduce chunk results per document. Like other pipelines, this is then followed by the officer name resolution step and a final reduce step to aggregate summaries per officer. We will discuss the details of the plan subsequently.

Results. To evaluate output quality without ground truth data, we came up with three binary criteria: (i) whether each officer name referred to a real person, (ii) if the summary included dates and locations of misconduct, and (iii) whether each identified misconduct instance was extensively described in the summary. To assess the accuracy of our evaluation criteria, we employed GPT-40-mini as a judge to evaluate each criterion for over 1,500 outputs across the baseline and all variants. To validate the LLM's judgments, we conducted a human evaluation on a subset of the data. For the first two criteria (officer name validity and inclusion of dates/locations), one of the authors manually assessed 100 randomly sampled outputs from both the baseline and DocETL variants. For the third criterion (extensive description of misconduct), due to the detailed and often graphic nature of the summaries, the author evaluated 50 output summaries, a process that required several hours of careful reading. The human evaluation revealed high agreement between the

LLM judge and human assessor— $96\%$ ,  $97\%$ , and  $92\%$  respectively—suggesting that our LLM-based evaluation method is a reliable proxy for human judgment in this task.

Table 7 illustrates these results. DocETL  $O$  is, on average,  $1.34\times$  more accurate compared to the baseline. The DocETL  $S$  and DocETL  $T$  pipelines performed similarly, with the notable exception of DocETL  $S$ , which often omitted dates and locations from summaries.

Table 7: Evaluation Metrics for Police Misconduct Identification Pipelines. Each value represents the fraction of outputs that pass the metric.  

<table><tr><td>Metric</td><td>Baseline</td><td>DocETL_S</td><td>DocETL_T</td><td>DocETL_O</td></tr><tr><td>The officer&#x27;s name is a specific name, not generic (e.g., not &quot;Officer 1&quot;)</td><td>0.84</td><td>0.93</td><td>0.89</td><td>0.87</td></tr><tr><td>The summary contains a date and location</td><td>0.67</td><td>0.1</td><td>0.91</td><td>0.92</td></tr><tr><td>Each identified instance of misconduct is described extensively in the summary</td><td>0.42</td><td>0.78</td><td>0.76</td><td>0.80</td></tr></table>

Our evaluation underscores the complexity and task-specific nature of assessing LLM-based pipelines. While the outputs of different plans may appear similar at first glance, our analysis reveals some variations in their quality and reliability. The baseline's poor performance highlights the importance of our rewrite rules. DocETL's summaries consistently failed to mention locations. DocETL and DocETL offered the most reliable results, with the latter being particularly suited for longer documents. This variability in plan performance emphasizes the necessity of DocETL's custom validation agents, which demonstrated proficiency in understanding the task-specific nature of evaluation: for instance, the map operation's evaluation prompt focused on the completeness of incident details and correct categorization of misconduct types, while the reduce operation's prompt emphasized accuracy of aggregation and information retention across cases. Without such tailored validation mechanisms, discerning the relative strengths of each plan would be challenging, if not impossible—highlighting the critical role of task-specific optimization and evaluation in LLM-powered document analysis.

DocETL's Optimized Pipeline. The DocETL $_O$  pipeline can be expressed using our rewrite directive syntax as follows:

$$
\begin{array}{l} \mathrm {M a p} \rightarrow \mathrm {U n n e s t} \rightarrow \mathrm {R e d u c e} \Rightarrow \\ \begin{array}{c} \operatorname {M a p} _ {M} \to \operatorname {S p l i t} \to (\operatorname {M a p} _ {S} \| \operatorname {M a p} _ {H}) \to \operatorname {G a t h e r} \to \operatorname {M a p} \to \\ (\operatorname {M a p} _ {v} \to \operatorname {M a p} _ {i}) ^ {\leq 1} \to \operatorname {R e d u c e} _ {D} \to \operatorname {U n n e s t} \to \operatorname {R e s o l v e} \to \operatorname {R e d u c e} \end{array} \\ \end{array}
$$

where  $\{\text{officer\_name}\}$  is the reduce key for the final summarization.

This pipeline begins with a map operation to extract metadata  $(\mathrm{Map}_M)$ , followed by document chunking of 12840 tokens each (Split). Each chunk then undergoes Directive Equation (3):  $\mathrm{Map}_S$  for summarization and  $\mathrm{Map}_H$  for header extraction. The Gather operation collects context for each chunk, including the header lineage for the current chunk, 2 full previous chunks, and summaries of the other previous chunks. The original Map operation is then applied to each rendered chunk, with gleaning applied for refinement. Results from all chunks of a document are combined using  $\mathrm{Reduce}_D$ . The pipeline then flattens the results (Unnest), resolves officer names (Resolve), and finally summarizes misconduct per officer (Reduce). Overall, this optimized pipeline incorporates several of our rewrite rules, including document chunking (1), header lineage context and summarization (3), gleaning for the Map operations (7), and duplicate key resolution (9).

Costs. For our sample dataset of 227 documents, the baseline incurred  $2.24, while DocETL_S and DocETL_T each cost$ 0.55. DocETL_O was more expensive at $1.35 due to processing all document chunks, but less expensive than the baseline (due to not needing to include entire documents in the reduce operation). Running the optimizer incurred a cost of approximately $100 and took about 20 minutes, with the bulk of the expense attributed to validation agents processing lengthy documents. DocETL_O took 364.97 seconds to run, and all other pipelines completed in less than 180 seconds. While the optimization cost of $100 for a task that takes < $3 may seem high, note that we are merely operating on a sample of the overall dataset; processing the dataset has already cost the team over $50,000; so this one-time cost of $100 is amortized across processing hundreds of thousands of documents. As part of this process, the optimizer considered and evaluated over 200 pipeline variants. As models become more cost-effective (e.g., GPT-4o-mini is over 100× cheaper), optimization costs will decrease significantly, making the investment even more worthwhile in the long run.

# 5.6 Case Study: Rewrite Directives in Legal Contract Analysis

One may wonder: if DocETL's agentic optimizer depends on how effectively LLMs transform abstract rewrite directives into concrete plans, how well do they actually perform? We examined this with a case study on our legal contract analysis task from Section 5.1. We selected three rewrite directive types that don't require physical parameter tuning: projection chaining (synthesizing a chain of dependent map operations, according to Equation 10), isolated projection (synthesizing independent map operations, per Equation 11), and gleaning (Equation 7). Using our GPT-4o-powered LLM agent, we generated 10 different instantiations of each directive, yielding 30 distinct plans with varying prompts, structures, and decomposition strategies.

Our study had two objectives: (i) to assess the quality of LLM-implemented directives and (ii) to evaluate our LLM-based plan evaluation mechanism. We executed all 30 plans on the 50 contracts, measuring precision, recall, F1 scores, and cost to characterize performance distribution across implementations of the same directive. We then had our optimizer (using GPT-4o-mini as judge) rank these plans per the approach in Section 4, and computed the Kendall's Tau between these rankings and actual performance metrics.

Figure 5 illustrates the results. We start with (i). Projection synthesis rewrites (both chaining and isolation) showed high variance in both cost and accuracy metrics. Cost variance was expected: more projections synthesized means more LLM calls and proportionally higher costs. More surprising was the substantial accuracy variance, which stemmed from implementation inconsistencies.  $20\%$  of the generated plans (all from chain projection implementations) failed to include document placeholders in prompts (e.g., writing extract  $\mathsf{X}$  clause from the document instead of extract  $\mathsf{X}$  clause from {{ input.document }}), resulting in the LLM receiving no text to analyze. Isolated projections consistently outperformed chaining projections for this task, likely because clause extraction subtasks are mostly independent. Gleaning directive implementations showed more consistent cost profiles, which is expected since they involve exactly three LLM calls per document (initial map, validation, and refinement). Despite implementation variance, many LLM-generated plans outperformed the unoptimized DocETL baseline, with  $47\%$  of plans achieving better precision,  $67\%$  of them achieving better recall, and  $40\%$  of them achieving better F1 scores. When compared against our optimized plan from the main experiment,  $30\%$  still achieved better precision,  $10\%$  achieved better F1 scores, though none improved on recall. Moving on to (ii), the Kendall's tau correlation between LLM judge rankings and actual F1 score rankings was 0.642. So, while there is considerable variance in implementation quality, our selection mechanism can identify the more effective plans.

Overall, while LLMs can translate abstract directives into working plans, quality varies considerably, and naive implementations may contain critical errors. This underscores the importance of generating many plans and our LLM-based plan evaluation mechanism and suggests potential improvements through better prompt engineering or selecting models particularly adept at prompt rewriting.

# 5.7 User Adoption and Impact

Since releasing DocETL as open source software in October 2024, we have observed increasing adoption across diverse domains and use cases. Users report successfully applying DocETL to complex document processing tasks where other tools struggled—for instance, one user switched from LlamaIndex to DocETL for automatically constructing knowledge graphs from textbooks, citing significantly improved results "on the first try." In another use case, the CEO of a security company who uses DocETL for multiple pipelines (e.g., analyzing logs) said, "DocETL is simply amazing. It simplifies what would otherwise be a painful document processing pipeline." We've seen successful deployments spanning healthcare (medical record analysis), legal (real estate closing documents, regulatory compliance), and scientific research (synthetic biology literature analysis, climate action plan evaluation). Users have also applied DocETL to more general enterprise tasks like summarizing

customer support tickets, extracting insights from financial reports, and resolving product entities in e-commerce catalogs. A particularly challenging use case involves forensic psychiatry records dating back to the 1970s, where DocETL effectively processes a mix of handwritten notes, various form formats, and evolving electronic records. While in many cases, DocETL adds multiple synthesized operations to a pipeline, users are able to—and want to—understand DocETL's optimized plans; the operations are simply described by natural language prompts, making them intuitive and transparent.

Since the initial release, based on user feedback, we have extended DocETL with production-critical features including rate limiting and open source model support, optimization of the resolve operator to skip redundant comparisons via transitivity, logging of intermediate outputs and prompts for observability, and a UI playground for rapid prototyping.

# 6 Discussion and Limitations

We reflect on the differences between DocETL and traditional database systems. Then, we acknowledge limitations of our work.

Revisiting Traditional Database Paradigms. LLM-powered document processing systems like DocETL differ from traditional database systems across several layers, ranging from operators—both logical and physical—to rewriting and optimization, to user specification and intent. The core difference is that LLMs are inherently non-deterministic and not always accurate. At the operator level, traditional database systems guarantee correct and consistent outputs, regardless of physical implementation choices. A hash join or nested loop join will produce identical results, differing only in performance characteristics. In contrast, DocETL's output quality and correctness can vary dramatically based on physical operator parameter choices. For example, different fold batch sizes or gather configurations directly impact accuracy rather than just performance. Moreover, even logical operators work differently; unlike traditional DBMSes where atomic attributes (e.g., a blob of text) remain atomic, DocETL must decompose these attributes, because LLM accuracy often decreases as document size increases. The processing order of these decomposed units matters—LLMs cannot always process chunks independently, which motivates specialized operations like our gather operator and folding approach for reduce operations.

Second, rewriting in traditional databases is purely logical and guaranteed to produce identical output, but in DocETL, it's semantic and instantiated by LLMs. In DocETL, operator output quality for rewrites can vary—e.g., if the LLM agent happens to synthesize bad prompts—and rewriting is not just for performance (latency), but also correctness. Moreover, unlike traditional DBMSes where there is only one way of executing a rewrite, here there are infinite. Consequently, the space of possible plans is infinite, even for a single operator, because each plan is instantiated by LLMs that could generate countless variations of prompts and configurations.

Third, optimization in DocETL is different because we lack a good model for accuracy, unlike well-understood cost models in traditional DBMS optimizers. DocETL must empirically evaluate plans using LLMs themselves as judges. LLMs are inherently uncalibrated for accuracy estimation [31], so we must score and rank actual sample outputs using pairwise comparisons. Moreover, in

DocETL, operator accuracy depends heavily on accuracy of other operators, and during optimization, the best suffix of a plan directly depends on which subplan was chosen for the prefix. This means that unlike traditional optimizers, e.g., Selinger's algorithm [41] or Cascades [16], that can optimize subplans and apply dynamic programming or divide and conquer to assemble an optimal plan, DocETL cannot rely on operator independence.

Finally, the specification layer in DocETL is inherently fuzzy. DocETL specifications can be ambiguous because they are in natural language, allowing flexibility in interpretation by LLMs. However, this flexibility comes with limitations—specifications may not capture all corner cases that might arise during processing, requiring robust fault tolerance mechanisms to handle unexpected scenarios when output schemas fail or rate limits are exceeded.

Limitations. While DocETL demonstrates accuracy improvements in real-world applications, there are some limitations. First, using LLMs for both directive implementation and validation risks shared biases, although our validation agent's different perspective often identifies issues despite sharing the underlying model. Recent work from the ML community has demonstrated that LLMs can often be more effective as verifiers than generators, especially if prompted to focus on specific criteria, as our validation agents do [52, 54, 55]. Nevertheless, our optimizer allows users to specify different models for the rewrite and validation agents, and we're exploring several other mitigation strategies: diversifying prompts; incorporating human expertise in the optimizer through interactive refinement of pipelines; and exploring hybrid validation approaches that combine LLM assessment with traditional techniques (e.g., allowing a user to provide labeled ground truth to verify accuracy via exact string matching). These ideas are guiding our development of a prototype interface for DocETL that enables users to incorporate their expertise both during optimization and by directly editing or correcting outputs, providing a human-in-the-loop approach to complement automated complex document processing.

# 7 Related Work

LLM-powered data processing frameworks have recently gained significant attention in the database community. LOTUS [37] extends Pandas with semantic operators, while Palimpzest [29] provides a declarative framework focusing on map-like operations. Aryn [1] offers a Spark-like API with PDF extraction capabilities and human-in-the-loop processing. Unlike DocETL, these systems primarily make simplifying assumptions about task complexity, typically focusing on extraction tasks or queries that capable LLMs can handle without decomposition. They employ various cost-based optimizations, including classical techniques like predicate pushdown [18] and ML-specific approaches like model cascades [49]. However, when applied to complex document processing tasks, even state-of-the-art models fall short. DocETL addresses this limitation through agent-driven optimization, exploring decomposition to improve accuracy. Moreover, DocETL is, uniquely, the only system to support documents with lengths that exceed LLM context windows and introduces new operators (e.g., gather, split) for this, as well as for entity resolution as a first-class citizen.

Other LLM-powered data processing systems focus on different settings—typically making strong assumptions about the structure of the documents and predictability of format. ZenDB [28] optimizes SQL queries for templatized documents, while DocETL handles arbitrary documents. EVAPORATE [3] specializes in table extraction through code synthesis (only where applicable, in semi-structured settings), which could complement DocETL. Regarding LLM agents: Caesura [47] uses LLMs to translate natural language to SQL pipelines but leaves optimization for future work; CleanAgent [40] uses agents to standardize and clean data (and also does not consider optimization). Other systems propose specialized pipelines for specific tasks: for instance, Edge et al. [11] use a fixed map-reduce pipeline with predefined prompts for knowledge graph querying—whereas DocETL enables flexible pipeline construction and optimization for any document processing task. A common limitation across these systems is inadequate context management, particularly for documents exceeding context windows or tasks requiring cross-document reasoning. While prompt optimization [25, 50] could complement DocETL, it falls short on complex document tasks, even with human guidance [51], particularly when data and tasks exceed single LLM call capabilities. Moreover, LLMs have been leveraged for a variety of data tasks beyond document processing, such as join discovery [10, 24], database tuning [46], ML pipelines [42], natural language to SQL [39], semantic table understanding [9, 12]. and others [14], but not for complex document processing.

Finally, declarative frameworks for intelligent data processing have a rich history in database research through crowdsourcing systems like CrowdDB, Deco, CDB, and Qurk [15, 27, 32, 35]. While these systems use human rather than machine intelligence, they demonstrate declarative interfaces' power for complex tasks. DocETL extends this tradition to address the unique challenges of LLM-powered processing [36] through its flexible interface and agent-driven optimization.

# 8 Conclusion

We introduced DocETL, a declarative system that optimizes complex document processing tasks using LLMs. We introduced several novel rewrite directives, an agent-based framework for plan rewriting and evaluation, and an opportunistic optimization strategy. Our evaluation across four unstructured document analysis tasks demonstrated that DocETL can find plans with outputs  $21 - 80\%$  more accurate than baselines. DocETL is a first step toward an agentic optimizer for LLM-powered data processing. While exploring the large space of possible plan decompositions is hard, our approach shows that automated optimization is both feasible and beneficial. Future work will focus on reducing cost by considering cheaper models for simpler sub-tasks, and incorporating human feedback to refine plans. With growing real-world adoption, DocETL provides a foundation for future research and applications in complex document processing.

# References

[1] Eric Anderson, Jonathan Fritz, Austin Lee, Bohou Li, Mark Lindblad, Henry Lindeman, Alex Meyer, Parth Parmar, Tanvi Ranade, Mehul A. Shah, Benjamin Sowell, Dan Tecuci, Vinayak Thapliyal, and Matt Welsh. 2024. The Design of an LLM-powered Unstructured Analytics System. arXiv:2409.00847 [cs.DB] https://arxiv.org/abs/2409.00847

[2] Guido Appenzeller. 2024. Welcome to LLMfflation - LLM inference cost is going down fast. a16z Blog, https://a16z.com/llmflation-llm-inference-cost/ (2024).  
[3] Simran Arora, Brandon Yang, Sabri Eyuboglu, Avanika Narayan, Andrew Hojel, Immanuel Trummer, and Christopher Re. 2023. Language models enable simple systems for generating structured views of heterogeneous data lakes. arXiv preprint arXiv:2304.09433 (2023).  
[4] Yushi Bai, Xin Lv, Jiajie Zhang, Hongchang Lyu, Jiankai Tang, Zhidian Huang, Zhengxiao Du, Xiao Liu, Aohan Zeng, Lei Hou, et al. 2023. Longbench: A bilingual, multitask benchmark for long context understanding. arXiv preprint arXiv:2308.14508 (2023).  
[5] Steven Bird, Ewan Klein, and Edward Loper. 2009. Natural language processing with Python: analyzing text with the natural language toolkit. "O'Reilly Media, Inc."  
[6] Surajit Chaudhuri. 1998. An overview of query optimization in relational systems. In Proceedings of the seventeenth ACM SIGACT-SIGMOD-SIGART symposium on Principles of database systems. 34-43.  
[7] Vassilis Christophides, Vasilis Efthymiou, Themis Palpanas, George Papadakis, and Kostas Stefanidis. 2020. An Overview of End-to-End Entity Resolution for Big Data. ACM Comput. Surv. 53, 6, Article 127 (dec 2020), 42 pages. https://doi.org/10.1145/3418896  
[8] Tyson Condie, Neil Conway, Peter Alvaro, Joseph M Hellerstein, Khaled Elmelegy, and Russell Sears. 2010. MapReduce online.. In Nsdi, Vol. 10. 20.  
[9] Tianji Cong, Madelon Hulsebos, Zhenjie Sun, Paul Groth, and HV Jagadish. 2023. Observatory: Characterizing Embeddings of Relational Tables. Proceedings of the VLDB Endowment 17, 4 (2023), 849-862.  
[10] Yuyang Dong, Chuan Xiao, Takuma Nozawa, Masafumi Enomoto, and Masafumi Oyamada. 2022. DeepJoin: Joinable Table Discovery with Pre-trained Language Models. arXiv preprint arXiv:2212.07588 (2022).  
[11] Darren Edge, Ha Trinh, Newman Cheng, Joshua Bradley, Alex Chao, Apurva Mody, Steven Truitt, and Jonathan Larson. 2024. From local to global: A graph rag approach to query-focused summarization. arXiv preprint arXiv:2404.16130 (2024).  
[12] Xi Fang, Weijie Xu, Fiona Anting Tan, Jiani Zhang, Ziqing Hu, Yanjun Qi, Scott Nickleach, Diego Socolinsky, Srinivasan Sengamedu, and Christos Faloutsos. 2024. Large Language Models on Tabular Data-A Survey. arXiv preprint arXiv:2402.17944 (2024).  
[13] Raul Castro Fernandez, Aaron J. Elmore, Michael J. Franklin, Sanjay Krishnan, and Chenhao Tan. 2023. How Large Language Models Will Disrupt Data Management. Proc. VLDB Endow. 16, 11 (jul 2023), 3302-3309. https://doi.org/10.14778/3611479.3611527  
[14] Raul Castro Fernandez, Aaron J Elmore, Michael J Franklin, Sanjay Krishnan, and Chenhao Tan. 2023. How large language models will disrupt data management. Proceedings of the VLDB Endowment 16, 11 (2023), 3302-3309.  
[15] Michael J Franklin, Donald Kossmann, Tim Kraska, Sukriti Ramesh, and Reynold Xin. 2011. CrowdDB: answering queries with crowdsourcing. In Proceedings of the 2011 ACM SIGMOD International Conference on Management of data. 61–72.  
[16] Goetz Graefe. 1995. The Cascades Framework for Query Optimization. IEEE Data(base) Engineering Bulletin 18 (1995), 19-29. https://api(semanticscholar.org/ CorpusID:260706023  
[17] Ashish Gupta, Inderpal Singh Mumick, and Venkatramanan Siva Subrahmanian. 1993. Maintaining views incrementally. ACM SIGMOD Record 22, 2 (1993), 157-166.  
[18] Joseph M Hellerstein and Michael Stonebraker. 2005. Anatomy of a database system. Readings in Database Systems, (2005).  
[19] Dan Hendrycks, Collin Burns, Anya Chen, and Spencer Ball. 2021. CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review. NeurIPS (2021).  
[20] Matthew Honnibal, Ines Montani, Sofie Van Landeghem, and Adriane Boyd. 2020. spaCy: Industrial-strength Natural Language Processing in Python. https://doi.org/10.5281/zenodo.1212303  
[21] Clayton Hutto and Eric Gilbert. 2014. Vader: A parsimonious rule-based model for sentiment analysis of social media text. In Proceedings of the international AAAI conference on web and social media, Vol. 8, 216-225.  
[22] Huiqiang Jiang, Qianhui Wu, Xufang Luo, Dongsheng Li, Chin-Yew Lin, Yuqing Yang, and Lili Qiu. 2023. Longlmlingua: Accelerating and enhancing llms in long context scenarios via prompt compression. arXiv preprint arXiv:2310.06839 (2023).  
[23] Adam Tauman Kalai and Santosh S Vempala. 2024. Calibrated language models must hallucinate. In Proceedings of the 56th Annual ACM Symposium on Theory of Computing, 160-171.  
[24] Moe Kayali, Anton Lykov, Ilias Fountalis, Nikolaos Vasiloglou, Dan Olteanu, and Dan Suciu. 2024. Chorus: Foundation Models for Unified Data Discovery and Exploration. Proceedings of the VLDB Endowment 17, 8 (2024), 2104-2114.  
[25] Omar Khattab, Arnav Singhvi, Paridhi Maheshwari, Zhiyuan Zhang, Keshav Santhanam, Saiful Haq, Ashutosh Sharma, Thomas T Joshi, Hanna Moazam, Heather Miller, et al. 2024. DSPy: Compiling Declarative Language Model Calls into State-of-the-Art Pipelines. In The Twelfth International Conference on Learning Representations.

[26] Mosh Levy, Alon Jacoby, and Yoav Goldberg. 2024. Same task, more tokens: the impact of input length on the reasoning performance of large language models. arXiv preprint arXiv:2402.14848 (2024).  
[27] Guoliang Li, Chengliang Chai, Ju Fan, Xueping Weng, Jian Li, Yudian Zheng, Yuanbing Li, Xiang Yu, Xiaohang Zhang, and Haitao Yuan. 2018. CDB: A crowd-powered database system. Proceedings of the VLDB Endowment 11, 12 (2018), 1926-1929.  
[28] Yiming Lin, Madelon Hulsebos, Ruiying Ma, Shreya Shankar, Sepanta Zeigham, Aditya G Parameswaran, and Eugene Wu. 2024. Towards Accurate and Efficient Document Analytics with Large Language Models. arXiv preprint arXiv:2405.04674 (2024).  
[29] Chunwei Liu, Matthew Russo, Michael Cafarella, Lei Cao, Peter Baille Chen, Zui Chen, Michael Franklin, Tim Kraska, Samuel Madden, and Gerardo Vitagliano. 2024. A Declarative System for Optimizing AI Workloads. arXiv preprint arXiv:2405.14696 (2024).  
[30] Nelson F Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Michele Bevilacqua, Fabio Petroni, and Percy Liang. 2024. Lost in the middle: How language models use long contexts. Transactions of the Association for Computational Linguistics 12 (2024), 157-173.  
[31] Yinhong Liu, Han Zhou, Zhijiang Guo, Ehsan Shareghi, Ivan Vulic, Anna Korhonen, and Nigel Collier. 2024. Aligning with Human Judgement: The Role of Pairwise Preference in Large Language Model Evaluators. In First Conference on Language Modeling. https://openreview.net/forum?id=9gdZI7c6yr  
[32] Adam Marcus, Eugene Wu, David R Karger, Samuel Madden, and Robert C Miller. 2011. Crowdsourced databases: Query processing with people. Cidr.  
[33] Maxwell Nye, Anders Johan Andreassen, Guy Gur-Ari, Henryk Michalewski, Jacob Austin, David Bieber, David Dohan, Aitor Lewkowycz, Maarten Bosma, David Luan, et al. 2021. Show your work: Scratchpads for intermediate computation with language models. arXiv preprint arXiv:2112.00114 (2021).  
[34] Pallets. 2024. Jinja. https://github.com/pallets/jinja/. Version 3.1.x.  
[35] Aditya Ganesh Parameswaran, Hyunjung Park, Hector Garcia-Molina, Neoklis Polyzotis, and Jennifer Widom. 2012. Deco: declarative crowdsourcing. In Proceedings of the 21st ACM international conference on Information and knowledge management. 1203-1212.  
[36] Aditya G Parameswaran, Shreya Shankar, Parth Asawa, Naman Jain, and Yujie Wang. 2024. Revisiting Prompt Engineering via Declarative Crowdsourcing. Cidr (2024).  
[37] Liana Patel, Siddharth Jha, Parth Asawa, Melissa Pan, Carlos Guestrin, and Matei Zaharia. 2024. Semantic Operators: A Declarative Model for Rich, AI-based Analytics Over Text Data. arXiv preprint arXiv:2407.11418 (2024).  
[38] Binghui Peng, Srini Narayanan, and Christos Papadimitriou. 2024. On limitations of the transformer architecture. arXiv preprint arXiv:2402.08164 (2024).  
[39] Mohammadreza Pourreza, Hailong Li, Ruoxi Sun, Yeounoh Chung, Shayan Talaei, Gaurav Tarlok Kakkar, Yu Gan, Amin Saberi, Fatma Ozcan, and Sercan O Arik. 2024. Chase-sql: Multi-path reasoning and preference optimized candidate selection in text-to-sql. arXiv preprint arXiv:2410.01943 (2024).  
[40] Danrui Qi and Jiannan Wang. 2024. CleanAgent: Automating Data Standardization with LLM-based Agents. arXiv preprint arXiv:2403.08291 (2024).  
[41] P Griffiths Selinger, Morton M Astrahan, Donald D Chamberlin, Raymond A Lorie, and Thomas G Price. 1979. Access path selection in a relational database management system. In Proceedings of the 1979 ACM SIGMOD international conference on Management of data. 23-34.  
[42] Shreya Shankar and Aditya G Parameswaran. 2024. Building Reactive Large Language Model Pipelines with Motion. In Companion of the 2024 International Conference on Management of Data. 520-523.  
[43] Freda Shi, Xinyun Chen, Kanishka Misra, Nathan Scales, David Dohan, Ed H Chi, Nathanael Schärli, and Denny Zhou. 2023. Large language models can be easily distracted by irrelevant context. In International Conference on Machine Learning. PMLR, 31210-31227.  
[44] Peiqi Sui, Eamon Duede, Sophie Wu, and Richard Jean So. 2024. Confabulation: The Surprising Value of Large Language Model Hallucinations. arXiv preprint arXiv:2406.04175 (2024).  
[45] Raphael Tang, Xinyu Zhang, Xueguang Ma, Jimmy Lin, and Ferhan Ture. 2023. Found in the middle: Permutation self-consistency improves listwise ranking in large language models. arXiv preprint arXiv:2310.07712 (2023).  
[46] Immanuel Trummer. 2022. DB-BERT: a Database Tuning Tool that" Reads the Manual". In Proceedings of the 2022 international conference on management of data. 190-203.  
[47] Matthias Urban and Carsten Binnig. 2024. Demonstrating CAESURA: Language Models as Multi-Modal Query Planners. In Companion of the 2024 International Conference on Management of Data. 472-475.  
[48] Tempest A. van Schaik and Brittany Pugh. 2024. A Field Guide to Automatic Evaluation of LLM-Generated Summaries. In Annual International ACM SIGIR Conference on Research and Development in Information Retrieval. https://apisemantic scholar.org/CorpusID:271114432  
[49] Xin Wang, Yujia Luo, Daniel Crankshaw, Alexey Tumanov, Fisher Yu, and Joseph E Gonzalez. 2017. Idk cascades: Fast deep learning by learning not to overthink. arXiv preprint arXiv:1706.00885 (2017).

[50] Yuxin Wen, Neel Jain, John Kirchenbauer, Micah Goldblum, Jonas Geiping, and Tom Goldstein. 2024. Hard prompts made easy: Gradient-based discrete optimization for prompt tuning and discovery. Advances in Neural Information Processing Systems 36 (2024).  
[51] Jules White, Quchen Fu, Sam Hays, Michael Sandborn, Carlos Olea, Henry Gilbert, Ashraf Elnashar, Jesse Spencer-Smith, and Douglas C Schmidt. 2023. A prompt pattern catalog to enhance prompt engineering with chatgpt. arXiv preprint arXiv:2302.11382 (2023).  
[52] Lunjun Zhang, Arian Hosseini, Hritik Bansal, Mehran Kazemi, Aviral Kumar, and Rishabh Agarwal. [n.d.]. Generative Verifiers: Reward Modeling as Next-Token Prediction. In The 4th Workshop on Mathematical Reasoning and AI at NeurIPS '24.  
[53] Jun Zhao, Can Zu, Hao Xu, Yi Lu, Wei He, Yiwen Ding, Tao Gui, Qi Zhang, and Xuanjing Huang. 2024. LongAgent: Scaling Language Models to 128k Context through Multi-Agent Collaboration. arXiv preprint arXiv:2402.11550 (2024).  
[54] Lianmin Zheng, Wei-Lin Chiang, Ying Sheng, Siyuan Zhuang, Zhanghao Wu, Yonghao Zhuang, Zi Lin, Zhuohan Li, Dacheng Li, Eric Xing, et al. 2023. Judging Ilm-as-a-judge with mt-bench and chatbot arena. Advances in Neural Information Processing Systems 36 (2023), 46595-46623.  
[55] Lianghui Zhu, Xinggang Wang, and Xinlong Wang. 2025. JudgeLM: Fine-tuned Large Language Models are Scalable Judges. In The Thirteenth International Conference on Learning Representations.

# A Gather Operator Specifications

# A.1 Gather Configuration

The gather operation's configuration includes:

- The group ID key (document ID)  
- The order key (chunk sequence within a group)  
- The content key (field containing chunk content)  
- The peripheral chunk configuration

The peripheral chunk configuration specifies "previous" and "next" sections, each potentially containing "head", "middle", and "tail" subsections, determining which surrounding chunks to include and how many. Each subsection must specify a content_key denoting the field to use as the content of the chunk.

# A.2 Header Lineage Preservation

A unique feature of the gather operation is its ability to maintain document structure through headers. This is particularly useful for documents with complex structures where processing a chunk with a certain level header requires knowledge of headers in the levels above, which may be in other chunks.

When a doc_header_key is specified in the configuration, the gather operation:

(1) Examines the doc_header_key field for every chunk preceding the one being rendered.  
(2) Reconstructs the relevant header structure by identifying the level of the first header in the current chunk and including all most recent headers from higher levels found in previous chunks.  
(3) Arranges these headers in their proper order.

This process ensures that each rendered chunk includes a complete "path" of headers leading to its content, preserving the document's overall structure and context even when split across multiple chunks.

Figure 6 demonstrates header handling in a gather operation for a 74-page legal contract. Headers are extracted from chunks via map operations. When rendering a chunk (e.g., Chunk 20), the operation includes the most recent headers of all levels (1, 2, etc.) above the first header in the current chunk, providing hierarchical context for LLM processing.

# B Rewrite Directive Instantiation

This appendix provides a detailed walkthrough of how an LLM agent instantiates a rewrite directive in DocETL, using the legal contract analysis task in Section 5.1.

# B.1 Initial Task and Baseline Operation

Our baseline approach used a single map operation with a prompt listing all 41 clause types to extract from legal contracts:

Given the following contract document:

{{input.document}}

Extract the text spans (if they exist) for each of the following categories. If a category is not present or cannot be determined, return an empty string. If there are multiple text spans for a category, return them as a comma-separated list of text spans.

1. Document Name: The name of the contract  
2. Parties: The two or more parties who signed the contract  
3. Agreement Date: The date of the contract  
4. Effective Date: The date when the contract is effective  
5. Expiration Date: On what date will the contract's initial term expire?  
6. Renewal Term: What is the renewal term after the initial term expires? This includes automatic extensions and unilateral extensions with prior notice.  
7. Notice to Terminate Renewal: What is the notice period required to terminate renewal?  
8. Governing Law: Which state/country's law governs the interpretation of the contract?  
9. Most Favored Nation: Is there a clause that if a third party gets better terms on the licensing or sale of technology/goods/services described in the contract, the buyer of such technology/goods/services under the contract shall be entitled to those better terms?  
10. Non-Compete: Is there a restriction on the ability of a party to compete with the counterparty or operate in a certain geography or business or technology sector?  
11. Exclusivity: Is there an exclusive dealing commitment with the counterparty? This includes a commitment to procure all "requirements" from one party of certain technology, goods, or services or a prohibition on licensing or selling technology, goods or services to third parties, or a prohibition on collaborating or working with other parties), whether during the contract or after the contract ends (or both).  
12. No-Solicit of Customers: Is a party restricted from contracting or soliciting customers or partners of the counterparty, whether during the contract or after the contract ends (or both)?  
13. Competitive Restriction Exception: This category includes the exceptions or carveouts to Non-Compete, Exclusivity and No-Solicit of Customers above.  
14. No-Solicit of Employees: Is there a restriction on a party's soliciting or hiring employees and/or contractors from the counterparty, whether during the contract or after the contract ends (or both)?  
15. Non-Disparagement: Is there a requirement on a party not to disparage the counterparty?  
16. Termination for Convenience: Can a party terminate this contract without cause (solely by giving a notice and allowing a waiting period to expire)?  
17. Right of First Refusal, Offer or Negotiation: Is there a clause granting one party a right of first refusal, right of first offer or right of first negotiation to purchase, license, market, or distribute equity interest, technology, assets, products or services?  
18. Change of Control: Does one party have the right to terminate or is consent or notice required of the counterparty if such party undergoes a change of control, such as a merger, stock sale, transfer of all or substantially all of its assets or business, or assignment by operation of law?

![](images/868775a8bfc5d8a12ce99bd190c8c83c9b792b8a771600342efdf2b1d66759f9.jpg)  
Figure 6: Example of Document Header Handling in a Gather Operation for Legal Contracts [19]. The example document has 74 pages. Headers are extracted from chunks via map operations. When rendering a chunk (e.g., Chunk 20), the operation includes the most recent headers of all levels (1, 2, etc.) above the first header in the current chunk, so the LLM has hierarchical context when processing the chunk.

19. Anti-Assignment: Is consent or notice required of a party if the contract is assigned to a third party?  
20. Revenue/Profit Sharing: Is one party required to share revenue or profit with the counterparty for any technology, goods, or services?  
21. Price Restriction: Is there a restriction on the ability of a party to raise or reduce prices of technology, goods, or services provided?  
22. Minimum Commitment: Is there a minimum order size or minimum amount or units per-time period that one party must buy from the counterparty under the contract?  
23. Volume Restriction: Is there a fee increase or consent requirement, etc. if one party's use of the product/services exceeds certain threshold?  
24. IP Ownership Assignment: Does intellectual property created by one party become the property of the counterparty, either per the terms of the contract or upon the occurrence of certain events?  
25. Joint IP Ownership: Is there any clause providing for joint or shared ownership of intellectual property between the parties to the contract?  
26. License Grant: Does the contract contain a license granted by one party to its counterparty?  
27. Non-Transferable License: Does the contract limit the ability of a party to transfer the license being granted to a third party?  
28. Affiliate IP License-Licensor: Does the contract contain a license grant by affiliates of the licensor or that includes intellectual property of affiliates of the licensor?  
29. Affiliate IP License-Licensee: Does the contract contain a license grant to a licensee (incl. sublicense) and the affiliates of such licensee/subLICENSE?  
30. Unlimited/All-You-Can-Eat License: Is there a clause granting one party an "enterprise," "all you can eat" or unlimited usage license?  
31. Irrevocable or Perpetual License: Does the contract contain a license grant that is irrevocable or perpetual?  
32. Source Code Escrow: Is one party required to deposit its source code into escrow with a third party, which can be released to the counterparty upon the occurrence of certain events (bankruptcy, insolvency, etc.)?  
33. Post-Termination Services: Is a party subject to obligations after the termination or expiration of a contract, including any post-termination transition, payment, transfer of IP, wind-down, last-buy, or similar commitments?  
34. Audit Rights: Does a party have the right to audit the books, records, or physical locations of the counterparty to ensure compliance with the contract?

35. Uncapped Liability: Is a party's liability uncapped upon the breach of its obligation in the contract? This also includes uncap liability for a particular type of breach such as IP infringement or breach of confidentiality obligation.  
36. Cap on Liability: Does the contract include a cap on liability upon the breach of a party's obligation? This includes time limitation for the counterparty to bring claims or maximum amount for recovery.  
37. Liquidated Damages: Does the contract contain a clause that would award either party liquidated damages for breach or a fee upon the termination of a contract (termination fee)?  
38. Warranty Duration: What is the duration of any warranty against defects or errors in technology, products, or services provided under the contract?  
39. Insurance: Is there a requirement for insurance that must be maintained by one party for the benefit of the counterparty?  
40. Covenant Not to Sue: Is a party restricted from contesting the validity of the counterparty's ownership of intellectual property or otherwise bringing a claim against the counterparty for matters unrelated to the contract?  
41. Third Party Beneficiary: Is there a non-contracting party who is a beneficiary to some or all of the clauses in the contract and therefore can enforce its rights against a contracting party?

# The output schema specified a list of clause-text pairs:

output: schema: clauses:'list[{clause_type:string，textSpan:string}]

# B.2 Optimization Process

B.2.1 Determine If Optimization Is Needed The DocETL optimizer first evaluates whether the operation needed improvement. The system uses an LLM agent to synthesize a validator prompt. This agent is provided the operation prompt and sample outputs, and instructed to devise binary validation criteria around precision and recall. The following validator prompt was generated:

1. Did the operation successfully extract all relevant text spans for each

```txt
category listed in the task prompt, ensuring no instances were missed, especially for categories with multiple possible text spans?   
2. Is the extracted information presented in the correct format, with text spans properly separated by commas where applicable, and are there any inconsistencies or errors in the extracted data?
```

When applied to sample outputs from the original user-written operation, the LLM validator replies:

```txt
"Needs improvement. Row 1 output is mostly accurate, but it misses several important categories such as 'Renewal Term', 'Notice to Terminate Renewal', 'Governing Law', 'Most Favored Nation', 'Exclusivity', 'No-Solicit of Customers',... The extraction process should be improved to ensure that all categories listed in the task prompt are addressed, even if the information is not present in the document. For categories that do not have applicable text spans, the output should explicitly state that the category is not applicable or that the information is missing, rather than omitting it entirely."
```

B.2.2 Select and Apply Rewrite Directive Based on this assessment, DocETL programmatically matches the case to applicable rewrite directives. For this example, we will focus on the implementation of Equation (11), which decomposes a complex map operation into independent subtasks. The optimizer then invokes the LLM agent with: the original prompt and output schema, sample contract documents, and instructions to decompose the task. As of March 2025, DocETL uses the following prompt to the LLM agent:

```txt
Original task prompt: {original_prompt}   
Output schema the operation will produce: { "clauses": "list[{clause_type: string, textSpan: string}]"}   
Input data sample: {sample_contract_text}   
Decompose the original task into parallel subtasks, where each subtask produces one or more keys of the output schema. Assume that the subtasks can be executed independently. You cannot rely on the output of one subtask to complete another subtask. Make sure you include the same input variables as in the original task prompt. Each prompt should be a Jinja2 template...   
[Additional instructions about format...]
```

B.2.3 LLM Agent Generates Decomposed Operations The LLM agent responded with a detailed decomposition plan:

```txt
{
"subtasks":[ "name":"extractbasic_contract_information","prompt":"From the following contract document:{inputdocument}]{nExtract the following basic information:\n- Document Name: The name of the contract\n- Parties: The two or more parties who signed the contract\n-Agreement Date: The date of the contract\n- Effective Date: The date when thecontract is effective\n- Expiration Date: On what date willthe contract's initial term expire?",
```

```jsonl
"output_keys": [ "document_name", "parties", "agreement_date", "effective_date", "expiration_date"] }, { "name": "extract_renewal_andterminationClauses", "prompt": "From the following contract document: \{input. document\} \nExtract the following clauses related to renewal and termination:\n- Renewal Term: What is the renewal term after the initial term expires?n- Notice to Terminate Renewal : What is the notice period required to terminate renewal?\nTermination for Convenience: Can a party terminate this contract without cause?", "output_keys": [ "renewal_term", "notice_toTerminate_renewal", "termination_for_convenience"] }, { "name": "extract_legal_governanceClauses", "prompt": "From the following contract document: \{ input. document\} \nExtract the following legal governance clauses:\n- Governing Law: Which state/country's law governs the interpretation of the contract?n- Anti-Assignment: Is consent or notice required of a party if the contract is assigned to a third party?\n- Change of Control: Does one party have the right to terminate or is consent or notice required if such party undergoes a change of control?", "output_keys": [ "governing_law", "anti_assignment", "change_of_control"] }, ....further clauses omitted due to brevity ] }
```

We similarly prompt the LLM to synthesize an additional operation to convert the flat schema output from the parallel_map into the original output schema format expected by the user, following Equation (11). For the sake of this walk-through, we will assume that each newly synthesized operation is able to accurately perform its subtask, but in practice, DocETL will recursively apply rewrites to each new subtask.

B.2.4 Plan Evaluation and Selection After generating the aforementioned plan and several alternatives (with variations in groupings and decomposition strategies), DocETL executes all the candidate plans on a sample, and invokes the validation agent to rate and compare outputs of plans. DocETL picks the top-ranked plan to replace the original operation with. Overall, the LLM agent effectively turns a high-level rewrite directive into a concrete implementation by, understanding the original task and data, identifying semantically meaningful ways to decompose it, generating appropriate prompts for each subtask, and creating the necessary schema transformations.

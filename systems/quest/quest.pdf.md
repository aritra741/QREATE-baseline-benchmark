# QUEST: Query Optimization in Unstructured Document Analysis

Zhaoze Sun, Qiyan Deng, Chengliang Chai, Kaisen Jin, Xinyu Guo+,

Han Han+, Ye Yuan, Guoren Wang, Lei $\mathrm {Cao}^{*\dagger }$ 

University of Arizon $\mathrm {na}^{\dagger },$ MIT*, Beijing Institute of Technology

# ABSTRACT

Most recently, researchers have started building large language models (LLMs) powered data systems that allow users to analyze unstructured text documents like working with a database because LLMs are very effective in extracting attributes from documents. In such systems, LLM-based extraction operations constitute the per-formance bottleneck of query execution due to the high monetary cost and slow LLM inference. Existing systems typically borrow the query optimization principles popular in relational databases to produce query execution plans, which unfortunately are inef-fective in minimizing LLM cost. To fill this gap, we propose QUEST, which features a bunch of novel optimization strategies for un-structured document analysis. First, we introduce an index-based strategy to minimize the cost of each extraction operation. With this index, QUEST quickly retrieves the text segments relevant to the target attributes and only feeds them to LLMs. Furthermore, we design an evidence-augmented retrieval strategy to reduce the possibility of missing relevant segments. Moreover, we develop an instance-optimized query execution strategy: because the attribute extraction cost could vary significantly document by document, QUEST produces different plans for different documents.For each document, QUEST produces a plan to minimize the frequency of attribute extraction. The innovations include LLM cost-aware oper-ator ordering strategies and an optimized join execution approach that transforms joins into filters. Extensive experiments on 3 real-world datasets demonstrate the superiority of QUEST, achieving 30%-6x cost savings while improving the F1 score by 10%-27% compared with state-of-the-art baselines.

# 1 INTRODUCTION

Modern corporations often maintain a large amount of unstruc-tured data including text documents such as web pages. In fact, according to IDC research [2], unstructured data accounts for 80%-90% of the data. Recently, researchers have started building LLMs-powered systems, such as UQE [9], ZenDB [29], Lotus [35],and Palimpzest [30], to analyze the valuable information hidden in text documents. These systems allow a user to select a set of documents, specify some attributes that can be extracted from them, and apply some database analytical operations on these attributes,e.g.,filter, aggregation, or join. The core is to leverage LLMs [4,36,39] to effectively extract out the attribute values that users are interested in because recent research [3] shows that LLMs are remarkably good at data extraction. These efforts, if successful, can turn un-structured data into actionable insights. For instance, a lawyer may employ this system to swiftly locate legal cases about murder with a minimum of three charges and a 15-year sentence.

Similar to traditional databases, a successful unstructured data analysis system relies on a query optimizer that automatically pro-duces a plan, minimizing query execution costs. However, LLMs play a central role in such a system, raising unique challenges and optimization opportunities. More specifically, compared to traditional database operations, LLM inferences are much more expensive in both execution time and monetary cost [30], no mat-ter whether using commercial LLM services or deploying open source LLMs on high-performance thus expensive GPUs. Because unstructured data analysis relies on LLMs to extract attributes, the extraction operation thus constitutes its performance bottleneck. Therefore, the key optimization objective in this scenario is to min-imize the LLM cost incurred during extraction, equivalent to (1) minimizing the LLM cost of each extraction operation, which de-pends on the number of input tokens to an LLM, and (2) minimizing the frequency of invoking the data extraction operations.

To achieve the above optimization objective, we propose QUEST with two key components: (1) an index-based attribute extraction strategy to minimize the number of input tokens per extraction; (2) an instance-optimized query execution strategy to minimize the frequency of attribute extraction. Crucially, these optimization strategies are model-agnostic. Although the cost and performance may vary across different LLMs, the core principles of QUEST remain effective in reducing the number of input tokens and extraction frequency. QUEST thus offers an affordable and scalable approach that allows users to select thousands of documents from a large document collection, specify any attributes out of tens or even hundreds of attributes that these documents potentially contain, and analyze these attributes.

**(1)Index-based Attribute Extraction.** QUEST designs an index for LLMs to efficiently and effectively extract attributes from docu-ments. Rather than using LLMs to scan each document routinely, it only feeds LLMs the relevant text segments, thus significantly reducing the number of input tokens. This retrieval augmented gen-eration (RAG) inspired solution features twoinnovative designs: a two-level index and evidence augmented retrieval.

Two-level Index. First, QUEST summarizes the subject of each docu-ment and indexes this information to filter documents irrelevant to the target attributes. Then QUEST builds a segment level index to retrieve relevant segments from the remaining documents. Com-pared to existing document analysis systems such as ZenDB [29], which filter data only at the segment level, our two-level strategy more accurately identifies the relevant segments because it avoids erroneously recognizing some segments as relevant when they are from documents in different subjects.

Evidence Augmented Retrieval. Second, when searching the index, existing RAG style solutions tend to miss relevant segments, be-cause the query, which typically contains the attributes and their text description, is often not informative enough. To solve this prob-lem, one can rely on users to manually enhance text descriptions like prompt engineering, but it is tedious and time-consuming. We propose a sampling-based approach to automatically collect the evidence on what the relevant segments should look like and use this evidence to augment the retrieval.

<!-- S70CmnfI[8Q.so] CASIS90:L0SC:AIXT -->

**(2) Instance-optimized Query Execution.** Rather than first ex-tracting out the attribute values involved in a query and then em-ploying the database query optimizer to produce an execution plan, QUEST adopts a lazy extraction strategy. That is, it interleaves at-tribute extraction and analytical operations (e.g., filter or join), only extracting an attribute when an analytical operation has to evaluate it. In this way, QUEST opens optimization opportunities to minimize the frequency of data extraction. For example, if a legal case in a document is not about murder, QUEST does not have to extract other attributes, e.g., the number of charges or the years of the sentence. Intuitively, similar to relational databases, appropriately ordering the filters or the joins in a query could effectively avoid extracting the values that have no chance to appear in the final query results.

Guided by the optimization objective of QUEST, we revisit the query optimization principles in databases, e.g.,filter ordering, pred-icate pushdown, and join ordering. As detailed in Sec. 3, rather than simply ordering the filters based on their selectivities and apply-ing the same order to process all documents, QUEST produces an instance-optimized order for each individual document, leverag-ing the observation that extracting the same attribute could incur significantly different cost across documents.

To accurately estimate the extraction cost per document-the key of this instance optimized strategy, QUEST adopts an "optimize at execution time" architecture. That is, unlike traditional database optimizers, which produce optimized plans before query execution, QUEST estimates the cost during query execution time and produces a plan per document on the fly.

Moreover, we show that pushing down the predicates does not always yield the optimal plan. Instead, QUEST introduces a join transformation method that converts a join into a specialized fil-ter and orders it with other filters in the query. We theoretically show that the plan produced in this way is guaranteed to be bet-ter than predicate pushdown. For a multi-way join, QUEST faces challenges in estimating join selectivities as data records are not available in advance. To address this, we introduce a dynamic join ordering strategy that determines which tables to join during query execution, leveraging our optimize at execution time architecture.

To summarize, we make the following contributions.

(1) We propose an execution-time optimizer that produces query plans instance-optimized w.r.t. different documents.

(2) We propose a join transformation technique that is guaranteed to outperform the classical predicate pushdown strategy.

(3) We propose a two-level index to effectively filter irrelevant seg-ments, reducing extraction costs without compromising accuracy.

(4) Extensive experiments demonstrate the superiority of QUEST, achieving 0.3-6x cost savings while improving the F1-score by 10%-27% compared with the state-of-the-art baselines.

# 2 QUEST OVERVIEW

In this section, we first introduce howv a user specifies a query and the types of queries that QUEST supports. We then describe QUEST's overall architecture and highlight the novel designs.

## 2.1 User Queries

In QUEST, a user could formulate a query in SQL semantics similar to ZenDB [29]. That is, the user selects a subset of documents from her data sources, e.g., the legal documents produced in the last two years. She then specifies some attributes that can potentially be extracted from these documents and applies some analytical opera-tions such as filtering and joining on these attributes. Note that the key techniques of QUEST are orthogonal to the query language and thus are compatible with other systems such as Palimpzest [30], which uses Python-style interfaces. Moreover, users who favor querying in natural language can use QUEST, which can employ current NL2SQL techniques [15, 16,31] to convert NL queries into SQL-like queries.

**Supported** **Queries.** In this work, we target optimizing Selection-Projection-Join (SPJ) queries over unstructured documents. We leave optimizations on other important types of queries as future work, such as aggregation.

We first introduce some notations. A denotes the set of attributes in the user-specified query $Q$ , and $a_{i}$  denotes each attribute in A. $\theta$  denotes the expression in the WHERE clause of $Q$ , consisting of a series of filters, and $\theta _{j}$ corresponds to each filter in 9. QUEST supports a broad range of filters. (1) QUEST supports queries that are conjunctions or disjunctions of any number of filters. As an example, in Figure 1, the query $Q$  seeks to find NBA players who are over the age of 35 and have made more than 12 All-Star appearances. The expression $\theta$  is a conjunction of these two filters $(.g.,\theta$ $:age>$ $35\text {ANDall-stars}>12)$ . (2) Any single filter $\theta _{j}$ for $a_{i}\in A$ can be an equality filter(e.g., $\theta _{j}:$ ai ="Kevin Durant"), an open range filter $\left(\text {e.g.,}\theta _{j}:a_{i}>27\right.$  or a close range filter $\left(\text {.g.,}\theta _{j}:25\leq _{i}\leq 30\right)$ $QUEST$  also supports join operations. We use $\mathcal {G}=\{\mathcal {T},\mathcal {E}\}$ to denote the join graph, where nodes(T) denote the set of tables and edges (ε) represent the join relations.

## 2.2 Overall Framework

Inspired by the principle of relational databases, QUEST first indexes the documents and conducts query optimization once receiving a query.However, different from traditional databases, which mini-mize query execution time, QUEST targets reducing LLM costs while ensuring analysis quality. We thus propose several innovative de-signs to achieve these objectives by (1) minimizing the cost of the attribute extraction via index and (2) minimizing the frequency of calling the extraction via query optimization.

Given a document collection $\mathcal {D}=\left\{d_{1},d_{2},\cdots ,d_{}\right\}$ , QUEST first builds a two-level index over all documents. Then, once the user selects a subset of documents, specifies some attributes in these documents, and composes a query on these attributes, QUEST will first sample some documents, extract the attribute values from them and collect some statistics used by the query optimizer, which aims to minimize the LLM costs of extracting attributes from documents However,fundamentally different from traditional databases, QUEST optimizer does not produce a query plan before query execution. Instead, it uses these statistics and the LLM costs calculated during query execution to produce optimized plans on the fly.Moreover, given a query, it produces query plans at a document by document basis instead of presuming a uniform plan for all documents. This is because the attribute extraction cost could vary significantly from

<!-- 2 -->


| Two-Level Index Offline Building<br>e(d1) 00 e(s1) 000<br>Segment<br>→ 000<br>e(d2) 000 e(s2) →<br>→ 000 Document →<br>000<br>Index<br>Index<br>Summarization & Embedding Segmentation & Embedding |
| --- |
| SELECT name, team Evidence-Augmented Segment Retrieval<br>FROM Players Relevant<br>WHERE age&gt;35 AND all-stars&gt;12 000 Attribute:age Documents<br>Value:36 Attribute 1:age<br>&lt;Description&gt; 000 Key Segment:... born March 3, Candidate 1:...born March 14, 1988...<br>Players: Basic info of NBA players. Doc-Index LLM 1988 Attribute 2:all-stars<br>Seg-Index<br>Candidate 1:...an NBA All-Star Game<br>name:Player's full name. Value:14 MVP...<br>Attribute:all-stars<br>team: Player's current team. Sample All-Star...<br>Key Segment:...a five-time NBA Candidate 2:...a ten-time NBA All-Star<br>---- Relevant<br>Query Q Documents Evidence Collection |
| Query Optimization<br>Statistics Order II P.name,T.coach II P.name,T.coach<br>SELECT P.name, T.coach<br>Filter Cost Sel age FROM Players P, Teams T ☒P.team =T.tname P.team=T.tname<br>age 30 0.2 WHERE T.championships&gt;6 II team IItname IIteam Otname IN [..]<br>all-stars 100 0.1 all-stars AND P.age&gt;35 AND P.all-stars&gt;12 Ordering σ champ.&gt;6 Ordering σ champ.&gt;6<br>Ordering<br>Filter Cost Sel AND P.team =T.tname<br>all-stars O all-stars&gt;12 σ all-stars&gt;12<br>age 35 0.2 &lt;Description&gt;...... σ age&gt;35 σ age&gt;35<br>all-stars 25 0.1 age Query Q'<br>Doc-level Filter Reordering Join Transformation |


**Figure 1: QUEST Framework**

document to document. To quickly produce these plans, QUEST fea-tures novel optimization strategies,which,although lightweight, guarantee to produce optimal plans in many cases.The query exe-cution engine uses index-based data extraction and other analytical operations such as join to execute query plans efficiently.

QUEST's key components include: a two-level index-based strat-egy to minimize the cost of extracting attributes from the documents - the most fundamental operation in QUEST; and (2) a query opti-mizer that revisits the classical query optimization principles in relational databases, such as filter ordering, predicate pushdown, and join ordering, to avoid unnecessary extraction operations.

## 2.3 Index-based Attribute Extraction

The key idea is to use an index to quickly and accurately identify the text segments that potentially contain the target attributes and only feed these relevant segments to LLMs for extraction. Moreover, we leverage the common patterns shown in the sample segments that have the target attributes to improve the extraction quality. The details are presented in Sec. 4.1.

At a high level, the index-based tuple extraction resembles Re-trieval Augmented Generation (RAG). That is, QUEST divides all documents into segments, encodes each segment into an embed-ding, and loads the embeddings into a high dimensional vector index such as PQ [18] or HNSW [33]. When a query comes, QUEST encodes the name of the relevant attributes and their corresponding text descriptions into an embedding. It then uses the vector index to retrieve the segments with embeddings similar to the query embedding. Then QUEST only extracts tuples from these segments.

QUEST optimizes the two key steps of this basic RAG style strat-egy,namely the indexing and the retrieval.

**Two-level** **Index.** In addition to indexing documents at the seg-ment level, QUEST constructs a document-level index to filter the documents irrelevant to the to-be-extracted attributes.The segment-level index will only be used to retrieve the relevant segments from the remaining documents, as shown in Figure 1. QUEST produces this document-level index by first extracting the key sentences from each document, encoding these sentences into an embedding e(di) to represent the document, and then indexing these embeddings. Next, QUEST segments each document, encodes each segment into an embedding e(si), and builds the segment-level index.

**Evidence-Augmented Segment Retrieval.** Although QUEST lets users explain attributes, embeddings from attribute names and descriptions often lack information to find all relevant segments. For example, when QUEST extracts the age attribute, simply embedding age alongside its description "Player's age." to search relevant segments may miss the segments such as "Wardell Stephen Curry II (born March 14,1988) is an American professional basketball player and point guard ...". This mismatch occurs because the segment does not explicitly mention "age", but instead contains a birthdate and unrelated details like "point guard". Therefore, its embedding is not necessarily similar to that of the query.

Rather than relying on users to provide such hints, which in fact is equivalent to a tedious prompt engineering process, QUEST automatically collects suich valuable information during sampling, serving as evidence to augment segment retrieval. Specifically,when using LLMs to extract an attribute from document samples, QUEST records the segments where a corresponding attribute value is ex-tracted from the sampled documents. Then QUEST encodes these segments into representative embeddings and uses each as evidence to retrieve the segments relevant to this attribute from the rele-vant documents. Finally, it merges all these segments,eliminates duplicates, and inputs them into the LLM for extraction.

<!-- 3 -->

## 2.4 Query Optimization

We revisit the classical query optimization principles in relational databases, such as filter ordering, predicate pushdown, and join ordering, to avoid unnecessary attribute extraction operations. **Filter Ordering.** In QUEST, the LLM cost of extracting different at-tributes from a document collection could vary significantly because the QUEST index tends to discover various numbers of relevant text segments with respect to different attributes. Similarly,the extrac-tion cost varies significantly document by document, even when extracting the same attribute. This variant cost observation guides us to propose a new strategy to order filters when multiple filters exist in one query.

First, unlike traditional databases, which simply order the filters based on their selectivities, QUEST orders the filters based on a cost model that takes into consideration both the LLM cost-the number of tokens of the relevant segments and the selectivities estimated on sample documents. In Figure 1, taking query $Q$  as an example, for document $d_{1}$ ,the filter on age with a low selectivity but a small number of candidate tokens should have a higher priority than the filter on allstars which although has a low selectivity, faces a large number of input tokens, thus incurring high LLM cost. Using this new cost model, we design a linear logarithmic time complexity algorithm that produces optimal plans in a broad range of scenarios.

Moreover, because extracting the same attribute from different documents could incur different costs, QUEST thoroughly abandons the “one single order for one query" methodology in traditional databases and instead produces different orders when evaluating tuples extracted from different documents, as shown in Figure 1.

EXAMPLE 1. For the query in Figure 1, the selectivity of all-stars, which is estimated on some sample documents, is smaller than that of age. However, the LLM costs vary between documents $d_{1}$  and $d_{2}$ . Therefore, when processing $d_{1}$ ,QUEST will extract age before all-stars, because the cost of extracting all-stars is significantly higher. On the contrary, the cost of extracting all-stars from $d_{2}$  is slightly lower than that of extracting age. Thus, QUEST will prioritize all-stars over age due to its low selectivity.

**Join** **Transformation.** Although QUEST couldexecute a join by first extracting the attributes of the two tables involved in the join and then applying an existing join algorithm such as hash join, this is sub-optimal due to the prohibitive attribute extraction cost,while minimizing the extraction cost is QUEST's key objective. Therefore, we propose a join transformation strategy that first extracts the join attribute of one table and then uses the extracted values as filters to filter the other table (as shown in the bottom right of Figure 1). In other words, QUEST transforms a join into a filter.Treating this automatically generated filter equally to other filters, the QUEST optimizer uses the cost model discussed above to order these filters. In this way, QUEST might prioritize joins over filters to minimize the LLM cost, contradictory to the predicate pushdown principle in traditional databases.

EXAMPLE 2. In Figure 1, Players and Teams join on the team (tname) attribute with the filters "P $age>35$  AND P $\text {P.all-stars>12}$ and "T. championships&gt;6". Suppose that after applying $\text {'P.age>35}$ AND P $\text {all-stars>}12^{\prime \prime }$ ,only a few documents satisfy the filters on Players; and the values of the team attribute only include Warriors, Lakers and Celtics in these remaining documents. QUEST will add an IN filter "T.tteam IN [Warriors, Celtics, Lakers]" to Teams and order it with the existing filter "T.championships&gt;6".If the new filter has low selectivity and cost, it is likely to be executed prior to "T.championships&gt;6", thus saving LLM cost.

**Dynamic** **Join** **Ordering.** Different join orders may incur signif-icantly different costs when multiple joins exist in a query. To reduce search space, traditional databases typically use dynamic programming to identify an effective order. However, accurately estimating join selectivities, the key to effectively ordering joins, is still an open problem. This is even worse in QUEST because the attribute values and the tables are not available beforehand. To address this issue, we introduce an algorithm that dynamically and progressively decides the join order during query execution. More specifically, QUEST first selects two tables to join based on our cost model, and it will determine the next join only after the first join finishes execution. This process iterates in a left-deep manner until all joins have been executed. In this way, every time QUEST decides which table to join, the left table has already been extracted. This effectively alleviates the problem of estimating join selectivity.

In the remainder of this paper, we first introduce our query optimization techniques to minimize the frequency of attribute extraction (Sec. 3), which constitute our core technical novelties. Then, in Sec. 4, we introduce our index-based attribute extraction method, which minimizes the LLM cost of each extraction operation while improving the accuracy.

**Remark.** Although our primary focus is on optimizing the LLM cost for executing individual query, QUEST's architecture naturally supports multiple concurrent queries. First, the two-level index built offline efficiently supports concurrent queries.Furthermore, the instance-optimized nature of query execution, processing doc-uments either individually or in batches, enables straightforward intra-query parallelism: a query spanning numerous documents can be partitioned across multiple workers, each executing the optimized plan for its document subset. Crucially, QUEST is able to cache the results of LLM attribute extractions. By storing and reusing previously extracted tuples, redundant extraction opera-tions can be eliminated among concurrent queries, significantly reducing overall cost and latency. These aspects, combined with standard database concurrency control mechanisms, ensure that QUEST is effective in serving simultaneous user requests. However, in-depth exploration of specific optimizations and benchmarking the performance of multiple query processing are beyond the scope of this paper and represent important directions for future work.

# 3 QUERY OPTIMIZATION

We first discuss the filter ordering optimization in Sec. 3.1. Then, we present the optimizations with respect to join in Sec. 3.2, including the optimization of one single join and join ordering.

## 3.1 Filter Ordering

As introduced in Section 2.4, QUEST differs from relational databases on filter ordering strategy, because QUEST's key objective is to mini-mize the LLM cost in extracting tuples. In this section, we introduce our filter ordering method that takes both the number of input tokens to LLMs and the selectivities of the filters into considera-tion, yields optimal orders with respect to different combinations of filters, e.g., conjunction, disjunction, or a mix of both.

### 3.1.1 The Filter Ordering Problem in QUEST

The filter ordering in QUEST aims to find an order of extracting attributes and evaluating the corresponding filters to minimize the LLM cost. Furthermore, as discussed in Section 2.4, because the extraction cost could vary significantly document by document, QUEST produces different orders with respect to different documents. Formally,we use $C_{Q}(o)$  to denote the total cost of executing query $Q$  on a document with an order (denoted by $0$ ) of the filters in $\theta$ .The goal is to find the optimal order $o*:$ 

$$o^{*}=\arg \min _{o\in O}C_{Q}(o)\tag{1}$$

Next, we introduce our filter ordering method and analyze its optimality considering different combinations of filters, namely conjunction, disjunction, and a mix of both.

### 3.1.2 Conjunctions

Consider a query $Q$  that includes a WHERE clause containing a con-junction of filters. Let $A_{}\subseteq A,A_{w}\subseteq A$ denote the set of attributes that appear in SELECT and WHERE clauses,respectively.For each filter $o[i]$  (i.e., the i-th filter in the order), the cost associated with extracting its relevant attribute is represented as $c^{F}[i]$ ,and its se-lectivity is given by p[i]. For each attribute aj E. $A_{}$ ,the generation cost is denoted by $c_{}^{E}$ . Therefore, for a given order $0$ , the expected query cost can be represented as follows:

$$C_{Q}(o)=\sum _{i=1}^{|o|}c^{F}[i]\prod _{j=1}^{i-1}p[j]+\left(\sum _{j=1}^{\left|A_{s}\right|}c_{j}^{E}\right)\prod _{i=1}^{|o|}p[i]\tag{2}$$

where $\prod _{j=1}^{i-1}p[j]$ represents the likelihood that filter $c^{F}[i]$ has to be processed by an LLM, given that all its preceding filters in $0$  return True. $\prod _{i=1}^{||}$ $p[i]$ represents the probability of all filters returning True. Only in this case, QUEST has to extract the attributes in the SELECT clause, leading to a cost of $\sum _{j=1}^{\left|A_{}\right|}c_{j}^{E}$ 

Remark. Note that for conjunctions, $A_{s}$  will have to be extracted only if all filters return True. Therefore, in this scenario, QUEST should always extract the attributes in $A_{w}$  first,followed by $A_{s}$ .As a result, when QUEST computes the optimal order for conjunctions, it only has to consider the cost of extracting attributes in $A_{w},$ i.e., only the first term in Equation 2.

Optimal Order. To find the optimal order with respect to each doc-ument, the brute-force method is to enumerate all possible orders, which has a time complexity of $O\left(\left|D_{Q}^{*}\right|x\left|A_{w}\right|!\right)$ and therefore is too costly. Our key insight here is that using the cost model in Eq.3, QUEST is able to find the optimal order $P^{*}$ in linear logarithmic time.

First, given a filter $\theta _{k}\in vrtht$ , QUEST uses the index to retrieve the segments relevant to the corresponding attribute and estimates its cost $c_{k}$  which is proportional to the number of tokens in these seg-ments. QUEST then uses its selectivity $p_{k}$  estimated on the sampled table,and the cost $c_{k}$  to compute a priority score, which determines the position of each filter $\theta _{k}$ in the optimal order.

LEMMA 1. Sorting filters in descending order based on the following priority score minimizes the expected query cost.

$$\text {priority}\left(\theta _{k}\right)=\frac {1-p_{k}}{c_{k}},\theta _{k}\in vartheta\tag{3}$$

Intuitively,Eq. 3 prioritizes a filter that is more likely to return False and has a low LLM cost. The proof of this lemma can be found in our technical report [1].

### 3.1.3 Disjunctions

For disjunctions, a better order should instead prioritize a filter that is more likely to return True. QUEST thus has a better chance to short-circuit other filters. Accordingly, we modify the cost model from Eq. 2 to the equation below:

$$\mathcal {C}_{Q}()=\sum _{i=1}^{||}c^{F}[i]\prod _{j=1}^{i-1}(1-p[j])+\left(\sum _{j=1}^{\left|A_{s}\right|}c_{j}^{E}\right)\left[1-\prod _{i=1}^{||}(1-p[i])\right]\tag{4}$$

Optimal Order. In this scenario, QUEST can still produce the optimal order by sorting the filters by their priority scores in descending order if the score is computed slightly different from Eq. 3.

$$\text {priority}\left(\theta _{k}\right)=\frac {p_{k}}{c_{k}},\theta _{k}\in vartheta.\tag{5}$$

However, in the disjunction scenario, the attributes $A_{s}$ in SELECT clause have to be handled differently, especially when an attribute exists in both the WHERE and SELECT clauses,e $\text {g.,}A_{}\cap$ $A_{w}\neq \emptyset .$ In this scenario, to correctly evaluate the query, these attributes must be extracted for the following reasons: (1) if one filter in $A_{w}$ returns true, QUEST has to extract them as the output of the query;(2)if no filter in $A_{w}$ returns true, although QUEST does not produce any output, it still has to extract these attributes. This is because in such circumstances QUEST has to examine all filters in $A_{w}$ while these attributes are also part of $A_{s}$ 

Therefore,if $A_{s}\cap$ $A_{w}$ $\neq \emptyset ,$  QUEST first extracts the attributes in $A_{s}\cap A_{w},$ followed by sorting and executing the filters in $A_{s}\backslash$ $\left(A_{s}\cap A_{w}\right)$ based on their priority scores, which still guarantees the optimal result. The proof is analogous to the way we prove the optimality of conjunction and, hence,is omitted here.

### 3.1.4 Conjunctions and Disjunctions

The aforementioned method can be extended to queries that involve both conjunctions (AND) and disjunctions (OR).

The observation here is that any expressions $\theta$  within the WHERE clause is a boolean expression, which can be represented nat-urally as an expression tree [38]; and the execution of the ex-pression is equivalent to a postorder traversal of the tree. As shown in Figure 2, each leaf node corresponds to a filter and each non-leaf node denotes a conjunction or disjunction of its chil-dren with the same operator precedence. Considering Figure 2, (01 OR θ2)AND $\left(\theta _{3}\mathrm {O}\right.$ $\theta _{4}$ AND θ5) is the expression within the WHERE clause of $Q$ ,where the leaf nodes correspond to each filter,i.e., $\theta _{1}$ to $\theta _{5}$ . $\theta _{1},$ $\theta _{2}$ are siblings because they have the same operation precedence.

Representing the expression with a tree structure naturally breaks it down into several sub-expressions. The expected total cost can be computed as a weighted sum of the expected costs of these sub-expressions, with the weights being the probability of each sub-expression evaluated to be True, namely the selectivity. As the weight (selectivity) assigned to each sub-expression is invariant to the order, minimizing the total expression cost is thus equivalent to minimizing the cost of each sub-expression. This property allows us to use dynamic programming to identify the optimal order of these sub-expressions, where the above sorting strategy can be applied to order the filters within each sub-expression. Equation 6formalizes the optimization objective.

<!-- 5 -->

$$\mathcal {C}^{*}\left(\theta _{T}\right)=\left\{\begin{aligned}&\min _{o\in O\left(\theta _{T}\right)}\left(\sum _{i=1}^{\left|\theta _{T}\right|}\mathcal {C}^{*}(o[i])\prod _{j=1}^{i-1}p_{o[j]}\right),\\ &\min _{o\in O\left(\theta _{T}\right)}\left(\sum _{i=1}^{\left|\theta _{T}\right|}\mathcal {C}^{*}(o[i])\prod _{j=1}^{i-1}(1-p_{o[j]})\right),\\ &c_{\theta _{T}},\quad \text {forasinglefilter,}i.e.,\left|\theta _{T}\right|=1\end{aligned}\right.\tag{6}$$

where $vartheta_{T}$ represents the set of children (i.e., sub-expressions) of the current node.o $\in O\left(varha_{T}\right)$ is one of the possible orders of the sub-expressions in $\theta _{T}$ ,where $o[i]$  is the i-th sub-expression. For example, if $T$  is the root of the tree in Figure 2, then $vartheta_{T}=$ $\left\{\left(\theta_{1}\right.\right.$ $\left.\left.\text {OR}\theta _{2}\right),\left(\theta _{3}\text {OR}\theta _{4}\text {AND}\theta _{5}\right)\right\}$ $p_{o[j]}$ denotes the probability of the $j$  th sub-expression in the order being True. Here, $O\left(\theta _{T}\right)$  refers to all possible orders of sub-expressions in $vartheta_{T}$ and $\left|O\left(vatta_{T}\right)\right|=2$ For the boundary condition, if $vartheta_{T}$  is a single filter, $C^{*}\left(vartheta_{T}\right)$ equals the cost of this filter. We implement the algorithm in a recursive manner in Algorithm 1. The overall time complexity is $O(|\theta |\log |\theta |)$ .

<!-- $\theta _{1}\rightarrow \theta _{2}\rightarrow \theta _{3}\rightarrow \theta _{5}\rightarrow \theta _{4}$ AND $\theta _{1}\rightarrow \theta _{2}$ $\theta _{3}\rightarrow \theta _{5}\rightarrow \theta _{4}$ θ1 $\theta _{2}$ θ3 $\theta _{5}\rightarrow \theta _{4}$ AND $\theta _{4}$ θs $\theta _{5}$ -->
![](https://web-api.textin.com/ocr_image/external/4c63bdda45f883df.jpg)

$\left(\theta _{1}OR\theta _{2}\right)$ AND( $\left(\theta _{3}OR\right.$ $\theta _{4}$ AND $\left.\theta _{5}\right)$ 

**Figure 2: Example of the Expression Tree.**

EXAMPLE 3. For the expression in Figure 2, take the leaf node $\theta _{1}$ as an example. Based on the boundary condition in Equation $6$ , its optimal expected cost $C^{*}\left(\left\{\theta _{1}\right\}\right)$  equals to the cost o $\text {f}\theta _{1}$ itself.Using the cost and selectivity of $\theta _{1}$ , we can calculate its priority score (Line 5-Line 6). The same applies to $\theta _{2}$ .Then, employing the first formulation from Equation 6, we calculate the optimal cost $C^{*}\left(\left\{\theta _{1}\theta _{2}\right\}\right)$ based on the priority score of $\theta _{1}$  and $\theta _{2}$ ,thus resulting in the order $\theta _{1}\rightarrow \theta _{2}$ (Line 11). Subsequently, the recursive call returns this order as the optimal order for the sub-expression( $\theta _{1}\text {OR}\theta _{2}$ θ(Line 8).We can further calculate the cost and selectivityto derive the priority score of $\theta _{1}$ OR $\theta _{2}$ (Line 8-Line 10). Similarly, we have the optimal order $\theta _{5}\rightarrow \theta _{4}$ for the sub-expression $\theta _{4}$ AND $\theta _{5}$  as well $as$  its priority score (Notably, similar to traditional databases, AND is executed with higher precedence than OR here). Next, we sort the sub-expressions $\theta _{3}$  and $\theta _{4}$ AND θ5 according to the priority of $\theta _{3}$  and $\theta _{4}$  AND $\theta _{5}$ , obtaining $\theta _{}\rightarrow \theta _{}\rightarrow \theta _{}$ (Line $5$ -Line $11$ ).Finally, for the full expression that serves as the entry point for recursion (Line 13),i.e., the root node, we derive the final optimal execution order: $\theta _{1}\rightarrow \theta _{2}\rightarrow \theta _{3}\rightarrow \theta _{5}\rightarrow \theta _{4}$ 

## 3.2 Query Optimization For Join

Next, we introduce the optimization techniques with respect to join queries. We begin with optimizing one single join, and then extend our discussion to queries involving multiple joins.

### Algorithm 1: Filter Ordering

**Input:** The expression $vartheta_{T}$  within the WHERE clause of $Q$ .

**Output**: The optimal order $o^{*}$ .

1 **def** Reorder( $\left(\theta _{T}\right)$ :

2

$$prior.init()$$

3

**for** $vartheta_{i}\in vartheta_{T}\text {do}$ 

$$\left|vartheta_{i}\right|=1\mathbf {t}\quad then$$

5

6

$c_{i},p_{i}=\text {Statistics}\left(vartheta_{i}\right);\text {prior.append}\left(vartheta_{i},c_{i},p_{i}\right);$ $//$ Leaf node

**else**

8

9

$$\begin{array}{l}o_{i}^{*}=\text {Reorder}\left(vartheta_{i}\right);\parallel \text {Non-leaf}\\ C^{*}\left(vartheta_{i}\right),p_{i}=\text {Statistics}\left(o_{i}^{*}\right);\end{array}\quad node$$

10

$\widehat {\circ }_{*}$ $prior.appen$ $\left.i),p_{i}\right)$ 

11

$o^{*}=0$ ptimalOrder(prior);// w.r.t. Equation 6

12

$$returno*$$

13 $o^{*}=\text {Reorder}\left(vartheta_{T}\right);$ 

14 **return** $o^{*}$ 

### 3.2.1 Single Join: Joining Two Tables

Consider a query that joins two tables $T_{1}$  and $T_{2}$  on attribute $a$ $\text {(i.e.,}\left.T_{}·=T_{2}·^{\prime }\right).$ .The query also has multiple filters 9. We abuse $\theta _{1}$  and $\theta _{2}$ a little to denote the filters on $T_{1}$  and $T_{2}$  respectively.

Typically, relational databases apply filters before joins to reduce the number of tuples in costly join operations. However, to minimize LLM costs, we find that converting joins into filters and optimizing them with other filters is often more effective in our scenario.

Taking the query in Figure 3 as an example, $\theta _{1}$  corresponds to the filter on $T_{1}$  (the Teams table), where T.championships&gt;6, and $\theta _{2}$  corresponds to the filter on $T_{2}$  (the Players table),where $\text {P.age}>35.$ A traditional query optimizer first pushes down $\theta _{1}$ and $\theta _{2}$ to $T_{1}$ and $T_{2}$ ,respectively. It then performs a join on the returned documents (i.e., the tuples underlined in Figure 3-c). We establish a cost mode1 to compute the expected cost under this optimization. [Plan ①:Push $\theta _{1}$ to $T_{},\theta _{2}$  to $T_{2}$  and join] The expected cost under the optimal order can be calculated as:

$$\text {Cost}\left(\theta _{1}\left(T_{1}\right)ogmapsto\theta _{2}\left(T_{2}\right)\right)=\sum _{i=1}^{\left|T_{1}\right|}\mathcal {C}_{1}^{i}+p_{1}\sum _{i=1}^{\left|T_{1}\right|}c_{a}^{i}+\sum _{i=1}^{\left|T_{2}\right|}\mathcal {C}_{2}^{i}+p_{2}\sum _{i=1}^{\left|T_{2}\right|}c_{a^{\prime }}^{i}\tag{7}$$

where $C_{1}^{i}$ is the expected cost of executing $\theta _{1}$  on the $i$  th document of $T_{1}$ . $p_{1}$  is the likelihood of having to extract $a$ after performing $\theta _{1}$  ,and $c_{a}^{i}$  is the cost of extracting $a$  from the $i$ -th document in $T_{1}$ .The expected cost of $\theta _{2}\left(T_{2}\right)$  is calculated in the same way.


| SELECT P.playername<br>FROM Players P, Teams T<br>WHERE P.age&gt;35<br>AND $T.championships>6$AND P.teamname=T.teamname |
| --- |



| Filters | sel | cost |
| --- | --- | --- |
| T.championships&gt;6 | 0.1 | 50 |
| T.teamname(join) | 0.3 | 30 |
| P.age&gt;35 | 0.3 | 50 |
| P.teamname(join) | 0.1 | 30 |


( $)Query$ 

(b) Statistics


| teamname | championships |
| --- | --- |
| Lakers | 17 |
| $Bulls$ | 6 |
| Celtics | 17 |
| $Warriors$ | 7 |
|  |  |



| playername | age | teamname |
| --- | --- | --- |
| LeBron James | 39 | Lakers |
| Stephen Curry | 36 | Warriors |
| Rudy Gobert | 32 | Timberwolves |
| Chris Paul | 39 | Warriors |
|  |  |  |


(c) Teams (30 tuples) (d)Players (51 tuples)

**Figure 3: Example for JOIN**

<!-- 6 -->

According to Figure 3, the cost of executing $\theta _{1}$  on $T_{1}$ can be computed as $\sum _{i=1}^{\left|T_{1}\right|}$ $C_{1}^{i}=\left|T_{1}\right|\times c_{1}^{i}=30\times 50=1500$ ,while the cost of extracting $a$  on $T_{1}$ can be computed as $p_{1}\sum _{i=1}^{\left|T_{1}\right|}c_{a}^{i}=p_{1}x\left|T_{1}\right|xc_{a}^{i}=0.1x30x30=90.$ Simi-larly,we have $\sum _{i=1}^{\left|T_{2}\right|}$ $C_{2}^{i}=2550$ and $p_{2}\sum _{i=1}^{\left|T_{2}\right|}c_{a^{\prime }}^{i}=459\text {on}T_{2}.$ Finally,we have $\text {Cost}\left(\theta _{1}\left(T_{1}\right)triangleright\theta _{2}\left(T_{2}\right)\right)=4599.$ 

However, in our scenario, the optimal plan might not be achieved. We analyze the join operation on unstructured documents, consist-ing of two steps: extracting values of the join attribute from one table and finding matches in the other table. Since the optimization goal of QUEST is to minimize data extraction, a join may not be more costly than a filter operation and could have a higher priority. Similar to filters, the priority of a join operation relies on its own data extraction cost and the potential extraction cost it may intro-duce to the other table, which in turn is determined by the number of matches that each tuple could potentially find, namely the join selectivity. Consequently, the priority of a join can be determined in the same manner as that of a filter. We are now prepared to order operations in a query with one join and multiple filters.

[Optimal Plan: Sort Join and Filters Together.] As shown in Eq. 8, the cost of the optimal order corresponds to:

$$\text {Cost}^{*}\left(\theta _{1}\left(T_{1}\right)boxtimes\theta _{2}\left(T_{2}\right)\right)=\sum _{i=1}^{\left|T_{1}\right|}\hat {C}_{1}^{i}+\sum _{i=1}^{\left|T_{2}\right|}\hat {C}_{2}^{i}\tag{8}$$

where $\hat {C}_{1}^{i}$ represents the optimal expected cost obtained by sorting $\theta _{1}$  with join on the i-th document in $T_{1}$ . The same applies to $\hat {C}_{2}^{i}$ 

Unfortunately, producing this optimal solution requires an ac-curate estimation of the join selectivity, which is known to be a notoriously hard problem in databases. It is even worse in our scenario, where the tables are in fact not available beforehand.

To tackle this challenge, we propose an approach that transforms a join operation into a filter operation and progressively orders the operations during query execution. First, it chooses one table and executes the respective operations, i.e., pushing down the filters on it and then extracting the join attribute. Now, QUEST has acquired all the values of this join attribute that could potentially produce the final query output. Therefore, it is able to convert the join operation into an IN filter and apply it to the other table. Using the samples from the second table, QUEST is able to estimate its selectivity. As a result, QUEST can order other filters along with this IN filter to minimize the expected cost. Essentially, QUEST might end up running the join operation ahead of the filters, contradicting the traditional database optimizers.

Taking Figure 3 as an example, suppose that QUEST chooses to transform the join into an IN operation as a filter on $12$ i.e., “P.teamname IN[Lakers, Celtics, Warriors]". Assume that the selectivity of this filter is 0.1 as shown in Figure 3-b. This means that approximately 10% of the tuples in the Players table can be joined with the tuples in the Teams table that satisfy $\theta _{1}$ .Then QUEST updates $\theta _{2}\text {o}$ $\hat {\theta _{2}}=\text {"P}$ .teamname IN [Lakers, Celtics, Warriors] AND $P.age>35"$ .Because this newly generated filter has a relatively low selectivity and cost, QUEST will prioritize it over existing filters based on the principle discussed in Section 3.1. This filter prunes most documents before running other filters (i.e., P.age&gt;35), thus significantly reducing the LLM cost.

Because we have two options to convert the join operation, namely an IN filter eitheron table $T_{1}$  or table $T_{2}$ , we establish two cost models respectively, for QUEST to make decision.

[Plan ②:Push 6 $\theta _{1}$ to $T_{1}$  and transform the join to filter on $T_{2}$ ] As dis-cussed above, this plan executes01on $T_{1}$ first, and then transforms the join operation to a filter on $12$  .Its cost is estimated as below:

$$\text {Cst}\left(\theta _{1}\left(T_{1}\right)\rightarrow \hat {\theta _{2}}\left(T_{2}\right)\right)=\sum _{i=1}^{\left|T_{1}\right|}\mathcal {C}_{1}^{i}+p_{1}\sum _{i=1}^{\left|T_{1}\right|}c_{}^{i}+\sum _{i=1}^{\left|T_{2}\right|}\hat {\mathcal {C}}_{2}^{i}\tag{9}$$

[Plan $\textcircled {3}$ :Push $\theta _{2}$ to $T_{2}$ and transform the join to filter on $T_{1}$ ]This plan executes $02$  on $T_{2}$ first, then transforms the join to a filter on $T_{1}$ . Its cost can be estimated in a similar way to that of Plan $\textcircled {2}$ .

$$\text {C}\left(\theta _{2}\left(T_{2}\right)\rightarrow \hat {\theta }_{1}\left(T_{1}\right)\right)=\sum _{i=1}^{\left|T_{2}\right|}\mathcal {C}_{2}^{i}+p_{2}\sum _{i=1}^{\left|T_{2}\right|}c_{}^{i}+\sum _{i=1}^{\left|T_{1}\right|}\hat {\mathcal {C}}_{1}^{i}\tag{10}$$

For Plan $\textcircled {2}$ , the cost on $\left|T_{1}\right|$ remains the same compared to Plan ①. However, the cost on $T_{2}$  changes since this plan prioritizes the filter on $a^{\prime }$ . Now the cost is $\sum _{i=1}^{\left|T_{}\right|}\hat {C}_{}^{i}=\left|T_{}\right|x\left(c_{a^{\prime }}^{i}+p_{a^{\prime }}xc_{}^{i}\right)=51x(30+01x50)=1785$ Here, $p_{a^{\prime }}$  is the selectivity of the IN filter. Then the overall cost $\text {bcom}\text {Cot}\left(\theta _{1}\left(T_{1}\right)\rightarrow \hat {\theta _{2}}\left(T_{2}\right)\right)=1590+1785=3375$ 

**Selecting** **a** **Plan.** Next, we discuss how to use the above cost models to produce a query plan. First, we present a lemma showing that Plans $\textcircled {1}$  and $\textcircled {2}$  are at least as good as Plan $\textcircled {1}$  in all cases. The proof can be found in our technical report [1]. Then, we show how $QUEST$ picks one between Plan $\textcircled {2}$ and Plan $\textcircled {3}$ .

LEMMA 2. Given a query $Q$  containing a join operation,the ex-pected cost of Plan $\textcircled {1}$  is always greater than or equal to that of Plan $\textcircled {2}$ $\text {aPa}(3)\text {,i.e.,C}\left(\theta _{1}\left(T_{1}\right)bxime\theta _{2}\left(T_{2}\right)\right)\geq \text {C}\left(\theta _{1}\left(T_{1}\right)\rightarrow \hat {\theta _{2}}\left(T_{2}\right)\right),$ $\text {andCost}\left(\theta _{1}\left(T_{1}\right)boxtimes\theta _{2}\left(T_{2}\right)\right)\geq \text {Cost}\left(\theta _{2}\left(T_{2}\right)\rightarrow \hat {\theta }_{1}\left(T_{1}\right)\right)$ 

Next, QUEST has to make a decision between Plan $\textcircled {2}$  and Plan $\textcircled {3}$ . The simplest approach is to calculate the cost using Equation 9and 10. While the first two terms are straightforward,the challenge lies in determining the third term, specifically the selectivity of $\theta (IN)$  . This is essentially about estimating the join selectivity be-twveen $T_{1}$  and $T_{2}$ . Precise estimation of join selectivity is a known issue in databases. Worst yet, in QUEST, the optimizer only has ac-cess to samples of $T_{1}$  and $T_{2}$ ,not the full tables, before executing the query.

Nonetheless,we state that it is typically sufficient to decide between Plans $\textcircled {2}$  and $\textcircled {3}$  by only considering the first two terms. This is because a small sum of these two terms suggests that the number of tuples, either before or after applying the filters, is small. Consequently,the selectivity of $\theta (IN)$  is low, which likely in turn leads to a small third term. Therefore, if a plan has a smaller cost on the first two terms than the other, its overall cost also tends to be smaller. Thus, given $,T_{2}$  $\sum _{i=1}^{\left|T_{1}\right|}C_{1}^{i}+p_{1}\sum _{i=1}^{\left|T_{1}\right|}c_{a}^{i}<\sum _{i=1}^{\left|T_{2}\right|}C_{2}^{i}+$ P2 $\sum _{i=1}^{\left|T_{2}\right|}c_{a^{\prime }}^{i}$ ,we choose Plan $\textcircled {2}$ , otherwise we choose Plan ③.

**Query Execution in QUEST: Mixing Query Optimization With** **Execution.** After selecting a plan $(e.g.,Plan\textcircled {2})$  , QUEST extracts the values of the join attribute $T_{1}·a$ , executes the filters on it if there are any, and then transforms the join into an IN filter on $T_{2}$ .Since QUEST has obtained all the values of $_{1}$ .a,it can more accurately estimate the selectivity of IN. QUEST then triggers the optimizer again and uses the filter ordering optimization described in Sec. 3.1to produce the optimal order to execute the remaining filters.

### 3.2.2 Adaptive Join Ordering

Next, we discuss the join ordering strategy, which orders multiple joins involved in a query, a classical yet challenging problem in relational databases. Given a set of tables $\mathcal {T}=\left\{T_{1}T_{2}\cdots T_{|\mathcal {T}|}\right\}$ 

<!-- 7 -->

users could specify a join graph $\mathcal {G}=\{\mathcal {T},\mathcal {E}\}$ ,where each edge indicates a join between two tables.In addition, $\theta _{i},i\in [1,|\mathcal {T}|]$ denotes the corresponding filters on table $T_{i}$ .

To produce an optimal join order, the classical database optimiz-ers,e.g.,the Selinger optimizer [7], utilize the dynamic program-ming algorithm [38] that depends on some key statistics, such as the cardinalities of the intermediate join results. Estimating these cardi-nalities becomes rather challenging in our scenario, as the attribute values have not been extracted from unstructured documents yet.

We introduce an adaptive join ordering approach to discover the optimal join order. First, it chooses one single join by iterating every edge $\in \mathcal {E}$ ,i.e.,every join in the query, estimating its cost, and choosing the join with the minimal cost. The cost of each join can be directly estimated using the cost model described in Section 3.2.1. Then it determines the join plan $Plan\textcircled {2}or\textcircled {3}$ ) of this selected join operation and immediately executes this join. We use $T^{\prime }$  to denote the result of the first join. Next, it finds another table to join with $T^{\prime }$ ', forming a left deep query plan. More specifically, we use $J\left(T^{\prime }\right)$ to denote the set of tables that can join with $T^{\prime }$ . QUEST selects the one in $J\left(T^{\prime }\right)$ that incurs the minimal cost. To this end, QUEST has to estimate the cost of $T^{\prime }$ $riangrigh_{j}$ $_{j}\in J\left(^{\prime }\right)$ .As discussed in Sec.3.2.1, because $T^{\prime }$  has already been available, QUEST transforms this join to a IN filter operation and estimates its cost,i.e., $\sum _{i=1}^{\left|_{j}\right|}\hat {C}_{j}^{i}.$ Afterward, it joins $T^{\prime }$  with the selected table according to the join plan. QUEST repeats this process until all joins are conducted.

# 4 INDEX-BASED ATTRIBUTE EXTRACTION

In addition to avoiding unnecessary data extraction operations, we propose an index-based strategy to further reduce the cost of each extraction and improve the accuracy.

## 4.1 Two-level Index Construction

QUEST starts with constructing a document-level index. Given a document set $D$  as input, QUEST first uses the NLTK package to gen-erate a document summary efficiently, which is then transformed into an embedding using a pretrained model. Here, we choose E5Model [44] due to its state-of-the-art performance on massive text embedding benchmarks covering diverse retrieval tasks.

QUEST then constructs the segment-level index. For each docu-ment $d\in \mathcal {D}$ ,QUEST dynamically splits the document into relatively small and semantically coherent segments. The goal is to ensure that each attribute can be extracted from a single segment.To achieve this, we employ the SemanticChunker function in LangChain to segment text by examining both its syntactic structure and seman-tic coherence. Initially, the document is divided into sentences. SemanticChunker then evaluates the embedding similarity of con-secutive sentences. If sentences are semantically coherent,they merge; if not, they remain separate. This iterative procedure contin-ues for all sentences, enhancing attribute extraction by maintaining semantic coherence.

Eventually, these segments are represented as a set S, where each $s\in \mathcal {S}$ is a coherent, self-contained portion of the document's content. QUEST then embeds each segment $s\in \mathcal {S}$  using E5Model. Finally, QUEST loads document and segment embeddings into two high-dimensional vector indexes for efficient data retrieval.

## 4.2 Searching the Index

Given a query, QUEST first uses the document-level index to search the relevant documents and then uses the segment-level index to identify the relevant segments from the returned documents. Doc-**ument** **Retrieval.** Once receiving a query, QUEST retrieves from $D$ the documents that potentially contain an attribute in the qquery.To achieve this, QUEST first converts attribute names and their descrip-tions into embeddings. Then it averages these embeddings to gen-erate a final embedding $e(Q)$ . Afterward, based on the document-level index $\mathcal {I}_{\mathcal {D}}$ , QUEST searches the documents with an embed-ding close to $(Q),i..,$ $D_{Q}=\left\{d_{i}|d_{i}\in \mathcal {D},\right.$ $\left.\text {,dist}\left(e\left(d_{i}\right),e(Q)\right)<τ\right\}$ where $dist()$  is the distance function. While cosine similarity is commonly used for embedding comparison, it is monotonically related to Euclidean distance when vectors are L2-normalized,i.e., $\left\|v_{1}-v_{2}\right\|^{2}=2-$ $.$ $·\cos \left(v_{1},v_{2}\right)$ . Thus, minimizing normalized Eu-clidean distance is equivalent to maximizing cosine similarity for ranking. We adopt it here because it is natively supported in vector indexing libraries such as PQ [18] and is computationally efficient. τ is a threshold initially set as a high value to guarantee a high recall. However, this may return some irrelevant documents. To solve this problem, QUEST automatically adjusts this threshold in the next segment retrieval phase based on the sampled documents to obtain a more precise document set $D_{Q}^{*}$ 

**Evidence Augmented Segment Retrieval.** As discussed in Sec-tion 2.3, to achieve accurate segment retrieval, we propose to sample a small subset (approximately 5% of $D_{Q}$ ) of documents that will be carefully analyzed by an LLM. To be specific, for the attributes in the attribute set $A_{Q}$  of query Q, QUEST asks the LLM to return their values and the segments from which these values are extracted.

Next, we transform these segments into embeddings.The key observation here is that the segments containingthe same attribute tend to show some common patterns. For example, in Stephen Curry's profile, the segment about the "age" attribute includes "Wardell Stephen Curry II (born March 14, 1988) is an American professional basketball player $..."$ , while the corresponding segment in Kevin Durant's profile mentions that "Kevin Wayne Durant (born September 29,1988), also known by KD, is an American professional basketball player.... The patterns of these segments are remarkably similar. Using these patterns as additional evidence could enhance retrieval, addressing the issue where simply using the query embed-ding may miss attribute-relevant segments, as discussed in Sec. 2.3.

When no relevant segments are found for an attribute $a_{i}$  in the sampled documents, QUEST leverages the LLM to synthesize evi-dence. It prompts the LLM with the attribute name, its description, and optional contextual information to generate a small number (e.g., 20) of representative text segments, which are then embedded.

However, using all these embeddings as evidence tends to un-necessarily introduce redundancy and, in turn, produce toomany candidate segments. We thus propose to utilize the $k-$  eans algo-rithm to group these embeddings (with a relatively small $k$ ,such as 3) and only use the cluster centers as evidence. We use $\bar {}_{i}^{j},j\in [1,k]$ to denote one of the cluster centers, i.e., one piece of evidence for $a_{i}$  (k pieces in total for each attribute).

Segment Retrieval. Next, we discuss how to use the collected evi-dence to retrieve the segments relevant to an attribute in the query, e $g$ ., the attributes age and all-stars in the query $Q$  shown in

<!-- 8 -->


|  | $Avg.\#-Tokens$ | #-Doc | $\#-Attributes$ | $\#-Quries$ |
| --- | --- | --- | --- | --- |
| LCR | 6247 | 100 | 10 | 10 |
| WikiText | 1264 | 200 | 20 | 25 |
| SWDE | 416 | 200 | 16 | 15 |


**Table 1: Datasets**

the middle block of Figure 1. For each document in $D_{Q}^{*},$ QUEST uti-lizes the segment-level index $\mathcal {I}_{S}$  to find the relevant segments for a given attribute $a_{i}$  based on each piece of evidence $\overline {e}_{i}^{j}$ -Next, QUEST combines the retrieved segments in each document with respect to the evidence of $a_{i}$ removes the duplicate segments,and feeds them into the LLM for attribute extraction.

Setting the Threshold. QUEST uses two distance thresholds to deter-mine whether a document or a segment is relevant to an attribute. Setting these thresholds appropriately is critical to ensure the qual-ity of retrieval. Setting these distance thresholds too high tends to return many irrelevant segments and hence increase extraction cost, while setting them too small might miss relevant segments, in turn impacting the extraction quality. Clearly, relying on users to manually set these thresholds correctly is challenging. QUEST thus introduces an automatic thresholding method to solve this problem.

For the threshold $1$ used to find documents relevant to a query $Q$ ,QUEST initially sets it as a high value to avoid missing relevant doc-uments. QUEST then adjusts it to an appropriate value by analyzing the LLM extraction results on the sampled documents.Specifically, QUEST first uses the high τ to obtain a set of documents denoted as $D_{Q}$ . QUEST then samples a subset $D_{Q}^{S}$ from $D_{Q}$ and uses LLM to extract the attributes of a table from $D_{Q}^{S}$ . Based on the result of the extraction, QUEST divides $D_{Q}^{S}$ into two subsets: $D_{Q}^{n}$ ,which con-sists of documents lacking attribute information therefore deemed irrelevant to the query,and $D_{Q}^{m}=D_{Q}^{S}\backslash D_{Q}^{},$ ,which contains rele-vant documents. The maximum Euclidean distance between the embeddings of documents in $D_{Q}^{}$ and the embedding $e(Q)$  serves as the threshold,i.e., $τ=\max \left\{\text {dist}\left(\left(d_{i}\right),(Q)\right)|d_{i}\in D_{Q}^{m}\right\}$ .Intuitively, this new $1$ threshold will exclude irrelevant documents.

Similarly, QUEST leverages the sampled documents to set the threshold $γ_{i}$  to retrieve the segments containing an attribute $a_{i}$ $i\in [1,M]$ . More specifically, $γ_{i}$  is set as the maximal distance be-tween any pair of segments containing the value of $a_{i}$ ,i.e., $γ_{i}=$ $\max \left\{\text {dit}\left(E_{i}[x],E_{i}[]\right)|\forall x,\in \left[1,\left|E_{i}\right|\right],x\neq \right\}$  where $E_{i}$  repre-sents the set of segments related to attribute $a_{i}$  in $D_{Q}^{m}$ $E_{}[x]$ and $E_{i}[y]$  denote the x-th and $y$ -th embeddings of two segments in $E_{i}$ .To be cautious, in implementation we increase $γ_{i}$  by 0.1, that is, $γ_{i}=γ_{i}+0.1$ ;and equally we adjust t.

# 5 EXPERIMENTAL EVALUATION

## 5.1 Experimental Settings

**Datasets.** We use 3 datasets with 500 documents in total, cover-ing diverse domains, and 50 queries in various types. We employ human evaluators verifying the attributes extracted by LLMs from documents, and thus establish the ground truth.

LCR [14] includes 3,000 case reports. We sample 100 documents from them. Each document averages 6,247 tokens and contains detailed information such as the court, judge, and legal reasoning. WikiText. We crawl 200 Wikipedia pages across 10 domains, such as directors, cities, NBA players, companies, etc., some of which can be joined; the average number of tokens per document is 1,264. SWDE [19] is a dataset used in our baseline [3]. We sample 200 web pages, with each averaging 416 tokens. Despite the relatively short length of the documents, SWDE contains 16 attributes.

The datasets vary in length, structure, and domain: WikiText has a hierarchical structure across various domains, SWDE includes short documents, and LCR features long documents from a single domain. They facilitate thorough evaluations in various scenarios. Ground Truth Generation. We organize each dataset into domains of similar documents, sample 5 documents per domain, and use LLMs to identify key attributes, as shown in Table 1. We utilize LLMs for attribute extraction from all documents, verified by 10graduate students.

Query Construction. We create queries for single tables and join tables. The queries cover both range and equality filters. We first construct the filters in WHERE clause: (1) For each query,we ran-domly sample a certain number of attributes from the attribute set in the query to construct the filters; (2) For numerical attributes, we randomly create different types of filters,including=,≤,and≥, while for categorical attributes, we only generate equality filters;(3) We then use these single filters to construct conjunctions, disjunc-tions, or a combination of both. Each of these three categories has roughly the same number of queries. Next, werandomly sample a certain number of attributes to form the SELECT clause.Finally, we ask graduate students to validate all queries and eliminate the unreasonable ones.

**Baselines.** We compare QUEST with various baselines.

(1) ZenDB [29] adopts a hierarchical semantic tree to extract tuples from documents and uses SQL-like queries for analysis.

(2) PZ (Palimpzest) [30] allows users to convert and analyze un-structured data with a declarative language hosted in Python. The existing PZ prototype offers basic optimizations on the usage of LLMs, while in-depth optimizations are still ongoing.

(3) Lotus [35] supports a bunch of LLM-powered operations to analyze documents. It features some basic optimizations to improve the accuracy and query latency.

(4) RAG [26]embeds attributes and their descriptions for similarity search. In contrast to QUEST, it does not incorporate a document-level index and does not utilize evidence to enhance retrieval.

(5) ClosedIE [23] uses a model that has been fine-tuned using a vast quantity of labeled (attribute, value) pairs to extract relevant information from a given context in response to a query.

(6) Eva (Evaporate)[3] is an LLM-based data extraction method. Rather than routinely employing LLMs to extract values from each document, it instead uses LLMs to automatically synthesize code. (7) QUEST is our full-fledged solution.

**Evaluation** **Metrics.** We measure accuracy, cost, and latency with respect to all queries. For accuracy, we evaluate the average preci-sion, recall, and F1-score across all queries. Given a query $Q$ , the set of tuples returned by a method is denoted as $T(Q)$ , and the ground truth is denoted as $GT(Q)$ . A tuple $t\in T(Q)$  is considered correctly extracted only if all its cell values match the correspond-ing ground truth values. Therefore, we have $P=\frac {|T(Q)\cap GT(Q)|}{|T(Q)|}$ $R=\frac {|T(Q)\cap GT(Q)|}{|GT(Q)|}\text {and}F1=\frac {2*P*R}{P+R}.$ .For LLM cost,we measure the

<!-- 9 -->

average number of input and output tokens per document for each query, including the cost of sampling, to reflect the full process-ing of QUEST. For latency, we measure the mean execution time of queries per document.

## 5.2 Comparison with Baselines

**Accuracy** w.r.t. **All** Queries. By the results (including P, R and $F1$ ) shown in Table 2, these method are ranked as follows: $\text {QUEST}\approx$ $Lotus>PZ>ZenDB>RAG>Eva>ClosedIE.$ 

QUEST and Lotus achieve the highest accuracy among all base-lines. Lotus performs well because it uses an LLM to scan every piece of text of all documents, leading to extremely high LLM costs. QUEST is competitive with Lotus but with a much lower cost, be-cause our two-level index and the evidence-augmented retrieval method accurately identify relevant segments for queries,feeding only these to LLMs. QUEST thus ensures quality with low LLM cost. On LCR dataset, QUEST achieves an F1-score of 0.7, much higher than that of Lotus (0.45). The reason is that the documents in LCR contain a large number of tokens, including much irrelevant infor-mation that misleads LLMs and causes hallucinations.

QUEST outperforms ZenDB because: (1) QUEST leverages the evi-dence to identify relevant segments, which is more accurate than ZenDB that simply uses the attribute description to find the most relevant sentence; (2) although ZenDB uses a semantic tree to locate each attribute, in practice, many documents, e.g., the documents in the LCR dataset, are not well-structured, making it hard for ZenDB to construct an effective tree. Therefore, the F1-score of ZenDB on LCR is only 0.52, much lower than that of QUEST (0.7). Similarly, QUEST outperforms PZ because its existing prototype lacks an effective text segment retrieval component.

<!-- ClosedIE Evaporate RAG Palimpzest ZenDB Lotus QUEST 1.0 WikiText 1.0 SWDE LCR 0.75 0.9 a00S 0.8 0.50 0.5 2Iou 0.7 2J0CS E $\mathfrak {S}_{c}^{\prime }$ 0.6 $\diamond$ 0.25 0.5 0.0 C1 C2 C3 0.4 C1 C2 C3 0.00 C1 C2 C3 -->
![](https://web-api.textin.com/ocr_image/external/f08458f8c7c1260f.jpg)

**Figure 4: F1-Score of Baselines (Different Query Groups)**

<!-- Lotus RAG Palimpzest ZenDB QUEST WikiText SWDE 10.0 LCR 3 1.0 (Ix)suasoL-# 7.5 2 (MIX)SeoL-4 0.5 (HIx)SuayoL 5.0 2.5 0 C1 C2 C3 C1 C2 C3 C1 C2 C3 -->
![](https://web-api.textin.com/ocr_image/external/603491c0a81d464c.jpg)

**Figure 5: Cost of Baselines (Different Query Groups)**

As expected, the RAG-based method is less effective than QUEST because the embedding of attribute and its descriptions is often not informative enough, thus tending to miss segments that are highly relevant to the query but do not possess similar phrases. Our evidence augmented retrieval strategy successfully solves this issue. Evaporate uses LLMs to generate code for data extraction, aiming to reduce LLMs costs. However, it does not perform well on accuracy because code essentially corresponds to a limited number of rules, which tend to be less effective when handling complex documents. ClosedIE performs poorly as pre-trained NLP models lack generalizability across domains.

**Overall** **Cost.** Table 3 shows the LLM cost of the baselines that have reasonable accuracy. We do not report thecost of ClosedIE and Eva. This is because the first one does not use LLM, while Eva just spends a few tokes on generating code. However,the accuracy of these two methods is ratherlow. The other methods are ranked as follows:QUEST &lt;ZenDB &lt;PZ &lt; RAG &lt;Lotus. QUEST is the most cost-effective because (1) it has a two-level index that can precisely locate a small number of segments where an attribute can be extracted, and (2)the filter reorder optimization minimizes the frequency of its LLM invocations by early terminating the evaluation of the filters whenever possible.

Lotus is the most expensive method because it feeds the entire document to LLMs for each filter. For example, on dataset LCR, Lotus costs 6x more tokens than QUEST. RAG is cheaper than Lotus because it feeds only a subset of segments to LLMs rather than the entire document. PZ and ZenDB save more cost than RAG because they reorder filters based on selectivities. However,both methods are more costly than QUEST. For example, on dataset WikiText, PZ and RAG consume more than 2x tokens than QUEST because they process every document in the same order, while QUEST generates the optimal order per document.

**Overall** **Latency.** Table 3 shows the query latency. ClosedIE and Eva are the fastest, although their accuracy in general is low. This is because ClosedIE does not use LLMs, while Eva only spends a few tokens on code generation. For other LLM-based methods, QUEST is about 2x faster than PZ, RAG, Lotus and ZenDB. This is because, in these methods, the LLM inferences dominate the query execution time, while the fine-grained filter ordering strategy of QUEST reduces both the number of LLM calls and the number of tokens consumed per call. Lotus is the slowest because it has to send each document to the LLM when evaluating a filter.

**Varying the** **Number** of **Filters.** We evaluate QUEST's performance with varying filter numbers, categorizing queries into: C1 with one filter, C2 with 2-3 filters, and C3 with 4 or more. We can observe in Figure 4 that as the number of filters grows, the accuracy of all baselines decreases because more filters tend to introduce more errors during attribute extraction. The cost of almost all baselines increases because more filters invoke more LLM calls. However, the increase of QUEST is the slowest, thanks to our filter ordering that reduces unnecessary attribute extraction.

## 5.3 Comparison of Filter Ordering Strategies

We evaluate the following baselines: (1) Random: The filters are ex-ecuted in random order; (2) Selectivity: The filters are ordered based on the selectivity; (3) Averagecost: The filters are ordered based on both the selectivity and the estimated average cost of ex-tracting each attribute from the sampled documents;(4)Exhaust: It exhaustively enumerates all possible orders and returns the optimal one per document.

In Figure 6, for queries in C1, the cost of all baselines is almost identical because there is only one filter and hence one order per query. For queries with more filters, these methods are ranked as follows by the LLM cost: QUEST ≈ Exhaust &lt;Averagecost

<!-- 10 -->


|  |  | ClosedIE | Eva | RAG | PZ | ZenDB | Lotus | QUEST |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Wiki | Precision | 0.33 | 0.39 | 0.79 | 0.75 | 0.81 | 0.93 | 0.93 |
| Wiki | Recall | 0.19 | 0.29 | 0.24 | 0.81 | 0.78 | 0.84 | 0.82 |
| Wiki | F1-score | 0.24 | 0.33 | 0.37 | 0.78 | 0.79 | 0.90 | 0.87 |
| SWDE | Precision | 0.72 | 0.85 | 0.88 | 0.90 | 0.82 | 0.95 | 0.94 |
| SWDE | Recall | 0.51 | 0.59 | 0.78 | 0.83 | 0.86 | 0.98 | 0.97 |
| SWDE | F1-score | 0.59 | 0.70 | 0.83 | 0.86 | 0.84 | 0.96 | 0.95 |
| LCR | Precision | 0.11 | 0.16 | 0.42 | 0.43 | 0.45 | 0.45 | 0.63 |
| LCR | Recall | 0.07 | 0.13 | 0.29 | 0.61 | 0.73 | 0.45 | 0.84 |
| LCR | F1-score | 0.09 | 0.14 | 0.34 | 0.50 | 0.55 | 0.45 | 0.72 |


**Table 2:Accuracy Comparison**


| Method | #-Token Cost | #-Token Cost | #-Token Cost | Latency(s) | Latency(s) | Latency(s) |
| --- | --- | --- | --- | --- | --- | --- |
| Method | Wiki | SWDE | LCR | Wiki | SWDE | LCR |
| Eva |  | - |  | 0.06 | 0.05 | 0.08 |
| ClosedIE | - | - | - | 0.76 | 0.65 | 1.83 |
| ZenDB | 260 | 280 | 2530 | 2.08 | 1.77 | 2.73 |
| PZ | 400 | 320 | 2610 | 2.17 | 2.16 | 2.85 |
| RAG | 440 | 340 | 3500 | 2.57 | 2.65 | 3.01 |
| Lotus | 2520 | 1150 | 12480 | 2.66 | 2.78 | 3.36 |
| QUEST | 170 | 190 | 2030 | 1.12 | 1.21 | 2.68 |


**Table 3: Cost and Latency Comparison**

<!-- Random Selectivity Averagecost Exhaust QUEST 400 WikiText 400 SWDE 300 300 ooL 200 200 100 ooT 100 0 C1 C2 C3 0 C1 C2 C3 Filter Groups Filter Groups LCR Time Comparison 4000 3000 103 SUeL 2000 0 1000 （第）amL $10^{1}$ 0 C1 C2 C3 4 5 6 8 9 Filter Groups Number of Filters -->
![](https://web-api.textin.com/ocr_image/external/796f677de5e25a51.jpg)

**Figure 6: Comparison of Filter Reordering Strategies**

Selectivi $ty<Ra$ ndom. This shows that QUEST produces optimal orders in most cases. As the number of filters increases, QUEST's performance improves due to increased optimization opportunities.

Furthermore, we evaluate the scalability of QUEST and Exhaust when handling queries with a relatively large number of filters. Figure 6 shows that as the number of filters increases, the run time of Exhaust explodes due to the exponential time complexity. Conversely, the run time of QUESTincreases slowly, indicating that it is more efficient and effective for complex queries.

## 5.4 Evaluation of Join

**Tables** **to** **be** **Joined.** We define 4 tables (i.e., Player,Team,City, Owner) in WikiText dataset.Player and Team join on the teamname attribute. Team and City join on the location attribute. Team and Owner join on the ownername attribute. We construct filters for each table using the method in Section 5.1.

**Two-table** **Join.** To demonstrate effectiveness, we compare QUEST with the typical optimization in relational databases, so-called Pushdown,which always pushes down the filters before performing

<!-- Pushdown QUEST E Optimal 400 400 SuoyoL 300 BIoL 300 #200 #200 100 G1 G2 G3 100 E1 Avg. -->
![](https://web-api.textin.com/ocr_image/external/61119869c7ea9014.jpg)

<!-- Pushdown QUEST Random Optimal 500 SuoMIoL 400 300 200 F1 F2 F3 -->
![](https://web-api.textin.com/ocr_image/external/65fcb57cf771fa7b.jpg)

**(a) Two-table Join**

**(b) Multi-table Join**

**Figure 7: Evaluation of Join**

the joins. We also compare QUEST with the Optimal plan, which is obtained by assuming the selectivity of each filter is known.

We create queries incorporating one of the three aforementioned joins, along with some random filters. In total, we construct 60queries. We classify these queries into three categories based on the number of filters, as previously stated. We execute the set of queries (G1-G3) and present the mean token consumption. In Figure 7-a, QUEST significantly reduces cost compared to Pushdown because it transforms a join to a filter operation and effectively orders the filters to minimize the frequency of LLM invocations. In this way, QUEST has the opportunity to run a join first if it incurs a small data extraction cost. In particular, QUEST only costs slightly more than Optimal due to its effective optimization strategies.

Next,we record the selectivity of each IN filter according to the plan chosen by QUEST for each query.We then classify the queries into three new categories $\left(E_{1}-E_{3}\right)$ based on the selectivities. The first group, $E_{1}$ ,corresponds to the selectivities ranging from 0-0.3, while $E_{2}$  and $E_{3}$  correspond to 0.3 -0.6 and 0.6-1,respectively. Moreover, we present the average cost associated with al1 queries. Figure 7-a illustrates that when the selectivity of the IN filter is low, it tends to be executed first, leading to lower cost than the traditional predicate pushdown strategy.Conversely, as the selectivity rises, the IN filter might fall back to the traditional predicate pushdown strategy, thus always finding a plan with the lowest cost.

**Multi-table** **Join.** Next, we evaluate QUEST on queries with multiple joins.Similarly, we create three groups of queries by the number of filters(F1-F3),and each group has 10 queries. The queries in each group apply the same filter operations, while queries in different groups apply different joins. To evaluate the effectiveness of QUEST, we compare it with (1) Random: each time we randomly select two tables to join using the above technique; (2) Pushdown: we push down all filters first and then run the joins and (3) Optimal: we assume that the selectivity of each filter is known and enumerate all possible join orders to obtain the optimal one.

<!-- 11 -->

<!-- Segment-level Index Two-level Index 1.00 0.95 1000 SsauaTaoE 0.90 800 0.85 0.80 600 0.75 CHIx)saoyoL-# 400 0.70 Precision Recall F1 Score Cost -->
![](https://web-api.textin.com/ocr_image/external/0b14ad23512abb8b.jpg)

(a) Ablation Study of Two-Level Index

<!-- No-evidence LLM-evidence QUEST 1.0 0.9 0.8 2oo1 0.7 0.6 0.5 0.4 0.3 WikiText SWDE LCR (b) Ablation Study of Evidence -->
![](https://web-api.textin.com/ocr_image/external/6c490108a9058d29.jpg)

<!-- 0.88 0.86 2oo-1 0.84 1.82 0.80 r=0.3 T=0.35 T=0.4 T=0.45 T=0.5 -->
![](https://web-api.textin.com/ocr_image/external/8f313a721da64c8a.jpg)

(c) Ablation Study of Threshold

<!-- Precession Recall F1 Score 1.0 0.9 10 $\mathbf {s}^{*}$ 0.7 0.6 0.5 905 0.15 0.20 0.25 Ratio -->
![](https://web-api.textin.com/ocr_image/external/184556f815476b5d.jpg)

**(d) Ablation** **Study of Sample Ratio**

<!-- 500 400 MtoMoL 300 200 100 0.01 0.03 0.05 0.10 0.15 0.20 0.25 Ratio -->
![](https://web-api.textin.com/ocr_image/external/13578e34fe8c6a76.jpg)

<!-- Precession Recall F1 Score 1.0 0.9 9 0.8 。 0.7 0.6 0.5 K -->
![](https://web-api.textin.com/ocr_image/external/b465228d6186c9c7.jpg)

<!-- 250 200 uoXoL# 150 100 50 0 2 4K 5 -->
![](https://web-api.textin.com/ocr_image/external/e80fef32a6725861.jpg)

(e) **Ablation Study of Cluster K**

**Figure 8: Ablation Studies**

In Figure 7-b, the system outperforms Random and Pushdown, comparable to the optimal plan in LLM cost. It outperforms Random because during query execution, QUEST dynamically selects the join operation that leads to the lowest cost. QUEST outperforms Pushdown since in unstructured document analysis, pushing down filters first does not always improve the efficiency of join queries.

## 5.5 Ablation Studies

**Ablation Study of Two-Level Index.** To demonstrate the effec-tiveness of our index, we conduct ablation studies on WikiText, comparing with the baseline that only uses the segment-level index. Here, we record the total cost incurred by each query across all documents and calculate the average over the queries. In Figure 8-a, the two-level index achieves a higher F1-score and a lower cost compared to the baseline because the segment-level index selects irrelevant documents, decreasing precision and increasing costs due to unnecessary document processing.

**Ablation** **Study** **of** **Evidence.** We evaluate QUEST against two base-lines: No-evidence, relying solely on the attribute and description, and LLM-evidence, using LLM-generated synthetic text to enhance the query. Figure 8-b shows QUEST surpasses both in accuracy by utilizing document-based evidence for enhanced structure and se-mantic reflection, leading to more precise retrieval.

**Ablation** **Study** **of** $τ$ .We evaluate the effectiveness of our strategy of setting the threshold τ automatically. Given a query about NBA players, our adaptive strategy sets $τ=0$ .4. Then, we vary t around 0.4. In Figure 8-c, if $1$  is large, the accuracy decreases because more irrelevant documents are retrieved. If $T$  is small, the accuracy also decreases because of mnissing many relevant documents.

**Ablation** **Study** **of** **Sample** **Rate.** We perform ablation studies on the WikiText dataset, adjusting the sampling rate near the de-fault 5%. Figure 8-d shows that accuracy initially rises with more samples but levels off quickly. Costs decrease first due to better selectivity estimation, then increase with excessive sampling due to LLM overhead. Overall, 5% efficiently balances quality and cost.

**Ablation** **Study** **ofCluster** K. We examine the Wiki Text dataset by varying the cluster count K near the default of 3. Figure 8-e demonstrates that while accuracy rises with additional clusters providing richer evidence, it soon levels off due to limited extra information. Precision remains stable, depending largely on ex-traction strategies. Costs rise with K as more clusters bring more evidence vectors and retrieved segments, increasing token usage.

# 6 RELATED WORK

**Language Models for Multi-Modal Data Analysis.** Many works focus on analyzing various types of data from diverse sources. Lotus [35] introduces several semantic operators to facilitate bulk semantic processing, including searching, extraction, and indexing, which can be used to build complex pipelines. However, it routinely utilizes LLMs to analyze the full text, incurring significant LLM costs. Some other works [8, 25,41,42] also apply LLMs or pre-trained language models to analyze unstructured documents. Like Lotus, they do not focus on optimizing the language model cost.

Palimpzest [30] analyzes unstructured data with a declarative lan-guage. Its optimizer produces an execution plan that uses LLMs to extract and analyze the data. However, its optimizations mainly fo-cus on choosing suitable LLMs for tasks, code synthesis, or prompt-ing strategies, which, although effective, are unrelated to classical query optimization principles such as filter ordering or join opti-mization. CAESURA [43] uses LLMs for natural language analysis over multi-modal data, decomposing queries into operators and invoking models like VisualQA (image-based) and TextQA (text-based) for question answering on different multi-modal tasks, with-out optimizing LLM costs. UQE [10] leverages LLMs for SQL-like analysis over multi-modal data, primarily enhancing aggregation queries with a sampling technique without considering filter order-ing or join optimization.

**Retrieval Augmented Generation.** RAG [6, 13,17,27,40] is a pop-ular method for tasks likequestion answering and is well-suited for attribute extraction, a key operation in QUEST, because it retrieves relevant segments using an index. However, Sec. 5.2 shows that the typical RAG's generic index-based retrieval is less effective than our customized two-level index and evidence augmented strategy. **Text-to-Table** **Extraction.** Some works focus on extracting struc-tured information from unstructured data. ZenDB [29] constructs a semantic hierarchical tree within each document to identify the sections that potentially contain a target attribute. Then, a single matching sentence, as well as several summaries within a section, are fed into an LLM for data extraction. It also uses several optimiza-tions,including filter ordering and predicate pushdown. However, ZenDB lacks fine-grained document-level query optimization and its index heavily relies on templated document structures. Unfortu-nately,in practice, abundant of documents lack a clear hierarchical structure. In particular, for documents with lengthy paragraphs, it is rather difficult to simply rely on several summaries and one sentence that matches the text of a query to identify the target attribute. EVAPORATE [3] uses LLMs to extract tables from HTML and PDF files through LLM-based code generation and adopts weak supervision to combine extraction functions. This aims to balance cost and quality. However, relying solely on LLM-generated code for complex documents is not highly accurate, as shown in Sec. 5.2.

<!-- 12 -->

Another line of work focuses on training models. Closed infor-mation extraction [21-23] uses language models to extract query-relevant information from context. Wu et al. [45] define text-to-table conversion as a sequence-to-sequence task, improving a pretrained model. Pietruszka et al. [37] uses a permutation-based decoder for text-to-table models,enhancing tasks such as entity extraction. Jiao et al. [24] finetune a pretrained model for instruction-following in text-to-table tasks. It extracts structured data, but lacks LLMs' accuracy and cross-domain generalization [3].

**LLMs** **for** **Data** **Preparation.** Data preparation is considered a data processing pipeline that converts raw data into an analyzable format, including tasks like data extraction, discovery,cleaning, integration and labeling. Recently,LLMs have shown great skill in data preparation. Several works finetune LLMs to enhance their abilities in conducting data preparation [28,47]. Other works utilize LLMs to address specific tasks, such as data extraction [3],schema matching [32,34], data cleaning (including data imputation [11,20], entity resolution [12], etc), and data labeling [5,46].

# 7 CONCLUSION & FUTURE WORK

We propose QUEST, a cost-effective LLM-powered system that fea-tures novel query optimizations tosupport unstructured document analysis. By introducing a two-level index, an evidence augmented retrieval strategy, and instance-optimized query execution, QUEST effectively reduces the LLM cost while maintaining high accuracy. Our comprehensive experiments showcase the efficacy of QUEST, achieving 30%-6x cost saving, while improving F1-score much.

A key future research direction is extending QUEST to support aggregation queries. Optimizations such as approximate query pro-cessing could estimate the aggregation results by analyzing only a subset of sampled documents. Moreover, we could judiciously cre-ate summaries for different possible attributes and directly produce aggregation results from the summaries. Exploring such strate-gies would further enhance QUEST's capabilityfor comprehensively analyzing unstructured documents.

## REFERENCES

[1] [n.d.]. https://anonymous.4open.science/r/QUEST/Fullversion.pdf

[2] 2019. https://solutionsreview.com/data-management/80-percent-of-your-data-will-be-unstructured-in-five-years/

[3] Simran Arora, Brandon Yang, Sabri Eyuboglu, Avanika Narayan, Andrew Hojel, Immanuel Trummer, and Christopher Ré. 2023. Language Models Enable Simple Systems for Generating Structuured Views of Heterogeneous Data Lakes. Proc. VLDB Endow.17,2(Oct. 2023),92-105. https://doi.org/10.14778/3626292.3626294

[4] Dhananjay Ashok and ZacharyC. Lipton. 2023. PromptNER: Prompting For Named Entity Recognition. (May 2023).

[5] Parikshit Bansal and Amit Sharma. 2023. Large language models as annota-tors:Enhancing generalization of nlp models at minimal cost. arXiv preprint arXiv:2306.15766(2023).

[6] Deng Cai, Yan Wang, Lemao Liu, and Shuming Shi. 2022. Recent Advances in Retrieval-Augmented Text Generation. In Proceedings of the 45th International ACM SIGIR Conference on Research and Development in Information Retrieval. https://doi.org/10.1145/3477495.3532682

[7] Surajit Chaudhuri. 1998. An overview of query optimization in relational systems. In Proceedings of the seventeenth ACM SIGACT-SIGMOD-SIGART symposium on Principles of database systems. 34-43.

[8] Zui Chen, Zihui Gu, Lei Cao, Ju Fan, Sam Madden, and Nan Tang. [n.d.]. Sym-phony: Towards Natural Language Query Answering over Multi-modal Data Lakes.([n.d.]).

[9] Hanjun Dai, Bethany Yixin Wang, Xingchen Wan, Bo Dai, Sherry Yang,Azade Nova, Pengcheng Yin, Phitchaya Mangpo Phothilimthana, Charles Sutton, and Dale Schuurmans. 2024. UQE: A Query Engine for Unstructured Databases.In The Thirty-eighth Annual Conference on Neural Information Processing Systems. https://openreview.net/forum?id=t7SGOv5W5z

[10] Hanjun Dai, Bethany Yixin Wang,Xingchen Wan, Bo Dai, Sherry Yang, Azade Nova, Pengcheng Yin, Phitchaya Mangpo Phothilimthana, Charles Sutton, and Dale Schuurmans. 2024. UQE: A Query Engine for Unstructured Databases. In The Thirty-eighth Annual Conference on Neural Information Processing Systems. https://openreview.net/forum?id=t7SGOv5W5z

[11]Zhicheng Ding,Jiahao Tian,Zhenkai Wang, Jinman Zhao, and Siyang Li. 2024. Data imputation using large language model to accelerate recommendation system.arXiv preprint arXiv:2407.10078(2024).

[12] Meihao Fan, Xiaoyue Han,Ju Fan,Chengliang Chai, Nan Tang, Guoliang Li, and Xiaoyong Du. 2024. Cost-effective in-context learning for entity resolution: A design space exploration. In 2024 IEEE 40th International Conference on Data Engineering (ICDE). IEEE,3696-3709.

[13] Wenqi Fan, Yujuan Ding, Liangbo Ning, Shijie Wang,Hengyun Li,Dawei Yin, Tat-Seng Chua, and Qing Li. 2024. A survey on rag meeting llms: Towards retrieval-augmented large language models. In Proceedings of the 30th ACM SIGKDD Conference on Knowledge Discovery and Data Mining. 6491-6501.

[14] Filippo Galgani and Achim Hoffmann. 2010. LEXA: Towards Automatic Legal Citation Classification. In AI 2010: Advances in Artificial Intelligence (Lecture Notes in Computer Science), Jiuyong Li (Ed.), Vol. 6464. Springer Berlin Heidelberg, 445-454.

[15] Dawei Gao, Haibin Wang, Yaliang Li, Xiuyu Sun, Yichen Qian, Bolin Ding, and Jingren Zhou. [n.d.]. Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation. ([n.d.]).

[16] Yingqi Gao,Yifu Liu, Xiaoxia Li, Xiaorong Shi, Yin Zhu, Yiming Wang, Shiqi Li, Wei Li, Yuntao Hong, Zhiling Luo, et al. 2024. XiYan-SQL: A Multi-Generator Ensemble Framework for Text-to-SQL. arXiv preprint arXiv:2411.08599(2024).

[17] Yunfan Gao,Yun Xiong, Xinyu Gao, Kangxiang Jia, Jinliu Pan, Yuxi Bi, Yi Dai, Jiawei Sun, and Haofen Wang. 2023. Retrieval-augmented generation for large language models: A survey. arXiv preprint arXiv:2312.10997(2023).

[18] Tiezheng Ge, Kaiming He, Qifa Ke, and Jian Sun. 2013. Optimized product quantization. IEEE transactions on pattern analysis and machine intelligence 36,4(2013),744-755.

[19] Qiang Hao, Rui Cai,Yanwei Pang, and Lei Zhang. 2011. From one tree to a forest. In Proceedings of the 34th international ACM SIGIR conference on Research and development in Information Retrieval. https://doi.org/10.1145/2009916.2010020

[20] Ahatsham Hayat and Mohammad Rashedul Hasan. 2024. CLAIM Your Data: Enhancing Imputation Accuracy with Contextual Large Language Models. arXiv preprint arXiv:2405.17712(2024).

[21] Pengcheng He, Jianfeng Gao, and Weizhu Chen. 2021. Debertav3: Improving deberta using electra-style pre-training with gradient-disentangled embedding sharing.arXiv preprint arXiv:2111.09543(2021).

[22] Pengcheng He, Xiaodong Liu, Jianfeng Gao, and Weizhu Chen. 2020. DeBERTa: Decoding-enhanced BERT with Disentangled Attention. Cornell University-arXiv,Cornell University-arXiv(Jun 2020).

[23] Pengcheng He, Xiaodong Liu, Jianfeng Gao, and Weizhu Chen. 2021. DEBERTA: DECODING-ENHANCED BERT WITH DISENTANGLED ATTENTION. In Inter-national Conference on Learning Representations. https://openreview.net/forum? id=XPZIaotutsD

[24] Yizhu Jiao,Ming Zhong, Sha Li, Ruining Zhao,Siru Ouyang,Heng Ji,and Jiawei Han.2023. Instruct and extract: Instruction tuning for on-demand information extraction.arXivpreprint arXiv:2310.16040 (2023).

[25] Saehan Jo and Immanuel Trummer. 2024. ThalamusDB: Approximate Query Processing on Multi-Modal Data. Proceedings of the ACM on Management of Data 2,3(2024),1-26.

[26] Patrick Lewis, Ethan Perez, Aleksandra Piktus, Fabio Petroni, Vladimir Karpukhin, Naman Goyal, Heinrich Küttler, Mike Lewis, Wen-tau Yih, Tim Rocktäschel, Sebastian Riedel, and Douwe Kiela. 2020. Retrieval-augmented generation for knowledge-intensive NLP tasks. In Proceedings of the 34th Inter-national Conference on Neural Information Processing Systems (Vancouver, BC, Canada) (NIPS '20). Curran Associates Inc., Red Hook, NY, USA, Article 793,

<!-- 13 -->

16 pages.

[27] Huayang Li, Yixuan Su, Deng Cai, Yan Wang, and Lemao Liu. [n.d.]. A Survey on Retrieval-Augmented Text Generation. ([n.d.]).

[28] Peng Li, Yeye He,Dror Yashar, Weiwei Cui, Song Ge, Haidong Zhang, Danielle Rifinski Fainman, Dongmei Zhang, and Surajit Chaudhuri.2023.Table-gpt:Table-tuned gpt for diverse table tasks. arXiv preprint arXiv:2310.09263(2023).

[29] Yiming Lin, Madelon Hulsebos, Runiying Ma, Shreya Shankar, Sepanta Zeigham, Aditya G Parameswaran, and Eugene Wu. 2024. Towards Accurate and Ef-ficient Document Analytics with Large Language Models. arXiv preprint arXiv:2405.04674(2024).

[30] Chunwei Liu, Matthew Russo, Michael Cafarella, Lei Cao, Peter Baile Chen, Zui Chen, Michael Franklin, Tim Kraska, Samuel Madden, Rana Shahout,and Gerardo Vitagliano. [n.d.]. Palimpzest: Optimizing AI-Powered Analytics with Declarative Query Processing. In Proceedings of the Conference on Innovative Database Research (CIDR) (2025).

[31] Xinyu Liu, Shuyu Shen, Boyan Li, Peixian Ma, Runzhi Jiang, Yuxin Zhang,Ju Fan, Guoliang Li, Nan Tang, and Yuyu Luo. 2024. A Survey of NL2SQL with Large Language Models: Where are we, and where are we going? arXiv preprint arXiv:2408.05109(2024).

[32] Yurong Liu, Eduardo Pena, Aecio Santos, Eden Wu, and Juliana Freire. 2024. Magneto: Combining Small and Large Language Models for Schema Matching. arXiv:2412.08194 [cs.DB] https://arxiv.org/abs/2412.08194

[33] Yu A Malkov and Dmitry A Yashunin. 2018. Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs.IEEE transactions on pattern analysis and machine intelligence 42, 4 (2018), 824-836.

[34] Marcel Parciak, Brecht Vandevoort, Frank Neven, Liesbet M. Peeters, and Stijn Vansummeren. 2024. Schema Matching with Large Language Models: an Experi-mental Study. arXiv:2407.11852 [cs.DB] https://arxiv.org/abs/2407.11852

[35] Liana Patel, Siddharth Jha, Carlos Guestrin, and Matei Zaharia. 2024. LOTUS: En-abling Semantic Queries with LLMs Over Tables of Unstructured and Structured Data. arXiv preprint arXiv:2407.11418 (2024).

[36] PengLi and TianxiangSun ect all. 2023. CodeIE: Large Code Generation Models are Better Few-Shot Information Extractors. (May 2023).

[37] Michal Pietruszka, Michal Turski, Lukasz Borchmann, Tomasz Dwojak, Gabriela Palka, Karolina Szyndler, Dawid Jurkiewicz, and Lukasz Garncarek. 2022. Sta-ble: Table generation framework for encoder-decoder models. arXiv preprint arXiv:2206.04045(2022).

[38] Bruno R Preiss. 1999. Data structures and algorithms. John Wiley & Sons, Inc.

[39] Oscar Sainz, Iker Garcia-Ferrero, Rodrigo Agerri, OierLopezde Lacalle, German Rigau, and Eneko Agirre. 2023. GoLLIE: Annotation Guidelines improve Zero-Shot Information-Extraction. (Oct 2023).

[40] Parth Sarthi, Salman Abdullah, Aditi Tuli, Shubh Khanna, Anna Goldie, and ChristopherD. Manning. 2024. RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval. (Jan 2024).

[41] James Thorne, Majid Yazdani, Marzieh Saeidi, Fabrizio Silvestri, Sebastian Riedel, and Alon Halevy. 2021. From natural language processing to neural databases. Proceedings of the VLDB Endowment (Feb 2021),1033-1039.https://doi.org/10. 14778/3447689.3447706

[42] Matthias Urban and Carsten Binnig. [n.d.]. Towards Multi-Modal DBMSs for Seamless Querying of Texts and Tables. ([n.d.]).

[43] Matthias Urban and CarstenBinnig. 2023. CAESURA: Language Models as Multi-Modal Query Planners. arXiv preprint arXiv:2308.03424 (2023).

[44] Liang Wang,Nan Yang,Xiaolong Huang, Jiao Binxing, Linjun Yang, Daxin Jiang, Rangan Majumder, and Furu Wei. 2022. Text Embeddings by Weakly-Supervised Contrastive Pre-training. Cornell University-arXiv,Cornell University-arXiv (Dec 2022).

[45] Xueqing Wu, Jiacheng Zhang, and Hang Li. 2022. Text-to-Table: A New Way of Information Extraction. In Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers). https://doi. org/10.18653/v1/2022.acl-long.180

[46] Ruixuan Xiao, Yiwen Dong, Junbo Zhao, Runze Wu, Minmin Lin, Gang Chen, and Haobo Wang. 2023. FreeAL: Towards Human-Free Active Learning in the Era of Large Language Models. In Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing. 14520-14535.

[47] Haochen Zhang, Yuyang Dong, Chuan Xiao, and Masafumi Oyamada. 2024. Jellyfish: Instruction-Tuning Local Large Language Models for Data Preprocess-ing. In Proceedings of the 2024 Conference on Empirical Methods in Natural Lan-guage Processing,Yaser Al-Onaizan, Mohit Bansal, and Yun-Nung Chen(Eds.). Association for Computational Linguistics, Miami, Florida, USA, 8754-8782. https://doi.org/10.18653/v1/2024.emnlp-main.497

<!-- 14 -->


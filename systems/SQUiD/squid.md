# SQUiD: Synthesizing Relational Databases from Unstructured Text

Mushtari SadiaZhenning YangYunming XiaoAng ChenAmrita Roy Chowdhury University of Michigan {mushtari，znyang，yunmingx，chenang，aroyc}@umich.edu

# Abstract

Relational databases are central to modern data management, yet most data exists in unstructured forms like text documents. To bridge this gap,we leverage large language models (LLMs) to automatically synthesize a relational database by generating its schema and populating its tables from raw text. We introduce SQUiD,a novel neurosymbolic framework that decomposes this task into four stages,each with specialized techniques. Our experiments show that SQUiD consistently outperforms baselines across diverse datasets.

# 1Introduction

Relational databases serve as the foundation for data management, supported by decades of mature infrastructure development and a wide array ofsophisticated analytical tools.However, much of today's data exists as raw, unstructured text - such as academic articles,medical records,and business reports (Harbert, n.d.). This unstructured data cannot be directly analyzed using conventional database tools,which rely on structured, relational inputs.Bridging this gap remains a long-standing goal of the data management community (Mansuri and Sarawagi, 2006; Smith et al., 2022a; Chu et al., 2007; Yafooz et al., 2013; Michelson and Knoblock, 2008; Murthy et al., 2012; Jain et al., 2007), with a key challenge being the conversion of unstructured text into queryable, structured formats compatible with existing relational database infrastructure.

Large language models (LLMs） presents a unique opportunity to automate this conversion, owing to their growing capability to understand natural language and perform complex information extraction tasks. Prior work in this space can be broadly categorized into two areas. The first focuses on generating summarizing structures from text, such as tables (Deng et al., 2024; Wu et al., 2022; Sundar et al., 2024; Li et al., 2023; Arora et al., 2O23) and mind maps (Jain et al., 2024)—but these non-relational representations are often tailored for specific downstream applications (Shavarani and Sarkar, 2025; Sui et al., 2024), and lack the expressiveness and semantics of relational databases. The second category manipulates a pre-defined and fully populated relational database-e.g., Text-to-SQL (Hong et al., 2024) approaches generate executable SQL queries from text over given schemas, while a recent work can update existing relational databases using text input (Jiao et al., 2024). However, a key challenge of managing unstructured text is precisely that such a pre-defined database often does not exist.

![](images/8f696302a78f676738d4e2a99343ca9351cef0af27a22626940e9221ebd399a9.jpg)  
Figure 1: Challenges of synthesizing relational DB from text

In this paper, we pursue a more ambitious goal - synthesizing a relational database from unstructured text from scratch-a task that we call Text2R. The Text2R task presents several unique challenges. First, a relational schema consists of multiple interrelated tables that capture complex entityrelationship semantics,and it must also preserve syntactic integrity, such as satisfying primary/foreign key constraints. Second, database records must be correctly identified and populated across tables. This involves ensuring value consistency - e.g.,the same entity must be consistently represented in all relevant tables.Third, the actual database creation requires valid and executable SQL statements,adding another layer of complexity. Naive approaches, such as directly prompting LLMs to synthesize databases,leads to diverse errors, including missing or hallucinated values, and SQL syntax issues (Fig. 1).

![](images/cef5bc8ac1489e5163231c1ac42b4257b70f40510217d7d5e2d7e60a2240ccdb.jpg)  
Figure 2:OverviewofSQUiD.(1)Schema Generationconstructsarelational schema thatdefinesthe tables,columns,and their relationships,fromtheentitiesin thetext.(2)ValueIdentification extracts relevantvalues (.g.,names,dates)fromthetext. These values are then organized during (3)Table Population by aligning them with the generated schema to form tuples. (4) Database Materialization programmaticall translates theoutput into SQLstatements,producingthe final relationaldatabase.

To address these challenges， we propose SQUiDl,a neurosymbolic framework for the Text2R task. Our key idea is to decompose the task into multiple modular stages in a principled manner—breaking the problem into manageable sub-tasks. This allows each stage to leverage specialized techniques,such as symbolic information extraction and LLM-assisted tool use, for improved performance. Via task breakdown, some stages can also be executed programmatically, enhancing both accuracy and consistency. Additionally, each stage incorporates best practices from relational database literature to guide prompt design.

SQUiD consists of four stages,which generalize across text from diverse domains. The schema generation stage uses LLMs to infer a relational schema from the input text, guided by carefully designed prompts that incorporate best practices to identify entities and relationships. In the value identification stage, intermediate representations in the form of triplets are extracted using both symbolic tools and LLMs. These triplets break down complex sentences into granular units,improving coverage of the extracted values. Next, the table population stage aligns these triplets with the generated schema to form schema-consistent tuples. Finally, instead of generating SQL directly via LLMs—which can be token-intensive—our database materialization stage programmatically translates the structured outputs into valid SQL statements,ensuring syntactic correctness and structural fidelity. The resulting SQL is then executed to instantiate the final database.We make the following contributions:

· We define a new task - synthesizing relational databases from unstructured text, or Text2R.This marks a clear departure from prior work, which

focuses on downstream relational tasks (e.g., Text2SQL), assuming a pre-existing database. ·We propose SQUiD,a novel neurosymbolic framework for Text2R, based on a four-stage decomposition. Each stage leverages custom techniques tailored to its specific subtask. We establish an automated benchmark methodology for Text2R.We also define a suite of evaluation metrics to assess schema and tuple quality along both semantic and syntactic dimensions. · We conduct extensive experiments across diverse text domains and show that SQUiD consistently outperforms direct prompting baselines.

# 2The Text2R Task

We begin by defining this new task of relational database synthesis,or Text2R. Given an unstructured document $D$ of natural language text, the goal is to produce a set of SQL statements $S$ ：(1) CREATE TABLE statements which define the schema $\mathcal { R }$ ,specifying the structure of the database in terms of tables and columns; and (2) INSERT statements which populate the relations with data extracted from the text in $D$ . The schema $\mathcal { R }$ consists of a set of tables $\mathbf { T } = \{ T _ { 1 } , T _ { 2 } , \dots , T _ { n } \}$ where each $T _ { i }$ has a set of columns $\mathbf { C } _ { i } = \{ C _ { i , 1 } , C _ { i , 2 } , . . . , C _ { i , k _ { i } } \}$ Each table corresponds to an entity type, and the tables are inter-related, organizing the extracted tuples from the text into a database.A tuple $t$ for table $T _ { i }$ is represented as: $t = \langle v _ { 1 } , v _ { 2 } , \ldots , v _ { k _ { i } } \rangle$ where $v _ { j }$ is the value corresponding to column $C _ { i j } \in T _ { i }$ Each tuple represents a unique instance of the entity described by $T _ { i }$ . Fig 3 illustrates the differences between Text2R and other tasks.

# 3SQUiD Framework

SQUiD decomposes the Text2R task into four modular stages that mirror the typical database construction process.First, a relational database schema is designed by identifying the domain's entities and relationships-this is the schema generation stage.

![](images/1208e2366b3a710c483881b24f57fce7188bb371d7599972a9d167c722f2fecc.jpg)  
Figure 3:Closest related works—T3(Deng et al.,2024),STRUCTSUM(Jain et al.,2024),and EVAPORATE(Arora et al, 2023)—whenappliedtoour example dataset,either producedasingle table with incorrectcolumn-valueasignmentsormultiple disconectedrlevanttables.Inotrast,asoninig.,QUiDrectlyeneraesallfiveablesoespondingtte entities (Traveler,Trip,Accommodation,Transportationand Destination)along with their proper relationships.

Next, SQUiD extracts all the relevant values from the text (value identification), which are then used to construct tuples (table population). Finally, the generated schema and tuples are translated into valid SQL statements during the database materialization stage. We describe these stages below, using the following text shown in Fig. 2 as a running example: “Sophia booked a guided tour of Rome with BestCityTours, and opted for the premium package. She was visiting Rome on June 10th. James, aged 29, was also visiting Rome on June 10th."

# 3.1Schema Generation

Challenge. The complexity of schema generation is both semantic and syntactic. Semantically, the schema must accurately capture the entityrelationship structure that reflects the underlying data. Syntactically, a valid schema must comply with the integrity constraints defined by the established principles of relational databases. Simply prompting LLMs to generate a schema without explicitly articulating the necessary relational database constraints can result in structurally invalid outputs, as illustrated in Fig. 4.

![](images/f35537733dcc82fa164c36b7b88f371f10deb257ae8c018f660d00be16b6d4be.jpg)  
Figure 4: Examples of valid versus invalid relational schemas. PK: Primary key; FK: Foreign key.

Approach. The novelty of our approach is to encode a standardized set of rules that reflect the best practices in relational database literature, effectively guiding the model through a structured design process.These rules cover:(1） identifying relevant entities and relationships,(2) defining tables with appropriate columns,(3) assigning primary and foreign keys,and (4) avoiding reserved SQL keywords in naming tables/columns. We encode these rules into two types of prompt strategies:

direct, and chain-of-thought (CoT) prompting. CoT decomposes schema generation into intermediate reasoning steps (e.g., entity identification, then table and key definition; see Appendix G).

Decoupling schema generation from tuple formation has another advantage - it allows schema validity to be evaluated in isolation. This modularity is essential for enforcing syntactic constraints: each table must define a primary key (a column, or set of columns that uniquely identifies each row); and tables should include foreign keys (columns referencing primary keys in other tables). These constraints capture relationships between tables and enable JOIN operations.

# 3.2Value Identification

Challenge. This stage identifies and extracts values from the text that correspond to columns across all tables in the schema, presenting two challenges. First, multiple values often need to be extracted and deduplicated from the input to form a complete tuple (i.e., an entity instance). In our example,“Sophia booked a guided tour of Rome with BestCityTours, and opted for the premium package. She was visiting Rome on June 1Oth.",we must recover several values, such as traveler name ("Sophia"), tour location ("Rome"), tour operator ("BestCityTours"),and date ("June 1Oth"); redundant mentions (e.g. "Rome") need to be detected and deduplicated. Second, a document may describe multiple instances of the same type of entity, so we need to assign each value to the correct tuple. For instance,in the passage we also have: “James, aged 29, was also visiting Rome on June 1Oth." Hence, we need to track that Sophia and James are different tourists,and form distinct tuples.

Approach. Our neurosymbolic approach first augments direct LLM prompting with two information extraction (IE) methods to isolate values in a structured format, and then guides the LLM to accurately group these values by tuples.

Triplet Generation. This step introduces an intermediate representation using triplets,a format commonly used in information extraction. Specifically, we consider two triplet formats:

· Symbolic triplets，in the form (subject, relation,object)—e.g.,(Sophia,visiting, Rome),extracted symbolically using the Stanford CoreNLP toolkit (Manning et al., 2014). · Schema-aligned triplets, in the form (table column， value)—e.g.，(Tour， Location, Rome),generated using prompt-based LLM extraction for the target schema (see Appendix G).

For instance, the earlier passage describing Sophia might yield the following schema-aligned triplets:

<table><tr><td>Sophia</td><td>James</td></tr><tr><td>&lt;Traveler, Name,Sophia&gt;</td><td>&lt;Traveler, Name, James&gt;</td></tr><tr><td>&lt;Trip,Destination,Rome&gt;</td><td>&lt;Trip,Destination,Rome&gt;</td></tr><tr><td>&lt;Booking,Date,June 10th&gt;</td><td>&lt;Booking,Date,June 10th&gt;</td></tr></table>

We consider these two types of triplets because each captures complementary sets of values. Symbolic tools use deterministic methods to parse the text, and often extract values that LLMs may overlook (e.g. modifier words like premium).In contrast,LLM-generated schema-aligned triplets are more structurally consistent with the database schema, (e.g., Location Rome).

To ensure comprehensive coverage,we additionally leverage part-of-speech (POS) taggig to identify all nouns, pronouns,and numerical tokens in the text, since these POS categories typically encompass most values. We then perform string matching to verify whether the extracted triplets include all such tokens. If any are missing, the LLM is prompted to augment the existing triplets by incorporating the missing POS tokens.

Triplet Deduplication. Both triplet generation methods often introduce redundancy. To reduce this, we use the "sentence-t5-base" model (Ni et al., 2021) to generate embeddings of the triplets and apply cosine similarity to identify near-duplicates. If a set of triplets has a pairwise cosine similarity above a tunable threshold $( 9 7 \% )$ , we retain only one representative triplet.

Triplet Grouping. To ensure that triplets are correctly grouped by entity instance,we apply two heuristics. First,we assume that the first table in the schema typically corresponds to the central entity (e.g., the tourist in a tourism booking system). Second, we leverage the structure of the input document, where each paragraph often describes a distinct instance of this central entity. Accordingly,we associate each paragraph with a unique identifier, which serves as the primary key for the first table. In particular, SQUiD uses an LLM to detect the number of distinct entity instances in the document and assign a unique identifier to each paragraph. Once assigned, each triplet is prefixed with its corresponding identifier. For example:

<table><tr><td>Sophia</td><td>James</td></tr><tr><td>&lt;1,Traveler, Name,Sophia&gt;</td><td>&lt;2, Traveler,Name,James&gt;</td></tr><tr><td>&lt;1,Trip,Destination, Rome&gt;</td><td>&lt;2,Trip,Destination, Rome&gt;</td></tr><tr><td>&lt;l,Booking,Date,June 10th&gt;</td><td>&lt;2,Booking,Date,June 10th&gt;</td></tr></table>

This structure ensures that all extracted values are correctly grouped by the entity instance they describe,and that the same identifier can be used to link rows across tables during the population stage.

# 3.3Table Population

Challenge. This stage constructs tuples for each table using the values identified in the previous stage, presenting two challenges.First, each value must be correctly aligned with its corresponding table column, meaning the LLM must output tuples in a schema-aligned format. However, extracting structured information in a single generation often results in malformed outputs-especially when the target format (e.g., JSON) is complex. Second, we must maintain referential integrity: references to the same entity instance must remain consistent across related tables.For example,a tuple in the Trip table may refer to a destination (e.g., Rome) and a traveler (e.g., Sophia), who also appears in the Traveler table.Here, the traveler ID used in the Trip table must match the primary key of the corresponding tuple in the Traveler table (Fig. 4). Approach. Before delving into the details, we remind readers that SQUiD has three possible inputs for table population: (1) text alone,(2) text with symbolic triplets,and (3) text with schema-aligned triplets. Including all three in a single prompt increases context length and can degrade output quality. Instead, each source is used independently as input to the prompt, and the resulting tuples are later combined. This is akin to ensemble learning in ML (Polikar, 2012), allowing us to leverage the complementary strengths of each input.

We now describe the process of table population. To address the value-alignment challenge, we use a structured format that is incrementally generatable by the LLM. Instead of emitting the entire structure at once, the format supports iterative generation, which reduces formatting errors. We ensure referential integrity by incorporating carefully chosen guidelines in the prompt that is compatible with the above format. In particular, we leverage tool use in LLMs (Qu et al., 2025) by introducing a

# lightweight tool extract that outputs one structured record at a time according to a given schema. This approach helps the LLM remain consistent with the expected output format.

After generating the records, we parse the output to extract each column-value pair for every tuple.

# 3.4Database Materialization

Challenge.A naive approach is to prompt LLMs with all prior schema and value information to generate the corresponding SQL INSERT statements directly. However, this method is both inefficient and error-prone. We observe that this is akin to a “program synthesis” task—it not only requires the production of a large number of redundant tokens, which can be costly; but is also britte to slight mistakes (e.g.,a slightly-malformed SQL statement will produce execution errors).

statistics. We categorize the text difficulty as easy (e.g., Tourism, Finance),medium (e.g., Education, California Schools), or hard (e.g., Mental Health, Superheroes), based on domain complexity, record sparsity, and LLM-induced verbosity.   

<table><tr><td>Schema</td><td>- traveler: &quot;id: int [PK]&quot;, &quot;name: string&quot;,&quot;age: int&quot; - trip:&quot;id: int[PK]&quot;,&quot;traveler_id: int[FK→traveler(id)&quot;,&quot;destination:string&quot;,</td></tr><tr><td>extract output</td><td>extract traveler: &quot;id&quot;:1; &quot;name&quot;: &quot;Sophia&quot;; &quot;age&quot;: 34; extract trip: &quot;id&quot;:1; &quot;traveler_id&quot;:1; &quot;destination&quot;: &quot;Rome&quot;</td></tr></table>

Approach. Instead, we observe that the required SQL statements are well-defined—creating specific tables and then inserting the corresponding tuples to these tables. Therefore,we decouple the materialization step from the LLM by parsing the model's output from the previous stage to programmatically construct executable SQL code. Specifically, we generate CREATE TABLE and INSERT INTO statements (as shown in Fig.2) which are executed on a local SQLite instance to instantiate the database. This separation enables deterministic parsing,ensuring syntactically correct SQL statements.

<table><tr><td rowspan="2">Domain</td><td colspan="3">Kaggle (24 tables/domain)</td><td colspan="6">BIRD (24 tables/domain)</td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td>Tourism Education Finance Calif. Schools Superhero Books Comp. Student Mental Health Authors</td><td></td><td></td></tr><tr><td>Cols/Table</td><td>12</td><td>8</td><td>10</td><td>26</td><td>9</td><td>7</td><td>6</td><td>2</td><td>5</td></tr><tr><td>Vals/Table</td><td>60</td><td>40</td><td>50</td><td>130</td><td>45</td><td>35</td><td>30</td><td>10</td><td>25</td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>Overall Total Values10,200</td><td></td></tr></table>

Table 1: Dataset statistics

Models.We test five state-of-the-art models: GPT-4O (OpenAI, 2024), DEEPSEEK-V2.5 (DeepSeek AI, 2024), CLAUDE 3.7 SONNET(Anthropic, 2024), LLAMA-3-8B-INSTRUCT (Meta AI, 2024), and QwEN3-8B (Alibaba, 2024).

Metrics.We propose a suite of novel metrics for a principled evaluation of the Text2R task, which are summarized in Table 2.

Schema Evaluation. We evaluate the quality of generated database schemas along three dimensions: entity coverage, primary key coverage, and foreign key coverage. Entity coverage assesses whether each column from the ground truth is represented in the generated schema.A column is considered covered if there exists a semantically equivalent column (based on cosine similarity between column names) in the output. Primary key coverage checks whether each generated table defines at least one primary key, while foreign key coverage evaluates whether all foreign keys correctly reference primary keys in valid, related tables within the schema. The last two metrics assess syntactic constraints that are essential for the correctness of relational database schemas.

# 4Evaluation Setup

Dataset.The Text2R task requires a text document paired with a ground-truth relational database—however, no existing benchmarks directly support this. To fill this gap,we introduce an automated dataset creation pipeline: starting from relational databases or CSV files (using column names and tuple values as ground truth), we prompt an LLM to generate textual descriptions of the tuples,which serve as the input for Text2R. Using this approach, we construct two datasets: (1) BIRD Dataset—covering six domains from the BIRD Text2SQL benchmark (Li et al., 2024); and (2) Kaggle Dataset—containing CSV files from three domains (tourism, education, finance) (Kiattisak,2023; Becker and Kohavi, 1996; Rai, 2023), which reflect more user-centric,realistic data often missing in BIRD.Table1 summarizes the dataset

Tuple Evaluation. Relational databases store data across multiple tables；therefore,evaluating the quality of such databases requires a holistic view that goes beyond individual tables or isolated values. To enable a principled evaluation, we flatten the schema into a single table—commonly referred to as a denormalized table (Elmasri and Navathe, 2016)—by performing a JOIN across all tables. In our databases, each table maintains a many-to-one or one-to-one relationship with a central table, enabling this complete JOIN of the entire schema. This consolidated table captures complete entityrelationship instances in a unified format. We generate two denormalized tables: one from the ground-truth database and one from the database produced by SQUiD. The two are then compared to assess the accuracy of the generated database.

We propose five novel metrics to evaluate the quality of the generated tuples along two dimensions: syntactic and semantic validity. Syntactic validity assesses whether the generated databases adhere to correct structural and relational rules. It is measured using:(1) Database Construction Success Rate, which measures the percentage of generated SQL statements that successfully materialize into databases with at least one non-null tuple, (2) Referential Integrity Rate (RRIR), which measures the fraction of foreign-key joins that yielded valid (non-null) tuples.

<table><tr><td></td><td>Evaluation Metrics</td><td>Definition</td><td>Formula</td></tr><tr><td rowspan="3"></td><td>Entity Coverage Score (ECS)</td><td>Avg. max cosine similarity betn. GT&amp; DB columns</td><td>∑1maxje[，Mcos_sim(iG）</td></tr><tr><td>Schema Primary Key Coverage (PKC)</td><td>% of tables with a defined primary key</td><td>#Tables with PK/#Tables</td></tr><tr><td>Foreign Key Coverage (FKC)</td><td>%oftables whose foreign keys refer valid primary keys#Tables with valid FK/#Tables</td><td></td></tr><tr><td rowspan="5">Tuple</td><td>Database Construction Success Rate (DBR) % of successfully generated databases</td><td></td><td>#Generated DB/#Text Documents</td></tr><tr><td>Tuple Coverage (TC)</td><td>% of GT tuples present in DB</td><td>|RgTNRDBl/RGT</td></tr><tr><td>Value Coverage (VC)</td><td>%of GT values present in DB</td><td>|VGTnVDBl/VGT|</td></tr><tr><td>Column Consistency (CC)</td><td>% of GT values present in DB in correct columns</td><td>|VeTnVDBl/vorl,where VGr,VDB ∈col</td></tr><tr><td>Ref.Integrity % (RIR)</td><td></td><td>Avg.tuplecompleesrFllt=∑</td></tr></table>

Table 2: Novel evaluation metrics for Text2R: GT denotes ground truth and DB denotes the generated databases

Semantic validity evaluates the comprehensiveness and correctness of the values populated. It is measured using:（1） Tuple Coverage,which measures the fraction of the ground truth tuples recovered; (2) Value Coverage, which measures the fraction of ground truth values populated; and (3) Column Consistency,which checks whether each value appears in its correct column.

Baseline.Our Text2R task is novel,and prior work targets fundamentally different objectives (see Sec.2),making direct comparison infeasible. To address this, we design a tailored baseline: using zero-shot prompting,we generate CREATE TABLE and INSERT INTO SQL statements directly from the input text, then execute them in SQLite to instantiate the database. Prompt details are in Appendix G.

# 5Experiments and Analysis

We evaluate the performance of SQUiD based on the following three research questions (RQs):

· RQ1. Can SQUiD generate a high-quality relational schema?   
· RQ2. Can SQUiD generate accurate relational tuples to populate the tables?   
· RQ3. How do SQUiD's design choices affect performance?

# 5.1 RQ1: Schema Evaluation

As described in Sec.3.1, we evaluate two prompting strategies for schema generation: Direct and Chain-of-Thought (CoT). Table 3 summarizes the results.We only consider schemas that match the format specified in the prompt, as this is required for SQUiD to process them later. We evaluate both syntactic validity—using primary key coverage (PKC) and foreign key coverage (FKC)—and semantic validity, using entity coverage (ECS). We first highlight general observations across all three metrics,followed by specific analysis. Overall, CoT consistently outperforms Direct across difficulty levels；except CLAUDE,which performs better with Direct but struggles with CoT due to format violations, likely due to overthinking (Liu et al.,2024b). QwEN-8B consistently fails to produce valid schemas, likely due to poor support for structured output tasks (Liu et al., 2024c).

Syntactic Validity. We observe that most CoTbased generations achieve full PKC and FKC, except GPT,which drops to $6 6 . 6 7 \%$ FKC in the medium dataset. This is because GPT occasionally generates a single table with no foreign key,when the text contains only a few entities.

Semantic Validity. For entity coverage ECS, DEEPSEEK with CoT performs the best, followed by LLAMA-8B and GPT-which show minor drops due to their tendency to generate paraphrased column names (e.g.,“heritage” or “ethnicity” instead of "race"), whereas DEEPSEEK aligns more closely with the ground truth. In terms of performance across domains (Appendix D), DEEPSEEK achieves the highest entity coverage in the Education domain $( 9 1 . 0 8 \% )$ and the lowest in the Mental Health domain $( 3 8 . 9 7 \% )$ . The ground truth of the latter has complex column names, such as“questiontext" and “answertext", suggesting that domain complexity significantly affects the quality of the generated schema.

# 5.2RQ2: Tuple Evaluation

Syntactic Validity. Table 4 reports the Database Construction Success Rate (DBR) and the improvement in Referential Integrity Rate (RRIR) over the baseline. We highlight three observations. First, SQUiD achieves perfect DBR $( 1 0 0 \% )$ across all models and difficulty levels,except for using DEEPSEEK on hard examples, where it drops slightly to $98 \%$ ．This indicates the robustness of SQUiD in consistently generating syntactically valid databases. In contrast, the baseline DBR varies widely-from as low as $9 . 7 \%$ （GPT） to $5 8 . 2 \%$ (CLAUDE) on average. Next, we turn to referential integrity. We note that SQUiD 's RRIR is a conservative (lower-bound) estimate, since records with missing values in the ground truth are treated as invalid under our metric.Nevertheless, SQUiD still achieves significant improvements over the baseline. For example,GPT exhibits the highest improvement ( $4 6 . 5 9 \times$ on easy examples). QWEN8B also achieve notable average improvements of $3 . 5 2 \times$ . Although LLAMA-8B achieves perfect DBR,its RRIR does not improve on the medium dataset, suggesting its baseline already exhibits relatively strong referential integrity.

<table><tr><td>Model</td><td>Prompt</td><td colspan="2">Easy</td><td colspan="2"></td><td colspan="2">Medium</td><td colspan="2">Hard</td><td colspan="2"></td><td colspan="2">Avg</td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>ECS(%)PKC(%）FKC(%)ECS(%) PKC(%)FKC(%) ECS(%)PKC(%)FKC(%)ECS(%)PKC(%）FKC(%)</td></tr><tr><td>CLAUDE3.7SONNET</td><td>Direct</td><td>86.2</td><td>100</td><td>100</td><td>80.7</td><td>100</td><td>100</td><td>45.3</td><td>100</td><td>100</td><td>70.7</td><td>100</td><td>100</td></tr><tr><td>LLAMA-8B INSTRUCT Direct</td><td>CoT</td><td>80.4 95.8</td><td>100 100</td><td>100 100</td><td>78.6 76.5</td><td>100 100</td><td>100 100</td><td>55.4 62.7</td><td>100 100</td><td>100 100</td><td>71.5 78.4</td><td>100 100</td><td>100 100</td></tr><tr><td>DEEPSEEKV2.5</td><td>Direct CoT</td><td>1 86.9</td><td>1 100</td><td>1 100</td><td>28.333.33 84.2</td><td>100</td><td>33.3 100</td><td>34.5 65.1</td><td>50 100</td><td>50 100</td><td>20.9 78.8</td><td>27.8 100</td><td>27.8 100</td></tr><tr><td>GPT-40</td><td>Diret</td><td>90.5</td><td>100</td><td>100</td><td>794</td><td>944</td><td>100</td><td>62.6</td><td>100</td><td>100</td><td>77.7</td><td>8</td><td>100</td></tr></table>

Table 3: Schema evaluation: Entity (ECS),PrimaryKey(PKC)andForeign Key (FKC)coveragescores.“-":schema generation failures that violate the requested structure in our prompts.CLAUDE-CoTand QwEN-8B are omited due to such failures.

<table><tr><td></td><td></td><td colspan="2">DBR(%)</td><td>RRIR SQUiD Baseline Improvement Factor</td></tr><tr><td rowspan="5">CLAUDE 3.7 SONNET</td><td>Easy</td><td>100.0</td><td>63.2</td><td>1.56×</td></tr><tr><td>Medium</td><td>100.0</td><td>63.4</td><td>1.10×</td></tr><tr><td>Hard</td><td>100.0</td><td>48.1</td><td>1.41×</td></tr><tr><td>Average</td><td>100.0</td><td>58.2</td><td>1.40×</td></tr><tr><td rowspan="5">DEEPSEEK</td><td>Easy</td><td>100.0</td><td>23.2</td><td>4.44×</td></tr><tr><td>Medium</td><td>100.0</td><td>42.4</td><td>1.70×</td></tr><tr><td>Hard</td><td>98.0</td><td>40.3</td><td>1.87×</td></tr><tr><td>Average</td><td>99.3</td><td>35.3</td><td>1.80×</td></tr><tr><td rowspan="4">GPT-40</td><td>Easy</td><td>100.0</td><td>2.0</td><td>46.59×</td></tr><tr><td>Medium</td><td>100.0</td><td>6.1</td><td>12.09×</td></tr><tr><td>Hard</td><td>100.0</td><td>21.0</td><td>2.63×</td></tr><tr><td>Average</td><td>100.0</td><td>9.7</td><td>13.93×</td></tr><tr><td rowspan="4">QWEN3 -8B</td><td>Easy</td><td>100.0</td><td>23.5</td><td>4.42×</td></tr><tr><td>Medium</td><td>100.0</td><td>32.2</td><td>2.52×</td></tr><tr><td>Hard</td><td>100.0</td><td>10.4</td><td>6.83×</td></tr><tr><td>Average</td><td>100.0</td><td>22.0</td><td>3.52×</td></tr><tr><td rowspan="4">LLAMA-3 8B-INSTRUCT Hard</td><td>Easy</td><td>100.0</td><td>63.2</td><td>1.54×</td></tr><tr><td>Medium</td><td>100.0</td><td>64.5</td><td>1.00×</td></tr><tr><td></td><td>100.0</td><td>40.1</td><td>1.87×</td></tr><tr><td>Average</td><td>100.0</td><td>55.9</td><td>1.64×</td></tr></table>

Table 4: Database Construction Success Rate $( \% )$ and the improvement factor in Referential Integrity Rate in SQUiD compared to the baseline.

and metrics. Notably,all 8B-parameter models (LLAMA-8B,QWEN-8B) under SQUiD significantly outperform all larger model baselines (GPT, CLAUDE,DEEPSEEK). In particular,although QWEN-8B's baseline lags behind those of CLAUDE and DEEPSEEK, its performance under SQUiD surpasses them—highlighting the effectiveness of our approach. Second, on average, all models using SQUiD achieve high TC $( \geq 0 . 9 5 )$ and strong VC/CC $( \geq 0 . 7 0 )$ ，with GPT showing the largest improvement over its baseline( $1 7 . 7 5 \times$ improvement on CC). This is primarily because failed database generations are assigned zero scores,and as shown in Table 4, GPT performs poorly in database construction under the baseline setting.Third, even for models with relatively strong baseline performance, such as LLAMA-8B, SQUiD improves VC and CC by $4 . 1 \times$ and $5 . 5 \times$ on hard examples, respectively.

Table 5:Tuple evaluation via Tuple Coverage (TC),Value Coverage (VC) and Column Consistency (CC). Best scores and improvement factors across models in bold. Gray indicates that SQUiD on all 8B models outperforms larger models.   

<table><tr><td rowspan="3"></td><td rowspan="3"></td><td colspan="3">SQUiD</td><td colspan="3">Baseline</td></tr><tr><td>TC(%)</td><td>VC(%)</td><td>CC(%)</td><td></td><td>TC(%)VC(%) CC(%)</td><td></td></tr><tr><td></td><td></td><td>98.0 (4.67x） 98.0 (4.67×)</td><td>39.0</td><td>21.0</td><td>21.0</td></tr><tr><td rowspan="4"></td><td>Med</td><td>100.0 (2.56×)</td><td></td><td>78.0 (6.00×) 74.0 (5.69×)</td><td>36.0</td><td>13.0</td><td>13.0</td></tr><tr><td></td><td>98.0 (2.72x) Hard 100.0 (2.44×)</td><td></td><td>63.0 (2.74×) 41.0 (3.73×)</td><td>41.0</td><td>23.0</td><td>11.0</td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td>Avg</td><td>99.0 (2.61x)</td><td>80.0 (4.21×)</td><td>71.0 (4.73×)</td><td>38.0</td><td>19.0</td><td>15.0</td></tr><tr><td rowspan="4"></td><td></td><td>100.0 (5.88×)</td><td>96.0 (6.86x)</td><td>96.0 (6.86x)</td><td>17.0</td><td>14.0</td><td>14.0</td></tr><tr><td>Med</td><td>99.0 (3.54×)</td><td>80.0 (5.33×)</td><td>77.0 (5.50x)</td><td>28.0</td><td>15.0</td><td>14.0</td></tr><tr><td>Hard</td><td>95.0 (2.64×)</td><td></td><td>59.0 (2.57×) 39.0 (3.90x)</td><td>36.0</td><td>23.0</td><td>10.0</td></tr><tr><td>Avg</td><td>98.0 (3.63×)</td><td></td><td>79.0 (4.65×） 71.0 (5.92×)</td><td>27.0</td><td>17.0</td><td>12.0</td></tr><tr><td rowspan="5">d</td><td></td><td></td><td></td><td>Easy 100.0 (50.00×） 97.0 (48.50×） 97.0 (48.50×)</td><td>2.0</td><td>2.0</td><td>2.0</td></tr><tr><td>Hard</td><td>97.0 (6.47x)</td><td></td><td>99.0 (16.50×） 81.0 (16.20×) 77.0 (19.25×)</td><td>6.0</td><td>5.0</td><td>4.0</td></tr><tr><td></td><td></td><td>61.0 (5.55×)</td><td>40.0 (6.67×)</td><td>15.0</td><td>11.0</td><td>6.0</td></tr><tr><td>Avg</td><td></td><td></td><td>99.0 (14.14×） 80.0 (13.33×) 71.0 (17.75×)</td><td>7.0</td><td>6.0</td><td>4.0</td></tr><tr><td>Easy</td><td>100.0 (1.82×)</td><td></td><td>95.0 (3.06x） 95.0 (3.17×)</td><td>55.0</td><td>31.0</td><td>30.0</td></tr><tr><td rowspan="4"></td><td>Med</td><td>99.0 (1.83x)</td><td></td><td>79.0 (2.82×) 75.0 (3.00×)</td><td>54.0</td><td>28.0</td><td>25.0</td></tr><tr><td></td><td>Hard 100.0 (3.45×)</td><td></td><td>70.0 (4.12×）44.0 (5.50×)</td><td>29.0</td><td>17.0</td><td>8.0</td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td>Avg</td><td>100.0 (2.17×)</td><td>81.0 (3.24×)</td><td>71.0 (3.38×)</td><td>46.0</td><td>25.0</td><td>21.0</td></tr><tr><td rowspan="5"></td><td></td><td>100.03.32</td><td></td><td>9.0(3.18)9.06.38)</td><td>22.0</td><td>190</td><td>180</td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td></td><td></td><td></td><td>Hard 99.0 (14.14×）51.0 (10.20×） 51.0(17.00×)</td><td>7.0</td><td>5.0</td><td>3.0</td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td>Avg</td><td>99.0 (4.95x)76.0 (4.75x) 75.0 (5.00x)</td><td></td><td></td><td>20.0</td><td>16.0</td><td>15.0</td></tr></table>

Semantic Validity. Table 5 reports Tuple Coverage (TC), Value Coverage (VC),and Column Consistency(CC) with three findings.First, SQUiD consistently outperforms the baseline across all models

<table><tr><td>Model</td><td>Diff.</td><td>(1)</td><td>(2)</td><td>(3)</td><td>(1)+(2)</td><td>T(%)S(%)L(%) T①S (%) TL (%) (1)+(3)</td><td>SQUiD (%) (1)+(2)+(3)</td></tr><tr><td></td><td>Easy</td><td>97.4</td><td>97.1</td><td>93.8</td><td>98.3</td><td>97.7</td><td>98.4</td></tr><tr><td></td><td>Med</td><td>68.2</td><td>74.6</td><td>74.1</td><td>77.3</td><td>77.5</td><td>78.2</td></tr><tr><td></td><td>Hard</td><td>51.7</td><td>58.4</td><td>51.3</td><td>60.7</td><td>60.5</td><td>63.1</td></tr><tr><td></td><td>Avg</td><td>72.4</td><td>76.7</td><td>73.1</td><td>78.8</td><td>78.6</td><td>79.9</td></tr><tr><td></td><td></td><td></td><td>94.5</td><td>92.7</td><td></td><td>95.4</td><td>96.4</td></tr><tr><td></td><td>Eaed</td><td>92.3</td><td></td><td></td><td>96.8</td><td></td><td></td></tr><tr><td></td><td>Hard</td><td>54.8</td><td>42.9</td><td>35.7</td><td>57.4</td><td>57.1</td><td>59.3</td></tr><tr><td></td><td>Avg</td><td>74.6</td><td>68.5</td><td>65.9</td><td>77.9</td><td>77.6</td><td>78.8</td></tr><tr><td></td><td>Easy</td><td>90.8</td><td>93.2</td><td>90.4</td><td>95.1</td><td>96.3</td><td>97.4</td></tr><tr><td></td><td>Med</td><td>75.3</td><td>69.7</td><td>68.6</td><td>80.4</td><td>81.2</td><td>81.3</td></tr><tr><td></td><td>Hard</td><td>50.6</td><td>41.8</td><td>51.7</td><td>56.3</td><td>59.4</td><td>61.6</td></tr><tr><td></td><td>Avg</td><td>72.2</td><td>68.2</td><td>70.2</td><td>77.3</td><td>79.0</td><td>80.1</td></tr><tr><td></td><td>ed</td><td>801</td><td>74.8</td><td>61.5</td><td>95.</td><td>944</td><td>95.4</td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td></td><td>Hard</td><td>60.6</td><td>37.9</td><td>40.4</td><td>64.3</td><td>68.5</td><td>70.7</td></tr><tr><td></td><td>Avg</td><td>73.3</td><td>55.1</td><td>54.4</td><td>78.3</td><td>79.7</td><td>81.9</td></tr><tr><td></td><td>sd</td><td></td><td></td><td>72.4</td><td></td><td></td><td>96.4</td></tr><tr><td></td><td></td><td>92.4</td><td>926</td><td></td><td>964</td><td>964</td><td></td></tr><tr><td></td><td>Hard</td><td>29.8</td><td>23.5</td><td>35.9</td><td>33.3</td><td>48.2</td><td>51.2</td></tr><tr><td></td><td>Avg</td><td>64.4</td><td>62.5</td><td>58.6</td><td>68.1</td><td>74.2</td><td>75.7</td></tr></table>

Table 6:Impact of different value source.The first three columns represent individual prompt settings,while the last three correspond to post-generation ensembling. $\mathbb { T } \oplus \mathbb { S }$ combines tuples generated from $\mathbb { T }$ and S while $\mathbb { T } \oplus \mathbb { L }$ combines $\mathbb { T }$ and L. SQUiD combines outputs from all three prompts.

# 5.3RQ3: Impact of SQUiD's Design Choices

We now evaluate the impact of SQUiD's design choices on value identification and table population. Recall that we consider three different prompts for table population based on their input source: (1） text only $( \mathbb { T } )$ ，(2） text with symbolic triplets $( \mathbb { S } )$ , and (3) text with schema-aligned triplets (L). SQUiD combines the rows generated from all three prompts. Table 6 evaluates how these different value sources affect the quality of the generated tuples,with the following observations.

First, using triplets significantly improves value coverage compared to extracting them from the text alone. This is evident from the observation that SQUiD outperforms $\mathbb { T }$ by $5- 1 2 \%$

Second, we examine how to best incorporate the triplets: whether to concatenate them with the input text in a single prompt, or to generate tuples separately and combine them post-hoc (ensembling). SQUiD adopts the latter strategy, and our results support this choice.Specifically, in the individual prompt setting, $\mathbb { T }$ outperforms both S and $\mathbb { L }$ in all but one case (CLAUDE).In contrast, the ensemble approaches (TS,TL and SQUiD) consistently outperform all the individual prompts. This suggests that including triplets directly in the input prompt increases context length, which degrades model performance—likely due to context window saturation (Liu et al., 2024a).

Finally, we evaluate our design choice of combining triples generated from symbolic tools and schema-aligned triplets from LLMs. Overall, TL outperforms $\mathbb { T } \oplus \mathbb { S }$ across most models on average, except for CLAUDE and DEEPSEEK.SQUiD consistently yields the best score,indicating that each source captures complementary information. LLM-generated triplets are schema-aware and can correctly group multi-word values under the correct columns (e.g.,mapping “car rental” to the transportation mode column, whereas symbolic tools only captured “car"). However, LLMs sometimes paraphrase values (e.g.,“low income” to“modest income"),whereas symbolic tools extract values verbatim, yielding closer alignment to the input.

# 6Related Work

Summarizing Structures. Text-to-table generation (Wu et al., 2022; Sundar et al., 2024; Li et al., 2023; Deng et al., 2024; Arora et al., 2023; Jain et al., 2024) projects explore sequence-to-sequence modeling,LLM prompt engineering,and structured summarization techniques. However, they can only generate flat tables, and cannot capture the relational database model in our work.

Manipulating Existing Databases. The goal of these projects is to leverage LLMs to interact with existing relational databases-such as to generate SQL queries from text (Hong et al., 2024; Pang et al., 2O2O), or to update them using natural language (Jiao et al., 2024). However, none of these works can synthesize a relational database from scratch, which is what SQUiD tackles.

Non-LLM Approaches. Prior to LLMs, integrating text into relational structures relied on traditional pipelines that combine information extraction, schema induction,and entity linking (Zhang et al.,2016; Smith et al., 2022b; Zhang et al., 2019). These methods rely on statistical or symbolic techniques,but required domain-specific heuristics and did not generalize to noisy or diverse input text.

# 7Conclusion

In this work,we have introduced a novel task of synthesizing relational databases from text, called Text2R.We have also developed a framework, SQUiD, designed to solve Text2R tasks. SQUiD has a neurosymbolic pipeline,with each stage incorporating specialized techniques for the task. Our experiments show SQUiD significantly outperforms baseline solutions across diverse datasets.

# Limitations

While we provide extensive evaluation of SQUiD on our benchmark, we leave comparisons with fewshot baselines and fine-tuned models for future work. Additionally, our current evaluation method is limited to user-centric text documents-that is,datasets where the generated database features a single central table to which all other tables relate, enabling a comprehensive SQL JOIN. This approach may not generalize to more complex schemas lacking such a central entity. Also, our evaluation relies primarily on public datasets, which may not fully capture the complexities of open-ended, real-world text; future work should extend evaluation to diverse, naturally occurring data sources.

# Ethics Statement

All datasets used in this work are publicly available and released under open licenses.The tools and models employed are authorized for research purposes and have been used in accordance with their intended terms.Detailed license information is provided in Appendix F.All experiments were performed strictly for research and evaluation.

Because our study requires user-centric documents for schema generation and value mapping evaluation, anonymization was not feasible without significantly compromising data integrity. To the best of the authors’knowledge, this research does not introduce any ethical risks beyond those already associated with the original datasets.

Since SQUiD uses large language models (LLMs) to synthesize databases,and LLMs are known to occasionally produce hallucinated or inaccurate content, there are potential risks when applying SQUiD in sensitive domains without human oversight. Careful review and verification are recommended before deploying the system in highstakes or privacy-critical applications.

Christopher Ré.2023. Language models enable simple systems for generating structured views of heterogeneous data lakes. Proc. VLDB Endow., 17(2):92- 105.   
Wen Bai, Shuo Liu,and Kai Zhang.2023． Schemadriven information extraction from heterogeneous tables. arXiv preprint arXiv:2306.12345.   
Barry Becker and Ronny Kohavi.1996. Adult. UCI MachineLearningRepository. DOI: https://doi.0rg/10.24432/C5XW20.   
Andrew Carlson and Charles Schafer.20o8. Bootstrapping information extraction from semi-structured web pages. In European Conference on Machine Learning and Principles and Practice of Knowledge Discovery in Databases (ECML PKDD).   
Chia-Hui Chang and Chun-Ying Wu.2016.Fastwrapper: Learning structure from web pages for data extraction. In Pacific-Asia Conference on Knowledge Discovery and Data Mining (PAKDD).   
Jiayi Chang,Yu Liu,and Fang Chen. 2024. Synthesizing text-to-sql data from weak and strong llms. InProceedings of the 2024 Annual Meeting of the Association for Computational Linguistics (ACL).   
Eric Chu,Akanksha Baid, Ting Chen,AnHai Doan, and Jeffrey Naughton. 2Oo7.A relational approach to incrementally extracting and querying structure in unstructured data. In Proceedings of the 33rd International Conference on Very Large Data Bases (VLDB), pages 1045-1056.   
DeepSeek AI. 2024. Deepseek-v2.5: A next-generation language model. Accessed: 2025-05-19. Licensed under the DeepSeek License.   
Xi Deng. 2010. Automatic web data extraction using tree matching and partial tree alignment. In Proceedings of IEEE International Conference on Data Engineering Workshops (ICDE Workshops).   
Xi Deng. 2011. Sede: Schema extraction from html data sources. In IEEE International Conference on Data Engineering (ICDE).   
Zheye Deng, Chunkit Chan, Weiqi Wang, Yuxi Sun, Wei Fan, Tianshi Zheng, Yauwai Yim, and Yangqiu Song. 2024. Text-tuple-table: Towards information integration in text-to-table generation via global tuple extraction.   
Ramez Elmasri and Shamkant B.Navathe. 2O16. Fundamentals of Database Systems,7 edition. Pearson.   
Tam Harbert. n.d. Tapping the power of unstructured data. https://mitsloan. mit.edu/ideas-made-to-matter/ tapping-power-unstructured-data.   
Zijin Hong, Zheng Yuan, Qinggang Zhang, Hao Chen, Junnan Dong,Feiran Huang,and Xiao Huang. 2024. Next-generation database interfaces: A survey of llmbased text-to-sql. arXiv preprint arXiv:2406.08426.

# References

Alibaba. 2024. Qwen3 language models. Accessed: 2025-05-19.Licensed under the Apache 2.0 License. Anthropic. 2024. Claude 3 model family. Accessed: 2025-05-19. Usage governed by Anthropic's terms of service. Simran Arora, Brandon Yang, Sabri Eyuboglu,Avanika Narayan,Andrew Hojel, Immanuel Trummer,and

Alpa Jain,AnHai Doan,and Luis Gravano. 2OO7. Sql queries over unstructured text databases. In 2007 IEEE23rd International Conference on Data Engineering (ICDE), pages 1255-1257.

Parag Jain,Andreea Marzoca, and Francesco Piccinno. 2024.STRUCTSUM generation for faster text comprehension. In Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers), pages 7876-7896, Bangkok, Thailand. Association for Computational Linguistics.

Yizhu Jiao,Sha Li, Sizhe Zhou,Heng Ji,and Jiawei Han. 2024. Text2DB: Integration-aware information extraction with large language model agents. In Findings of the Association for Computational Linguistics: ACL 2024, pages 185-205,Bangkok, Thailand. Association for Computational Linguistics.

Ratanakorn Kiatisak. 2023. Traveler trip data. Accessed: 2025-05-07.

Jinyang Li, Binyuan Hui, Ge Qu, Jiaxi Yang,Binhua Li, Bowen Li, Bailin Wang, Bowen Qin, Ruiying Geng, Nan Huo,et al.2O24. Can llm already serve as a database interface? a big bench for large-scale database grounded text-to-sqls.Advances in Neural Information Processing Systems,36.

Mingda Li,Yichong Chen，and Jiawei Han. 2023. Seq2seqset: Modular table generation via sequential header and set-based body construction.In Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing.

Nelson F. Liu, Kevin Lin, John Hewitt, Ashwin Paranjape,Michele Bevilacqua,Fabio Petroni,and Percy Liang. 2024a. Lost in the middle: How language modelsuse long contexts. Transactions of the Association for Computational Linguistics,12:157-173.

Ryan Liu, Jiayi Geng, Addison J. Wu, Ilia Sucholutsky, Tania Lombrozo,and Thomas L.Griffths.2024b. Mind your step (by step): Chain-of-thought can reduce performance on tasks where thinking makes humans worse.

Yu Liu, Duantengchuan Li, Kaili Wang, Zhuoran Xiong, Fobo Shi, Jian Wang,Bing Li,and Bo Hang.2024c. Are llms good at structured outputs?a benchmark for evaluating structured output capabilities in llms. Information Processing and Management, 61(5):103809.

Christopher Manning,Mihai Surdeanu, John Bauer, Jenny Finkel, Steven Bethard,and David McClosky. 2014. The stanford corenlp natural language processing toolkit. In Proceedings of 52nd Annual Meeting of the Association for Computational Linguistics: System Demonstrations,pages 55-60, Baltimore,Maryland. Association for Computational Linguistics.

I.R.Mansuri and S. Sarawagi. 2OO6. Integrating unstructured data into relational databases. In 22nd International Conference on Data Engineering (ICDE'06), pages 29-29.

Meta AI. 2024. Llama 3: Open foundation and instruction-tuned language models. Accessed: 2025- 05-19.Licensed under Meta's LLaMA 3 Community License.

Matthew Michelson and Craig A.Knoblock.2Oo8. Creating relational data from unstructured and ungrammatical data sources. Journal of Artificial Intelligence Research,31:543-590.

Karin Murthy, Prasad M. Deshpande,Atreyee Dey, Ramanujam Halasipuram, Mukesh Mohania, P. Deepak, Jennifer Reed, and Scott Schumacher.2O12. Exploiting evidence from unstructured data to enhance master data management. Proceedings of the VLDB Endowment, 5(12):1862-1873.

Jianmo Ni, Gustavo Hernandez Abrego, Noah Constant, Ji Ma, Keith B. Hall, Daniel Cer,and Yinfei Yang. 2021.Sentence-t5: Scalable sentence encoders from pre-trained text-to-text models.

Christina Niklaus,Matthias Cetto,André Freitas,and Siegfried Handschuh.2O18.A survey on open information extraction. arXiv preprint arXiv:1806.05599.

Madhav Nimishakavi and Partha Talukdar.2O16.Relation schema induction using tensor factorization with side information. In Proceedings of the 2016 Conference on Empirical Methods in Natural Language Processing (EMNLP).

OpenAI. 2024. Gpt-4o technical report. Accessed: 2025-05-19. Usage governed by OpenAI's terms of service.

Long Pang, Tao Zhang,and Ming Hu.202O. Rat-sql: Relation-aware schema encoding and linking for textto-sql parsers. In Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics (ACL).

Robi Polikar.2012.Ensemble learning. Ensemble Machine Learning: Methods and Applications, pages 1-34.

Changle Qu, Sunhao Dai, Xiaochi Wei, Hengyi Cai, Shuaiqiang Wang, Dawei Yin, Jun Xu, and Ji-rong Wen. 2025. Tool learning with large language models: A survey. Frontiers of Computer Science,19(8).

Harun Rai. 2023. Fintech customer life time value (ltv) dataset. Accessed: 2025-05-07.

Thomas Scholak, Siva Reddy Patra, and James Compositionality. 2O21. Picard: Parsing incrementally for constrained auto-regressive decoding. In Proceedings of the 2021 Conference on Empirical Methods in Natural Language Processing (EMNLP).

Hassan Shavarani and Anoop Sarkar. 2O25. Entity retrieval for answering entity-centric questions. In Proceedings of the 4th International Workshop on Knowledge-Augmented Methods for Natural Language Processing,pages 1-17,Albuquerque,New Mexico, USA. Association for Computational Linguistics.

Abraham Silberschatz,Henry F.Korth,and S.Sudarshan.2020. Database System Concepts,7 edition. McGraw-Hill Education.

Ce Zhang, Jan Hoffmann, Ce Wang, et al. 2016. Deepdive: Declarative knowledge base construction. Communications of the ACM, 60(5):93-102.

Fan Zhang, Alan Riter, et al. 2019. Openki: Integrating open information extraction and knowledge bases. In Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics (ACL).

Ellery Smith,Dimitris Papadopoulos,Martin Braschler, and Kurt Stockinger. 2O22a. Lillie: Information extraction and database integration using linguistics and learning-based algorithms. Information Systems, 105:101938.

Jack Smith, Evangelos Kanoulas,et al. 2O22b. Lillie: Language-independent linked information extraction. Data and Knowledge Engineering,137:101998.

Yuan Sui, Mengyu Zhou, Mingjie Zhou, Shi Han, and Dongmei Zhang. 2024. Table meets llm: Can large language models understand structured table data? a benchmark and empirical study. In Proceedings of the 17th ACM International Conference on Web Search and Data Mining,WSDM '24, pages 645- 654, New York, NY, USA. Association for Computing Machinery.

Srivatsan Sundar, Dhruv Jain, Yuwei Zhang,and H. V. Jagadish. 2024. gtbls: Generating tables from text by learning table structures.In Proceedings of the 2024 Conference of the Association for Computational Linguistics.

Xueqing Wu, Jiacheng Zhang,and Hang Li.2O22. Textto-table: A new dataset and method for structured table generation.In Proceedings of the 6Oth Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers), pages 2518-2533.

Wael M.S. Yafooz, Siti Z.Z. Abidin, Nasiroh Omar, and Zanariah Idrus. 2O13.Managing unstructured data in relational databases.In 20l3 IEEE Conference on Systems,Process and Control (ICSPC), pages 198- 203.

Tao Yu, Rui Zhang, Kai Yang, Michihiro Yasunaga, Dongxu Wang, Zifan Li, Qingming Ma, Irene Li, Shanelle Yao, Yi Zhang,et al. 2018.Spider: A largescale human-labeled dataset for complex and crossdomain semantic parsing and text-to-sql task. In Proceedings of the 2O18 Conference on Empirical Methods in Natural Language Processing (EMNLP), pages 3911-3921.

Yuniarti Yuliana and Chia-Hui Chang.2O16.Afis:Automatic format-induction system for detail web pages. In The Asian Conference on Artificial Intelligence (TAAI).

Yuniarti Yuliana and Chia-Hui Chang. 2O2O. Dcade: Dynamic content alignment for data extraction from web pages. Journal of Information Science, 46(5):656-674.

# A Definitions

1. Canonical Join Query: The canonical join of the database schema is the natural join of all the relations in the schema. (Elmasri and Navathe, 2016)

2. Primary Key: A primary key is a set of one or more attributes that uniquely identifies a tuple within a relation.No attribute in the primary key can have a null value. (Silberschatz et al., 2020, Section 3.3.2)

3.Foreign Key: A foreign key is an attribute, ora set of attributes,in one relation that references the primary key of another relation. It ensures referential integrity between the two relations. (Silberschatz et al., 202O, Section 3.4)

4. Referential Integrity: Referential integrity is a property of a relational database that ensures that every foreign key value in a child table either matches a valid primary key in the referenced parent table or is null (if allowed). It guarantees that relationships between tables remain consistent. (Silberschatz et al., 2020, Section 3.4)

# B Dataset

Our dataset generation approach is illustrated in Fig. 5.For the BIRD dataset, we flatten each multitable database obtained from the BIRD benchmark (Li et al., 2O24) into a single table by joining related tables. Then, using the LLAMA-8B-INSTRUCT model (see prompts in Appendix 6),we generate a natural language sentence for each row. Five consecutive sentences are concatenated to create a paragraph-style input document. The same approach is applied to the Kaggle datasets (Kiattisak, 2023; Rai, 2023; Becker and Kohavi, 1996).

# CMetrics

We assess the quality of both the generated schema and its instantiated content using a suite of novel evaluation metrics that capture structural correctness, semantic alignment, and data fidelity, providing a comprehensive measure of generation quality.

# C.0.1 Schema Evaluation

We evaluate the quality of generated database schemas using three complementary metrics:

Entity Coverage Score (EcS) for columnlevel semantic alignment, Primary Key Coverage (PKC) for schema completeness,and Foreign Key Coverage （FKC） for referential integrity.

Entity Coverage Score (ECS) evaluates how well the predicted schema recovers the ground truth column names. Let $\{ c _ { 1 } , \ldots , c _ { N } \}$ be the ground truth column names and $\big \{ \hat { c } _ { 1 } , \dots , \hat { c } _ { M } \big \}$ be the predicted columns. For each ground truth column $c _ { i }$ ， we compute its cosine similarity with every predicted column $\hat { c } _ { j }$ and select the highest similarity. ECS is the average of these maximum scores:

$$
\mathtt { E C S } = \frac { 1 } { N } \sum _ { i = 1 } ^ { N } \operatorname* { m a x } _ { j \in [ 1 , M ] } \mathtt { c o s \_ s i m } ( c _ { i } , \hat { c } _ { j } )
$$

where cosine similarity is computed as:

$$
\mathsf { c o s \_ s i m } ( u , v ) = { \frac { u \cdot v } { \| u \| \| v \| } }
$$

This metric captures the best semantic match for each ground truth column using SentenceTransformer embeddings (all-MiniLM-L6-v2).

Primary Key Coverage (PKC) measures how well the generated schema supports tuple-level uniqueness by checking whether primary keys are defined. PKC is defined as:

$$
\mathsf { P K C } = \frac { \mathbb { N } \mathbf { u } \mathrm { m } \_ \mathsf { P K } } { \mathbb { N } \mathbf { u } \mathrm { m } \_ \mathsf { t a b l e s } }
$$

Here,Num_PK is the number of generated tables that define at least one primary key，and Num_tables is the total number of generated tables. This metric reflects the model's ability to generate structurally valid tables that enforce rowlevel uniqueness through primary keys.

Foreign Key Coverage (FKC) assesses the extent to which the generated schema maintains referential integrity across tables. FKC is defined as:

$$
\mathtt { F K C } = \frac { \mathtt { N u m \_ F K _ { v a l i d } } } { \mathtt { N u m \_ F K } }
$$

Here, $\mathtt { N u m \_ F K _ { v a l i d } }$ is the number of foreign keys that correctly reference existing primary keys, and Num_FK is the total number of generated foreign keys. This metric evaluates the model's ability to establish valid inter-table relationships, ensuring that foreign keys point to legitimate primary key targets.

CSV File

![](images/4a0542ad720ba8de797e045f5e38e12b33b9a6f0cb59291d0c713eb523ddbc94.jpg)  
Figure 5: Our dataset generation process

# C.0.2Database Evaluation

We use five evaluation metrics to assess how well the generated database reconstructs the ground truth data: Database Construction Success Rate (DBR)，Referential Integrity Rate (RRIR),Tuple Coverage (TC),Value Coverage (VC),and Column Consistency (CC). Database Construction Success Rate (DBR) captures the percentage of successfully generated databases from text documents.

$$
\mathsf { D B R } = \frac { \# \mathsf { G e n e r a t e d ~ D B } } { \# \mathrm { T e x t ~ D o c u m e n t s } }
$$

Referential Integrity Rate (RRIR) captures whether foreign key joins result in meaningful, nonsparse rows during execution.Let $\mathrm { \textmathcal { D } }$ be the set of evaluated databases,and let each database $d \in \mathcal { D }$ produce a set of rows $\mathcal { R } _ { d }$ from a canonical foreign key join. For each row $r \in \mathcal { R } _ { d }$ ,let $n _ { \tt t o t a l } ( r )$ be the number of columns, and $n _ { \tt N L 1 } ( r )$ the number of columns with null values. The per-database score is:

$$
\mathtt { R R I R } ( d ) = \frac { 1 } { | \mathscr { R } _ { d } | } \sum _ { r \in \mathscr { R } _ { d } } \bigg ( 1 - \frac { n _ { \mathtt { n u l l } } ( r ) } { n _ { \mathtt { t o t a l } } ( r ) } \bigg )
$$

The overall score across all databases is:

$$
{ \mathrm { R R I R } } = { \frac { 1 } { | \mathcal { D } | } } \sum _ { d \in \mathcal { D } } { \mathrm { R R I P } } ( d )
$$

This metric provides a practical signal of referential soundness during execution by quantifying the completeness of joined rows in terms of non-null content.

Tuple Coverage (TC） quantifies how many ground truth rows are recovered through canonical joins. Let $\mathcal { R } _ { \mathtt { G T } }$ be the set of primary keys from the ground truth database,and $\mathcal { R } _ { \mathrm { j } \circ \mathrm { i n } }$ be the set of primary keys resulting from the canonical join query over the generated database. Then:

$$
\mathtt { T C } = \frac { | \mathcal { R } _ { \mathtt { G T } } \cap \mathcal { R } _ { \mathtt { j o i n } } | } { | \mathcal { R } _ { \mathtt { G T } } | }
$$

This metric reflects the row-level reconstruction accuracy.

Value Coverage (vC) measures the proportion of ground truth cell values that are accurately recovered in the predicted database.A predicted value $\hat { v }$ is considered a match to a ground truth value $v$ if:

· For numeric values: $| v - \hat { v } | < 1 0 ^ { - 2 }$ (i.e., absolute difference less than 0.01). · For textual values: the cosine similarity between embeddings satisfies cos_sim $( v , \hat { v } ) >$ 0.8.

Let $\mathcal { V } _ { \mathtt { G T } }$ be the set of all ground truth values, and $\mathcal { V } _ { \mathtt { D B } }$ be the set of predicted values matched to ground truth under the criteria above.Then VC is defined as:

$$
\mathrm { V C } = \frac { | \mathcal { V } _ { \sf G T } \cap \mathcal { V } _ { \sf D B } | } { | \mathcal { V } _ { \sf G T } | }
$$

This ratio reflects the overall proportion of correctly reconstructed cell values, incorporating both numeric precision and semantic similarity for text.

Column Consistency (CC) quantifies the proportion of matched values that appear under the correct column names in the predicted database.A column name in the prediction is considered correct if its semantic similarity with the corresponding ground truth column name exceeds a threshold of O.7, i.e.,

$$
\mathsf { c o s \_ s i m ( c o l _ { G T } , c o l _ { D B } ) > 0 . 7 }
$$

Formally, restricting the sets $\mathcal { V } _ { \mathtt { G T } }$ and $\mathcal { V } _ { \mathtt { D B } }$ to values within a specific column col, CC is defined as:

$$
\mathrm { C C } = \frac { | \mathcal { V } _ { \sf G T } \cap \mathcal { V } _ { \sf D B } | } { | \mathcal { V } _ { \sf G T } | } , \quad \mathrm { w h e r e } \ \mathcal { V } _ { \sf G T } , \mathcal { V } _ { \sf D B } \in \sf c o l  { }
$$

Here,the intersection counts only those values matched under semantically correct columns according to the cosine similarity criterion above.

# DExperimentation Details

# D.1 Experimental Setting

Computational Resources and Model Sizes. We report the number of parameters,computational budget,and infrastructure details for all models and experiments used in this work. The models employed include: LLAMA3-8B-INSTRUCT (8B parameters), CLAUDE 3.7 SONNET (parameter size not disclosed), GPT-4o (parameter size not disclosed), QwEN3-8B (8B parameters), and DEEPSEEK-V2.5 (16B parameters). All experiments, including both development and final evaluation runs,were conducted using 1 GPU (NVIDIA A10, 24 GB VRAM) over a total of approximately 100 GPU hours. Our computing environment included 48-core Intel Xeon Silver 4310 CPUs and 128 GB RAM, running on Ubuntu $2 4 . 0 4 . 2 ~ \mathrm { L T S }$ These details are provided to support reproducibility and contextualize the performance reported in this study.

# D.2Results

We report additional results from our study in this section. Table 7 presents schema coverage scores across different domains and datasets for the DEEPSEEK-V2.5 model and CoT approach. Table 8 shows the impact of different value sources

on Tuple Coverage (TC), Value Coverage (VC) and Column Consistency (CC).   
Table 7: Schema coverage scores across different domains and datasets for the DEEPSEEK-V2.5 model and CoT approach.   

<table><tr><td>Domain</td><td></td><td>ECS</td><td>PKC</td><td>FKC</td></tr><tr><td rowspan="3"></td><td>Tourstion</td><td>9.15</td><td>100</td><td>100</td></tr><tr><td></td><td></td><td></td><td></td></tr><tr><td>Finance</td><td>84.71</td><td>100</td><td>100</td></tr><tr><td></td><td>California Schools</td><td>76.84</td><td>100</td><td>100</td></tr><tr><td rowspan="5"></td><td> Superhero</td><td>77.55</td><td>100</td><td>100</td></tr><tr><td>Books</td><td>84.87</td><td>100</td><td>100</td></tr><tr><td>Computer Student</td><td>57.46</td><td>100</td><td>100</td></tr><tr><td>Mental Health Survey</td><td>38.97</td><td>100</td><td>100</td></tr><tr><td>Authors</td><td>86.44</td><td>100</td><td>100</td></tr></table>

# D.3Additional Context

Baseline Join Query vs SQUiD Join Query. For the baseline case, the model was prompted to generate join queries after seeing the full table contents, allowing it to tailor joins to observed values. In contrast, SQUiD ’s join queries are issued independently of table population,which may result in more None retrievals.

# ERelated Work

Recent research relevant to our task of synthesizing relational databases from unstructured text spans three primary areas: (1） summarizing structured information from text (2) interacting with or modifying existing databases (3) domain-specific, nonLLM approaches based on rule-based or statistical methods for relational structure extraction from text.

Summarizing Structures from Text. A widely studied area related to our task is Open Information Extraction (OpenIE),which extracts subject, predicate,object (SPO) triplets from unstructured text (Niklaus et al., 2018). While OpenIE provides useful abstractions, the extracted triplets are not organized under a formal data model. A more structured alternative is the text-to-table generation task. Early works approach this as a sequence modeling problem, jointly generating column headers and cell contents (Wu et al., 2022). More recent systems such as $\mathbf { g T B L S }$ (Sundar et al., 2024) and

<table><tr><td rowspan="3">Model</td><td rowspan="3">Diff.</td><td colspan="2">T</td><td colspan="4"></td><td colspan="2">L</td><td colspan="2"></td><td colspan="2">TS</td><td colspan="2">TL</td><td colspan="3">SQUiD</td></tr><tr><td colspan="2"></td><td colspan="2"></td><td colspan="2">(2)</td><td colspan="2">(3)</td><td colspan="2"></td><td colspan="2">(1)+(2)</td><td colspan="2">(1)+(3)</td><td colspan="2">(1)+(2)+(3)</td></tr><tr><td>(1)</td><td>VC</td><td>CC</td><td>TC</td><td>VC</td><td>CC</td><td>TC VC</td><td>CC</td><td>TC</td><td>VC</td><td>CC</td><td>TC</td><td>VC</td><td>CC</td><td>TC</td><td>VC CC</td></tr><tr><td rowspan="4">CLAUDE3.7SONNET</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>Easy1.000.970.971.000.970.970.980.930.931.000.980.981.000.970.971.000.980.98</td><td></td><td></td></tr><tr><td>Med 0.850.680.640.930.740.700.930.740.700.970.770.720.970.770.720.980.780.74</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>Hard0.820.510.330.940.580.370.880.510.330.960.600.400.970.600.391.000.630.41</td><td></td><td></td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>Avg.0.890.72 0.650.960.760.680.930.720.650.980.780.700.98 0.780.700.990.800.71</td><td></td></tr><tr><td rowspan="4">DEEPSEEK-V2.5</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>Easy 0.990.920.92 0.99 0.940.941.000.92 0.91</td><td></td><td></td><td></td><td></td><td></td><td></td><td>1.00 0.96 0.961.00 0.950.951.00 0.96 0.96</td><td></td><td></td></tr><tr><td>Med 0.960.760.710.870.680.640.900.690.660.980.790.750.98 0.800.760.990.800.77</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td>Hard 0.89 0.54 0.35 0.83 0.42 0.26 0.75</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>0.350.24</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>0.950.57 0.380.950.570.380.950.59 0.39</td><td></td></tr><tr><td>Avg.0.950.740.660.900.680.620.880.650.600.980.780.700.980.780.700.980.79 0.71</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td rowspan="4">GPT-40</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>Easy0.980.900.900.980.930.931.000.900.890.990.950.951.000.960.961.000.970.97</td><td></td><td></td></tr><tr><td>Med 0.940.750.71 0.880.690.660.900.68 0.640.980.80 0.760.98 0.810.770.99 0.810.77</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td>Hard 0.81 0.50 0.32 0.78 0.41</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>0.290.93 0.51 0.33 0.92 0.56 0.38 0.97 0.59 0.38 0.97 0.61 0.40</td><td></td></tr><tr><td>Avg.0.910.710.640.880.670.630.940.690.620.970.770.700.980.790.700.990.800.71</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td rowspan="4">LLAMA3-B-INSCad.95.70..76..07...00.750..0.76..0.7</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>Easy 0.99 0.89 0.88 0.81 0.74 0.74 0.77 0.61 0.601.000.950.951.000.940.941.000.950.95</td><td></td><td></td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td>Avg.0.960.730.640.810.540.490.790.540.470.990.780.690.990.790.701.000.810.71</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td rowspan="4">QWEN3-8B</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>Easy0.990.920.92 0.97 0.92 0.920.850.72 0.721.00 0.960.961.000.96 0.961.00 0.96 0.96</td></tr><tr><td>Med 0.940.710.710.900.710.710.960.670.670.950.740.730.98 0.780.780.98 0.790.79</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td>Hard0.570.290.290.360.230.230.760.350.350.590.330.330.990.480.480.990.51 0.51</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr><tr><td>Avg. 0.830.640.640.750.620.620.850.58 0.580.850.680.670.99 0.740.740.990.76 0.75</td><td></td><td></td><td></td><td></td><td></td><td></td></table>

Table 8: Impact of diferent value sources on Tuple Coverage (TC), Value Coverage (VC)and Column Consistency (CC).TS combines tuples generated from $\mathbb { T }$ and $\mathbb { S }$ while TL combines T and L. SQUiD combines outputs from all three prompts.

Seq2Seq&Set(Li et al., 2023) decouple schema inference from data population in the text-to-table task,yielding improvements in table validity and structure. Other lines of work explore extracting structured data from semi-structured documents such as HTML and PDF using LLMs (Arora et al.. 2023)，or schema-driven information extraction from heterogeneous tables (Bai et al., 2023). However, the outputs remain flat and lack the normalized relationships central to relational database design. T3 (Deng et al., 2024) takes a step further by converting extracted tuples into flat tables,which is conceptually closest to our use of intermediate triplet representations. Still, their method does not capture inter-table relationships,limiting alignment with relational database requirements. Additionally, other research explores non-relational structures such as mind maps for representing extracted information (Jain et al., 2O24), which similarly do not align with the relational database model our work targets.

Manipulating Existing Databases. Another line of work focuses on interacting with or updating existing relational databases using language. Early work such as (Mansuri and Sarawagi, 2OO6) proposed integrating unstructured sources into relational databases using information extraction and matching techniques,but relied heavily on statistical models,rule-based systems and domainspecific heuristics. In TEXT2DB (Jiao et al., 2024), LLM agents ingest documents and update a preexisting relational database. While it operates on relational databases, it assumes an existing database with a predefined schema and does not attempt to synthesize a new one. On the other hand, the textto-SQL literature (Hong et al., 2024; Yu et al., 2018) focuses on translating natural language queries into executable SQL statements over a known schema. Other works in this space include relation-aware schema encoding for better generalization (Pang et al.,2O2O), constrained decoding for syntactically valid SQL generation (Scholak et al., 2021), and synthetic data generation to improve model robustness (Chang et al., 2024). However, none of these works attempt to synthesize a relational database from text.

Non-LLM Approaches for Relational Structure Extraction From Text. Before LLMs, integrating unstructured text into relational databases relied on classical pipelines combining information extraction, schema induction, and entity linking. Systems such as DeepDive (Zhang et al., 2016), LILLIE (Smith et al., 2022b), and OpenKI(Zhang et al., 2O19) extracted structured facts and aligned them with relational schemas using statistical inference， symbolic reasoning，or context-aware matching. In web-centric domains,methods like SEDE(Deng, 2010, 2011) and wrapper induction systems (Carlson and Schafer, 2OO8; Chang and Wu, 2016; Yuliana and Chang,2016, 2020) inferred schemas from repeated HTML patterns and populated tables using DOM-based alignment. Statistical models such as SICTF (Nimishakavi and Talukdar,2016) induced relation schemas from OpenIE triples via joint tensor factorization. These nonLLM methods demonstrated the feasibility of relational synthesis via symbolic or statistical reasoning, but typically required domain-specific tuning and struggled to generalize across diverse, noisy input text.

Broadly, existing research either aims to extract tables from text or to interface with predefined relational databases-without bridging the gap between the two. To our knowledge, no existing work performs fully automated and domain-generalized text-to-relational database synthesis. Our system fills this gap by leveraging a neurosymbolic framework that decomposes the task into interpretable stages.

# FArtifact Use

# F.1Dataset License Information

In accordance with ACL guidelines, we disclose the licenses of all datasets used.

The BIRD benchmark datasets (Li et al., 2024) are distributed under various open licenses including Public Domain, CC0, CC-BY 4.0, CC-BY-SA 4.0, GPL,and CPOL, all permiting research use and redistribution.

The Kaggle datasets utilized in our experiments are licensed as follows,and all allow research use and redistribution:

· Tourism dataset (Kiattisak, 2O23): Licensed under Creative Commons Attribution 4.0 (CCBY 4.0).   
·Education dataset (Becker and Kohavi, 1996): Licensed under Creative Commons Attribution 4.0 (CC-BY 4.0).   
· Finance dataset (Rai, 2O23): Licensed under the MIT License.

The language models employed are publicly available and used under their respective license or terms of service:

permits free use,modification, and redistribution under open-source terms.

Additionally，we will release our generated dataset publicly under a CC BY 4.0 License.

# F.2Software and Language Models

We used Stanford CoreNLP (v4.5.9) (Manning et al., 2014), licensed under GNU GPLv3, which

· LLAMA-3-8B-INSTRUCT (Meta AI, 2024): Released under Meta's research license allowing academic use.   
· CLAUDE 3.7 SONNET (Anthropic, 2024): Provided under Anthropic's terms for research and commercial use.   
· GPT-4o (OpenAI, 2024): Accessed via OpenAI's API under their usage policies.   
· QWEN3-8B (Alibaba, 2024): Released with a permissive license for research use.   
· DEEPSEEK-V2.5 (DeepSeek AI, 2024): Licensed for research use as specified by DeepSeek AI.

# GPrompts

All of the prompts we use in SQUiD are provided in Figures 6 to 20.

![](images/417d514e160ad64061e22b84e8291973653ccf62e6850af21c0f1f8446b349ef.jpg)  
Figure 6: Prompts for dataset generation with LLAMA3-8B-INSTRUCT: system prompt

![](images/8c527eb15e7a93dba4c713ed07b6c1421a0426da4e91e09672f235c56583c8c9.jpg)  
Figure 7: Prompts for dataset generation with LLAMA3-8B-INSTRUCT: user prompt template

![](images/5a03c49ea25de70bd826523247b27cbf2c04b5bd119c69b2e7bf15284fdc42dd.jpg)  
Figure 8: Prompts for schema generation: system prompt

![](images/029a782e85439cf599ae71d4f13b74bc72f9c4a632309817fbdf99481ab92caa.jpg)  
Figure 9: Prompts for schema generation: user prompt template

![](images/21fa746624782b2bd4bc13a89ad6ab0c3ba24e476eae8df37e3dc6cd9bfb9ac5.jpg)  
Figure 10: Prompts for schema generation: CoT - system prompt

![](images/841e33bf2837bf80b4b9240b4ea46bc42b38d494286a60997a263e3d7c21bc3e.jpg)  
Figure 11: Prompts for schema generation: CoT - user prompt template

You are a helpful assistant that who assists a user with information extraction tasks. Your job is to associate a unique superkey value with each paragraph in the text. You will be given multiple paragraphs of text，a database schema， and a superkey. Your task is to associate the superkey value with each paragraph in the text. Each paragraph MUST be associated with a superkey value. No two superkey values should be the same. Fill in the <FILL IN WITH APPROPRIATE VALUE OF {superkey}> with the value.You will not provide code or SQL，you will do the task yourself.

![](images/28c58cf9220afee0b99f6a1968bc1d491535d4910cc046ce34069cfcdde2642b.jpg)  
Figure 12: Prompts for triplet generation with LLM- unique identifier association: system prompt   
Figure 13: Prompts for triplet generation with LLM- unique identifier association: user prompt template

![](images/61bd6c7e13a6817c86c6709f0f52a8d0134fd39a85632f88f761b8d179271d8e.jpg)  
Figure 14: Prompts for triplet generation with LLM- triplet generation: system prompt

![](images/f239aaaabcd4a3a5896386da531ef0424f87a2cb1e1e8c4325c214a671b3a9bc.jpg)  
Figure 15: Prompts for triplet generation with LLM- triplet generation: user prompt template

![](images/79dd299068164151eeec308e83794fadfa5f2bc28077f16e9530405155f52d1f.jpg)  
Figure 16: Prompts for table population: tooluse prompt for extraction   
Figure 17: Prompts for table population: Method T

system_prompt $=$ f"""You are an expert at populating values in a database from text based on a given database schema. I have provided a paragraph of text and a database schema. Using this information, your task is to extract relevant values and format them according to the schema.Do not provide code, do the task yourself."   
user_prompt = f"   
### \*\*Text: $\star \star$   
{text}   
### \*\*Schema: $\star \star$   
{schema}   
### \*\*Expected Output Format:\*\*   
{data_template}   
Output as many rows as necessary to populate the data. Replace the '#' with the actual values from the text.   
You will follow this chain-of-thought reasoning to generate the final output:   
- Generate output entries relevant to the text.   
- Follow the given output format strictly. Do not add any additional explanations or comments. Only output the data entries in given format. Do not provide code，do the task yourself.   
### \*\*Output: $\star \star$

![](images/860293a8d29ebf1d0336d2d3194db1486670e6ad4b0fd6baa8014c31fabd450e.jpg)  
Figure 18: Prompts for table population: Method S

![](images/23dfdd696972d140e291f2d474ef6dc83a18984c8bff3b2cb6c57883f682f9a3.jpg)  
Figure 19: Prompts for table population: Method L

![](images/759506478206a74a200bc9cac8626690833318ffc08ad8524d59a8b9d274b392.jpg)  
Figure 20: Prompts for baseline

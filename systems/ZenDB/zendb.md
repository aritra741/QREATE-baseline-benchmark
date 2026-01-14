

Towards Accurate and Efficient Document Analytics
with Large Language Models
## Yiming Lin
## 1
## , Madelon Hulsebos
## 1
## , Ruiying Ma
## 2
## , Shreya Shankar
## 1
## , Sepanta Zeighami
## 1
## ,
## Aditya G. Parameswaran
## 1
## , Eugene Wu
## 3
## 1
UC Berkeley,
## 2
## Tsinghua University,
## 3
## Columbia University
## {yiminglin,madelon,shreyashankar,zeighami,adityagp} @berkeley.edu
mry21@mails.tsinghua.edu.cn, ewu@cs.columbia.edu
## ABSTRACT
Unstructured data formats account for over 80% of the data cur-
rently stored, and extracting value from such formats remains a
considerable challenge. In particular, current approaches for man-
aging unstructured documents do not support ad-hoc analytical
queries on document collections. Moreover, Large Language Mod-
els (LLMs) directly applied to the documents themselves, or on
portions of documents through a process of Retrieval-Augmented
Generation (RAG), fail to provide high-accuracy query results, and
in the LLM-only case, additionally incur high costs. Since many
unstructured documents in a collection often follow similar tem-
plates that impart a common semantic structure, we introduce
ZenDB, a document analytics system that leverages this semantic
structure, coupled with LLMs, to answer ad-hoc SQL queries on
document collections.ZenDBefficiently extracts semantic hierar-
chical structures from such templatized documents and introduces
a novel query engine that leverages these structures for accurate
and cost-effective query execution. Users can impose a schema on
their documents, and query it, all via SQL. Extensive experiments
on three real-world document collections demonstrateZenDB’s
benefits, achieving up to 30×cost savings compared to LLM-based
baselines, while maintaining or improving accuracy, and surpassing
RAG-based baselines by up to 61% in precision and 80% in recall, at
a marginally higher cost.
## 1  INTRODUCTION
The vast majority—over 80%—of data today exists in unstructured
formats such as text, PDF, video, and audio, and is continuing to
grow at the rate of over 50% annually [2,8]. In fact, an overwhelming
95% of businesses have recognized management of this unstruc-
tured data as a significant problem [1]. Considerunstructured text
documents, such as Word or PDF documents, with a rich treasure
trove of untapped information. Due to the inherently free-form na-
ture of natural language, coupled with visual formatting, real-world
unstructured documents pose a particularly difficult challenge for
data management.Is there any hope for successfully querying or
extracting value from unstructured documents?
Example 1.1 (Civic Agenda Report: Vanilla LLMs and RAG).Our
journalism collaborators at Big Local News at Stanford have col-
lected large tranches of civic meeting agenda PDF reports for var-
ious US counties as part of their agenda watch project, as in Fig-
ure 1-a, and want to analyze these reports. One such query could
be to count the number of construction projects of a certain type,
across meetings. To do so, one could use Large Language Mod-
els (LLMs). However, even advanced LLMs, such as GPT-4, strug-
gle with queries issued on such reports (e.g.,푄1in Figure 1-d),
## R
## A1
## A3
## B2
## B3
## ......
## A2
c) Semantic Hierarchical Tree
## B1
## ............
b) Semantic Structure
SELECT COUNT(Projects.name)
FROM Projects
WHERE Projects.type = ‘Capital Improvement’
AND Projects.begin_time > ‘2022’
Q1: ‘What is the number of Capital Improvement
projects that start after 2022’
## Q2:
d) Natural Language Query and corresponding SQL Query
a) Civic Project Agenda Report
## R
## A1
## B1
## B2
## C1
## (1)
## (10)
## (11)(22)
## (63)
## (192)
## (64)
Figure 1:Civic Agenda Document and Semantic Structures.
especially when these queries involve aggregations and/or multi-
ple filters on long documents. The error-prone nature of LLMs is
not surprising given that LLMs can’t effectively handle large con-
texts [19,45], or complex data processing tasks [48,49]. The costs
of processing all documents in a collection via LLMs (e.g., through
OpenAI APIs) are also high. Another strategy, Retrieval-Augmented
Generation (RAG) [39,41], identifies one or more text segments
within each document that are most relevant (e.g., via embedding
distance) to the given query, incorporating these segments into
prompts, reducing the cost. However, RAG struggles to identify the
appropriate text segments, even for simple queries. Suppose we
want to identify the capital improvement projects. RAG retrieves the
segments that most closely matches "capital improvement projects"
within the document, such as the red box in Figure 1-a. However,
it fails to capture over 20 additional projects in subsequent pages,
such as the "PCH Median Improvement Project" (B2 in Figure 1-b)
belonging to "Capital Improvement Projects" (A1). Overall, both
the vanilla LLM approach and RAG are unsuitable: both have low
accuracy, while the LLM approach additionally has high cost.
Leveraging Semantic Structure Helps.The reason RAG didn’t
perform well above was because the text segment provided to
the LLM did not leverage the semantic structure underlying the
document. Instead, if we are aware of this semantic structure, we
can identify the capital improvement projects (A1 in Figure 1-b) by
checking all of the subportions (e.g., B1, B2) under it, where each one
corresponds to the description of such a project, and provide this
arXiv:2405.04674v1  [cs.DB]  7 May 2024

## LLM
ZenDB
## RAG
## Cheap
93% lower cost
97% lower cost
25% higher
accuracy
48% higher
accuracy
## Accurate
Figure 2:Understanding the differences
betweenZenDB, LLMs and RAG.
a) Scientific Papers
b) Notice of Violations c) Employee Job Descriptions
Figure 3:Templatized Documents: Scientific Papers, Notice of Violations, Job Descriptions.
to an LLM to interpret. By doing so, weprovide all of the pertinent
information to an LLM, unlike RAG, while also not overwhelmingit
with too much information. Indeed, when we leverage semantic
structure for a group of sample queries on GPT-4-32k, as in our
systemZenDB, described next, we surpass the vanilla LLM and
RAG approachesby 25% and 48% in accuracy, while only having
7% of the costof LLMs, as detailed in Figure 2.
Templatized Documents Provide Semantic Structure.Given
that semantic structure is helpful,how do we extract this semantic
structure within unstructured documents?Turns out, while unstruc-
tured documents vary considerably in format, many documents
that are part of collections are created using templates, which we
calltemplatized documents. Templatized documents are observed
across domains, including civic agenda reports, scientific papers,
employee job descriptions, and notices of violations, as listed in
Figure 1 and Figure 3. For instance, two scientific papers from the
same venue use similar templates, just as civic documents for the
same purpose from the same local county often adhere to a uni-
form template. Templatized documents often exhibit consistent
visual patterns in headers (e.g., font size and type), when describing
content corresponding to the same semantic “level” (e.g., section
headers in a paper often follow the same visual pattern.) We high-
light the “templates” using blue boxes in Figure 3. Thus, templatized
documents are often have a discernible hierarchical structure that
reflects different semantic levels within the document. For exam-
ple, a 9-page complex civic agenda report (such as Figure 1-a) can
be broken down into portions (e.g., A1, A2, A3 in Figure 1-b) and
further into subportions (e.g., B2), indicating a possible semantic
hierarchy, such as Figure 1-c, across the documents following the
same template.
Leveraging Semantic Structure: Challenges.Unfortunately, the
semantic structure of the templates isn’t known—and neither do we
expect these templates to be rigidly adhered to, nor do we expect
there to just be one template across the collection of documents
from a specific domain. Uncovering possible common semantic
structures across documents is a challenge. In addition, to sup-
port queries over unstructured data where there isn’t a predefined
schema, it’s not entirely clear what the data model or query inter-
face should look like. Furthermore, using LLMs for query evaluation
incurs high monetary costs and latencies; it’s not obvious how we
can leverage the semantic structures across documents to enable
accurate query execution with low cost and latency.
Addressing Challenges inZenDB.We introduceZenDB, a docu-
ment analytics system that supports ad-hoc advanced SQL queries
on templatized document collections, and address the aforemen-
tioned challenges. First, we introduce the notion ofSemantic Hierar-
chical Trees (SHTs)that represent the semantic structure for a given
document, and effectively act as an index to retrieve only portions
of the document that are pertinent to a given query. We build SHTs
across documents by leveraging the uniform visual patterns in the
document templates. We cluster the visual patterns found across
documents to extract and detect various template instantiations,
coupled with minimal LLM calls for this purpose. We show that if
documents obey a property we termwell-formattedness, then our
procedure correctly recovers their semantic structure. Second, we
introduce an extension to SQL to query unstructured documents
(e.g.,푄1in Figure 1 could be expressed as a SQL query푄2.) Users
can easily impose a schema on a collection of documents by simply
listing a table name as well as a description for the entities in the
table, without listing the attributes, which can then be lazily defined
and populated in response to queries. Finally, we introduce a novel
tree search algorithm that leverages SHTs to minimize cost and
latency while answering queries without compromising on quality.
Specifically, we propose a summarization technique to create sum-
mary sketches for each node within the tree.ZenDBcan navigate
through the tree, identifying the appropriate node to answer a given
query by examining these sketches, akin to how a person might
use a table of contents to find the right chapter for a specific task.
Other Related Work.Supporting queries on non-relational data
isn’t new. For unstructured data, the field of Information Retrieval
(IR) [37,53] investigates the retrieval of documents via keyword
search queries, but doesn’t consider advanced analytical queries.
For semi-structured data [15,16,47], query languages like XQuery
or XPath, as well as extensions to relational databases for querying
XML and JSON, help query hierarchically organized data, as in our
SHTs, but there, the hierarchy is explicit rather than implicit as in
our setting. Recent efforts have sought to bridge the gap between
structured queries, like SQL, and unstructured documents. One line
of work [58,61] has explored the upfront transformation of text
documents into tables. Doing this ETL process with Large Language
Models (LLMs) like GPT-4 on entire documents is expensive and

## Document
## Ingestion
(Section 3)
## Unstructured
## Documents
Schema & Query Spec. (Section 4)
Data Population (Section 5)
## Query
## Execution
(Section 6)
## Query Results
Figure 4:User Workflow withZenDB.
error-prone relative to approaches that focus the LLM’s attention
on specific semantic portions, as we saw above. Others [24,55,56]
have explored writing SQL queries directly on text data, as part
of multi-modal databases. Most work there boils down to apply-
ing LLMs to the entire document, and only works well on simple,
small documents. However, using these methods on complex, large
documents we saw above leads to high costs and reduced accuracy.
None of the approaches above have explored the use of seman-
tic structure to reduce cost and improve accuracy when querying
documents. We cover this and other related work in Section 8.
We make the following contributions in this paper, as part of
buildingZenDB, our document analytics system.
•We identify that we can leverage templates within document
collections to support ad-hoc analytical queries.
•We introduce the notion of Semantic Hierarchical Trees (SHTs)
that represents a concrete instantiation of a template for a spe-
cific document, as well as novel methods to efficiently extract
SHTs from an array of templatized documents.
•We develop a simple extension to SQL to declare a schema,
specify attributes on-demand, and perform analytical queries.
•We design a query engine that leverages SHTs, facilitating query
execution in a cost-effective, efficient, and accurate manner.
•We implement all of these techniques withinZenDBand evalu-
ate its performance on three real-world datasets, demonstrating
substantial benefits over other techniques.
## 2  USER WORKFLOW WITHZENDB
In this section, we present an overview of user workflows with
ZenDB, as illustrated in Figure 4. First,
## 1
document collections are
ingested into the system by understanding common semantic struc-
ture (Section 3). Then,2users (typically database administrators)
can specify a schema for these documents, including tables and
lazily-specified attributes, followed by queries that reference this
schema, either specified by end-users who know SQL, or generated
by applications (Section 4).ZenDBalso populates upfront a set
of system-defined tables/attributes to help capture the mapping
between tuples and the documents (Section 5). Finally,3given
queries on these documents, either generated by applications or by
end-users directly,ZenDBwill execute them efficiently, leveraging
the semantic structure (Section 6).
1Semantic Structure Extraction.Given a collection of templa-
tized documents that adhere to one or more predefined semantic
structures, the first step withinZenDBinvolves extracting this
structure in the form of Semantic Hierarchical Trees (SHTs), per
document, so that they can be used downstream for query execu-
tion. This is broken down into two sub-problems: First, how do
we extract an SHT from a single document? Second, how do we
leverage common semantic structure across documents to scale
up SHT extraction? Since templatized documents typically display
consistent visual patterns in headers for similar semantic content,
we cluster based on such visual patterns, coupled with minimal
LLM invocations, to construct a single SHT (Section 3.2). Then, we
use a visual pattern detection approach to determine whether we
CREATE TABLE Projects WITH DESCRIPTION "The projects table contains
the description for a set of civic agenda projects.”
ALTER TABLE Projects
ADD name TEXT WITH DESCRIPTION "Name of Project",
ADD type TEXT WITH DESCRIPTION "Type of Project",
ADD begin_time DATE WITH DESCRIPTION "Begin time of Project";
Figure 5:Creating the Projects Table and Adding Attributes.
can reuse a previously identified semantic structure in the form
of a template, synthesized from a concrete SHT, or extract a new
one (when there are multiple templates in a collection), all without
using LLMs (Section 3.3).
2Schema/Query Specification and Table Population.Given
one SHT per document,ZenDBthen enables users to specify a
schema across documents in a selection, followed by issuing queries
on that schema. Schema definition happens via an extension of stan-
dard SQL DDL: users (typically database administrators) provide a
name and description for each table—that we calldocument tables,
along with names, types, and descriptions for any attributes; the
attributes can be lazily added at any point after the table is cre-
ated (Section 4.1). For example, Figure 5 shows the query used to
create a "Projects" table along with attributes (e.g., name). Subse-
quently, other users can write queries that reference such tables
and attributes (e.g.,푄2in Figure 1), as in standard SQL (Section 4.2);
these queries could also be generated by applications (including
form-based or GUI-based applications), or by translating natural
language queries into SQL. We still concretize the query in SQL to
provide well-defined semantics.
While attributes are added lazily and attribute values are computed
or materialized in response to queries, we proactively identify map-
pings between tuples and documents during schema specification
(Section 5). Specifically, we identify the SHT node that represents
the portion of the document that captures all of the relevant tuples
in a given user-specified table, as well as the mapping between
tuples to individual SHT nodes, if they exist, using a combination
of minimal LLM invocations and automated rules. These are then
stored in our data model as hidden system-defined attributes, such
as the span of the text that corresponds to the given tuple, leverag-
ing nodes in the SHTs built earlier. These system-defined attributes
allow for LLMs to extract the user-defined attribute values per tuple
as needed, while reducing costs, while also leveraging the shared
semantic structure across documents.
3Query Execution.Finally,ZenDBexecutes the user-specified
SQL queries using the pre-constructed SHTs per document, while
minimizing cost and latency, and maximizing accuracy. Unlike tradi-
tional relational databases, where I/O and sometimes computation
are often the bottleneck, here, the LLM calls invoked byZenDB
becomes both a cost and latency bottleneck. Therefore,ZenDBaims
to minimize such calls, while still trying to extract attribute values
as needed to answer queries, by using a combination of predicate
pushdown and projection pull-up. We additionally develop a cost
model forZenDB, focusing on monetary cost (Section 6.1). Our cost
model design is flexible and can be adapted to optimize for latency
instead, e.g., if we instead use an open-source LLM on-prem. Fur-
thermore, we design novel physical implementations that leverage
SHTs (Section 6.2). In particular, we maintain a sketch for each node
in each SHT, and leverage this sketch as part of a tree search to
identify the appropriate text span to evaluate a given query, akin to
how a person would use a table of contents to find the right chapter.
Finally, we maintain provenance (i.e., the specific document text

## R
## A1A2
## B1B2
## 1
## 1063
## 11
## 22
## R
## A1A2
## B1
## B2
## E1
## E2
a) Phrase Clustering Based on Visual Patternsb) SHT
## (1)
## (10)
## C1
## 24
## ......
## E1E2
## 64
## 75
p1
p2(63)p2
## (11)p3(22)p3
## (64)p4
## (75)p4
p1
p2
p3
p4
p5
Figure 6:SHT Construction in Civic Agenda Report.
span) for query answers, ensuring that users can verify the source
of the information and ensuring trust in the system outputs.
## 3  SEMANTIC HIERARCHICAL TREE
In this section, we describe our process for recovering structure
from documents in the form of Semantic Hierarchical Trees (SHTs),
which then acts as an index for subsequent querying. We start by
formalizing the notion of SHTs and templates, and then describe
how to extract an SHT for a single document, followed by extracting
them across collections by leveraging shared templates.
## 3.1  Preliminaries
We focus on rich text documents, such as PDF and Word documents,
that include visual formatting information (e.g., multiple font types
and sizes), as shown in Figure 3.
Documents, Words, and Phrases.Consider a set of documents
## D={퐷
## 1
## ,퐷
## 2
## , ...,퐷
## 푙
}. For each document퐷∈ D, which may be
a PDF or Word document, we often instead operate on a plain
text serialized representation, extracted as a preprocessing step. To
generate this representation for a document퐷, we use an extraction
tool such as pdfplumber [13], which generates a sequence of words
## 푊
## 퐷
## =[푤
## 1
## , ...,푤
## 푚
], each with formatting and location features
(e.g., font name/size/bounding boxes). For simplicity, we ignore
images, but they can be treated as a special word. For any two
consecutive words푤
## 푖
and푤
## 푖+1
, if they have the same formatting
features: font size, name (e.g., Times New Roman), and type (e.g.,
bold or underline), we group them into a phrase푠. We let푆
## 퐷
## =
## [푠
## 1
## , ...,푠
## 푛
## ]
be the sequence of phrases corresponding to퐷—we often
operate on푆
## 퐷
instead of the document directly.
Visual Patterns.For each phrase푠∈푆
## 퐷
, we further define avisual
pattern,푝(푠), as a vector of visual formatting features; we currently
use:푝(푠)=[푠푖푧푒,푛푎푚푒,푡푦푝푒,푎푙푙_푐푎푝,푛푢푚_푠푡,푎푙푝ℎ푎_푠푡,푐푒푛푡푒푟]but
other features may be included. Here, the first three features corre-
spond to the font, as in the word-level features we had previously,
and the remaining three features are phrase-level features:푎푙푙_푐푎푝
is a Boolean value that denotes whether the phrase푠is capital-
ized,푛푢푚_푠푡and푎푙푝ℎ푎_푠푡indicate whether the phrase starts with
a number (e.g., 1) or a letter (e.g., A), while푐푒푛푡푒푟indicates if a
phrase is in the center of a line.
Candidate SHTs.We are now in a position to define SHTs. We
define acandidate SHTfor a document퐷to be a single-rooted,
ordered, fully connected, directed tree푇=(푉,퐸), where each
푣∈푉corresponds to a single distinct phrase푠
## 푖
## ∈푆
## 퐷
, denoted
푖푛푑(푣)=푖, thephrase indexfor푣, satisfying (1)푖푛푑(푣)<푖푛푑(푣
## ′
## )for
any children푣
## ′
of푣, and (2)푖푛푑(푣)<푖푛푑(푣
## ′
)for any right siblings푣
## ′
of푣. These two properties together imply that a pre-order traversal
of푇visits nodes in increasing phrase index order. A candidate
SHT for Figure 1a is shown in Figure 6b. Node A1 represents the
phrase (and section header) “Capital Improvement and Disaster
Recovery Projects (Design)”, while B2 represents the phrase (and
subsection header) “PCH Median Improvement Project”. The phrase
index for each node is shown in parenthesis, e.g.,푖푛푑(A1)=10;
i.e., A1 corresponds to푠
## 10
; ignore the p
## 푖
(in red) for now. The SHT
obeys the two conditions listed, e.g., A1 (with phrase index 10) has
children (11 and 22) and a sibling (63) with larger phrase indexes.
Note, however, that not all phrases in푆
## 퐷
are found in the SHT;
this is by design: the SHT simply represents the phrases correspond-
ing to theheadersof the document, while those that correspond
to thecontentare omitted. For example, Figure 6b omits phrases
## 푠
## 2
## , ..,푠
## 9
. However, in certain cases, it may be convenient to refer
to headers and content together. For this, we definetext spanor
푡푠, to be a sequence of phrases푠
## 푖
## , ...,푠
## 푖+푘
## ∈푆
## 퐷
, or equivalently
[푖,푖+푘]. We define푛푒푥푡(푣)for a given node푣to be the phrase
index corresponding to its sibling to the immediate right, if avail-
able, or, if not, the sibling to the immediate right of the closest
ancestor that has one. If none of the ancestors of푣have a right
sibling,푛푒푥푡(푣)=푛, where푛is the total number of phrases in푆
## 퐷
## .
To illustrate,푛푒푥푡(A1)=푛푒푥푡(B2)=63 (i.e., A2), while푛푒푥푡(A2)=
## 푛푒푥푡(
R)=100, assuming푠
## 100
is the final phrase in our document. A
given node푣∈푉has a text span:푡푠(푣)=[푖푛푑(푣),푛푒푥푡(푣)−1], i.e.,
푣“covers” all of the phrases until the next node with phrase index
푛푒푥푡(푣). Thus,푡푠(R)is[1,100], while푡푠(B2)is[22,62]. That is, B2
“covers” both the header,푠
## 22
, as well as the content푠
## 23
## , . . .,푠
## 62
, until
the next header, A2. In the following, we equivalently refer to a
node푣, its header phrase푠
## 푖푛푑(푣)
(i.e., the header corresponding to
푣), or text span푡푠(푣)(i.e., the header and content contained within
푣). We finally introduce the notion of agranularityorheightof a
node푣, which is simply the depth of푣in the SHT; in our example,
the depth of R is 1, and A1 is 2.
3.2  SHT Construction on a Single Document
Given a document퐷with phrases푆
## 퐷
, there are exponentially many
candidate SHTs; our goal is to identify thetrue SHTthat correctly
reflects the semantic structure of the document. To do so, our pro-
cedure,oracle_gen(퐷), first identifies which phrases are header
phrases (and therefore correspond to SHT nodes). We then assemble
these phrases into a tree, ensuring that it is a candidate SHT.
Header Phrase Identification.To identify if a phrase푠∈푆
## 퐷
is
a header phrase, we make use of visual patterns푝(푠). We cluster
the phrases in푆
## 퐷
based on their visual patterns. For our running
example, the clusters that emerge are shown in Figure 6a, each
labeled with its visual pattern (in red). Here, the majority of the
phrases end up in the cluster with pattern p5—this corresponds
to the content phrases in the document (e.g., C1 in Figure 1-a is a
paragraph). To remove clusters whose phrases do not correspond
to header phrases, we use LLMs as an oracle. We randomly sample
푚푖푛(|퐶|,푘)(푘is a predefined threshold) phrases in each cluster퐶∈
C. For each sampled phrase푠∈퐶, we construct the LLM prompt “Is
the phrase [s] a header in the document?”. If over half of the sampled
phrases in퐶are non-headers, then퐶is pruned (e.g., the cluster
containing C1 is dropped since C1 is a paragraph). To verify if
GPT-4 is effective at disambiguating headers from non-headers, we
carefully examined over 200 documents from 16 datasets, covering
six diverse domains. In our testing, when푘=10, GPT-4 effectively
removes non-header clusters on 97% of the documents with total

cost as $0.37. Still, since this cost is non-zero, we would want to
minimize it when working on a large collection of documents; as
we illustrate in our next section, we only invoke LLMs for a small
subset of documents, each corresponding to a different template.
Tree Construction.Given the header phrases across the remaining
clusters inC, we assemble the corresponding nodes into a tree. We
proceed top-down, operating on one cluster at a time, adding the
entire cluster to the partially constructed SHT. At each step, we
pick the cluster퐶that contains the phrase with the lowest index.
For each phrase푠
## 푖
in this cluster퐶, we create a corresponding node
## 푣
## 푖
and add it to the partially constructed SHT, in increasing phrase
index order, simultaneously. For each such node푣
## 푖
, we examine the
푡푠of all existing nodes in the partially constructed SHT, and pick its
parent to be the ancestor푣
## 푗
such that푖푛푑(푣
## 푖
## ) ∈푡푠(푣
## 푗
), and there is
no other푣
## 푘
## >푣
## 푗
such that푖푛푑(푣
## 푖
## ) ∈푡푠(푣
## 푘
). This condition basically
ensures that푣
## 푖
is added under the most specific node푣
## 푗
that can
accommodate it. Once we’ve identified the appropriate parents for
each node in the cluster, we then add all of these nodes together.
The root (usually corresponding to푠
## 1
) merits special treatment: if
there is no cluster that contains푠
## 1
, we create a node corresponding
to푠
## 1
, else we start with the cluster that contains푠
## 1
. Usually this
cluster just has푠
## 1
; if it contains other phrases, we create an artificial
root node corresponding to an empty phrase푠
## 0
, and deem it to be
the root. We then process the cluster that contains푠
## 1
along with
other phrases. Returning to our example, the cluster corresponding
to visual pattern푝
## 1
with phrase푠
## 1
is processed first, allowing R
to be added to the tree. Then, the cluster corresponding to푝
## 2
is
processed next as it has the lowest phrase index number 10, with
A1 and A2 added to the tree together, both with R as parent. Then,
the cluster corresponding to푝
## 3
is processed, with B1 and B2 being
added as children of A1, and so on.
Correctness for Well-Formatted SHTs.Next, we show that if
the true SHT for a document has a property that we callwell-
formattedness, thenoracle_gen(퐷) correctly outputs the true SHT.
Given an SHT푇, the visual prefix푣푖푠푝푟푒(푣)for a node푣is defined
to be the sequence of visual patterns from the root to푣. In our
example,푣푖푠푝푟푒(B1)=푝
## 1
## 푝
## 2
. We extend the definition to a set in
the natural way, e.g.,푣푖푠푝푟푒({B2, A1})= {푝
## 1
## ,푝
## 1
## 푝
## 2
}. Let푝푠푒푡(푝)be a
function that accepts a visual pattern and returns all the nodes that
obey that pattern. For example,푝푠푒푡(푝
## 2
## )={A1, A2}.
Then, an SHT푇=(푉,퐸)is said to bewell-formattedif (1) for
any two siblings푣
## 푖
## ,푣
## 푗
## ,푝(푣
## 푖
## )=푝(푣
## 푗
); (2) for all visual patterns
푝,푣푖푠푝푟푒(푝푠푒푡(푝))is unique. The first condition mandates that
sibling nodes, such as퐵1and퐵2, must share the same visual pattern.
However, it does not require that all nodes at the same depth, like
퐵2and퐸1, must have identical visual patterns. In our agenda watch
dataset, subsection headers within a section often have similar
formatting, but this need not hold across sections, i.e., different
sections may use different formatting. The second condition states
that nodes sharing the same visual pattern must have identical
visual prefixes. For example,퐵1and퐵2have the visual prefix푝
## 1
## 푝
## 2
## .
Thus, the visual pattern signifies a certain “semantic level” within
the SHT, following a consistent path to the root.
Theorem 3.1.If the true SHT for a document퐷iswell-formatted,
and if an LLM can correctly identify non-headers, thenoracle_gen(퐷)
outputs the true SHT.
Proof.Let푇and퐺푇be the SHT returned byoracle_genand
in the ground truth, respectively. We prove푇=퐺푇when푇is a
well-formatted SHT by induction. Let푣
## 푖
be the i-th node added in
theoracle_genapproach, and푁
## 푖−1
## ={푣
## 1
## ,푣
## 2
## , ...푣
## 푖−1
}be the first
(푖−1)-th nodes added inoracle_gen, respectively. Let푇
## 푖−1
and
## 퐺푇
## 푖−1
be the induced subgraph of푇and퐺푇based on the set of
nodes푁
## 푖−1
. By induction, we assume thatoracle_genreturns the
correct SHT, i.e.,푇
## 푖−1
## =퐺푇
## 푖−1
, when adding the first(푖−1)-th
nodes, and we further prove that, by adding푣
## 푖
## ,푇
## 푖
## =퐺푇
## 푖
## .
## Let푣
## 푗
and푣
## ′
## 푗
be the parent node of푣
## 푖
in푇
## 푖
and퐺푇
## 푖
, respectively.
We prove that푣
## 푗
## =푣
## ′
## 푗
by considering two cases: one where there
exists a node푣
## 푘
## ∈푇
## 푖−1
## (and푣
## 푘
## ∈퐺푇
## 푖−1
, since푇
## 푖−1
## =퐺푇
## 푖−1
) shares
the same visual pattern as푣
## 푖
, i.e.,푝(푣
## 푘
## )=푝(푣
## 푖
), and one where it
does not. Let푔(푣)be the granularity (i.e., height of node) of푣in푇
## 푖
## .
## Let푝푎푡ℎ(푣
## 푖
)be the sequence of nodes from root to푣
## 푖
in푇
## 푖
## .
## Assume∃푣
## 푘
## ∈푇
## 푖−1
and푣
## 푘
## ∈퐺푇
## 푖−1
, s.t.,푝(푣
## 푘
## )=푝(푣
## 푖
## ).푔(푣
## 푗
## )=
## 푔(푣
## 푖
## )+1since푣
## 푗
is the parent node of푣
## 푖
in푇
## 푖
. By definition,∀푣∈
## 푝푎푡ℎ(푣
## 푖
## ),푣≠푣
## 푖
, we have푖푛푑(푣)<푖푛푑(푣
## 푖
## )and푖푛푑(푣
## 푖
## ) ∈푡푠(푣). We
call each푣∈푝푎푡ℎ(푣
## 푖
## ),푣≠푣
## 푖
as a candidate parent node of푣
## 푖
since
adding an edge from푣to푣
## 푖
will make푇
## 푖
a valid candidate SHT. Thus
## 푣
## ′
## 푗
## ∈푝푎푡ℎ(푣
## 푖
)since GT should be at least a valid SHT and there is
no other푣
## 푚
## >푣
## 푗
such that푖푛푑(푣
## 푖
## ) ∈푡푠(푣
## 푚
## ). If푔(푣
## ′
## 푗
## )≠푔(푣
## 푗
), there
at least exists one node푣
## 푙
## ∈푝푎푡ℎ(푣
## 푖
## )and푣
## 푙
is a child node of푣
## ′
## 푗
## ,
s.t.,푝(푣
## 푙
## )=푝(푣
## 푖
), since퐺푇
## 푖
is a well-formatted SHT and the sibling
nodes푣
## 푙
and푣
## 푖
belonging to the same parent푣
## ′
## 푗
should have the
same visual pattern. By푝(푣
## 푘
## )=푝(푣
## 푖
), we have푝(푣
## 푙
## )=푝(푣
## 푘
), and
thus푔(푣
## 푙
## )=푔(푣
## 푘
), since푣푖푠푝푟푒(푣
## 푙
## )=푣푖푠푝푟푒(푣
## 푘
## ).푔(푣
## 푙
## )=푔(푣
## 푘
## )
implies푔(푣
## ′
## 푗
## )=푔(푣
## 푗
), which contradicts with푔(푣
## ′
## 푗
## )≠푔(푣
## 푗
## ). By
contradiction, we have푔(푣
## ′
## 푗
## )=푔(푣
## 푗
)and further푣
## 푗
## =푣
## 푗
## 푗
since both
## 푣
## 푗
and푣
## ′
## 푗
are in푝푎푡ℎ(푣
## 푖
## ).
## Assume푣
## 푘
## ∈푇
## 푖−1
and푣
## 푘
## ∈퐺푇
## 푖−1
, s.t.,푝(푣
## 푘
## )=푝(푣
## 푖
## ). Similarly
we show푣
## 푗
## =푣
## ′
## 푗
by contradiction in this case. Assuming푣
## 푗
## ≠푣
## ′
## 푗
## ,
there at least exist a node푣
## 푙
## ∈푝푎푡ℎ(푣
## 푖
## ),푣
## 푙
## ≠푣
## 푖
and푣
## 푙
is a child
of푣
## ′
## 푗
, s.t.,푝(푣
## 푙
## )=푝(푣
## 푖
), since푣
## ′
## 푗
## ∈푝푎푡ℎ(푣
## 푖
## )
and퐺푇
## 푖
is a well-
formatted SHT. However, this contradicts to the assumption that
## 푝(푣
## 푘
## )=푝(푣
## 푖
). By contradiction, we have푣
## 푗
## =푣
## ′
## 푗
, which concludes
the proof.□
3.3  SHT Construction across Documents
Given a set of documentsD={퐷
## 1
## , ...,퐷
## 푙
}, applyingoracle_gen(퐷
## 푖
## )
to each퐷
## 푖
can be costly when푙is large. Here, we leverage the fact
that, in addition to beingwell-formatted, the documents share com-
montemplates. We define the notion of a template below. We process
each document퐷
## 푖
in turn, attempting it to match against one of the
existing templates푡푝∈ TPvia a functiontemplate_gen(푡푝,퐷
## 푖
## );
if a match is successful, a SHT for퐷
## 푖
is returned–without any LLM
calls. Otherwise, we calloracle_gen(퐷
## 푖
)—here, the corresponding
template푡푝for the returned SHT is added toTP. If there are mul-
tiple successful matches inTP, we return the largest SHT of them
all; the rationale here is that we want to capture as much of the
header information as possible as part of the SHT.
Template.We now define the notion of a template associated with
an SHT. Thetemplatefor an SHT푇:푡푝={푔:{푝}}is a sorted
dictionary that captures the mapping between the granularities푔

## 1
## 2
## 56
## 3
a) SHT1
## 4
p1
p2p2
p3p3p4
## 1: {p1}
## 2: {p2}
3: {p3, p4}
tp(SHT1)
## 1
## 2
## 5
## 3
## 4
p1
p2p2
p3p3
b) SHT2
## (1)
## (5)
## (20)
## (12)(24)
## 1
## 23
p1
p2p2
c) SHT3
## (1)
## (8)
## (35)
## 1
## 23
p2
p3p4
d) SHT4
## (1)
## (6)
## (74)
Figure 7:SHT construction by Pattern Matching; the documents
represented by b and c are matches to푡푝(SHT1))but not d.
of nodes and the set{푝}of visual patterns found at that granularity.
This dictionary is additionally sorted by granularity in increasing
order.푡푝(SHT1)is the template of SHT1 shown in Figure 7-a. We
let푡푝.푔and푡푝.푝be the granularities and visual patterns in푡푝. For
SHT1 in Figure 7-a,푡푝.푔={1,2,3}and푡푝.푝={푝
## 1
## ,푝
## 2
## ,푝
## 3
## ,푝
## 4
## }. Let
푡푝.푔(푝)be the granularity of a visual pattern푝in푡푝, e.g.,푡푝.푔(푝
## 1
## )=
1 for SHT1. (This value is unique by construction from Section 3.2.)
## If푝∉푡푝.푝,푡푝.푔(푝)=−1.
Template Matching and Generation.We say a document퐷
matchesa template푡푝if the visual patterns contained amongst
the phrases푆
## 퐷
cover each granularity1. . .푖, for some푖which is a
prefix of푡푝. For instance, document퐷
## 1
with true SHT, SHT1, has
a corresponding template푡푝(SHT1)in Figure 7-a, and document
## 퐷
## 2
, has a true SHT, SHT2, Figure 7-b. Since퐷
## 2
includes patterns
## {푝
## 1
## ,푝
## 2
## ,푝
## 3
}, it covers every granularity of the template of퐷
## 1
, and
thereforematchesthe template. Additionally, document퐷
## 3
with
true SHT, SHT3, in Figure 7-c, which includes patterns{푝
## 1
## ,푝
## 2
}, also
matches the template, since it covers a prefix of the granularities
in the template (namely 1 and 2), even though it lacks patterns
{푝3,푝4}. On the other hand, document퐷
## 4
with true SHT, SHT4, in
Figure 7-d, does not contain a match for푝
## 1
, thereby not meeting
the prefix constraint, and not being a match for the template. Our
rationale for admitting prefix matches is the observation that as
the granularity of a header becomes more fine-grained, its visual
pattern tends to be more varied. For example, for two scientific
papers obeying the same template, the visual patterns of sections
remain consistent, but within each section the visual patterns used
may vary depending on individual preferences. Note here that in
our implementation, we allow for any non-zero prefix for a match;
for more constrained document collections, a user may set a prefix
threshold, e.g., at least three levels of the template must be covered.
Armed with templates and matches to a template, we can now
describe ourtemplate_gen(푡푝,퐷)procedure, listed in Algorithm 1.
We proceed in two phases, where we first identify all of the phrases
## 푠∈푆
## 퐷
that match those in푡푝.푝, we add these phrases as nodes to푉
for our yet-to-be-constructed SHT (Line 3-5). Given these phrases,
we check if there is a match for the template푡푝, where a match is
defined as above to be a prefix of the template. If no match is found,
an empty result is returned (Line 6-7), else we assemble the nodes
in푉into an SHT; we use a similar tree construction procedure as
in the previous section, operating on the phrases found in the first
step, clustered based on visual pattern (Line 8-10).
## 4  DATA MODEL AND QUERY LANGUAGE
In the previous section, we described how we can extract SHTs for
each document in a collection as part of document ingestion. Here,
## Algorithm 1:template_gen(푡푝,퐷)
## 1푆퐻푇
## 퐷
## =(푉,퐸),푉=∅,퐸=∅
## 2퐺={}
## 3for푠
## 푖
## ∈푆
## 퐷
do
## 4if푝(푠
## 푖
## ) ∈푡푝.푝then
## 5푉=푉∪푠
## 푖
## ,퐺=퐺∪푡푝.푔(푝(푠
## 푖
## ))
## 6if퐺=∅or∃푖∈퐺,푖>1,(푖−1)∉퐺then
7Return{}
## 8for푣
## 푖
## ∈푉,푣
## 푗
## ∈푉do
## 9if푖푛푑(푣
## 푗
## ) ∈푡푠(푣
## 푖
## )and
## 푣
## 푘
## ∈푉,푖푛푑(푣
## 푘
## )>푖푛푑(푣
## 푖
## ),푠.푡.,푖푛푑(푣
## 푗
## ) ∈푡푠(푣
## 푘
## )then
## 10퐸=퐸∪(푣
## 푖
## ,푣
## 푗
## )
11Return푆퐻푇
## 퐷
we define the data model used byZenDBto represent the SHTs as
well as other system-specific information, along with user-defined
tables that we callDTables, short forDocument Tables.
## 4.1  Data Model Definition
In addition to traditional relational tables that we callbase tables,
ZenDBsupports three new types of tables that respectively (i)
represent the SHTs per document collection, (ii) let users specify
one or more structured relations over the documents, calledDTables,
to be used within queries; (iii) maintain system metadata associated
with the user-defined tables. We describe each one in turn.
4.1.1SHT Table.TheSHT table, shown in Figure 8-c, is a system-
defined and maintained table that represents the SHTs in a doc-
ument collection. Each row captures information about an SHT
Node, and is populated as described subsequently in Section 5. Its
main attributes are:
•doc_id,node_ididentify the node in a given document.
•namerepresents the header phrase푠corresponding to the node.
•granularityrepresents the depth of the node in the tree.
•context,summary,sizecorrespond to the entire sequence of
phrases in the text span, a short summary of the text span, and
the number of tokens in the text span.
•st_pageanded_page, listing the start and end pages for the
text span.
•child_idsandancestor_ids, the IDs for the children and
entire sequence of ancestors.
We note thatsummary,size,st/ed_page, andancestor_idscan
be derived from the other attributes, but we store them explicitly for
convenience. These attributes are all used during query processing.
4.1.2User-defined DTables.Users can use SQL to define DTables,
with those tables being used in subsequent queries (Figure 5). We
use a special keywordDESCRIPTIONto both designate the fact that
this is not an ordinary table, and also allowing natural language to
be provided that may be used in LLM prompts. To define such a
table, the user can say:
CREATE  TABLE[name] (...)  WITH  DESCRIPTION [description]
Here, the user provides a natural language description for the table.
Attributes may be provided during table creation in parentheses
(or omitted), and/or could be added afterwards, via the standard
approach to alter schemas:

node_iddoc_idgranularitynamest_pageed_pagecontextsummarysizechild_ids
## A11
## 1
Capital Improvement Projects (Design)
112context_1S(context_1)TC(context_1)[A0, A1, ...]
B11Marie Canyon Green Street
R1Public Works Commission Agenda Report
## 2
## 3
## 11
## 11
context_2S(context_2)
context_3S(context_3)
TC(context_2)
TC(context_3)
## [B1, B2, ...]
## []
c) SHT Table (Partial)
doc_id*nametypebegin_time
## 1
## NULLNULLNULL
table_nametable_nodetable_descriptiont_range
ProjectsRProjects table contains a set of projects in public agenda report...[3,3]
doc_id
## 1
2??ProjectsProjects table contains a set of projects in public agenda report...
text_span*
## TS1
node*
## B1
a) Projects (Partial)
## 1
## NULLNULLNULL
## TS2B2
## B21
PCH Median Improvements Project
312context_4S(context_4)TC(context_4)[]
doc_id*meeting_datesubject
## 1
## NULLNULL
text_span*
## TS1
node*
## R
b) Agenda Meeting (Partial)
1R[1,1]Agenda MeetingAgenda Meeting table describes the agenda meeting...
2??Agenda MeetingAgenda Meeting table describes the agenda meeting...
d) Table Catalog (Partial)
table_nameattr_description
Projectsname of project
type
## TEXT
TEXTProjectstype of project
attr_name
name
type
TEXTAgenda Meetingsubject of meetingsubject
e) Attribute Catalog (Partial)
table_text_span
## TS3
## ?
## TS4
## ?
ancestor_ids
## []
## [R]
## [A1, R]
## [A1,R]
multi_tuple
## False
## ?
## False
## ?
User-Defined Tables (* is system-defined attribute)
System-Defined Tables
Figure 8: Data Model: User-Defined Tables and System-Defined Tables.
ALTER  TABLE[name]
ADD[name] [type] WITH  DESCRIPTION [description], ... ;
Again, a natural language description for the attributes are provided
when they are added. As we will discuss in Section 5, when the
user creates a DTable,ZenDBpopulates them offline with rows
that correspond to tuples. Each tuple represents one entity that can
be found in a document. User defined attributes for these tuples
are populated withNULL, and are filled in on-demand during query
time, as shown in Figure 8a. Here, theProjectDTable contains
user-defined attributesname,type, andbegin-time.ZenDBalso
maintains three hidden system-defined attributes per DTable—the
document id, text span used to extract the tuple, and SHT nodes
used in the derivation. These attributes track how each tuple was
derived, to provide context when extracting tuple attributes later
on, and for debugging and provenance purposes. For instance,퐵1
corresponds to the “Marie Canyon Green Street” project tuple, and
the tuple’s text span may be the same as퐵1or a subset (Figure 8c).
The user-defined attributes represent the result of areadoper-
ation over each attribute. In addition, every expression implicitly
defines additional attributes in this table. For instance, if a query
evaluatesProjects.name = “Capital Improvement”directly us-
ing an LLM call, then the attribute[Projects.name|eq|Capital
Improvement]is instantiated and populated with the LLM response.
Note that we chose to represent these user-specified DTables as
regular tables as opposed to views or materialized views; but they
could also be represented as such.
4.1.3System-Defined Tables.In addition to the SHT table,ZenDB
maintains two system-defined tables:Table CatalogandAttribute
## Catalog
store metadata related to tables and attributes respectively
(Figure 8d,e). In addition to names and descriptions,Table Catalog
tracks the text span and SHT node(s) used to identify the contents
of the table (since a table may be a small portion of the document),
used to localize search when extracting tuples—thereby reducing
cost during query processing. The attributet_rangerefers to the
min/max granularities of the nodes used to extract tuples in the
table. For example, allProjecttuples extracted so far have gran-
ularity 3, thust_range = [3,3]; this is the setting where tuples
correspond to nodes (of some granularity) within the SHT. Finally,
to handle the special case where the table is extracted from a leaf
node in the SHT, i.e., there are multiple tuples corresponding to a
single node that has no finer granularity node below it, we mark
this by settingmulti_tupletoTrue. For instance, consider the
scenario when users want to create a table called “References” and
each tuple corresponds to a reference in a published paper.
## 4.2  Query Language
ZenDBcurrently supports a subset of SQL, corresponding to simple
non-nested queries on one or more DTables with optional aggrega-
tion, as represented by the following template:
SELECT[attr] | agg(attr)FROM[ST]+
WHERE[predicate]GROUP  BY[attr]
where[..]denotes a list of elements,attrrefers to an expression
over an attribute,STrefers to one or more DTables, andagg()in-
cludesSUM, COUNT, AVG, MAX, MIN
## 1
. A predicate has the form:
attr op operand, where the operators include>|≥|<|≤|=|LIKE|IN,
andoperandis one or more constants.LIKEis used for fuzzy match-
ing where either string similarity or semantic similarity could be
used
## 2
. We add a restriction that if multiple DTables are listed in the
FROMclause, then theWHEREclause includes a predicate specifying
that the tuples are equi-joined ondoc_id. We add this restriction
for now to only allow for within-document joins, but we plan to
relax this in future work.
Figure 9 shows a query where, for each document whose meeting
time is before “2023 October”, we count the “Capital Improvement”
projects starting after “2022-06-01”; here, we make use of the within-
document join across two tables.
The query semantics are defined as fully populating the user-
defined DTables with the LLM results of all attribute reads and
expressions, and then executing the SQL query as normal. We
follow these semantics because it allows for minor consistencies
during query evaluation.  Specifically, under an oracle LLM that
always returns complete and correct responses, the contents of
the attribute reads and expressions will always be consistent (e.g.,
typeis[’A’, ’B’], andtype = ’A’is true). However, modern
LLMs are imperfect and sensitive to the input prompt and con-
text formulation, so the extracted attribute values and expressions
## 1
Text attributes only supportCOUNT, date attributes only supportCOUNT, MAX, MIN.
## 2
InZenDBwe use Jaccard similarity with a 0.9 threshold by default.

over the attributes may be inconsistent (e.g., extractedtypeis’B’,
buttype=’A’is true). Better understanding and reconciling these
potential inconsistencies is outside the scope of this paper, and is
important future work.
## 5  TABLE POPULATION
We next describe how we can populate the system-defined tables
and attributes described above. Populating the SHT table is straight-
forward and therefore omitted; we will describe how thesummary
field is populated in Section 6.
Populating Tables Overview.When a user defines a new DTable
T, updatingAttribute Catalog(Figure 8e) andtable_name,
table_descrinTable Catalog(Figure 8d) is easy. However,ZenDB
must process the document collectionDto fill in the system-defined
attributes (SDAs) inTable CatalogandT, and populateTwith
tuples. WhileZenDBproactively identifies tuples forT, it doesn’t
populate any user-defined attributes until query time.
Consider a partitioning ofD=
## Ð
## D
## 푖
## ⊆D
## D
## 푖
, whereD
## 푖
is a set
of documents sharing the same template, as identified during SHT
construction. For eachD
## 푖
,ZenDBpicks a document퐷∈ D
## 푖
and
uses an LLM to populateTwith tuples, and fill in the SDAs.ZenDB
then uses a rule-based approach to extract tuples from the remain-
ing documents퐷
## ′
## ∈ D
## 푖
−{퐷}without invoking LLMs. We describe
the single document and multi-document extraction next.
Single Document Extraction.To populate SDAs for퐷for a given
DTableT, we first identify the node in the SHT for퐷that captures
all of the entities for theT; we call this thetable node. We then
identify nodes that correspond to tuples that lie underneath this
node. We use two prompts,table_oracleandtuple_oracleto
identify if a given node corresponds to a table or tuple respectively.
table_oracle: If the  following  text  describes [table_name], [table_descr],
return  true. Otherwise , return  false. [node_context ].
tuple_oracle: If the  following  text  describes  one [tuple_descr] in [
table_name], [table_descr], return  true. Otherwise , return  false. [
node_context ].
In these prompts,[]is a placeholder.[table_name],[table_descr],
and[tuple_descr]correspond to the table name and description,
and the tuple description inTable Catalog(e.g., Figure 8d).
## [node_context]
provides the entire text span corresponding to
the node fromSHT table(e.g., in Figure 8c).
To identify the table node,ZenDBwalks the SHT top-down and
submitstable_oracleto LLMs for each node. If the response for
all of a node푣’s children are true, then we add푣as a candidate table
node and stop descending into푣’s children. Finally,ZenDBfills in
the Least Common Ancestor (LCA) of the candidate table nodes as
table_nodeinTable Catalog.
Once thetable_nodeis found,ZenDBattempts to populateT
with tuples. Once again,ZenDBperforms a top-down traversal
starting fromtable_nodeand evaluatestuple_oracleon each
node. If a node푣evaluates to true, it means the node corresponds
to an entity. We insert a new tuple intoT, assign its node and text
span to that of푣’s, and stop traversing푣’s descendants. If no nodes
evaluate to true, it implies a leaf node contains multiple tuples
and so we flagmulti_tupleas true inTable Catalogwithout
populatingT. We handle this case separately in Section 6.
Multi-document Extraction.Repeated LLM calls for extracting
tuple boundaries for every document is too expensive, so we use a
rule-based approach to populate tuples (and other SDAs) from the
rest of the documents that share the same template.
Consider populatingtable_nodefor document퐷
## ′
## ∈ D
## 푖
## ,퐷
## ′
## ≠
퐷, where tuples from퐷were populated as described previously. Let
thetable_node(i.e., the finest granularity node below which all the
tuples are found) andt_range(i.e., tuple granularity range) of the
tableTin document퐷(that has already been populated) be푣
## 푡푛
and
[푙,푟], respectively. For퐷
## ′
, if there exists a node푣in its SHT such
that푣’s granularity matches that of푣
## 푡푛
and the textual similarity
between푣’s phrase and that of푣
## 푡푛
is greater than a threshold, then
we set푣to be the table node for퐷
## ′
; else if no such푣exists, the root
is set to be the table node.
Now, to populate tuples, suppose for the tuple range[푙,푟]in
퐷,푙=푟=푥. In this easy case, there is a well-defined granularity
in the SHT where tuples are found. Then, we add all nodes at
granularity푥from퐷
## ′
as candidate tuples toT(assuming there is
a non-zero number of them). If푙≠푟or if the SHT for퐷
## ′
has a
maximum height<푥, then we simply setmulti_tupleto true; in
this case, the granularity for tuples is ambiguous, and so we treat it
similar to the case where there may be multiple tuples at a given
node.
Multi-document Extraction Rules.In more detail, we define
the following two rules. For each node푣in an SHT, we use푣.푎푡푡푟
to denote any attribute푎푡푡푟belonging to푣in the SHT table (e.g.,
푣.푔푟푎푛푢푙푎푟푖푡푦). For the document퐷
## ′
## ∈ D
## 푖
, let푉
## 퐷
## ′
be the set of
nodes corresponding to퐷
## ′
in the SHT table, and퐷
## ′
## .table_node
be thetable_nodeofTin document퐷
## ′
in Table Catalog.
## Rule 1:∀푣
## 푖
## ∈푉
## 퐷
## ′
, if푣
## 푖
## .푔푟푎푛푢푙푎푟푖푡푦=푣
## 푡푛
.푔푟푎푛푢푙푎푟푖푡푦as well as
## 푆푖푚(푣
## 푖
## .푛푎푚푒,푣
## 푡푛
.푛푎푚푒>휃, then퐷
## ′
## .table_node=푣
## 푖
## .
## Else,퐷
## ′
## .table_node=푟표표푡.
If the rule is unsatisfied, we set thetable_nodeto be the root node
of SHT corresponding to퐷
## ′
. To populate the nodes corresponding
to tuples, we first populate the granularity range of tuplest_range.
## Rule 2: If∃푣
## 푗
## ∈퐷
## ′
## .table_node.child_ids,푙≤푣
## 푗
## .푔푟푎푛푢푙푎푟푖푡푦≤
푟, then퐷
## ′
## .t_range=[푙,푟]. Else,multi_tuple=푡푟푢푒.
If the granularities of tuples ofTin document퐷
## ′
are consis-
tent, i.e.,푙=푟in퐷
## ′
.t_range, then we create a set of nodes푉,
where for each푣∈푉,푣.푔푟푎푛푢푙푎푟푖푡푦=푙and퐷
## ′
## .table_node∈
푣.푎푛푐푒푠푡표푟_푖푑푠.푉is further converted to a set of tuples whose
푡푒푥푡_푠푝푎푛=푣.푐표푛푡푒푥푡and푛표푑푒푠={푣}. These tuples are inserted
into the tableT. If Rule 2 is violated, we setmulti_tupleas true
to denote that we do not have a one-to-one mapping between the
set of nodes and tuples when populating the table for퐷
## ′
## . Note
that doing so might introduce false positives instead of false neg-
atives. False positives are permissive since they will not lose the
context of where the answers may be present, and in Section 6 we
will discuss how to reduce false positives during query execution.
Whenmulti_tuplein퐷is true, we don’t populatet_rangebut set
multi_tupleas true for퐷
## ′
. Overall, when the number of distinct
templates (i.e.,|D
## 푖
|) in documentsDis small, the cost incurred by
LLMs to populate the SDAs is minimal, since we only invoke LLMs
on a single document for each cluster.
## 6  QUERY ENGINE
We discuss howZenDBgenerates a query plan for a given query푄
in Section 6.1, and then describe our physical operator implemen-
tations that leverage SHTs in Section 6.2.

SELECT Agenda_Meeting.doc_id, COUNT(Projects.name)
FROM Projects, Agenda_Meeting
WHERE Projects.type = ‘Capital Improvement’
AND Projects.begin_time > ‘2022-06-01’
AND Agenda_Meeting.meeting_time < ‘2023 October’
AND Projects.doc_id = Agenda_Meeting.doc_id
GROUP BY Agenda_Meeting.doc_id
Figure 9: A Query on Civic Agenda Documents.
Figure 10: A Query Plan for the Query in Figure 9.
## 6.1  Logical Query Plan
Unlike traditional settings where I/O and computation costs domi-
nate, here, LLM invocations add to monetary cost
## 3
and/or latency,
and thus must be minimized if possible. Keeping this guideline in
mind, when generating a logical query plan for a given query푄,
ZenDBfirst parses the SQL query into a parse tree of relational
operators. Subsequently, predicates are pushed down to reduce
intermediate sizes and thereby downstream LLM invocations—but
also taking into account the fact that predicate evaluations that
rely on LLMs can be expensive.ZenDBrelies on the standard ap-
proach from prior work [32] for expensive predicate reordering
that takes into account both the selectivity and cost.  Specifically,
we define a metric푓(표)for each selection operator표. Let푠
## 표
be
the selectivity of표, computed as푠
## 표
## =
## |푇
## 푠
## |
## |푇
## 푐
## |
, where푇
## 푐
## (푇
## 푠
) are tu-
ples that are processed (satisfy) the predicate associated with표.
## Let푒
## 표
be the average cost for evaluating a tuple using operator
표, which is estimated adaptively during query execution as more
tuples are processed by표. The goodness of a selection operator
표is then defined as푓
## 표
## =푒
## 표
## ×푠
## 표
. Intuitively, if an operator표has
lower cost푒
## 표
and selectivity푐
## 표
,표is preferred to be executed early.
ZenDBwill sort the set of selection operators on the same table
in the increasing order of푓(표).  Projections on the other hand, are
pulled up, to avoid having to populate attributes through LLM calls
for tuples that may get discarded. Until a selection or projection
is encountered that requires a specific attribute for a tuple, that
attribute stays uninterpreted, and therefore NULL.
From a join order standpoint,ZenDBadopts a greedy algorithm
to generate a left-deep tree, in an approach akin to standard rela-
tional query optimization techniques. Here, instead of optimizing
for reducing the sizes of intermediate results, we focus on reducing
the LLM invocation cost. Let퐸(푇)be the cost (in terms of dollars
or latency) for evaluating all of the predicates in푄corresponding
only to table푇on all of the tuples of푇.ZenDBranks the tables
in푄as푇
## 1
## ,푇
## 2
, ...based on their퐸(푇
## 푖
)in increasing order, form-
ing a left deep tree with푇
## 1
as the driving table, followed by푇
## 2
## 3
This is common for several commercial LLMs like OpenAI, Claude-3 [7], Google
## Gemini [3].
## Algorithm 2:푡푟푒푒_푒푣푎푙푢푎푡푒(푆퐻푇,푡푢푝푙푒,푒)
## 1퐶푢푟푟푒푛푡푁표푑푒푠={푡푢푝푙푒.푛표푑푒}
## 2퐴푛푠=∅
## 3푇=푔푒푡푇푟푒푒(푆퐻푇,푛표푑푒)
4/*Refine candidate nodes*/
## 5while푠푡표푝_푐표푛푑푖푡푖표푛(푇)=퐹푎푙푠푒do
## 6퐶푁푠=∅
## 7for푛∈퐶푢푟푟푒푛푡푁표푑푒푠do
## 8if푠푒푎푟푐ℎ_표푟푎푐푙푒(푛,푒)= Truethen
## 9퐶푁푠=퐶푁푠∪푛
## 10퐶푢푟푟푒푛푡푁표푑푒푠=퐶푁푠.푐ℎ푖푙푑푠_푖푑
11ife.type = predicatethen
12/*Evaluating A Predicate*/
## 13for푛표푑푒∈퐶푁푠do
## 14if푒푣푎푙푢푎푡푒_표푟푎푐푙푒(푛표푑푒.푠푢푚푚푎푟푦,푒)=푇푟푢푒then
## 15퐴푛푠=퐴푛푠∪푛표푑푒
16Return퐴푛푠
17ife.type = attributethen
18/*Extracting Attribute Values*/
## 19for푛표푑푒∈퐶푁푠do
## 20퐴푛푠=퐴푛푠∪푒푥푡푟푎푐푡_표푟푎푐푙푒(푛표푑푒.푠푢푚푚푎푟푦,푒)
21Return퐴푛푠
to form푇
## 1
⊲⊳푇2, with the remaining tables being selected based
on퐸(.). Whenmulti_tupleis false, implying that in table푇, we
have pre-populated potential tuples, and therefore have a more
precise estimate,퐸(푇)=|푇|×푒is estimated at query time, where
|푇|is the number of tuples in푇,푒denotes the average cost of eval-
uating a single tuple. Initially,퐸(푇)is set to be|푇|to prioritize
evaluating the table with the smaller number of tuples, and푒will
be estimated adaptively as more tuples are processed during query
execution. One logical plan for the query in Figure 9 is shown in
Figure 10, whereagenda_meetingonly has one tuple compared to
theProjectstable with more than 40 tuples, and thus is evaluated
first. The estimation of퐸(푇)whenmulti_tupleis true will be
described in Section 6.2.
## 6.2  Physical Query Plan
During query execution, each tuple in the user-defined DTables
has attribute values that begin asNULLas in Figure 8a, but some at-
tributes will get populated through selections or projections. When
multi_tupleis true,ZenDBleverages LLMs to create a set of tu-
ples satisfying the corresponding predicates with their attributes
listed in the projections to be computed, as will discussed shortly.
We now discuss our implementations of various operators.
Scan.As part of our scan operator,ZenDBexecutes the query
document by document (which explains the restriction of join on
doc_idin Section 4.2). This operator first retrieves the tuples in
the first document as a batch, followed by tuples in the second
document; thus only one SHT is processed at a time.
Selections and Projections.Consider a predicate푝푟푒푑or a projec-
tion푝푟표푗on table푇; a similar procedure is followed in either case.
Saymulti_tupleis false, so each row in푇corresponds to a single
potential tuple.ZenDBthen calls a function푒푣푎푙푢푎푡푒(푆퐻푇,푡푢푝푙푒,푒),

listed in Algorithm 2, with푒set to푝푟푒푑(respectively,푝푟표푗) to eval-
uate whether푡푢푝푙푒satisfies푝푟푒푑, returning it if so (respectively,
the value of the attribute in푝푟표푗). This function implements a tree
search on the SHTs, leveraging summaries for each node, as defined
in Section 4.1. We next describe how we populate this푠푢푚푚푎푟푦
per node in the SHT table (Figure 8c).
Summary Creation.Given the SHT for a document퐷and the ex-
pression푒,푆(푣), the summary for a node푣, comprises the following:
(1) The phrase(s) corresponding to both푣and its ancestors. (2) An
extractive summary of the text span of푣, which is a set of impor-
tant sentences determined using standard (non-LLM) NLP tools
like NLTK [10]. (3) The top-1 sentence the text span of푣with the
highest semantic similarity (e.g., cosine similarity) with푒.
Parts (1) and (2) are prepared offline when the SHT is built. Part
(3) is added during query processing. Including phrases (i.e., head-
ers) of ancestors in (1) often helps enhance accuracy by including
additional background for interpreting푣’s text span. For example,
in Figure 1, the summary of node퐵2contains the header phrase
of its parent, “Capital Improvement Projects (Design)”, helping us
identify푣as a candidate node when evaluating a predicate such as
type = Capital Improvement.
Tree Search Algorithm.Given a document퐷with its푆퐻푇, a tuple
node푛표푑푒, an expression푒(either a predicate or a projection), our
Algorithm 2, first identifies a sub-tree푇in푆퐻푇with푛표푑푒as the
root (Line 4), searches푇top-down. For each node푛in one layer, it
calls푠푒푎푟푐ℎ_표푟푎푐푙푒(푛,푒)to check whether푛’s summary contains
the right information to evaluate expression푒. It then adds all the
nodes that pass푠푒푎푟푐ℎ_표푟푎푐푙푒into a candidate set퐶푁푠(Line 6-12),
and recursively searches their children until a stopping condition
is met (Line 6). This condition is (1) the leaf node is reached, (2) the
number of tokens in the summary of the node is larger than that of
its context (i.e., text span).
search_oracle(node , e): If the  following  text  contains  the  information
that  describes [e.descr], return  True; otherwise , return  False. The
context  is [node.summary ].
Example: [e.descr] ='the  type of  project  is  Capital  Improvement'
For each candidate node푛∈퐶푁푠, if the expression푒is a predicate,
then a call to an LLM with prompt푒푣푎푙푢푎푡푒_표푟푎푐푙푒(푛표푑푒.푠푢푚푚푎푟푦,푒)
is issued to evaluate if the summary of node satisfies the predi-
cate. This step stops early when there exists one node that passes
푒푣푎푙푢푎푡푒_표푟푎푐푙푒(푟푐,푒)(Line 11-17). When푒is a projected attribute,
푒푥푡푟푎푐푡_표푟푎푐푙푒(푛표푑푒.푠푢푚푚푎푟푦,푒)is instead used to extract the value
of the projected attribute (Line 18-22).
evaluate_oracle(context , e):   Return  True if   [e.descr] based  on the
following  context [context ]. Otherwise , return  False.
Example: [e.descr] ='type of  project  is  Capital  Improvement'
extract_oracle(context , e): Return [e.descr]   based  on the  following
context [context ].
Example: [e.descr] ='name of  project'
Each selection operator표returns the set of tuples in table푇
satisfying the predicate associated with표to downstream opera-
tors.   We handle the case wheremulti_tupleis true for table푇in
## Section 6.3.
Even though executing a tree search procedure by exposing node
summaries to LLMs incurs additional cost, it is minimal in prac-
tice since the height of the tree is often small (thus, the number
of iterations is small), and the size of the summary is small and
controllable. In Section 7 we show that the benefit introduced by
summaries, which achieves better accuracy and lower cost, domi-
nates the additional cost.
Other Operators.We use nested loop as our join algorithm. As
mentioned earlier, even if we consider latency to be the primary
optimization criterion, the evaluation of predicates and projections
through LLM invocations would dominate overall latency, and
the number of intermediate tuples to be processed during query
execution is often not a large number. If we further treat monetary
cost as the primary criterion, then joins are effectively free. Thus,
a simple nested loop join suffices. Similarly, other operators like
aggregation and group-by use simple relational variants.
Provenance of Query Answers.ZenDBmaintains the prove-
nance in the form of the corresponding text span(s) for the returned
query answers in a manner analogous to classical relational prove-
nance [30]. During query processing, we keep track of the sequence
of text spans consulted to populate attributes or verify predicates,
as an additional metadata attribute, per tuple. These text spans are
combined into an array during joins. While we could apply the same
idea to aggregations and capture the provenance of contributing
tuples into an array, this representation is unwieldy. Determining
how best to show all of this provenance to end-users to ensure trust
in query answers is an important topic for future work.
6.3  Operators for the Multiple Tuple Case
Whenmulti_tupleis true for tableT, there are no tuples inTafter
population in Section 5, and the context oftable_nodemay contain
multiple tuples. Let푝푟푒푑(푇)and푝푟표푗(푇)be a set of predicates and
projected attributes associated with tableTin a given query푄.
In this case,ZenDBsearches the text span corresponding to the
table_nodeofT, and creates a set of tuples satisfying푝푟푒푑(푇)
with푝푟표푗(푇)being populated by LLMs.
Whentable_nodeis a leaf node in its SHT,ZenDBsubmits the
promptmulti_tuple_oracle (table_node,푝푟푒푑(푇),푝푟표푗(푇))to
LLMs to extract the projected values for the tuples that satisfies the
given predicate푝푟푒푑(푇).
multi_tuple_oracle(node ,pred(T),proj(T)): The  following  text  describes
one or more [tuple_descr ]. For  each [tuple_descr], if pred(T), then
return [proj(T)] based  on the  following  context [node.context ].
## Example:
## [tuple_descr] ='paper'
[predT] ='publication  year is  greater  than  2009  and  conference  is VLDB'
[proj(T)] ='name of paper , authors  of  paper'
As an example, consider a publication document퐷, where users
want to create a table calledReferencewith the schema as {name,
year}, whose text span corresponds to the references section in a
paper. Assume that in the SHT of퐷, the references section is a leaf
node. In this case,ZenDBwill not further parse the reference section
into individual references, but will callmulti_tuple_oracle()to
extract the paper name and authors per reference from VLDB whose
publication year is later than 2009, directly over the references
section.
Whentable_nodeis not a leaf node in its SHT of document
퐷, let퐷
## ′
be a document sharing the same template with퐷and
populating its system-defined attributes via퐷in Section 5. Let
푠푡표푝_푔푟푎푛푢푙푎푟푖푡푦be the granularity for stopping searching in Al-
gorithm 3, and푠푡표푝_푔푟푎푛푢푙푎푟푖푡푦=퐷.푡푢푝푙푒_푟푎푛푔푒.푙, i.e., the small-
est granularity of tuples in퐷. Note that this may introduce false

## Algorithm 3:푡푟푒푒_푒푣푎푙푢푎푡푒_푚푢푙푡푖_푡푢푝푙푒
## Input:푆퐻푇,푡푎푏푙푒_푛표푑푒,푝푟푒푑(푇),푝푟표푗(푇),푠푡표푝_푔푟푎푛푢푙푎푟푖푡푦
## 1퐶푢푟푟푒푛푡푁표푑푒푠={푡푎푏푙푒_푛표푑푒}
## 2푇푢푝푙푒푠=∅
## 3푔푟푎푛푢푙푎푟푖푡푦=푡푎푏푙푒_푛표푑푒.푔푟푎푛푢푙푎푟푖푡푦
## 4푇=푔푒푡푇푟푒푒(푆퐻푇,푡푎푏푙푒_푛표푑푒)
5/*Refine candidate nodes*/
## 6while푔푟푎푛푢푙푎푟푖푡푦≤푠푡표푝_푔푟푎푛푢푙푎푟푖푡푦do
## 7퐶푁푠=∅
## 8for푛∈퐶푢푟푟푒푛푡푁표푑푒푠do
## 9if푠푒푎푟푐ℎ_표푟푎푐푙푒(푛,푒)= Truethen
## 10퐶푁푠=퐶푁푠∪푛
## 11푔푟푎푛푢푙푎푟푖푡푦=푔푟푎푛푢푙푎푟푖푡푦+1
## 12퐶푢푟푟푒푛푡푁표푑푒푠=퐶푁푠.푐ℎ푖푙푑푠_푖푑
## 13퐴푛푠=∅
## 14for푛∈퐶푁푠do
## 15퐴푛푠=퐴푛푠∪푚푢푙푡푖_푡푢푝푙푒_표푟푎푐푙푒(푡,푝푟푒푑(푇),푝푟표푗(푇))
16Return퐴푛푠
Datasets# of DocumentsAvg # PagesAvg # Tokens
## Publication10011.513230
## Civic Agenda418.73185
## Notice807.13719
Table 1:Characteristics of Datasets.
positives (one node might correspond to multiple tuples) but would
avoid false negatives (there will not exist nodes that correspond to
portions of a tuple).ZenDBexecutestree_evaluate_multi_tuple
in Algorithm 3.ZenDBstarts searching the subtree of SHT with
table_nodeas the root (Line 4). We use the same summary-based
search as intree_evaluatein Algorithm 2 to refine the nodes
that are related to the given query top-down layer by layer, and
stop  the  search  when  the  granularity  of  current  layer  exceeds
푠푡표푝_푔푟푎푛푢푙푎푟푖푡푦(Line 6-12). For each node푛∈퐶푁푠that are
related to the query and might contain multiple tuples, we call
multi_tuple_oracleto extract the corresponding tuples (Line
## 13-15).
## 7  EVALUATION
In this section, we evaluateZenDBover three real document col-
lections on accuracy, latency, and cost.
## 7.1  Methodology
7.1.1    Data & Query Sets.We collected three real-world datasets
(i.e., document collections): scientific publications, civic agenda
reports, and notice of violations; details are displayed in Table 1.
Scientific Publications.This dataset was collected from a system-
atic review study that examined research questions in the field of
personal data management at UC Irvine [11]. The study analyzed
over 500 publications; we randomly selected 100 papers for our
dataset. The study explored 20 research questions with human-
labeled answers for all of the publications.
Civic Agenda Reports.This dataset, from our collaborators at Big
Local News, comprises 41 civic agenda reports from 2022 to 2024 in
the City of Malibu [14]. Each report details a series of government
projects, including their status, updates, decisions, and timelines
for beginning, ending, and expected construction.
Notice of Violations.This dataset, also from Big Local News, of 80
documents describe notices of violations issued by the US Dept. of
Transportation from 2023 to 2024 [12]. Each document concerns
potential violations detailed by the Hazardous Materials Safety
Administration, including detailed violation orders and descriptions,
penalty decisions, and proposed compliance orders.
Query Workload.For each dataset, we devise a query workload
comprising 9 SQL queries, informed by the needs of our collabora-
tors. These 9 queries are divided into groups of three, QG1, QG2,
and QG3, varying in the number of predicates, from one to three
respectively.  To generate these queries, we first define tables along
with a set of attributes per dataset. Then we randomly select푖at-
tributes to create푖predicates for the queries in group QGi, and
inSELECT, we additionally include one attribute that is not used
in the predicates, as well asdoc_id. When we end up sampling
attributes across multiple relations, we list both in theFROMclause,
and additionally add an equijoin condition ondoc_id. So, over-
all, our queries include selections, projections, and joins. We omit
aggregations in our workload since we use relational versions for
those operators evaluated after the corresponding attribute values
are extracted; and thus the performance on such queries would be
similar to that on the queries without them.
7.1.2    Strategies Compared and Evaluation Metrics.We compare
ZenDBwith four baselines, GPT_single, GPT_merge, RAG_seq, and
RAG_tree. The first two operate on an entire document at a time.
GPT_single uses a separate LLM call per predicate and projection
by constructing a corresponding prompt, appending the entire doc-
ument as context. GPT_merge combines all of the predicates and
projections into a single LLM call alongside the entire document.
RAG_seq and RAG_tree refer to RAG-based techniques in two vari-
ants implemented by LlamaIndex [9], a state-of-the-art open-source
RAG framework: sequential chunking and tree-style chunking, re-
spectively. In RAG_seq, we set the chunk size to 128 tokens and
selected top-푘chunks, where푘=max(1,5%×doc_size/128). That
is, we retrieve at least one chunk, but no more than 5% of the of
the document. RAG_tree constructs a hierarchical tree from the
document without leveraging semantic structure. This tree is con-
structed by first chunking the leaves at a fixed granularity. Nodes
higher up in the hierarchy are formed by recursively summarizing
the nodes below. Subsequently, a path from the root to leaf is re-
trieved, instead of just one leaf. GPT-4-32k is used to evaluate the
queries for all strategies.
We use precision and recall to measure the quality of query
answers. Given a query푄, let푇_푡푟푢푡ℎ(푄)and푇_푝푟푒(푄)be the
set of tuples in the ground truth vs. predicted by an approach,
respectively. Precision is measured as
## |푇_푡푟푢푡ℎ(푄)∩푇_푝푟푒(푄)|
## |푇_푝푟푒(푄)|
, and
recall is
## |푇_푡푟푢푡ℎ(푄)∩푇_푝푟푒(푄)|
## |푇_푡푟푢푡ℎ(푄)|
. We count the number of input and
output tokens to measure the cost of LLM invocations [6]. Finally,
we measure the latency of query execution by taking three runs
and reporting the average.
## 7.2  Experimental Results
Experiment 1:ZenDBvs. GPT-only Strategies.We first com-
pareZenDBwith GPT_single and GPT_merge, both operating on

PrecisionRecallCost ($) / Tokens (×1000)Latency(Seconds)
StrategiesPUBCIVICNOTICEPUBCIVICNOTICEPUBCIVICNOTICEPUBCIVICNOTICE
GPT_single0.740.450.710.380.450.770.98 / 16.20.33 / 5.40.3 / 5.314.615.36.1
GPT_merge0.630.340.660.40.450.720.8 / 13.20.2 / 3.20.2 / 3.712.97.45
RAG_seq0.510.120.360.380.130.380.02 / 0.40.02 / 0.290.01 / 0.183.765.11.3
RAG_tree0.510.20.20.380.040.170.07 / 1.20.04 / 0.660.02 / 0.35108.91.3
ZenDB0.720.730.730.530.840.740.03 / 0.560.03 / 0.530.02 / 0.254.871.7
Table 2:Average Precision, Recall, Cost / # of Tokens and Latency of Strategies Per Query, Per Document, in Publication (PUB), Civic Agenda
(CIVIC), Notice of Violation (NOTICE) Datasets. (GPT-4-32k is Used.)
PrecisionRecallCost ($) / Tokens (×1000)Latency(Seconds)
StrategiesQG1QG2QG3AvgQG1QG2QG3AvgQG1QG2QG3AvgQG1QG2QG3Avg
GPT_single0.94  0.66  0.620.740.650.160.320.380.8 / 13.21 / 16.61.1 / 18.90.98 / 16.212.814.116.914.6
GPT_merge0.940.410.630.630.650.130.410.40.8 / 13.20.8 / 13.20.8 / 13.20.8 / 13.212.812.913.112.9
RAG_seq0.730.40.390.510.60.230.310.380.01 / 0.23   0.02 / 0.38  0.03 / 0.590.02 / 0.42.7   3.9   4.53.76
RAG_tree0.790.330.420.510.680.190.270.380.05 / 0.820.08 / 1.30.1 / 1.60.07 / 1.28.410.411.210
ZenDB0.93  0.64   0.60.720.7   0.54  0.340.530.02 / 0.41  0.03 / 0.56  0.04 / 0.710.03 / 0.563.9   5.2   5.44.8
Table 3:Average Precision, Recall, Cost / # of Tokens and Latency of Strategies Per Query, Per Document, in Publication Dataset. (GPT-4-32k is
## Used.)
PrecisionRecallCost ($) / Tokens (×1000)Latency(Seconds)
StrategiesQG1QG2QG3AvgQG1QG2QG3AvgQG1QG2QG3AvgQG1QG2QG3Avg
GPT_single0.640.360.360.450.730.370.240.450.2 / 3.20.33 / 5.40.47 / 7.60.33 / 5.47.515.323.115.3
GPT_merge0.640.220.160.340.730.320.290.450.2 / 3.20.2 / 3.20.2 / 3.20.2 / 3.27.36.97.57.4
RAG_seq0.250.1100.120.360.0400.130.01 / 0.14  0.02 / 0.3  0.03 / 0.430.02 / 0.293.3   5.2   6.95.1
RAG_tree0.360.2300.20.120.0100.040.03 / 0.490.04 / 0.60.05 / 0.880.04 / 0.665.98.912.38.9
ZenDB0.89  0.72  0.610.730.86  0.79  0.830.840.02 / 0.430.04 / 0.590.04 / 0.680.03 / 0.535.17.28.87
Table 4:Average Precision, Recall, Cost / # of Tokens and Latency of Strategies Per Query, Per Document, in Civic Dataset. (GPT-4-32k is Used.)
PrecisionRecallCost ($) / Tokens (×1000)Latency(Seconds)
StrategiesQG1QG2QG3AvgQG1QG2QG3AvgQG1QG2QG3AvgQG1QG2QG3Avg
GPT_single0.71  0.65  0.760.710.9   0.67   0.750.770.2 / 3.70.31 / 5.20.43 / 7.10.3 / 5.34.96.27.36.1
GPT_merge0.70.560.620.660.80.60.770.720.2 / 3.70.2 / 3.70.2 / 3.70.2 / 3.74.855.15
RAG_seq0.610.310.170.360.670.220.260.380.01 / 0.12  0.01 / 0.19  0.01 / 0.230.01 / 0.180.9   1.3   1.71.3
RAG_tree0.580.360.240.20.390.50.170.170.02 / 0.250.02 / 0.380.03 / 0.410.02 / 0.352.12.73.12.6
ZenDB0.79  0.67  0.720.730.870.620.730.740.01 / 0.19  0.02 / 0.26   0.02 / 0.30.02 / 0.251.41.72.11.7
Table 5:Average Precision, Recall, Cost / # of Tokens and Latency of Strategies Per Query, Per Document, in Notice Violation Dataset.
(GPT-4-32k is Used.)
an entire document at a time. Table 2 reports our metrics of interest
on the three datasets, while Table 3, Table 4, and Table 5 provide
a breakdown per dataset. We first note thatZenDBachieves com-
parable precision and recall to GPT_single on the publication and
notice datasets. Notably,ZenDBsurpasses GPT_single in the civic
dataset,improving precision by 28% and recall by 39%, due to
this dataset’s complex semantic structure, which poses challenges
for GPT_single in generating high-quality responses.ZenDB’s ap-
proach of querying based on SHTs, focuses LLM attention on por-
tions of documents at a time, thereby enhancing performance. We
also observe that combining multiple predicates into a single prompt
makes it more difficult for the LLM to provide the correct answer,
resulting in performance degradation. On the cost and latency
front,ZenDBsignificantly reduces both relative to GPT_single and
GPT_merge. Specifically,ZenDBachievescost savings of approx-
imately 29×, 10×, and 4×for the publication, civic, and notice
datasets respectively. It’s noteworthy thatZenDB’s cost savings
increase with document size, as the number of tokens it uses is
somewhat independent of document size. Instead, it relies on the
size of the summary and the number of levels of the SHTs explored
during execution, which are controllable factors. Accordingly, we
observe varying levels of latency savings withZenDB,up to a 4×
reductionacross datasets.
Experiment 2:ZenDBvs. RAG-only Strategies.When com-
pared with RAG_seq and RAG_tree, we observe that RAG_seq
achieves significant cost and latency savings compared to GPT-only
strategies. However, relying solely on retrieving physical chunks
based on embedding similarity as in RAG, fails to accurately iden-
tify the appropriate text spans related to the queries, leading to
a substantial degradation in precision and recall. WhileZenDB
incurs a slightly higher cost, it offers substantial advantages over
RAG-based approaches thanks to the use of semantic structure,
withincreases in precision by up to 61% and recall by up to
80%. RAG_tree generally shows slight improvements in precision
and recall over RAG_seq, but it similarly falls short ofZenDBfor
a similar reason. Its use of tree-style physical chunking often fails
to accurately identify the appropriate text spans. Moreover, the

PublicationCivic AgendaViolation
## Datasets
## 0
## 0.2
## 0.4
## 0.6
## 0.8
## 1
## Average Precision
ZenDB
no-ES
no-node-name
no-DS
## (a)  Average Precision
PublicationCivic AgendaViolation
## Datasets
## 0
## 0.2
## 0.4
## 0.6
## 0.8
## 1
## Average Recall
ZenDB
no-ES
no-node-name
no-DS
## (b)  Average Recall
PublicationCivic AgendaViolation
## Datasets
## 0
## 0.1
## 0.2
## 0.3
## 0.4
## 0.5
## 0.6
## 0.7
Average # of Tokens (x1000)
ZenDB
no-ES
no-node-name
no-DS
(c)  Average # of Tokens (×1000)
PublicationCivic AgendaViolation
## Datasets
## 0
## 1
## 2
## 3
## 4
## 5
## 6
## 7
## 8
## 9
Average Latency (Seconds)
ZenDB
no-ES
no-node-name
no-DS
(d)  Average Latency (Seconds)
Figure 11:The Effect of Summary Construction to Performance ofZenDBin Real Datasets.
Datasets (# of Docs)# of Nodes# of LayersCost ($) /TokensLatency
## Publication (100)13.42.80.05 / 1.8k6min
## Civic (41)32.12.90.01 / 0.36k1min
## Violation (80)8.92.20.01 / 0.32k1min
Table 6:SHT Construction. (GPT-4 is Used.)
DatasetsCost ($) / TokensFPFNLatency
Publication (100)0.048 / 95.4k007 min
Civic (41)0.005 / 10.1k0.0803 min
Violation (80)0.005 / 8.9k0.0402 min
Table 7:Table Population. (GPT-3.5-Turbo is Used.)
PublicationCivic AgendaViolation
## 0
## 0.2
## 0.4
## 0.6
## 0.8
## 1
## Average Precision
ZenDB
ZenDB-light
(a)Precision
PublicationCivic AgendaViolation
## 0
## 0.2
## 0.4
## 0.6
## 0.8
## 1
## Average Recall
ZenDB
ZenDB-light
(b)Recall
Figure 12:ZenDBvs.ZenDB-light: Precision and Recall.
exhaustive summary construction and usage in RAG_tree results
in higher cost and latency compared toZenDB.
Experiment 3: Data Preparation.Next, we examine two phases
withinZenDBhappening prior to queries, SHT construction and
table population, and compare it to the costs of online queries.
Experiment 3.1: SHT Construction.We present the average number
of nodes and layers per SHT, and thetotalcost, number of tokens,
and latency on three datasets, in Table 6. SHT construction is an
offline process, making latency at the level of minutes not problem-
atic. The cost is affected by the number of distinct templates in the
datasets.ZenDBuses LLMs to verify headers for SHT generation
for one document per template, with the remaining SHTs created
through visual pattern matching. The cost is further reduced by
sampling the phrase clusters. In the publication dataset, the publica-
tions originate from 6 conferences, whereas the other two datasets
follow a consistent template. Therefore, the publication dataset has
a higher cost than the others, although all costs are minimal.
Experiment 3.2: Table Population.When users define a DTable,ZenDB
populates the system-defined attributes using LLM-based and rule-
based  approaches.  Table  7  presents  thetotalcost  and  number
of tokens (we use GPT-3.5-Turbo)
## 4
, with additional latency and
## 4
When the context size of a node exceeds the token limit (e.g., the root node in
publication dataset), we use NLTK [10] to summarize the context and adjust the
summary size to approximately match the token limit of a prompt.
PublicationCivic AgendaViolation
## 0
## 1
## 2
## 3
## 4
## 5
## 6
## 7
## 8
## 9
\# of Queries
## 10
## 3
ZenDB-light
Figure 13:# of Queries on 1 Doc-
ument by 1 $.
PublicationCivic AgendaViolation
## 0
## 1
## 2
## 3
## 4
## 5
## 6
## 7
## 8
## Average Lantecy
ZenDB
ZenDB-light
Figure 14:ZenDBVSZenDB-
light: Latency.
quality results. In particular, to show the quality of table popula-
tion, let푡푠
## 푔
## (푒)and푡푠
## 푝
(푒)be the text span of an entity푒(a table
or a tuple) in the ground truth and predicted byZenDB, respec-
tively. We label푡푠
## 푔
## (푒) ⊂푡푠
## 푝
(푒)as a false positive (FP), indicat-
ing that the predicted text span contains the true text span but
is larger, which is acceptable since it doesn’t miss the correct an-
swers will be refined by the tree-search algorithm. In constrast,
## (푡푠
## 푝
## (푒) ⊂푡푠
## 푔
## (푒))∨(푡푠
## 푝
## (푒)∩푡푠
## 푔
(푒))=∅)is considered a false neg-
ative (FN) because the predicted text span does not encompass all
the true text spans, potentially resulting in missed answers. Notably,
ZenDBdemonstrates a low FP rate in the violation and civic agenda
datasets, showcasing the effectiveness of the approach. The cost
incurred in this step is minimal, thanks to the use of the affordable
LLM GPT-3.5-Turbo (around 100x cheaper than GPT-4).
End-to-end cost comparison:ZenDBvs. Others.AlthoughZenDB
incurs costs to construct SHTs and populate tables before a query
arrives, these costs are minimal, totaling 0.1, 0.015, and 0.015 dollars
for the publication, civic agenda, and notice of violations datasets,
respectively.Even if we ran just a single query subsequently, we
would have lower end-to-end costsforZenDBcompared to GPT-
single and GPT-merge, with the loading costs getting amortized
across queries.
Experiment 4: The Effect of Summary Construction inZenDB.
We examine the effect of summary construction onZenDBper-
formance in Figure 11. Recall that in Section 6.2, the summary of
each node푣in a SHT consists of three components: an extractive
summary (ES), the phrases of푣and its ancestors (node-name), and
the top-1 sentence related to a given query predicate or projection
within the text span of푣(DS, i.e., Dynamic Summary). We explored
three variations ofZenDBby removing one component at a time
from the summary: no-ES, no-node-name, and no-DS (e.g., no-ES
refers to the strategy that excludes the extractive summary from
the summary of the node). We observe that the extractive summary
impacts the quality of query answers (i.e., precision and recall)
the least, while both dynamic summaries and node names (i.e.,

the header phrases) affect performance more significantly. Node
names provide useful metadata that adds more context for the LLM,
helping refine the search space. The dynamic summary plays a
critical role in summary construction by not only identifying the
relevant nodes but also retrieving the text span most related to the
given query. We also note that storing node names has a minimal
impact on cost and latency due to their compact size. In contrast,
both extractive and dynamic summaries have a greater size, though
they still represent a relatively small portion of the overall cost and
latency.
Experiment 5:ZenDBDriven by A Cheaper LLM: GPT-3.5-
Turbo.We next study the impact of replacing the more expensive
LLM used inZenDB, GPT-4-32k, with an almost 100×cheaper LLM,
GPT-3.5-turbo, when evaluating queries. We denote this version as
ZenDB-light. In Figure 12,ZenDB-light exhibits approximately
a 7% decrease in precision and a 3% decrease in recall compared
toZenDB, at 100×lower cost. This demonstrates that by refining
the text span thatZenDBuses for evaluating queries, as opposed
to the entire complex document,ZenDBis able to provide a much
simpler and more precise context for LLMs to evaluate. This makes
it easier for less-advanced but cheaper models like GPT-3.5-turbo
to not just process the entire text span, but also answer the query
accurately. We report the average number of SQL queries that can be
executed on a single document by spending 1 dollar usingZenDB-
light, in Figure 13.ZenDB-light can run approximately 3.5k, 3.7k,
and 8k SQL queries with 2 predicates and one projection on average
in one document within budget for the publication, civic agenda
reports, and notices of violations, respectively, demonstrating the
practicality ofZenDB-light.
## 8  RELATED WORK
We now survey related work on querying unstructured data.
Text-to-Table Extraction.One approach to querying unstructured
data is by simply extracting unstructured data into tables, follow-
ing which they are queried as usual. This approach is followed
by Google DocumentAI [4] and Azure Document Intelligence [5],
as well as approaches such as text-to-table [61]. Using an LLM to
populate entire tables upfront can be expensive and error-prone
on large and complex document collections as in our case. Evap-
orate [18] uses an LLM to infer schema, and then populate tables,
using synthesized rules if possible. Simple extraction rules, such as
ones generated by Evaporate, are not applicable in our setting.
Retrieval-Augmented Generation (RAG).RAG techniques [20,
34,41,60], help identify smaller text portions that are most relevant
to a given query in order to fit into finite context windows, reduce
cost, and in some cases improve accuracy. Most techniques use
fixed granularity chunking policies and don’t account for semantic
structure, while recent extensions rely on potentially expensive
recursive summarization to build a hierarchy [9,52]. We showed
that this RAG_tree approach suffers from the same issues as vanilla
RAG. The leaf nodes still use fixed size chunks that are divorced
from semantics, and thus fail to find relevant text segments. In
comparison,ZenDBleverages semantic structure to boost precision
and recall by up to 61% and 80%.
Multi-Modal Databases.Recent work creates of multi-modal
databases [24,35,55,56,58] that support SQL-like interfaces over
text, images, and/or video. However, they all apply LLMs or other
pre-trained models to entire documents at a time, and are thus
limited to simple, small documents. This is equivalent to our vanilla
LLM approach, which is expensive and not very accurate. Other
work [31] has used interactive query processing to improve query
results through user feedback. None of these approaches have ex-
plored the use of semantic structure to reduce cost and improve
accuracy.
Natural Language Interfaces to Data.Supporting natural lan-
guage querying over structured data is a long-standing question
in the database community; a recent survey is one by Quamar et
al. [50]. While the database community has been working on this
problem for over a decade, e.g., [40], LLMs have dominated recent
benchmarks [21,42]. In our work, we instead focus on the inverse
problem of structured (SQL) queries over unstructured data—but
this line of work could aid the first step of SQL query construction.
LLMs meet Data Management.LLMs potentially disrupts the
field of data management [29], but the first step is to actually un-
derstand tables. Recent work [25,28,62] explores how well LLMs
understand tabular data, and representing knowledge learned by the
LLM as structured data [51,59]. Many data management problems
have been revisited, including query rewriting [44], database tun-
ing [57], data preprocessing [63], data and join discovery [26,27,36],
data profiling [33], and data wrangling [23,43,48]. Some recent
work has also explored how well LLMs can generate tables [54].
ZenDBalso uses LLMs, but to a new setting: document analytics.
Structured Extraction.Structured extraction from web pages,
pdfs, and images has a long history of work. For instance, Snow-
ball [17] proposed structured extraction over the open web, and
leverage common techniques such as wrapper induction [38,46]
which also leverage the hierarchical structure of HTML documents
and headings. In contrast,ZenDBtakes as input PDFs, which are
often not hierarchically encoded. Other works, such as Shreddr [22]
extract from images of forms where the templates are identical, and
focus on efficient use of crowd workers. These are also relevant
due to the similarities between LLMs and crowdsourcing [49].
## 9  CONCLUSION
We presentedZenDB, a document analytics system that leverages
templatized structure present in documents in a collection to sup-
port cost-efficient and accurate query processing. During ingest,
ZenDBextracts structure from documents in the form of SHTs,
guaranteeing that the results are correct for well-formatted docu-
ments. Then, during table creation,ZenDBmaps tuples to nodes
in the SHT, with attribute values to be populated during querying.
ZenDBsupports SQL queries on user-defined document tables, ap-
plying predicate reordering and pushdown, and projection pull-up
techniques, coupled with a summary-based tree-search approach
to optimize query processing. Across multiple domains,ZenDB
provides a compelling trade-off point relative to LLM-only or RAG
based approaches. In future work, we plan to study the setting
where there are no templates or when the templates are very noisy,
as well as expand the space of SQL queries supported. In addition,
we envision a rich design space for user interfaces to allow users to
explore the results ofZenDBqueries alongside their provenance.

## REFERENCES
[1]2019.https://www.forbes.com/sites/rkulkarni/2019/02/07/big-data-goes-big/?sh=
## 45b1c73420d7.
## [2]2021.https://mitsloan.mit.edu/ideas-made-to-matter/tapping-power-
unstructured-data.
## [3]   2023.gemini.google.com.
## [4]   2023.https://cloud.google.com/document-ai?hl=en.
## [5]   2023.https://cloud.google.com/document-ai?hl=en.
## [6]   2023.https://openai.com/pricing.
## [7]   2023.https://www.anthropic.com/news/claude-3-family.
## [8]
## 2023.https://www.forbes.com/sites/stevemcdowell/2023/03/09/komprise-
unleashes-fresh-insights-about-your-unstructured-data/?sh=5f444c474aa9.
## [9]   2023.https://www.llamaindex.ai/.
## [10]   2023.https://www.nltk.org/.
## [11]   2024.http://personal-informatics.depstein.net.
[12]   2024.https://primis.phmsa.dot.gov/enforcement-data/cases/NOPV.
## [13]   2024.https://pypi.org/project/pdfplumber/0.1.2/.
[14]   2024.https://www.malibucity.org/AgendaCenter.
## [15]
Serge  Abiteboul.  1997.Querying  semi-structured  data.  InDatabase The-
ory—ICDT’97: 6th International Conference Delphi, Greece, January 8–10, 1997
## Proceedings 6. Springer, 1–18.
## [16]
Serge Abiteboul, Peter Buneman, and Dan Suciu. 2000.Data on the web: from
relations to semistructured data and XML. Morgan Kaufmann.
[17]Eugene Agichtein and Luis Gravano. 2000. Snowball: Extracting relations from
large plain-text collections. InProceedings of the fifth ACM conference on Digital
libraries. 85–94.
[18]Simran Arora, Brandon Yang, Sabri Eyuboglu, Avanika Narayan, Andrew Ho-
jel, Immanuel Trummer, and Christopher Ré. 2023.  Language Models Enable
Simple Systems for Generating Structured Views of Heterogeneous Data Lakes.
Proceedings of the VLDB Endowment17, 2 (2023), 92–105.
## [19]
## Yushi Bai, Xin Lv, Jiajie Zhang, Hongchang Lyu, Jiankai Tang, Zhidian Huang,
Zhengxiao Du, Xiao Liu, Aohan Zeng, Lei Hou, et al.2023.   Longbench: A
bilingual, multitask benchmark for long context understanding.arXiv preprint
arXiv:2308.14508(2023).
[20]Deng Cai, Yan Wang, Lemao Liu, and Shuming Shi. 2022.  Recent advances in
retrieval-augmented text generation. InProceedings of the 45th International
ACM SIGIR Conference on Research and Development in Information Retrieval.
## 3417–3419.
[21]Shuaichen Chang, Jun Wang, Mingwen Dong, Lin Pan, Henghui Zhu, Alexan-
der Hanbo Li, Wuwei Lan, Sheng Zhang, Jiarong Jiang, Joseph Lilien, et al.2023.
Dr. spider: A diagnostic evaluation benchmark towards text-to-sql robustness.
arXiv preprint arXiv:2301.08881(2023).
[22]Kuang Chen, Akshay Kannan, Yoriyasu Yano, Joseph M Hellerstein, and Tapan S
Parikh. 2012. Shreddr: pipelined paper digitization for low-resource organizations.
InProceedings of the 2nd ACM Symposium on Computing for Development. 1–10.
[23]Zui CHen, Lei Cao, Sam Madden, Ju Fan, Nan Tang, Zihui Gu, Zeyuan Shang,
Chunwei  Liu,  Michael  Cafarella,  and  Tim  Kraska.  2023.   Seed:  Simple,  effi-
cient, and effective data management via large language models.arXiv preprint
arXiv:2310.00749(2023).
[24]Zui Chen, Zihui Gu, Lei Cao, Ju Fan, Sam Madden, and Nan Tang. 2023. Sym-
phony: Towards natural language query answering over multi-modal data lakes.
InConference on Innovative Data Systems Research, CIDR. 8–151.
[25]Tianji Cong, Madelon Hulsebos, Zhenjie Sun, Paul Groth, and HV Jagadish. 2023.
Observatory: Characterizing Embeddings of Relational Tables.arXiv preprint
arXiv:2310.07736(2023).
[26]Xiang Deng, Huan Sun, Alyssa Lees, You Wu, and Cong Yu. 2022. Turl: Table
understanding through representation learning.ACM SIGMOD Record51, 1
## (2022), 33–40.
## [27]
Yuyang Dong, Chuan Xiao, Takuma Nozawa, Masafumi Enomoto, and Masafumi
Oyamada. 2022. DeepJoin: Joinable Table Discovery with Pre-trained Language
Models.arXiv preprint arXiv:2212.07588(2022).
[28]Xi  Fang,  Weijie  Xu,  Fiona  Anting  Tan,  Jiani  Zhang,  Ziqing  Hu,  Yanjun  Qi,
Scott Nickleach, Diego Socolinsky, Srinivasan Sengamedu, and Christos Falout-
sos. 2024.  Large Language Models on Tabular Data–A Survey.arXiv preprint
arXiv:2402.17944(2024).
## [29]
Raul Castro Fernandez, Aaron J Elmore, Michael J Franklin, Sanjay Krishnan, and
Chenhao Tan. 2023. How large language models will disrupt data management.
Proceedings of the VLDB Endowment16, 11 (2023), 3302–3309.
## [30]
Boris Glavic et al.2021. Data provenance.Foundations and Trends®in Databases
## 9, 3-4 (2021), 209–441.
## [31]
Benjamin Hättasch, Jan-Micha Bodensohn, Liane Vogel, Matthias Urban, and
Carsten Binnig. 2023. WannaDB: Ad-hoc SQL Queries over Text Collections. In
BTW 2023. Gesellschaft für Informatik eV, 157–181.
[32]Joseph M Hellerstein and Michael Stonebraker. 1993. Predicate migration: Op-
timizing queries with expensive predicates. InProceedings of the 1993 ACM
SIGMOD international conference on Management of data. 267–276.
[33]Zezhou Huang and Eugene Wu. 2024. Cocoon: Semantic Table Profiling Using
Large Language Models.arXiv preprint arXiv:2404.12552(2024).
[34]Gautier Izacard, Patrick Lewis, Maria Lomeli, Lucas Hosseini, Fabio Petroni,
Timo Schick, Jane Dwivedi-Yu, Armand Joulin, Sebastian Riedel, and Edouard
Grave. 2022. Few-shot learning with retrieval augmented language models.arXiv
preprint arXiv:2208.03299(2022).
[35]Saehan Jo and Immanuel Trummer. 2023. Demonstration of ThalamusDB: An-
swering Complex SQL Queries with Natural Language Predicates on Multi-Modal
Data. InCompanion of the 2023 International Conference on Management of Data.
## 179–182.
## [36]
Moe Kayali, Anton Lykov, Ilias Fountalis, Nikolaos Vasiloglou, Dan Olteanu, and
Dan Suciu. 2023. CHORUS: foundation models for unified data discovery and
exploration.arXiv preprint arXiv:2306.09610(2023).
[37]Mei Kobayashi and Koichi Takeda. 2000. Information retrieval on the web.ACM
computing surveys (CSUR)32, 2 (2000), 144–173.
## [38]
Nicholas Kushmerick. 2000. Wrapper induction: Efficiency and expressiveness.
Artificial intelligence118, 1-2 (2000), 15–68.
[39]Patrick  Lewis,  Ethan  Perez,  Aleksandra  Piktus,  Fabio  Petroni,  Vladimir
## Karpukhin, Naman Goyal, Heinrich Küttler, Mike Lewis, Wen-tau Yih, Tim Rock-
täschel, et al.2020. Retrieval-augmented generation for knowledge-intensive nlp
tasks.Advances in Neural Information Processing Systems33 (2020), 9459–9474.
[40]Fei Li and Hosagrahar V Jagadish. 2014. NaLIR: an interactive natural language in-
terface for querying relational databases. InProceedings of the 2014 ACM SIGMOD
international conference on Management of data. 709–712.
## [41]
Huayang Li, Yixuan Su, Deng Cai, Yan Wang, and Lemao Liu. 2022. A survey on
retrieval-augmented text generation.arXiv preprint arXiv:2202.01110(2022).
## [42]
## Jinyang Li, Binyuan Hui, Ge Qu, Jiaxi Yang, Binhua Li, Bowen Li, Bailin Wang,
Bowen Qin, Ruiying Geng, Nan Huo, et al.2024.  Can llm already serve as a
database interface? a big bench for large-scale database grounded text-to-sqls.
Advances in Neural Information Processing Systems36 (2024).
[43]Yuliang Li, Jinfeng Li, Yoshihiko Suhara, AnHai Doan, and Wang-Chiew Tan.
- Deep entity matching with pre-trained language models.arXiv preprint
arXiv:2004.00584(2020).
## [44]
Jie Liu and Barzan Mozafari. 2024. Query Rewriting via Large Language Models.
arXiv preprint arXiv:2403.09060(2024).
[45]Nelson F Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Michele Bevilacqua,
Fabio Petroni, and Percy Liang. 2024. Lost in the middle: How language models
use long contexts.Transactions of the Association for Computational Linguistics
## 12 (2024), 157–173.
[46]Tomohiro Manabe and Keishi Tajima. 2015.   Extracting logical hierarchical
structure of HTML documents based on headings.Proceedings of the VLDB
## Endowment8, 12 (2015), 1606–1617.
[47]Jason  McHugh,  Serge  Abiteboul,  Roy  Goldman,  Dallas  Quass,  and  Jennifer
Widom. 1997.  Lore: A database management system for semistructured data.
ACM Sigmod Record26, 3 (1997), 54–66.
[48]Avanika Narayan, Ines Chami, Laurel Orr, Simran Arora, and Christopher Ré.
- Can foundation models wrangle your data?arXiv preprint arXiv:2205.09911
## (2022).
[49]Aditya G Parameswaran, Shreya Shankar, Parth Asawa, Naman Jain, and Yujie
Wang. 2023. Revisiting prompt engineering via declarative crowdsourcing.arXiv
preprint arXiv:2308.03854(2023).
[50]Abdul Quamar, Vasilis Efthymiou, Chuan Lei, Fatma Özcan, et al.2022. Natural
language interfaces to data.Foundations and Trends®in Databases11, 4 (2022),
## 319–414.
[51]Mohammed Saeed, Nicola De Cao, and Paolo Papotti. 2023.  Querying large
language models with SQL.arXiv preprint arXiv:2304.00472(2023).
[52]Parth Sarthi, Salman Abdullah, Aditi Tuli, Shubh Khanna, Anna Goldie, and
Christopher D Manning. 2024. RAPTOR: Recursive Abstractive Processing for
Tree-Organized Retrieval. InThe Twelfth International Conference on Learning
## Representations.
[53]Amit Singhal et al.2001. Modern information retrieval: A brief overview.IEEE
## Data Eng. Bull.24, 4 (2001), 35–43.
[54]Xiangru Tang, Yiming Zong, Yilun Zhao, Arman Cohan, and Mark Gerstein. 2023.
Struc-Bench: Are Large Language Models Really Good at Generating Complex
Structured Data?arXiv preprint arXiv:2309.08963(2023).
## [55]
James  Thorne,  Majid  Yazdani,  Marzieh  Saeidi,  Fabrizio  Silvestri,  Sebastian
Riedel, and Alon Halevy. 2021.  Database reasoning over text.arXiv preprint
arXiv:2106.01074(2021).
## [56]
James Thorne, Majid Yazdani, Marzieh Saeidi, Fabrizio Silvestri, Sebastian Riedel,
and Alon Halevy. 2021. From natural language processing to neural databases.
InProceedings of the VLDB Endowment, Vol. 14. VLDB Endowment, 1033–1039.
[57]Immanuel Trummer. 2022. DB-BERT: a Database Tuning Tool that" Reads the
Manual". InProceedings of the 2022 international conference on management of
data. 190–203.
[58]Matthias Urban and Carsten Binnig. 2023.  Towards Multi-Modal DBMSs for
Seamless Querying of Texts and Tables.arXiv preprint arXiv:2304.13559(2023).
[59]Matthias Urban, Duc Dat Nguyen, and Carsten Binnig. 2023. OmniscientDB: a
large language model-augmented DBMS that knows what other DBMSs do not
know. InProceedings of the Sixth International Workshop on Exploiting Artificial
Intelligence Techniques for Data Management. 1–7.

[60]Zhiruo Wang, Jun Araki, Zhengbao Jiang, Md Rizwan Parvez, and Graham
Neubig. 2023. Learning to Filter Context for Retrieval-Augmented Generation.
arXiv preprint arXiv:2311.08377(2023).
## [61]
Xueqing Wu, Jiacheng Zhang, and Hang Li. 2021. Text-to-table: A new way of
information extraction.arXiv preprint arXiv:2109.02707(2021).
[62]Pengcheng  Yin,  Graham  Neubig,  Wen-tau  Yih,  and  Sebastian  Riedel.  2020.
TaBERT: Pretraining for joint understanding of textual and tabular data.arXiv
preprint arXiv:2005.08314(2020).
## [63]
Haochen Zhang, Yuyang Dong, Chuan Xiao, and Masafumi Oyamada. 2023.
Large language models as data preprocessors.arXiv preprint arXiv:2308.16361
## (2023).
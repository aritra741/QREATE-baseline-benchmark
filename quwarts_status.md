November 12, 2026

I want to write down the main design decisions in QuWARTS, the current results, and what I am working on next.

The scores below are structure F2, cell F1 at τ=0.20, and query score. Query score is structure F2 × cell F1 on each query, then averaged. That is not the same as multiplying the two column means. I am using the query-score mean to compare against DocETL. The numbers are from the held-out 80/20 test split.

The main idea is to extract information from the documents once and reuse it for different databases.

Some work is expensive because it reads every document. For example, finding each player’s team requires reading the corpus. Other work is much cheaper because it only works on the values we already found. For example, checking if “LA Lakers” and “Los Angeles Lakers” refer to the same team only compares a small list of team names. We can use embeddings or an LLM for this without paying the cost of reading the whole corpus again.

So the system keeps the extracted information in a shared evidence store. It stores the original value, parsed value, source span, unit, and possible entity matches. It does not merge or normalize values immediately.

For example, entity resolution runs once and stores possible matches:

| Name A | Name B | Match score |
|---|---|---|
| LA Lakers | Los Angeles Lakers | 0.95 |
| Philadelphia Warriors | Philadelphia 76ers | 0.72 |

This match table is computed once. Multiple databases can reuse it, including a shared canonical ID for joins.

There can be more than one database. A query is sent to the first database that can rewrite it and cover the predicate. We do not rank the feasible databases, so a later one might answer it better. If that first database cannot rewrite the query or the join matches no keys, the query is not served from it. The database is kept for other queries.

I use selection pushdown. Some per-query systems already do this, and Boris told me to use it. The system first extracts filter attributes. It then extracts the remaining attributes only for documents that pass the filters. This cannot be used for every query. For example, `NOT EXISTS`, `EXCEPT`, and unfiltered `COUNT(*)` need information about rows that do not pass a filter. For these cases, the system extracts the full data.

Here are the current results. Each cell is mean structure F2 / mean cell F1@0.20 / mean query score.

| Corpus | QuWARTS | DocETL |
|---|---|---|
| Player | 0.735 / 0.459 / **0.387** | 0.536 / 0.293 / 0.202 |
| Med | 0.399 / 0.150 / 0.139 | 0.837 / 0.195 / **0.166** |
| Art | 0.177 / 0.114 / **0.070** | 0.418 / 0.098 / 0.069 |
| Finan | 0.359 / 0.068 / 0.039 | 0.537 / 0.114 / **0.084** |
| Legal | 0.162 / 0.033 / 0.022 | 0.789 / 0.129 / **0.124** |
| CSPaper | not run | 0.777 / 0.094 / 0.089 |

QuWARTS has a higher query score on Player and Art. Player is a large gap (0.387 vs 0.202). It is also the corpus I developed the system on, so I do not treat that result as enough evidence that the system generalizes. Art is 0.070 vs 0.069. DocETL has much better structure there (0.418 vs 0.177).

The system is also not using all of its allowed budget. On Art, it used 1.12M tokens out of a 5.11M token cap. This cap is already about 25% to 30% of DocETL’s cost. The system stops after one extraction pass because it thinks all requirements are satisfied. But that only means every required attribute was attempted. It does not mean the extracted values are good enough.

The next step is to test improvements on Art only. I will use the remaining budget for additional extraction passes. The system will compare outputs from different extraction methods and re-check values where they disagree.

The goal is to improve structure F2 and the product at τ=0.20 while staying under about 25% to 30% of DocETL’s total cost.

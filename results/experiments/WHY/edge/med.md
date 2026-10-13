# med (drug, disease), realistic v1: what carries our system over DocETL, revised after the challenge

Scores at 20% tolerance (swap file): ours 0.259, DocETL 0.120, so the summed gap over 20 queries is 2.78.
No model calls were made. Scripts are in `revise/`. Run each from the repo root as
`PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python revise/<script> revise`.

## 0. Scoring facts to settle first

- **QJ2 is worth 0.286, not 0.0** (`qj2.py`, `qj2c.py`, `qj2d.py`).
  - The 0.0 in the stream record, and in my earlier rescoring (0.245), is an artifact.
  - `official_sql` rewrites `disease.prognosis LIKE '%chronic%'` to `CASE WHEN disease.sig_4e499c217891_r = 1 ...`. That column does not exist in a view completed while the catalogue held fewer queries, so `predicates()`, which is cached on its first call, lacked the QJ2 signature.
  - The SQL then errors, returns no rows and scores 0.
  - Scored on the raw SQL, the same view gives 0.2857 (OTC 1 and Rx 16, against correct '' 2, OTC 1, Rx 4).
- **The challenger's explanation is wrong.** They said the swap's 0.286 is the tolerant tier. It is not: `exp_swap.score_multi` uses the benchmark path.
- **The `normalize_sql` join-literal bug is real but only affects the tolerant tier.** Under it, the correct QJ4 answer becomes 4 instead of 3, ours 8 and DocETL 53. Tolerant join scores should not be quoted.
- **Replicates** (`replicates.py`). There are three realistic streams that share the build journal, and their patch reads were re-made.
  - Our mean is 0.259, 0.259 and 0.209 (average 0.242).
  - Q8 is exact in 1 of 3 runs; the other two answer 3 against a correct 2.
  - Q13 is exact in 1 of 3 runs (rep1: 8 against 8).
  - Q12 and QJ4 are exact in 3 of 3 runs. But both come from the shared build reads, which were not re-sampled, so their stability is not tested.

## Findings that survive

### F1. Most of the gap is four exact single-number hits made of offsetting errors (KEPT, strengthened)

A single number is scored exactly. Four queries flip between 0 and 1:

| Query | System that hits | Correct | Answer | How the answer is made up |
|---|---|---|---|---|
| Q8 | ours | 2 | 2 | 1 true + 1 false match; exact in 1 of 3 replicates |
| Q12 | ours | 21 | 21 | 12 true + 9 false matches, 9 misses |
| QJ4 | ours | 3 | 3 | none of our 3 pairs (149861-1709, 149973-1361, 445144-1769) is a correct pair |
| Q6 | DocETL | 30 | 30 | 13 true + 17 false matches; 17 of the 30 matches are prose replies quoting the SQL |

- Net, these give +2.0 of the 2.78 summed gap (72%).
- The non-single-number queries add only +0.78: Q1 +0.278, Q3 +0.25, Q7 +0.107, QJ2 +0.107, QJ1 +0.037.

A graded view (`taus.py`) shows a systematic difference underneath the lottery:
- Over the 13 single-number queries, ours is closer to the correct count in 12. The median |log ratio| is 0.41 for ours and 1.44 for DocETL.
- Within ±20% of the correct count: ours 5 of 13 (Q2, Q6, Q8, Q12, QJ4), DocETL 1 of 13 (Q6).
- DocETL overcounts in 12 of 13. Examples (correct / ours / DocETL):
  - Q5: 3 / 0 / 59
  - Q8: 2 / 2 / 28
  - Q10: 13 / 17 / 58
  - Q13: 8 / 5 / 86
  - Q15: 4 / 2 / 34

**Where this breaks down:** a single exact hit depends on errors cancelling. Q8's hit does not reproduce in 2 of 3 replicates, Q13's hit appears in 1 of 3, and DocETL's one hit (Q6) is made of prose replies.

### F2. Our edge is precision, not recall (REVISED; this replaces the earlier recall and "commit" claim)

Per-document filter outcomes, over the 20 single-table LIKE filters (`chunkcf.py`):
- "single" means documents that fit in one 8k chunk, so both systems read the whole document in one call.
- "multi" means documents we chain over 2 or more chunks.
- "head" means our chunk 0 only (E13-head reuses the same prompt sha for 1514 of 2032 shared reads, so head equals chunk 0).

| Documents | System | True-match rate | False-match rate | F1 |
|---|---|---|---|---|
| single (967 negatives, 206 positives) | ours | 0.61 | 0.137 | 0.540 |
| single | DocETL | 0.72 | 0.461 | 0.370 |
| multi (647 / 142) | ours, head only | 0.47 | 0.073 | 0.523 |
| multi | ours, all chunks merged | 0.73 | 0.175 | 0.579 |
| multi | DocETL | 0.65 | 0.400 | 0.377 |

- DocETL finds more true matches on single-chunk documents.
- Our advantage is a false-match rate about 3x lower. It holds where neither system chunks.
- It also holds with chunking removed: our head-only F1 is 0.523 against DocETL's 0.377.

**Where this breaks down:**
- On documents over 20k tokens, merging the chunks raises our false-match rate to 0.343, and F1 falls from 0.538 (head only) to 0.327. DocETL's F1 there is 0.226.
- On documents under 6k tokens (only 4 drug and 10 disease documents), DocETL finds 22 of 27 positives and we find 9. These are per-document failures:
  - 87524: every field came back null.
  - 1110: we read Yescarta, another drug on the same page; the correct row is promethazine.

### F3. DocETL's extra false matches are mostly not supported by the document text (NEW numbers)

On single-chunk documents (`chunkcf_text.py`):

| False matches | DocETL | Ours |
|---|---|---|
| Text never contains the constant | 250 | 55 (4.5x fewer) |
| Text contains the constant | 196 | 77 (2.5x fewer) |

Over all filters (`support.json`): DocETL 874 false matches, 414 of them unsupported by the text; ours 302, 94 unsupported.

Q8 "Pfizer", document by document (`pfizer.json`). DocETL writes "Pfizer" for 22 documents:
- 15 never mention Pfizer. Four of these state the real manufacturer, which we read correctly:
  - 422147: Boehringer Ingelheim
  - 461870: Janssen Pharmaceuticals
  - 489250: Alfasigma
  - 97675: Centurion Remedies
- 6 mention Pfizer in another role:
  - 1110: a stock headline
  - 117088: COVID-vaccine authorisation
  - 219293: vaccine-policy news
  - 236378: news item about Pfizer Inc
  - 52966: spam "pfizer japan viagra"
  - 640907: a Viagra citation
- 1 is genuine: 654970, Detrol "manufactured by Pfizer".

So the Pfizer error is mostly echo, plus role confusion. It is not a correct reading of another page.

### F4. Seeing the constant does not cause the echo. The prompt's framing is associated with it, but the cause is not isolated (REVISED from the original constant-priming claim)

Both systems see the constant:
- Our W0 usage lines show 'oral', 'capsule', 'injection', 'infectious' and 'chronic'.
- Our patch specs for Q4 and Q10 show 'with food' and 'lung' (the arriving queries' own constants).
- Both systems' choice lists contain 'take with food' and 'refrigerate'.

Within-reader test (`usage_ab.py`). E13-raw keeps the usage phrase; E13-nousage drops it. Same drift stream, 1417 matched reads (same table, context, document and chunk). On documents whose correct value lacks the constant:
- False matches to the shown constants: 16/979 = 0.016 with the phrase, 19/979 = 0.019 without.
- 'Bayer' and the other manufacturer constants: 0/157 to 0/162 in both arms.
- 'pregnant women': 14/125 vs 16/125.
- So showing example constants does not raise false matches in our reader.

The same constants in DocETL (`docetl_echo.py`): its echo rate is high only when the constant sits in the query's SQL. Rate with the constant in the SQL / without:

| Column ~ constant | In SQL | Not in SQL |
|---|---|---|
| manufacturer ~ 'bayer' | 37/315 = 0.117 | 0/417 |
| manufacturer ~ 'pfizer' | 27/96 = 0.281 | 0/643 |
| manufacturer ~ 'forest pharmaceuticals' | 18/78 = 0.231 | 0/669 |
| affected_organs ~ 'lung' | 51/87 = 0.586 | 6/83 = 0.072 |
| recommended_usage ~ 'with food' | 46/164 = 0.280 | 22/327 = 0.067 |

It does not happen for every constant. For 'pregnant women' the rate is lower with the constant in the SQL: 3/54 = 0.056 vs 17/189 = 0.090. 'refrigerate' (in SQL 0/78, without 78/490) is not a valid contrast, because the realistic Q5 filter is the stem 'refrigerat', not the drift workload's 'refrigerate'.

The challenger's split (ours 0.231 with the constant shown vs 0.090 without) mixes this up with which columns are involved. The shown constants are the broad stems (oral, capsule, injection, chronic, with food, lung). The A/B test above holds the column fixed and finds no effect.

**What remains confounded:** DocETL's prompt differs from ours in three ways at once:
- the constant appears as a SQL predicate;
- one field per call instead of 8-16;
- the whole document in one call.

Separating them needs a DocETL rerun with the constants masked (GPU).

**Second channel:** prose replies that quote the SQL account for 126 of DocETL's 874 false matches (93 of them quote the query or constant), and for 30 of its 43 Q4 false matches.

### F5. Read-time merging and filtering explain part of the recall and of Q12, not the precision edge (NEW)

- **Chunk merging.** Q12's exact hit needs the merge: head only gives 16, all chunks give 21, against a correct 21. Q2 goes from 43 to 64 (correct 57).
  - Merging adds 66 false matches on multi-chunk documents. 43 of them (65%) are in documents whose text contains the constant. That fits values read off other pages of these multi-page crawls: the correct row describes one entity, and the correct generic name first appears a median 39% of the way into the text.
- **Item filter** (`core/adapt/catalogue.filter_list_items`). It keeps only list items stated word for word in the document and empties a cell with none (QUWARTS_ITEMFILTER_EMPTY=1). It is model-free and was on for manufacturer, storage_conditions, unsuitable_population, risk_factors and 10 other columns. Test: `itemfilter_cf.py`.
  - Removing it from ours changes no query score: Q6 25 → 29 (correct 30) and Q13 5 → 20 (correct 8) both stay wrong.
  - Applying it to DocETL on the same columns leaves its mean at 0.1204, although its false matches drop sharply:
    - Pfizer 27 → 6
    - refrigerat 56 → 3
    - pregnan 17 → 0 (true matches 13 → 5)
    - genetic risk 78 → 0 (true matches 8 → 0)
  - Q5 becomes exact (3 false matches, 0 true) and Q6 is lost.
  - Applying it to every filtered DocETL column (which our system does not do) raises DocETL to 0.230, almost all through new exact hits (Q3, Q5, Q14, QJ3).
  - So this step is not part of the med gap. It also shows how easily exact hits move.

### F6. The representation layer contributes nothing measurable (KEPT, now exact)

- t0 rewrites change no LIKE result in the filter columns (challenger: 670 rows, 0 flips).
- `rawkeys.py` reverts the entity-resolution and group rewrites of disease_name (26 drug cells, 10 disease cells) to the item our build read stated, then rescores. QJ1 goes from 0.037 to 0.0325; QJ2 to QJ5 do not change.
- So the join gains (QJ4 +1, QJ2 +0.107) do not come from entity resolution.

### F7. The cost edge comes from making few passes over the corpus (KEPT, with corrected numbers and the condition)

- **DocETL:** 30.49M prompt + 0.15M completion tokens, 2647 calls, 1.52M input tokens per query.
- **Ours:** build 2.50M, 295 calls. The stream charged 7.03M over 944 calls, all of it in two patch events:
  - Q4: 4.53M charged, 1.81M paid.
  - Q10: 2.50M charged, 1.34M paid.
- The other 18 of 20 queries are free. The template build had already read 17 schema columns, 8 of them the realistic group-by and filter columns. Each patch prefetched every remaining schema column of its table.

Where it breaks down:
- One patch event costs as much as 1.6-3.0 DocETL queries.
- On the drift stream, a measured worst case (E13-noreuse: every query starts from the build) charged 1.02M per query, against DocETL drift's 2.12M per query. So without reuse the edge drops from about 3x to about 2x per query (different query sets, so the ratio is approximate).
- With a schema that keeps growing, the 18-of-20 free queries would not recur.

## Status of the original claims

- **Claim 0 (DocETL's false matches come from its query-specific, primed reads; ours are query-independent): REVISED.**
  - Our reads are also primed: by the usage lines, by the arriving query in the Q4 and Q10 patches, and by the choice lists.
  - Holding the column fixed, seeing the constant does not raise our false matches (1.6% vs 1.9%).
  - For the same constants, DocETL echoes 12-28% when they sit in its SQL and 0% when they do not.
  - The cause is how the prompt frames the constant (as a SQL predicate in a one-field, whole-document call), not whether the constant is visible. The three framing factors are still confounded.
- **Claim 1 (our recall edge from "never null" plus committing to the constant): REVISED.**
  - We have no overall recall edge. DocETL finds more true matches on single-chunk documents (0.72 vs 0.61).
  - The edge is a false-match rate about 3x lower, and it holds without chunking.
  - Chunk merging gives us recall on long documents at a precision cost.
  - The "commit" effect appears only for the realistic workload's broad LIKE stems.
- **Claim 2 (exact single-number scoring turns offsetting errors into 0/1; 72% of the gap): KEPT.**
  - Replicates show Q8 is not stable (1 of 3) and Q13 can flip in our favour (1 of 3).
  - The graded metric shows a real, systematic difference: closer in 12 of 13 queries.
  - QJ2 is now a valid 0.286.
- **Claim 3 (the representation layer is not the source): KEPT.** Reverting the entity-resolution and group rewrites changes QJ1 by 0.005 only. The read-time item filter, another non-prompt step, is also not part of the gap.
- **Claim 4 (cost from shared reads that are reused): KEPT, with the condition.** The edge comes from extracting the fixed schema in about three passes; patch reads are not query-independent. Worst case without reuse is still about 0.5x DocETL per query on med drift.

## Still unexplained

- **Why DocETL's whole-document, one-field, SQL-framed read invents or echoes values that the text does not support** (250 such false matches on single-chunk documents, against our 55). Without model calls, I cannot separate the SQL predicate, the field count and the reading window. This needs a DocETL rerun with the constants masked, or our reader in one-field mode.
- **Why DocETL finds more true matches on single-chunk documents** (0.72 vs 0.61). It may be due to our multi-field prompt (8-16 fields) or to our "give the value as the document states it" instruction; not tested.
- **Why the stream's stored scores and the cached `predicates()` disagree with the swap path.** The stream scorer should be audited for other queries that use signature columns.

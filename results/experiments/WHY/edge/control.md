# Control collections (art, cspaper): revised findings after the devil's-advocate round

Realistic v1 unless stated otherwise. Scores are at 20% tolerance (tau 0.2). Single numbers are scored exactly.
No model calls were made. Scripts are in `control/revise/` and run from the repo root with the quwarts venv and env vars.

## What the control lacks, in one table

| condition (present in player / med / legal) | art | cspaper | evidence |
|---|---|---|---|
| DocETL drops documents (long docs) | 0.6% drops, rows step 0 | 0% drops, rows step 0 | rows_by_length.py |
| joins (join-key agreement) | single table | single table | schema |
| constant priming lowers DocETL's match precision | -0.05 | -0.13 | literal_prec.py (player -0.29, med -0.29, legal -0.26) |
| DocETL empties reach the score | 1/22 queries moved by the absence fill | 0/22 | fill_score.py |
| single numbers small enough to hit exactly | 0/6 hit by either system | 0/6 | shape.py (med: ours exact 3/13, DocETL 1/13) |

## Findings that survive

### F1. Absence fill: large at the cell level, almost invisible at the query level on realistic v1, workload-dependent
- **Test:** DocETL's per-query databases with our absence rule (`context_probe.absence_value`) applied to its NULLs. Dropped rows were not added back. Script: `fill_score.py`.
- **Realistic, gap before -> after the fill (tau 0.2):**
  - art +0.019 -> +0.007
  - cspaper +0.003 -> +0.003
  - player +0.459 -> +0.453
  - med +0.139 -> +0.139
  - legal +0.149 -> +0.160
- **Realistic, queries whose score moved:** 3 of 107.
  - art Q16 `AVG(awards)`: 0 -> 0.25, which equals ours.
  - player QJ2 `SUM` per team: 0.107 -> 0.267.
  - legal Q6 `AVG(legal_basis_num)`: 0.16 -> 0.00.
- **Drift (`fill_score_drift.py`), share of the gap the fill closes:**
  - art 23% (+0.083 -> +0.064)
  - cspaper 86% (+0.033 -> +0.005)
  - player 20%
  - legal 19%
  - med 0%
  - 41 of 284 queries moved, e.g. art `zodiac, AVG(awards) WHERE marriage='Married'`: DocETL 0.144 -> 0.288 (ours 0.649).
- **Mechanism:** the fill changes an answer only when the query treats NULL differently from 0 or No: AVG, MIN, COUNT(col), or GROUP BY on that column, or a group whose values are all NULL under SUM. The realistic queries use these columns mostly through SUM, `='Yes'` or `>=1` filters, where NULL and 0/No give the same result.
  - Realistic uses absence-fill columns in 29 of 107 queries; drift uses them in 127 of 284.
  - My regex split into "NULL-sensitive" and "NULL-insensitive" query forms separates poorly on drift: 35% vs 28% of queries moved. Treat the form rule as approximate.
- **Breakdown:** cspaper realistic Q13 and Q20 are NULL-sensitive (`GROUP BY use_agent` / `uses_reranker`, with `AVG(baseline_amount)`), yet they did not move. `baseline_amount` binds both systems: with the correct `uses_reranker` column the score is still 0.0.

### F2. The single-number queries in the control hide a consistent ordinal edge that exact scoring erases
- art and cspaper each have 6 of 22 single-number queries. Both systems score 0 on all of them, but ours is closer to the correct value in **6/6 and 6/6**. Script: `shape.py`.
  - art median relative error: ours 0.45, DocETL 0.67. Examples (correct / ours / DocETL):
    - Q5: 31 / 46 / 181
    - Q15: 58 / 34 / 310
    - Q19: 380 / 404 / 341
  - cspaper median relative error: ours 0.83, DocETL 0.99. Examples:
    - Q19: 89 / 19 / 1
    - Q9: 66 / 8 / 1
- **Contrast with med:** 13 of 20 queries are single numbers over small correct counts (2-57). Ours is exact on 3 (Q8 2, Q12 21, QJ4 3) and DocETL on 1 (Q6 30), giving means of 0.231 vs 0.077. That accounts for 0.100 of med's 0.139 gap.
- **Condition:** an exact hit needs a count fed by few documents. Art counts are 31-575 over 1000 documents, so a false-match rate of about 1.5% on 970 negatives already rules out an exact hit.
- **Breakdown:** with relative tolerance instead of exact scoring, only art Q19 (ours 6% off) would enter. So the edge is real but far from correct; scoring alone does not hide a large edge.

### F3. DocETL's wins in the control are compensating errors or vocabulary disclosure by the shown constant
**art Q9** (`SUM(teaching) GROUP BY birth_continent`, ours 0.338 vs DocETL 0.656). Script: `q9_factorial.py`, a 2x2 (continent source x teaching source):

| continent \ teaching | ours | DocETL | correct |
|---|---|---|---|
| ours | 0.338 | 0.564 | 0.677 |
| DocETL | 0.547 | 0.656 | 0.547 |
| correct | 0.625 | 0.875 | 1.000 |

- **Shapley shares of the 0.318 gap:** teaching 0.168, continent 0.150.
- DocETL's continent abstention (89% empty) helps only while the summed column over-counts. With correct teaching, DocETL's continent scores 0.547 against ours 0.677.
- **Our teaching over-counts:** ours = 1 on 452 documents; the correct data has 184.
  - Adjudication of 50 random disagreements (seed 0; ours = 1, correct = 0; `teach_sample.txt`):
    - 16 are correct-data misses, e.g. doc 265 "director and professor of graduate studies in sculpture at Yale University", doc 840 "taught weaving ... at the Kunstgewerbeschule Zurich", doc 123 "from 1894 to 1927 was the Professor of Painting there".
    - 7 are ambiguous, e.g. doc 852 "teacher of Edouard Detaille", doc 885 "Principal at the Winnipeg School of Art".
    - 27 are our reader's false positives, mostly study read as teaching: doc 575 "studied under Gustave Moreau and became his favorite student", doc 425 "was taught and supervised by ... Robert Morris", doc 100 "His teachers were Karl Bryullov".
  - Even against a corrected label (about 270 teachers), ours over-counts about 1.6x and DocETL's Q9 read (251 among our continents) about 0.9x.
- **The over-assertion is a property of the 7B reader, not of the shared read** (`teach_reads.py`). Share of documents read as 1, by setup:

| setup | said 1 | precision |
|---|---|---|
| 6-field read (no `art_institution` co-field) | 0.44 | |
| 15-field read | 0.45 | 0.36 |
| 15-field read without descriptions (E13-nodesc) | 0.45 | |
| nullable variant (E7) | 0.51 | |
| qwen32b | 0.32 | 0.48 |
| llama8b | 0.77 | |

- **DocETL's 19 distinct teaching reads** (`teach_docetl.py`): said 1 median 0.34 (range 0.22-0.57), precision 0.43. Q9's read is its most conservative (0.22, with 78% empty).
- **Robustness:** swapping each Q9 column with every other DocETL read keeps DocETL above ours. Medians: continent 0.581, teaching 0.547 (`docetl_wins.py`).

**art Q13** (`composition='Balanced'`, ours 0.097 vs DocETL 0.339).
- DocETL's only composition read with 'Balanced' in its SQL scores 0.339. Its 2 other reads score 0.000.
- All of our 0.097 comes from the representation layer: the raw view scores 0.000 (`revert_rep.py`).
- **Mechanism:** the correct data uses a closed label the reader does not produce by itself. Showing the constant tells the reader the label exists, so copying it into 84 documents (11 correct) beats never producing it.

**cspaper Q10** (ours 0.451 vs DocETL 0.750). With the correct `uses_knowledge_graph` in DocETL's table, its score falls to 0.451 (`col_oracle.py`). Its errors in that column (53% empty) offset its `application_domain` errors.

**cspaper Q17** (`LIKE '%Medical%'`). DocETL's `application_domain` reads whose SQL showed 'Medical' have a median of 0.104; reads that did not show it have a median of 0.028.

### F4. Constant priming is weaker in the control and, where strong, lands on queries nobody scores on
Precision of predicate matches (hits / all matches), `literal_prec.py`:

| collection | ours | DocETL, constant shown | DocETL, not shown |
|---|---|---|---|
| art | 0.705 | 0.628 | 0.676 |
| cspaper | 0.789 | 0.647 | 0.773 |
| player | 0.982 | 0.659 | 0.947 |
| med | 0.672 | 0.357 | 0.648 |
| legal | 0.738 | 0.475 | 0.739 |

- Showing the constant costs DocETL 0.05 (art) and 0.13 (cspaper) of precision, against 0.26-0.29 in the treatment collections.
- This replaces my earlier false-match-per-document comparison. That comparison rewarded abstention: DocETL leaves 84% of cspaper empty.
- Where art priming is large (`birth_city LIKE '%Paris%'`: DocETL 181 vs correct 31; `death_city`: 310 vs 58), the queries are single numbers that ours also misses (46, 34). The score difference is 0.

### F5. The representation layer has a small net positive effect on art, and none on cspaper
Script: `revert_rep.py`, which reconstructs raw values from `build.db` plus `patch_reads`; cells reachable through `__rep_map` are 100% for century, field, genre, tone and birth_country.
- art: raw 0.235 -> view 0.243 (+0.008, about 40% of our +0.019 edge).
  - Gains: Q11 +0.118, Q13 +0.097, Q18 +0.061, Q22 +0.024.
  - Losses: Q12 -0.062 and Q7 -0.034 (century '20th || 21st' -> '20th', and nationality first item), Q3 -0.023.
- cspaper: 0.071 -> 0.071.
- Without the layer, art's edge is +0.010.

### F6. No rows step in the control; within player, the rows step follows document length
Script: `rows_by_length.py`.
- art and cspaper rows step: 0.000 on both workloads. Drops are art 0.6% and cspaper 0-1.8%; median document length is 3.4k and 4.0k characters.
- Player, queries on the player table only (6.7k characters):
  - realistic: drop 0.142, rows step +0.052
  - drift: drop 0.069, rows step +0.009
- Player, queries touching team or city (61-77k characters):
  - realistic: drop 0.767, rows step +0.270
  - drift: drop 0.390, rows step +0.116
- **Breakdown:** legal has one length (19k characters) and a drift drop of 0.52, which depends on the field. Med realistic drops 4.7% but its rows step is -0.018. Drops predict that a rows step exists, not its sign.

### F7. Correct-data artifacts cap some control queries for both systems
Even with the correct column in either system's table, these stay at 0 (`col_oracle.py`):
- art Q6 (death_country blank -> NULL; correct 560, ours 210, DocETL 114)
- Q10
- Q20
- Q21

century is blank for 291 of 1000 artists, which caps Q7 and Q12 at 0.64.

### F8. Cost edge: the number of passes (unchanged)
DocETL / ours token ratios:
- art 5.95x
- cspaper 6.65x
- player 7.85x
- med 3.17x
- legal 9.98x (corrected from 7.5x)

## Tested and rejected

- **Majority/minority cell split as the control/treatment separator (withdrawn).** With symmetric imputation, legal shows the same parity as the control. With DocETL given the absence fill, query gaps are unchanged (F1). The cell gap among non-empty answers is similar in every collection (`stated_split.py`):
  - art +0.08 / +0.09
  - cspaper +0.03 / +0.17
  - player +0.10 / +0.15
  - legal +0.12 / +0.12
  - med +0.08 / +0.02
- **Correct value stated verbatim in the text as the mechanism (rejected).** Within collections, the gap is not larger on stated cells. Gap after the fill, stated vs not stated:
  - art +0.106 vs +0.206
  - cspaper +0.151 vs +0.259
  - player +0.256 vs +0.172
  - legal +0.290 vs +0.180
  - med +0.067 vs +0.094
  
  The pooled correlation is a difference between collections.
- **Documents per answer cell (support) as the reason (partial only).** Pooled, the gap falls with support (Spearman -0.40, p = 2e-5). But low-support control queries (support < 3) still show no edge: art +0.011 (n=4), cspaper -0.006 (n=5). Within collections, only player is significant (`support.py`).
- **Worst-column-accuracy threshold (rejected).** Med has worst-column accuracy of 0.14 for ours (18 of 20 queries below 0.4), yet it has a +0.139 gap. Cell accuracy misses predicate-level correctness (`threshold.py`).

## Noise

- **DocETL read-to-read noise** (`docetl_noise.py`): each used column is resampled from DocETL's other distinct reads, 20 resamples.
  - art DocETL mean 0.207 (sd 0.018, range [0.177, 0.238]); ours (0.243) is above all 20. DocETL's actual run scores 0.225.
  - cspaper DocETL mean 0.023 (range [0.006, 0.047]), while its actual run scores 0.068 and ours 0.071.
  - So DocETL's realistic control runs sit at the top of their read distribution. Part of that is priming: resampled reads mostly did not see the query's constant, as Q13 shows.
- **Our replicates** share build reads (byte-identical `build_reads`), so they measure patch noise only.

## Untested

- Full-text cspaper, where the evidence is outside the 4,000 characters, needs new documents and model calls. Without full text, the column oracle shows the binding columns for most cspaper queries are list columns (generator_model, evaluation_dataset, evaluation_metric, baseline: ours 0.02-0.04) or derived group keys (retrieval_method ours 0.42 vs DocETL about 0.03), not the Yes/No columns where our recall advantage lies.

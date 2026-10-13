<!-- Verification by hand after the multi-agent run (2026-10-13):
- Legal type-check artifact: confirmed. judgment_year, hearing_year, first_judge, fine_amount are declared value_type str; 62,502 "Validation failed" lines in logs/docetl_legal.log, dominated by integer outputs (first_judge 29,096, judgment_year 23,011, legal_basis_num 16,267, fine_amount 4,968); DocETL converts string arguments with ast.literal_eval (systems/docetl-main/docetl/operations/utils/api.py:1226).
- Cost: confirmed from build.json + streams/fixed4-realistic_100.jsonl (legal 4.56M + 5.31M = 9.87M; player 5.99M). usage.jsonl is NOT usable for this: it carries history cloned from earlier runs (legal 99M).
- Largest call of ours over all logged runs: 12,264 input tokens (report says 10.6k for this run); still below the ~14k step.
- med Q8: DocETL's manufacturer contains "Pfizer" in 28 rows (incl. prose replies); 21 of those documents never mention Pfizer (report: 22 / 15 counting exact values only). Direction confirmed.
-->
# What carries our system's accuracy and cost edge over DocETL

Scope: realistic v1 workload, Qwen2.5-7B-instruct through local Ollama, scores at tolerance tau = 0.2 unless stated (tau = share of the correct column's range; single numbers are always scored exactly). Drift = the template workload. All evidence is post-hoc on saved reads, logs and tables. No model was called. Per-area notes: `edge/<area>/FINAL.md` (player, med, legal, control, cost).

Terms used throughout (one term per concept):
- **dropped document**: DocETL stores no row for a document, because its answer failed the output contract after retries.
- **protocol failure**: a DocETL reply that is not a valid tool call (empty reply, prose, or a value of the wrong declared type).
- **false match**: a document counted by a WHERE/LIKE filter whose correct value does not satisfy the filter.
- **abstention**: an empty answer (NULL) where the correct value exists.
- **absence fill**: our code writes 0 or No when the reader returns null for a never-null count or Yes/No field (`context_probe.absence_value`).
- **pass**: reading every document of a table once.
- **swap steps**: DocETL's table repaired cumulatively with our values: rows (add dropped documents), empty (fill abstentions), values (replace the rest; equals our score).

Gaps (ours - DocETL, mean query score, recomputed from `WHY/swap`): realistic player 0.459, legal 0.149, med 0.139, art 0.018, cspaper 0.002 (sum 0.767; player 60%, legal 19%, med 18%). Drift: player 0.296, legal 0.097, art 0.083, cspaper 0.033, med 0.022.

## 1. Answer in one paragraph

The accuracy gap is not one property, and it is not "better reading" in general. It has three parts, and their mix differs by collection. (a) **Whether a document's answer survives the output contract.** DocETL sends the whole document in one call and requires a typed tool call. The 7B model fails that contract above about 14k tokens per call, or when a declared type contradicts the natural answer. Our reader never makes a call above 10.6k tokens, accepts free JSON and always keeps one row per document. This accounts for 66% of the player gap and 68-88% of the legal drift gap, and the legal part is an artifact of our harness configuration. (b) **What the reader is told about the answer space, and where that information is applied.** Our side applies absence values in code, forbids null, lists allowed labels (the template workload's constants happen to be the majority labels) and nulls labels outside the set. DocETL frames the query's constant as an SQL predicate and copies the description's example values. The result is a false-match rate about 3x lower in med, fewer spurious groups and abstentions in legal, and zeros instead of NULLs in drift. (c) **The scorer amplifies small per-document differences.** Exact single numbers, group-key structure and two-sided join keys turn modest precision differences into 0/1 outcomes (72% of the med gap). Three things do not carry the accuracy edge: reading once and sharing the result (DocETL's own reads shared across queries move its score by -0.028 to +0.024), the representation layer (about 0, except +0.008 on art) and decoding temperature. The cost edge comes from the **number of passes per table**, mostly from reading columns before any query asks for them (36-75% of the log token ratio), less from reuse alone (3-47%). The cost per read is about equal at equal field sets. Cost and accuracy share a cause only through DocETL's protocol failures, which both drop rows and spend retry tokens (legal, player). On "it cannot really be the prompt": the wording is not the cause, but the information the prompt and code carry (output contract, absence semantics, label set, how a constant is framed) is a large part of it. The single largest item is call size under a strict output contract.

## 2. Causes, ranked by share of the gap

Shares come from different decompositions (swap steps, Shapley over error kinds, per-query bootstrap), so they overlap and must not be summed across rows. "Points" = mean query-score points within the collection.

| Rank | Cause | Where it matters | Points (share of that gap) | Approx. share of summed realistic gap |
|---|---|---|---|---|
| 1 | Call size vs strict output contract (protocol failure) | player | 0.307 of 0.459 (65.7%); drift 41.1% | ~40% |
| 2 | Exact single-number scoring over a lower false-match rate | med (also player QJ17) | ~0.100 of 0.139 (72%) | ~13% |
| 3 | Answer-space information: closed label set + abstention policy | legal | structure 27% (tau 0.2), Q3+Q4+Q10 28% | ~10% (the two overlap) |
| 4 | Value form set by the co-read field set | player | ~17.5% of the gap (FORM) | ~10% |
| 5 | Type-check drops (harness artifact) | legal | drift 68-88%; realistic <= 24% (upper bound) | <= 5% realistic |
| 6 | Absence fill in code | drift: cspaper, art, player, legal | drift cspaper 86%, art 23%, player 20%, legal 19%; realistic about 0 | ~0 realistic |

### 2.1 Call size vs a strict output contract (player; 65.7% of the realistic gap)

- **Property.** Tokens per call under a strict tool-call contract. DocETL puts the whole document in one call (team/city documents 15-32k tokens) and requires a tool call with declared types. Our reader chunks at about 8k tokens (over 4,913 calls: median 6.7k, p95 9.9k, max 10.6k), accepts free JSON and writes one row per document whatever the reply.
- **Effect.** Shapley share of the long-document mechanism: 0.307 points (65.7% of the realistic gap); 41.1% of the drift gap. Drop rate is a step, not a slope. Below 14k tokens it is 0-5% for every table when the field set lacks championship (team 3/104). At 14-16k it is team 0.56 and city 0.59; at 16-18k team 0.85, city 0.92, player 0.50. Documents of 14.5k tokens or more hold 455/493 (92%) of realistic drops. Removing team repairs -0.308 of the gap, city -0.224, player -0.006.
- **Mechanism.** Below the step, DocETL's own template succeeds 95-100% of the time with the same instructions, temperature and contract. Call size is therefore the variable that switches failure on inside DocETL's own setup (confounded with document identity). Of 6,566 logged failures, 69% are empty replies (no text, no tool call) and 20% are prose holding valid JSON, so a lenient parser would recover at most about 20-28%. A failed document tends to keep failing: retries succeed for 16-24%. A second trigger works on short documents: team.championship is typed str, and the model answers with a number. With championship in the field set, 11/18 team documents of 8-14.5k tokens are dropped, against 3/104 without it.
- **Cases.** real:player#QJ15 (championship): DocETL drops 23/30 team documents and scores 0.000, ours 0.749. Where DocETL answers, it writes '2016 NBA Championship' for doc 6 (correct 1) and '1979 NBA Championship' for doc 21 (correct 0); ours reads 18.0 for doc 2 (correct 18). real:player#QJ17: the city (city_name, population) run dropped 23/29 documents.
- **Conditions.** Documents of more than about 14k tokens with a 7B model and a typed tool-call output, or any document whose declared type contradicts the natural answer.
- **Breakdowns.** Above the step, player documents fail less often than team/city documents of the same length (18-22k: 0.20 vs 0.75/0.84), unexplained. Our reader has never made a call above 10.6k tokens, so which of its parts keeps it clear (chunking, field placement after the document, free JSON, temperature 0.1) is untested. Cross-check in the control: within player, player-table queries (6.7k characters) have drop rate 0.142 and rows step +0.052, while team/city queries (61-77k characters) have drop rate 0.767 and rows step +0.270. Med drops 4.7% but its rows step is -0.018, so drops predict that a rows step exists, not its sign.

### 2.2 Exact single-number scoring over a lower false-match rate (med; 72%)

- **Property.** A single number is scored 0/1, and each count sums true and false matches over documents. Underneath, the two readers differ in per-document filter precision.
- **Effect.** Exact hits are worth +2.0 of med's 2.78 summed gap: Q8, Q12 and QJ4 for ours (+3), Q6 for DocETL (-1). Graded instead of 0/1, ours is closer in 12 of 13 single-number queries (median |log ratio| 0.41 vs 1.44) and within 20% in 5/13 vs 1/13. The per-document edge is precision, not recall. On single-chunk documents (both systems read the whole document in one call): ours true-match 0.61 / false-match 0.137 / F1 0.540; DocETL 0.72 / 0.461 / 0.370. On multi-chunk documents with our first chunk only: 0.47 / 0.073 / 0.523, against DocETL 0.65 / 0.400 / 0.377.
- **Mechanism.** DocETL overcounts in 12 of 13 queries, so its counts rarely land on the correct value. Ours can land on it, sometimes through errors that cancel. Many of DocETL's extra false matches are not supported by the text. On single-chunk documents, DocETL has 250 false matches where the text never contains the constant, against our 55 (4.5x). Over all filters, DocETL has 874 false matches (414 unsupported, 126 prose replies, 93 of them quoting the query); ours has 302 (94 unsupported). Showing the constant is not sufficient to cause this. In our reader, the usage phrase on vs off gives false-match rates of 0.016 vs 0.019 (Bayer 0/157 in both arms). DocETL echoes the same constants when they sit in its SQL and not otherwise: Bayer 37/315 vs 0/417, Pfizer 27/96 vs 0/643, lung 51/87 vs 6/83. The cause lies in the framing (an SQL predicate, one field per call, a whole-document window), and these three factors are not separated.
- **Cases.** real:med#Q8 ("drugs made by Pfizer"): correct 2, ours 2 (1 true + 1 false), DocETL 28. DocETL writes 'Pfizer' for 22 documents, 15 of which never mention Pfizer: 422147 (Boehringer Ingelheim), 461870 (Janssen), 489250 (Alfasigma) and 97675 (Centurion), all read correctly by ours. real:med#Q12: correct 21, ours 21 = 12 true + 9 false (9 misses), DocETL 65. real:med#QJ4: correct 3, ours 3, but none of our three pairs is a correct pair; DocETL 26.
- **Conditions.** Single-number counts over low-base-rate filters on about 100 documents, so an exact hit is reachable.
- **Breakdowns.** Exact hits are unstable: Q8 is exact in 1 of 3 replicates, and so is Q13 (replicate means 0.259 / 0.259 / 0.209). Q12 and QJ4 come from a build that was never re-sampled. On documents over 20k tokens, chunk merging raises our false-match rate to 0.343 (F1 0.327, against 0.538 for the first chunk alone). On short documents (under 6k tokens), DocETL finds 22/27 positives and ours 9. Chunk merging gives the Q12 hit (first chunk only: 16; merged: 21). The model-free item filter contributes about 0. The same mechanism appears in player: real:player#QJ17 (exact COUNT over a join) needs every team.location right. Correct 10, ours 10, DocETL 0, with 6 prose answers, 5 None, 'Los Angeles' for Miami and 'Orlando, Florida'.

### 2.3 Answer-space information: closed label sets and the abstention policy (legal; overlapping 27% and 28%)

- **Property.** For categorical columns our prompt states the allowed values, lists up to three workload constants and says "Never null", and a conform step nulls labels outside the set. DocETL answers in free text, may answer empty ("if unknown, return empty string") and shows only the description's example plus the constants in the current SQL.
- **Effect (labels).** At tau 0.2 the group-key (structure) part of the legal gap is 0.594/2.237 (27%); at tau 0 it is 16%. Number of groups, correct / ours / DocETL: Q2 16/12/41, Q4 52/83/148, Q8 3/4/6, Q15 8/10/19. Putting our verdict column into DocETL's table: Q2 0.184 -> 0.460, Q8 0.123 -> 0.667, Q11 0 -> 0.160 (+0.98 summed). Conform alone is 5.6% / 3.8% / 5.7% / 15.5% of the gap at tau 0 / 0.05 / 0.1 / 0.2. It holds on Q2 across 3 identical DocETL reruns (+0.18 to +0.20) but not on Q1 (-0.14 to +0.14).
- **Effect (abstention).** Bootstrap ours - DocETL, robust from tau 0.05 up: Q3 +0.198 [0.115, 0.285], Q4 +0.275 [0.162, 0.383], Q10 +0.198 [0.092, 0.298] at tau 0.2; Q10 +0.246 [0.149, 0.341] at tau 0. Q3+Q4+Q10 sum to 28% of the gap at tau 0.2 and 38% at tau 0. Our judge column in DocETL's Q4 table: 0.135 -> 0.347.
- **Mechanism.** The score is structure F2 over group keys times cell F1, with tolerance relative to the column range, so every extra label (prose, 'Dismissible', 'Not Guilty', the NULL group) costs structure, while count errors in small groups pass at tau 0.2. For abstention: the judge is named once, in the certification line near the end, after character 2000 in 536/570 documents. DocETL leaves it empty in 32-38% of documents even when they are short (doc 103: 423 tokens, name at character 1537), whereas ours leaves 0 empty and gets 511/570 surnames right. DocETL's abstention changes with the query's prompt (judge 2-83%, case_type 4-85% across maps, against 7.4-8.6% for an identical-prompt rerun), not with reading ability. When the SQL shows a judge constant, it reads 496/552 surnames correctly. A related effect is anchoring on the description's example label. When the SQL shows no other label, DocETL's Criminal share is 0.22-0.61 (correct 1.8%, ours 1.4%); when it shows non-criminal labels, 0.055-0.139.
- **Cases.** real:legal#Q8: DocETL makes 6 groups (structure 0.556). With our verdict column the same table makes 3 groups (structure 1.0) while still selecting only 52 of 237 relevant cases; both systems miss the big Dismissed count (correct 211, ours 138, DocETL 36). real:legal#Q4: DocETL's 196-document NULL group becomes real judges, and its group count falls from 148 to 116.
- **Conditions.** GROUP BY or WHERE on a categorical column, a metric that charges for extra groups, and values that are stated but need a small inference.
- **Breakdowns.** The label benefit depends on the template workload's constants being the majority labels; minority constants would pull the other way. Our per-document case_type is no more accurate: 'Civil Case' on 451/570 documents, of which 235 are correctly Administrative; 272/570 right overall, against 249-262 for DocETL. real:legal#Q14 goes against us (DocETL 0.320, ours 0.185). "Never null" invents values: we give a nationality on 59 documents whose correct value is empty (DocETL 18), and our Australia count of 83 equals the correct 83 by coincidence (only 20 of those documents get Australia). Nulling DocETL's anchored labels lowers its score (-0.138), so its loss is per document and a post-step cannot remove it.

### 2.4 Value form set by the co-read field set (player; ~17.5% of the gap)

- **Property.** Which fields are read together. DocETL reads exactly the query's columns; ours reads the union of the build workload's columns for the table.
- **Effect.** Within player's values step (48% of the gap; Shapley over error kinds at tau 0.2): PROSE 33%, FORM 36%, NUM 20%, WRONG 16%, OK -5%. Interaction is 41% (23% at exact scoring), and 66% of it sits in QJ17 and QJ19. team.team_name read together with location gives short forms in 48.6-55.2% of answers. Read alone it gives 0.2%; with championship, 0/69; at our field set, DocETL gives 2/48 short and ours 0/30.
- **Mechanism.** This is a property of the 7B model, not of our reader. Our own single-field owner probes shortened 'Israeli-American' to 'American' and 'Taiwanese-Canadian' to 'Canadian', while our (name, nationality) read kept the full forms. The edge comes from DocETL's per-query field set happening to be a form-shifting pair, which ours was not. For joins, both sides must agree with each other, not with the correct data. In real:player#QJ19, our team.ownership and owner.name share the same short names ('Stan Kroenke', 'Dan Gilbert'), so the join matches; fixing one side of DocETL gives 0, both sides 0.667.
- **Cases.** QJ19: DocETL's ownership is 'Jeanie Buss' (the description's example) for doc 3 (correct Joseph Chung-Hsin Tsai) and doc 20 (correct James Lawrence Dolan), and 'Carnival Cruise Lines' for doc 16 (correct Micky Arison). DocETL also copies SQL constants onto the wrong documents: 'American-born naturalized Azerbaijani' 139 times on doc 134 (correct Mexican-American; ours Mexican-American).
- **Breakdowns.** A workload whose union field set is a bad pair would hurt ours as well. 'Concise and normalized' wording, example priming and temperature are not separated. Owner evidence is n=2. QJ19 scores 0.667 for ours even though American is 4 against a correct 14.

### 2.5 Type-check drops (legal; a harness artifact)

- **Property.** On the Ollama path, DocETL applies `ast.literal_eval` to string tool arguments, so '2008' becomes 2008. Our harness declared digit-valued fields as str (judgment_year, hearing_year, first_judge, fine_amount), so validation rejects the int. After 3 in-call retries the document is dropped, and the harness's second pass repeats the cycle.
- **Effect.** Drift: adding the dropped rows recovers 68% / 79% / 80% / 88% of the legal gap at tau 0 / 0.05 / 0.1 / 0.2. Realistic, only Q5 and Q15: 8% (tau 0), 25% (tau 0.05), 23% (tau 0.2). Rescoring with both drops and wrapped years fixed: Q5 0.000 -> 0.356 (ours 0.323), Q15 0.022 -> 0.196 (ours 0.212). That puts the realistic upper bound at about 0.035 of the mean, or 24% of the gap.
- **Mechanism.** The log has 62,502 'Validation failed' outputs. Rejected judgment_year values are int years (2006: 2,924; 2007: 1,761); -1 appears twice. The surviving rows are often written after DocETL's retry message as JSON text ('{"hearing_year": 2007}'), so they land in wrong groups. The drop and the wrapping multiply. A COUNT per group needs nearly every document: with partial coverage Q5 scores 0 even when the added rows carry our values. With full coverage from DocETL's own surviving year reads (84% correct), Q5 scores 0.294.
- **Cases.** real:legal#Q5 keeps 79/570 rows (4,160 calls, 22.7M tokens); real:legal#Q15 keeps 56 rows (4,270 calls, 24.0M tokens).
- **Breakdowns.** This is not a property of DocETL's design. Typing the fields int, or a provider without the literal_eval branch, should remove it (not rerun). Counterexample: attr:Splits/train.sql#12:66cde6f4 drops 510/570 documents yet scores DocETL 0.22 against ours 0.0. **The paper's legal drift comparison is not valid until this is rerun.**

### 2.6 Absence fill in code (drift only)

- **Property.** For never-null count and Yes/No fields, our code writes 0 or No when the reader returns null. DocETL stores NULL.
- **Effect.** Giving DocETL the same fill: realistic gaps barely move (art +0.019 -> +0.007, player +0.459 -> +0.453, med and cspaper unchanged; 3 of 107 queries move). Drift: closes cspaper 86% (+0.033 -> +0.005), art 23%, player 20%, legal 19%, med 0%; 41 of 284 queries move. Player's EMPTY0 share is 23.5% of the drift gap and 2.2% of the realistic gap.
- **Mechanism.** The fill changes an answer only where the query treats NULL differently from 0/No: AVG, MIN, COUNT(col), GROUP BY on the column, or an all-NULL group. Realistic v1 uses these columns mostly in SUM, ='Yes' or >=1 (29 of 107 queries); the drift templates use them in 127 of 284, often with AVG, MIN or COUNT(col). Our model also leaves the field null (olympic_gold_medals: 106/114 documents whose correct value is 0, despite "Never null"), so the 0 comes from code, not from reading. Natural experiment: mvp_awards' description says "use 0 if none". There our model writes 0 itself (110/124), and DocETL's empty rate falls to 20.6% (olympic 83.0%, nba_championships 95.8%).
- **Cases.** Drift cspaper groupby20:q7: DocETL 0.192 -> 0.402 with the fill (ours 0.784). real:art#Q16 AVG(awards): DocETL 0 -> 0.25 (ours 0.25).
- **Breakdowns.** Separating NULL-sensitive from NULL-insensitive query forms by regex works poorly on drift (35% vs 28% of queries moved). Over all cells whose correct value is 0, our olympic false positives are worse than DocETL's (7.0% vs 1.9%). DocETL's count false positives copy the description's example number (mvp 2: 52%; olympic 3: 62%) and ours do not; why is untested.

### 2.7 Checked and found not to carry the accuracy edge

- **Reading once and sharing.** DocETL's own reads, one read shared across all queries / consensus over its reads / as run / ours: player 0.114 / 0.172 / 0.105 / 0.564; legal 0.083 / 0.104 / 0.109 / 0.258; med 0.103 / 0.098 / 0.120 / 0.259. Rebuilding DocETL's 20 player join queries from one donor read per table scores 0.038 against 0.037 actual (ours 0.643). The join-key gap (earlier 0.75/0.97 vs 0.19/0.20) comes from per-read key accuracy, not from reuse.
- **Representation layer.** Med: reverting entity-resolution and group rewrites changes only QJ1 (0.037 -> 0.0325). Player: zero rewrites. Art: net +0.008 (gains Q11 +0.118, Q13 +0.097; losses Q12 -0.062, Q7 -0.034 from '20th || 21st' -> '20th'). cspaper: 0.
- **Decoding temperature** (DocETL uses Ollama's default 0.8, ours 0.1). Three identical DocETL runs disagree per document on 27-30% of case_type answers, and their Q2 scores are 0.184 / 0.233 / 0.209. A majority over 3 runs leaves Q2 unchanged (0.189-0.212). Player: majority over 3-4 runs raises cell accuracy 0.443 -> 0.489 (nationality 0.58 -> 0.78) but leaves join keys (location 0.21 -> 0.19). Single DocETL runs carry about ±0.025 of score noise per query.

## 3. The control: art and cspaper (gap 0.018 and 0.002)

Do the causes above predict a small edge here? Mostly yes, though this was checked after the fact.

- **No dropped documents, as cause 1 predicts.** The documents are short (3.4k and 4.0k characters). Drop rate is 0.6% (art) and 0-1.8% (cspaper); the rows step is 0.000 on both workloads.
- **Exact scoring hides an ordinal edge (cause 2's condition fails).** On single-number queries ours is closer in 12 of 12 (art median relative error 0.45 vs 0.67, cspaper 0.83 vs 0.99), but both systems score 0 on all 12. The correct counts are large (31-575 out of 1,000 documents), so even a 1.5% false-match rate rules out an exact hit. Examples (correct / ours / DocETL): art Q5 31/46/181, Q20 575/311/262; cspaper Q9 66/8/1. In med the counts are 2-57, so the same edge becomes 0.100 of the gap.
- **Priming costs DocETL less precision.** Match precision, constant not shown -> shown: art 0.676 -> 0.628 (-0.05) and cspaper 0.773 -> 0.647 (-0.13), against -0.26 to -0.29 for player, med and legal. Most art conditions are '=' on columns where the shown constant barely changes the reads (false-match rate 0.023 -> 0.030). Where art priming is strong (LIKE '%Paris%': false-match rate 0 -> 0.156), it inflates single numbers that both systems miss anyway.
- **Absence fill (cause 6) explains nearly all of cspaper's drift edge (86%) and 23% of art's**, and about nothing on realistic v1, as its query-form condition predicts.
- **DocETL's wins come from cancelling errors or from a disclosed label, not from better reading.** In art Q9 (ours 0.338, DocETL 0.656), our reader says teaching = 1 for 452 artists against a correct 184. On 50 adjudicated cases: 27 are reader false positives (study read as teaching, e.g. doc 575 'studied under Gustave Moreau'), 16 are misses in the correct data and 7 are ambiguous. DocETL's 89% empty continents push teachers into a NULL group, which offsets the overcount. With the correct teaching column, DocETL's continent scores 0.547 against ours 0.677. In art Q13, DocETL scores 0.339 only with the read whose SQL showed 'Balanced' (other reads score 0.000), and our 0.097 comes entirely from the representation layer. cspaper Q10 and Q17 follow the same two patterns.
- **Correct-data limits apply to both systems.** art Q6, Q10, Q20 and Q21 stay at 0 even with the correct column. century is blank for 291/1000 artists, which caps Q7 and Q12 at 0.64.
- **Noise.** Resampling DocETL's art reads from its other reads of the same column gives 0.207 ± 0.018 (range 0.177-0.238); ours (0.243) is above all 20 resamples. DocETL's actual 0.225 sits near the top of its own distribution. Priming and read noise are confounded in this resample.

## 4. What is specific to a 7B model and may shrink with frontier models

Likely to shrink:
- **Protocol failure on long calls (cause 1).** It accounts for 69% empty replies, the 14k-token step and prose stuffed into fields. A frontier model breaks a tool-call contract far less often, so the 65.7% player share, and DocETL's retry spend, should fall.
- **Copying example values from the description or the SQL.** Examples: 'Jeanie Buss', '(e.g., N)' counts, 'Criminal Case', 'Pfizer', 'American-born naturalized Azerbaijani'.
- **Form shift by co-read fields** (short vs full names), and prompt-dependent abstention (2-85%).
- **Over-assertion of teaching.** Our reader says 1 for 0.44-0.45 of artists in every field set, against 0.32 with qwen32b and 0.77 with llama8b. This shows the effect is a property of the model.
- **Temperature-0.8 sampling noise** in DocETL's reads.

Not model-specific, so expected to persist:
- **Scorer amplification.** Exact single numbers, group-key structure and two-sided join agreement.
- **Absence fill in code.** It is an asymmetry in schema information: is_nullable is applied by our code, and DocETL only sees the description text.
- **Closed label sets.** A conform step that nulls out-of-set labels is model-independent, but how much it is worth depends on how many out-of-set labels the model emits.
- **The legal type-check artifact.** It is a configuration bug, independent of model quality; it should be fixed, not attributed.
- **The cost edge (number of passes).**

## 5. Withdrawn under challenge (do not repeat)

- "Reading once and sharing gives consistent join keys, and that is our edge." Rebuilding DocETL's joins from one donor read gives 0.038 vs 0.037; the read-once counterfactual moves DocETL by -0.028 to +0.024.
- "Re-read inconsistency links the cost and accuracy edges." The only shared cause is protocol failure (mainly legal coercion).
- "Our recall edge from 'never null' plus committing to the constant" (med). There is no recall edge on single-chunk documents (0.61 vs 0.72); the edge is precision.
- "Showing the constant causes DocETL's false matches." Our reader shows constants without echoing them (0.016 vs 0.019); the cause is the framing, and its factors are unseparated.
- "QJ2 = 0 is tolerant-tier contamination" (med). QJ2 is a valid 0.286. The stream's 0.0 came from a missing signature column (`sig_4e499c217891_r`), which moves our med mean 0.245 -> 0.259.
- "Companion fields cause DocETL's abstention" (legal). The same field set under different SQL gives 0.13 vs 0.42 empty.
- "The Q12 fold drives legal." Bootstrap +0.157, CI [-0.185, 0.536].
- "A majority/minority cell split separates the control from the treatment collections." Symmetric imputation removes it.
- "NULL-as-absence explains art Q9." It is a cancelling error between teaching and continent.
- "Our reads are more expensive per read (0.58-0.81)." At equal field sets DocETL's first pass costs 0.92-1.23 times ours.
- "Read count explains 87-139% of the cost ratio" and "99/107 zero-call queries come from reuse." Without foresight, reuse alone gives 32/107 zero-call queries.
- "Every protocol failure gets 3 validation retries." A no-tool-call reply is skipped after one call; only type-check failures retry 3 times.
- "Wall-clock ratios of 1.4-6.3x." The runs shared a server (implied concurrency 6.8-7.9, num_ctx 32768 vs 16384), so time is not comparable.
- "No null per-chunk keys." The correct figure is state_name 61/67 with 6 null chunks and 0 wrong.

## 6. The cost edge

- **Property.** A pass costs about the table's document tokens, whatever the number of columns: each extra column adds only 34-87 input and 9-21 output tokens per chunk. DocETL makes one pass per (query, table). Ours makes a pass only when its stored columns fall short of a query. Foresight (the template build plus a catalogue planner that reads every remaining column of a table in one patch) fills columns in advance.
- **Effect.** Input-token ratio DocETL/ours, build charged: art 6.23, cspaper 6.86, legal 10.13, med 3.20, player 7.91. Ladder of plans, each priced at our measured per-document cost:
  - B (our reader on DocETL's plan): 1.10-1.64.
  - C (reuse only, patch only missing columns): 1.62-3.80, with 32/107 zero-call queries.
  - D (template build plus patch-only): 2.75-6.28, with 71/107.
  - E (as run): 3.20-10.13, with 99/107.
  - F (read-once bound): 12.8-23.5.

  Share of the log ratio:

  | Component | art | cspaper | legal | med | player |
  |---|---|---|---|---|---|
  | Reuse alone | 0.19 | 0.29 | 0.03 | 0.33 | 0.47 |
  | Template-build foresight | 0.24 | 0.21 | 0.29 | 0.51 | 0.24 |
  | Catalogue foresight | 0.45 | 0.40 | 0.46 | 0.07 | 0.11 |
  | Per read plus failures | 0.12 | 0.10 | 0.22 | 0.08 | 0.18 |
- **Mechanism.** Reuse saves a pass only when every column a query needs is already stored. In legal almost every query brings a new column, so reuse alone gives 1 zero-call query out of 15. DocETL pays the document cost again for every query: player.team and team.team_name are read 13 times, team.location 10, art.birth_continent 7. Its protocol failures add spend. The harness's second pass is 25.3% (legal), 27.6% (player) and 9.0% (med) of DocETL's tokens and changes the score by at most 0.005. Legal Q5 and Q15 alone are 47.6% of DocETL's legal tokens.
- **Case.** Legal: DocETL 98.08M tokens over 16,146 calls. Ours 9.87M: build 4.56M plus one patch at Q3 (5.31M, including 220 probe calls); 14 of 15 queries made 0 calls. Player: DocETL 46.9M against ours 5.95M; 25 of 28 queries made 0 calls.
- **Breakdowns.** The edge belongs to materialising once over a schema that covers the workload, which is an asymmetry in planning information. Our reader does not cause it. A DocETL given the same column list (one map per table, then SQL) would be about 2-4x cheaper than ours; for legal the estimate is about 4-4.5M against our 9.87M. Ours is 2.2-4.0x above the read-once bound because of unused build columns, a second group pass and probes (36-38% of our total on med and player). On a tiny table (owner: 16 documents, 2 queries) DocETL is 2.6x cheaper. On drift, foresight is only 0-15% of the log gap. The ladder is modelled; the per-document price is within -22% to +65% of measured runs.
- **Coupling with accuracy.** Only through protocol failures. Pass count and foresight carry 78-92% of the log token ratio but move accuracy by 0.03 or less.

## 7. Unexplained, and the decisive tests left

Model calls are needed for 1-6 (GPU, the user's go-ahead):
1. **Rerun DocETL with digit fields typed int**, and with raw tool-call arguments logged: legal Q5, Q15, three drift maps, and player QJ15/QJ20 (championship). This removes the harness artifact, and is needed before the legal drift and player championship numbers go into the paper.
2. **Separate the parts of the protocol-failure cause.** Run our reader in one-call whole-document mode above 14k tokens, then switch on chunking, free JSON, field placement and temperature 0.1 one at a time. A complementary arm: DocETL on chunked documents. This test decides cause 1.
3. **Separate DocETL's constant echo** (med 250 vs 55 unsupported false matches). Arms: SQL constant masked, one field vs many fields, whole document vs chunks. Also explain DocETL's higher recall on single-chunk documents (0.72 vs 0.61).
4. **Example copying.** Rerun DocETL with the description examples removed ('e.g., Guilty', '(e.g., N)', 'Jeanie Buss'), and with the three majority verdict labels shown (the verdict half of legal anchoring is still untested).
5. **Temperature.** Repeated identical prompts at 0.1 and 0.8 for both readers, to separate sampling from prompt effects (SQL, co-read fields).
6. **Re-sample the build reads** to test whether the exact hits on med Q12 and QJ4 are stable.

Model-free, possible now:

7. Audit every stream-recorded score for the missing-signature-column artifact found on med QJ2.
8. Run a patch-only replay with the planner off, from the read journal, to replace the modelled cost ladder with measured numbers.
9. Re-report every share at tau 0 / 0.05 / 0.1 / 0.2. Several shares depend strongly on tau: legal type-check drops 68-88% (drift) and 8-25% (realistic); structure 16% -> 27%; the player values interaction 23% (exact) -> 41%.

Still open, with no test designed yet: why player documents above 14k tokens drop less often than team/city documents of the same length; the WRONG-kind cells (16% of player's values step); legal Q9 (we produce 110 groups against 39 correct) and Q11 (both systems score 0); why med's rows step is negative; and why foresight is worth 40-46% of the cost ratio on realistic art, cspaper and legal but 0-15% on drift (working hypothesis: how new columns arrive in each stream).

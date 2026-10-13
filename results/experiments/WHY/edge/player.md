# Player: what carries our system over DocETL. Revised after the devil's advocate

No model calls were made. Scripts are in `revise/` (new) and in `challenge/` and the parent folder (earlier). Run them from the repo root with the environment given in the task. Realistic v1 workload, 28 queries; tau 0.2 unless stated.
Gap: DocETL 0.105, ours 0.564. The exp_swap steps take: rows 26.6%, empty 25.2%, values 48.2%.

## Status of the original claims

| # | Original claim | Status | Why |
|---|---|---|---|
| 0 | Size per call: DocETL's whole-document call fails the tool-call protocol on long documents, and those losses are ~66% of the gap | **Revised** | The share holds. The property is narrower than "size": a step at ~14k tokens, plus a separate field-type trigger. Our reader never makes a call in the failing region, so the operative part of our prompt is untested. |
| 1 | Reading once and sharing gives consistent join keys | **Withdrawn** | Requested test run: DocETL's join queries rebuilt from one donor read per table score 0.038 vs 0.037 actual (ours 0.643). |
| 2 | Co-read fields change value form; ours avoids short forms | **Revised** | It is a property of the model's field set, not of our reader. The nationality "leak" is mostly rebutted: ours is full-form on 4/5 documents whose value was never shown. |
| 3 | The "values" step is explained by kinds of DocETL error | **Revised** | Shapley shares: PROSE 33%, FORM 36%, NUM 20%, WRONG 16%, OK -5%. The interaction is 41%, and two queries hold 66% of it: an exact-scored COUNT (QJ17) and a two-sided join key (QJ19). |
| 4 | DocETL's numeric false positives and empty zeros are reading errors | **Revised** | EMPTY0 is not reading: both models leave unmentioned counts null, and our code turns null into 0 using the schema's is_nullable. NUMFP: DocETL copies the description's example number and we do not. The cause is untested. |
| 5 | Cost: ours 5.99M tokens vs DocETL 46.9M | **Kept** | Verified, and the mechanism is sharpened: a patch reads every remaining column of a table. The 49% wasted share is still an estimate. |

---

## F1 (revised claim 0). A document that ends up in one call of more than ~14k tokens fails DocETL's tool-call protocol. Our reader never makes such a call.

**Property.** DocETL sends the whole document in one call and needs a tool call back. Our reader chunks at ~8k tokens: in 4913 calls, the median prompt is 6.7k tokens, p95 9.9k and max 10.6k. It accepts free JSON (0 empty and 12 unparseable responses).

**Effect.**
- Realistic, field sets without championship (`revise/drops_realistic.py`):
  - Below 14.5k tokens: team 3/104 documents dropped, player 15/1652, city 7/36.
  - At or above 14.5k: team 97/136 (71%), city 190/225 (84%), player 139/322 (43%).
  - The documents at or above 14.5k account for 92% of all realistic drops (455/493).
- Finer bands, realistic and drift together, no championship:
  - 0-14k: 0-5% for every table (city 13-14k 0.33, n=3 documents).
  - 14-16k: team 0.56, city 0.59, player 0.01.
  - 16-18k: 0.85 / 0.92 / 0.50.
  - 22k and above: 0.85 / 0.94 / 0.66.
- The Shapley share of the protocol failure (rows + prose + empty answers from long documents) is 65.7% of the realistic gap and 41.1% of the drift gap. Removing the team repairs costs 0.308 and the city repairs 0.224; player costs 0.006.

**Mechanism (what the data show).**
- **Below 14k, DocETL's own prompt works.** At that size the same template, temperature, instruction placement and tool contract succeed on 95-100% of documents. Call size is the variable that switches failure on within DocETL's own configuration. It is confounded with document identity, since a longer document is a different document.
- **Most failures are empty replies.** Of 6566 logged failures (`revise/logfail.py`), 69% are empty (no text and no tool call), 20% are prose that contains every field as JSON, 8% could not be parsed from the log, and 3% are other prose. A lenient JSON parser would therefore recover at most ~20-28% of drops. Most drops are the model returning nothing, not a parsing quirk.
- **A failure repeats when retried.** Retries of the identical prompt succeed for 16-24% of documents, against 41-61% on first attempts in the 8-16k band (challenge/retry.py).

**Second trigger: field type.** team.championship is typed 'str' in DocETL's tool schema, but the model answers it as a number.
- Below the step, field sets that include championship drop 12/26 team documents (46%) in the realistic workload, against 3/104 (3%) without it. In drift the rate is 54-78%.
- Prose failures with championship contain 62 bare numbers, 18 quoted numbers and 41 '-1' (the numeric sentinel).
- Where DocETL does answer it, it writes '2016 NBA Championship' (doc 6) and '1979 NBA Championship' (doc 21).
- Our reader writes numbers (1.0, 18.0) for the same 'text' field. Its free JSON is not type-checked, and its field line says "aggregated as a number".
- Cost: QJ15 has 23/30 team documents dropped and scores 0.000 vs our 0.749.

**Conditions.** Holds for documents of more than ~14k tokens, at 7B scale, under a strict tool-call contract.

**Breakdowns and open questions.**
- **Table matters above the step.** Player documents fail less than team/city documents at the same length (18-22k: player 0.20, team 0.75, city 0.84).
- **Our prompt is untested in the failing region.** Our reader never sent a call above 10.6k tokens, so I cannot say whether chunking, fields-after-document placement, temperature 0.1 or the free-JSON contract keeps it out of the failure. The challenger's model-call arms (DocETL chunked at T unset vs 0.1; ours unchunked at 0.1 vs 0.8; fields after the document; championship typed number) remain the decisive tests.
- **Frontier models.** A frontier model would likely break the format less often, so this share may shrink.

## F2 (revised claim 3). The "values" step (48%) splits into four named error kinds plus a large interaction, and two queries make up most of that interaction.

`revise/shap_values.py`. Start state: DocETL's db with rows added and NULLs filled. Step = +0.2211 (tau 0.2) and +0.1571 (exact).

| group | alone | Shapley (share of the values step) at tau 0.2 | at exact |
|---|---|---|---|
| PROSE (single-field read returned prose, kept as the value) | +0.054 | 0.074 (33%) | 38% |
| FORM (short or long form of the correct value) | +0.068 | 0.081 (36%) | 32% |
| NUM (number false positive or off) | +0.028 | 0.043 (20%) | 23% |
| WRONG (other wrong value, value where the correct one is empty, 'Not found') | -0.004 | 0.036 (16%) | 22% |
| OK (DocETL right at tau but different from ours) | -0.016 | -0.012 (-5%) | -15% |

- Interaction (step minus the sum of the single effects): 41% at tau 0.2, 23% at exact.
- By table (Shapley): team 61%, player 22%, owner 16%, city 0.7%. The table interaction is only 13%, so the kind interaction comes mostly from cells of the same table.
- Combined with F1: PROSE in the values step is the same protocol failure in its single-field form. The protocol failure therefore covers rows + PROSE + long-document empties, which is where the 65.7% comes from.

### Where the interaction sits

QJ17 (+1.0) and QJ19 (+0.667) hold 66% of the interaction points. Q8 adds +0.58, but there every kind alone gives -0.179, so Q8 is a scoring artifact.

**QJ17** (COUNT of teams in cities over 1M):
- Correct 10, ours 10, DocETL 0.
- A single number is scored exactly, so every team.location key on the path must be right. DocETL's single-field location read has prose on docs 2, 5, 7, 10, 14 and 20, None on 8, 11, 12, 13 and 17, 'Los Angeles' for Miami (16), and 'Orlando, Florida' (22). Its city table dropped 23/29 documents.
- No single kind of repair reaches 10. The query is all-or-nothing.

**QJ19** (teams per owner nationality): the two sides of the join must agree with each other.
- Correct: American 14, Israeli-American 1, Taiwanese-Canadian 1.
- Ours: American 4, Israeli-American 1, Taiwanese-Canadian 1. Ours matches because both of our sides use the same short names ('Stan Kroenke', 'Dan Gilbert', 'Joseph Tsai'), which are not the correct full names ('Enos Stanley Kroenke'). It scores 0.667 because the labels are right and the two singleton counts are exact. American 4 vs 14 is wrong.
- DocETL's team.ownership read has 10 None and 5 prose answers, the description example 'Jeanie Buss' on docs 3 and 20, 'Carnival Cruise Lines' for Arison, and 'Not found'.
- DocETL's owner.nationality gives 'Canadian' (doc 7) and 'American' (doc 15).
- Fixing only one table gives 0. Fixing both gives 0.667.

**Lenient scoring.** The overall gap survives scoring that needs a correct label and a correct value: ours 0.638 vs 0.157 at tau 0.2, and 0.407 vs 0.100 exact. Single-query gaps such as QJ19 and QJ20 (0.667 each, 10.4% of the summed gap) rest on correct labels and singleton groups.

## F3 (revised claim 2). Value form depends on which fields are read together. DocETL reads per-query field sets, and one of them, (location, team_name), shortens names.

**Property.** DocETL's field set is exactly the query's columns. Ours is the union of the build workload's columns for that table: team (championship, location, team_name), player 6 fields, city 3 fields.

**Effect.** FORM is 36% of the values step (about 17% of the gap). Its cells:
- team.team_name, read with (location, team_name): 41 cells in QJ7/8/9/10/13 ('Pelicans', 'Thunder', 'Nuggets'...).
- player.nationality: 9 cells (Q1, QJ6).
- owner.nationality: 4 cells (QJ19/20).
- player.college: 15 cells (Q4, a small score effect).
- Rates for team_name: (location, team_name) gives short forms in 48.6-55.2% of answers, whether or not the SQL joins city. Alone it is 0.2%. With (championship, team_name) it is 0/69, and at our field set DocETL gives 2/48 vs ours 0/30.

**Mechanism.** This is a 7B-model property: the form of the answer depends on which fields are co-read. It is not a property of our reader. At equal field sets the two readers do not differ measurably. Our reader shows the same effect:
- Our single-field owner probes wrote 'Canadian' (doc 7) and 'American' (doc 15).
- Our (name, nationality) read of the same documents wrote 'Taiwanese-Canadian' and 'Israeli-American'.
- The owner documents state the full form, e.g. doc 15: "an Israeli-American billionaire".
- No example constants exist for owner, so prompt examples played no part. This is n=2.

**Nationality "leak" check** (`revise/nat_shown.py`). The build workload's nationality constants are American, American-Venezuelan, American-born naturalized Azerbaijani, Croatian, Dutch, French, Greek-American, Nigerian-American, Serbian and Slovenian. Our field line shows only the first three.
- On the 9 gold multi-part documents, ours is exact on 4/4 documents whose value was shown and on 4/5 whose value was not: doc 96 'American-Spanish', 102 'Cameroonian-American', 120 'American-Chinese', 134 'Mexican-American'. Doc 115 'Greek and Nigerian' became 'Greek'.
- A document-specific leak does not explain our full forms. General priming by the hyphenated examples, or the wording "give the value as the document states it" against DocETL's "Keep names concise and normalized", cannot be separated without model calls.
- DocETL on the same documents:
  - Doc 134 (correct 'Mexican-American'): 'American' 303 times and 'American-born naturalized Azerbaijani' 139 times. The second is a copy of a SQL constant onto the wrong document.
  - Docs 32 and 51 get the same constant 131 times each.
  - Doc 102 gets JSON text in the field 257 times.

**Conditions.** Holds when a query's field set happens to be a form-shifting pair (location + team_name).

**Breakdown.** The effect is not a stable reader advantage. A workload whose union field set happened to be a bad pair would hit our reader the same way.

## F4 (revised claim 4). Count columns: EMPTY0 comes from schema information that our code applies, not from reading. DocETL's false positives copy the description's example number.

**EMPTY0** (23.5% of the drift gap, 2.2% of realistic). In both systems the model leaves an unmentioned count null.
- **Ours** (`build_reads`, player 6-field read, gold-0 documents):
  - olympic_gold_medals: the model returned null on 106/114 documents (98 single-call, 8 chunked), although single-call prompts carry "Never null: always give a value". The 0 comes from `absence_value`, applied in code from the benchmark's is_nullable.
  - mvp_awards, whose description says "use 0 if none": the model itself wrote 0 on 110/124.
- **DocETL, natural experiment on that same description phrase** (`revise/zero_counts.py`; all realistic and drift runs; correct value 0):

  | field | DocETL empty | ours empty |
  |---|---|---|
  | mvp_awards ("use 0 if none") | 20.6% (n=19746) | 0% |
  | fiba_world_cup | 83.3% | 0% |
  | olympic_gold_medals | 83.0% | 0% |
  | nba_championships | 95.8% | 0% |

- **Mechanism.** The information "absent means 0" reaches DocETL only when the description says so. Our system gets it from is_nullable and applies it in code. This is a difference in schema information, not reading quality. An earlier counterfactual (DocETL NULL read as 0) is consistent with this: players template 0.108 to 0.167.

**NUMFP** (`revise/fp_values.py`).

| field | description example | DocETL false positives that equal the example | our false-positive values |
|---|---|---|---|
| mvp_awards | 2 | 1411 of ~2700 (52%) | {1: 4, 2: 1} |
| olympic_gold_medals | 3 | 212 of 343 (62%) | {1: 7, 2: 1} |
| fiba_world_cup | 1 | 1222 of 1804 | {1: 8, 2: 3} |

- Our reader sees the same examples but does not copy them.
- A SQL constant does not raise DocETL's false-positive rate (mvp: 0.165 with const 1, 0.178 without).
- Documents where DocETL is wrong in ≥90% of runs include docs 73, 37 and 41, which never mention MVP. We write 0 on all five such documents.
- **Breakdowns.**
  - Among non-empty answers, fiba_world_cup false positives are 91% for DocETL, a selection effect of its 83% empties.
  - Over all gold-0 cells, ours is worse than DocETL on olympic_gold_medals (7.0% vs 1.9%) and better on fiba_world_cup (9.1% vs 15.2%) and mvp_awards (4.0% vs 13.8%). Our false positives also rise with document length (1/5/18% for <2k/2-8k/≥8k).
  - Why DocETL copies the example is untested. Candidates: the "as precisely and exhaustively (i.e., high recall) as possible" system prompt (verified in docetl api.py:818), Ollama's default temperature (no temperature passed; no params layer in the qwen2.5:7b-instruct manifest), and instruction placement.

## F5 (new). DocETL samples its answers, but de-noising them closes little of the join-key gap

- **Same prompt, different answers.** Among 444 groups of DocETL runs with an identical prompt (same table, fields and SQL), two runs disagree on 21% (player), 30% (team) and 5% (city) of non-empty answers (`revise/same_prompt.py`).
- **Majority vote as a proxy for lower temperature.** Taking the per-document majority over 3-4 identical runs, with empty and missing counted as answers (`revise/mode_vs_sample.py`), raises overall cell accuracy from 0.443 to 0.489:

  | column | single run | majority vote |
  |---|---|---|
  | player.nationality | 0.58 | 0.78 |
  | team.team_name | 0.45 | 0.49 |
  | team.location | 0.21 | 0.19 |
  | city.city_name | 0.19 | 0.22 |

  Our join keys are near 1.0: per-chunk team_name 60/61, location 56/61, city_name 65/67, state_name 61/67 with 6 null chunks and 0 wrong. This corrects my earlier "no nulls".
- **Conclusion.** Sampling explains part of the nationality noise but little of the key deficit. That deficit is F1 plus F3.

## F6 (claim 5, kept). Cost

- **DocETL.** 46.89M prompt + 0.18M completion tokens over 4636 calls (player 24.62M, team 13.21M, city 8.96M, owner 0.10M).
- **Ours.** The build cost 2.04M tokens (322 calls). The 3 patches cost 3.91M: Q4 2.22M, QJ11 1.42M, QJ19 0.27M. 25/28 queries made 0 calls.
- **Sharpened mechanism.** A patch reads every remaining column of the table, not only the missing one:
  - Q4 needed college but fetched name, birth_date, college, draft_pick, draft_year, fiba_world_cup and nba_championships (141 documents each).
  - QJ11 fetched founded_year, championships and ownership.
  - QJ19 fetched all 5 owner columns.

  So each table is read at most twice (build + one patch), while DocETL reads (queries × tables per query) times. The cost edge therefore does not depend on the build anticipating the columns. On a workload disjoint from the build, ours would pay about one full-table patch per table (estimate: about 2.2 + 1.4 + 0.3 + city ≈ 4-5M on top of, or instead of, the build). This estimate is not measured.
- **Still an estimate.** DocETL's "49% of prompt tokens on calls that returned no row" remains an estimate (cost2.py reproduces 44.2M of 46.9M). Per-call phase tokens are not logged.

## Unexplained or untested
- Which part of our reader (chunking, placement, free JSON, temperature 0.1) keeps it free of protocol failures above 14k tokens. Our reader was never run there.
- Why player documents above 14k tokens fail less than team/city documents of the same length.
- Why DocETL copies the description's example number and we do not.
- Q8: every kind alone gives -0.179 and all together +0.044. A scoring artifact from position labels ('Power forward') and the null-position group.
- About 16% of the values step is WRONG-kind cells (e.g. team.ownership 'Jeanie Buss' copied from the description example; 'Carnival Cruise Lines' for Micky Arison). These are attributed by kind but not by cause.

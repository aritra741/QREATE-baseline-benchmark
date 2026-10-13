# Legal: what gives our system its edge over DocETL (revised after the devil's-advocate round)

No model calls. Everything below is computed from saved reads, saved tables and logs. The scripts are in
`edge/legal/revise/`, and each result names the script that produced it. Scores are structure F2 x cell F1 on the official
scoring path (`exp_tau.score_multi`). "Gap" means the sum over queries of (ours - DocETL).

## 0. The gap at every tolerance, and what the cumulative repairs recover (revise/tausteps.py)

| workload | tau | ours (sum) | DocETL (sum) | gap | rows step | empty step | values step |
|---|---|---|---|---|---|---|---|
| realistic v1 (15 q) | 0    | 0.896 | 0.252 | 0.643 | 0.000 (0%)  | 0.199 (31%)  | 0.444 (69%) |
| realistic v1        | 0.05 | 2.633 | 0.726 | 1.907 | 0.024 (1%)  | 0.062 (3%)   | 1.821 (95%) |
| realistic v1        | 0.1  | 3.175 | 0.977 | 2.199 | 0.093 (4%)  | 0.077 (4%)   | 2.029 (92%) |
| realistic v1        | 0.2  | 3.870 | 1.633 | 2.237 | 0.283 (13%) | -0.312 (-14%)| 2.266 (101%)|
| drift (test maps)   | 0    | 0.866 | 0.362 | 0.504 | 0.341 (68%) | 0.173 (34%)  | 0.025 (5%)  |
| drift               | 0.05 | 1.991 | 0.679 | 1.312 | 1.040 (79%) | 0.069 (5%)   | 0.227 (17%) |
| drift               | 0.1  | 2.516 | 0.743 | 1.772 | 1.415 (80%) | 0.009 (1%)   | 0.283 (16%) |
| drift               | 0.2  | 3.239 | 1.189 | 2.050 | 1.801 (88%) | 0.420 (20%)  | -0.237 (-12%)|

Split of the realistic gap into the part from the group keys (structure F2) and the part from the cells, using a
symmetric product split (revise/structsplit.py): at tau 0.2, structure 0.594 (27%) and cells 1.643 (73%); at tau 0,
structure 0.106 and cells 0.537. DocETL makes more groups than the correct answer on almost every GROUP BY query:
Q2 41 groups vs 16 correct (ours 12), Q4 148 vs 52 (ours 83), Q3 169 vs 56 (ours 123), Q5 24 vs 5 (ours 11),
Q8 6 vs 3 (ours 4), Q11 13 vs 5 (ours 5), Q15 19 vs 8 (ours 10).

---

## F1. All-or-nothing type validation per document drops whole documents (drift: the main cause; realistic: Q5 and Q15 only)

**Property.** DocETL validates each document's whole answer against the declared output schema. After three failed
validations the document is silently dropped (`skip_on_error`). Our reader writes a value per cell, and a value it
cannot parse becomes NULL in that cell only. The row stays.

**Mechanism (confirmed in code and log).** Our harness types every non-numeric benchmark field as `str`, including
digit-valued ones: judgment_year, hearing_year, first_judge ("1 if yes, 0 if none") and fine_amount. For Ollama models,
DocETL's `parse_llm_response` (docetl/operations/utils/api.py ~l.1221) runs `ast.literal_eval` on every string value of
a tool call, so `'2008'` becomes 2008 and `'1'` becomes 1. `validate_output_types` then rejects the int for a `str`
field. Of the 62,502 'Validation failed' outputs in logs/docetl_legal.log, the rejected judgment_year values at the final
attempt are int years (2006: 2,924; 2007: 1,761; 2009: 1,692; 2008: 1,482; -1 only 2). For the field sets
(judgment_year, legal_basis_num) and (case_number, judgment_year), 7,622 of 7,622 and 3,143 of 3,143 rejected outputs
are (int, int). The model was reading years; the gate threw them away.

How some years survive: the content-JSON fallback branch (api.py ~l.1185, used when the reply is not a tool call)
parses JSON with no `literal_eval`. In drift, 438 clean year strings survived, 379 of them in two maps
(Agg#8:8bef48e5, 193; Agg#6:ed968b3e, 186).

**Effect.**
- Drift: the rows step recovers 68% of the gap at tau 0, 79-80% at tau 0.05-0.1 and 88% at tau 0.2 (table above).
  Drop rates per map: legal_groupby20:q4 (case_number, judgment_year) keeps 3 of 570 rows;
  Splits/train#11:3a2cf6b1 (counsel_for_applicant, first_judge) keeps 14; Splits/train#9 (first_judge, hearing_year)
  keeps 80; Splits/train#12:66cde6f4 (first_judge, judgment_year) keeps 60.
- Realistic: only Q5 (judgment_year; 79 of 570 rows) and Q15 (hearing_year; 56 rows) are hit. Their combined gap is
  0.513 of 2.237 (23%) at tau 0.2, 0.482 of 1.907 (25%) at tau 0.05, and 0.053 of 0.643 (8%) at tau 0. At tau 0 only
  Q15 counts, because Q5 scores 0 for both systems.
- The reading behind the gate is nearly as good as ours. DocETL's 438 surviving year strings match the correct year
  in 368 cases (84%; ours is 544/570, 95%). Putting DocETL's own surviving reads into our full-coverage Q5 table
  (302 documents; 49 differ from ours) gives Q5 0.294, against ours 0.323 at tau 0.1-0.2 (revise/cf_ownyears.py,
  variant d).
- A COUNT per group needs nearly every document. With only those 331 documents covered (DocETL's 79 rows plus 252
  dropped documents that have a surviving read), Q5 stays at 0.0 at every tau, **even when the 252 added rows carry
  our values** (variant c). Coverage, not reading accuracy, decides Q5. Q15 behaves the same way: 0.022 -> 0.028.

**Conditions.** It holds for an Ollama (or SageMaker) provider, which triggers the `literal_eval` branch, together with
digit-valued fields declared `str`. It also needs aggregate queries whose answer depends on every document (COUNT or
SUM per group).

**Breakdowns.**
- It is a configuration artifact of our harness. Typing these four fields as int, or using a provider without the
  `literal_eval` branch, should remove it. The required rerun has not been done, because it needs model calls.
- Whether Qwen emitted JSON numbers or quoted strings cannot be told from the log, since both paths end as int after
  parsing. The drop is the same either way under this parser.
- Counterexample: attr:Splits/train.sql#12:66cde6f4 (510/570 dropped) has DocETL 0.22 and ours 0.0. Adding the
  dropped rows takes DocETL to 0.0.
- In drift, the rows step is not entirely "gate" queries. attr:Agg#7:61dda821 drops only 23 documents, and its 0.163
  gap is all values.

---

## F2. A closed label vocabulary for grouped label columns (verdict, case_type) is where most of the realistic "values" gap sits

**Property.** For a categorical column, our reader returns one label from a fixed set. The prompt states the allowed
values, adds "Follow each field's allowed values", lists three workload constants, and says "Never null". A post-step
(`conform`) then nulls anything outside the set. DocETL's prompt holds the same benchmark description, but its answers
are free text. Out-of-domain labels ('Dismissible', 'Disputed', prose, JSON-in-string) and in-domain but rare labels
('Guilty', 'Not Guilty', 'Criminal Case') each become separate groups.

**Effect.**
- Single-column swaps (our column into DocETL's table, everything else DocETL's) show verdict is the biggest single lever:
  - Q2 0.184 -> 0.460
  - Q8 0.123 -> 0.667, above ours (0.536)
  - Q11 0 -> 0.160
  - Together +0.98 at tau 0.2 (44% of the gap). Results are in cf/ and were rescored at every tau.
- Q8 traced (revise/structcell.py):
  - Gold groups are Dismissed 211 / Approved 23 / Others 3.
  - DocETL makes 6 groups: Dismissed 36, Not Guilty 6, Guilty 4, Dismissible 3, Approved 2, plus one prose label
    (structure 0.556, cells 0.222).
  - With our verdict, DocETL's table makes exactly 3 groups (structure 1.0, cells 0.667), even though its defendant
    column selects only 52 of the 237 relevant cases. Both systems get the big count wrong (DocETL 36, ours 138, correct
    211; the tolerance at tau 0.2 is ±41.6). The Q8 edge is therefore the label set, not the coverage.
- Q2 traced:
  - DocETL makes 41 groups: ('Criminal Case', NULL) 147, ('Criminal Case', 'Guilty') 24, ...
  - Ours makes 12 groups, although our per-document case_type is poor: 'Civil Case' on 451 of 570 documents, against
    156 correct Civil. Ours scores 0.329 because its group set is small and in-domain.
- Per document, our case_type is no more accurate than DocETL's best map (ours 272/570; DocETL attr:legal_filter20:q2:63b03320
  250/561; DocETL realistic Q2 runs 249-262). The edge comes from which labels appear, not from more correct documents.

**The conform post-step (original claim 1, revised).** It is measured against each tau's own gap (revise/conform_tau.py):
- tau 0: +0.036 / 0.643 = 5.6%
- tau 0.05: +0.072 / 1.907 = 3.8%
- tau 0.1: +0.126 / 2.199 = 5.7%
- tau 0.2: +0.346 / 2.237 = 15.5%

Rows changed per query: Q1 7, Q2 38, Q4 31, Q8 34, Q11 20, Q12 56. Only Q1 (+0.142 at tau 0.2), Q2 (+0.180) and Q8
(+0.024) gain. Stability across reruns:
- Q2 SQL on the three identical-prompt DocETL runs (v1 Q2, v2 Q1, v3 Q1) gains +0.18 to +0.20 at tau 0.2
  (mean 0.193), +0.07 to +0.11 at tau 0.05, and 0 to +0.036 at tau 0. Conformed DocETL scores 0.364 / 0.437 / 0.404,
  all above ours (0.329). The Q2 gain is robust.
- Q1 SQL on four DocETL tables (v1 Q1 plus the three Q2-prompt runs) gains -0.143 to +0.142 at tau 0.2 (mean +0.01).
  The Q1 gain is not robust. It comes from 7 rows and is a structure-F2 effect.
- On our side, undoing conform costs 0.204 summed at tau 0.2 and 0.09 at tau 0 (challenge/ours_noconform.py). Out of
  domain, the two readers are about equal on verdict: DocETL 32-36 per run (~6%), ours raw 24/570 (4.2%). The
  difference is the post-step, not the reader.

**Label anchoring by the one example in the description (new; supported for the label distribution, mixed for the score).**
The benchmark description, used verbatim by both systems, is "type of the case, choose one from [...]; (e.g., Criminal
Case)" and "court's decision, choose one from: [...]; (e.g., Guilty)". The examples name the rarest correct labels
(Criminal Case 10/570 = 1.8%, Guilty + Not Guilty 8/570 = 1.4%). In DocETL's prompt they are the only concrete labels
unless the SQL shows others. Ours also lists 'Administrative Case', 'Civil Case', 'Commercial Case' and 'Approved',
'Dismissed', 'Others'. These are the template workload's constants and the three most frequent correct labels in each
column (revise/ourspec.py renders our build prompt; the original ourprompt.py matched it to 484/484 prompt hashes).

Natural experiment over all DocETL legal maps (revise/mapscan.py; 15 maps read case_type, 15 read verdict):
- **Criminal share of non-empty case_type answers.** 0.055-0.139 in the 5 maps whose SQL shows non-criminal case_type
  constants. 0.22-0.61 in the 10 maps that show none.
  - The 3 identical-prompt runs give 0.335 / 0.367 / 0.335, so sampling spread is about 0.03, far below the effect.
  - Ours is 8/570 = 1.4%.
- **Guilty/Not Guilty share of verdict answers.**
  - 0.02 (v1 Q4) and 0.09 (v3 Q10) when 'Dismissed' is shown.
  - 0.13-0.38 otherwise: Q8 0.35, v3 Q8 0.375, Q11 0.29.
  - Ours is 1.8%.
- **The anchor pulls toward whatever set is shown, including too far.**
  - legal_filter20:q8 shows only 'Civil Case' and gets Civil on 493/557.
  - v1 Q4 shows only 'Dismissed' and gets Dismissed on 507/564 (correct share 67%).
- **Score effect when DocETL's own anchored reads are swapped in** (revise/shownprior.py, revise/shownverdict.py):
  - Case_type from 63b03320 (all three non-criminal labels shown): Q1 0.178 -> 0.617, Q14 0.32 -> 0.463, Q2 0.184 ->
    0.186, Q6 0.16 -> 0.154.
  - Case_type from q8 ('Civil Case' only): Q1 0.139.
  - Verdict from Dismissed-only maps: Q2 0.184 -> 0.084 / 0.078, Q8 0.123 -> 0.0.
  - No DocETL map shows all three majority verdict labels, so the verdict half of this mechanism cannot be tested from
    DocETL's side without model calls.
- **Nulling the anchored labels in DocETL's tables lowers the score** (sum -0.138 at tau 0.2; revise/anchorlabels.py).
  The anchored answers sit on documents whose correct label is a majority label. Removing them takes those documents
  out of the right groups, so the loss is per document, not a junk group that conform could remove.

**Conditions.** It needs a GROUP BY or WHERE on a categorical column, and a metric that charges for every extra group
(structure F2) while tolerating count errors relative to the column's range. Small groups always pass at tau 0.2 (Q8
range 208, so ±41.6), which makes the group set decide the score.

**Breakdowns.**
- Our case_type default to 'Civil Case' (451/570; 235 of those are correctly Administrative) costs us Q14: DocETL 0.320
  vs ours 0.185, and the case_type swap confirms it.
- The anchoring helps only because the template workload's constants happen to be the three majority labels. A
  workload whose constants were minority labels would pull our answers the wrong way, as the 'Civil Case'-only and
  'Dismissed'-only DocETL maps show.
- At tau 0 almost nothing of this survives: the structure part is 0.106 of 0.643.

---

## F3. Answer-or-abstain policy: "Never null" against "if unknown, return empty string" (judge, nationality, case_type)

**Property.** Our field spec says "Never null: always give a value" for judge_name, case_type, verdict, nationality,
defendant and others. DocETL's runner says "If a text field is unknown, return empty string". Whether DocETL then
answers depends on the query's prompt.

**Effect and mechanism.**
- **judge_name (Q3, Q4).**
  - DocETL leaves 32% (Q3) and 38% (Q4) empty; ours leaves 0 empty, with 511/570 surnames right.
  - The judge is named once, in the certification line near the end: "...true copy of the Reasons for Judgment herein
    of the Honourable Justice Moore". The name first appears after character 2,000 in 536/570 documents.
  - Abstention is not a length limit. DocETL leaves doc 103 empty (423 tokens, name at character 1,537), and Q4's empty
    rate is highest for short documents (<4k tokens: 131/261) and lowest for long ones (>10k: 11/88).
  - Swapping our judge column into DocETL's Q4 gives 0.135 -> 0.347 (ours 0.449). DocETL's 196-document NULL group
    becomes real judges, and its 148 groups drop to 116.
  - Under other prompts DocETL reads judges well: attr:Mixed#4:5da01b31, whose SQL shows judge constants, has 2% empty
    and 496/552 surnames right. Its empty rate across the 7 maps with judge_name ranges from 2% to 83%. This is a
    prompt effect, not a capability gap.
- **nationality_for_applicant (Q10; revise/q10.py).**
  - Of the 303 documents with a non-empty correct nationality, DocETL leaves 146 empty (48%, flat by length: 45% / 50% /
    54%) and ours 71. When it answers, DocETL is right on 127/157 (81%), ours on 215/232 (93%).
  - China: ours 59/63 right, DocETL 33 (plus 7 'People's Republic of China', which our representation layer rewrites to
    China).
  - Bangladesh: ours 25/26, DocETL 14.
  - On Q10 the empty step recovers 0.372 -> 0.470 and the values step 0.470 -> 0.553.
- **case_type empty rate** (of 570, including dropped rows) ranges from 4% to 85% across DocETL maps, against a
  replicate floor of 7.4-8.6% for one identical prompt.

**Conditions.** It holds where the value is stated but needs a small inference (the certifying judge is the deciding
judge; the applicant's nationality is implied).

**Breakdowns.**
- "Never null" invents values where the correct answer is empty. Ours puts a nationality on 59 documents whose correct
  nationality is empty (DocETL on 18).
- Our Australia count of 83 equals the correct 83 only by coincidence: just 20 of the 83 correct-Australia documents get
  'Australia' from us. The scorer compares counts, so a right count on the wrong documents scores in full.
- Q14 (case_type default) goes against us.
- The companion-field explanation of DocETL's abstention, from my original claim 2, is **withdrawn**. The same field set
  gives very different empty rates under different SQL: case_type with defendant_current_status 0.13 vs 0.42; judge
  with verdict 0.38 vs 0.59. A field set seen once is also confounded with the SQL text and with sampling (see F4).

---

## F4. Decoding temperature and run-to-run noise (new; it changes how per-document evidence can be read)

- Ours samples at temperature 0.1 (core/llm/ollama.py default; drift_live.py l.223). DocETL's runner passes only
  max_tokens, num_ctx and api_base (run_docetl_drift.py l.137), and DocETL's map does not set a temperature (map.py
  l.227-231 comment). The qwen2.5:7b-instruct manifest has no params layer, so Ollama's default (0.8) applies.
- Three identical DocETL runs (same SQL, same fields) disagree per document on case_type in 27-30% of documents and on
  verdict in 20-24%. Their Q2 scores are 0.184, 0.233 and 0.209 at tau 0.2 (challenge/replicates.py, re-checked). The v1
  run used for the gap is the lowest.
- So "ours gives the same verdict in every query" follows mechanically from reading once. Cross-query disagreement in
  DocETL is not evidence of a companion-field effect. A majority of 3 runs lifts per-document case_type accuracy
  (249-262 -> 275) but not the Q2 score (0.189-0.212). Temperature therefore explains the per-document flips but not
  the score gap.
- Document bootstrap (revise/boot_all.py, 300 resamples, the same draw for gold and both systems; ours minus DocETL,
  mean and 95% CI):
  - Q1: tau 0.05 +0.204 [0.163, 0.25]; tau 0.2 +0.19 [-0.057, 0.377].
  - Q2: tau 0.05 +0.088 [0.007, 0.159]; tau 0.2 +0.143 [0.023, 0.253]. Against DocETL+conform at tau 0.2: +0.019
    [-0.114, 0.128]. The Q2 edge is the conform step.
  - Q12: see F5.
  - The other queries are in the table below.

| query | mechanism (this file) | tau 0 | tau 0.05 | tau 0.1 | tau 0.2 |
|---|---|---|---|---|---|
| Q1 case_type count | F2 | +0.023 [0, 0.226] | +0.204 [0.163, 0.25] | +0.182 [0.062, 0.25] | +0.19 [-0.057, 0.377] |
| Q2 case_type x verdict | F2 (conform) | +0.025 [-0.026, 0.103] | +0.088 [0.007, 0.159] | +0.087 [0.004, 0.163] | +0.143 [0.023, 0.253] |
| Q3 judge count | F3 | +0.149 [0.079, 0.211] | +0.19 [0.117, 0.278] | +0.223 [0.147, 0.331] | +0.198 [0.115, 0.285] |
| Q4 judge, dismissed | F3 | +0.097 [0.029, 0.171] | +0.163 [0.075, 0.246] | +0.226 [0.131, 0.329] | +0.275 [0.162, 0.383] |
| Q5 judgment year | F1 | +0.028 [0, 0.139] | +0.307 [0.11, 0.44] | +0.379 [0.246, 0.494] | +0.398 [0.323, 0.556] |
| Q6 case_type avg statutes | F2 + F3 | +0.005 [0, 0.025] | +0.029 [-0.212, 0.25] | +0.054 [-0.212, 0.37] | +0.116 [-0.212, 0.5] |
| Q8 immigration verdicts | F2 | +0.004 [0, 0] | +0.245 [0, 0.536] | +0.472 [0.268, 0.667] | +0.415 [0.099, 0.543] |
| Q10 nationality | F3 | +0.246 [0.149, 0.341] | +0.234 [0.123, 0.335] | +0.218 [0.117, 0.32] | +0.198 [0.092, 0.298] |
| Q12 company plaintiff | (F5) | +0.012 (vs DocETL+fold+conform) | +0.037 | +0.081 | +0.157 [-0.185, 0.536] |
| Q14 case_type x evidence | F2 breakdown | +0.026 [0, 0.25] | +0.192 [0.025, 0.25] | +0.063 [-0.135, 0.25] | -0.135 [-0.385, 0.077] |
| Q15 hearing year | F1 | +0.019 [0, 0.112] | +0.197 [0.072, 0.303] | +0.234 [0.138, 0.376] | +0.308 [0.184, 0.505] |

What this shows:
- The edges that hold at every tau from 0.05 up are Q3 and Q4 (judge abstention, F3), Q10 (nationality abstention,
  F3), Q5 and Q15 (type gate, F1), and Q2.
- Q8 holds at tau >= 0.1 only.
- Q1 holds at tau 0.05-0.1 only, and Q6 and Q12 are not distinguishable from 0.
- Q3 and Q4 are robust even at tau 0. Their bootstrap means (0.149 and 0.097) differ from the full-sample gaps (0.078
  and 0.01) because resampling duplicates documents, which changes the counts per judge. Read these intervals as
  stability checks, not as unbiased estimates.

---

## F5. Q12 ("company plaintiff") is not a robust part of the edge (original claim 4, withdrawn as a driver)

- Full-sample scores are ours 0.221 and DocETL 0.0 at every tau. Our tau-0 score rests on one exact cell (Approved 29 =
  correct 29). Moving one row out of Approved gives 0.0 at tau 0 (challenge/q12perturb.py).
- Bootstrap over documents (revise/boot_q12.py, 500 resamples):
  - Ours averages 0.018 at tau 0 (95% CI [0, 0.221]) and 0.227 at tau 0.2 ([0, 0.536]).
  - Ours minus DocETL+fold+conform: +0.012 at tau 0 (P(diff <= 0) = 0.92); +0.157 at tau 0.2, CI [-0.185, 0.536],
    P = 0.24.
- What survives is per document. Among the documents whose correct plaintiff status is Company and which a system also
  labels company (in any case), ours has 42/87 verdicts right and DocETL 15/53. The fold
  'company' -> 'Company' is a benchmark inconsistency: the description says to write 'company', while the correct data
  stores 'Company'. Our T0 normalization resolves it, and DocETL with a case-insensitive comparison would too.

---

## F6. Cost: read once, reuse across queries (original claim 5, kept and reframed)

- DocETL realistic legal: 98.08M prompt tokens + 0.42M completion over 16,146 calls.
  - Q5 (22.66M; 4,160 calls; 7.3 calls per document) and Q15 (24.01M; 4,270 calls) are the F1 retry loops, 46.7M
    (48%) together. Net of the ~7.3M a normal single pass costs for the two, the retry overhead is ~39M (~40%).
  - The other 13 queries cost 3.6-4.8M each at 1.00-1.23 calls per document.
- Ours: build 4.56M (727 calls, with chunking for documents over the window), plus one patch at Q3 for judge_name,
  which the template build lacked (925 calls including 220 probe calls; 5.31M). The other 14 queries made 0 calls.
  Total 9.87M, against DocETL's 98.5M (10x) or 51.4M without the retry loops (5.2x).
- Property: cost scales with the number of distinct column sets that need reading, not with the number of queries.
  Here 15 queries needed 2 reads.
- Breakdown: compared with a single DocETL map over the union of all 15 queries' columns, which is an oracle a stream
  does not have, ours costs more. One-field DocETL passes cost 3.62-3.63M and two-field passes 3.88-4.17M, so a typed
  all-column pass would be about 4-4.5M against our 9.87M. A column outside the build (judge_name) costs a full extra
  pass, larger than one DocETL query (5.31M vs 3.62M) because of chunking and probe calls.

---

## Status of the original claims

0. **Type gate drops documents. Revised.** The mechanism is confirmed. It is a harness configuration artifact
   (str-typed digit fields + Ollama `literal_eval` + skip_on_error). Its share is drift 68-88% (depending on tau) and
   realistic 8% (tau 0) to 25% (tau 0.05). DocETL's own surviving reads (84% correct) show the loss is coverage, not
   reading.
1. **Conform. Revised.** 5.6% / 3.8% / 5.7% / 15.5% at tau 0 / 0.05 / 0.1 / 0.2. It is robust on Q2 (three replicates,
   +0.18 to +0.20) and not on Q1 (-0.14 to +0.14, 7 rows). It is folded into F2, the closed label vocabulary.
2. **Companion fields cause DocETL's abstention. Withdrawn as causal.** It is confounded with the SQL text and with
   sampling at temperature 0.8. What remains is F3: abstention depends on the query's prompt, 2-83% for judge_name.
3. **Judge / entity reading. Revised.** The Q4 gain (+0.212) is abstention (F3), not entity resolution. DocETL reads
   judges well when the prompt shows a judge constant (5da01b31: 496/552). The defendant part has no share at tau 0.2.
4. **Q12 fold. Withdrawn as a driver.** It is not robust under bootstrap: tau 0 mean 0.018; tau 0.2 difference CI
   includes 0, P = 0.24.
5. **Cost. Kept.** It is reframed as a property of read-once reuse against per-query re-reading. Against an oracle
   all-column map, ours costs about 2x more.

## Still unexplained or untested

- Whether the verdict half of label anchoring holds needs a DocETL run whose prompt shows the three majority verdict
  labels. Whether the 'e.g., Guilty' example drives the Guilty/Not Guilty answers needs a run with the example removed.
  Both need model calls.
- Q11 is 0 for both systems. Our case_number averages ~1.5 per verdict against correct 6.5-9.3, and DocETL has an outlier
  (Guilty average 980,388). This is unexamined.
- Q9 (defendant_current_status): we produce 110 groups against 39 correct, and DocETL 10. Both score low; unexamined.
- Q6 needs both of our columns. Swapping only case_type gives 0.185 and only legal_basis_num gives 0.0, against ours
  0.37. Why the pair matters is untested.
- The rerun of DocETL with digit fields typed int, which would settle F1's realistic share without assumptions, is not
  done (it needs model calls).

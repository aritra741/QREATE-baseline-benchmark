# Cost edge on realistic v1: revised findings after the devil's-advocate round

No model calls were made. Every number comes from saved runs. The scripts are in `cost/revise/`, with their JSON outputs beside them:
- `ladder.py` prices hypothetical plans with our measured per-document read cost.
- `second_pass.py` covers the harness's second pass, re-scoring, and legal Q5/Q15.
- `decomp2.py` gives the bounded decomposition.
- `reread_same_fields.py` measures DocETL re-read disagreement at equal field sets.
- `docetl_readonce.py` re-scores DocETL with a single shared read per column.

The original notes are in `cost/NOTES.md`; the challenger's scripts are in `cost/challenge/`.

## Measured totals (input tokens; ours = W0 build + charged stream)

| | ours | DocETL | ratio | ratio, stream only | zero-call queries (ours) |
|---|---|---|---|---|---|
| art | 4.46M | 27.79M | 6.23 | 12.7 | 21/22 |
| cspaper | 0.88M | 6.06M | 6.86 | 11.9 | 21/22 |
| legal | 9.68M | 98.08M | 10.13 | 18.8 | 14/15 |
| med | 9.53M | 30.49M | 3.20 | 4.3 | 18/20 |
| player | 5.93M | 46.89M | 7.91 | 12.0 | 25/28 |

## F1. A ladder of plans: where the token ratio comes from (revises original claims 0 and 3)

**Method.** Each plan is priced with our own measured cost of reading one document:
- The base is the median of single-column journal reads (`patch:<c>`, `frozen:<c>`, `probe:<c>`), summed over chunks, with input and output looked up by prompt_sha in usage.jsonl.
- Each extra column adds a measured marginal cost per chunk (34-87 input and 9-21 output tokens).
- What each query needs comes from DocETL's stats.json fields. These are produced by `C.design(spec,{qid:sql})`, the same design our system uses.

**Validation.** The model prices the W0 build at -5% (legal, med, player), -17% (cspaper) and -22% (art) of the measured cost. It prices the catalogue group reads at +0% (cspaper, med), +1% (legal), +24% (art) and +65% (player) of the measured cost. The two overestimates come from windowed reads: groups with share 0.10-0.17 on long documents.

**The plans:**
- A: DocETL as measured.
- B: our reader with DocETL's plan, one pass per (query, table).
- C: shared reads with no build. Only the columns a query lacks are patched, and nothing is anticipated.
- D: the W0 template build plus patch-only.
- E: as run (build plus catalogue planner).
- F: a read-once lower bound, one pass per table over every column the workload uses.

| | A/B | A/C | A/D | A/E | A/F | zero-call queries C / D / E |
|---|---|---|---|---|---|---|
| art | 1.25 | 1.77 | 2.75 | 6.23 | 13.9 | 6 / 14 / 21 of 22 |
| cspaper | 1.21 | 2.11 | 3.16 | 6.86 | 15.9 | 9 / 15 / 21 of 22 |
| legal | 1.64 | 1.77 | 3.47 | 10.13 | 22.3 | 1 / 9 / 14 of 15 |
| med | 1.10 | 1.62 | 2.95 | 3.20 | 12.8 | 4 / 13 / 18 of 20 |
| player | 1.45 | 3.80 | 6.28 | 7.91 | 23.5 | 12 / 20 / 25 of 28 |
| total | | | | | | 32 / 71 / 99 of 107 |

Share of ln(A/E), the log token ratio:

| | per-read + failure ln(A/B) | reuse alone ln(B/C) | template-build foresight ln(C/D) | catalogue foresight ln(D/E) |
|---|---|---|---|---|
| art | 0.12 | 0.19 | 0.24 | 0.45 |
| cspaper | 0.10 | 0.29 | 0.21 | 0.40 |
| legal | 0.22 | 0.03 | 0.29 | 0.46 |
| med | 0.08 | 0.33 | 0.51 | 0.07 |
| player | 0.18 | 0.47 | 0.24 | 0.11 |

The ordering holds when the planner's 20-document probes are charged in C and D. The catalogue share is then 0.45 / 0.45 / 0.48 / 0.19 / 0.19.

**Property → effect → mechanism.**
- **Property.** Reading a document costs about its length. Each column adds only 34-87 input tokens per chunk; a document is 700 to 15k tokens.
- **Effect.** The bill is therefore set by the number of passes over each table, not by how many columns are read.
- **Mechanism.** DocETL makes one pass per (query, table): 22 passes on art, and player.team or team.team_name 13 times. A shared-read system makes one pass each time the stored column set falls short of a query. Reuse alone (C) saves only on queries whose columns are all already stored. In legal almost every query brings at least one new column, so C has 1 zero-call query of 15 and reuse alone is worth 3% of the log ratio. What turns the rest into zero-call queries is reading columns before anyone asks for them, at marginal cost. Two kinds of foresight do this: the W0 template build covers 7-12 of the realistic columns, and the catalogue planner reads every remaining schema column on the first miss. Together they carry 36% (player) to 75% (legal) of the log ratio.

**Conditions.**
- The effect is largest where the stream keeps asking new single columns of the same table: art has 8 single-column arrivals and legal 6.
- Catalogue foresight is small on med (0.07) and player (0.11). There, probes on small or long tables cost a lot, and the W0 build already covers most of what is needed.

**Breakdowns.**
- Our run is 2.2-4.0 times above F. The extra cost comes from W0 columns no realistic query uses (art: 5 of 15), the second group pass, and probes. Probes are 36-38% of our total on med and player, and the probe-free ratio is 4.97 (med) and 12.7 (player).
- On tiny tables our cost is higher than DocETL's. On owner (16 documents, 2 queries), DocETL used 2.51 passes and we used 6.56, of which 5.25 were probes.
- On the drift workload, the measured E13 ablations (COST/summary.json) confirm the direction:
  - Without patch reuse we are still 1.8-2.0 times cheaper than DocETL: art 32.2M vs 57.9M, cspaper 11.3M vs 20.7M, player 97.8M vs 190.6M.
  - "nobatch" patches only the query's own columns. It raises patch tokens by 47% on art (6.08M to 8.91M) and 35% on cspaper (1.16M to 1.57M), and leaves player unchanged. That is 15%, 9% and 0% of the drift log gap.
  - So foresight's share depends on how columns arrive in the stream. It is 40-46% on realistic art, cspaper and legal, and 0-15% on drift.

**Fairness.**
- Our system knows the benchmark schema and was built from a template workload. DocETL sees one query at a time.
- A DocETL given the same column list could run one map per table (plan F) and would be 13-24 times cheaper than DocETL as run, or 2-4 times cheaper than our system, before its failure overhead.
- The cost edge therefore belongs to the property "materialise once over a column set that covers the workload". It does not belong to our prompt or reader.

## F2. Per read, at equal fields, the two readers cost about the same (revises claim 3)

DocETL's first-pass tokens divided by plan B's are 1.23 (art), 1.20 (cspaper), 0.92 (legal), 1.00 (med) and 0.99 (player). DocETL's template carries the SQL and costs about 320-520 tokens per call, against our 120-180 base. On legal our chunking adds a repeated prompt and a carried note per chunk, and DocETL instead truncates 7 documents (0.41M tokens per pass go unread).

The earlier statement that "per read, ours is not cheaper (0.58-0.81)" compared our wide catalogue reads (10-16 columns) and probes against DocETL's 1-3-field reads. Bounded both ways, the old read-count × per-read split gives:
- read count: 0.66-1.05 of the log ratio if probes count as reads, 0.87-1.39 if they are left out;
- per read: -0.06 to +0.16, or -0.12 to +0.13.

These are accounting identities, not mechanisms. The ladder replaces them.

## F3. DocETL's failure overhead (revises claim 1; mechanism corrected)

**Corrected mechanism** (docetl api.py 495-540 and 1196; map.py 363-390):
- A reply with no tool call raises InvalidOutputError inside validation_fn. The error escapes the retry loop, so the item is skipped after a single call.
- Only type-check failures get the 3 in-call retries. Each retry re-sends the whole conversation, so it costs a full document.

The overhead splits as follows:

| | second pass, share of DocETL tokens | validation retries, share | rows the second pass adds / first-pass misses | score at 20% with → without the second pass |
|---|---|---|---|---|
| art | 1.7% | 0.2% | 233 / 356 (65%) | 0.2246 → 0.2246 |
| cspaper | 0.5% | 0.3% | 17 / 19 | 0.0678 → 0.0679 |
| legal | 25.3% | 18.8% | 96 / 1,169 (8%) | 0.1089 → 0.1093 |
| med | 9.0% | 0.3% | 44 / 165 (27%) | 0.1204 → 0.1225 |
| player | 27.6% | 3.8% | 123 / 621 (20%) | 0.1052 → 0.1001 |

The second pass is the harness's own retry (run_docetl_drift.py lines 172-173).

**What this means.**
- Without the second pass the token ratio is 6.13, 6.82, 7.57, 2.91 and 5.72, against 6.23, 6.86, 10.13, 3.20 and 7.91 measured. The second pass accounts for 13% (legal), 16% (player) and 8% (med) of the log ratio, and about 1% elsewhere. All failure overhead together is 25% (legal), 18% (player), 8.5% (med) and about 1% (art, cspaper).
- The second pass costs up to 28% of DocETL's tokens and changes its score by at most 0.005 at 20%. At tau 0 the change is player +0.011 and med +0.007.
- Failures on long documents recur, so re-sending them buys almost nothing. Player city QJ10 recovered 0 of 25.

**The temperature confound** (confirmed):
- run_docetl_drift.py passes no temperature. The qwen2.5:7b-instruct manifest has only model, system, template and license layers, with no params layer. DocETL therefore sampled at Ollama's default of 0.8.
- Our caller uses 0.1 (core/llm/ollama.py, line 52).
- When the identical prompt is re-sent, 65% of art's first-pass failures succeed. Art documents are short (about 800 tokens), so those failures look like sampling. On long documents (player, legal, med) only 8-27% succeed, so those failures look systematic.

## F4. The Ollama type-coercion bug: a cost artifact that also costs accuracy beyond the dropped rows (claim 2 kept, corrected)

**Mechanism** (verified): on the Ollama path, api.py about line 1226 applies `ast.literal_eval` to string arguments, so "2005" becomes an int. The str schema then fails validation, which triggers 3 retries and then drops the row.

**Cost.** Legal Q5 made 4,160 calls (22.7M tokens) and Q15 made 4,270 calls (24.0M tokens). Together that is 47.6% of DocETL's legal tokens, and their second passes are 22.2M of the 24.8M second-pass tokens.

**Correction.** The surviving rows are not mainly ones where no year was found. 26 of Q5's 79 rows and 31 of Q15's 56 rows hold a year wrapped in JSON or prose, for example `{"hearing_year": 2007}` (5 rows). The model wrote these after DocETL's "Please try again" message.

**Re-score without model calls** (years parsed out of the strings; dropped rows filled with our values), at 20%:

| | DocETL | years parsed | dropped rows filled | both | ours |
|---|---|---|---|---|---|
| legal Q5 | 0.000 | 0.000 | 0.096 | 0.356 | 0.323 |
| legal Q15 | 0.022 | 0.066 | 0.048 | 0.196 | 0.212 |

- The two effects multiply: neither fix alone recovers much, and both together reach our level. Only 12 of 26 (Q5) and 13 of 31 (Q15) parsed years equal the correct year exactly.
- The bug is worth up to (0.356 + 0.174) / 15 = 0.035 of the legal mean. That is about 24% of the legal realistic gap (0.109 → 0.258), against 0.008 when only the swap "rows" step is counted.
- This figure is an upper bound, because the dropped rows were filled with our values. This is the one place where the cost cause and the accuracy cause are clearly the same.

## F5. Re-reading costs tokens but does not explain the accuracy gap (claim 4: the accuracy link withdrawn; the draw part revised)

**Read-once counterfactual on DocETL's own reads** (`docetl_readonce.py`, rows held fixed). Each column takes DocETL's first read in stream order in every later query ("first"), or the most common non-empty value over all its reads ("modal"):

| at 20% | DocETL | first (read once) | modal (consensus) | ours |
|---|---|---|---|---|
| art | 0.225 | 0.248 | 0.236 | 0.243 |
| cspaper | 0.068 | 0.040 | 0.069 | 0.071 |
| legal | 0.109 | 0.083 | 0.104 | 0.258 |
| med | 0.120 | 0.103 | 0.098 | 0.259 |
| player | 0.105 | 0.114 | 0.172 | 0.564 |

- Sharing one of DocETL's own reads moves its score by -0.028 to +0.024, and consensus by at most +0.067 (player).
- The large gaps (player 0.46, legal 0.15, med 0.14) do not close, so the number of reads is a cost cause, not an accuracy cause.
- Collection-level check: cspaper has the largest read ratio (11.0) and an accuracy gap of 0.003. Med has the smallest (5.0) and a gap of 0.139.
- On art birth_continent, read 7 times, DocETL averages 0.414 against our 0.431. It wins Q9 (0.656 vs 0.338) and Q13 (0.339 vs 0.097). On Q1, filling only DocETL's empty answers with ours gives 0.838, above our 0.677.

**Re-reads are new draws, but of a mixture.** Pairs of DocETL queries that asked the same field set differ only in the SQL. Across their documents:
- player (56 pairs): 26.5% of answers change (6.4% different value, 9.0% blank vs filled, 11.2% dropped vs present);
- med (3 pairs): 45% change;
- pairs with different field sets: 40% (player), 45% (art) and 22% (cspaper, against 2% for its single same-field pair).

The reference point is our reader at temperature 0.1 sent the same prompt twice: 12.5% of answers change (WHY/repeat). DocETL's draws therefore mix temperature-0.8 sampling, the SQL shown in the prompt and the co-requested fields. Without a GPU these cannot be separated.

## F6. Time comparison (claim 5: estimates withdrawn)

Measured wall-clock, build plus stream against DocETL's summed per-map seconds:
- art 4,722 s vs 6,897 s (1.46×)
- legal 7,105 s vs 36,857 s (5.2×)
- med 4,123 s vs 8,628 s (2.1×)
- player 2,884 s vs 13,462 s (4.7×)

cspaper's stream was fully replayed (0 paid calls), so it is not comparable. These ratios measure server state, not design:
- Our paid stream calls ran at an implied concurrency of 6.8-7.9, at num_ctx 32768. The build ran at 16384.
- Art's stream throughput was 51 tokens per call-second, against 503 in its build. Legal, med and player were 152-205 against 173-282.
- realistic_docetl_gpu0.log shows DocETL legal running from 22:46 to about 09:03, overlapping our V3 streams (22:44-02:10). The log name suggests the same GPU-0 server.

The realistic DocETL logs contain 0 APIConnectionError lines. The 190k (art) and 189k (legal) such lines are only in the drift logs, so they confound drift times only.

## Kept unchanged

- Scope push-down saved 0 documents on realistic v1: every patch scope was the whole table.
- Re-read counts: player.team and team.team_name 13×, team.location 10×, city.city_name 9×, art.birth_continent 7×.
- DocETL's cumulative tokens pass ours (with the build charged) by query 2-4.

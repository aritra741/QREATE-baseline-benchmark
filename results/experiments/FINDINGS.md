# Experiment findings (running log)

> **Erratum (2026-10-02 13:20).** From 2026-10-01 23:40 to 2026-10-02 13:20 a code edit for E7b dropped the line
> "Answer No unless the document indicates Yes." from the prompt of every never-null yes/no field, even with no
> experiment variables set. Runs that started in that window and made new reads were invalid: E7b, E7 and E7c on
> cspaper, all five prompt-width runs (E2.1b), and the `fragile` policy runs (E3.3). **All have been re-run with the
> fixed prompts (2026-10-02, 12:42–23:02); their sections below show the re-run numbers and say where they differ
> from the invalid run** (the E7 cspaper result at 0% drift changed sign; the `fragile` policy on med matches unlimited
> instead of beating it; the other conclusions held). Everything else (Phase 1, all replays and per-corpus analyses, E8, E9, the E7 shared read
> and the E7 player stream, the latter checked by a no-call replay) is unaffected. Found because the cspaper
> `fragile` control, which has nothing to skip, did not reproduce the recorded sweep; details and the quarantined
> outputs are in `_invalid_promptbug/README.md`. A guard step now replays a recorded stream with model calls refused
> before any GPU step runs.

Results of the experiment plan (`results/drift_design/EXPERIMENT_PLAN.md`), newest last. Every number links to the
file it comes from; step status is in `results/experiments/STATUS.md`. Model: Qwen 2.5 7B on local Ollama (4-bit
unless stated). Scores are per-query structure F2 × cell F1@0.20, averaged.

## Setup checks

**Replays reproduce the recorded runs exactly (cspaper).** All 30 recorded fixed4 streams (5 drift levels × unlimited
and 5 budgets) were re-run from the journals with every query's database kept, with model calls refused: 0 streams
differ in any query's action, missing columns, tokens or score
(`E2-replay/live/cspaper/verify.json`). The per-query analyses below use these databases.

**The error breakdown's scores match the recorded ones** (0 of 59 queries differ at 100% drift;
`E2.4-errors/cspaper/per_query.csv`).

## cspaper

### Patch cost estimates are accurate (E4.1)
Across 128 patches, estimated / actual tokens has median 1.001 and 10th–90th percentile 0.996–1.004
(`E2.2-patches/cspaper/summary.json`). **The budget anomalies are not caused by bad cost estimates.**

### Many patch tokens buy nothing (E2.2)
Share of patch tokens on patches whose query did not improve over static and whose columns no later query
improved with: 0% at 25% and 50% drift, 32% at 75%, 39% at 100% (unlimited streams; `E2.2-patches/cspaper/`).

### Cell values, not structure, limit cspaper (E2.4)
| System | Structure F2 | Cell F1@0.20 | No rows / structure / values / fully right |
|---|---|---|---|
| Static, 100% drift | 0.022 | 0.016 | 40 / 19 / 0 / 0 |
| Unlimited, 0% drift | 0.640 | 0.167 | 6 / 34 / 19 / 0 |
| Unlimited, 100% drift | 0.650 | 0.187 | 6 / 36 / 17 / 0 |
| 10% budget, 25% drift | 0.639 | **0.230** | 7 / 34 / 18 / 0 |
| 10% budget, 100% drift | 0.574 | 0.166 | 7 / 39 / 13 / 0 |

No query is fully right in any stream. Patching recovers the structure (rows and joins) static loses; what remains
is wrong cell values. The odd "10% budget beats unlimited at 25% drift" point is entirely cell F1 (0.230 vs 0.185).
(`E2.4-errors/cspaper/summary.json`)

### Reading a column can make a query worse than leaving it empty (E2.3)
Between a budgeted and the unlimited stream at the same drift level, 88 query answers differ; in 31 the budgeted
(fewer patches) answer scores higher, and 28 of those 31 were answered **without their own patch**. Of the cells
that differ, 12,241 are filled in one stream and empty in the other; only 455 hold two different values
(`E2.3-order/cspaper/summary.json`). Patches never overwrite: a (column, document) is read at most once per stream.

**Case: `agent_framework` (qualitative).** `SELECT agent_framework, COUNT(paper_name) FROM cspaper WHERE
data_modality = 'Text' GROUP BY agent_framework` (25% drift):

| | NULL | Other | ToT | CoT | Multi-Agent | Score |
|---|---|---|---|---|---|---|
| Gold (138 text papers) | 107 | 14 | 1 | 6 | 10 | — |
| Unlimited: patched for every paper | 27 | 82 | 23 | 11 | 12 | 0.32 |
| 10% budget: patch skipped, values from an earlier scoped patch | 129 | 16 | 3 | 4 | 3 | 0.64 |

`agent_framework` only has a value when a paper uses an agent framework; gold leaves it empty for 107 of 138 text
papers. Read for every paper, the model assigns a framework to papers that have none (82 "Other", 23 "ToT"). The
budgeted stream's only values came from an earlier query's patch, scoped by pushdown to the papers that query
selected, so the rest stayed empty, which is right for most of them.

**Which papers were read, and how well (per paper, against gold; 164 of 200 papers match a gold row):**
- The first query of the unlimited stream (a `retrieval_method` query that also needs `agent_framework`) read
  `agent_framework` for all 171 in-scope papers in one 197k-token patch. The 10% budget (116k) could not afford it
  and skipped it; later queries then read the column for 58 papers, each scoped by its own filter.
- On the 45 papers read in both streams, the values are **identical** (12 of 36 gold-matched correct in both): the
  patch prompt's context made no difference here.
- On the 116 papers read only by the unlimited stream, gold is empty for 78 of the 95 matched. The model gave **all
  116** a framework (77 "Other", 21 "ToT"); 13 of 95 are right. Left empty, 78 of 95 would have been right.

So the loss is from *which documents are read*, and from the model never answering "none" for this column. It is
not from the prompt's context.

**Interpretation (to test on the other corpora):** for a *conditional* column (one that applies only when another
holds), an unconditional read invents values, and a wrong value costs more than a missing one, because it moves rows
into wrong groups. This explains the budget anomalies better than the patch order alone: a budgeted stream sometimes
wins by reading *less*. It suggests two system changes to test: read a conditional column only on the documents where
its condition holds, and an explicit "not applicable" answer in the patch prompt.

**Root cause: the field spec contradicts itself.** The patch prompt's line for the column (from the benchmark's
attribute file, the published protocol input) reads:

> agent_framework (text): main agent-style reasoning framework used by the system, choose one from [...], **if the
> system does not use agent, leave it empty**. Allowed values: CoT, ToT, Multi-Agent Collaboration, Other.
> **Never null: always give a value.** ...

The description says "leave it empty"; the attribute file marks the column not nullable, so the prompt adds "Never
null". The model follows the stronger instruction and picks a value (usually the catch-all "Other"). Of the 7
not-nullable columns across the five corpora whose description mentions an empty case, 5 are "use 0 if none" counts
or flags (consistent: never null, absence value 0); `agent_framework` (and possibly `performance_on_NQ`, cspaper)
are real contradictions. So this one anomaly is a benchmark-metadata artifact, not a general property of patching;
whether false fills matter elsewhere is measured per column below (E2.1).

### Per-column accuracy on the documents read (E2.1, unlimited stream at 100% drift)
On cspaper (`E2.1-columns/cspaper/columns.csv`), two other failure kinds dominate besides false fills:
- **Missed values deep in the paper.** `performance_on_hotpotqa`: gold has a value, prediction is empty, in 81% of
  cases; `evaluation_dataset` 46%. These values sit in results tables and evaluation sections.
- **Lists and derived counts.** `baseline` agrees with gold in 2% of cells where both have a value (gold
  `GPT-3|| GPT-4|| LLaMA2|| ...`, prediction `None` or a description such as "well-known general-purpose public
  embedding model"); `baseline_amount` (the count of baselines) 12%, often `0.0`.

## Shared read: 4-bit vs 16-bit vs OpenRouter (E1.2)
Same 216 reads of player (one per document and table, every column the 80 input queries use), same prompts:

| Backend | Held-out 20: score | Structure F2 | Cell F1@0.20 | All 100 queries |
|---|---|---|---|---|
| OpenRouter `qwen/qwen-2.5-7b-instruct` | 0.609 | 0.883 | 0.657 | 0.517 |
| Ollama 16-bit `qwen2.5:7b-instruct-fp16` | 0.590 | 0.880 | 0.639 | 0.490 |
| Ollama 4-bit `qwen2.5:7b-instruct` (Q4_K_M) | 0.560 | 0.868 | 0.615 | 0.482 |

With three 4-bit runs (the recorded one and two repeats, E1.1), same prompts every time:

| Run | Held-out 20 | All 100 (95% CI over queries) |
|---|---|---|
| 4-bit, recorded | 0.560 | 0.482 (0.422–0.542) |
| 4-bit, repeat 1 | 0.548 | 0.483 (0.423–0.544) |
| 4-bit, repeat 2 | 0.552 | 0.473 (0.412–0.533) |
| 16-bit | 0.590 | 0.490 (0.429–0.551) |
| OpenRouter | 0.609 | 0.517 (0.454–0.578) |

Share of extracted cells (2,035 per run) that are identical between two runs:

| | 4-bit rep 1 | 4-bit rep 2 | 16-bit | OpenRouter |
|---|---|---|---|---|
| 4-bit recorded | 0.949 | 0.955 | 0.885 | 0.871 |
| 4-bit rep 1 | | 0.957 | 0.888 | 0.881 |
| 4-bit rep 2 | | | 0.890 | 0.874 |
| 16-bit | | | | 0.913 |

**Reading:**
- **Run-to-run noise is real but small.** At temperature 0.1, about 5% of cells change between identical 4-bit
  runs, and the held-out score moves by up to 0.012 (all 100 queries: up to 0.010). Gaps below about 0.015 on 20
  queries are noise.
- **Quantization is a real, larger effect.** 4-bit vs 16-bit changes about 11% of cells, twice the run-to-run
  rate, and 16-bit scores above all three 4-bit runs (held-out +0.03 to +0.04).
- **16-bit is closer to OpenRouter than 4-bit is** (91% vs 87–88% identical cells), and the remaining gap
  (0.019 held-out, 0.027 on all 100) is about one to two noise widths. OpenRouter's serving stack (likely 16-bit
  or 8-bit, a different runtime) is not observable, so the rest is not attributed.
- **Implication for the paper:** results from the 4-bit server are slightly pessimistic; comparisons between systems
  run on the same server are unaffected in direction. The 95% CIs over queries (±0.06 on 100 queries) are much wider
  than the backend gaps, so per-query paired comparisons, not unpaired means, are needed to resolve gaps this size.
(`E1-reads/summary.json`, `E1-reads/openrouter_vs_ollama_cells.csv`)
(`results/quwarts_router_v3/player{,_ollama,_ollama_fp16}/shared_read_protocol/score_blank.json`)

## player

**Replay reproduces the recorded run** (all 30 streams identical; `E2-replay/live/player/verify.json`).

**Every patch token paid off (E2.2).** At every drift level, 0% of patch tokens went to patches whose query and
later users of its columns gained nothing (cspaper: up to 39%). Cost estimates: median estimated/actual 1.005
(10th–90th percentile 1.005–1.010). This is why player's budget curve is a steady staircase while cspaper's
saturates at 10%: on player each skipped patch costs score.

**The budget buys back cell values, not structure (E2.4).**

| System | Structure F2 | Cell F1@0.20 | No rows / structure / values / fully right |
|---|---|---|---|
| Static, 100% drift | 0.710 | 0.049 | 5 / 90 / 23 / 0 |
| 10% budget, 100% drift | 0.723 | 0.160 | 3 / 92 / 15 / 8 |
| 25% budget, 100% drift | 0.719 | 0.205 | 3 / 91 / 14 / 10 |
| 50% budget, 100% drift | 0.710 | 0.357 | 5 / 90 / 12 / 11 |
| Unlimited, 100% drift | 0.753 | 0.468 | 0 / 94 / 10 / 14 |

Unlike cspaper (static returns no rows for 40 of 59 queries), player's static database still returns the right
rows; the withheld columns come back empty, so only cell F1 collapses.

**Order effects are small and one-directional (E2.3).** 329 query answers differ between a budgeted and the unlimited
stream at the same level; the budgeted one is higher in only 15. No cell ever holds two different values across
streams (38,028 differing cells are all filled in one and empty in the other).

**Per-column (E2.1):** where both have a value, agreement is high (0.86–1.0 on 15 of 19 columns). Two columns fail
for metadata reasons:
- `player.position`: gold is empty for 65 of 141 players; the model fills 63 of them, almost always with
  "Frontcourt", for players whose documents never mention a position. The field line says *"choose one from
  ['Frontcourt', 'Backcourt'] ... Never null: always give a value."*
- `player.team` (a join key): empty in 42% of players who have one in gold. These players played for several teams;
  gold takes the last one listed (e.g. Jay Vincent: "... Philadelphia 76ers, and Los Angeles Lakers" → Lakers). The
  field says *"the current NBA team ..., or the last NBA team the player joined"*, but its workload examples are
  non-NBA clubs ('Bursaspor Basketbol', 'Cedevita Olimpija'), and the model returns nothing.

## Across corpora: "never null" columns whose gold is often empty

The cspaper `agent_framework` and player `position` cases are one pattern. Of the **132** columns the benchmark's
attribute files mark not nullable, **69 are empty in at least 5% of gold rows, and 57 of those are used by the
workloads** (`E2.1-columns/never_null_vs_gold.txt`). Med is most affected: `sequelae` is empty in 85% of gold rows,
`storage_conditions` 81%, `manufacturer` 71%, `activation_conditions` 70%, `diagnosis_challenges` 69%; also cspaper
`performance_on_hotpotqa` 85%, player `city.gdp` 76%, art `marriage` 71%. For each, the prompt says "Never null:
always give a value" (the published protocol input), so the model must invent a value where gold has none, and an
invented value scores worse than an empty one.

This is a benchmark-protocol confound that affects every system given the attribute files. **Experiment E7** (queued)
drops "Never null" for text fields (numeric "0 if none" counts and 0/1 flags keep it) and re-runs the player shared
read and the player, cspaper, art (0% and 100% drift) and med (0%) streams on the same 4-bit server.

## art

**Replay reproduces the recorded run** (`E2-replay/live/art/verify.json`). Cost estimates: median estimated/actual
0.997 (10th–90th 0.996–1.005). Patch tokens with no value: 0% at 25–75% drift, 16% at 100% (`E2.2-patches/art/`).

| System | Structure F2 | Cell F1@0.20 | No rows / structure / values / fully right |
|---|---|---|---|
| Static, 100% drift | 0.256 | 0.035 | 8 / 35 / 0 / 0 |
| 10% budget, 100% drift | 0.369 | 0.190 | 2 / 40 / 1 / 0 |
| 25% budget, 100% drift | 0.387 | 0.230 | 2 / 40 / 1 / 0 |
| 50% budget, 100% drift | 0.385 | 0.246 | 2 / 40 / 1 / 0 |
| Unlimited, 100% drift | 0.527 | 0.340 | 0 / 42 / 1 / 0 |

On art the budget buys back both structure (0.37 → 0.53) and cells; no query is fully right in any stream.
Order effects: 155 answers differ between a budgeted and the unlimited stream; the budgeted one is higher in 8
(`E2.3-order/art/summary.json`).

Never-null columns over-filled (E2.1): `marriage` (gold empty 71%, filled in 55% of those), `genre` (32%, 99%),
`century` (29%, 99%), `age` (25%, 98%), `zodiac` (14%, 75%).

## Across corpora: values are often right in substance but differ in form

Exact agreement (normalized strings, numbers within 20%) understates value quality for list-valued and free-text
columns. A lenient check (any shared list item; case, dashes and spacing unified) on the cells where both prediction
and gold have a value (`E2.1-columns/<corpus>/columns.csv`):

| Column | Exact | Lenient | Example (gold → prediction) |
|---|---|---|---|
| art.field | 0.13 | 0.92 | |
| art.art_institution | 0.003 | 0.58 | `China Academy of Art` → `China Academy of Art \|\| Académie des Beaux-Arts` |
| art.genre | 0.05 | 0.56 | `Abstract\|\|Geometric` → `Abstract \|\| Conceptual` |
| art.art_movement | 0.25 | 0.69 | `Surrealism` → `Surrealist` |
| art.century | 0.27 | 0.48 | `20th-21st` → `20th–21st` (en dash), or `20th` |
| art.birth_city | 0.40 | 0.80 | |
| cspaper.application_domain | 0.36 | 0.82 | |
| cspaper.data_modality | 0.70 | 0.99 | |

The benchmark's own tolerant score (normalized comparison, recorded on every stream) is only slightly higher than the
benchmark score at 100% drift, unlimited: cspaper 0.153 → 0.165, player 0.387 → 0.411, art 0.256 → 0.286,
med 0.086 → 0.095, legal 0.114 → 0.139. So most of these near-misses still break queries: a `GROUP BY` or a
comparison with a constant needs the exact label, and an extra list item puts a row in the wrong group. **Surface
form, not facts, is a large share of the remaining error on art and cspaper.**

### Canonicalizing to the workload's vocabulary does not help (E8, negative result)
Each query's served view was rewritten so that every text value (each list item) maps to the closest label in the
column's vocabulary known when the query arrives: declared allowed values plus the string constants that the build
workload and the queries so far compare the column with (same normalized form, else a close spelling), then
re-scored. No model calls (`E8-canon/<corpus>/summary.json`):

| Stream | Cells rewritten | Score before → after | Queries up / down |
|---|---|---|---|
| art, unlimited, 0% drift | 3,492 | 0.2698 → 0.2708 | 1 / 2 |
| art, unlimited, 100% drift | 3,377 | 0.2557 → 0.2555 | 0 / 2 |
| art, 10% budget, 100% drift | 3,354 | 0.1408 → 0.1408 | 0 / 0 |
| cspaper, unlimited, 0% / 100% drift | 162 / 216 | unchanged | 0 / 0 |

Why: the columns with the largest form gaps (`art_movement`, `genre`, `art_institution`) are only grouped by in
the workload, never compared with a constant, so the workload gives no vocabulary for them; where constants exist
(`marriage = 'Married'`), the rewrites are mostly case changes the scorer already ignores; and extra list items are
not removed by mapping. The form gap is in *output labels the system has no way to know* (gold's label set for a
`GROUP BY` column) and in list membership (which items gold counts), not in spellings of known constants.

## Run-to-run variance of a whole drift stream (E1.1)

The unlimited stream at 100% drift, re-run with every patch read again (fresh patch journal; same builds, same
4-bit server; `E1-variance/summary.json`):

| Corpus | Recorded | Repeat | Repeat − recorded (95% CI over queries) | Queries changed | Patch reads | Same prompt as recorded | Identical response |
|---|---|---|---|---|---|---|---|
| cspaper | 0.1533 | 0.1533 | 0.000 (0.000 – 0.000) | 0 of 59 | 1,009 | 1,009 | 786 (78%) |
| player | 0.3870 | 0.3885 | +0.0015 (−0.0019 – +0.0065) | 8 of 118 | 1,098 | 842 | 552 of 842 (66%) |

About a quarter to a third of patch responses differ between identical runs (mostly formatting and wording; on
player, different values also change which documents later patches are scoped to, so 256 prompts differ), but the
stream score moves by at most 0.002. **Stream-level noise is two orders of magnitude below the drift effects
(static vs adaptive: 0.15–0.35) and the budget effects (0.02–0.25) reported earlier**. Gaps of about 0.005 (e.g.
med's 100% budget 0.081 vs unlimited 0.086) are above this noise but still small enough to call marginal.

## med

**Replay reproduces the recorded run** (`E2-replay/live/med/verify.json`). Cost estimates: median estimated/actual
1.003 (10th–90th 1.002–1.005). **A third of med's patch tokens buy nothing:** 18% at 25% drift, 30–32% at 50–100%
(of 19.9M patch tokens at 100% drift, 6.3M; `E2.2-patches/med/`).

| System | Structure F2 | Cell F1@0.20 | No rows / structure / values / fully right |
|---|---|---|---|
| Static, 100% drift | 0.155 | 0.067 | 14 / 62 / 0 / 0 |
| 10% budget, 100% drift | 0.196 | 0.103 | 9 / 67 / 0 / 0 |
| 50% budget, 100% drift | 0.268 | 0.123 | 6 / 70 / 0 / 0 |
| 100% budget, 100% drift | 0.330 | 0.153 | 4 / 72 / 0 / 0 |
| Unlimited, 100% drift | 0.335 | 0.157 | 4 / 72 / 0 / 0 |

**On med, structure (rows and groups) is the bottleneck,** not cell values: structure F2 stays at 0.34 with
unlimited patching, and 72 of 76 queries have the wrong rows. They return **too few** rows, not too many: 61 of 76
queries have fewer result rows than gold, 8 more (cspaper 36 fewer / 1 more of 59; player 69 / 3 of 118; art 21 / 18
of 43). So false fills, though frequent, are not what breaks med's queries. The causes seen in the failing queries:

- **Fewer distinct group labels.** `GROUP BY administration_route` or `prescription_status` yields fewer groups than
  gold (values missing, or several gold labels collapsed into one).
- **Joins on list-valued keys.** `drug JOIN disease ON drug.disease_name = disease.disease_name`: in gold only 15 of
  100 drug rows match a disease (both sides hold `a||b||c` lists, and SQL equality on a list rarely matches); in
  ours 8 of 91. Our extraction also writes lists into `disease.disease_name` itself (e.g. `acute kidney injury ||
  chronic kidney disease`), so even fewer drug rows can join.

Per column (E2.1), med has the strongest false fills (`drug.activation_conditions`: gold empty 70%, filled in 96%;
`disease.risk_factors` 91%; `drug.prescription_status` 94%) and very low exact agreement on free-text columns
(`disease.treatment_challenges` 0.00 exact / 0.10 lenient; `disease.prognosis` 0.02 / 0.70;
`disease.diagnostic_methods` 0.06 / 0.94). **Med's free-text columns are compared and grouped as exact strings,
which no extraction matches**; this, with the list-valued join keys, bounds what any system can score on med.
Order effects: 94 answers differ across budgets at the same level, 17 higher with a budget (15 without their own patch).

### 16-bit on a whole drift stream (E1.2)
The player unlimited stream at 100% drift, built and patched entirely with `qwen2.5:7b-instruct-fp16` (fresh build
read, 2.04M tokens; patches 5.68M): **0.392** (95% CI 0.332–0.453), against 0.387 and 0.3885 for the two 4-bit runs;
static 0.0402 vs 0.0399 (`E1-variance/summary.json`). Quantization moves the drift stream by about +0.004, far less
than on the shared read (+0.03 held-out). The drift conclusions do not depend on the 4-bit model.

## E7: letting text fields be empty (dropping "Never null")

**Player shared read, 4-bit, same 216 reads with "Never null" removed from text fields**
(`QUWARTS_NULLABLE_TEXT=1`; `results/quwarts_router_v3/player_ollama_nullable/`):

| | Held-out 20 | All 100 | Structure F2 (all) | Cell F1 (all) |
|---|---|---|---|---|
| Recorded 4-bit | 0.560 | 0.4825 | 0.876 | 0.540 |
| Never-null dropped | 0.568 | 0.4801 | 0.869 | 0.545 |

Paired over the 100 queries: −0.002 (95% CI −0.022 to +0.016), 24 up and 27 down: **no effect**, and within the
run-to-run noise measured above. The instruction was not what drove the false fills: `player.position` is still filled
for 61 of the 65 players whose gold is empty (65 before). The field's description ("choose one from ['Frontcourt',
'Backcourt']") and its allowed values still invite a guess. **E7b** (queued) adds a field-level instruction to answer
null when the document does not state the value and not to guess from the allowed values.

## legal

**Replay reproduces the recorded run** (`E2-replay/live/legal/verify.json`). Cost estimates: median estimated/actual
1.000 (10th–90th 0.999–1.001). Patch tokens with no value, unlimited streams: 50% at 25% drift, 33% at 50%, 40% at
75%, 39% at 100% (of 29.9M); at 100% drift the 50% budget wastes **55%** of its patch tokens, the 25% budget 0%.

| System | Structure F2 | Cell F1@0.20 | No rows / structure / values / fully right |
|---|---|---|---|
| Static, 100% drift | 0.396 | 0.013 | 9 / 12 / 9 / 0 |
| 10% budget, 100% drift | 0.561 | 0.081 | 5 / 16 / 9 / 0 |
| 25% budget, 100% drift | 0.636 | 0.167 | 3 / 17 / 10 / 0 |
| 50% budget, 100% drift | 0.607 | 0.102 | 3 / 18 / 9 / 0 |
| 75% budget / unlimited, 100% drift | 0.758 | 0.168 | 1 / 17 / 12 / 0 |

### The "25% beats 50%" anomaly, patch by patch (E2.2)
Patches at 100% drift (position, tokens, gain on its own query, later queries using its columns, their summed gain):

| Stream | Patches |
|---|---|
| Unlimited | 0: 4.0M, +0.19, 5 later (+0.36) · **1: 4.0M, 0, 1 later (0)** · **2: 4.0M, 0, 1 later (0)** · 4: 3.9M, +0.22, 7 later (+1.37) · 7: 0.1M, +0.33 · 8: 2.3M · 10: 3.8M, 7 later (+1.09) · 11 · 16 · 23 · ... |
| 50% budget | 0 · **1 · 2** · 8 · 26, then the budget is spent: 4, 10, 16 are skipped |
| 25% budget | 0 · 8 (12 later, +2.31) · 25 (4 later, +1.39) · 26 (3 later, +1.21); 1 and 2 do not fit, so they are skipped |

The 50% budget spends 8M of its 14.5M on patches 1 and 2, which help nothing; the 25% budget cannot afford them,
so it saves its budget for patches 8, 25 and 26, which feed 19 later queries.

**Why patches 1 and 2 buy nothing (qualitative).** Both read a counsel column for all 570 cases to answer
`SELECT first_judge, MIN(counsel_for_respondent) ... GROUP BY first_judge` (and the same with
`counsel_for_applicant` by `evidence`). The answer is one alphabetically-first name per group, so any extra name in a
cell changes it; and the model's notion of "counsel" differs from gold's: gold records the barrister (`Mr T
Reilly`), the model often the firm (`Australian Government Solicitor`, `Clayton Utz`) or "The applicant appeared
in person".

## Across corpora: MIN/MAX over a text column is nearly unwinnable and expensive

Queries whose answer is `MIN` or `MAX` of a text column, unlimited streams at 100% drift:

| Corpus | Such queries | Their mean score | Other queries' mean score | Patch tokens they trigger |
|---|---|---|---|---|
| med | 30 of 76 | 0.000 | 0.142 | 8.6M of 19.9M |
| legal | 12 of 30 | 0.000 | 0.191 | 12.0M of 29.9M |
| player | 3 of 118 | 0.444 | 0.386 | 0 |
| cspaper, art | 0 | — | — | — |
| **All** | **45 of 326** | **0.03** | **0.265** | **20.5M of 62.8M (33%)** |

Their patches do feed some later queries: on legal, 8.0M of their 12.0M tokens bought nothing and they carry 0.3 of
the 5.3 summed later gain; on med, 3.5M of 8.6M bought nothing but they carry 1.4 of 3.2. **Experiment E3.3
(queued):** a `fragile` budget policy that never patches for such a query (a later query that needs the same columns
patches them itself), at every budget on legal and med, with cspaper as a control (no such queries).

## DocETL on the drift queries (interim, run still in progress)

DocETL (0.2.6, same local 4-bit model, one map per query and table with the fair prompt) has scored 107 of the 326
drift test queries so far (`results/docetl_drift_ollama/<corpus>/per_query.json`). On those queries, at 100% drift:

| Corpus | Queries | DocETL | Ours, adaptive | Ours, static | DocETL tokens (per query) | Ours: patches on these queries + one shared build |
|---|---|---|---|---|---|---|
| cspaper | 36 of 59 | 0.089 | 0.114 | 0.010 | 13.0M (362k) | 1.16M + 0.40M |
| player | 36 of 118 | 0.095 | 0.444 | 0.038 | 64.2M (1.78M) | 3.73M + 2.04M |
| art | 9 of 43 | 0.069 | 0.137 | 0.000 | 12.3M (1.37M) | 4.07M + 2.43M |
| med | 25 of 76 | 0.066 | 0.105 | 0.033 | 55.6M (2.23M) | 13.95M + 2.54M |
| legal | 1 of 30 | 0.118 | 0.185 | 0.000 | 17.9M | 4.01M + 4.56M |

Interim reading: adaptive patching scores above DocETL on every corpus so far, at a fraction of its tokens (DocETL
re-reads every document for each query; our build is shared and patches read only missing columns). DocETL is above
our static build everywhere, as expected when the static build lacks the drifted columns. Numbers will change as the
remaining 219 queries finish.

**Update (2026-10-02 23:10): cspaper, player and med complete.** On all their test queries at 100% drift: cspaper
DocETL 0.105 vs adaptive 0.153 (static 0.008; 20.7M vs 1.56M tokens incl. our build); player 0.081 vs 0.387 (static
0.040; 190.6M vs 7.71M); med 0.056 vs 0.086 (static 0.031; 170.6M vs 22.46M). Art 30 of 43 (0.151 vs 0.235), legal 8 of
30 (0.016 vs 0.137) still running. The player join collapse holds on all 118 queries: DocETL 0.125 / 0.034 / 0.008 for
0 / 1 / 2+ joins, ours 0.369 / 0.438 / 0.382 (`E9-query-types/summary.json`).

**Player drift streams with "Never null" dropped for text fields** (fresh build and patches, 4-bit;
`E7-stream-nullable-player/`):

| Drift | Recorded | Never-null dropped | Paired difference | Queries up / down |
|---|---|---|---|---|
| 0% | 0.3794 | 0.3734 | −0.006 | 12 / 24 |
| 100% | 0.3870 | 0.3843 | −0.003 | 16 / 22 |

Slightly negative on player (more queries down than up, by amounts near the stream noise of ±0.002): letting text
fields be empty loses some values gold has, more than it removes invented ones. cspaper, art and med streams follow.

**E7b: a field-level null instruction makes it worse** (re-run with the fixed prompts, 2026-10-02). Text fields
relaxed as in E7, plus on each text field's line "If the document does not state it, answer null; do not guess from
the allowed values" (player shared read, 4-bit; `results/quwarts_router_v3/player_ollama_nullhint/`):

| | Held-out 20 | All 100 | Structure F2 | Cell F1 |
|---|---|---|---|---|
| Recorded 4-bit | 0.560 | 0.483 | 0.876 | 0.540 |
| E7b null hint | 0.531 | 0.430 | 0.872 | 0.487 |

Paired over 100 queries: **−0.053 (95% CI −0.086 to −0.021)**, 21 up / 37 down; far outside the noise. On 10 player
columns checked cell by cell against gold, false fills drop from 75 to 58 (of about 117 gold-empty cells), but misses
rise from 110 to 131 (of 816 gold values); most of the increase is the join key `player.team` (37 → 55 of 139 players
left empty), and a missing join key drops a player from every join. `player.position` false fills fall only from 65
to 52 of 65. (The invalid first run gave −0.062; same conclusion.)

*(The null-handling conclusion is restated below, after E7c, with all three variants on the fixed prompts.)*

**cspaper drift streams with "Never null" dropped for text fields** (re-run with the fixed prompts, 2026-10-02;
`E7-stream-nullable-cspaper/`):

| Drift | Recorded | Never-null dropped | Paired difference | Queries up / down |
|---|---|---|---|---|
| 0% | 0.1341 | 0.1214 | **−0.013** | 4 / 11 |
| 100% | 0.1533 | 0.1730 | **+0.020** | 8 / 4 |

Mixed on cspaper: negative at 0% drift, positive at 100%. Cell by cell at 100% drift: `agent_framework` false fills
fall from 108 to 50 of 151 gold-empty papers (misses rise from 9 to 24 of 49), but other text columns lose values gold
has: `baseline` misses 18 → 57 of 188, `evaluation_dataset` 88 → 109 of 193. (The invalid first run gave +0.013 at 0%
and +0.018 at 100%; the 0% result changed sign with the prompt fix.) E7c, relaxing only `agent_framework`, is being
re-run.

**E7c: relaxing only `cspaper.agent_framework`** (the one text field whose description names an empty case; re-run
with the fixed prompts, 2026-10-02; `E7c-stream-contradicted-cspaper/`):

| Drift | Recorded | E7 (all text relaxed) | E7c (agent_framework only) |
|---|---|---|---|
| 0% | 0.1341 | 0.1214 (−0.013; 4 up / 11 down) | 0.1315 (−0.003; 7 / 7) |
| 100% | 0.1533 | 0.1730 (+0.020; 8 / 4) | 0.1380 (**−0.015**; 6 / 8) |

At 100% drift E7c leaves the other columns as recorded (`baseline` misses 20 of 188, `evaluation_dataset` 89 of 193)
and cuts `agent_framework` false fills from 108 to 74 of 151 (misses 9 → 16 of 49), yet the stream score *falls*.
So the gain of E7 at 100% does not come from `agent_framework`; it comes from the other relaxed columns (where gold
is often empty and leaving cells empty changes which rows a filter or group keeps). The contradictory column
explains the specific query examined above and the false fills, but fixing it does not help the stream.

**Conclusion on null handling (E7, E7b, E7c; all with the fixed prompts):** dropping "Never null" moves scores by
−0.013 to +0.020 depending on corpus and drift level, a field-level null hint costs −0.053, and fixing the one
contradictory field costs up to −0.015. On this 7B model, prompt-level control of empty answers trades invented values
for missed ones, with no consistent gain. It is not a lever worth carrying into the system; the never-null confound in
the benchmark's metadata bounds every system given the same attribute files.

## E2.1b: prompt width (RQ2) — player

Re-run with the fixed prompts (2026-10-02). The same 12 player columns read on all 141 players, 1, 3, 6 or 12 columns
per read (fixed column order, first window of each document), scored on the values as committed (absence values of
never-null counts applied) (`E2.1b-width/player/`):

| Columns per read | Exact agreement (both have a value) | False-fill rate | Miss rate | Tokens |
|---|---|---|---|---|
| 1 | 0.806 | 0.703 | 0.036 | 6.48M |
| 3 | 0.797 | 0.780 | 0.055 | 2.23M |
| 6 | 0.788 | 0.747 | 0.041 | 1.16M |
| 12 | 0.780 | 0.769 | 0.041 | 0.63M |

Narrower reads are slightly more accurate (+2.6 points from 12 to 1 column per read) at 10× the tokens (the invalid
run gave +2.3). On player, prompt width is a weak lever.

(An earlier version of this table scored raw responses and showed width-1 reads missing far more values; that was a
measurement error: narrow reads answer `null` for a "0 if none" count, which the database stores as 0.)

**E2.1b width — art** (re-run with the fixed prompts; 12 columns, 100 artists; `E2.1b-width/art/`):

| Columns per read | Exact agreement | Lenient agreement | False-fill rate | Miss rate | Tokens |
|---|---|---|---|---|---|
| 1 | 0.449 | 0.589 | 0.98 | 0.051 | 1.21M |
| 3 | 0.467 | 0.612 | 0.92 | 0.092 | 0.48M |
| 6 | 0.466 | 0.620 | 0.85 | 0.124 | 0.29M |
| 12 | 0.483 | 0.636 | **0.60** | 0.112 | 0.20M |

The opposite of player: on art **wider reads are better** (+3.4 points exact, +4.7 lenient from 1 to 12 columns) and
6× cheaper (the invalid run: +3.7 / +4.3). Asked for one column, the model fills a value for 98% of gold-empty cells;
asked for twelve, 60%: a single-field prompt pushes the model to produce *some* value. Prompt width trades false
fills (narrow reads) against misses (wide reads), and the balance depends on how often the corpus's gold is empty.

**E2.1b width — legal** (re-run with the fixed prompts; 12 columns, 60 cases; `E2.1b-width/legal/`):

| Columns per read | Exact agreement | Lenient agreement | False-fill rate | Miss rate | Tokens |
|---|---|---|---|---|---|
| 1 | **0.547** | 0.576 | 0.176 | 0.084 | 3.65M |
| 3 | 0.504 | 0.557 | 0.135 | 0.136 | 1.25M |
| 6 | 0.475 | 0.537 | 0.135 | 0.121 | 0.65M |
| 12 | 0.479 | 0.533 | 0.162 | 0.099 | 0.35M |

On legal narrow reads are clearly better (+6.8 points exact from 12 to 1 column per read; the invalid run gave
+6.9), at 10× the tokens. False fills stay low at every width (legal's gold is rarely empty on these columns).

**E2.1b width — cspaper** (re-run with the fixed prompts; 12 columns, 40 papers; `E2.1b-width/cspaper/`): flat.
Exact agreement 0.572 / 0.581 / 0.575 / 0.580 at 1 / 3 / 6 / 12 columns per read (lenient 0.650 / 0.691 / 0.693 /
0.694); false fills 0.40 at width 1 vs 0.18–0.21 wider; tokens 531k vs 84k. Width does not matter on cspaper except
for cost and false fills (the invalid run was also flat).

**E2.1b width — med** (re-run with the fixed prompts; disease table, 12 free-text columns, 40 diseases;
`E2.1b-width/med/`): exact agreement is near zero at every width (0.040 / 0.052 / 0.100 / 0.062 at 1 / 3 / 6 / 12),
lenient 0.518 / 0.535 / 0.542 / 0.458; false fills 0.77–0.85 throughout; tokens 4.0M vs 0.40M.

### Prompt width: summary over the five corpora (RQ2)

All five re-run with the fixed prompts (2026-10-02):

| Corpus | Exact, 1 col/read | Exact, 12 cols/read | Difference | Token ratio (1 vs 12) |
|---|---|---|---|---|
| legal | 0.547 | 0.479 | **+0.068** | 10× |
| player | 0.806 | 0.780 | +0.026 | 10× |
| cspaper | 0.572 | 0.580 | −0.008 | 6× |
| med | 0.040 | 0.062 | −0.022 (lenient +0.060) | 10× |
| art | 0.449 | 0.483 | −0.034 | 6× |

There is no general prompt-width effect. A one-column read is never cheaper; it is better on two corpora (legal,
player), worse on one (art), flat on cspaper, and mixed on med (worse exact, better lenient). It invents more values
where gold is often empty (art 98% false fills at width 1, med 85%). **Answer to RQ2 on this model:** patch reads are
not systematically more accurate because they ask for fewer columns; the adaptive curve's small rises under drift
(cspaper +0.02, player +0.01) are better explained by the order and scope effects found in E2.3 (which documents get
read, which values a narrower scope leaves empty) than by prompt width. The invalid first runs gave the same signs on
every corpus.

## E3.3: the `fragile` budget policy (skip patches for MIN/MAX-over-text queries) — legal

Re-run with the fixed prompts (2026-10-02). All 25 budgeted streams (5 budgets × 5 drift levels), same budgets as
the recorded first-come-first-served (fcfs) sweep, reads reused from the journals (`E3.2-fragile/live/legal/`,
comparison in `E3-policies/legal/summary.json`):

| Drift | Policy | 10% | 25% | 50% | 75% | 100% | Unlimited |
|---|---|---|---|---|---|---|---|
| 50% | fcfs | 0.130 | **0.090** | 0.127 | 0.127 | 0.127 | 0.127 |
| 50% | fragile | 0.130 | 0.131 | 0.122 | 0.122 | 0.122 | |
| 75% | fcfs | 0.069 | 0.117 | **0.070** | 0.113 | 0.113 | 0.113 |
| 75% | fragile | 0.069 | 0.117 | 0.106 | 0.106 | 0.106 | |
| 100% | fcfs | 0.052 | 0.110 | **0.053** | 0.114 | 0.114 | 0.114 |
| 100% | fragile | 0.052 | 0.110 | **0.107** | 0.107 | 0.107 | |

Over the 25 streams: mean score **0.1136 vs 0.1106**, tokens **158M vs 219M (−28%)**. The 50%-budget collapses at
75% and 100% drift (0.070, 0.053) and the 25% dip at 50% drift (0.090) are gone; score no longer falls when the
budget grows past 25% (it levels off). The cost: at large budgets the policy saturates just below unlimited (0.107 vs
0.114 at 100% drift; 0.122 vs 0.127 at 50%), because the skipped patches would have helped a few later queries.
(The invalid first run gave 0.1137 vs 0.1106 and the same −28%.)

Also visible: at 25% and 50% drift, the **10% budget beats unlimited** (0.130 vs 0.122 / 0.127) under both policies.
The same over-reading effect as on cspaper (reading a column for every document hurts some later queries) shows up
on legal too.

**`fragile` policy — med** (re-run with the fixed prompts, 2026-10-02; 30 of 76 test queries are MIN/MAX over text;
`E3-policies/med/summary.json`):

| Drift | Policy | 10% | 25% | 50% | 75% | 100% | Unlimited (tokens) |
|---|---|---|---|---|---|---|---|
| 50% | fcfs | 0.078 | 0.075 | 0.088 | 0.093 | 0.093 | 0.0935 (11.1M) |
| 50% | fragile | 0.076 | 0.089 | **0.093** (7.3M) | 0.093 | 0.093 | |
| 75% | fcfs | 0.057 | 0.057 | 0.072 | 0.081 | 0.081 | 0.0809 (14.6M) |
| 75% | fragile | 0.057 | 0.066 | 0.075 | **0.080** (10.8M) | 0.080 | |
| 100% | fcfs | 0.051 | 0.055 | 0.060 | 0.075 | 0.081 | 0.0858 (19.9M) |
| 100% | fragile | 0.051 | 0.069 | 0.078 | **0.084** (12.7M) | 0.084 | |

Over the 25 streams: mean **0.0828 vs 0.0797**, tokens **130M vs 154M (−16%)**, and score rises with budget at every
drift level (fcfs is non-monotone at 50% drift). On med the policy **matches unlimited patching with about two thirds
of its tokens** (100% drift: 0.084 at 12.7M vs 0.0858 at 19.9M; 50%: 0.093 at 7.3M vs 0.0935 at 11.1M). The skipped
patches' columns are picked up by later queries' own patches, so little is lost at large budgets.
**Correction:** the invalid first run showed the policy *beating* unlimited (0.087 at 100% drift, 0.098 at 50%); with
the fixed prompts it matches unlimited, it does not beat it.

## E9: scores by query type

Every drift test query classified by its SQL (sqlglot): joins, aggregation (MIN/MAX split by text vs numeric
column), filter kind, number of predicates, extras (HAVING / ORDER / LIMIT / CASE); scores per system at 100% drift
unless stated; DocETL on the queries it has finished (218 of 326 at the time of writing)
(`E9-query-types/summary.json`, `per_query.csv`). **All 326 drift test queries have a GROUP BY** (the
`attribute_pool` test set is built from grouped queries), so grouping is not a usable dimension here.

**Aggregation (all corpora):**

| Aggregation | n | Static | Adaptive 0% | Adaptive 100% | 25% budget | 50% budget | DocETL (n) | Structure F2 | Cell F1 | Patch tokens |
|---|---|---|---|---|---|---|---|---|---|---|
| AVG / SUM | 88 | 0.017 | 0.357 | 0.360 | 0.160 | 0.272 | 0.086 (54) | 0.718 | 0.444 | 5.4M |
| MIN/MAX over numbers | 70 | 0.002 | 0.236 | 0.238 | 0.113 | 0.160 | 0.083 (40) | 0.608 | 0.324 | 17.6M |
| COUNT only | 123 | 0.052 | 0.206 | 0.211 | 0.166 | 0.172 | 0.120 (99) | 0.568 | 0.279 | 19.2M |
| MIN/MAX over text | 45 | 0.022 | 0.041 | 0.030 | 0.036 | 0.030 | 0.001 (25) | 0.499 | 0.040 | 20.5M |

Numeric aggregates are the easiest (AVG/SUM 0.36), COUNT is middling, and MIN/MAX over text is unwinnable for every
system (ours 0.03, DocETL 0.001), with the lowest cell F1 (0.04) while taking the most patch tokens (see E3.3).

**Joins (only player and med have joins; within corpus):**

| Corpus | Joins | n | Adaptive 100% | Static | DocETL (n) |
|---|---|---|---|---|---|
| player | 0 | 68 | 0.369 | 0.045 | 0.141 (43) |
| player | 1 | 26 | 0.438 | 0.065 | 0.038 (19) |
| player | 2+ | 24 | 0.382 | 0.000 | 0.011 (18) |
| med | 0 | 39 | 0.090 | 0.031 | 0.070 (29) |
| med | 1 | 37 | 0.081 | 0.031 | 0.066 (25) |

**DocETL collapses with joins on player (0.141 → 0.038 → 0.011) while ours does not (0.37 → 0.44 → 0.38).** A likely
cause (not yet checked value by value): DocETL extracts each table with its own per-query map, so join keys
extracted for different tables need not match, while our shared build reads every table's join keys with the same
field specs. On med both are flat (its
joins fail for both, on list-valued keys; see med above). Joins are also the most budget-sensitive: at a 25% budget,
1-join and 2+-join queries fall to 0.092 and 0.106 (unlimited 0.229 and 0.382), since one missing join-key column
zeroes the whole query.

**Filters and predicates:** numeric-only filters score highest (0.449, n=13); string equality / IN 0.255 (n=167); no
filter 0.187 (n=143). Queries with HAVING / ORDER / LIMIT / CASE score higher (0.405 vs 0.214), mostly because they
are concentrated on player.

**`fragile` policy — cspaper (control, no such queries; re-run with the fixed prompts):** all 25 streams identical
to the recorded sweep (mean 0.1453, 7.87M tokens in both, 0 model calls): the policy is an exact no-op where there
is nothing to skip. (The invalid first run differed slightly and made 740 calls with changed prompts, which is how
the prompt bug was found.)

## E3.2: budget policies on cspaper (all five)

25 streams per policy (5 budgets × 5 drift levels), same budgets, reads reused from the journals (new reads paid);
`E3-policies/cspaper/summary.json`. Policies: **fcfs** (recorded: any patch that fits), **fragile** (skip MIN/MAX-
over-text queries), **oracle** (hindsight reference: skip patches that bought nothing in the unlimited stream),
**cap** (also skip any patch estimated above 25% of the whole budget), **pace** (spend no faster than the stream
advances: after query k of n, at most budget × (k/n + 0.25)).

| Policy | Mean score | Tokens | 100% drift: 10% / 25% / 50% / 75% / 100% budget |
|---|---|---|---|
| fcfs | 0.1453 | 7.87M | 0.120 / 0.137 / 0.147 / 0.153 / 0.153 |
| fragile | 0.1453 | 7.87M | identical to fcfs (no such queries) |
| oracle | 0.1453 | 7.20M (−9%) | 0.120 / 0.137 / 0.147 / 0.153 / 0.153 |
| cap | 0.1398 | 6.11M (−22%) | 0.027 / 0.129 / 0.128 / 0.156 / 0.153 |
| pace | **0.1466** | **6.04M (−23%)** | 0.100 / 0.132 / 0.125 / 0.153 / **0.172** (0.54M) |

Unlimited at 100% drift: 0.153 at 1.16M tokens.

- **oracle** confirms the patch accounting: skipping patches that bought nothing saves 9% of tokens and changes no
  score. It does not remove cspaper's oddities (e.g. the 10% budget beating unlimited at 25% drift), because those come
  from patches that *do* help their own query but over-read for later ones.
- **cap** hurts small budgets (at 10% almost every patch exceeds a quarter of the budget: 0.027 at 100% drift).
- **pace** is the best policy on cspaper: highest mean, 23% fewer tokens, and above unlimited at high budgets (100%
  drift: 0.172 at 0.54M vs 0.153 at 1.16M; 75% drift: 0.192 at 0.49M vs 0.149 at 0.69M). By spending gradually it
  skips the early patches that read a column for every paper (the over-reading found in E2.3), leaving later, scoped
  patches to read fewer documents. It is not monotone in budget (100% drift: 0.132 at 25% vs 0.125 at 50%), so it is
  not yet a policy to recommend on its own; legal and med follow.

## E3.2: budget policies on legal (all five)

(`E3-policies/legal/summary.json`; definitions as for cspaper above.)

| Policy | Mean score (25 streams) | Tokens | 100% drift: 10% / 25% / 50% / 75% / 100% budget |
|---|---|---|---|
| fcfs | 0.1106 | 219M | 0.052 / 0.110 / **0.053** / 0.114 / 0.114 |
| fragile | **0.1136** | **158M** | 0.052 / 0.110 / 0.107 / 0.107 / 0.107 |
| oracle | 0.1129 | 158M | 0.052 / 0.110 / 0.106 / 0.106 / 0.106 |
| cap | 0.0992 | 167M | 0.037 / 0.031 / 0.078 / 0.114 / 0.114 |
| pace | 0.1030 | 177M | 0.032 / 0.073 / 0.079 / 0.101 / 0.109 |

- **fragile matches the hindsight oracle** on legal (0.1136 vs 0.1129, the same 158M tokens): a rule read off the
  SQL (skip MIN/MAX over text) captures what hindsight about wasted patches captures.
- **cap** hurts small budgets again (25% budget at 100% drift: 0.031 vs fcfs 0.110).
- **pace is worse than fcfs on legal** (0.1030 vs 0.1106); it was the best policy on cspaper (0.1466 vs 0.1453).
  Pacing withholds budget from early patches; on legal the early patches include the useful ones (patches 0 and 4
  feed 12 later queries, see the patch-by-patch table), so delaying them costs score. **No single generic policy wins
  on both corpora; the SQL-based `fragile` rule is the only one that never hurts** (legal +0.003, med +0.003,
  cspaper no-op).

**Oracle on med** (`E3-policies/med/summary.json`): 0.0797, identical to fcfs, at 130M vs 154M tokens (−16%); the
`fragile` rule is *better* than this hindsight oracle on med (0.0828 at 130M). The oracle only skips patches that bought
nothing; the fragile rule also skips patches whose columns later queries read better under their own, narrower scope.

**Cap on med**: 0.0812 at 147M tokens (fcfs 0.0797 at 154M, fragile 0.0828 at 130M); it hurts the 10% budget (0.041 vs
0.051 at 100% drift) and helps the 25% budget (0.084 vs 0.055). Pace on med, and all policies on player and art, run
on the next job.

**Pace on med** (finished on job 16050764, A800 40GB node; same 4-bit model): 0.0821 at 145M tokens.

**Budget policies on the three corpora with budget anomalies** (mean over 25 streams each; tokens in parentheses):

| Policy | cspaper | legal | med |
|---|---|---|---|
| fcfs (recorded) | 0.1453 (7.9M) | 0.1106 (219M) | 0.0797 (154M) |
| fragile | 0.1453 (7.9M) | **0.1136** (158M) | **0.0828** (130M) |
| oracle (hindsight) | 0.1453 (7.2M) | 0.1129 (158M) | 0.0797 (130M) |
| cap | 0.1398 (6.1M) | 0.0992 (167M) | 0.0812 (147M) |
| pace | **0.1466** (6.0M) | 0.1030 (177M) | 0.0821 (145M) |

The SQL-based `fragile` rule is the best or tied-best on legal and med, a no-op on cspaper, and never below fcfs; it
matches or beats the hindsight oracle everywhere. Pacing is best on cspaper and second on med but loses on legal;
the per-patch cap is the weakest overall. Player and art follow.

## E6.2: other local models

**Llama 3.1 8B (4-bit), player shared read** (same 216 reads and prompts; 4 slots at a 16k context on the A800 node;
0 prompts possibly truncated, 0 answers cut off; `results/quwarts_router_v3/player_ollama_llama8b/`):

| Model | Held-out 20 | Structure F2 | Cell F1 | All 100 queries |
|---|---|---|---|---|
| Qwen 2.5 7B, 4-bit | 0.560 | 0.868 | 0.615 | 0.482 |
| Qwen 2.5 7B, 16-bit | 0.590 | 0.880 | 0.639 | 0.490 |
| Llama 3.1 8B, 4-bit | 0.466 | 0.781 | 0.565 | 0.468 |

Llama is lower on the held-out queries (−0.094), mostly in structure (0.781 vs 0.868), and close on all 100 (−0.014).
Drift streams on player and cspaper follow, to test whether adaptive vs static holds across model families.

**Llama 3.1 8B, player drift streams** (fresh build and patches with Llama; `E6.2-stream-llama8b-player/`; 1,742
calls, 0 prompts possibly truncated, 4 answers cut off):

| Model | Adaptive, 0% drift | Adaptive, 100% | Static, 100% | Patch tokens at 100% |
|---|---|---|---|---|
| Qwen 2.5 7B, 4-bit (recorded) | 0.379 | 0.387 | 0.040 | 5.67M |
| Llama 3.1 8B, 4-bit | 0.356 | 0.359 | 0.040 | 5.76M |

**The drift result holds across model families**: with Llama the adaptive stream keeps its score from 0% to 100%
drift (0.356 → 0.359) while the static build collapses to the same 0.040, at the same patch cost. Llama is about 0.03
below Qwen throughout.

**Llama 3.1 8B, cspaper drift streams** (`E6.2-stream-llama8b-cspaper/`):

| Model | Adaptive, 0% drift | Adaptive, 100% | Static, 100% | Patch tokens at 100% |
|---|---|---|---|---|
| Qwen 2.5 7B, 4-bit (recorded) | 0.134 | 0.153 | 0.008 | 1.16M |
| Llama 3.1 8B, 4-bit | 0.149 | 0.125 | 0.008 | 1.26M |

On cspaper Llama starts higher than Qwen (0.149 vs 0.134) and loses some score under drift (0.125 at 100%), where
Qwen gained; adaptive still recovers most of what static loses (static 0.008 for both). Across the two corpora the
adaptive-vs-static gap holds for both model families; the small rises of Qwen's adaptive curve under drift are
model-specific.

**Qwen 2.5 32B (4-bit), player shared read** (2 slots at a 16k context, whole A800 40GB; 216 calls, 0 prompts possibly
truncated, 0 answers cut off, 61.7 s per call; `results/quwarts_router_v3/player_ollama_qwen32b/`):

| Model | Held-out 20 | Structure F2 | Cell F1 | All 100 queries |
|---|---|---|---|---|
| Llama 3.1 8B, 4-bit | 0.466 | 0.781 | 0.565 | 0.468 |
| Qwen 2.5 7B, 4-bit | 0.560 | 0.868 | 0.615 | 0.482 |
| Qwen 2.5 7B, 16-bit | 0.590 | 0.880 | 0.639 | 0.490 |
| **Qwen 2.5 32B, 4-bit** | **0.690** | **0.916** | **0.714** | **0.575** |

Model scale is the largest single effect measured so far on the shared read: +0.13 held-out and +0.09 on all 100
queries over the 7B model, in both structure and cell values (far beyond the 0.01 run-to-run noise and the 0.03 of
quantization). Its drift streams on cspaper and player follow.

**Qwen 2.5 32B, cspaper drift streams** (`E6.2-stream-qwen32b-cspaper/`):

| Model | Adaptive, 0% drift | Adaptive, 100% | Static, 100% | Patch tokens at 100% |
|---|---|---|---|---|
| Qwen 2.5 7B, 4-bit (recorded) | 0.134 | 0.153 | 0.008 | 1.16M |
| Llama 3.1 8B, 4-bit | 0.149 | 0.125 | 0.008 | 1.26M |
| **Qwen 2.5 32B, 4-bit** | **0.162** | **0.224** | 0.008 | 1.21M |

With 32B the adaptive stream not only holds under drift but rises (0.162 → 0.224), and static collapses to the same
0.008. The patch cost is the same (1.2M). So the rise of the adaptive curve under drift seen with Qwen 7B is larger
with a stronger model: patches read the drifted columns with each new query's context, and a stronger model uses that
context better than the build read's.

**Qwen 2.5 32B, player drift stream at 100% drift** (`E6.2-stream-qwen32b-player/`):

| Model | Adaptive, 100% drift | Static, 100% drift | Patch tokens |
|---|---|---|---|
| Qwen 2.5 7B, 4-bit (recorded) | 0.387 | 0.040 | 5.67M |
| Llama 3.1 8B, 4-bit | 0.359 | 0.040 | 5.76M |
| **Qwen 2.5 32B, 4-bit** | **0.421** | 0.052 | 5.70M |

**E6.2 conclusion:** across three models (Llama 3.1 8B, Qwen 2.5 7B and 32B) and two corpora, adaptive patching keeps
its score under full drift while the static build collapses to 0.01–0.05, at the same patch cost for every model. A
stronger model raises every number (32B: player 0.421, cspaper 0.224 at 100% drift) without changing the patch cost,
so the adaptive-vs-static result is not an artifact of the 7B model.

## E3.2: budget policies on player

(`E3-policies/player/summary.json`; player has no MIN/MAX-over-text patches to skip, so `fragile` = fcfs.)

| Policy | Mean score | Tokens | 100% drift: 10% / 25% / 50% / 75% / 100% budget |
|---|---|---|---|
| fcfs | **0.3363** | 43.0M | 0.142 / 0.176 / 0.292 / 0.355 / 0.387 |
| oracle | 0.3363 | 43.0M | identical (no patch on player bought nothing) |
| cap | 0.3076 | 29.8M | 0.120 / 0.120 / 0.150 / 0.355 / 0.387 |
| pace | 0.3260 | 41.5M | 0.126 / 0.150 / 0.318 / 0.337 / 0.347 |

On player every patch pays off (E2.2), so first-come-first-served is already the best policy: skipping or delaying
patches only loses score (cap −0.029, pace −0.010). This is the counterpart of legal and med, where a third of patch
tokens bought nothing and skipping them helped.

## E3.2: budget policies on art, and all five corpora

Art (`E3-policies/art/summary.json`; no MIN/MAX-over-text queries, so `fragile` = fcfs):

| Policy | Mean score | Tokens | 100% drift: 10% / 25% / 50% / 75% / 100% budget |
|---|---|---|---|
| fcfs | 0.2356 | 44.1M | 0.141 / 0.179 / 0.191 / 0.215 / 0.256 |
| oracle | 0.2356 | 44.1M | identical (art's one no-value patch at 100% drift is already skipped by the budgeted streams) |
| cap | 0.2263 | 36.3M | 0.101 / 0.169 / 0.218 / 0.215 / 0.256 |
| pace | **0.2405** | **37.3M** | 0.149 / 0.196 / 0.227 / 0.255 / 0.255 |

**All five corpora** (mean score over 25 streams; tokens):

| Policy | cspaper | player | art | legal | med |
|---|---|---|---|---|---|
| fcfs | 0.1453 (7.9M) | **0.3363** (43.0M) | 0.2356 (44.1M) | 0.1106 (219M) | 0.0797 (154M) |
| fragile | 0.1453 (no-op) | 0.3363 (no-op) | 0.2356 (no-op) | **0.1136** (158M) | **0.0828** (130M) |
| oracle | 0.1453 (7.2M) | 0.3363 | 0.2356 | 0.1129 (158M) | 0.0797 (130M) |
| cap | 0.1398 (6.1M) | 0.3076 (29.8M) | 0.2263 (36.3M) | 0.0992 (167M) | 0.0812 (147M) |
| pace | **0.1466** (6.0M) | 0.3260 (41.5M) | **0.2405** (37.3M) | 0.1030 (177M) | 0.0821 (145M) |

- **`fragile` never hurts** (no-op where there is nothing to skip, best on legal and med) and matches or beats the
  hindsight oracle everywhere. It is the one policy to adopt.
- **Pacing** wins on cspaper and art (+0.001, +0.005, with 15–23% fewer tokens) and loses on player and legal (−0.010,
  −0.008): it helps where early full-corpus patches over-read, and hurts where early patches are the useful ones.
- **The per-patch cap** is never best and hurts small budgets on every corpus.
- Whether skipping helps tracks the share of wasted patch tokens (E2.2): 0% on player (fcfs best), 16% on art, ~33–39%
  on cspaper, legal and med.

**E7 on med (0% drift, fresh build with "Never null" dropped for text fields; `E7-stream-nullable-med/`):** 0.0952 →
**0.0518 (−0.043)**, 8 queries up / 18 down. Over all three med tables, false fills fall from 842 to 710 of 1,262
gold-empty cells, but misses rise from 276 to 446 of 2,204 gold values. Med is the corpus where gold is most often
empty, yet relaxing hurts it most: its bottleneck is too few rows (see med above), and each additional empty value
drops rows from groups and joins. This is the strongest evidence that the never-null instruction, contradictory as it
is, is the better default on this model.

**E7 on art** (`E7-stream-nullable-art/`): 0% drift 0.2698 → 0.2893 (+0.020; 18 up / 13 down); 100% drift 0.2557 →
0.2220 (−0.034; 15 / 18).

**E7 across corpora (dropping "Never null" for text fields; paired difference vs recorded):**

| Corpus | 0% drift | 100% drift |
|---|---|---|
| player | −0.006 | −0.003 |
| cspaper | −0.013 | +0.020 |
| art | +0.020 | −0.034 |
| med | **−0.043** | (not run) |

Signs differ by corpus and even by drift level within a corpus; the mean is negative. Together with E7b (−0.053) and
E7c (−0.003 / −0.015), this settles RQ8's null-handling question: on this model the benchmark's never-null
instruction, though contradicted by gold for 69 of 132 columns, is the better default.

## E5.1: why the planner loses to the shared read (player)

For each budget of the planner sweep (4-bit server) and each of the 20 held-out queries, the score gap to the shared
read is attributed to the first cause that applies, measured on the database the query was scored on: a join key the
query needs is empty (under 5% of rows filled); another needed column is empty; or every needed column was read
(`E5.1-planner/summary.json`, `per_query.csv`). Summed gap over the 20 queries:

| Budget | Planner score | Join key empty | Other column empty | All read, values differ |
|---|---|---|---|---|
| 5% | 0.077 | 6.35 (10 queries) | 3.30 (9) | 0.00 (1) |
| 10% | 0.134 | 6.35 (10) | 1.88 (7) | 0.30 (3) |
| 25% | 0.232 | 6.01 (9) | 0.39 (5) | 0.15 (6) |
| 50% | 0.285 | 4.24 (7) | 0.14 (3) | 1.10 (10) |
| 75% | 0.340 | 0.31 (1) | 1.42 (4) | 2.66 (15) |
| 100% | 0.340 | 0.31 (1) | 1.20 (4) | 2.88 (15) |

- **At small budgets the planner loses on join keys**: half the held-out queries have a join key the planner left
  unread, and each such query loses about 0.6 (the whole query zeroes). The planner scores columns one by one and
  does not see that a join key is worth the whole query.
- **At large budgets it reads everything and still trails** (15 queries, 2.7–2.9 summed gap): the difference is in
  the values, i.e. in how the columns are read.

**Confound found while doing this:** the planner's reads use `field_specs` (each column's name and SQL type only),
while the shared read it was compared with (0.560) used the protocol variant (the benchmark's column descriptions,
allowed values and nullability). Part of the "planner vs shared read" gap is therefore information, not planning.
**E5.0 (running)** re-runs the shared read with the planner's field specs on the same server, to separate the two.

## E5.0: the shared read without descriptions — the planner comparison corrected

Player shared read on the 4-bit server with the planner's field specs (each column's name and SQL type only), against
the protocol read with the benchmark's descriptions (`results/quwarts_router_v3/player_ollama_plain/shared_read/`):

| Player, held-out 20 | Score | Structure F2 | Cell F1 | Tokens |
|---|---|---|---|---|
| Shared read, protocol (descriptions, allowed values, nullability) | 0.560 | 0.868 | 0.615 | 1.30M |
| **Shared read, plain (names and types only)** | **0.234** | 0.419 | 0.288 | 1.25M |
| Planner, 25% budget (names and types only) | 0.232 | | | 2.63M |
| Planner, 75–100% budget (names and types only) | **0.340** | | | 5.5–6.7M |

**Correction of the earlier RQ5 reading.** With the same column information, the planner does not lose to the shared
read: it matches it at a 25% budget and beats it by +0.11 at 75% and above (all 100 queries: plain shared read
0.212). The "planner 0.340 vs shared read 0.560" gap reported since 2026-10-01 was entirely the difference in input
information. **The benchmark's column descriptions are worth +0.33 on the held-out queries (structure F2 0.419 →
0.868)**, the largest single effect measured, larger than model scale (7B → 32B: +0.13). The planner should be re-run
with the protocol field specs to compare like with like at the higher level (E5.2).

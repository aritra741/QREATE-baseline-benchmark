# Experiment findings (running log)

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

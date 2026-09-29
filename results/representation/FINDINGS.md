# Representation layer and tolerant evaluator (branch `representation`, 2026-09-29)

Code:
- `core/represent/`: `grammar`, `normalize`, `programs`, `llm`, `resolve`, `router` and the `build` entry point;
- `eval/represent_eval.py`, `eval/tolerant_score.py`, `eval/tolerant_rescore.py`.

Results live in this folder:
- `REPORT.md` (every view), `COLUMNS.md` (tiers per column), `BUDGET.md` (the router's frontier), `DRIFT.md`;
- `tolerant_rescore/REPORT.md`.

No document was re-read. Views are built from the frozen protocol databases. The model tier used 0.49M tokens across every experiment here.

## What was missing
- The router's shared-read path stored raw extracted strings: canonicalization was off and there was no entity resolution.
- The old compiler's rules for IN-list domains, a shared canonical ID and type unification (RULES.md 1–3) never reached the router.
- The benchmark scorer counts a different spelling of the same value as wrong. Examples: `19th–20th` vs `19th-20th`, `a || b` vs `b||a`, the string `'null'` vs a missing value.

## Tolerant evaluator (reported next to the benchmark metric)
- **What it does:** one symmetric, corpus-independent normalization of every stored cell, in both gold and predicted databases, and of the query's string literals. The unchanged metric then runs.
  - The rules cover case, dashes and quotes, lists as sets, missing-value sentinels, bare numbers, written dates, ordinal centuries and booleans.
  - It normalizes the data, not the result rows, so two spellings of one value form one group before aggregation. An earlier result-row version double-counted groups and was dropped.
- **Check:** the benchmark path reproduces every stored QuWARTS and DocETL score.
- **Held-out macro (six corpora):**

  | Metric | QuWARTS | DocETL |
  |---|---:|---:|
  | Benchmark | 0.288 | 0.198 |
  | Tolerant | 0.305 | 0.201 |

- **Per-corpus changes in the protocol runs:**
  - Med QuWARTS moves 0.273 → 0.352, now above DocETL (0.295).
  - DocETL Finan drops 0.210 → 0.181: gold `'N/A'` strings compared as numbers had been counted as dividends.

## The layer
- **Grammar.** The workload states representation in its literals and operators:
  - `=`, `!=`, `IN` literals give exact spellings;
  - `LIKE` cores give substrings;
  - `LOWER` / `TRIM` mark case and space tolerance;
  - numeric operators give types;
  - `a.x = b.y` gives shared domains;
  - raw `GROUP BY` gives one spelling per value.

  Literal shapes (Potter's Wheel token signatures) and case/separator conventions describe values the workload has not named yet: constants change, their form does not.
- **T0, rules (free):**
  - cleaning and vocabulary spelling;
  - conventions;
  - whole-word containment of a vocabulary value (`Justice Flick` → `Flick`, `calm and neutral` → `Neutral`);
  - one value or a set. A declared multi-valued column that the workload only compares by `=` / `IN` is read as single-valued: the operators state the cardinality the workload expects.
- **T1, programs (free):**
  - FlashFill-style span-and-case programs, one per pattern class.
  - Classes keep a column's frequent tokens literal (`justice Aa` vs `Aa j`).
  - A program is learned from T0's own confident rewrites and needs two agreeing examples.
- **T2, model (budgeted):**
  - residual distinct values, batched and memoized;
  - the column's own rewrites are shown as demonstrations;
  - an answer is kept only if it is a vocabulary value or grounded in the source (every word occurs there).
  - Its cost is linear in distinct residual values, not rows or documents.
  - *Cascade* mode: the model labels two representatives per pattern class and programs generalize.
- **Entity resolution:**
  - join columns take the entity side's spelling (fold, containment, then optional model multiple-choice);
  - raw grouping columns merge folded duplicates.
- **Views:** the raw database is kept. The view is a materialized copy with `__rep_map` (raw cell, view cell, tier). Rebuilding it from the maps costs no model call.

## Results: frozen protocol runs, train literals only
Benchmark metric, all queries; the CI is paired against raw.

| Corpus | Raw | Free tiers (T0+T1+ER) | + model (all) | Model tokens | Held-out, free tiers (DocETL) |
|---|---:|---:|---:|---:|---:|
| Art | 0.307 | **0.377** (+0.070 [0.04, 0.10]) | 0.383 | 35k | 0.269 (0.232) |
| Legal | 0.295 | **0.341** (+0.046 [0.018, 0.079]) | 0.343 | 2.6k | 0.222 (0.135) |
| Med | 0.187 | 0.187 (tolerant 0.242 → 0.269) | 0.187 | 0 | 0.273 (0.298) |
| Finan, CSPaper, Player | – | unchanged | unchanged | ≤ 1k | – |

Held-out macro with the free tiers:

| Metric | QuWARTS (free tiers) | Earlier QuWARTS | DocETL |
|---|---:|---:|---:|
| Benchmark | **0.300** | 0.288 | 0.198 |
| Tolerant | **0.315** | 0.305 | 0.201 |

Art moves from below DocETL (0.219 vs 0.232) to above it (0.269).

## Observations
1. **Almost all of the gain is free.**
   - On Art, T0 alone gives +0.070. About half of it is the cardinality rule: without it, +0.033. It raises `birth_country` cells from 0.40 to 0.83.
   - The router's budget frontier (`BUDGET.md`) is flat: model tokens add ≤ +0.006 (Art) and +0.002 (Legal) over zero tokens.
   - On Med, CSPaper and Player the residual after the free tiers is empty or tiny, and the router spends nothing.
2. **Programs beat the model when the variation is syntactic.** Cell accuracy against gold (`COLUMNS.md`):

   | Legal `judge_name` view | Cell accuracy | Model tokens |
   |---|---:|---:|
   | Raw | 0.109 | 0 |
   | T0 | 0.319 | 0 |
   | Model on the residual, no demonstrations | 0.491 | ~5k |
   | Model on the residual, with demonstrations | 0.651 | ~5k |
   | Programs | **0.830** | 0 |
   | Programs + model | 0.867 | 2.6k |
   | Cascade | 0.868 | 0.7k |

   The 7B model is an inconsistent normalizer: it drops or keeps titles differently across batches. A program learned from the workload's own literals is consistent.
3. **Program coverage is the gold-free signal for choosing a tier.** Coverage is the share of residual values in pattern classes with two agreeing examples.
   - `judge_name`: coverage 0.64 and 5.9 values per class. Programs win, and the cascade matches the model at 1/7 of the tokens.
   - Art `style`: coverage 0 (the variation is semantic). Programs add nothing. Only the model helps (+0.019 cells, 19k tokens), and the cascade loses that gain because model labels do not generalize by programs.
   - So the router should run programs, or the cascade, on high-coverage columns. It should spend on the model per distinct value only on zero-coverage columns with high workload use.
4. **Most remaining errors are extraction, not representation.**
   - Art `tone`, `color` and `composition` stay at or below 0.09 in every view: the values are annotated from the painting.
   - CSPaper `application_domain` is tagged with two domains where gold has one.
5. **Entity resolution matters little here.**
   - Player's joins already match (74/111 reference cells; the rest are non-NBA clubs, correctly left unjoined).
   - Med's join columns are lists in gold too, so exact-string joins fail on both sides. Resolution lifts Med's tolerant score 0.242 → 0.269 and leaves the benchmark score unchanged.
6. **Under drift, a frozen representation fades.**
   - Art, full-schema read, benchmark metric, frozen free tiers over raw: +0.054 [0.027, 0.086] at 25% drift, +0.035 at 50%, +0.012 at 75%, +0.009 at 100%. Drifted queries use columns the train literals never described.
   - **Online** views take each arriving query's literals into the workload, with no reads and at most a few thousand model tokens. At 100% drift online beats raw by +0.023 and frozen by +0.015 (CI crosses 0).
7. **Online can hurt when the declared cardinality is wrong.**
   - CSPaper at 100% drift: −0.023 [−0.046, −0.004].
   - The cause: `generator_model` is declared single-valued but stored as lists in gold. When a new `= 'GPT-4'` literal arrives, T0's "one value" rule collapses an extracted list to the matching model, which creates matches gold's exact-string semantics does not have.
   - The benchmark's declarations disagree with its own gold in both directions: Art `birth_country` is declared multi and is single in gold, where the rule gains +0.037; CSPaper `generator_model` is declared single and is a list in gold, where the rule costs −0.023 online.
   - I did not tune a data-profile guard on these results, to avoid fitting rules to the evaluation. This is the open problem the layer leaves.

## From DocETL and MOAR
- **What is used:**
  - DocETL's *resolve before reduce* (entity resolution before grouping);
  - validation of model output, in gleaning's spirit (here, grounding against the source value);
  - MOAR's cost/accuracy frontier across budgets (`BUDGET.md`);
  - MOAR's replacement of LLM calls with synthesized code (T1 programs).
- **What neither paper addresses:** workloads and drift.
- **Not built:** re-extraction of residual cells (gleaning on documents) as a fourth tier.

## Caveats and a fixed artifact
- Cell accuracy is gold-based audit. Finan has no document↔gold map, so it has no cell audit.
- Drift constants were drawn from gold values (as the drift sets were built), which helps online views.
- **The chunked-scoring artifact:** scoring drift queries in chunks changed the scorer's signature-predicate eligibility, so a rewrite named a signature column the database lacked and the query scored 0. The fix computes predicates over the whole level's query set. All affected Art drift results were re-scored, and frozen views now score identically on the queries the levels share.

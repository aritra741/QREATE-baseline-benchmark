# DocETL with its optimizers vs our system (8 queries where our edge was largest)

Queries: players QJ14, QJ15, QJ17, QJ19, QJ20 (joins over long team/city documents and team/owner); med Q8, Q12, QJ4
(counts with a constant). Per-query numbers: `comparison.json` (built by `systems/DocETL/exp_optimizer_comparison.py`).

## Haiku executing (agents: Haiku)

| | mean score at 20% | executing-model tokens (8 queries) |
|---|---|---|
| DocETL, plain | 0.394 | 13.1M |
| DocETL + MOAR (labeled sample, upper bound) | 0.398 | 33.6M (understated: search tokens of the 5 salvaged runs were not recorded) |
| DocETL + v1 (no labels) | 0.476 | 281.1M |
| our reader alone (no build, planner or representation layer) | 0.431 | 5.9M |
| **our full system** (initial build, planner, representation layer, reuse; whole realistic stream run from scratch on Haiku) | **0.626** | 23.1M for the whole stream of 48 queries (0.48M per query; DocETL ~1.6M per query) |

- MOAR improved one query (QJ14 0.941 -> 1.000), lowered one (QJ15 0.881 -> 0.851), and left the rest unchanged. Its search looped
  without terminating on 5 of 8 queries (millions of SELECTION steps, no new evaluations); for those, per table, the best
  candidate it had evaluated on the labeled sample was used ("salvaged"; noted per table in per_query.json).
- v1 helped on med Q8 (0 -> 1.000: a gleaning pass that checks the manufacturer is "supported verbatim" removed copied
  constants; but 42 of 98 documents were dropped, which also removes chances of false matches) and QJ15 (0.881 -> 0.911);
  hurt QJ20 (0.667 -> 0.286). It used 10-35x plain DocETL's tokens. Two med runs crashed once on Anthropic's content filter
  and one on DocETL's "Rate limit hit too many times"; each succeeded on one retry.
- Join spelling, measured (rows with a join partner; correct / DocETL / our reader): team-city 28/27/26, 28/29/26, 28/27/28;
  team-owner 16/12/7, 16/10/5. QJ17's 0 vs 1.000 is one row: DocETL wrote "New York" for the Knicks, the city table has
  "New York City".

## Qwen executing

DocETL's optimizers did not produce usable plans with a local 7B executor in this setup. Five harness fixes were needed to get
them running (type check; v1 needs `optimize: true`; v1 crash when every sampled item fails; v1 crash on plain-text sample
rows; agent-written steps naming OpenAI models and OpenAI embeddings mapped to local models). After that, v1 needed more than
6 hours per table and ended with "No valid plans were generated" on one query; MOAR's candidate plans produced empty outputs
(steps written for a strong model, run on a 7B model with a small default context). Outputs of those attempts are kept under
`results/docetl_optimized/invalid-*` and `incomplete-v1-qwen-7h`, not used in any comparison.

## Our full system on Haiku vs on Qwen (`full_system_haiku.json`)

Whole realistic stream, mean at 20%: players 0.593 on Haiku vs 0.564 on Qwen (28 queries); med 0.185 vs 0.259 (20 queries).
On the 8 queries: identical on QJ14, QJ17, QJ19, QJ20 and med Q12; QJ15 0.705 vs 0.749; med Q8 and QJ4 0 on Haiku vs 1.0 on
Qwen. Those two are exact single counts (one document off scores 0); on Qwen, Q8 was exact in only 1 of 3 replicates, so
their 1.0 on Qwen is partly chance.

## Caveat on "ours"

"ours (Qwen)" in comparison.json is the full system (initial build, planner, representation layer, reuse across the
stream): mean 0.844 on these 8 queries. "ours (Haiku)" in comparison.json is only the reader on each query's fields; the
full system on Haiku is the separate row above (0.626) and `full_system_haiku.json`.

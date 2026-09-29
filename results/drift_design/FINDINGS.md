# Drift experiments: findings (branch `experiment/drift-design`, 2026-09-29)

QuWARTS only, on the design in `README.md`.
- Code: `eval/drift_run.py`.
- Tables: `RESULTS.md` (generated).
- Per corpus: `reads.jsonl` (the build read), `audit_reads.jsonl`, `run/` (simulations, memoized scores, the audit).

Queries that read a table's `id` were removed (Med 52, Legal 5, Player 2): the key maps a gold row to its document and is not in the documents. The first run, which still had them, is in `_superseded_id_queries/`.

**Med correction (2026-09-29, after the first version of this file).** Med's databases were built on an old incumbent database from an earlier repair experiment, with rows for only 70/70/75 of the 100/98/99 documents. Its empty join-key `__canonical` columns also made every rewritten join return nothing. The registry no longer names an incumbent for Med, so Med is now built from its documents like Art, CSPaper and Player. No model calls were needed. Med's drift results were replayed and the numbers above updated; the old run is in `_superseded_med_incumbent/`. The Med rebuild-quality rows in `REBUILD_QUALITY.md` predate the fix.

## In one paragraph
When queries start asking about columns the build never extracted, a build that does not adapt breaks, and the controller recovers it: at 100% attribute drift, the mean over six corpora is 0.028 for static and 0.249 for adaptive. Reading a document costs about the same whether the prompt asks for 10 fields or 25. So extracting every schema column up front costs 1.06–1.57× the minimal build, while going back to the documents for a missing column costs almost a second read. Under attribute drift:
- robust build + controller: **1.02×** the clairvoyant build;
- lean build + controller: **1.64×**.

QuWARTS should read the whole schema at build time and keep the controller as the fallback. Updating the value representation as each query arrives helps where queries use columns or spellings the build never described (Legal +0.071, Art +0.034), and is neutral elsewhere.

## What ran
- **Build reads.** One read per corpus, informed by W0 alone and covering every schema column of every table the pool reads. Cost: 31.7M tokens.

  | Corpus | Build-read tokens |
  |---|---:|
  | CSPaper | 0.52M |
  | Player | 2.15M |
  | Art | 3.12M |
  | Med | 3.98M |
  | Legal | 4.90M |
  | Finan | 17.07M |

- **Replay.** Every policy was replayed on 324 streams (6 corpora × 3 seeds × 18) with both metrics and no further model calls.
- **Audit.** The replay's approximation was measured on a document sample.
- **Total spend:** ≈ 45M tokens (≈ $4.5). This includes the superseded Med and Legal reads (8.9M) and the audits (4.6M).

## Findings (benchmark metric; 95% paired bootstrap CIs)

**1. Attribute drift breaks a static build; the controller recovers it.**

| Corpus | Static | Adaptive | Adaptive − static [95% CI] |
|---|---:|---:|---|
| CSPaper | 0.028 | 0.184 | +0.156 [+0.100, +0.217] |
| Player | 0.035 | 0.409 | +0.374 [+0.310, +0.437] |
| Art | 0.053 | 0.233 | +0.180 [+0.128, +0.238] |
| Med | 0.036 | 0.238 | +0.202 [+0.135, +0.273] |
| Legal | 0.011 | 0.224 | +0.214 [+0.169, +0.261] |
| Finan | 0.006 | 0.205 | +0.198 [+0.144, +0.255] |

- On the combined axis the mean gap is +0.111. The tolerant metric agrees (+0.169 to +0.387).
- On gradual streams, the last quarter of the attribute axis is at 0.012–0.109 for static and 0.20–0.41 for adaptive.

**2. Build robust, not lean.**
- **Cost ratio R/L.** The robust read costs this multiple of the lean read:

  | Corpus | R/L |
  |---|---:|
  | Player | 1.06 |
  | Finan | 1.07 |
  | Legal | 1.08 |
  | Art | 1.29 |
  | CSPaper | 1.31 |
  | Med | 1.57 |

  Med is the highest because W0 never reads its `institution` table.
- **Price of a miss.** The first miss re-reads its scope, about 85–95% of the build when the scope is the whole corpus.
- **Measured cost at 100% attribute drift** (× clairvoyant): lean + controller 1.64, robust + controller 1.02.
- **Where lean is cheaper.** Only when no attribute drift arrives: 6–36% on the value axis (Legal, Finan, Art, Med). On CSPaper and Player, T0 already needs columns W0 never read.
- **The build-time rule.** Prefetch the schema whenever the premium R − L is below the cost of one full-scope patch. This is ski rental at build time; it holds on all six corpora.
- **Provenance of the rule.** It comes out of this experiment. The pre-registered QuWARTS policy was lean + controller; both are reported.

**3. What a patch reads matters more than when to rebuild.**
- Patch-only, OnlinePT and the drift policy cost the same everywhere. After one full-corpus robust patch, every column is complete.
- Eager rebuilding costs 6–70% more.
- Patches that read only the query's missing columns cost 1.8–3.6× more (Finan 107.6M vs 32.1M): each new column is another full re-read.

**4. Online representation.** Online minus frozen at 100% drift:

| Corpus | Axis | Online − frozen [95% CI] |
|---|---|---|
| Legal | attribute | +0.071 [+0.039, +0.109] |
| Legal | combined | +0.045 [+0.017, +0.077] |
| Art | value | +0.034 [+0.020, +0.048] |
| Art | attribute | +0.022 [+0.011, +0.034] |
| Finan | attribute | −0.007 [−0.011, −0.003] |
| CSPaper, Player, Med | every axis | within ±0.003 |

- Look-ahead representation (W0 plus the whole stream) is no better than online.
- Value-drift accuracy mostly follows the variants' own difficulty, the same for every policy (Player 0.41 → 0.58, Finan 0.17 → 0.41, Legal 0.22 → 0.18).

**5. Replay audit.** Small prompts (a lean build's W0 fields, a patch's other fields) were compared with the robust prompt, as cell accuracy against gold, small minus robust:

| Corpus | Documents | W0 fields | Patch fields |
|---|---:|---|---|
| CSPaper | 20 | −0.034 | −0.040 [−0.081, −0.008] |
| Art | 20 | −0.008 | −0.054 [−0.092, −0.016] |
| Player | 40 | −0.018 | 0.000 |
| Med | 30 | −0.009 | +0.011 |
| Legal | 20 | +0.011 | +0.082 [+0.020, +0.143] |

- Finan has no gold map.
- The replay slightly flatters patched columns on CSPaper and Art and understates them on Legal. The robust build's values are exact.

## Verification
- **Memoized scores:**
  - queries rescored on every fixed database sharing a digest: 0 mismatches;
  - online positions rescored after rebuilding their views, on four streams including new Legal and Med ones: 0 mismatches, identical digests and actions.
- **Replay equivalence:** checked on 4 partial-scope patches, with cells outside the scope set to NULL. The scores are unchanged.
- **Performance memos:** they give identical outputs.
- **No `id` query remains:** none in any stream, and no stream query needs a column outside the robust read.

## Caveats
- **Replay:** patches and rebuilds reuse the W0 read's values. A real patch's prompt would carry a usage phrase from the queries that asked for the column.
- **CIs:** they pool the 84 positions over 3 seeds. Positions within a stream are not independent draws.
- **Costs:** these are the controller's token estimates. The build reads came in 1.8% under them.
- **Scope:** only scorable (aggregation) queries are included.

## Open
- A corpus where R/L is large, to exercise the lean branch.
- Real (non-replayed) patches on a sample.
- A test–retest read to separate sampling noise from prompt effects.

## Value-drift constants re-sampled (selectivity-matched)
Value-drift variants first drew their new constants by gold frequency, which favoured common values and made value drift easier. They are now drawn uniformly among constants that occur in about as many gold cells as the replaced one (within a factor of two). W0, T0 and the attribute pools are unchanged, so the build reads stand. Value and combined streams were regenerated and replayed; the old ones are in `_superseded_value_sampling/`. On the full read, value variants now score close to their test queries on CSPaper, Player, Art, Med and Legal. Finan's variants still score 0.404 against 0.169 for its test queries. Their source queries also score high (0.259), so the remaining gap comes from which queries can be re-instantiated (those with string constants), not from the constants. `RESULTS.md` has the regenerated numbers. The rebuild-quality test (`REBUILD_QUALITY.md`) used the old seed-0 value stream.

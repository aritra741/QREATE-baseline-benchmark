# Drift experiments: findings (branch `experiment/drift-design`, 2026-09-29)

QuWARTS only, on the design in `README.md`.
- Code: `eval/drift_run.py`.
- Tables: `RESULTS.md` (generated).
- Per corpus: `reads.jsonl` (the build read), `audit_reads.jsonl`, and `run/` (stream simulations, memoized scores, the audit).

## What ran
- **Build reads.** One W0-informed robust read per corpus.
  - Usage phrases come from W0's columns only. Every schema column of every table the pool reads is included (Player's `owner` too). Long documents use chained reads.
  - Cost: 31.8M tokens, 1.8% under the cost model's estimate.

  | Corpus | Build-read tokens |
  |---|---:|
  | CSPaper | 0.52M |
  | Player | 2.15M |
  | Art | 3.12M |
  | Med | 4.00M |
  | Legal | 4.91M |
  | Finan | 17.07M |

- **Replay.** Every policy was replayed on every stream:
  - 6 corpora × 3 seeds × 18 streams = 324 streams, 10,584 query positions;
  - both metrics; no further model calls.
- **Audit.** The replay's approximation was measured on a document sample (3.7M tokens).
- **Total:** ≈ 35.4M tokens, ≈ $3.5.

## Policies
- **Static:** lean build (W0's attributes), no adaptation, representation frozen at W0's literals.
- **Lean + controller:** the pre-registered QuWARTS policy. A lean build, the drift controller (answer / patch / rebuild), and online representation: each arriving query's literals join the representation workload before it is answered.
- **Robust + controller:** a build of every schema column, the same controller for anything outside it, and online representation.

Under replay, both controller policies answer from the same values (a patch's scope pushdown keeps answers exact; module docstring), so they differ only in cost. The ablations (frozen or look-ahead representation, no representation, rebuild policies, non-robust patches) are in `RESULTS.md`.

## Findings
**1. Attribute drift breaks a static build; the controller recovers it.**
- Benchmark metric at 100% attribute drift:

  | Corpus | Static | Adaptive | Adaptive − static [95% CI] |
  |---|---:|---:|---|
  | CSPaper | 0.028 | 0.184 | +0.156 [+0.100, +0.217] |
  | Player | 0.023 | 0.410 | +0.387 [+0.316, +0.459] |
  | Art | 0.053 | 0.233 | +0.180 [+0.128, +0.238] |
  | Med | 0.074 | 0.200 | +0.126 [+0.070, +0.188] |
  | Legal | 0.009 | 0.225 | +0.216 [+0.158, +0.276] |
  | Finan | 0.006 | 0.205 | +0.198 [+0.144, +0.255] |
  | **Mean** | 0.032 | 0.243 | +0.210 |

- On the combined axis the mean gap is +0.112. The tolerant metric agrees (+0.157 to +0.395 on the attribute axis).
- Gradual streams: in the last quarter, static is at 0.002–0.105 and adaptive at 0.14–0.43. The controller patches when the drifted queries arrive.

**2. The lean build is the wrong default: build robust, adapt beyond it.**
- **Measured cost.** At 100% attribute drift, relative to a clairvoyant build (the design of W0 plus the whole stream):
  - lean + controller costs **1.77×** (CSPaper 0.74M vs 0.48M; Finan 32.1M vs 17.6M);
  - robust + controller costs **1.11×**.
- **Why.** A read costs about the document's length whatever the number of fields:
  - The robust build costs only 1.06–1.31× the lean build (R/L: Legal 1.06, Player 1.06, Finan 1.07, Med 1.11, Art 1.29, CSPaper 1.31).
  - The first miss re-reads its scope, 85–96% of the build when the scope is the corpus.
- **The build-time rule.** In ski-rental terms, buying at build time costs the premium R − L, and one full-scope miss costs about R. Prefetching the schema is therefore the minimax choice whenever the premium is below one miss's rent. That holds on all six corpora.
- **The controller still matters beyond the build.** Two identifier columns are outside the benchmark schema: Legal `ID` (5 queries) and Player `id` (2 queries). Their patches re-read every document, which is why Legal's robust + controller is at 1.54× clairvoyant.
- **Where lean is cheaper.** Only with no attribute drift: 6–22% on the value axis for Legal, Med, Finan and Art. On CSPaper and Player, T0 already needs columns W0 never read, so lean patches even at 0% drift.
- **Provenance of the rule.** It comes out of this experiment. The pre-registered QuWARTS policy was lean + controller; both are reported.

**3. Robust patches matter far more than when to rebuild.**
- Patch-only and the drift policy (ski rental with the drift prediction) cost the same everywhere. After one robust patch of the whole corpus, every column is complete; the rent cap then rules rebuilds out, correctly.
- OnlinePT rebuilds once on Legal (+0.7M). Eager rebuilding costs 5–70% more.
- Non-robust patches (only the query's missing columns) cost 1.7–3.6× more (Finan 107.6M vs 32.1M): each new column is another full re-read.

**4. Online representation helps where the drift reaches columns or values the build never described.** Online minus frozen at 100% drift:

| Corpus | Axis | Online − frozen [95% CI] |
|---|---|---|
| Art | value | +0.034 [+0.020, +0.048] |
| Art | attribute | +0.022 [+0.011, +0.034] |
| Legal | attribute | +0.049 [+0.016, +0.090] |
| Finan | attribute | −0.007 [−0.011, −0.003] |
| CSPaper, Player, Med | every axis | within ±0.003 |

- On Legal, drifted queries group or filter by columns W0 never used (`judge_name`, `first_judge`).
- On Finan the small loss is a real cost of online representation.
- Look-ahead representation (W0 plus the whole stream) is no better than online: learning each query's literals as it arrives loses nothing.
- Value-drift accuracy mostly tracks the variants' own difficulty, the same for every policy: it rises with the level on Player (0.41 → 0.58) and Finan (0.17 → 0.41) and falls on Legal (0.37 → 0.11). Values extracted wrongly are not a representation problem (representation finding 4).

**5. Replay audit.** On a document sample, the small prompts (a lean build's W0 fields, a patch's other fields) were compared with the robust prompt. Cell accuracy against gold, small minus robust:

| Corpus | W0 fields | Patch fields |
|---|---|---|
| CSPaper | −0.034 | −0.040 [−0.081, −0.008] |
| Art | −0.008 | −0.054 [−0.092, −0.016] |
| Player | −0.018 | 0.000 |
| Med | −0.061 | −0.039 |
| Legal | +0.047 | +0.093 [+0.033, +0.152] |

- So on four corpora the replay overstates the lean policies by up to about 0.05 per cell, and on Legal it understates them. The robust build's values are exact.
- Value agreement between the prompts is 0.45–0.89. This includes sampling variation at temperature 0.1, which a test–retest read would separate (not run).

## Verification
- **Memoized scores:** 18 queries rescored on every fixed database sharing a digest, and 24 online positions rescored after rebuilding their views from scratch. 0 mismatches; digests identical after the rebuild.
- **Replay equivalence:** on 4 first patches with partial scope (Art 787/1000, CSPaper 193/200, Legal 309/570, Finan 2/100 documents), cells outside the scope were set to NULL. The scores are unchanged.
- **Speed-up:** the memo of `sql_table_attributes` gives the same output on 20 random contexts, and two re-simulated streams are identical to the stored ones.
- **Tolerant scoring:** normalizing only the referenced columns gives the same 16 scores.

## Caveats
- **Replay:** patches and rebuilds reuse the W0 read's values. A real patch's prompt would carry a usage phrase from the queries that asked for the column.
- **Identifier queries:** `ID`/`id` (7 queries) have no values in any policy.
- **CIs:** paired bootstraps over the 84 positions pooled across 3 seeds. Positions within a stream are not independent draws.
- **Costs:** these are the controller's token estimates for every read it decides on.
- **Scope:** only scorable (aggregation) queries are included.

## For QuWARTS
- **Build:** the schema of every table in the workload (robust), when the premium over the lean read is below the cost of one full-scope patch. This is a gold-free check from the cost model; otherwise build lean.
- **Serve:** the free representation tiers, online per arriving query.
- **Adapt:** the drift controller with robust patches for anything outside the build.
- **Open:**
  - a corpus where R/L is large, to exercise the lean branch;
  - real (non-replayed) patches on a sample;
  - a test–retest read.

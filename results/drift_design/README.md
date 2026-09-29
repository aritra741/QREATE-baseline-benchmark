# Drift experiment design (branch `experiment/drift-design`, 2026-09-29)

This design replaces `results/drift_eval`. That older version mutated the 80/20 train queries, and its train split already read almost every attribute. It never contained Finan; SEC is a different dataset and stays out.

Code:
- `eval/drift_pool.py` builds the query pools.
- `eval/drift_design.py` builds the workloads, the streams and their characterization.

Outputs:
- `POOL.md` and `DESIGN.md` (both generated);
- per corpus: `pool.json`, `build.json`, `design_seed{0,1,2}.json` (streams, characterization, and the SQL of every query) and `design_summary.json`.

## 1. Query pools: every query we have
- **Sources:**
  - every statement in the benchmark's query files (`Query/<Dataset>/**`: Select, Filter, Agg, Mixed, Join, Expanded, Variations, Subsample, Splits and the rest);
  - the case80 analytical workloads.
- **Normalization:** statements are normalized and de-duplicated.
- **Row keys are left out:** a query that reads a table's `id` is dropped (Med 52, Legal 5, Player 2 queries). The key only maps a gold row to its document; it is not in the documents.
- **What a query needs to be kept:** it must be *scorable* (an aggregation query, the only kind the metric scores) and *valid* (it runs on gold and returns at least one non-NULL row). Non-aggregation Select/Filter queries are left out; they have only the benchmark's official accuracy, not our metric.

| Corpus | Scorable, valid queries | Attributes | Largest sources |
|---|---:|---:|---|
| Med | 175 | 34 | Splits 105, case80 47, Mixed 13, Agg 10 |
| Finan | 165 | 25 | Splits 64, case80 80, Agg 10, Variations 6, Mixed 5 |
| Legal | 151 | 17 | Splits 55, case80 80, Agg 10, Mixed 6 |
| Art | 156 | 21 | Splits 60, case80 80, Agg 10, Mixed 6 |
| CSPaper | 141 | 15 | Splits 47, case80 80, Agg 10, Mixed 4 |
| Player | 338 | 28 | Splits 131, case80 98, Expanded 59, Mixed 27, Variations 11, Agg 10 |

## 2. Build workload (the new "train")
- **Attribute focus:**
  - Attributes are ordered by the Fiedler vector of their co-occurrence graph: an edge's weight is the number of pool queries that read both attributes. This is spectral bisection, which keeps attributes that are queried together on the same side.
  - The order is cut where the queries reading only the first side and the rest are most balanced. That first side is the build workload's focus A0.
  - The procedure is deterministic, is fixed before any QuWARTS run, and looks only at SQL.
- **Split:**
  - Queries within A0 are split once, 60/40, into the build workload W0 and the in-distribution test queries T0.
  - The rest, which read at least one attribute outside A0, form the attribute-drift pool.
- **Why W0 is fixed across seeds:** the build's extraction must be a real read whose prompts come from W0 alone (see §6), so there is one W0 per corpus. The seeds vary the streams.

| Corpus | Focus (share of attributes) | Cut share | W0 | T0 | Attribute-drift pool | Value-drift pool |
|---|---:|---:|---:|---:|---:|---:|
| Med | 17 of 34 (0.50) | 0.23 | 53 | 36 | 86 | 117 |
| Finan | 14 of 25 (0.56) | 0.38 | 49 | 33 | 83 | 116 |
| Legal | 10 of 17 (0.59) | 0.35 | 46 | 30 | 75 | 53 |
| Art | 16 of 21 (0.76) | 0.39 | 46 | 31 | 79 | 59 |
| CSPaper | 11 of 15 (0.73) | 0.39 | 43 | 29 | 69 | 80 |
| Player | 13 of 28 (0.46) | 0.28 | 96 | 64 | 178 | 153 |

## 3. Drift axes
Each axis is varied separately, because each asks something different of the system.
- **Attribute drift.** Real pool queries that read attributes W0 never reads. This needs new extraction: patch, rebuild, or prefetch at build time.
- **Value drift.** W0 and T0 queries re-instantiated with constants W0 never uses:
  - equality constants (`=`, `!=`, `IN`) become gold values of the same column, drawn by frequency;
  - one `LIKE '%core%'` pattern becomes a word of the column's gold values. Only words in 2+ cells and at most 30% of them are eligible, so no `LLP` among auditors. Only patterns in WHERE, or the single pattern of a CASE branch labelled with its own core, are changed, and the label changes with them (a new value family, as an analyst adds one);
  - a variant is kept only if its gold answer is non-empty and it is not already a pool query;
  - up to 3 variants per source query, drawn round-robin across sources.

  This needs representation: the stored values must be written the way the new constants are.
- **Combined.** Half of the drifted queries come from each axis.

Gold is used only as a query generator uses it: to validate queries and draw constants. The system under test never sees it.

## 4. Streams
- **Levels:** for each axis and drift level p ∈ {0, 25, 50, 75, 100}%, a stream has N = 28 queries: a share p from the axis's drift pool and the rest from T0.
- **Nesting:** levels are nested, so a level's drifted queries contain those of the lower levels. Each stream is shuffled.
- **Gradual streams:** per axis and seed, 56 queries, with the drift probability rising linearly from 0 to 1. These are for the adaptive controller.
- **Seeds:** three, varying which queries a stream draws and their order.

## 5. Drift characterization (measured, mean of 3 seeds; excerpt at 0% and 100%, all levels in `DESIGN.md`)
- **Attribute axis:** attribute-novelty rises with p, from 0.00–0.04 at 0% to 1.00 at 100% on every corpus. The unseen feature mass rises to 0.41–0.56, and the Jensen–Shannon divergence of the (column, clause) feature distributions rises from 0.05–0.12 to 0.32–0.49. Constant novelty stays at its natural level.
- **Value axis:** constant-novelty rises to 1.00, while attribute-novelty stays at 0.00 (0.04 on CSPaper, from T0) and the JS divergence stays near its 0% level (at most +0.05). The axis is isolated.
- **Combined axis:** in between, by construction.
- **CliffGuard's delta barely moves or falls as the drift grows** (Art attribute 0.23 → 0.27, Finan 0.42 → 0.30).
  - Its distance is over distributions of distinct query representations, and in pools this diverse almost every query's representation is unique.
  - So it does not measure drift magnitude here; this is a finding in its own right.
  - The controller's novelty test, which counts unseen features, tracks the design.
- **QB5000 templates** keep column names and are nearly unique per query. The structural axis is therefore reported as an operator profile (join, group, having, case, in, like, comparisons, aggregates, ...).

## 6. Runs this design needs (done: see `FINDINGS.md` and `RESULTS.md`)
**Leakage in the existing reads.** Every read we have was prompted with "Workload use" phrases from the old 80% train split. They include literal examples ("compared with specific values, for example 'Frontcourt', ..."). That split overlaps the new drift pools. Replaying those reads would give the build knowledge of future queries, so the experiment needs a read informed by W0 alone.

**One read per corpus covers every policy.**
- It is W0-informed and robust: every schema column is read, with usage phrases for W0's columns only.
- It is the system's own build read. A lean build (W0's attributes only) and patches are projections of it.
- Two approximations follow:
  - fewer fields in a lean prompt;
  - no usage phrase for a patched column, which is conservative.

  Both can be measured on a 20-document sample.

| Corpus | Estimated tokens | At the observed ~$0.10 per M tokens |
|---|---:|---:|
| Med | 4.0M | $0.40 |
| Finan | 17.5M | $1.75 |
| Legal | 5.0M | $0.50 |
| Art | 3.2M | $0.32 |
| CSPaper | 0.5M | $0.05 |
| Player | 2.2M | $0.22 |
| **All six** | **32.3M** | **≈ $3.2** |

After those reads, every policy is replayed at no further model cost:
1. **Lean-static:** W0's attributes, no adaptation, frozen representation.
2. **Lean-adaptive (QuWARTS):** drift controller (answer / patch / rebuild) and online representation.
3. **Robust (prefetch every schema column)** with online representation.
4. **Ablations:** adaptive without online representation; detector-triggered rebuild; a representation built from W0 and the whole stream (an upper bound for representation).

Every policy is scored with both metrics per stream, with tokens for build and adaptation, and paired confidence intervals over 3 seeds.

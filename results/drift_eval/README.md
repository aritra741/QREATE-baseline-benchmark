# Workload-drift query sets (built 2026-09-28; the experiment has not been run)

Built by `systems/WDIRS/quwarts/eval/drift_sets.py` (`--all`). The corpora are Med, Legal, Art, CSPaper and Player; Finan (SEC filings) is excluded. Nothing here calls a model.

## Frozen train set (0% drift)
`<corpus>/frozen_train.json` holds the query ids, the SQL and a SHA-256 hash of the case80 input split (seed 42), the split the frozen QuWARTS build used. Rerunning the builder refuses to continue if the split ever changes.

The frozen system is the benchmark-protocol shared read on a blank base, with chained long documents where a corpus has them. Its results on this set are the 0% point:

| Corpus | Run | Queries | Score (structure F2 × cell F1@0.2) | Structure F2 | Cell F1@0.2 | Build tokens |
|---|---|---:|---:|---:|---:|---:|
| Med | `med_chain` | 79 | 0.166 | 0.430 | 0.173 | 3.72M |
| Legal | `legal_chain` | 64 | 0.319 | 0.896 | 0.338 | 4.67M |
| Art | `art` | 64 | 0.329 | 0.696 | 0.394 | 2.44M |
| CSPaper | `cspaper` | 64 | 0.240 | 0.895 | 0.275 | 0.45M |
| Player | `player_chain` | 80 | 0.494 | 0.873 | 0.556 | 2.15M |

## How drift is defined
- **Representation** (CliffGuard, Mozafari et al., SIGMOD 2015, δ_separate): a query is the set of (column, clause) pairs it uses, with clauses select, where and group by. A query has drifted when it uses a pair no train query uses.
- **Kinds of drift** follow the workload-shift taxonomy of Negi et al. (VLDB 2023): filters on new columns, new grouping columns, and new aggregated or projected columns.
- **Drifted queries.** Each is a train query changed by one operator, keeping its shape (pack, CASE bucketing, HAVING, joins):
  - *replace* one column by an unused column of the same table and kind (CliffGuard's neighbourhood: a change of the query's column set);
  - or *add* a filter on a column the train set never filters on, or a grouping column it never groups by.
- **Constants** compared with the new column are re-drawn from that column's ground-truth values:
  - the median for comparisons;
  - the quartiles for BETWEEN;
  - frequent values for `=` and `IN`;
  - distinct frequent words for successive LIKE patterns.
- **Identifier-like columns** (more than 90% distinct values) are not grouped by or compared with `=` / `IN`, unless their table is a smaller dimension joined to a larger one.
- **A mutant is kept only if it:**
  - uses at least one new (column, clause) pair;
  - executes on the ground-truth tables;
  - returns at least one non-null row.
- **Drift levels** (the mixture construction of gradual concept drift; Gama et al., ACM Computing Surveys 2014):
  - the set at level d has as many queries as the train set: a share d of drifted queries and 1 − d of train queries;
  - levels are nested (the drifted queries at 25% are among those at 50%, and so on);
  - drifted queries are spread over as many source queries as possible;
  - each set records its CliffGuard distance from the train set and the share of its (column, clause) occurrences the train set never uses.

## The sets

| Corpus | Pool | 25%: δ / novel share | 50% | 75% | 100% | Operators at 100% |
|---|---:|---|---|---|---|---|
| Med | 632 | 0.013 / 0.09 | 0.038 / 0.22 | 0.073 / 0.35 | 0.130 / 0.46 | 79 replace |
| Legal | 510 | 0.021 / 0.10 | 0.085 / 0.21 | 0.188 / 0.30 | 0.327 / 0.39 | 48 replace, 16 add |
| Art | 512 | 0.016 / 0.12 | 0.063 / 0.26 | 0.142 / 0.37 | 0.246 / 0.49 | 61 replace, 3 add |
| CSPaper | 494 | 0.024 / 0.09 | 0.092 / 0.20 | 0.211 / 0.28 | 0.380 / 0.36 | 38 replace, 26 add |
| Player | 182 | 0.016 / 0.06 | 0.064 / 0.13 | 0.140 / 0.18 | 0.251 / 0.24 | mostly add (the train set uses most columns) |

The CliffGuard distance and the novel-feature share both grow with the level on every corpus.

**Files** (per corpus):

| File | Contents |
|---|---|
| `frozen_train.json` | the frozen train set |
| `drift_pool.json` | every valid drifted query, with its source, operator and new pairs |
| `drift_25.json` … `drift_100.json` | the sets, each with its hashes and statistics |
| `summary.json` | the per-corpus summary |

## Caveats
- **Gold is used only to build the benchmark, not by the system.** Ground-truth values fix the constants and validate the queries; the system never sees these tables.
- **Scoring:** drifted queries are scored the same way as benchmark queries, by executing them on the gold tables.
- **Degree of change:** one operator per query keeps drifted queries close to the workload's style. Larger per-query drift, such as two operators or new join graphs, is not included.
- **Player** has the least room for drift. Its train set already uses most columns in most clauses, so its 100% set reaches a novel-feature share of 0.24, against 0.36–0.49 elsewhere.

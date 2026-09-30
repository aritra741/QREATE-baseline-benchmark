# Template-paired drift (branch `experiment/drift-design`)

Code: `eval/drift_paired.py` (streams), `eval/drift_run.py` with `QUWARTS_DRIFT_DESIGN=drift_paired` (replay). Tables: `RESULTS.md` (levels), `PAIRED.md` (each drifted query against its own source). W0, T0 and the build reads are those of `drift_design`.

## Design, and the prior work each part follows
- **Templates and instances** (QB5000; DSB and TPC query generation): every level of a stream is built from the same base queries (T0). At level p, p% of them are replaced by drifted versions of themselves, so only drift changes between levels.
- **Value drift = parameter drift** (DSB's shifting parameter distributions; Bruno, Chaudhuri & Thomas, TKDE 2006, on target cardinalities): constants no build query uses, selectivity-matched to the replaced constant (within a factor of two of its gold count).
- **Attribute drift = an unseen column on the same template** (Negi et al., VLDB 2023): one column is replaced by a schema column the build never read. It has the same role (group, filter or aggregate) and type, and a similar number of distinct values (within a factor of two). String constants compared with it become selectivity-matched values of the new column. Columns in joins, LIKE, range comparisons and CASE conditions are not swapped.
- **Levels and gradual streams** (DBA bandits / HMAB dynamic workloads; DSB distribution sequences): 0/25/50/75/100% of up to 28 base queries; gradual streams of twice the base, with drift probability rising; 3 seeds.
- **Validity:** every generated query returns a non-empty answer on gold.
- **Base sizes per axis** (T0 queries with a variant): attribute 14–28, value 5–18, combined 16–28. Legal's value axis has only 5 base queries.

## Paired result at 100% drift (benchmark metric, 3 seeds): QuWARTS on the drifted query minus on its source

| Corpus | Attribute | Value | Combined | Static on drifted attribute queries |
|---|---|---|---|---:|
| CSPaper | +0.055 [−0.012, +0.123] | +0.064 [−0.007, +0.154] | +0.040 [−0.014, +0.100] | 0.007 |
| Player | +0.057 [−0.015, +0.132] | −0.098 [−0.193, −0.009] | −0.001 [−0.064, +0.064] | 0.041 |
| Art | +0.099 [+0.022, +0.179] | +0.016 [−0.050, +0.084] | +0.079 [+0.011, +0.147] | 0.016 |
| Med | −0.009 [−0.020, +0.000] | +0.009 [−0.032, +0.049] | −0.009 [−0.029, +0.011] | 0.034 |
| Legal | −0.037 [−0.111, +0.037] | +0.115 [+0.044, +0.192] | −0.004 [−0.074, +0.067] | 0.000 |
| Finan | −0.041 [−0.099, +0.015] | +0.088 [+0.036, +0.139] | +0.012 [−0.033, +0.055] | 0.000 |
| **Mean** | **+0.021** | **+0.032** | **+0.020** | |

These are replayed from the full read (QuWARTS's patches reuse its values), as in `drift_design`.

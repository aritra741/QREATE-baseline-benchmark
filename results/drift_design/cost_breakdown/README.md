# Where patch tokens go when each new column is fetched per query (cost model, no calls)

Protocol: the build reads W0 columns only; a query with a new column gets its description and re-reads the documents in its scope that lack it. Mean of 3 seeds. Shares are of patch tokens.

| Corpus | Stream | Patch tokens (x build) | Re-read a document already re-read | Long documents | Column reused later | Value found word for word | Computable from build columns | Saved by scope (M) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| cspaper | attribute/100 | 0.71M (1.8x) | 0.68 | 0.00 | 0.83 | 0.06 | 0.00 | 0.11 |
| cspaper | combined/100 | 0.87M (2.2x) | 0.75 | 0.00 | 0.50 | 0.04 | 0.00 | 0.17 |
| cspaper | attribute/gradual | 0.98M (2.5x) | 0.77 | 0.00 | 0.65 | 0.06 | 0.00 | 0.44 |
| player | attribute/100 | 6.27M (3.0x) | 0.73 | 0.77 | 0.74 | 0.12 | 0.00 | 0.34 |
| player | combined/100 | 5.58M (2.7x) | 0.71 | 0.76 | 0.54 | 0.16 | 0.00 | 0.00 |
| player | attribute/gradual | 6.55M (3.2x) | 0.74 | 0.76 | 0.72 | 0.22 | 0.00 | 0.40 |
| art | attribute/100 | 4.56M (1.9x) | 0.78 | 0.00 | 0.80 | 0.30 | 0.00 | 0.93 |
| art | combined/100 | 3.49M (1.4x) | 0.71 | 0.00 | 0.78 | 0.19 | 0.00 | 1.56 |
| art | attribute/gradual | 4.57M (1.9x) | 0.78 | 0.00 | 0.75 | 0.36 | 0.00 | 1.14 |
| med | attribute/100 | 12.85M (5.0x) | 0.74 | 0.62 | 0.63 | 0.18 | 0.00 | 0.42 |
| med | combined/100 | 8.94M (3.5x) | 0.63 | 0.60 | 0.52 | 0.14 | 0.00 | 0.42 |
| med | attribute/gradual | 12.07M (4.7x) | 0.73 | 0.62 | 0.70 | 0.18 | 0.00 | 1.70 |
| legal | attribute/100 | 21.79M (4.7x) | 0.82 | 0.49 | 0.71 | 0.29 | 0.00 | 9.42 |
| legal | combined/100 | 18.55M (4.0x) | 0.79 | 0.48 | 0.86 | 0.28 | 0.00 | 8.12 |
| legal | attribute/gradual | 21.33M (4.6x) | 0.81 | 0.48 | 0.75 | 0.26 | 0.00 | 1.76 |
| finan | attribute/100 | 89.03M (5.4x) | 0.83 | 1.00 | 0.88 | 0.19 | 0.00 | 24.71 |
| finan | combined/100 | 96.09M (5.9x) | 0.85 | 1.00 | 0.59 | 0.12 | 0.00 | 24.98 |
| finan | attribute/gradual | 84.75M (5.2x) | 0.83 | 1.00 | 0.82 | 0.15 | 0.00 | 32.08 |

## Three checks (cost model and stored values; no calls) — `checks.py`, `chk_<corpus>.json`

**Cost law.** Over 45 streams per corpus (3 axes × 5 levels × 3 seeds), patch tokens under lazy augmentation against the stream's characterization:

| Corpus | r(tokens, unseen feature mass) | r(tokens, attribute novelty) | r(tokens, constant novelty) |
|---|---:|---:|---:|
| CSPaper | 0.78 | 0.75 | 0.29 |
| Art | 0.91 | 0.89 | −0.10 |
| Legal | 0.87 | 0.87 | −0.07 |
| Player | 0.86 | 0.87 | −0.19 |

**Shape transfer.** Share of value-drift literal parts (equality values and LIKE cores) whose Potter's-Wheel shape is among the shapes of W0's literals for the column: CSPaper 0.95, Player 0.88, Art 0.71, Legal 0.65. Misses are semantic columns (Art style, color; Legal defendant names).

**Scope soundness.** Pushdown on raw stored values vs on the online representation, single-table value-drift queries: identical on CSPaper, Legal and Player; on Art the representation keeps 306 documents that raw values wrongly pruned and halves the queries pruned to nothing (15 → 7 of 59). Queries pruned to nothing on every view (CSPaper 30/77, Legal 14/53) are extraction misses: no stored value matches the literal.

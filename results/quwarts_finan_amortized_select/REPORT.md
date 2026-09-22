# Finan amortized θ25 selection-program arm

**Corrected interpretation:** the official combined product 0.0543 is a destructive interaction between two selectors, not evidence that candidate generation is the remaining bottleneck. Program-only was an independently frozen alternative: product 0.0872 at 66,700 tokens (4.8% of DocETL’s 1,381,827). Residual-only product 0.0972 cannot be produced without those compiler tokens; its causal cost is 333,114, not 266,414.

The previously published label `candidate generation is the remaining bottleneck` is withdrawn. A later three-replica program-only test is in `results/quwarts_finan_amortized_program_only_repro/`.

## Scores (unchanged frozen artifacts)

| System | structure F2 | cell F1@0.20 | product | tokens |
| --- | ---: | ---: | ---: | ---: |
| Plumbing | — | — | 0.0158 | 0 |
| Prior θ25 per-cell selector | — | — | 0.0296 | 344,601 |
| Frozen DocETL | 0.5367 | 0.1142 | 0.084 | 1,381,827 |
| Program-only | 0.4642 | 0.1457 | 0.0872 | 66,700 |
| Residual-only | 0.4321 | 0.1346 | 0.0972 | 266,414 sidecar / **333,114 causal** |
| Combined (program then residual `setdefault`) | 0.5228 | 0.0878 | 0.0543 | 333,114 |

Combined used setdefault after program fills. Residual never overwrote a program cell (0 same-cell conflicts; 315 + 56 = 371 combined cells). The regression is bag-level SQL interaction.

## Freeze status of the sub-arms

Both sidecars were materialized and bag-hashed in `frozen.json` before `load_ground_truth`. Materialization rules were fixed in code before gold.

- Program-only 66,700 equals the ledger sum of compiler + critic + repair and includes every Qwen call required to produce that sidecar.
- Residual prompts, filters, and schedule depend on the compiled specifications, so residual-only is not a 266,414-token independent arm.

## Per-query products that explain 0.0872 / 0.0972 → 0.0543

| Query | program | residual | combined | Δ vs program | mechanism |
| --- | ---: | ---: | ---: | ---: | --- |
| `finan_filter20:q9` | 0.3704 | 0.3704 | 0.0000 | −0.3704 | two useful selections interacted through a filter (1 row each; bags differ) |
| `finan_agg20:q4` | 0.3704 | 0.5000 | 0.0000 | −0.3704 | residual added a second row; aggregate-value / FP-support interaction |
| `finan_agg20:q13` | 0.0000 | 0.1630 | 0.0000 | 0.0000 | residual’s extra row destroyed its own aggregate win |
| `finan_groupby20:q14` | 0.1340 | 0.2679 | 0.2143 | +0.0803 | group reassignment (7 → 8 rows) |
| `finan_filter20:q8` | 0.0000 | 0.0000 | 0.1299 | +0.1299 | extra residual `exchange_code` cells created a second filter row |
| `finan_multiagg20:q18` | 0.0163 | 0.0043 | 0.0204 | +0.0041 | mild aggregate-value interaction |
| `finan_agg20:q14` | 0.1299 | 0.0000 | 0.1299 | 0.0000 | program win survived; bags still differ |
| `finan_multiagg20:q4` | 0.3750 | 0.2500 | 0.3750 | 0.0000 | bags differ; product preserved |

Those two −0.3704 drops, plus the smaller mix of +0.0803 / +0.1299 / +0.0041, recover the 0.0329 mean-product gap from program-only to combined.

## Hashes (from the original freeze)

- Inventory `0fc5a8bb1758aab9ce2092814da8e5c15708890503623171f125bb3c2dce7580`
- Samples `ceabd5b0ac976976b93db253e31070fccc89976abff97bf871e4da35f4dd7ba7`
- Official schema `3f88e9f1a5ef0e559280ac4e6470ed5fa536a99fe1c4fc588bba8bdc24bfad1e`
- Policy payload `c0af5ce0e5754586da55523f9a1659ab678395e4eba553f8d4e40b7e9bb265ea`
- Prompt module `d104f4f93737a049433017f622dad3b7d328515d62239d6db4b52a4203640bd0`
- Validated specs `e5fe872fe35ef5228cf9d952aec0ed586a889b8c5a4252ded71a12e7149c0a30`
- Program bags `5c67d7a39058fcc634f9c525145eb697981168dec9567b5287676ec80f4a41c0`
- Residual bags `50021e9dca0481f6a80cf62af7d41be2ba16a2d7e3bb9e245ca032eb7e0c91f1`
- Combined bags `8a744039965c664ff7c295e649df99bcd170349fdeb8d3024bd1bcfc8a2735a8`
- Ledger `78edb507c11e1b81af1c71042be347c16287768081f86a51fada0c76995309e0`

Artifacts: `results/quwarts_finan_amortized_select/`.

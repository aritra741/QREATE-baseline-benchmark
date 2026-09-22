# Finan program-only three-replica reproducibility test

**Decision: `program-only win is replica-dependent; consensus does not beat DocETL`**

Replica 3 product 0.0910 exceeds frozen DocETL 0.084. The predeclared three-replica majority consensus product is 0.0784 and does not. Global spend 198,433 ≤ θ25 345,457. Candidate-set recall is identical across replicas (189 / 1179); the consensus miss is selector instability, not a generation-recall failure.

## Part 1. Existing sub-arm validation

Program-only and residual-only were genuine frozen alternatives, not post-gold reconstructions. `materialize_fills` and `frozen.json` both precede `load_ground_truth` in `finan_amortized_select_arm.py`. Existing 0.0872 is **not** diagnostic-only.

| Sub-arm | frozen before gold | materialization fixed before gold | DBs/bags hashed before gold | exact tokens | 16-query F2 | cell F1@0.20 | product |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Program-only | yes | yes | yes | **66,700** | 0.4642 | 0.1457 | 0.0872 |
| Residual-only | yes | yes | yes | 266,414 sidecar / **333,114 causal** | 0.4321 | 0.1346 | 0.0972 |
| Combined | yes | yes | yes | 333,114 | 0.5228 | 0.0878 | 0.0543 |

- Program-only 66,700 equals the ledger sum of compiler + critic + repair and includes every Qwen call required to produce that sidecar.
- Residual-only requires the compiled programs (schedule, filters, residual prompts). Causal cost is 333,114, not 266,414.
- Combined used program fills first, then residual `setdefault`. Zero same-cell overwrites.

### Existing hashes

| Object | SHA-256 |
| --- | --- |
| Inventory | `0fc5a8bb1758aab9ce2092814da8e5c15708890503623171f125bb3c2dce7580` |
| Samples | `ceabd5b0ac976976b93db253e31070fccc89976abff97bf871e4da35f4dd7ba7` |
| Official schema | `3f88e9f1a5ef0e559280ac4e6470ed5fa536a99fe1c4fc588bba8bdc24bfad1e` |
| Policy payload | `c0af5ce0e5754586da55523f9a1659ab678395e4eba553f8d4e40b7e9bb265ea` |
| Prompt module | `d104f4f93737a049433017f622dad3b7d328515d62239d6db4b52a4203640bd0` |
| Compiler prompts jsonl | `112ecb68a267fcbb43534f225214c7fdf9bafd7850da7701fba5a91974cea61f` |
| Critic prompts jsonl | `0801e6008f095690cf35ee68e52e654575b039b04f3f3b8afea396c6515c6261` |
| Validated specs | `e5fe872fe35ef5228cf9d952aec0ed586a889b8c5a4252ded71a12e7149c0a30` |
| Program bags | `5c67d7a39058fcc634f9c525145eb697981168dec9567b5287676ec80f4a41c0` |
| Residual bags | `50021e9dca0481f6a80cf62af7d41be2ba16a2d7e3bb9e245ca032eb7e0c91f1` |
| Combined bags | `8a744039965c664ff7c295e649df99bcd170349fdeb8d3024bd1bcfc8a2735a8` |
| Ledger | `78edb507c11e1b81af1c71042be347c16287768081f86a51fada0c76995309e0` |
| Program DB | `b26581fbe054ac2523fc4b3c0eea7277a39b6b5795dfdbc167fe1aa3f38cc4f5` |
| Residual DB | `c6e7576ec0bf0cfc39ea6191f1ba8dcc4864c5825af7b3c02df6d7f9f23c6e41` |
| Combined DB | `bba706784ca38460f33fa2f10565ec1687687b8eda4938c055fa7ce25ad0332e` |

## Combined-arm interference (frozen artifacts only)

Residual never displaced a program cell. The 0.0543 combined product is SQL-level interaction of 315 program cells plus 56 residual cells.

Largest regressions:

- `finan_filter20:q9`: program 0.3704 and residual 0.3704 both collapse to combined 0.0000. Each sidecar returns one row; the union of cells changes the surviving filter row. Classification: two individually useful selections interacted through a filter.
- `finan_agg20:q4`: program 0.3704 / residual 0.5000 / combined 0.0000. Combined grows 1 → 2 rows. Classification: increased false-positive support plus aggregate-value interaction.
- `finan_agg20:q13`: residual 0.1630 → combined 0.0000 when program cells ride along (2 → 3 rows). Classification: increased false-positive support / aggregate-value interaction.
- `finan_groupby20:q14`: program 0.1340 / residual 0.2679 / combined 0.2143 (7 → 8 groups). Classification: group reassignment.
- `finan_filter20:q8`: program 0 / residual 0 / combined 0.1299 after residual `exchange_code` cells add a second filter row. Classification: increased false-positive support that happened to score.
- `finan_multiagg20:q18`: mild constructive aggregate interaction (0.0163 → 0.0204).

No residual-overwrite class occurred. This diagnostic was not used to change the consensus policy.

## Part 2. Fresh three-replica program-only test

Finan only. Same frozen inventory and samples. Unchanged compiler, critic, executor, construct, and NULL-only overlay. No residual calls. Cache reuse disabled. `replica_id` is telemetry only (0 leaks into model user text). Per-replica compiler+critic cap 69,091; three-replica max 207,273 < θ25.

| Replica | compiler+critic tokens | attributes compiled by Qwen | accepted cells |
| ---: | ---: | ---: | ---: |
| 1 | 65,879 | 8 / 14 (then empty-spec restore) | 253 |
| 2 | 66,628 | 8 / 14 | 260 |
| 3 | 65,926 | 8 / 14 | 339 |
| Global | **198,433** | — | consensus 249 |

### Official scores

| Arm | structure F2 | cell F1@0.20 | product | tokens | accepted | SQL-visible | empty bags |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| plumbing | 0.2891 | 0.0259 | 0.0158 | 0 | 0 | 0 | 6 |
| replica 1 | 0.4183 | 0.1241 | 0.0784 | 65,879 | 253 | 247 | 3 |
| replica 2 | 0.4183 | 0.1241 | 0.0784 | 66,628 | 260 | 247 | 3 |
| replica 3 | 0.4629 | 0.1520 | **0.0910** | 65,926 | 339 | 326 | 2 |
| three-replica consensus | 0.4183 | 0.1241 | **0.0784** | 198,433 | 249 | 236 | 3 |
| frozen DocETL | 0.5367 | 0.1142 | **0.0841** | 1,381,827 | — | — | — |

Declared DocETL bar is product 0.084. Consensus 0.0784 does not clear it. Replica 3 does.

Empty bags: plumbing `{q7, q11-multi, q17, q8, q11-filter, q3}`; replicas 1–2 and consensus `{filter20:q7, multiagg20:q11, filter20:q8}`; replica 3 `{filter20:q7, multiagg20:q11}`.

### Per-query product and Δ plumbing

| Query | plumbing | r1 | r2 | r3 | consensus | r1 Δ | r3 Δ | cons Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `finan_multiagg20:q4` | 0.1250 | 0.3750 | 0.3750 | 0.2500 | 0.3750 | +0.2500 | +0.1250 | +0.2500 |
| `finan_filter20:q9` | 0.0000 | 0.3704 | 0.3704 | 0.3704 | 0.3704 | +0.3704 | +0.3704 | +0.3704 |
| `finan_filter20:q7` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_multiagg20:q11` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_multiagg20:q18` | 0.0043 | 0.0043 | 0.0043 | 0.0163 | 0.0043 | 0 | +0.0120 | 0 |
| `finan_agg20:q4` | 0.0000 | 0.3704 | 0.3704 | 0.3704 | 0.3704 | +0.3704 | +0.3704 | +0.3704 |
| `finan_groupby20:q14` | 0.1235 | 0.1340 | 0.1340 | 0.1235 | 0.1340 | +0.0105 | 0 | +0.0105 |
| `finan_agg20:q11` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_multiagg20:q9` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_agg20:q13` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_agg20:q17` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_filter20:q8` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_filter20:q11` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_filter20:q15` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_agg20:q3` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| `finan_agg20:q14` | 0.0000 | 0.0000 | 0.0000 | 0.3261 | 0.0000 | 0 | +0.3261 | 0 |

Replica 3’s official win is concentrated on `finan_agg20:q14` (+0.3261) and a smaller `q18` gain, partly offset by a weaker `q4` multiagg. Majority vote drops those singleton-replica cells, so consensus tracks replicas 1–2.

## Agreement before gold

| Pattern | cells |
| --- | ---: |
| All three select the same candidate | 183 |
| Exactly two select the same candidate | 66 |
| Conflicting selections (no two-vote majority) | 11 |
| One selection plus abstentions | 120 |
| All abstain | 799 |

Pairwise specification agreement (14 attributes): 1–2: 8; 1–3: 7; 2–3: 8.

Pairwise cell-selection agreement (1179 cells): 1–2: 1028; 1–3: 895; 2–3: 976.

Consensus policy (frozen before scoring): ≥2 replicas same candidate ID → materialize that ID; otherwise abstain. No union, no confidence tie-break, no residual fallback, no query-effect inspection.

## Freeze gates (all four arms)

All true before gold: 100 entity rows; `__entity_id` unchanged; incumbent non-NULL cells unchanged; every written value reconstructs from an opaque inventory ID; official queries execute; empty sidecar reproduces plumbing; spend 198,433 ≤ 345,457.

## Diagnostics after gold (not official)

Candidate-set recall is the shared frozen inventory: 189 / 1179 for every replica and the consensus.

Selector accuracy given present: replica 1 22/189; replica 2 22/189; replica 3 21/189; consensus 16/189.

Replica 3 accepted more cells (339 vs 253/260) without higher gold-cell accuracy. Consensus is stricter (249 cells, 16/189). The official miss is majority-vote conservatism under selector variance, not missing candidates in the inventory.


## New-run hashes

| Object | SHA-256 |
| --- | --- |
| Inventory (reused) | `0fc5a8bb1758aab9ce2092814da8e5c15708890503623171f125bb3c2dce7580` |
| Samples (reused) | `ceabd5b0ac976976b93db253e31070fccc89976abff97bf871e4da35f4dd7ba7` |
| Prompt module | `d104f4f93737a049433017f622dad3b7d328515d62239d6db4b52a4203640bd0` |
| Consensus policy | `1bbfffe3fc780f1d8cb7b12167a819d5cc823f8f00bf5eebe2dfb1eeaad18316` |
| Ledger fingerprint | `b60ca5e20b0db7331093b1fbe6ed307e675a8f7d86476a6b7b70a3431eb75d05` |
| Replica 1 specs | `902cd28f3da352c292853fbd2f7a6873942292cb7b20bc8dca64772a1c50c8ab` |
| Replica 2 specs | `8cf92f16daed0946a6f6b3177393a1a3d2efcc78380c5769e3eea4fb5576b101` |
| Replica 3 specs | `d852c2a3c1af404413357864ba10a764ea2a1dcd2643074dc6d73a5a32d6bc21` |
| Replica 1 bags | `c15be151959348d28ff7745b253fe1cb864f51d3effd7ecd26c21e34f4f6419d` |
| Replica 2 bags | `a325cc6457bb954c264f3ac3a95b5f25545e6a6d69fce891b9734d1de31dab43` |
| Replica 3 bags | `613344e2e37602f1f6b0cef906c062359550be18d2bf4f3be6b54ae80b494038` |
| Consensus bags | `ad061cb4bad59668ad8a03a89cac170adab746bd5bcdf9571ed0f74c55eca6f1` |
| Agreement | `029f3388bd9fc7e48a20b26de02e6a9b4d791182ea3b19708117ab434076913c` |
| Replica 1 / 2 / 3 / consensus DBs | `bad0bdb53650435962692f6e6608e40a22b5420e8e8f83ab9b036e90acaba95c` / `8333b29f2e48a3a6fe99e38e0fb2fdfe2fb3e03d97ca3ab469e7d32271fec8ff` / `4b02c19abdb97fdaec4ca651b2d09f947762b2d510766c7a5eed76a60706e7c8` / `41a94f42bd8d641e7cb1f2e03be3fdde5f068e6cfa36c340130a261ec7a3ae04` |
| Replica 1 / 2 / 3 journals | `9af1eb9f1caee3460dbfe69e8f477d0a66c3aa77e462322ca8a1b42b1ddcd678` / `fd9c73d6fede9d051819c980b2ba7e3d7992b57d45599b87aed963c8d9434873` / `8b7456284538d2ec077985e19f6308abd94f6372fa6b1f47b580a7a4ce2ddd50` |

Artifacts: `results/quwarts_finan_amortized_program_only_repro/`.

**Primary decision:** `program-only win is replica-dependent; consensus does not beat DocETL`

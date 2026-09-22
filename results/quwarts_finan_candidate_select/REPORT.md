# Finan schema-grounded candidate-selection arm

Qwen selected opaque candidate IDs only. Values were built after the call from those IDs. Gold was loaded after freeze.

## Decision

**`candidate selection beats DocETL`**

16-query product **0.1221** vs DocETL **0.084**, C1 availability oracle **0.0767**, exact-message A1 **0.0440**, shared-bundle **0.0411**, plumbing **0.0158**.

Short selector cards covered **100** entities and **1,174** cells (517 accepted) versus **79** shared-bundle fills.

## Scores

| Set | structure F2 | cell F1@0.20 | product |
| --- | ---: | ---: | ---: |
| θ25 16-query | 0.313 | 0.049 | 0.0296 |
| θ100 16-query | 0.544 | 0.171 | **0.1221** |
| θ100 15-query | 0.525 | 0.153 | 0.1056 |

Spent 1,303,552 of 1,381,827. Unused 78,275. θ25 is a prefix (314 calls, spent 344,601).

## Coverage vs quality

| Metric | Value |
| --- | ---: |
| Calls | 1174 |
| Accepted cells | 517 |
| Abstentions | 657 |
| Entities | 100 |
| Empty candidate sets | 3 |
| Candidate-set recall | 188 / 1174 (0.160) |
| Selector accuracy given gold in set | 76 / 188 (0.404) |
| Operations | identity 808, none 366 |
| Predicate-literal copying | 0 |
| SQL-visible fills | 466 |

Wrong-period 185, wrong-candidate 163, wrong-component 96, wrong-unit 1. Generation still misses most gold spans; the product lift is from filling many more NULL cells, not from high per-cell exactness.

13 of 16 query bags changed. Largest product lifts: `finan_filter20:q8` +0.556, `finan_filter20:q9` +0.370, `finan_agg20:q14` +0.370, `finan_multiagg20:q4` +0.250.

## Gates

All pre-spend gates passed: gold-free candidates, extractive outputs are IDs, every candidate has source offsets, official descriptions present, no extra query literals in extractive prefixes, empty overlay reproduces plumbing, no overwrite of non-NULL cells, 100 rows, all queries execute, hard ledger.

## Hashes

| Object | SHA-256 |
| --- | --- |
| Official schema | `3f88e9f1a5ef0e559280ac4e6470ed5fa536a99fe1c4fc588bba8bdc24bfad1e` |
| Attribute specs | `60225252c29a3e981f6b77da50186c1caf12747cfd0a61afdaf46179a61d2d9f` |
| Candidate inventory | `0fc5a8bb1758aab9ce2092814da8e5c15708890503623171f125bb3c2dce7580` |
| Schedule θ100 | `1012954f54ae9a741bde824ea7f2df27833b0606060288dc2e1a70569b0b1358` |
| Rendered prompts | `4602881bd66ff3647eec68c6bf704f6b7c2f2d8d2f168a7dcbad2f3dbff968d7` |
| Plumbing | `ad91c2554f32510cb378737009e6479cfcb71299f245c7fe766722057b2b2a3d` |

Artifacts: `results/quwarts_finan_candidate_select/`.

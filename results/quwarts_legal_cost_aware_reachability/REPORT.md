# Legal cost-aware candidate reachability

No frozen artifact was modified. No selection arm or model call was launched.

Semantic feasibility is already settled: the frozen inventory contains a shared assignment at **0.2123**. This audit asks whether that win can be acquired cheaply enough to leave selector headroom under θ25 = 12,610,011.

## Ledger reconciliation

Proposal 4,425,885 + verification 7,831,475 + router 5,674 = **12,263,034**. Gap vs frozen generation spend: **0**.
Surface candidates, deterministic normalized expansions, and AST workload labels cost zero. A semantic or composed candidate is charged the full proposer that emitted it. Supported and uncertain official candidates remain eligible without verification, so those verifiers are not charged. One call is never split across candidates. Charged official semantic/composed proposers total 3,114,285 tokens over 601 calls; the residual 9,148,749 is unused proposers, all verifiers, and router.

## Part 1. Channel-restricted shared searches

| Channels | Best product | Writes | Qwen generation cost | Beats DocETL |
| -------- | -----------: | -----: | -------------------: | -----------: |
| empty | 0.0225 | 0 | 0 | no |
| surface | 0.0600 | 743 | 0 | no |
| normalized | 0.0225 | 4 | 0 | no |
| workload_label | 0.1039 | 553 | 0 | no |
| semantic | 0.0381 | 57 | 3,063,307 | no |
| surface+normalized | 0.0600 | 747 | 0 | no |
| surface+workload_label | 0.1681 | 1291 | 0 | yes |
| surface+normalized+workload_label | 0.1886 | 1297 | 0 | yes |
| surface+workload_label+semantic | 0.2123 | 1347 | 3,063,307 | yes |
| surface+normalized+workload_label+semantic | 0.2123 | 1351 | 3,063,307 | yes |
| surface+normalized+workload_label+semantic+composed | 0.2123 | 1351 | 3,114,285 | yes |

These are feasible lower bounds, not exact maxima. Deterministic subsets have generation cost 0 because no charged call is required. The 0.2123 full-inventory point still costs the original 12,263,034 if the frozen semantic generation schedule is replayed in full; a selector that only materializes surface + normalized + workload_label pays nothing.

## Part 2. Ablation of the 0.2123 winner

- `drop_composed`: product 0.2123 (beats DocETL). winner used 0 composed writes
- `drop_semantic`: product 0.1681 (beats DocETL). projected ablation; dedicated DET search later reached 0.1886
- `drop_normalized`: product 0.2123 (beats DocETL). winner used 4 normalized writes; not required
- `drop_workload_label`: product 0.0694 (misses DocETL). causally required for a win
- `drop_surface`: product 0.1065 (misses DocETL). causally required for a win

Removing every winner-used semantic proposer for one attribute still left a win:

- `case_type` semantic-call cohort: product 0.1696, still wins True
- `hearing_year` semantic-call cohort: product 0.2065, still wins True
- `legal_basis_num` semantic-call cohort: product 0.2088, still wins True
- `defendant_current_status` semantic-call cohort: product 0.1968, still wins True
- `first_judge` semantic-call cohort: product 0.1968, still wins True
- `plaintiff_current_status` semantic-call cohort: product 0.1953, still wins True

Causal importance for retaining product > 0.1235: **surface and workload_label are required**; normalized and composed are not; semantic is helpful (0.1886 → 0.2123) but not necessary.

## Part 3. Minimum-cost winning inventory

The cheapest winning generating-call set found is the empty set. Backward elimination, greedy pruning, and forward selection all stop at the deterministic inventory. Zero is a certified minimum over generating-call units because no cheaper non-negative cost exists.

The 0.2123 assignment is also realizable from only the 56 proposers that emitted its semantic writes (242,136 tokens), without verifiers.

| Tokens | Product | Label |
| -----: | ------: | --- |
| 0 | 0.1886 | deterministic |
| 242,136 | 0.2123 | winner-used semantic proposers |
| 3,063,307 | 0.2123 | all official semantic proposers |
| 12,263,034 | 0.2123 | full frozen generation replay |

## Part 4. Budget frontier

| Budget | Best product | Spent | Headroom | Beats DocETL |
| -----: | -----------: | ----: | -------: | -----------: |
| 0 | 0.1886 | 0 | 12,610,011 | yes |
| 100,000 | 0.1886 | 0 | 12,610,011 | yes |
| 250,000 | 0.2123 | 242,136 | 12,367,875 | yes |
| 500,000 | 0.2123 | 242,136 | 12,367,875 | yes |
| 1,000,000 | 0.2123 | 242,136 | 12,367,875 | yes |
| 2,000,000 | 0.2123 | 242,136 | 12,367,875 | yes |
| 4,000,000 | 0.2123 | 242,136 | 12,367,875 | yes |
| 6,000,000 | 0.2123 | 242,136 | 12,367,875 | yes |
| 8,000,000 | 0.2123 | 242,136 | 12,367,875 | yes |
| 10,000,000 | 0.2123 | 242,136 | 12,367,875 | yes |
| 12,263,034 | 0.2123 | 242,136 | 12,367,875 | yes |

Residual selector headroom at the cheapest win: **12,610,011** = 12,610,011 − 0.

| Selector configuration | Tokenized estimate | Fits in headroom |
| --- | ---: | --- |
| Frozen five-program selector | 332,184 | yes |
| Compact per-cell reranker, one pass | 2,143,859 | yes |
| Compact per-cell reranker, two passes | 4,287,718 | yes |
| Adjudication on replica disagreements (1441 cards) | 1,608,774 | yes |

Card estimates were obtained by rendering the proposed cards and running the Qwen tokenizer. No API calls were made.

## Part 5. Deterministic-only feasibility

- Best product: **0.1886**
- Assignment hash: `413cdf54c6b3eb13e469abedd50fe308047dd2c006b2dbab41498f0662b73902`
- Writes: 1297; retained plumbing: 1681 / 2978
- Hamming distance from the 0.2123 assignment: 59
- Paid-channel writes remaining: 0
- Independent rebuild product matches checkpoint: True; official bags match: True; unknown IDs: 0
- F2 0.5721; F1@0.20 0.2357
- Writes by attribute/channel: {"defendant_current_status:workload_label": 202, "legal_basis_num:surface": 192, "hearing_year:workload_label": 113, "legal_basis_num:workload_label": 126, "plaintiff_current_status:surface": 58, "first_judge:surface": 228, "case_number:workload_label": 32, "hearing_year:surface": 155, "case_number:surface": 53, "defendant_current_status:surface": 57, "case_type:workload_label": 35, "plaintiff_current_status:workload_label": 39, "first_judge:normalized": 1, "defendant_current_status:normalized": 1, "hearing_year:normalized": 1, "verdict:workload_label": 2, "first_judge:workload_label": 1, "case_type:normalized": 1}

| Query | Full 0.2123 | Deterministic | Delta |
| --- | ---: | ---: | ---: |
| `legal_multiagg20:q4` | 0.0017 | 0.0004 | -0.0013 |
| `legal_filter20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q7` | 0.5000 | 0.5000 | +0.0000 |
| `legal_multiagg20:q11` | 0.1111 | 0.1111 | +0.0000 |
| `legal_multiagg20:q18` | 0.0962 | 0.0962 | +0.0000 |
| `legal_agg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_groupby20:q14` | 0.3750 | 0.3750 | +0.0000 |
| `legal_agg20:q11` | 0.2500 | 0.2256 | -0.0244 |
| `legal_multiagg20:q9` | 0.0712 | 0.0159 | -0.0553 |
| `legal_agg20:q13` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q17` | 0.2500 | 0.2500 | +0.0000 |
| `legal_filter20:q8` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q11` | 0.7500 | 0.4511 | -0.2989 |
| `legal_filter20:q15` | 0.1923 | 0.1923 | +0.0000 |
| `legal_agg20:q3` | 0.8000 | 0.8000 | +0.0000 |
| `legal_agg20:q14` | 0.0000 | 0.0000 | +0.0000 |

Queries that lose when semantic candidates are removed:

- `legal_multiagg20:q4`: 0.0017 → 0.0004 (-0.0013)
- `legal_agg20:q11`: 0.2500 → 0.2256 (-0.0244)
- `legal_multiagg20:q9`: 0.0712 → 0.0159 (-0.0553)
- `legal_filter20:q11`: 0.7500 → 0.4511 (-0.2989)

## Part 6. Candidate-call utility

Of 785 proposal calls, **56** emit a candidate used in the 0.2123 assignment (242,136 tokens). The remaining proposal tokens, all 7,831,475 verification tokens, and 5,674 router tokens are unused by that assignment. The deterministic winning assignment uses **zero** of those calls.

Context split of proposers: {"whole_document": {"calls": 641, "tokens": 3652427, "in_2123": 50}, "retrieved_pack": {"calls": 144, "tokens": 773458, "in_2123": 6}}.

The 12.263M generation spend was dominated by calls that no winning assignment needs. A live Legal run can skip semantic/composed proposal and verification entirely.

## Separate conclusions

1. Semantic feasibility: the frozen inventory contains a winning shared assignment (0.2123).
2. Acquisition feasibility: a winning subset can be generated at **0** candidate-generation tokens.
3. Selection headroom at that cost: **12,610,011** tokens. The frozen five-program selector (332,184) fits, as do both tokenized reranker passes and the disagreement-adjudication estimate.

deterministic candidates already contain a Legal win

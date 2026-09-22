# Fresh Full-Window Additive QuWARTS Arm (Finan)

**Decision:** `diagnostic M4 did not reproduce under fresh sampling`

The run is valid. All 112 primary Qwen calls completed under θ100. The official 16-query product is **0.0292**, above plumbing **0.0158** and below frozen DocETL **0.084** and diagnostic M4 **0.0904**. No prompt, cap, acceptance, document-set, or materialization change was made after scoring.

This is a controlled seven-document arm. Document IDs were derived from frozen DocETL `pipeline_output` artifacts and then checked against `{9, 10, 18, 69, 70, 78, 93}`. That set is not the generic QuWARTS selection policy.

Gold, scorer output, prior completions, and DocETL answer tables were loaded only after `frozen.json` was written.

---

## 1. Decision table

| System | 16-query product |
|---|---:|
| Plumbing | 0.0158 |
| Fresh full-window additive QuWARTS | **0.0292** |
| Frozen DocETL | 0.084 |
| Diagnostic M4 using stored replay completions | 0.0904 |

`0.0292 > 0.084` is false, so the arm does not beat DocETL.

The mechanism isolated by M4 (full-window query-specific extraction + type-valid retention without exact-span rejection + non-destructive plumbing-NULL fills) therefore **did not reproduce** when QuWARTS issued its own fresh Qwen calls.

---

## 2. Locked inputs

| Item | Value |
|---|---|
| Model | `qwen/qwen-2.5-7b-instruct` |
| Cache | fresh (`results/quwarts_finan_full_window_additive/cache`) |
| Domain | Finan only |
| Base database | `results/quwarts_finan_plumbing/artifacts/databases/finan_plumbing.db` |
| Query set | exact 16 IDs from `results/docetl_finan_case80/query_manifest.json` |
| Documents | 7 IDs derived from frozen `pipeline_output` |
| Document IDs | `9, 10, 18, 69, 70, 78, 93` |
| Tasks | 16 × 7 = **112** |
| θ25 | 345,457 |
| θ100 | 1,381,827 |
| Uniform input cap | **11,719** |
| Completion cap | 400 |
| Tokenizer slack | 200 |
| Ledger safety | 2,048 |
| Reserved total | 1,381,776 ≤ θ100 |
| Scheduling | DocETL manifest order |
| Prompt | generic DocETL `extract_fields` structure |
| Context | full document, mid-cut truncation |
| Retries | none (HTTP transport only) |
| Official output | query-local overlay, not a seven-row replacement table |

---

## 3. Pre-spend gates

All gates passed before the first Qwen call:

| Gate | Result |
|---|---|
| Exactly 16 query IDs | true |
| Exactly seven unambiguous document IDs | true |
| Exactly 112 primary tasks | true |
| Schemas contain every AST-referenced base attribute | true |
| Empty overlays reproduce plumbing bags | true |
| Candidate fills only a NULL cell | true |
| Candidate cannot overwrite a non-NULL cell | true |
| Query-local writes cannot affect another query | true |
| Missing markers never enter SQLite | true |
| All 100 plumbing rows and identities survive | true |
| All official queries execute | true |
| Precomputed maximum charges fit θ100 | true |
| No gold / scorer / prior-completion / answer-table path reachable | true |

---

## 4. Spend and checkpoints

θ25 is the largest completed-query prefix with spend ≤ 345,457. The θ25 journal is the exact 28-row prefix of the θ100 journal.

| | θ25 | θ100 |
|---|---:|---:|
| Completed queries | 4 | 16 |
| Journal rows / calls | 28 | 112 |
| Spent | 314,401 | 1,255,801 |
| Unused | 31,056 | 125,026 |
| Empty bags | 5 | 2 |

θ25 completed queries:

```text
finan_multiagg20:q4
finan_filter20:q9
finan_filter20:q7
finan_multiagg20:q11
```

The next query (`finan_multiagg20:q18`) finished at 393,208, which exceeds θ25, so it was excluded from the θ25 freeze. Unused budget was not spent on refiners, validators, or extra prompts.

No reservation refusal occurred. No provider failure occurred. Call count remained **112**.

---

## 5. Call and parse diagnostics

| Metric | Count |
|---|---:|
| Primary Qwen calls | 112 |
| Malformed outputs | 0 |
| Deterministic JSON salvages | 0 |
| Accepted fields | 132 |
| Missing markers (`-1`, `""`, null) | 141 |
| Type-invalid | 0 |
| Illegal categorical | 0 |
| Field cells | 273 |

Accepted fields by attribute:

| Attribute | Accepted | Missing marker |
|---|---:|---:|
| auditor | 26 | 2 |
| principal_activities | 22 | 6 |
| net_profit_or_loss | 21 | 7 |
| revenue | 18 | 10 |
| earnings_per_share | 12 | 2 |
| business_segments_num | 7 | 7 |
| net_assets | 6 | 8 |
| remuneration_policy | 5 | 16 |
| total_debt | 4 | 17 |
| exchange_code | 4 | 17 |
| major_equity_changes | 4 | 17 |
| dividend_per_share | 3 | 4 |
| cash_reserves | 0 | 21 |
| the_highest_ownership_stake | 0 | 7 |

---

## 6. Token percentiles

Rendered/truncated input tokens (Qwen tokenizer, after mid-cut):

| | tokens |
|---|---:|
| min | 7,860 |
| p25 | 11,713 |
| median | 11,719 |
| p75 | 11,719 |
| max | 11,719 |
| mean | 11,176.7 |
| truncated prompts | 96 / 112 |

Provider usage (prompt + completion):

| | tokens |
|---|---:|
| min | 7,886 |
| p25 | 11,745 |
| median | 11,756.5 |
| p75 | 11,772.8 |
| max | 11,816 |
| mean | 11,221.4 |

Estimated completion tokens (usage − truncated input): mean **44.7**, range 24–97.

---

## 7. Overlay materialization

For each query, a 100-row copy of the clean plumbing relation was filled only where the plumbing cell was NULL and this query produced a type-valid candidate.

| Metric | Count |
|---|---:|
| Accepted fills (non-NULL cells added) | **73** |
| Blocked overwrites | 59 |
| Sentinels blocked | 0 |
| Missing aligned rows | 0 |
| Isolation failures | 0 |
| Identity checksum (all overlays) | `c78abe65517253f5aed475209d1694921a064ce2812dacf7386ae49afc8d051b` |
| Queries with at least one fill | 14 |
| Queries with score lift vs plumbing | 3 |
| Empty official bags (θ100) | `finan_multiagg20:q11`, `finan_agg20:q17` |

`finan_agg20:q17` and `finan_agg20:q14` produced no accepted fills; their overlay databases remain byte-identical to plumbing (`ad91c255…`).

---

## 8. Scores

### θ25 (4 completed queries; remaining 12 use unchanged plumbing)

| Set | F2 | cell F1@0.20 | product |
|---|---:|---:|---:|
| 16-query | 0.3238 | 0.0337 | 0.0236 |
| 15-query count-only | 0.3295 | 0.0359 | 0.0252 |

### θ100 (all 16 completed)

| Set | F2 | cell F1@0.20 | product |
|---|---:|---:|---:|
| 16-query | 0.4347 | 0.0538 | **0.0292** |
| 15-query count-only | 0.4478 | 0.0574 | 0.0312 |

### Per-query (θ100 vs plumbing)

| Query | F2 | F1@0.20 | product | plumbing | Δ | pred rows | fills |
|---|---:|---:|---:|---:|---:|---:|---:|
| finan_multiagg20:q4 | 1.000 | 0.250 | 0.2500 | 0.1250 | +0.1250 | 2 | 11 |
| finan_filter20:q9 | 0.556 | 0.000 | 0.0000 | 0.0000 | 0 | 1 | 2 |
| finan_filter20:q7 | 0.556 | 0.000 | 0.0000 | 0.0000 | 0 | 1 | 4 |
| finan_multiagg20:q11 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0 | 0 | 2 |
| finan_multiagg20:q18 | 0.065 | 0.067 | 0.0043 | 0.0043 | 0 | 1 | 12 |
| finan_agg20:q4 | 1.000 | 0.000 | 0.0000 | 0.0000 | 0 | 2 | 3 |
| finan_groupby20:q14 | 0.636 | 0.211 | 0.1340 | 0.1235 | +0.0105 | 7 | 3 |
| finan_agg20:q11 | 0.862 | 0.000 | 0.0000 | 0.0000 | 0 | 5 | 4 |
| finan_multiagg20:q9 | 0.556 | 0.000 | 0.0000 | 0.0000 | 0 | 1 | 8 |
| finan_agg20:q13 | 0.238 | 0.000 | 0.0000 | 0.0000 | 0 | 1 | 3 |
| finan_agg20:q17 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| finan_filter20:q8 | 0.238 | 0.333 | 0.0794 | 0.0000 | +0.0794 | 1 | 6 |
| finan_filter20:q11 | 0.455 | 0.000 | 0.0000 | 0.0000 | 0 | 2 | 9 |
| finan_filter20:q15 | 0.000 | 0.000 | 0.0000 | 0.0000 | 0 | 1 | 2 |
| finan_agg20:q3 | 0.556 | 0.000 | 0.0000 | 0.0000 | 0 | 1 | 4 |
| finan_agg20:q14 | 0.238 | 0.000 | 0.0000 | 0.0000 | 0 | 1 | 0 |

Score lift is concentrated in three queries. Fourteen queries received fills; most of those fills did not move F2 × cell F1@0.20.

---

## 9. Comparison to frozen current-snapshot DocETL replay

Compared only after both arms were frozen.

| Check | Value |
|---|---:|
| Normalized value agreement | 0.227 |
| NULL / non-NULL agreement | 0.755 |
| Candidate overlap | 62 / 273 |
| Overlay-bag agreement | 2 / 16 |

Fresh Qwen outputs agree with stored replay completions on about one quarter of normalized values. The M4 diagnostic used those stored completions; this arm does not.

---

## 10. Hashes and isolation

Plumbing and the DocETL manifest remain byte-identical.

| Artifact | SHA-256 |
|---|---|
| Plumbing database | `ad91c2554f32510cb378737009e6479cfcb71299f245c7fe766722057b2b2a3d` |
| Ordered query IDs | `7107c8e6f4128aa31d14ffa21c73b1eec87ca70f687a81a8ae7bf5e415bace1d` |
| Ordered document IDs | `52435d9a2159e8b8c6767bd19e0161a4ce5929437e3351bfaa7d6a494e01b323` |
| Source contents | `470c8cf1af581e475601db14116fda23a6a71716a3f76ad162132fddbf759e24` |
| Mapping | `7c28808e5929a373bdf4ef5b36de9d5e8bf850daaad3ebdd63a16f243c7c3056` |
| Schemas | `6ddc5b7a750f3a4188f350330b77d87aeb05bc008d16e6b420a7a63f5bc894cb` |
| Prompt template | `9c47e11449155384cfaf56a1d6dda1699ee6604970f5d62447d233a51fd5ffda` |
| Policy | `310020fa7442cb75d5d4db2f6990df2e4657766a775bd4a6a47ed85106aa8450` |
| Input cap | `5feebf37afe234422c169b669b0cc5cfd63402404da2756bc3c564b1bfff1363` |
| Rendered prompts (payload hash) | `cb91474d45b2258c66df1a8ff58650073e9e012e495ad88279f483c781087b5e` |
| Rendered prompts file | `7501b4cd1ce987a3ff7921859a6ae1fd57ab0576ec55759f2035a74b8ab6d509` |
| θ25 bags | `9e6774f71ba3795a40d79a456062abc49db54bcac0f6bd7d72aa6a762e43e3d8` |
| θ25 journal | `e2f72f952241acbd57ff40424077304b35e5214371480bc96199d8702ee2d852` |
| θ25 ledger | `6d26715cb5e43750bdd82e3962f5462c7260bffcb2a4dcb86544e2002c0d170c` |
| θ100 bags | `1fd650179dc397c7637a938679dea6ecfe2378b8636c2d62b87d0aefab78e2aa` |
| θ100 journal | `58ea316c374d453c8a07663081e55998647c314fde299187d731fdff408ae724` |
| θ100 ledger | `348e6dc1c5265c3a3fe733ccad701bfbe453667c5a642a8e21a998c75db89262` |

| Invariant | Result |
|---|---|
| θ25 journal is a prefix of θ100 | true |
| Plumbing unmodified | true |
| Isolation OK | true |
| Isolation failures | none |

---

## 11. Artifacts

```text
results/quwarts_finan_full_window_additive/
  pre_spend_gates.json
  rendered_prompts.json
  frozen.json
  theta25_{frozen,journal,ledger,bags}.json
  theta100_{frozen,journal,ledger,bags}.json
  finan_full_window_additive_arm.json
  query_local/*.db
```

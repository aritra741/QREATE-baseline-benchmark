# Fresh Exact-Message Additive QuWARTS Arm (Finan)

**Decision:** `exact messages improve QuWARTS but do not beat DocETL`

The run is valid. The 102/102 request-equality gate passed before any call. Official A1 scores **0.0440** on the 16-query product: above the prior non-equivalent arm (0.0292) and plumbing (0.0158), below frozen DocETL (0.084) and diagnostic M4 (0.0904).

No adapter, acceptance, overlay, schedule, or budget change was made after scoring. Frozen DocETL, prior fresh-arm, and plumbing trees were not modified.

Gold was loaded only after `frozen.json`.

---

## 1. Decision table

| System | 16-query product |
|---|---:|
| Plumbing | 0.0158 |
| Prior fresh non-equivalent arm | 0.0292 |
| Fresh exact-message **A1** | **0.0440** |
| Current-snapshot DocETL replay | 0.0534 |
| Fresh exact-message **D0** (native-map diagnostic) | 0.0525 |
| Frozen DocETL | 0.084 |
| Diagnostic M4 | 0.0904 |

A1 > 0.0292 and A1 ≤ 0.084, so the arm improves QuWARTS without beating DocETL.

D0 (0.0525) matches the current-snapshot replay (0.0534) to two decimal places. Exact messages plus the DocETL tool path reproduce that native diagnostic. They do not reproduce M4 (0.0904).

On the 102 request-identical pairs, raw tool-call agreement is **0.529**. That disagreement can now be attributed to model/provider variability.

---

## 2. Locked inputs and gate

| Item | Value |
|---|---|
| Model / route | `openrouter/qwen/qwen-2.5-7b-instruct` |
| Temperature / max_tokens | omitted (as in the instrumented requests) |
| Cache | fresh, LiteLLM `caching=False` |
| Documents | `9, 10, 18, 69, 70, 78, 93` (derived, not hardcoded policy) |
| Tasks | 16 × 7 = 112 generated requests |
| Comparable stored primaries | **102 / 102 identical** |
| Generated-only (`q3`/`q14`) | 10, same adapter, invariants passed |
| Completion reservation | 72 + 64 = **136** |
| θ25 / θ100 | 345,457 / 1,381,827 |

All pre-spend gates passed. Request payloads were frozen in `request_payloads.json` before the first call.

---

## 3. Spend and checkpoints

θ25 is the 21-call, 3-query journal prefix. Its last `spent_after` is **259,324**. The θ25 journal is the exact prefix of the θ100 journal.

| | θ25 | θ100 |
|---|---:|---:|
| Completed queries | 3 | 15 |
| Calls | 21 | **111** |
| Spend (journal) | 259,324 | 1,366,894 |
| Unused vs ceiling | 86,133 | 14,933 |

The last call issued was `finan_agg20:q14` / doc `78`. The next reservation (doc `93`, 15,519) would have exceeded θ100, so it was not issued. `q14` uses the unchanged plumbing bag.

No completion exceeded the 136 reservation. The ledger never crossed the ceiling.

A transport SSL failure interrupted the first process after in-memory calls past θ25. Those unpersisted calls were discarded. The arm resumed from the frozen 21-row θ25 journal with provider-error retries only (not validation retries).

---

## 4. Call diagnostics

| Metric | Count |
|---|---:|
| Primary calls | 111 |
| Malformed | 0 |
| Accepted type-valid fields | 187 journaled / 150 in the resume-process counter |
| A1 fills | 109 |
| Blocked overwrites | 72 |
| Empty A1 bags | `finan_filter20:q8` |
| Empty D0 bags | q18, q17, q8, q3, q14 |

API usage:

| | Prompt | Completion |
|---|---:|---:|
| min | 303 | 16 |
| median | 15,490 | 37 |
| max | 17,410 | 78 |
| mean | 12,276 | 38.8 |

Precomputed input tokens: min 214, mean 12,214, max 17,320.

---

## 5. Scores

### A1 official overlay (θ100)

| Set | F2 | cell F1@0.20 | product |
|---|---:|---:|---:|
| 16-query | 0.5312 | 0.0612 | **0.0440** |
| 15-query count-only | 0.5508 | 0.0653 | 0.0469 |

θ25 A1 product: **0.0314** (16) / 0.0335 (15).

### D0 native seven-row map (θ100)

| Set | F2 | F1@0.20 | product |
|---|---:|---:|---:|
| 16-query | 0.4489 | 0.0625 | **0.0525** |
| 15-query count-only | 0.4789 | 0.0667 | 0.0560 |

### A1 per-query vs plumbing

| Query | F2 | F1@0.20 | product | Δ plumbing |
|---|---:|---:|---:|---:|
| finan_multiagg20:q4 | 1.000 | 0.375 | 0.3750 | +0.2500 |
| finan_multiagg20:q11 | 0.556 | 0.222 | 0.1235 | +0.1235 |
| finan_groupby20:q14 | 0.636 | 0.316 | 0.2010 | +0.0775 |
| finan_multiagg20:q18 | 0.065 | 0.067 | 0.0043 | 0 |
| all others | — | — | 0 | 0 |

---

## 6. Agreement on the 102 identical requests

| Check | Result |
|---|---:|
| Raw tool-call agreement | 0.529 (54 / 102) |
| Normalized value matches | 123 cells |
| NULL / non-NULL matches | 234 cells |
| D0 bag agreement vs replay | 6 |
| A1 overlay-bag agreement vs replay | 1 |

Because the 102 request payloads matched byte-for-byte, the 47% raw disagreement is model/provider variability, not prompt or window mismatch.

---

## 7. Hashes

| Artifact | SHA-256 |
|---|---|
| Plumbing | `ad91c2554f32510cb378737009e6479cfcb71299f245c7fe766722057b2b2a3d` |
| Replay `frozen.json` | `2c362e9e73e0020cbf0f42289a7ca814f0f675d016be8e025c07910345b7638f` |
| Prior fresh `frozen.json` | `4b4e6b100a611c69eebcbbe9452c2da99767d474a3137c2332abe0839992384d` |
| Ordered query IDs | `7107c8e6f4128aa31d14ffa21c73b1eec87ca70f687a81a8ae7bf5e415bace1d` |
| Ordered document IDs | `52435d9a2159e8b8c6767bd19e0161a4ce5929437e3351bfaa7d6a494e01b323` |
| Source contents | `470c8cf1af581e475601db14116fda23a6a71716a3f76ad162132fddbf759e24` |
| Schemas | `6ddc5b7a750f3a4188f350330b77d87aeb05bc008d16e6b420a7a63f5bc894cb` |
| Adapter source | `96b99788b26d50d0f4532c5e3002ac32bef418a6e6b63fcf00baf04eb7926847` |
| Policy | `859eb3153215c4c1d1ce8f133d55e5c8925ed0617938742f335687786e579f35` |
| Requests | `af5a5b73f4962f28eafda175de52226818cdece3f38971b2f8955a67d24b89cc` |
| Equality tests | `e9cb54beb637b0f80df4f0d5ba614bb15fc9ff139a4a0d6b01b77a592bda3d9b` |
| Request payloads file | `55e12b199de82abd049c9b823c0e13eee55a1a70212fedf44f8ac9c4469a4d33` |

Isolation failures: none. Plumbing unchanged.

Runner: `systems/WDIRS/quwarts/eval/finan_exact_message_additive_arm.py`  
Output: `results/quwarts_finan_exact_message_additive/`

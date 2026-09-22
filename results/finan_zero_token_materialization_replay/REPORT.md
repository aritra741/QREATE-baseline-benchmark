# Zero-Qwen Reconciliation and Materialization Replay (Finan)

**Decision:** `context window is the remaining dominant lever`

**Corrected causal conclusion:** `prompt/context/materialization and historical runtime-configuration differences remain material; a different seven-document snapshot is not supported`

No Qwen calls. Frozen trees were not modified:

```text
results/docetl_finan_current_snapshot_replay/
results/quwarts_finan_docetl_unit_parity/
results/quwarts_finan_plumbing/
```

Gold was loaded only after `freeze.json` was written.

---

## 1. Causal conclusion

The current seven source files are byte-identical to the `source_text` stored in frozen DocETL `pipeline_output` artifacts (agreement **1.000**).

Therefore this run does **not** report `both prompt/context and historical-input differences remain material`.

What remains material, with document contents held fixed:

| Difference | Status |
|---|---|
| Seven-document file bytes | Not supported (agreement 1.000) |
| Historical YAML plans | Unavailable |
| Truncation / `max_input_tokens` | Material (~10.4k after-trunc vs frozen ~12.3k) |
| Validation retries | Material (133 journaled calls vs frozen 112) |
| Provider nondeterminism | Residual on completed queries |
| Prompt / context / materialization vs QuWARTS | Material (see scores) |

Frozen historical raw DocETL calls are **N/A**, not `0.000`.

---

## 2. Strict-budget prefix

Declared ceiling **1,381,827**. Over-budget diagnostic spent **1,412,380**. Charge per call = API prompt + completion tokens. Calls are not split.

| | Strict-budget prefix | Over-budget diagnostic |
|---|---|---|
| Spend | **1,369,703** | 1,412,380 |
| Remainder | **12,124** | 0 |
| Included calls | 130 | 133 |
| Primary (attributed document) | 108 | — |
| Retries (`document_id` missing / validation) | 22 | — |
| Completed queries | 14 | 14 (same set) |
| Incomplete | `finan_agg20:q3`, `finan_agg20:q14` | same |

- Last included call: index **130**, `finan_agg20:q3` / doc `9`, charge 319.
- First excluded call: index **131**, `finan_agg20:q3` / doc `18`, charge 17,117 (would reach 1,386,820).

The three over-budget calls did not finish another query. Native bags for the 14 completed queries are therefore identical on the prefix and the diagnostic.

Incomplete programs stay empty. Plumbing is not substituted.

**Future hard ceiling:** refuse to start a call unless `spent + max_permitted_call_charge ≤ ceiling`. Observed max call charge is **17,677**. A pre-call reservation using that cap would have blocked the overshoot.

---

## 3. Native-score reconciliation (0.053 vs 0.049)

There is one canonical native score for a frozen call prefix.

**Canonical native (M2):** DocETL `pipeline_output` → keep SQL schema columns only → numeric coerce → `pandas.to_sql`. Complete = the live run finished the query.

That path **reproduces** the official live bags and the official product **0.053365**.

The older acceptance-gate “native” score **0.049** is a different, incorrect path. It is retained only as `acceptance_native_buggy_reconstruction`.

| Check | Official live vs acceptance C | Official live vs canonical M2 |
|---|---|---|
| Call prefix | No (C used every journal row, including retries) | Yes (same completed 14) |
| Completed-query definition | Same 14 IDs | Same |
| Retry winner | No (C inserted extra rows; some docs dropped in live output) | Yes (live `pipeline_output`) |
| Parsed rows | No (5–6 live rows vs 7–16 C rows) | Yes |
| Unknown encoding | No (C coerced `-1` / `''` to NULL) | Yes (`-1` / `''` then numeric coerce) |
| SQL | Yes | Yes |
| Query manifest | Yes | Yes |
| Incomplete queries | No (C rematerialized partial `q3`) | Yes (empty) |
| Scorer inputs | No | Yes |

First differing artifact on the official-vs-C path is **table construction**: C inserted every journal call as a row and nulled DocETL sentinels. Example: `finan_agg20:q13` live table has 6 rows and `avg_eps=51.5`; C’s 7-row NULL-coerced table produced `avg_eps=25.75`.

M0 rematerialization **reproduces** stored QuWARTS parity bags exactly.

---

## 4–6. Materializers and scores

Rules were hashed in `freeze.json` before gold.

| ID | Rule |
|---|---|
| M0 | Existing QuWARTS exact-span grounding (stored `normalized_value`). Unknown = NULL. |
| M1 | Type-valid structural normalization; no verbatim span. Missing markers → NULL. |
| M2 | Actual DocETL write path (above). |
| M3 | M1 values plus DocETL missing sentinels `-1` / `''`. |
| M4 | Copy 100-row plumbing DB; fill NULL cells on the seven IDs (`N` ↔ `N.txt`); never overwrite non-NULL; no sentinels. |

### 16-query DocETL manifest

| Source × materializer | F2 | F1@0.20 | Product | Empty bags | Non-NULL cells |
|---|---:|---:|---:|---|---:|
| Strict-budget / over-budget **M2 canonical** | 0.479 | 0.077 | **0.0534** | q18, q17, q3, q14 | 175 |
| Strict-budget / over-budget M3 | 0.479 | 0.077 | **0.0534** | same | 175 |
| Strict-budget / over-budget M1 | 0.459 | 0.066 | **0.0382** | same | 175 |
| Strict-budget / over-budget M0 | 0.173 | 0.035 | **0.0165** | 9 queries | 94 |
| QuWARTS M0 (stored parity) | 0.000 | 0.000 | **0.0000** | 15 / 16 | 17 |
| QuWARTS M1 | 0.112 | 0.010 | **0.0058** | 12 | 77 |
| QuWARTS M3 | 0.272 | 0.052 | **0.0223** | 7 | 77 |
| Plumbing | 0.289 | 0.026 | **0.0158** | 6 | — |
| **M4 plumbing overlay** | 0.556 | 0.140 | **0.0904** | q17, q3 | 57 fills / 24 skipped |

### 15-query count-only subset

| Source × materializer | F2 | F1@0.20 | Product |
|---|---:|---:|---:|
| M2 / M3 DocETL | 0.511 | 0.082 | **0.0569** |
| M1 DocETL | 0.489 | 0.070 | **0.0407** |
| M0 DocETL | 0.184 | 0.037 | **0.0176** |
| QuWARTS M0 | 0.000 | 0.000 | **0.0000** |
| QuWARTS M1 | 0.120 | 0.011 | **0.0062** |
| QuWARTS M3 | 0.275 | 0.056 | **0.0238** |
| Plumbing | 0.292 | 0.028 | **0.0169** |
| M4 overlay | 0.549 | 0.116 | **0.0747** |

The 1,412,380-token run is labeled **over-budget diagnostic**. Its native M2 score equals the strict-budget prefix because no additional query completed.

M4 changed six queries vs plumbing: q4 (+0.250), q11 multiagg (+0.123), groupby q14 (+0.078), agg q11 (+0.157), filter q8 (+0.260), agg q14 (+0.326). Identity, signatures, joins, and query SQL were not altered.

---

## 7. Loss attribution (do not add)

Same frozen completions; deltas interact.

| Contrast | Δ product (16) |
|---|---:|
| Exact-span rejection, DocETL: M1 − M0 | **+0.0216** |
| Exact-span rejection, QuWARTS: M1 − M0 | **+0.0058** |
| DocETL retention semantics: M2 − M1 | **+0.0152** |
| Missing sentinels, DocETL: M3 − M1 | **+0.0152** |
| Missing sentinels, QuWARTS: M3 − M1 | **+0.0165** |
| Plumbing overlay: M4 − plumbing | **+0.0746** |

SQL predicates changed by NULL vs sentinel (M1 vs M3) on the prefix: `finan_multiagg20:q4` (range / CASE / GROUP BY / aggregate; `avg_cash` NULL vs float), `finan_multiagg20:q11` (`<> ''` / CASE / GROUP BY; 2 vs 4 bag rows), `finan_filter20:q15` (GROUP BY / aggregate; company_count 1 vs 4).

### Rejection-count reconciliation

| Reported count | Definition / denominator | Recomputed |
|---|---|---|
| **62 found-but-rejected** | QuWARTS field with non-empty `raw_value` and NULL `normalized_value` / **79** non-empty raw QuWARTS cells | **62 / 79** |
| **104 stated_span_failed** | Prior C `parse_map` on all DocETL journal calls, value used as evidence, `included_document_text` as context | Request-window on pipeline cells: **88**; full isolated source: **81**; QuWARTS journal span failures: **62**. The extra ~16–23 vs 104 are retry / dropped-doc journal rows that are not in `pipeline_output`. |
| **75 typed_reject** | Prior C missing-marker or `normalize_value` error on all journal field cells | Pipeline-cell M1: **48** `missing_marker` / **229** cells. The extra ~27 are retry / failed-doc journal cells. |

Intersections:

- The **62** is a subset of QuWARTS raw-non-NULL cells (79). All 62 are span / grounding rejects (`stated_span_failed` or `grounding=rejected`).
- The **104** and **75** were counted on DocETL completions, not on the QuWARTS 62. They can overlap with each other (a cell can be a missing marker and also fail a reconstructed span check) but they do not share a denominator with the 62.
- Pipeline-cell M0 keeps **94** non-NULL cells; M1/M2 keep **175**. The 81-cell span drop is the DocETL M0→M1 gap.

---

## Decision

Pre-declared before gold:

1. If M0 ≠ stored QuWARTS bags or M2 ≠ canonical native DocETL bags → internally inconsistent.
2. Else if `(M1_QuWARTS − M0_QuWARTS) > (canonical_DocETL − M1_QuWARTS)` and M1_QuWARTS > plumbing → acceptance is sufficient to justify a new full-window QuWARTS arm.
3. Else if M4 > plumbing and M1_QuWARTS ≤ M0_QuWARTS and M1_DocETL ≈ M0_DocETL → non-destructive plumbing composition is the only beneficial replay.
4. Else → context window is the remaining dominant lever.

M0 and M2 reproduce their targets, so the artifacts are consistent.

QuWARTS M1 is only **0.0058**. That lift (0.0058) is smaller than the remaining gap to canonical DocETL (0.0534 − 0.0058 = 0.0476). Acceptance on the existing 2.4k-token completions does not recover the DocETL result.

M4 is a large additive gain (**0.0904**) by filling 57 plumbing NULLs on the seven files while keeping the other 93 rows. That is composition with plumbing evidence, not a QuWARTS extraction success. The frozen rule therefore does not select “plumbing only.”

**`context window is the remaining dominant lever`**

Do not launch another extraction arm from this task. The next extraction question, if taken later, is the full-document truncated window (~10–12k), not another short-pack QuWARTS arm under current acceptance.

---

## Integrity

Prior frozen artifacts unchanged after this run.

| Artifact | sha256 |
|---|---|
| `results/docetl_finan_current_snapshot_replay/frozen.json` | `2c362e9e73e0020cbf0f42289a7ca814f0f675d016be8e025c07910345b7638f` |
| `results/docetl_finan_current_snapshot_replay/call_journal.json` | `2c6695412daa8a8e62933ef3012b51b298a1fd394a010de28978c07fc6dae4c5` |
| `results/quwarts_finan_docetl_unit_parity/finan_docetl_unit_parity_arm.json` | `84c1e528767604b0fd8b620cdd9a464e616eb6c6a870a9bb1dc3703cd67a2607` |
| `results/quwarts_finan_plumbing/artifacts/databases/finan_plumbing.db` | `ad91c2554f32510cb378737009e6479cfcb71299f245c7fe766722057b2b2a3d` |

### Freeze hashes

| Object | sha256 |
|---|---|
| rule specification | `195dc472bef593ddb71d498a12e8986c8067b00020f0bfeb5beee781fe042771` |
| decision rule | `0185ea90664e1f6f72d8ac2a5179b7e84bbd63c419090d00aba470e0d8d6d3a1` |
| parsed values | `e4fc612287d4090c914bbbbdf420bae73ac1dc94a788c7aa7fc885efbf87e0d3` |
| accepted / rejected | `883044972fdb801ec13dceb31d3cb3e1651dd605c5b2bcd790e3bbfb3885cef9` |
| bags | `56bb7125929a7c82f01a553af2287f1636648d2ffc55a430a5de7bb949d16cbc` |
| scorer manifest | `e5988f15221355cf52d08d90d34980ba9ccec9427e176ddaf7c0cef0a9f1798f` |
| M4 database | `1a8d680875a54c6e7bf6db2069e2158cf488504932606c529fcc9684faf0188d` |
| prefix call indices | `850c77d466ec9d646c4eef9b2842df339c1246155289c40d09b7c0dc3553c7fc` |

### On-disk reports

| Path | sha256 |
|---|---|
| `results/finan_zero_token_materialization_replay/freeze.json` | `9901b18007dcbd0d9eacb0a40cb2f3a9e565063022b219234e24090b4885973a` |
| `.../reconciliation_report.json` | `fd4074569ddb4b52f0530b25c0627a753c0788a4e74df65998c49a65f3821bfd` |
| `.../budget_prefix.json` | `24f49f4deb0d4f9389e04d1e89335ed7890f7080a85f760d1cf305d5cab47e4e` |
| `.../canonical_bags.json` | `523d7c34ef35db041e95af49f034b919ad879397ff48b703d8708c79b07bf354` |
| `.../native_reconciliation.json` | `51ffd76d0e4af7b41a197fc7091d467ffe36fff6c67be991b08d32ff79fa7a93` |

Runner: `systems/WDIRS/quwarts/eval/finan_zero_token_materialization_replay.py`

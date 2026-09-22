# Instrumented DocETL Current-Snapshot Replay (Finan)

**Conclusion:** `both prompt/context and historical-input differences remain material`

This was a replay on the **current** seven Finan files, not a reconstruction of the historical ingest snapshot. Exact YAML plans were not on disk. The run used the stored DocETL runner, prompt template, model lock, and current execution path:

```text
one query-specific extract_fields MapOp over seven documents
→ original benchmark SQL in SQLite
```

No QuWARTS retrieval, grounding, repair, signatures, fallback, shared tables, or query-witness logic was added. Frozen DocETL and QuWARTS artifacts were not modified.

---

## Setup

| Item | Value |
|---|---|
| Dataset | Finan only |
| Query set | 16 IDs from `results/docetl_finan_case80/query_manifest.json` |
| Documents | `[9, 10, 18, 69, 70, 78, 93]`, derived from every frozen `pipeline_output` (identical across all 16 queries) |
| Isolated input | `results/docetl_finan_current_snapshot_replay/isolated_input/finance/` (original `source_data` untouched) |
| Model | `openrouter/qwen/qwen-2.5-7b-instruct` |
| Cache | fresh, `bypass_cache=True` |
| Budget | hard ledger θ100 = **1,381,827** |
| DocETL source revision | `a27ad68a74bf3835ebe272708a836d023dd64f4f` |
| Planned primary work | 16 × 7 = **112** map calls |

Preflight confirmed 112 planned primary calls and aborted if the runner selected another document count, added optimizer stages, changed batching, or generated a different operator DAG.

Instrumentation started from `results/docetl_execution_anatomy_audit/instrumentation_patch.py` and was tested with mocked calls only. Fixture result:

| Check | Result |
|---|---|
| Messages unchanged | true |
| Truncation unchanged | true |
| Parsed result unchanged | true |
| Args unchanged | true |
| Overall | **ok** |

Gold, scorer output, and answer-table inspection happened only after freeze.

---

## Execution

| Item | Value |
|---|---|
| Planned primary calls | 112 |
| Journaled calls | **133** (112 primary + 21 MapOp validation retries) |
| Completed queries | **14 / 16** |
| Stopped at | `finan_agg20:q3` after 4 of 7 documents |
| Never started | `finan_agg20:q14` |
| Spent | **1,412,380** (prompt 1,407,471 + completion 4,909) |
| Unused budget | 0 |
| Cache status | `bypass` on all 133 calls |
| Provider errors | 0 |
| Parse/validation failures | 2 |
| Truncated calls | 118 / 133 |

The ceiling was crossed by in-flight calls. The completed prefix was frozen. Unfinished queries were left explicitly incomplete and scored as empty bags. Plumbing results were not substituted into the native DocETL score.

---

## Scores

Official metric: structure F2 × cell F1@0.20, then mean product.

| System | F2 | F1@0.20 | Product | Tokens | Empty bags |
|---|---:|---:|---:|---:|---|
| Frozen historical DocETL (16) | 0.537 | 0.114 | **0.084** | 1,381,827 | q18, q17, q3 |
| Current-snapshot DocETL replay (16) | 0.479 | 0.077 | **0.053** | 1,412,380 | q18, q17, q3 (+ q14 incomplete) |
| Current-snapshot replay (15 count-only) | 0.511 | 0.082 | **0.057** | 1,412,380 | same minus q14 |
| QuWARTS DocETL-unit parity (16) | 0.000 | 0.000 | **0.000** | 310,046 | 15 / 16 |
| Plumbing (16) | 0.289 | 0.026 | **0.016** | 0 | — |
| Plumbing (15) | 0.292 | 0.028 | **0.017** | 0 | — |

Replay **0.053** is above QuWARTS **0.000** and plumbing **0.016**, but does not reproduce frozen DocETL **0.084**.

On the 14 finished queries the replay product is **0.061** versus frozen **0.087**. The gap is not only the unfinished prefix.

### Per-query (replay vs frozen DocETL @0.20)

| Query | Replay F2 | Replay F1 | Replay prod | Pred rows | Frozen F2 | Frozen F1 | Frozen prod | Frozen rows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| finan_multiagg20:q4 | 1.000 | 0.375 | 0.375 | 2 | 1.000 | 0.500 | 0.500 | 2 |
| finan_filter20:q9 | 0.556 | 0.000 | 0.000 | 1 | 0.556 | 0.000 | 0.000 | 1 |
| finan_filter20:q7 | 0.556 | 0.000 | 0.000 | 1 | 0.556 | 0.000 | 0.000 | 1 |
| finan_multiagg20:q11 | 0.714 | 0.300 | 0.214 | 4 | 0.714 | 0.250 | 0.179 | 4 |
| finan_multiagg20:q18 | 0.000 | 0.000 | 0.000 | 0 | 0.000 | 0.000 | 0.000 | 0 |
| finan_agg20:q4 | 1.000 | 0.000 | 0.000 | 2 | 1.000 | 0.000 | 0.000 | 2 |
| finan_groupby20:q14 | 0.385 | 0.000 | 0.000 | 4 | 0.472 | 0.118 | 0.055 | 5 |
| finan_agg20:q11 | 0.556 | 0.000 | 0.000 | 3 | 0.714 | 0.000 | 0.000 | 4 |
| finan_multiagg20:q9 | 1.000 | 0.000 | 0.000 | 2 | 1.000 | 0.167 | 0.167 | 2 |
| finan_agg20:q13 | 0.833 | 0.222 | 0.185 | 4 | 0.833 | 0.222 | 0.185 | 4 |
| finan_agg20:q17 | 0.000 | 0.000 | 0.000 | 0 | 0.000 | 0.000 | 0.000 | 0 |
| finan_filter20:q8 | 0.238 | 0.333 | 0.079 | 1 | 0.455 | 0.286 | 0.130 | 2 |
| finan_filter20:q11 | 0.833 | 0.000 | 0.000 | 4 | 0.833 | 0.000 | 0.000 | 4 |
| finan_filter20:q15 | 0.000 | 0.000 | 0.000 | 2 | 0.000 | 0.000 | 0.000 | 2 |
| finan_agg20:q3 | 0.000 | 0.000 | 0.000 | 0 | 0.000 | 0.000 | 0.000 | 0 |
| finan_agg20:q14 | 0.000 | 0.000 | 0.000 | 0 | 0.455 | 0.286 | 0.130 | 2 |

---

## A. Historical versus replayed DocETL

Zero new model calls. Align by query ID, document ID, and extracted field.

| Comparison | Result |
|---|---|
| Frozen raw calls / rendered prompts | **Unavailable** — marked, not inferred |
| Source-text agreement (112 query×doc texts vs frozen `pipeline_output`) | **1.000** |
| Raw output agreement | 0.000 (no frozen raw calls) |
| Normalized value agreement | 0.000 (same) |
| NULL / non-NULL agreement | 0.103 (252 field cells vs frozen extracted tables) |
| Query-table pairs compared | 14 |
| Final-bag agreement | 0.286 |

The seven current files are the same bytes that frozen DocETL stored as `source_text`. The unmatched 0.084 is **not** a different 7-file document snapshot.

Residual mismatch on completed queries:

1. **Truncation / configuration** — 118/133 calls truncated; mean after-trunc **10,378** Qwen tokens / **10,582** API prompt tokens versus frozen **12,304** input tokens/call.
2. **Retry protocol** — current MapOp validation retries produced 133 calls versus frozen **112**.
3. **Prefix freeze** — q3 incomplete, q14 never run (frozen q14 product 0.130).
4. **Provider nondeterminism** — same schema/SQL, different cells (q4 0.375 vs 0.500; multiagg q9 0 vs 0.167; filter q8 0.079 vs 0.130; groupby 0 vs 0.056).

---

## B. DocETL versus QuWARTS prompt/context

The ~1.07M token gap is almost entirely the document window.

| | Frozen DocETL | Current replay | QuWARTS parity |
|---|---:|---:|---:|
| Mean input / context tokens | 12,304 | 10,582 API / 10,378 Qwen | 2,361 |
| Total tokens | 1,381,827 | 1,412,380 | 310,046 |
| Truncated calls | n/a (no journal) | 118 / 133 | retrieved pack, not full-doc truncate |
| Non-NULL extraction rate | n/a | 0.792 | sparse; 62 found-but-rejected |
| Malformed rate | n/a | 0.015 | — |

What accounts for the difference:

- DocETL sends the **full annual report**, then `truncate_messages` mid-cuts it (observed cuts of 197k–829k tokens from 213k–829k-token prompts).
- QuWARTS sends a **~2,400-token retrieved pack**.
- DocETL adds system prompt + tool schema; unknowns are **`-1` / `""`**, not `null`.
- DocETL prompt has **no exact-span evidence requirement**; QuWARTS requires an exact span for stated values.

112 × 12,304 ≈ 1,378,048, matching frozen prompt tokens. 112 × 2,361 ≈ 264k of QuWARTS’s 310k. The remainder is instruction/schema overhead.

---

## C. Acceptance-gate replay

Same frozen replay completions, three zero-token materializers. Extracted values were not altered.

274 raw extracted values.

| Materializer | Retained non-NULL | Empty bags | Product (16) | Rejections |
|---|---:|---|---:|---|
| Native DocETL parse / SQL | 213 | q18 | **0.049** | — |
| QuWARTS strict span-grounding | 103 | 7 queries | **0.017** | 104 `stated_span_failed` |
| Type-valid, no exact-span reject | 199 | q18 | **0.038** | 75 `typed_reject` |

QuWARTS’s found-but-rejected rule independently collapses DocETL’s own raw outputs (0.049 → 0.017, near plumbing 0.016). That effect is separate from prompt quality.

---

## Why this conclusion

- **Prompt/context/materialization is better on the current files.** Replay 0.053 ≫ QuWARTS 0.000 and above plumbing 0.016. Gate C shows native DocETL keep-rules retain more of the same completions.
- **Historical run conditions are still required to hit 0.084.** Same seven file bytes, but a different truncation cap (~12.3k vs ~10.4k), a 112-call no-retry path, and a finished 16-query prefix. Exact historical YAML was not on disk.

This is not “current DocETL replay reproduces the frozen advantage” (0.053 ≠ 0.084). It is not “inconclusive because the exact historical pipeline is unavailable” — the executable runner ran. It is not a different 7-file ingest snapshot (`source_text` agreement = 1.0).

Do not launch another QuWARTS extraction arm. The mismatch versus frozen 0.084 is configuration, truncation, retries, the unfinished prefix, and residual nondeterminism — not source contents.

If QuWARTS copies one thing next, the smallest measured lever is **acceptance**: stop exact-span rejection of type-valid values (C: 0.017 → 0.038; native 0.049). Next is the **full-document truncated window** (~10–12k vs 2.4k) and the **`-1` / `""` unknown protocol** that keeps SQL filters from dropping rows.

---

## Integrity

Prior frozen artifacts remained byte-identical after this run.

| Artifact | sha256 |
|---|---|
| `results/docetl_finan_case80/summary.json` | `d5a42ba33092908f1ca876de089635bbf04ad5617acd215aa1ee9a351868f2cc` |
| `results/docetl_finan_case80/query_manifest.json` | `e94136f82cb634d45c2c37a861452f2e2e00185b7de3ecb8049d4b814986bfcd` |
| `results/quwarts_finan_plumbing/artifacts/databases/finan_plumbing.db` | `ad91c2554f32510cb378737009e6479cfcb71299f245c7fe766722057b2b2a3d` |
| `results/quwarts_finan_docetl_unit_parity/finan_docetl_unit_parity_arm.json` | `84c1e528767604b0fd8b620cdd9a464e616eb6c6a870a9bb1dc3703cd67a2607` |

### Pre-call and freeze hashes (`frozen.json`)

| Object | sha256 |
|---|---|
| ordered query IDs | `7107c8e6f4128aa31d14ffa21c73b1eec87ca70f687a81a8ae7bf5e415bace1d` |
| derived document IDs | `52435d9a2159e8b8c6767bd19e0161a4ce5929437e3351bfaa7d6a494e01b323` |
| current source contents | `470c8cf1af581e475601db14116fda23a6a71716a3f76ad162132fddbf759e24` |
| ID-to-file mapping | `7c28808e5929a373bdf4ef5b36de9d5e8bf850daaad3ebdd63a16f243c7c3056` |
| DocETL runner | `99cb2dd05fdc32828d8a5fc3adca65e36d7582c796dc95b7c1cff70b02f79f03` |
| DocETL grid runner | `89b3a2050612ca690052549602d0c41265cf85be2a39928d1fa16b99eb22d263` |
| DocETL API | `4ef13edf9a585e9f78325b1e20f5a88f0e7d57d0733542d1211464e4d12701d2` |
| DocETL source revision | `a27ad68a74bf3835ebe272708a836d023dd64f4f` |
| prompt template | `d670861c3b2292d169d81320d5395c032de877ddea2ee45e072fd02510edcd1d` |
| model parameters / configuration | `877cf458bf988e14cf4df22afbde24630ab704b0a7023981fdad7313aecb0fe7` |
| isolated input manifest | `ec6ae0832ad4723a521566d764968b226e8d6967a7b19ce600164668ab41545b` |
| execution input | `16e1adb25a809b7c6f02e9996bcd89509c6afe490ac792ab3bc35359c86d49be` |
| journal | `f76e62eab985fb2877876ccabc6f848b402178ecd9e1ab03a05f314db21291bb` |
| rendered prompts | `d405faf6cc50049160857f7dc8b157767800718f4982c9a568403b801b270c95` |
| raw completions | `ae5e2ede85f1defee0e7bda570884b42ad97644fdbb38ece0bab6d287cf48750` |
| extracted tables | `ecbf84ab17f514fccaf929271614071713c702dba811407d24ba819666df4519` |
| SQLite bags | `8333206cea14aaa249a15aeb5231a5b22cca1686abfdfee97340942b26856518` |
| ledger spent | `d9661567956d34b0130910f8666e21937ac2ba44f9b15636892c9e744f09f7cb` |
| isolated snapshot | `ede2f302634e0d27e641c341c8fbf7409fde36b309e96c90626d6d9979d551e2` |
| isolated documents | `dc99af4995300233895c6e6eb642536690e8b877b07867b3f4047981b1b1d9ed` |

### Isolated current files

| File | sha256 |
|---|---|
| `isolated_input/finance/9.txt` | `ede2f302634e0d27e641c341c8fbf7409fde36b309e96c90626d6d9979d551e2` |
| `isolated_input/finance/10.txt` | `5bf7b8105f67c5b5689745595320f7c77c178519be52940b0727481e256384ef` |
| `isolated_input/finance/18.txt` | `71c4bc105b279e6c3df1c7a406a0717e34f330b8264b7c80b1746632833ad99c` |
| `isolated_input/finance/69.txt` | `74472b2d9c0b6047f26f7428a524d1fa52706d951007d533c84f2fc2e7d89643` |
| `isolated_input/finance/70.txt` | `6ef930ad507c598ca553d209e1e296f970361b261d6dbc345c8f653366e7a974` |
| `isolated_input/finance/78.txt` | `1f142b24e64abdb3355703f74a4ff5198038d4469c6767c13feca886dabf2872` |
| `isolated_input/finance/93.txt` | `fbdbe8b86f788f7bf5e952f169f7ed77c5e192f97e1f9899e6effca4e67f1a7e` |

---

## Machine-readable paths

All under `results/docetl_finan_current_snapshot_replay/`:

| Artifact | Path |
|---|---|
| This report | `REPORT.md` |
| Scored report | `docetl_current_snapshot_replay.json` |
| Freeze record | `frozen.json` |
| Call journal | `call_journal.json` |
| Preflight | `preflight.json` |
| Instrumentation fixture | `instrumentation_fixture.json` |
| Rendered prompts | `rendered_prompts.json` |
| Raw completions | `raw_completions.json` |
| Parsed map outputs / tables | `extracted_tables.json` |
| Final SQLite bags | `sqlite_bags.json` |
| Isolated documents | `isolated_input/finance/` |

# Reproduction-Gap Audit and Cross-Query Consistency Replay (Finan)

**Decision:** `prompt/window mismatch prevented sampling isolation`

**Framing:** `diagnostic M4 did not reproduce under a fresh QuWARTS execution`

Do not attribute the 0.227 normalized-value disagreement solely to provider sampling. Prompt-template hashes already differ (`d670861c…` vs `9c47e114…`), and this audit finds **0 / 112** tasks with both an identical prompt and an identical context window.

No Qwen calls. Frozen trees were not modified:

```text
results/docetl_finan_current_snapshot_replay/
results/quwarts_finan_full_window_additive/
results/quwarts_finan_plumbing/
```

Gold was loaded only after `freeze.json` was written.

**Secondary findings** (not selected):

- Cross-query consistency does **not** materially improve the fresh arm (R1 = R3 = R0 = 0.0292; R2 falls to 0.0165).
- Non-missing fresh judgments are mostly not gold-correct (41 / 132 exact). Unanimous repeated keys are the exception (27 / 41).
- Most accepted fills are SQL-inert (86 / 132 leave-one-out bags unchanged).

---

## 1. Prompt and context audit

Aligned 112 QuWARTS tasks to the first attributed DocETL primary call per `(query_id, document_id)`. Ten DocETL primaries are missing (`finan_agg20:q3` docs 70/78/93; all seven of `finan_agg20:q14`).

| Class | Count |
|---|---:|
| Byte-identical prompts | **0** |
| Semantically identical, byte-different | **0** |
| Different prompts | **112** |
| Byte-identical document windows | 15 |
| Identical prompt **and** window | **0** |

Window token overlap (Qwen tokenizer, 102 comparable pairs):

| | Jaccard | Tokens only in DocETL | Tokens only in QuWARTS |
|---|---:|---:|---:|
| mean | 0.766 | 2,101 | 9.2 |
| p25 | 0.785 | 14 | 0 |
| median | 0.850 | 374 | 0 |
| p75 | 0.956 | 626 | 2 |
| max | 1.000 | 12,463 | 67 |

Causes (a task may contribute to several):

| Cause | Tasks |
|---|---:|
| System message (`send_output` persona vs `Return one JSON object.`) | 102 |
| JSON completion vs DocETL tool schema | 102 |
| Model identifier (`openrouter/…` vs `qwen/…`) | 102 |
| Temperature / completion cap (`None`/`None` vs `0.1`/`400`) | 102 |
| Document window | 87 |
| User wrapper (field list, SQL, or missing-value prose) | 30 |
| DocETL primary missing | 10 |

Field names and order match the AST-derived schemas whenever both sides exist. Missing-value instructions (`-1` / `""`) appear in both user templates. Neither user prompt requires exact-span evidence. Both embed the original SQL as the “natural-language” query.

Because no task has an identical prompt and an identical window, **stochastic sampling cannot be isolated from these artifacts**.

### Representative diffs

Wrappers and windows are summarized; full unified diffs are in `diff_*.txt`.

| Pair | Query / doc | Why |
|---|---|---|
| Closest | `finan_multiagg20:q4` / `10` | Same extract_fields user stem; DocETL doc 10 is untruncated. Still differs in system message and tool vs JSON. |
| High disagreement | `finan_multiagg20:q18` / `9` | Window Jaccard 0.13; DocETL mid-cut vs QuWARTS 11,719-token cap. |
| Fresh QuWARTS improved plumbing | `finan_multiagg20:q4` / `9` | Product 0.125 → 0.250. |
| M4 improved, fresh did not | `finan_multiagg20:q11` / `9` | M4 Δ+0.123; fresh product stays 0.000. Same pattern for `finan_agg20:q11` and `finan_agg20:q14`. |

Closest-pair system lines:

```diff
-You are a a helpful assistant, ... send_output ...
+Return one JSON object. Do not explain.
```

---

## 2. Exact-message adapter (not executed)

The adapter rebuilds DocETL primary messages from `query AST + extraction schema + document` using the recovered `extract_fields` template, the instrumented system prompt, Finan attribute numerics, and DocETL `truncate_messages`. It does not copy stored rendered prompts as runtime inputs. No API call was made.

Tests compare generated `(system, user)` to stored primary messages after dropping transport metadata.

| Check | Result |
|---|---|
| Exact matches | **102 / 112** |
| Stored primaries available | 102 |
| Schema mismatches | 0 |
| Context-window mismatches | 0 |
| Parameter mismatches | 0 |
| Missing stored primaries | 10 |
| Gate 112/112 | **fail** |

Every stored primary matched exactly, including the live over-truncated user strings. The gate fails only because `q3`/`q14` never produced the last ten stored messages. The adapter is **not** claimed equivalent to a complete 112-call DocETL run.

---

## 3. Canonical repeated-judgment inventory

Keys are `(document_id, base_attribute)` from the frozen fresh journal. Sentinels are not candidates.

| Class | Keys |
|---|---:|
| Singleton | 14 |
| Repeated | 84 |
| Unanimous repeated | 16 |
| Conflicting repeated | 20 |
| Majority-resolved | 28 |
| Missing-only | 34 |

Sixteen unanimous keys exist. Twenty repeated keys conflict. Overlay values for the same key often already agree when only one query wrote a non-NULL fill.

---

## 4. Zero-token replays

Rules were frozen in `freeze.json` before gold.

| Replay | 16-query product | 15-query product | Fills | Shared | Abstained | Empty bags |
|---|---:|---:|---:|---:|---:|---|
| Plumbing | 0.0158 | — | 0 | 0 | 0 | — |
| **R0** local fresh | **0.0292** | 0.0312 | 73 | 0 | 0 | q11, q17 |
| R1 shared unanimous | 0.0292 | 0.0312 | 79 | 29 | 0 | q11, q17 |
| R2 conflict abstention | 0.0165 | 0.0176 | 52 | 29 | 63 | q11, q17, q8 |
| R3 shared strict majority | 0.0292 | 0.0312 | 81 | 45 | 0 | q11, q17 |
| Frozen DocETL | 0.084 | — | — | — | — | — |
| Diagnostic M4 | 0.0904 | — | 57 | — | — | — |

R0 reproduces the frozen fresh bags (`1fd65017…`) and the frozen product **0.029229**.

R1 writes six extra NULL fills and does not change official bags. R3 changes bag bytes (`8d85342a…`) without changing any per-query product. R2 removes the score lift on `finan_multiagg20:q4` (0.250 → 0.125) and `finan_filter20:q8` (0.079 → 0.000).

Isolation failures: **0**. All overlays keep 100 rows and the plumbing identity checksum. Plumbing / replay / fresh checksums are unchanged.

### Per-query products

| Query | Plumbing | R0 | R1 | R2 | R3 |
|---|---:|---:|---:|---:|---:|
| finan_multiagg20:q4 | 0.1250 | 0.2500 | 0.2500 | 0.1250 | 0.2500 |
| finan_groupby20:q14 | 0.1235 | 0.1340 | 0.1340 | 0.1340 | 0.1340 |
| finan_filter20:q8 | 0.0000 | 0.0794 | 0.0794 | 0.0000 | 0.0794 |
| finan_multiagg20:q18 | 0.0043 | 0.0043 | 0.0043 | 0.0043 | 0.0043 |
| all other queries | 0 | 0 | 0 | 0 | 0 |

---

## 5. SQL-effect waterfall

73 materialized R0 fills plus accepted-but-blocked cells were traced gold-free through bag change, then labeled after freeze.

| Earliest terminal reason | Count |
|---|---:|
| not written (blocked overwrite or value did not stick) | 108 |
| official bag changed | 15 |
| bag changed outside scored cells | 13 |
| branch unchanged | 6 |
| blocked by another missing conjunct | 2 |
| correct and score-improving | 2 |
| group unchanged | 1 |

Leave-one-out: 46 fills change some official bag; 86 do not. Only two bag-changing fills are credited as score-improving after gold.

---

## 6. Post-freeze accuracy

Gold labels were not used to choose R0–R3.

| Slice | n | exact / normalized | numeric tol |
|---|---:|---:|---:|
| Unanimous repeated judgments | 41 | 27 | 35 |
| Majority / other repeated | 25 | 7 | 9 |
| Conflicting judgments | 63 | 6 | 12 |
| Singleton judgments | 3 | 1 | 3 |
| Fills that changed a bag | 46 | 11 | 17 |
| Fills that did not change a bag | 86 | 30 | 42 |

Unanimous repeated keys are mostly right. Conflicting keys are mostly wrong. Sharing them cannot close the DocETL gap, and abstaining them (R2) erases the only fresh-arm lifts.

---

## 7. Decision

Earliest causal blocker: prompt and context are not equal, so the 0.227 value disagreement is not a sampling measurement.

```text
prompt/window mismatch prevented sampling isolation
```

A later exact-message adapter arm would still have to execute new Qwen calls. This task did not.

---

## Integrity

| Artifact | sha256 |
|---|---|
| Plumbing database | `ad91c2554f32510cb378737009e6479cfcb71299f245c7fe766722057b2b2a3d` |
| Replay `frozen.json` | `2c362e9e73e0020cbf0f42289a7ca814f0f675d016be8e025c07910345b7638f` |
| Fresh `frozen.json` | `4b4e6b100a611c69eebcbbe9452c2da99767d474a3137c2332abe0839992384d` |
| Fresh θ100 journal | `13d7ef4b4f0f145b9b9fc6c598fd980a9915c38d1246f7bdfa63ff0e47ddac1c` |
| Replay call journal | `2c6695412daa8a8e62933ef3012b51b298a1fd394a010de28978c07fc6dae4c5` |
| Canonical inventory | `59fc3c2f3b29ea9ffc8a73b47c230c302905c90e29a0256f11bf661479c5a25d` |
| Replay specifications | `a9ecadc4bbfec1c95b68b8539357347e694c43755ffa67485149ae66eb3e09f9` |
| R0 bags | `1fd650179dc397c7637a938679dea6ecfe2378b8636c2d62b87d0aefab78e2aa` |
| R1 bags | `1fd650179dc397c7637a938679dea6ecfe2378b8636c2d62b87d0aefab78e2aa` |
| R2 bags | `2fb9028835fe90ac89d6d7d8864d43bf769297292e13665eca583afdff756620` |
| R3 bags | `8d85342af0921e9374ce0dfbd7d78580ac095a1544668eb68bf0a47fd70ce43d` |

Runner: `systems/WDIRS/quwarts/eval/finan_reproduction_gap_audit.py`  
Adapter: `systems/WDIRS/quwarts/core/docetl_exact_message/`  
Output: `results/finan_reproduction_gap_audit/`

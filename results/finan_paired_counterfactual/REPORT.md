# Budget-Feasible Two-Sample Counterfactual (Finan)

**Decision:** `agreement improves stability but not enough to beat DocETL`

No Qwen calls. Source trees were not modified:

```text
results/docetl_finan_current_snapshot_replay/
results/quwarts_finan_exact_message_additive/
results/quwarts_finan_plumbing/
```

Gold was loaded only after `freeze.json`. A fresh paired arm was not launched.

---

## 1. Eligibility

Pair-eligible only if all seven documents have one byte-identical primary in both samples. Retries and non-identical requests are excluded.

**Eligible (14):**

```text
finan_multiagg20:q4
finan_filter20:q9
finan_filter20:q7
finan_multiagg20:q11
finan_multiagg20:q18
finan_agg20:q4
finan_groupby20:q14
finan_agg20:q11
finan_multiagg20:q9
finan_agg20:q13
finan_agg20:q17
finan_filter20:q8
finan_filter20:q11
finan_filter20:q15
```

**Ineligible (2):**

| Query | Why |
|---|---|
| `finan_agg20:q3` | Sample A missing docs 70, 78, 93 |
| `finan_agg20:q14` | Sample A missing all seven; Sample B missing doc 93 |

Every scheduled program has 14 accounted primary charges. No missing costs.

---

## 2. Cost schedule (gold-free)

Paired-program cost = sum over seven documents of (A usage + B usage). Schedule: ascending cost, then query ID.

| θ | Programs | Spend | Unused |
|---|---:|---:|---:|
| 25 (`345,457`) | 2 | 344,810 | 647 |
| 100 (`1,381,827`) | 8 | 1,380,664 | 1,163 |

θ25 is the exact prefix of θ100.

θ25: `finan_agg20:q4`, `finan_agg20:q11`

θ100 adds: `finan_groupby20:q14`, `finan_filter20:q7`, `finan_filter20:q15`, `finan_filter20:q9`, `finan_agg20:q13`, `finan_agg20:q17`

Six eligible programs do not fit, including the two largest A1-lifting queries (`finan_multiagg20:q4`, `finan_multiagg20:q11`).

---

## 3. Pair classifications (14 eligible queries)

| Class | Cells |
|---|---:|
| Equal non-missing | 122 |
| Both missing | 65 |
| Conflicting non-missing | 42 |
| A only | 11 |
| B only | 12 |

---

## 4. Scores

| System | 16-query product | 15-query product |
|---|---:|---:|
| Plumbing | 0.0158 | — |
| P0 agreement-only θ100 | **0.0206** | 0.0220 |
| P1 one-sided | 0.0206 | 0.0220 |
| P2 Sample A only | 0.0206 | 0.0220 |
| P3 Sample B only | 0.0206 | 0.0220 |
| Fresh exact-message A1 | 0.0440 | — |
| Current-snapshot native replay | 0.0534 | — |
| Frozen DocETL | 0.084 | — |
| Diagnostic M4 | 0.0904 | — |
| Either-sample oracle (same schedule) | 0.0158 | 0.0169 |
| Perfect-label paired ceiling | 0.0298 | 0.0318 |

θ25 P0 is plumbing (0.0158): the two cheapest programs do not move the product.

θ100 lift is entirely `finan_groupby20:q14` (0.1235 → 0.2010). P1–P3 match P0 on every query product, so extra one-sided or single-sample fills on this schedule are SQL-inert for the scored metric.

| Policy | Fills | Blocked overwrites |
|---|---:|---:|
| P0 | 23 | 28 |
| P1 | 29 | 34 |
| P2 | 36 | 39 |
| P3 | 36 | 37 |

Empty official bags (plumbing-empty queries plus unscheduled empties): `finan_multiagg20:q11`, `finan_filter20:q8`, `finan_filter20:q11`, `finan_agg20:q3`.

---

## 5. Post-freeze accuracy (scheduled cells only)

| Slice | n | exact |
|---|---:|---:|
| Equal non-missing | 51 | 18 |
| A only | 7 | 1 |
| B only | 5 | 2 |
| Conflicting A | 17 | 1 |
| Conflicting B | 17 | 1 |
| P0 fills on bag-changing queries | 43 | 15 |
| P0 fills on SQL-inert queries | 8 | 3 |

Agreement is more often correct than one-sided or conflicting values, but not correct enough—and not scheduled onto enough high-leverage queries—to beat 0.084. Even the perfect-label ceiling on this cheapest-first schedule is only **0.0298**.

---

## 6. Decision

Eight complete paired programs fit the budget, so the blocker is not “too few queries.” Official P0 is **0.0206 < 0.084**.

```text
agreement improves stability but not enough to beat DocETL
```

Do not launch a fresh paired arm from this counterfactual.

---

## Integrity

All pre-score invariants passed. Isolation failures: none.

| Object | sha256 |
|---|---|
| Plumbing | `ad91c2554f32510cb378737009e6479cfcb71299f245c7fe766722057b2b2a3d` |
| Replay frozen | `2c362e9e73e0020cbf0f42289a7ca814f0f675d016be8e025c07910345b7638f` |
| Exact-message frozen | `2ca732b10253cc8d4fc383bf65935b7360635bc77cfd38672b53ff63532272e4` |
| Inventory | `8b81f8d0aa232b8de5133d3f2e8998aecfaf2f817b1c72ad9c26a96bdc899708` |
| Program costs | `16166968a15440d9f359ddd8e525681b3e4c991f1d5544a702458e9ad35fffb3` |
| Schedule θ25 | `e391f77d3f75ecfe5d6f29675a96cc67e3efcc4cf24781b268398e88484730d3` |
| Schedule θ100 | `04fdc8b2ae4f28740981a55011e41b59eb2cd10e04b15b7593bd6def63a7742b` |
| Parsed pairs | `32bbf83fabf82c5fbb96eff2eaa1d908695754a9d4979bacbcb2b616146716f3` |
| P0 bags | `3c7b8508185c32f4fca83c618bd76c90e22f80f6e2a25e90c7725f8639ff651b` |

Runner: `systems/WDIRS/quwarts/eval/finan_paired_counterfactual.py`  
Output: `results/finan_paired_counterfactual/`

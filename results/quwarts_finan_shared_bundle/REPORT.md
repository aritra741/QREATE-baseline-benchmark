# Shared-Bundle Full-Window QuWARTS Arm (Finan)

**Decision:** `bundle extraction reduces per-field quality`

Gold was loaded only after `frozen.json`. Bundles, ranking, input cap, acceptance, and materialization were not changed after scoring. Plumbing, exact-message, and replay trees were not modified.

---

## 1. Comparison

| System | 16-query product |
| --- | ---: |
| Plumbing | 0.0158 |
| Shared-bundle θ25 | 0.0197 |
| **Shared-bundle θ100** | **0.0411** |
| Fresh exact-message per-query A1 | 0.0440 |
| Current-snapshot native replay | 0.0534 |
| Frozen DocETL | 0.084 |
| Diagnostic M4 | 0.0904 |

15-query count-only product at θ100: **0.0351**.

The arm is valid. It covers 17 complete entities instead of seven per-query documents, but accepted values are mostly wrong (**25/79** exact, **31.6%**) and the product stays below both exact-message A1 and DocETL.

---

## 2. Shared attribute workload

The 16-query AST union is 14 base attributes. SELECT aliases are excluded.

| Attribute | Type | Occurrences | Queries | NULL rows | Impact unit |
| --- | --- | ---: | ---: | ---: | ---: |
| auditor | TEXT | 28 | 4 | 59 | 112 |
| principal_activities | TEXT | 22 | 4 | 53 | 88 |
| exchange_code | TEXT | 21 | 3 | 87 | 63 |
| net_profit_or_loss | REAL | 7 | 4 | 82 | 28 |
| revenue | REAL | 7 | 4 | 84 | 28 |
| major_equity_changes | TEXT | 8 | 3 | 93 | 24 |
| remuneration_policy | TEXT | 7 | 3 | 89 | 21 |
| cash_reserves | REAL | 5 | 3 | 88 | 15 |
| total_debt | REAL | 5 | 3 | 96 | 15 |
| business_segments_num | REAL | 4 | 2 | 83 | 8 |
| earnings_per_share | REAL | 4 | 2 | 85 | 8 |
| net_assets | REAL | 3 | 2 | 100 | 6 |
| dividend_per_share | REAL | 2 | 1 | 88 | 2 |
| the_highest_ownership_stake | REAL | 2 | 1 | 95 | 2 |

---

## 3. Bundles

Co-occurrence edges are in `cooccurrence_graph.json`. Partition (max 3, descending occurrence then name, max affinity, then smaller bundle, then lexical signature):

1. `auditor+exchange_code+major_equity_changes`
2. `business_segments_num+principal_activities+total_debt`
3. `cash_reserves+net_profit_or_loss+revenue`
4. `dividend_per_share`
5. `earnings_per_share+remuneration_policy`
6. `net_assets`
7. `the_highest_ownership_stake`

---

## 4. Tasks, packages, schedule

| Inventory | Count |
| --- | ---: |
| Potential tasks | 674 |
| Potential packages | 100 |
| Scheduled packages θ25 | 4 |
| Scheduled packages θ100 | 17 |
| Executed packages θ25 / θ100 | 4 / 17 |
| Documents covered θ100 | 17 |
| Calls | 115 |

θ25 documents: `10`, `5`, `83`, `12`

θ100 adds: `55`, `3`, `6`, `15`, `16`, `19`, `34`, `53`, `73`, `75`, `76`, `90`, `100`

θ25 is an exact execution prefix of θ100.

| Checkpoint | Reserved | Actual spend | Unused |
| --- | ---: | ---: | ---: |
| θ25 (`345,457`) | 305,308 | 304,741 | 40,716 |
| θ100 (`1,381,827`) | 1,373,741 | 1,371,376 | 10,451 |

---

## 5. Router

Derived before calls from model context `32,768`, exact-message max completion `78` + safety `64` → reservation **142**, ledger margin `2,048`, max instruction/tool tokens `810`:

```text
input_cap = 12,000
document_room = 11,190
```

Whole-document tasks: **6**. Mid-cut tasks: **668**. After-truncation tokens: min 8,074 / mean 11,966 / max 12,000.

---

## 6. Acceptance and shared materialization

| Stat | θ100 |
| --- | ---: |
| Accepted fills | 79 |
| Blocked overwrites | 0 |
| Missing markers | 151 |
| Typed rejects | 0 |
| Malformed calls | 0 |
| Queries whose bags changed | 8 |
| Empty official bags | 5 |

Accepted by attribute: exchange_code 16, auditor 15, major_equity_changes 15, business_segments_num 9, revenue 8, principal_activities 5, total_debt 5, net_profit_or_loss 2, earnings_per_share 2, remuneration_policy 1, the_highest_ownership_stake 1. `cash_reserves`, `dividend_per_share`, and `net_assets` produced no accepted values.

One accepted entity–attribute value is visible to every referencing query. SQL and signatures were unchanged.

---

## 7. Per-query products (θ100)

Material lifts vs plumbing:

| Query | Plumbing | Shared-bundle | Δ |
| --- | ---: | ---: | ---: |
| `finan_groupby20:q14` | 0.1235 | 0.2679 | +0.1445 |
| `finan_agg20:q13` | 0.0000 | 0.1299 | +0.1299 |
| `finan_agg20:q14` | 0.0000 | 0.1299 | +0.1299 |

All other queries are score-inert. Leave-one-out score contribution is concentrated on document `55` and attributes `principal_activities`, `business_segments_num`, `auditor`, and `exchange_code`.

---

## 8. Post-freeze accuracy

| Slice | n | correct |
| --- | ---: | ---: |
| Exact / normalized | 79 | 25 |
| Numeric tolerance | 79 | 25 |
| Predicate-truth | 72 | 43 |
| Group / CASE attributes | 63 | 23 |
| SQL-visible fills | 78 | — |
| Fills on score-changing queries | 47 | — |

Per-attribute exact: exchange_code 12/16; major_equity_changes 5/15; business_segments_num 3/9; principal_activities 2/5; auditor **0/15**; revenue **0/8**; total_debt **0/5**.

---

## 9. Decision

Seventeen complete entity packages fit the budget, so sharing does convert saved per-query calls into more entities. Official product is **0.0411 < 0.0440** and **< 0.084**, and accepted fields are mostly incorrect.

```text
bundle extraction reduces per-field quality
```

---

## Integrity

All pre-score gates passed. Isolation failures: none. Prior artifacts unchanged.

| Object | sha256 |
| --- | --- |
| Plumbing | `ad91c2554f32510cb378737009e6479cfcb71299f245c7fe766722057b2b2a3d` |
| Exact-message frozen | `2ca732b10253cc8d4fc383bf65935b7360635bc77cfd38672b53ff63532272e4` |
| Replay frozen | `2c362e9e73e0020cbf0f42289a7ca814f0f675d016be8e025c07910345b7638f` |
| Inventory | `e3510d8ac5f178bbf970d9c13dade9b13027045772885333cce91bb9fec0cdcb` |
| Graph | `747f9542025182f062c2b936c3bd3bb098be84150caa4339aca55c7d26d755d0` |
| Bundles | `4134fe1ec452025282dee650551e5e61ca82689005d187f496f2823366b7861c` |
| Schedule θ25 | `887ac271bec5f314eb2f8975261d89acbc946f75c0abd4de72af540acef1c8ac` |
| Schedule θ100 | `a4facfd18580f9a4fb3616164ffb0d33fd441dd17a3b119dd0dd649e46720ad2` |
| Rendered prompts | `001a82cf3d76f99c63fb7528216ed51f9b0bff8df30f6d0e4df57c24eaf1236b` |

Runner: `systems/WDIRS/quwarts/eval/finan_shared_bundle_arm.py`  
Output: `results/quwarts_finan_shared_bundle/`

# Legal shared-database candidate reachability

No frozen artifact was modified. No model arm was launched. Bidirectional-substring `gold_match` did not evaluate search moves. Every scored state is one shared materializable database: exactly one `KEEP_PLUMBING` or frozen candidate ID per NULL cell, the same assignment for all 16 queries, official overlay NULL-only writes, values taken from frozen candidate IDs, and `official_sql` bags.

## Question

Does any single globally consistent database formed only by retaining plumbing or selecting frozen candidate IDs beat Legal DocETL product 0.1235?

Yes. Independent rebuild from plumbing plus the assignment manifest scores **0.21234293187418188**.

| Source | Product |
| --- | ---: |
| Best feasible channel-cohort search (prior) | 0.0927 |
| Legal DocETL | 0.1235 |
| Query-local relaxed upper (prior; not shared) | 0.2251 |
| **Best shared frozen-ID database (this search)** | **0.2123** |

The cohort search was too coarse. The query-local upper is too permissive because it allows different assignments per query. This search closes that gap with one shared assignment.

## Independent rebuild

The winning assignment was reconstructed from frozen candidate IDs only. Values were looked up in `results/quwarts_legal_multichannel_candidates/candidate_inventory.json` and written onto a fresh copy of plumbing. Official bags matched the checkpoint byte-for-byte.

| Check | Result |
| --- | --- |
| Unknown candidate IDs | 0 |
| Manifest value ≠ frozen candidate value | 0 |
| Non-NULL incumbent overwrites | 0 |
| Rows | 570 |
| Official bags match checkpoint | yes |
| Rebuild product = incremental product | yes |
| Mean structure F2 | 0.6102 |
| Mean cell F1@0.20 | 0.2548 |
| Product | 0.21234293187418188 |
| Changed cells | 1351 |
| Assignment hash | `f62251bdeec8571f79a35df11e657e1a886404bfc4437584b06494c1efc6ffdb` |
| Manifest SHA-256 | `7a382af89b5e614079f6c26201c526b47487fe51bb073671d46309db6a8ce6e3` |
| Bag SHA-256 | `b08fd3452a87117cfb1d41abcbf84c0117ac9a9fd2d1b788284ca4fa946de61d` |
| Database SHA-256 | `a52e3c764f5506a5f3d82a77a4e161e8a34b73667b36872968a4a015c835d46c` |

Checkpoint files: `results/quwarts_legal_shared_reachability/best/{assignment_manifest.json,fills.json,bags.json,shared.db,checkpoint.json}`.

## Trajectory

| Phase | Best product | Changed cells | New best states | Evaluations |
| ----- | -----------: | ------------: | --------------: | ----------: |
| A | 0.1873 | 1350 | 80 | 165000 |
| B | 0.2123 | 1351 | 1 | 625 |
| C | 0.2123 | 1351 | 0 | 6389 |
| D | 0.2123 | 1351 | 0 | 7031 |

Seed list hash (20 Phase-A random-order seeds and 20 anneal seeds): `995090f06e90a197e4af3e88db8a676b8b323eefa84d8cdc100540260d7861d0`.

Phase A single-cell coordinate ascent from plumbing reached 0.0544. Ascent from forced all-expanded climbed `0.0810 → 0.089 → 0.101 → 0.122 → 0.139 → 0.151 → 0.171 → 0.1873` by reverting substring-collision surface spans and writing typed frozen values. Remaining starts were reconstructed from frozen IDs and scored, then Phase B/C/D continued from the Phase A winner. Phase C (beam 128, 3 sweeps) and Phase D (8 of 20 frozen anneal seeds) found no further global improvement. No exact shared CP-SAT/MILP optimum was certified.

## Starting-state products (reconstructed from candidate IDs)

| Start | Product |
| --- | ---: |
| plumbing | 0.0225 |
| forced all-expanded | 0.0810 |
| optional all-expanded | 0.0811 |
| best shared cohort (0.0927 construction) | 0.0927 |
| best forced channel subset `{normalized,workload_label,semantic}` | 0.0920 |
| best optional channel subset `{surface,workload_label}` | 0.0811 |
| replica 1 | 0.0329 |
| replica 2 | 0.0257 |
| replica 3 | 0.0340 |
| replica 4 | 0.0271 |
| replica 5 | 0.0340 |
| surface-only | 0.0368 |
| workload-label-only | 0.0425 |
| all-except-surface | 0.0920 |

These are the reconstructed start databases, not copied result bags.

## Best-state analysis

- Product versus DocETL: **0.2123 > 0.1235**
- Retained plumbing cells: **1627 / 2978**
- Written cells: **1351**
- Exact-gold selections: **890**
- Observationally equivalent selections: **40**
- Incorrect selections that remain because they still raise the shared 16-query product: **421**
- Verdict-related writes: **2** (`verdict:workload_label`). Filter `q9` stays 0.0. The frozen inventory still has **0/208** exact-gold `Approved` verdicts, so verdict candidates do not unlock that query.
- Composed-channel writes: **0**

### Selected candidates by channel

| Channel | Writes |
| --- | ---: |
| surface | 743 |
| workload_label | 548 |
| semantic | 56 |
| normalized | 4 |
| composed | 0 |

### Selected candidates by attribute

| Attribute | Writes |
| --- | ---: |
| legal_basis_num | 321 |
| defendant_current_status | 277 |
| hearing_year | 277 |
| first_judge | 232 |
| plaintiff_current_status | 104 |
| case_number | 84 |
| case_type | 54 |
| verdict | 2 |

Largest attribute/channel cells: `first_judge:surface` 228, `defendant_current_status:workload_label` 202, `legal_basis_num:surface` 192, `hearing_year:surface` 155, `legal_basis_num:workload_label` 126, `hearing_year:workload_label` 113.

### Incorrect selections that still help

These writes are not exact-gold and not observationally equivalent to gold, but they remain in the winning shared assignment because removing them would lower the global mean product. Typical cases:

- `first_judge` surface spans that are not gold `0`/`1` but change COUNT/group support (documents 107, 139, 13, 239).
- `hearing_year` surface years that are the wrong calendar year (documents 464 and 105 write 2001/2003 versus gold 2007) yet move rows into counted year buckets used by other queries.
- Status spans such as document 183 `defendant_current_status` = `Solicitors for the Respondent: Australian Government Solicitor` versus gold `Government`.
- Numeric near-misses such as document 423 `legal_basis_num` = `3.02` versus gold `3`.

The search never copied gold values. Every such write is a frozen candidate ID.

### Per-query products

| Query | Plumbing | Best shared | Delta |
| --- | ---: | ---: | ---: |
| `legal_multiagg20:q4` | 0.0000 | 0.0017 | +0.0017 |
| `legal_filter20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q7` | 0.0000 | 0.5000 | +0.5000 |
| `legal_multiagg20:q11` | 0.0952 | 0.1111 | +0.0159 |
| `legal_multiagg20:q18` | 0.0052 | 0.0962 | +0.0909 |
| `legal_agg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_groupby20:q14` | 0.0588 | 0.3750 | +0.3162 |
| `legal_agg20:q11` | 0.0000 | 0.2500 | +0.2500 |
| `legal_multiagg20:q9` | 0.0000 | 0.0712 | +0.0712 |
| `legal_agg20:q13` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q17` | 0.0000 | 0.2500 | +0.2500 |
| `legal_filter20:q8` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q11` | 0.0000 | 0.7500 | +0.7500 |
| `legal_filter20:q15` | 0.0000 | 0.1923 | +0.1923 |
| `legal_agg20:q3` | 0.2000 | 0.8000 | +0.6000 |
| `legal_agg20:q14` | 0.0000 | 0.0000 | +0.0000 |

Still-zero queries: filter `q9` (verdict `Approved`), agg `q4`, agg `q13`, filter `q8`, agg `q14`. Those zeros are not a certified shared upper bound.

### Multi-cell interactions

Single-cell ascent from forced-all was enough to cross DocETL (0.1873). The only later accepted improving block was Phase B `attribute:hearing_year`: force every `hearing_year` cell with an exact-gold frozen candidate to that candidate. That one shared block raised global product `0.1873 → 0.2123` by lifting `legal_agg20:q3` from 0.4000 to 0.8000 (mean-product +0.0250). Other attribute, query, pair, and entity goldish blocks were evaluated and rejected because they were not globally improving.

Conjunctive two-predicate repairs and Phase C/D combinatorial moves did not beat 0.2123. A state that helped one query while lowering the 16-query mean was never accepted as the winner.

### Distance from frozen selector replicas

Hamming distance on the 2978-cell assignment:

| Replica | Distance |
| --- | ---: |
| replica_1 | 1881 |
| replica_2 | 1875 |
| replica_3 | 1757 |
| replica_4 | 1753 |
| replica_5 | 1808 |

The winning database is far from every frozen selector replica. Those replicas are not near-optimal shared assignments.

## Exact solver

No certified shared optimum and no certified shared upper bound. Unsupported joint constructs include `AVG`, `MAX`, `HAVING`, and shared `first_judge` identity across COUNT and AVG. The 0.2123 figure is a feasible heuristic maximum, not an exact maximum. The prior query-local 0.2251 remains a looser non-shared relaxation, not a shared-assignment bound.

## Decision

A realizable assignment above DocETL was found. The rebuilt shared database is formed only from plumbing plus frozen candidate IDs, uses one assignment for all 16 queries, and scores 0.2123 > 0.1235.

frozen candidate inventory can beat Legal DocETL

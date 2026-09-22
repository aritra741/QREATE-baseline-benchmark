# Query-conditioned expert budget scaling

QuWARTS only beats under optimistic semantic sharing

Stage A replayed frozen DocETL map rows on the Gate 2A experts. No new Qwen call was made. Stage B was not started. θ100 was not run.

The schedule, both routing policies, and the checkpoint prefixes were hashed before any DocETL map row or benchmark gold was read. Schedule hash `ac8c43797d845d270a4a43e3ae694e396d6c6bd12260036def5a643bca01794d`.

## Frozen order

Experts are ranked greedily, without gold or baseline answers:

marginal query coverage × marginal AST-observable coverage × cross-query field reuse × workload occurrence count ÷ exact rendered token cost.

Duplicate observables keep weight `1/(1 + experts already covering them)`. A shared column with no Gate 2A role match scores 0. Query id is the tie-break. Every expert is costed on all 570 rendered documents. A checkpoint takes the longest prefix whose full experts fit; the next expert is not started.

Only the first two experts have a positive score. After they cover the shared presence observables, later experts have zero marginal query coverage or zero cross-query reuse, so they follow query-id order.

| Rank | Expert | Score | Tokens |
| --- | --- | ---: | ---: |
| 1 | legal_multiagg20:q18 | 1.162e-3 | 3,690,476 |
| 2 | legal_multiagg20:q4 | 3.162e-5 | 3,653,291 |
| 3 | legal_agg20:q11 | 0 | 3,609,104 |
| 4 | legal_agg20:q13 | 0 | 3,615,936 |
| 5 | legal_agg20:q14 | 0 | 3,606,960 |
| 6 | legal_agg20:q17 | 0 | 3,623,848 |
| 7 | legal_agg20:q3 | 0 | 3,593,934 |
| 8 | legal_agg20:q4 | 0 | 3,591,092 |
| 9 | legal_filter20:q11 | 0 | 3,632,960 |
| 10 | legal_filter20:q15 | 0 | 3,634,654 |
| 11 | legal_filter20:q7 | 0 | 3,632,390 |
| 12 | legal_filter20:q8 | 0 | 3,617,060 |
| 13 | legal_filter20:q9 | 0 | 3,622,144 |
| 14 | legal_groupby20:q14 | 0 | 3,629,432 |
| 15 | legal_multiagg20:q11 | 0 | 3,650,926 |
| 16 | legal_multiagg20:q9 | 0 | 3,669,040 |

θ25 is an exact prefix of θ50, which is an exact prefix of θ75.

| Checkpoint | Budget | Experts completed | Projected tokens | Unused | Role-compatible observables |
| --- | ---: | --- | ---: | ---: | --- |
| θ25 | 12,610,011 | q18, multiagg q4, agg q11 | 10,952,871 | 1,657,140 | 4 presence checks |
| θ50 | 25,220,022 | θ25 plus agg q13, agg q14, agg q17 | 21,799,615 | 3,420,407 | same 4 |
| θ75 | 37,830,032 | θ50 plus agg q3, agg q4, filter q11, filter q15 | 36,252,255 | 1,577,777 | those 4 plus Company, Government, and the defendant IN-list |

The four presence observables are `case_number IS NOT NULL`, `first_judge IS NOT NULL`, and nonempty plaintiff and defendant status. θ75 adds three filters. Case bands, statute bands, verdict families, averages, `hearing_year`, and `GROUP BY first_judge` stay uncovered under conservative routing. Uncovered queries at θ75 are filter q9, filter q7, multiagg q11, groupby q14, multiagg q9, and filter q8.

Stored DocETL maps contain 550 document ids, and `legal_agg20:q14` has 549. Twenty documents are absent from every map (`16`, `44`, `110`, `118`, `119`, `166`, `206`, `257`, `258`, `284`, `298`, `315`, `325`, `344`, `388`, `447`, `506`, `520`, `522`, `558`). Those rows stay on plumbing. Duplicate doc ids in a map keep the last row. The budget prefix is still whole experts: no expert was cut mid-document to fit a checkpoint.

## Routing

Conservative: an expert fills its own query from its map columns. Another query receives a sidecar only for a Gate 2A role-compatible observable. Base columns are not overwritten for that other query.

Optimistic, diagnostic only: an earlier expert’s value may fill the same base attribute and output type on a query whose own expert has not run, including roles Gate 2A rejected. This policy is not a QuWARTS result.

## Diagnostic products

DocETL product is 0.12350932750098194. Plumbing product is 0.022455905439098717. No query failed to execute.

| Budget | Tokens | Experts | Policy | Direct queries | Reused queries | F2 | F1@0.20 | Product |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| θ25 | 10,952,871 | 3 | conservative | 3 | 7 | 0.3248394185 | 0.1026515152 | 0.09043195648165 |
| θ25 | 10,952,871 | 3 | optimistic | 3 | 11 | 0.4513858704 | 0.1026515152 | 0.09043195648165 |
| θ50 | 21,799,615 | 6 | conservative | 6 | 5 | 0.4140959545 | 0.1026515152 | 0.09043195648165 |
| θ50 | 21,799,615 | 6 | optimistic | 6 | 9 | 0.6888524480 | 0.1390179367 | 0.13250247787203 |
| θ75 | 36,252,255 | 10 | conservative | 10 | 4 | 0.5390959545 | 0.1026515152 | 0.09043195648165 |
| θ75 | 36,252,255 | 10 | optimistic | 10 | 6 | 0.7067095908 | 0.1390179367 | 0.13250247787203 |

Conservative cell F1 stays at 0.1026515152 from θ25 through θ75. Extra experts raise structure F2 on queries whose cell F1 is 0, so the product does not move. It stays below DocETL.

Optimistic θ25 also stays at 0.09043195648165. Optimistic θ50 and θ75 reach 0.13250247787203, which is above DocETL by 0.00899315037104463. The product does not rise further from θ50 to θ75.

The optimistic margin is reused structure, not a new direct expert. At θ50 the reused query `legal_groupby20:q14` has product 0.625, against 0.05882352941176471 under conservative presence-only reuse. Reused `legal_multiagg20:q9` has product 0.10695187165775404. Both use shared `case_number`, `case_type`, or `verdict` values for CASE and numeric roles that Gate 2A marked incompatible. Direct products that are nonzero under both policies are `legal_multiagg20:q18` at 0.18808777429467086 and `legal_agg20:q11` at 1.0. `legal_agg20:q3` stays at 0.20000000000000004 whether or not its expert has run.

Empty conservative bags: filter q9, filter q8, filter q11, and filter q15 at θ25 and θ50; filter q9 and filter q8 at θ75. Optimistic θ25 leaves filter q8 empty. Optimistic θ50 and θ75 have no empty bags.

Per-query products at the two decision checkpoints. Exact values are in `diagnostic_scores.json`.

| Query | Conservative θ75 | Optimistic θ50 |
| --- | ---: | ---: |
| legal_multiagg20:q4 | 0 | 0 |
| legal_filter20:q9 | 0 | 0 |
| legal_filter20:q7 | 0 | 0 |
| legal_multiagg20:q11 | 0 | 0 |
| legal_multiagg20:q18 | 0.18808777429467086 | 0.18808777429467086 |
| legal_agg20:q4 | 0 | 0 |
| legal_groupby20:q14 | 0.05882352941176471 | 0.625 |
| legal_agg20:q11 | 1 | 1 |
| legal_multiagg20:q9 | 0 | 0.10695187165775404 |
| legal_agg20:q13 | 0 | 0 |
| legal_agg20:q17 | 0 | 0 |
| legal_filter20:q8 | 0 | 0 |
| legal_filter20:q11 | 0 | 0 |
| legal_filter20:q15 | 0 | 0 |
| legal_agg20:q3 | 0.20000000000000004 | 0.20000000000000004 |
| legal_agg20:q14 | 0 | 0 |

## Stage B

The live-run gate requires a conservative θ50 or θ75 product above 0.12350932750098194. Conservative products are 0.09043195648165 at both checkpoints. The live arm would depend on the optimistic attribute-sharing policy, which was not verified as role-compatible. Stage B was not launched. The expert order and routing were not changed after scoring.

QuWARTS only beats under optimistic semantic sharing

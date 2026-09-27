# Why 9 of the 16 held-out Legal queries score 0 for every system

This is an audit only: it reads gold, after the freeze. Nothing here feeds the system. The source is `zero_diagnosis.json`, produced by `quwarts/eval/router_zero_diagnosis.py`.

The zero queries are agg20:q4, q13, q14 and q17; filter20:q7, q8, q11 and q15; and multiagg20:q4. Every one of them is killed by at least one of four columns. Accuracy below is per document, for QuWARTS (the per-attribute run), on documents where gold is non-null.

| Column | QW acc | Fair DocETL acc | What goes wrong | Zero queries it hits |
|---|---:|---:|---|---|
| `case_number` | 0.11 | 0.02 | This is a count of distinct precedents cited, with gold typically 1–7. The meaning is generated correctly from the SQL aliases (`avg_precedents`, `many_precedents`), but the model answers the "if absent: 0" fallback for most documents. DocETL answers -1 (NULL) for 97% of documents. | q13, filter q7, filter q8, multiagg q4 |
| `legal_basis_num` | 0.19 | 0.07 | This is a count of distinct statutes cited. QuWARTS over-counts (mode 4 vs gold 1–2), probably counting sections rather than distinct Acts. DocETL often gives NULL or 0. | q14, q17, filter q11 |
| `first_judge` | 0.47 | 0.00 | Gold is split 53/47 between 0 and 1 ("whether it was the first judgment"). Both systems answer 1 for about 99% of documents. The generated meaning ("1 indicates the case was heard by a judge") is tautological. | q4, q14, multiagg q4 |
| `defendant_current_status` | 0.50 | 0.04 | QuWARTS gives NULL for 37% of documents where gold says Government/Company/Organization; DocETL gives NULL for 95%. The plain variant (no description) won the per-attribute choice because consistent NULLs look consistent. | q17, filter q11, filter q15 |

## Why one wrong column zeroes a query
The product is structure F2 × cell F1@0.20. When a GROUP BY key is degenerate (first_judge), the groups vanish. When an aggregated count is biased (AVG or MAX of case_number or legal_basis_num), every cell misses the 20% band. Either failure alone gives 0, however good the other columns are.

## Generic causes, and gold-free signals the system could use
1. **Count attributes are computed, not stated.** "Number of distinct X cited" appears nowhere in the text. A 7B model asked for the number in one shot defaults to 0 or -1, or over-counts.
   - Signal: the column is numeric, aggregated in the SQL, and its generated meaning is "number of …".
   - Mechanism: enumerate the X items, then dedupe and count them in code.
2. **Degenerate reads of discriminating columns.** The workload GROUPs BY first_judge and compares it with both 0 and 1, which implies it is expected to split the corpus. A read that is about 99% one value contradicts the workload.
   - Signal: the value distribution on the sample used for the consistency check.
   - Mechanism: regenerate the meaning with competing interpretations, and keep one whose reads are non-degenerate.
3. **The consistency choice rewards abstention.** Agreement between repeated reads counts NULL = NULL as agreement.
   - Mechanism: score consistency on non-null agreement plus coverage, with the coverage expectation taken from how the SQL uses the column (compared with specific literals means values are expected).

## Contamination note
This diagnosis looked at held-out gold, so any post-fix score on these 16 queries is optimistic. The four columns are also heavily used in the 64 input queries: case_number in 21, legal_basis_num in 26, first_judge in 9, defendant_current_status in 8. The fixes are column-level mechanisms driven by workload signals, not per-query patches. They should be fixed before re-scoring and checked on another corpus.

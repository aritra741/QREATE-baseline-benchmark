# Finan long-document read strategies (development diagnostic, 2026-09-26)

20 filings (length-stratified), 14 workload attributes, Qwen 2.5 7B, no query context.
Scored against gold after all outputs were stored (`report.json`). One of 916
exhaustive chunk calls is missing. Not a frozen result.

| Strategy | Tokens / filing | Cell score, gold non-null (1% tol.) | Coverage | Precision | Agreement with exhaustive |
|---|---:|---:|---:|---:|---:|
| plumbing (stored) | - | 0.04 | 0.17 | 0.23 | 0.14 |
| program (stored official) | ~3.3k amortized | 0.06 | 0.38 | 0.15 | 0.15 |
| window_small (2.9k BM25, 1 call) | 3,563 | 0.17 | 0.46 | 0.37 | 0.35 |
| head (first 10.1k tokens, 1 call) | 10,877 | 0.22 | 0.43 | 0.50 | 0.34 |
| window_1 (10.1k BM25, 1 call) | 10,775 | 0.29 | 0.69 | 0.43 | 0.47 |
| window_attr (3k BM25 per attribute) | 42,063 | 0.26 | 0.65 | 0.40 | 0.44 |
| exhaustive (all 3k chunks, majority) | 167,012 | 0.40 | 0.94 | 0.43 | 1.00 |

Window recall of verbatim gold values (108 cells): head 0.60, window_small 0.44,
window_1 0.80, window_attr 0.81.

Findings:
1. At equal cost, one attribute-targeted window beats the document head (0.29 vs 0.22),
   mostly through recall (0.80 vs 0.60 of gold values visible).
2. Per-attribute windows cost 4x more and do worse than one shared window.
3. Head wins on headline financials (revenue, net assets, total debt) and windows win on
   auditor, EPS and ownership stake: the best read differs by attribute.
4. Agreement with the exhaustive read ranks the strategies almost exactly as gold does
   (only head vs window_small swap, 0.34 vs 0.35), so it is a usable gold-free signal.
5. At theta25 (about 3.5k tokens per filing) only window_small or programs fit;
   window_small has about 3x the program's cell score but sees only 44% of gold values.
6. Even exhaustive reading reaches only 0.40: numeric financials stay below 0.3 for every
   strategy, which points at unit/currency normalization, not at what the model sees.

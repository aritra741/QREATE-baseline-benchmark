# Long documents: chained reads with carried context (2026-09-27)

Before: a document longer than the shared-read window (10,108 Qwen tokens, inherited from
`corpus_probe.context`, not a model limit) was read from its first window only. On Finan that is
about 9% of a median filing (100 filings, median 118k tokens, 14.0M in total; only 1 fits).

Now (`--long chain`, `core/router/chunked.py`): a longer document is read in full as even chunks of at
most 9,808 tokens, in order. Each call returns the fields its chunk states and a note of at most 80
words for the next chunk (entity, period, currency and units, section); the next call gets it before
its text. Chunk answers are combined per field by a rule declared before the runs: nulls and declared
absence values do not vote, multi-valued fields take the union, others the most frequent committed
value with ties to the earliest chunk. Documents that fit the window are read exactly as before (their
reads were reused from the head runs). 14 Finan chunks that the endpoint rejected as too long (tables
of mostly padding, which its length estimate counts by characters) were re-sent with the padding
collapsed.

Documents longer than the window: Med 121 of 297, Finan 99 of 100, Legal 86 of 570, Player 82 of 216,
Art and CSPaper none.

Held-out queries, benchmark protocol (descriptions for both systems), paired with the fair DocETL run
(`protocol_comparison_chain.json`; the head version is `protocol_comparison.json`):

| Corpus | QuWARTS head | QuWARTS chain | DocETL fair | chain − DocETL (95% CI) | Tokens chain / DocETL |
|---|---:|---:|---:|---|---:|
| Med | 0.230 | 0.273 | 0.298 | −0.025 [−0.15, 0.10] | 3.72M / 23.6M |
| Finan | 0.168 | 0.275 | 0.210 | +0.066 [−0.07, 0.21] | 16.19M / 37.4M |
| Legal | 0.197 | 0.199 | 0.135 | +0.063 [−0.03, 0.18] | 4.67M / 72.6M |
| Art | 0.219 | = | 0.232 | −0.013 [−0.08, 0.04] | 2.44M / 22.8M |
| CSPaper | 0.178 | = | 0.059 | +0.119 [0.01, 0.23] | 0.45M / 6.7M |
| Player | 0.609 | 0.586 | 0.254 | +0.333 [0.20, 0.48] | 2.15M / 14.4M |
| Macro | 0.267 | 0.288 | 0.198 | | 29.6M / 177.6M (16.7%) |

All 80 Finan queries: 0.182 → 0.313. Finan cells filled (of 100 filings), head → chain: auditor 33 → 97,
revenue 53 → 91, total_assets 31 → 97, cash_reserves 22 → 95, earnings_per_share 36 → 91.
No corpus is now below DocETL by more than 0.025; the remaining cost gap is Finan (43% of DocETL's
tokens, since the whole filing is now read once).

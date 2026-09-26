# Why the recorded DocETL Finan run kept 7 of 100 filings (2026-09-26)

Reproduced with `systems/DocETL/diagnose_finan_skips.py`: the grid run's exact runner,
prompt, model (`openrouter/qwen/qwen-2.5-7b-instruct`), timeout and retries, one filing
per pipeline, `skip_on_error` forced off. Query `finan_multiagg20:q4`. The frozen
`results/docetl_finan_case80` artifacts were not modified.

## Facts from the recorded run

- The log has 1,600 model calls: DocETL attempted all 100 filings for each of the 16 queries.
- Only 112 calls were counted (the token counter records successful calls only), and every
  query's output has the same 7 rows: filings 9, 10, 18, 69, 70, 78, 93.
- The map runs with `skip_on_error=True`, so a failed call silently drops the filing.

## What the rerun shows

| Filing | Qwen tokens | Result |
|---|---:|---|
| 10 | 7,738 | ok |
| 9 | 907,234 | ok (DocETL truncated it) |
| 1 | 51,784 | 400: "maximum context length is 32768 tokens ... you requested about 41876 tokens"; DocETL had logged "Cutting 9673 tokens from a prompt with 39527 tokens" |
| 23 | 30,250 | 400: "... you requested about 37483 tokens"; DocETL did not truncate |
| 68 | 26,725 | 400 from the routed provider: "The request was rejected as invalid" |

## Cause

DocETL truncates prompts to the model's context using its own token count, which
undercounts Qwen's tokens on these filings (29.9k by DocETL's count was 41.8k by the
endpoint's). Truncated or untruncated prompts that DocETL believes fit therefore exceed the
endpoint's 32,768-token limit, the provider returns HTTP 400, and `skip_on_error=True`
drops the filing without logging it. The failure depends only on the document, which is why
the same filings fail in every query.

## Consequences

- DocETL's Finan score (product 0.0841) and token total (1,381,827) come from 7 filings.
  The theta25 budget derived from that total (345,457) is 25% of a run over 7% of the corpus.
- The same mechanism can drop long documents elsewhere: Legal's recorded outputs have
  550-554 of 570 cases per query, Med's 88-119 rows per table. Not yet checked there.
- A fair baseline needs DocETL's truncation to count with the Qwen tokenizer (or keep a
  safety margin), with failures logged.

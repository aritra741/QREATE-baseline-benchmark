# Fresh Legal query-expert arm, θ50

run invalid

No Qwen call was issued. The frozen timeout-retry reserve does not fit θ50, so the arm stopped in preflight.

Schedule hash `ac8c43797d845d270a4a43e3ae694e396d6c6bd12260036def5a643bca01794d` matches Stage A. The six-expert prefix is unchanged. All 3,420 rendered requests match the Gate 2A specifications: 0 token mismatches, same system prompt, same user template, same SQL, same field order, same tool schema, temperature unset, `max_tokens` unset. Request hashes are in `requests.json`.

## Reservation

DocETL `call_llm` retries a timeout up to `max_retries_per_timeout=2`, so each document can be transmitted 3 times. The scheduling reserve is that policy, plus 256 completion tokens per attempt. Those 256 tokens are not sent as `max_tokens`. Rate-limit and connection retries in the same loop are unbounded and are not given a finite reserve.

| Checkpoint | Prompt tokens | 1 attempt + 256 completion | 3 attempts + 256 completion | Ceiling | Fits under the 3-attempt reserve |
| --- | ---: | ---: | ---: | ---: | --- |
| θ25, first 3 experts | 10,952,871 | 11,390,631 | 34,171,893 | 12,610,011 | no |
| θ50, all 6 experts | 21,799,615 | 22,675,135 | 68,025,405 | 25,220,022 | no |

The 3-attempt θ50 reserve, 68,025,405, is also above θ100 (50,440,043). One transmission of the six experts does fit θ50, with 3,420,407 tokens left. That is 1,000.12 tokens per request. The shortest rendered prompt is 726 tokens and the longest is 33,208, so that slack cannot hold a second transmission of a normal document. A per-request retry allowance that follows the frozen timeout policy therefore does not fit.

Per-expert prompt totals, equal to Gate 2A:

| Expert | Prompt tokens | Min | Max | Truncated documents |
| --- | ---: | ---: | ---: | ---: |
| legal_multiagg20:q18 | 3,690,476 | 874 | 33,208 | 7 |
| legal_multiagg20:q4 | 3,653,291 | 808 | 33,209 | 7 |
| legal_agg20:q11 | 3,609,104 | 730 | 33,181 | 7 |
| legal_agg20:q13 | 3,615,936 | 742 | 33,193 | 7 |
| legal_agg20:q14 | 3,606,960 | 726 | 33,201 | 7 |
| legal_agg20:q17 | 3,623,848 | 756 | 33,191 | 7 |

## Frozen routing, not executed

The same-attribute-sharing manifest and the conservative ablation were hashed before any call. Routing hash `90cf224fa3bac73f4fc28bf6925af06b647b795beee472db21a92f0dbd6ec2db`. Precedence is unchanged: the target query’s own expert, else the earliest scheduled expert that emits the attribute, else plumbing. NULL from a shared expert does not replace an earlier non-NULL value. No database was built, because no expert completed.

Gold, DocETL map rows, and Stage A per-query products were not loaded.

run invalid

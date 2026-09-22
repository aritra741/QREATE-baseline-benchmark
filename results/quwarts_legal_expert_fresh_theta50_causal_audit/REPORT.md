# Fresh Legal θ50 causal audit

Conclusion: `historical completions would restore the win, but fresh semantics do not`

No model call was made. Stage A substitutions and the gold cell study are diagnostic-only.

## Reproduction

- fresh θ25 same-attribute `0.04208752074497511`
- fresh θ50 same-attribute `0.07420320131953051`
- fresh θ50 conservative `0.04208752074497511`
- Stage A θ50 optimistic `0.13250247787202657`
- DocETL `0.12350932750098194`
- schedule `ac8c43797d845d270a4a43e3ae694e396d6c6bd12260036def5a643bca01794d`
- routing `90cf224fa3bac73f4fc28bf6925af06b647b795beee472db21a92f0dbd6ec2db`
- all six experts completed
- θ25 journal is an exact prefix of θ50
- plumbing and frozen databases were unchanged at the end of the audit

The gap is semantic disagreement on calls that both runs completed. It is not the 369 terminal failures, not missing coverage, and not an artifact of SQL after a correct extraction.

`R_fresh_recovery` adds 166 cross-expert cells and does not change the product. Salvage recovers nothing: all 326 malformed responses are empty `send_output` objects. D1 fills 455 terminal-failure cells from Stage A, changes 11 bags, and leaves every per-query product unchanged. D4, the fresh cross-expert ceiling, also stays at 0.07420320131953051. D2 replaces successful fresh values with Stage A values and reaches 0.13250247787202657, above DocETL. The product lift is four queries: `legal_agg20:q11` +0.75, `legal_groupby20:q14` +0.125, `legal_multiagg20:q9` +0.03427745305310287, and `legal_multiagg20:q18` +0.02351097178683384.

## Failure taxonomy

3,420 primary requests: 3,051 successes and 369 terminal failures. Terminal classes are malformed empty tool calls (326) and provider HTTP 400 (43). No terminal failure is a timeout, rate limit, or connection error; those retries that occurred later succeeded. 327 terminals used all three attempts. 185 of the 369 terminals are in the shortest document-length decile, and 43 are in the longest decile.

## Why legal_agg20:q14 has 112 missing documents

112 missing rows are terminal requests, not unissued primaries. 105 are empty send_output objects after the allowed attempts. 7 are provider HTTP 400 responses on the longest truncated documents, which return no tool payload.
Malformed empty calls: 105. Provider errors: 7 on 258.txt, 284.txt, 298.txt, 315.txt, 325.txt, 520.txt, 522.txt.

## Salvage

Rules hash `df6c14542e3dd45347b9bc07779c94ba014b9f3477df4c4e113975b3491e2298`.
Inspected 369 failed responses. Recovered 0 fields and 0 rows.
Every malformed raw response is an empty send_output object. No field can be recovered without inventing a value.

## Comparison

| arm | product | F2 | cell F1@0.20 | diagnostic-only |
| --- | ---: | ---: | ---: | --- |
| fresh θ50 same-attribute | 0.07420320131953051 | 0.6825760209189262 | 0.08044507575757576 | False |
| R_fresh_recovery | 0.07420320131953051 | 0.6825760209189262 | 0.08044507575757576 | False |
| D1 terminal-failure substitution | 0.07420320131953051 | 0.6825760209189262 | 0.08044507575757576 | True |
| D2 successful-call substitution | 0.13250247787202657 | 0.6709953051230941 | 0.1390179367201426 | True |
| D3 full Stage A substitution | 0.13250247787202657 | 0.688852447980237 | 0.1390179367201426 | True |
| D4 fresh coverage ceiling | 0.07420320131953051 | 0.6825760209189262 | 0.08044507575757576 | True |
| Stage A θ50 optimistic | 0.13250247787202657 | 0.688852447980237 | 0.1390179367201426 | True |
| Legal DocETL | 0.12350932750098194 | None | None | False |

## Replay deltas

### R_fresh_recovery

- substituted cells: 166
- affected documents: 48
- SQL-visible substitutions: 59
- queries changed: 7
- empty bags: 0
- product: 0.07420320131953051

### D1_terminal_failure_substitution

- substituted cells: 455
- affected documents: 101
- SQL-visible substitutions: 155
- queries changed: 11
- empty bags: 0
- product: 0.07420320131953051

### D2_successful_call_semantic_substitution

- substituted cells: 9186
- affected documents: 544
- SQL-visible substitutions: 3553
- queries changed: 14
- empty bags: 0
- product: 0.13250247787202657

### D4_fresh_perfect_coverage

- substituted cells: 155
- affected documents: 47
- SQL-visible substitutions: 57
- queries changed: 5
- empty bags: 0
- product: 0.07420320131953051

### D3_full_stage_a_substitution

- substituted cells: 250
- affected documents: 14
- SQL-visible substitutions: 125
- queries changed: 14
- empty bags: 0
- product: 0.13250247787202657

## Agreement on cells both runs completed

- cells: 7511
- exact agreement with raw Stage A values: 1349
- normalized agreement: 3439
- NULL/non-NULL agreement: 4298
- normalized disagreements: 4072
- D2 cells that change an official bag: 3553
- D2 cells that do not change an official bag: 1118

On the 7,511 cells both runs completed, fresh matches the gold document table on 904 cells (0.12035681001198242) and Stage A matches on 1,095 (0.1457861802689389). On the 4,072 normalized disagreements, fresh matches gold on 286 (0.07023575638506876) and Stage A on 477 (0.11714145383104126). Agreed cells match gold on 618 of 3,439 (0.17970340215178832). Cross-expert fresh fills match gold on 1 of 189. Salvage recovered no value. This gold comparison did not choose a replay.

## Stopping rule

The Legal query-expert line stops. No θ75, θ100, replica, vote, or prompt variant is recommended.

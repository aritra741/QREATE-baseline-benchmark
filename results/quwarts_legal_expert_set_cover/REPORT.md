# Gate 2A: query-conditioned expert set cover

no four-expert cover exists

Zero model calls. The 16 Legal map experts were reconstructed from the DocETL map template, the frozen manifest SQL, and `Legal_attributes.json` types. Every expert was rendered on all 570 source documents. DocETL answer tables, extracted values, benchmark gold, and scorer outputs were not read.

## Reconstruction

Each expert is one DocETL map (`extract_fields`) for one of the 16 manifest queries. The model is `openrouter/qwen/qwen-2.5-7b-instruct`. The text supplied as the “natural-language query” is the benchmark SQL. These queries have no separate natural-language descriptions.

The sent task is:

- system prompt: DocETL map persona (`a helpful assistant` on “a collection of unstructured documents”), including the `send_output` instruction
- user template: one legal record, the SQL, a bullet list of base columns, numeric-versus-string guidance, missing-value rules (`-1` for numbers, empty string for text), then the document
- output schema: `number` if `Legal_attributes.json` types the column as int, otherwise `str`
- tool schema: strict `send_output` object, all fields required, `additionalProperties: false`, no enums
- truncation: DocETL middle-cut when the tiktoken `gpt-4o` meter of `json.dumps(message)` exceeds 32,768 − 100 (`litellm.model_cost` for this model). Qwen is not a tiktoken model, so DocETL falls back to `gpt-4o` for the cut
- parameters: temperature unset, `max_tokens` unset, timeout 420s, 2 retries, no gleaning, no resolve

Attribute descriptions (precedent-count, statute-count, hearing-start year, 1/0 `first_judge`, verdict label set) live in `Legal_attributes.json` and are not interpolated into the prompt or the tool schema. `supplied_to_model` is false for every field description. Expert hashes are SHA-256 of that reconstructed specification.

| Query | Hash | Fields |
| --- | --- | --- |
| legal_multiagg20:q4 | `73a8da498313a526784a157d73e80ce86d31458255f30488319557b5486a8f7d` | case_number, first_judge, legal_basis_num, verdict |
| legal_filter20:q9 | `106f3c89e8c5e1f4269415dd146a5853e5941315869a28aa099d530481d43bf4` | plaintiff_current_status, verdict |
| legal_filter20:q7 | `73cef73cd12fafb85a5eb6665222a901c00ee09ab647aa4d4bf9e73a6fb32251` | case_number, hearing_year, verdict |
| legal_multiagg20:q11 | `45a08a7a6e022ba87f00d3baa2e291a2d2c0c0f87a4570769dc6d944757315e5` | case_number, legal_basis_num, verdict |
| legal_multiagg20:q18 | `43ea1f37859ff1fade0b6fd05c18b3137a2a5416ed5506241aab9398fba7d605` | case_number, defendant_current_status, legal_basis_num, plaintiff_current_status |
| legal_agg20:q4 | `6357413ec6cbaa7c8eb2677fb1f18511027b4eda3b97732cbee21bdba7e88ffb` | first_judge |
| legal_groupby20:q14 | `45c234d0737b1828f1a5b291eff199fb9d9920ecd6c7effdbd939f295910fe69` | case_number, case_type |
| legal_agg20:q11 | `a8bef82daf50b668c13b507956922c8967fcbbc8f9a3c7990f8b4bd149b2d039` | plaintiff_current_status |
| legal_multiagg20:q9 | `0ea8a461b70cb581dedd2af363948bd0cde13b647f3a1a153df4101816a1d939` | case_number, case_type, legal_basis_num, verdict |
| legal_agg20:q13 | `d267201be03bd5c7b93795a16242ff30c05ff95e8b9b1bda69985f10e339bdae` | case_number, case_type |
| legal_agg20:q17 | `cc5a52941058d51b3139152ae2759b57ff555643a35be4685fbdd58c601432d3` | defendant_current_status, legal_basis_num |
| legal_filter20:q8 | `4fd3f8d8e3e5ad9c755e09c68dede909b68ea5eb3bc6d38ee84be6ac85069535` | case_number, case_type |
| legal_filter20:q11 | `418442946b216bd2798063083a8e293ecddfddcadc6754508f08dae38937ecef` | case_type, defendant_current_status, legal_basis_num |
| legal_filter20:q15 | `c3794a7997e12213edd87dc72aab24519a1faec05873f98121b59fc4087c1e7f` | defendant_current_status, plaintiff_current_status, verdict |
| legal_agg20:q3 | `86ecd27cf0701b319062d51d7f2a766a98bebc604f9d7d8c640832664174ed0d` | hearing_year |
| legal_agg20:q14 | `87b19aa0377b561fc453ab3fc2621c3ba5bf3a333fe431124c0729bc935047c6` | first_judge, legal_basis_num |

Full templates, tool schemas, and truncation parameters are in `experts.json`.

## Compatibility

Coverage requires the sent schema and the supplied SQL to support the observable’s role. Sharing a base attribute is not enough. The binary matrix and the reason for every cell are in `compatibility.json`.

Nine of the 24 observables have at least one compatible expert:

- presence: `case_number IS NOT NULL`, `first_judge IS NOT NULL`, nonempty plaintiff status, nonempty defendant status
- predicate filters: `verdict = 'Approved'`, `case_type = 'Civil Case'`, `defendant_current_status = 'Government'`, defendant status `IN (...)`, `plaintiff_current_status = 'Company'`

Fifteen observables have no compatible expert. The same rejection applies to every query that names the field:

- `AVG(case_number)`, `MAX(case_number)`, and `AVG(legal_basis_num)`: the tool schema asks for a number, and it does not state precedent-count or statute-count component semantics
- both `hearing_year` range filters and the `hearing_year` group key: the schema names the column and does not distinguish hearing year from judgment, citation, or publication year
- `GROUP BY first_judge`: the sent schema does not request judge identity; the attribute configuration is a 1/0 indicator and is not sent
- six `CASE` group branches (case number bands, case type, defendant status, statute bands, plaintiff status, verdict family) and `verdict = 'Dismissed'` inside `SUM(CASE)`: the tool schema is an unconstrained string and does not distinguish the branch labels

Those 15 remain uncovered if all 16 experts are kept. Exact coverage is impossible at every set size. The minimum number of experts for an exact 24-cover does not exist, so there is no token projection for that minimum.

The nine compatible observables are not themselves a four-expert cover. Six of them are unique to disjoint queries (`Approved` → q9, `Civil Case` → q8, the defendant `IN` list → q15, `Government` → q11, nonempty defendant status → q17 or q18, `first_judge` presence → q4, q14, or multiagg q4). Covering those nine takes six experts.

## Set cover, sizes 1–4

All 2,516 subsets were scored from the rendered token matrix. Ranking did not use benchmark scores: more observables, then fewer tokens, then more same-role reuse, then fewer role conflicts. `subsets.json` has every subset.

| Size | Subsets | Max observables | Tokens at that cover | Cheapest tokens | Cheapest cover |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 16 | 3 | 3,690,476 | 3,591,092 | 1 |
| 2 | 120 | 5 | 7,325,130 | 7,185,026 | 1 |
| 3 | 560 | 6 | 10,873,858 | 10,791,986 | 1 |
| 4 | 1,820 | 7 | 14,464,950 | 14,401,090 | 2 |

Every size-4 subset is above 12,610,011. The cheapest four-expert projection is 14,401,090. Six hundred ninety-six subsets of size 1–3 fit the token cap. The best of those covers 6 observables for 10,873,858 tokens.

Best size-1–4 subset under the ranking above:

- experts: `legal_filter20:q9`, `legal_agg20:q4`, `legal_filter20:q8`, `legal_filter20:q15`
- observables covered: 7 of 24
- uncovered: the 15 role failures above, plus nonempty defendant status and `defendant_current_status = 'Government'`
- duplicate coverage: 0
- same-role reuse: 0
- role conflict: `plaintiff_current_status` is both a nonempty presence check (q9) and a `Company` filter (q15)
- calls per document: 4
- projected input tokens: 14,464,950
- projected completion tokens: 0
- projected total: 14,464,950

Completion reservation is 0 because DocETL calls `completion()` without `max_tokens`. Historical completion totals were not used as an estimate.

## Exact 570-document render

9,120 requests (16 experts × 570 documents). Prompt tokens are Qwen 2.5 counts of the truncated system text, user text, tool schema, and tool choice. All 570 documents have a rendering path.

Seven documents are middle-truncated on every expert: `258.txt`, `284.txt`, `298.txt`, `315.txt`, `325.txt`, `506.txt`, `522.txt`. The other 563 fit inside the 32,768-token meter. Per-document rows are in `projection.json`.

Per-expert totals (completion reservation 0):

| Query | Prompt tokens | Truncated documents |
| --- | ---: | ---: |
| legal_multiagg20:q4 | 3,653,291 | 7 |
| legal_filter20:q9 | 3,622,144 | 7 |
| legal_filter20:q7 | 3,632,390 | 7 |
| legal_multiagg20:q11 | 3,650,926 | 7 |
| legal_multiagg20:q18 | 3,690,476 | 7 |
| legal_agg20:q4 | 3,591,092 | 7 |
| legal_groupby20:q14 | 3,629,432 | 7 |
| legal_agg20:q11 | 3,609,104 | 7 |
| legal_multiagg20:q9 | 3,669,040 | 7 |
| legal_agg20:q13 | 3,615,936 | 7 |
| legal_agg20:q17 | 3,623,848 | 7 |
| legal_filter20:q8 | 3,617,060 | 7 |
| legal_filter20:q11 | 3,632,960 | 7 |
| legal_filter20:q15 | 3,634,654 | 7 |
| legal_agg20:q3 | 3,593,934 | 7 |
| legal_agg20:q14 | 3,606,960 | 7 |

## Output routing

No extra Qwen resolver. For the best four-expert subset, each covered observable has one primary expert. The other expert is not merged into that value. `plaintiff_current_status` stays split: q9 can fill only the nonempty presence sidecar, and q15 can fill only the `Company` filter sidecar. A disagreement between those outputs is left unresolved. Uncovered observables keep their original SQL. Group, predicate, presence, and numeric roles are not written into one canonical cell. The map is in `routing.json`.

## Comparison

| Execution | Calls | Tokens | Semantics |
| --- | --- | --- | --- |
| DocETL | 16 maps/document, 15.44 calls/document | 50,440,043 | query-conditioned maps |
| Best four experts | 4 calls/document | 14,464,950 (25,377 per document) | 7/24 role-compatible observables |
| Observable sidecars | 28.55 calls/processed document | 69,933 tokens/processed document | 180/570 documents |
| Generic evidence graph | 3.281 calls/document | 14,386 projected tokens/document | validation agreement 0.2769 |

Four query-conditioned maps cost about 1.76× the evidence-graph per-document projection and sit above θ25 (12,610,011). They do not recover the roles the evidence graph also failed to make explicit. DocETL’s 16 maps remain the only reconstructed tasks that see every query, and even those 16 schemas leave 15 observables without a role-compatible extraction.

## Pass/fail

| Gate | Result |
| --- | --- |
| All 24 observables have a compatible expert | Fail. 15 have none. The best four cover 7. |
| At most four extraction experts | The search cap was four. Exact coverage does not exist at four or at sixteen. |
| No additional resolver | Pass. Resolver count is 0. Adding one would also exceed the four-call cap. |
| Projected total ≤ 12,610,011 | Fail for every four-expert subset. Floor 14,401,090. Best cover 14,464,950. |
| All 570 documents rendered | Pass. |
| Numeric, temporal, entity-role, and group semantics explicit in the selected schemas | Fail. Descriptions are not in the sent schema. |
| Role-separated sidecars without a shared canonical value | Pass as a routing design. It cannot populate the 17 observables this subset leaves open. |
| No gold or baseline answers | Pass. |

no four-expert cover exists

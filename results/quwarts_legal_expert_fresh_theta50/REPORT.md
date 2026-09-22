# Fresh Legal query-expert arm

Conclusion: `fresh sampling does not reproduce the diagnostic win`

Same-attribute sharing is the official materialization. Conservative routing is the ablation.

DocETL product: 0.12350932750098194

## Request policy

- max_tokens=256. DocETL left the completion cap unset. This is the only budget-control change.
- Historical valid Legal DocETL completions: 8813 rows, maximum framed tool-call 205 tokens.
- Attempts: 1 primary + at most 2 retries.
- Retryable: timeout, provider HTTP 5xx, rate limit, connection error, and a malformed successful response when the retry reservation fits.
- Missing usage on an issued attempt is charged at the full reserved prompt + 256. Charged worst-case failures below include those attempts: provider HTTP 400 on documents whose prompt plus 256 exceeds the provider context, connection loss, and rate limits.
- θ25 terminal failures stay terminal at θ50.

## Checkpoints

### theta25

- primary attempts: 1710
- retries by cause: `{"connection": 4, "malformed": 319, "other": 2}`
- terminal failures: 156
- charged worst-case failures: 825072
- actual prompt tokens: 10974405
- actual completion tokens: 67889
- reserved attempt tokens: 12170772
- reconciled spend: 11867366
- unused retry pool: 742645
- experts completed: legal_multiagg20:q18, legal_multiagg20:q4, legal_agg20:q11
- missing document rows: `{"legal_agg20:q11": 68, "legal_multiagg20:q18": 71, "legal_multiagg20:q4": 17}`
- request hashes: `{"legal_agg20:q11": "710929c33c1ca49afe4d7382153e58c124757d4ef2c587c9c3b2caf0bc5308be", "legal_multiagg20:q18": "ed1745dc7309d676c49cfc5ed461163a339577ed832d98e654e72a885a5ff2a9", "legal_multiagg20:q4": "a0ae67f0e9044c173922f463450283088de57dc7558fc8c23c6bbeb3bc68fc35"}`
- journal prefix: True
- same-attribute product: 0.04208752074497511 (F2 0.45138587044013007, F1 0.05388257575757576)
- conservative product: 0.04208752074497511 (F2 0.2906424063878425, F1 0.05388257575757576)
- database hashes: `{"legal_agg20:q11": "fa129ff1132d0972c8f3c805bdec201032c7e36b171e863f3a773d624d4b75b9", "legal_agg20:q13": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_agg20:q14": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_agg20:q17": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_agg20:q3": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_agg20:q4": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_filter20:q11": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_filter20:q15": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_filter20:q7": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_filter20:q8": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_filter20:q9": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_groupby20:q14": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_multiagg20:q11": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b", "legal_multiagg20:q18": "cc9ed7c085073caf3263a42dcc8ee8667634ae8838cac903095eaf89a68cbc05", "legal_multiagg20:q4": "f45e5366a73d372580b762fc1d8307986e9c243242ac71a7269d595f8e2edaf0", "legal_multiagg20:q9": "48d4b3d844b4a3cfb4a849cb0884e354a7060e0406d8cdcc6c63aa0d90dba37b"}`
- same-attribute bag hash: 9460f926f77b512a849e372d3d5d54bffe5da8689fbef608b245a4ce5293325e
- conservative bag hash: 5877e7ffc79a249b9c171efe09e43cf050261ed8faaab13ba9cfbfd0c518ba71

| query | same-attribute product | conservative product |
| --- | ---: | ---: |
| legal_multiagg20:q4 | 0.0 | 0.0 |
| legal_filter20:q9 | 0.0 | 0.0 |
| legal_filter20:q7 | 0.0 | 0.0 |
| legal_multiagg20:q11 | 0.0 | 0.0 |
| legal_multiagg20:q18 | 0.16457680250783702 | 0.16457680250783702 |
| legal_agg20:q4 | 0.0 | 0.0 |
| legal_groupby20:q14 | 0.05882352941176471 | 0.05882352941176471 |
| legal_agg20:q11 | 0.25 | 0.25 |
| legal_multiagg20:q9 | 0.0 | 0.0 |
| legal_agg20:q13 | 0.0 | 0.0 |
| legal_agg20:q17 | 0.0 | 0.0 |
| legal_filter20:q8 | 0.0 | 0.0 |
| legal_filter20:q11 | 0.0 | 0.0 |
| legal_filter20:q15 | 0.0 | 0.0 |
| legal_agg20:q3 | 0.20000000000000004 | 0.20000000000000004 |
| legal_agg20:q14 | 0.0 | 0.0 |

### theta50

- primary attempts: 3420
- retries by cause: `{"connection": 9, "malformed": 783, "other": 2, "rate_limit": 3}`
- terminal failures: 369
- charged worst-case failures: 1583884
- actual prompt tokens: 22213773
- actual completion tokens: 121907
- reserved attempt tokens: 24567442
- reconciled spend: 23919564
- unused retry pool: 1300458
- experts completed: legal_multiagg20:q18, legal_multiagg20:q4, legal_agg20:q11, legal_agg20:q13, legal_agg20:q14, legal_agg20:q17
- missing document rows: `{"legal_agg20:q11": 68, "legal_agg20:q13": 23, "legal_agg20:q14": 112, "legal_agg20:q17": 78, "legal_multiagg20:q18": 71, "legal_multiagg20:q4": 17}`
- request hashes: `{"legal_agg20:q11": "710929c33c1ca49afe4d7382153e58c124757d4ef2c587c9c3b2caf0bc5308be", "legal_agg20:q13": "a8aab3629db12d046c847ab09bf787da0b4a9020cca941f66e63a4b30780ce3b", "legal_agg20:q14": "ff33e5e6efdd421298cdca40d5a91571e518aad744d1767a60e69ec45462f6b3", "legal_agg20:q17": "bf79b653b7d5cb5d05495337a96e3423a97bee7cc9e2e8459e51939bbb72684f", "legal_multiagg20:q18": "ed1745dc7309d676c49cfc5ed461163a339577ed832d98e654e72a885a5ff2a9", "legal_multiagg20:q4": "a0ae67f0e9044c173922f463450283088de57dc7558fc8c23c6bbeb3bc68fc35"}`
- journal prefix: True
- same-attribute product: 0.07420320131953051 (F2 0.6825760209189262, F1 0.08044507575757576)
- conservative product: 0.04208752074497511 (F2 0.37989894233555493, F1 0.05388257575757576)
- database hashes: `{"legal_agg20:q11": "fa129ff1132d0972c8f3c805bdec201032c7e36b171e863f3a773d624d4b75b9", "legal_agg20:q13": "16b1bfce8cbf8469c39908f8f014f52accd309cc238a282d4cea76317ed42027", "legal_agg20:q14": "fdcba1a3b13e96dc73286872e2deed40d83b9141bbe52bc4a6e63550d99a0a33", "legal_agg20:q17": "0c438278eb8729987b89304ddfb68047b31afa9f27ddcf99b70331152727962b", "legal_agg20:q3": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769", "legal_agg20:q4": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769", "legal_filter20:q11": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769", "legal_filter20:q15": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769", "legal_filter20:q7": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769", "legal_filter20:q8": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769", "legal_filter20:q9": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769", "legal_groupby20:q14": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769", "legal_multiagg20:q11": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769", "legal_multiagg20:q18": "cc9ed7c085073caf3263a42dcc8ee8667634ae8838cac903095eaf89a68cbc05", "legal_multiagg20:q4": "f45e5366a73d372580b762fc1d8307986e9c243242ac71a7269d595f8e2edaf0", "legal_multiagg20:q9": "c86b5b00fe22bab3ed3a05a89cf23d6949ecd2fed938c758bea3f8cc8fbc0769"}`
- same-attribute bag hash: f9a50990f6d5f84368c10c0c1aad8f65cc74feb238f9c764497738815725d3a7
- conservative bag hash: fc4d64aaae934cf55624ccecffd9e6d8b904f8277414319e76c0e034ddcead43

| query | same-attribute product | conservative product |
| --- | ---: | ---: |
| legal_multiagg20:q4 | 0.0 | 0.0 |
| legal_filter20:q9 | 0.0 | 0.0 |
| legal_filter20:q7 | 0.0 | 0.0 |
| legal_multiagg20:q11 | 0.0 | 0.0 |
| legal_multiagg20:q18 | 0.16457680250783702 | 0.16457680250783702 |
| legal_agg20:q4 | 0.0 | 0.0 |
| legal_groupby20:q14 | 0.5 | 0.05882352941176471 |
| legal_agg20:q11 | 0.25 | 0.25 |
| legal_multiagg20:q9 | 0.07267441860465117 | 0.0 |
| legal_agg20:q13 | 0.0 | 0.0 |
| legal_agg20:q17 | 0.0 | 0.0 |
| legal_filter20:q8 | 0.0 | 0.0 |
| legal_filter20:q11 | 0.0 | 0.0 |
| legal_filter20:q15 | 0.0 | 0.0 |
| legal_agg20:q3 | 0.20000000000000004 | 0.20000000000000004 |
| legal_agg20:q14 | 0.0 | 0.0 |


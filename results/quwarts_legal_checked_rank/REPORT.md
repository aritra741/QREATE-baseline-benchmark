# Legal candidate-aligned checked extraction

Gold was loaded only after `generation_frozen.json`. The selector did not read benchmark gold, DocETL answers, reachability assignments, or prior gold-labeled audits.

## Checked labels

Cells 537. Exact 0.0615. Observational including UNCERTAIN 0.1248. Committed candidate observational accuracy 0.7283 on 92 labels. Decided-label observational accuracy 0.7128. False absence 0.0040 on 501 gold-positive cells. Candidate coverage 0.6427. Incomplete scans 0.

Label counts: {"KEEP_PLUMBING": 425, "candidate": 92, "UNCERTAIN": 443}. Candidate rate 0.1713. KEEP rate 0.4427. UNCERTAIN rate 0.8250 of extracted cells.

Evidence coverage: 98 whole-document scans and 22 exhaustive chunk reductions on the 120 sample entities; incomplete scans 0. Three earlier scan rows belong to entities dropped when the split was locked and were not used as labels. Ledger {"verify_absence": 142205, "scan_reduce": 39922, "scan_chunk": 459583, "verify_check": 898535, "scan": 498116, "adjudicate": 639292, "verify_match": 948825}. Scan 997,621 of the 8,196,507 scan cap. Verification and absence 1,989,565 of the 3,152,502 cap. Adjudication 639,292 against the 630,500 cap. Causal spend 3,626,478 of 12,610,011.

## Ranker

Train gold-observational 0.0883. Validation gold-observational 0.0645. Validation agreement with checked labels 0.0108.

| Attribute | Checked obs | Ranker obs | Writes |
| --- | ---: | ---: | ---: |
| `case_number` | 0.0000 | 0.0000 | 0 |
| `case_type` | 0.4286 | 0.0000 | 0 |
| `defendant_current_status` | 0.0617 | 0.0494 | 4 |
| `first_judge` | 0.0000 | 0.0000 | 0 |
| `hearing_year` | 0.3958 | 0.0833 | 3 |
| `legal_basis_num` | 0.1250 | 0.0357 | 7 |
| `plaintiff_current_status` | 0.0562 | 0.3483 | 2 |
| `verdict` | 0.3158 | 0.0000 | 0 |

| Confidence band | Writes | Observational precision |
| --- | ---: | ---: |
| 0.85+ | 51 | 0.5098 |
| 0.75-0.85 | 85 | 0.3647 |
| 0.65-0.75 | 0 | 0.0000 |
| 0.55-0.65 | 0 | 0.0000 |
| <0.55 | 0 | 0.0000 |

Full-corpus writes 136. Sample writes 16. Extrapolation ratio 8.5000.
Count-inflation fixture: {"base_count": 0, "inflated_count": 1, "base_having": 0, "inflated_having": 1, "uncertain_blocked": true, "passed": true}.

## Scores

| Arm | Causal tokens | Accepted | F2 | F1@0.20 | Product |
| --- | ---: | ---: | ---: | ---: | ---: |
| plumbing | 0 | 0 | 0.2054 | 0.0365 | 0.0225 |
| checked ranker | 3626478 | 136 | 0.2054 | 0.0490 | 0.0350 |
| DocETL | 50440043 |  | 0.7892 | 0.1294 | 0.1235 |

## Per-query versus plumbing

| Query | Plumbing | Official | Delta |
| --- | ---: | ---: | ---: |
| `legal_multiagg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q7` | 0.0000 | 0.0000 | +0.0000 |
| `legal_multiagg20:q11` | 0.0952 | 0.0952 | +0.0000 |
| `legal_multiagg20:q18` | 0.0052 | 0.0052 | +0.0000 |
| `legal_agg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_groupby20:q14` | 0.0588 | 0.0588 | +0.0000 |
| `legal_agg20:q11` | 0.0000 | 0.0000 | +0.0000 |
| `legal_multiagg20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q13` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q17` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q8` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q11` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q15` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q3` | 0.2000 | 0.4000 | +0.2000 |
| `legal_agg20:q14` | 0.0000 | 0.0000 | +0.0000 |

## Hashes

```json
{
  "design": "92081198a330617d646413fabb7f9b67077606ff11f654870b94e81c9f8d6d43",
  "sample": "b2e13e93ba0b1aaa7a3ff45c90fdb0afe4620f6cbf3758c5c92ddb08037176dc",
  "prompts": "d337fff4683e67531ee8790e1fe0c985e0ef8602955bc62a0e28573bf406ed7e",
  "scans": "41118db34e57fb290e308fc731fbe8fc9e16bad0e543dc8d3f551c7d691f4d5a",
  "cells": "d0e855e952c1de253e02a1b76753393a3d1dd59581a728d3cbf8c1d6f6ae82e7",
  "features": "74530ec93ff197bc3d9a321decea4d7bdb7ad867b16b5ec8cfb7f4d2cdd48018",
  "grid": "b5b4e16d83a7a1644620b4363755bacce774718da0e56e02b9669129aaab21c5",
  "selected_threshold": "81887b3de9d8d3926d4300611e93bf7536d5e6f1337f5e8009f21dcbb86c25b1",
  "assignment": "3a269267b761e02b26e03f02d511d77618c9dc38ed6a1f793b3c9fd9b05bda53",
  "official_db": "c4de635734606fd81179b85d7807927ecaf7f34edfc1be70b92551356fc0b62e",
  "official_bags": "057ac738422485ab497a35b88157ff37a8efffc981ac1a0e0dda091e4ca859c3",
  "rebuild_match": true,
  "ledger": "c2e9fe1b69132d89fb8c39171c5847a4fc889b4acfbb9145e4115c3c6736c901",
  "spent": 3626478,
  "gold_loaded": true,
  "forbidden_inaccessible": true
}
```

checked references are accurate but deterministic ranking fails

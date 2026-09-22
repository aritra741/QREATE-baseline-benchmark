# Legal evidence-card aggregation audit

Zero Qwen. Frozen evidence-card artifacts were not modified. Gold was used only to score diagnostic replays. Reachability-assignment candidates were not admitted to any domain.

## Decision reconstruction

{
  "n_cells": 2978,
  "selectable": 2958,
  "n_invalid": 0,
  "n_missing": 0,
  "repaired_responses": 1488,
  "unique_raw_recoverable": 8697,
  "n_salvaged": 0,
  "n_repair_changed": 0,
  "n_outside_card": 0,
  "parsed_A_mismatches": 0,
  "adjudicated_cells": 1062,
  "journal_overwrite_note": "Repaired rows store the repair raw, not the pre-repair malformed text. Salvage uses the stored raw only."
}

Invalid IDs: 0. Missing pass decisions: 0. Repaired responses: 1488. Raw texts with a unique listed ID: 8697. Salvaged (malformed/invalid raw with exactly one listed ID): 0. Repair changed apparent choice vs stored raw: 0. Selections outside the final card: 0.

Rule lattice frozen before replay: `19eaa5864e9276e97d63ff802ff7499fff921c064f00ccb28eed8be0ed1ec3a7`.

## Fixed-rule replays

| Rule | Required stored-call cost | Accepted | SQL-visible | F2 | F1@0.20 | Product |
| ---- | ------------------------: | -------: | ----------: | -: | ------: | ------: |
| A | 3468542 | 1800 | 1800 | 0.6961 | 0.0958 | 0.0881 |
| B | 7491088 | 1184 | 1184 | 0.4234 | 0.0846 | 0.0706 |
| C | 10873912 | 1715 | 1715 | 0.6453 | 0.0806 | 0.0705 |
| J_only | 12056166 | 775 | 775 | 0.5100 | 0.0417 | 0.0342 |
| majority_original | 10873912 | 884 | 884 | 0.5451 | 0.0612 | 0.0537 |
| official_original | 12056166 | 1659 | 1659 | 0.6692 | 0.0733 | 0.0639 |
| A_backbone | 3468542 | 1800 | 1800 | 0.6961 | 0.0958 | 0.0881 |
| A_fill_BC | 10873912 | 1815 | 1815 | 0.6961 | 0.0958 | 0.0881 |
| A_fill_J | 12056166 | 1841 | 1841 | 0.7011 | 0.1047 | 0.0965 |
| A_fill_BC_then_J | 12056166 | 1856 | 1856 | 0.7010 | 0.1047 | 0.0965 |
| A_replace_BC | 10873912 | 1815 | 1815 | 0.6961 | 0.0958 | 0.0881 |
| A_replace_J | 12056166 | 1841 | 1841 | 0.7009 | 0.1047 | 0.0965 |
| A_replace_BC_then_J | 12056166 | 1856 | 1856 | 0.7009 | 0.1047 | 0.0965 |
| A_veto_double_keep | 10873912 | 1725 | 1725 | 0.6841 | 0.0733 | 0.0639 |
| nonkeep_plurality | 10873912 | 884 | 884 | 0.5451 | 0.0612 | 0.0537 |
| nonkeep_plurality_A_tiebreak | 10873912 | 2195 | 2195 | 0.7192 | 0.1222 | 0.1139 |
| any_two_then_A | 10873912 | 1815 | 1815 | 0.6961 | 0.0958 | 0.0881 |
| J_on_three_way_only | 12056166 | 1837 | 1837 | 0.6959 | 0.1027 | 0.0951 |
| prio_A_J_C_B | 12056166 | 2265 | 2265 | 0.7191 | 0.1243 | 0.1152 |
| prio_A_C_B_J | 12056166 | 2265 | 2265 | 0.7191 | 0.1243 | 0.1152 |
| prio_J_A_C_B | 12056166 | 2265 | 2265 | 0.7121 | 0.1021 | 0.0922 |
| prio_C_A_B_J | 12056166 | 2265 | 2265 | 0.7048 | 0.0839 | 0.0756 |
| unanimous_candidate_else_A | 10873912 | 1800 | 1800 | 0.6961 | 0.0958 | 0.0881 |
| unanimous_or_two_candidate_else_A | 10873912 | 1815 | 1815 | 0.6961 | 0.0958 | 0.0881 |
| A_only_when_another_pass_agrees | 10873912 | 797 | 797 | 0.5455 | 0.0612 | 0.0537 |
| A_or_J_only_when_supported_by_another_pass | 12056166 | 1572 | 1572 | 0.6638 | 0.0710 | 0.0628 |
| Legal DocETL | 50440043 |  |  | 0.7892 | 0.1294 | 0.1235 |

Best fixed rule: `prio_A_J_C_B` at 0.1152 (post-hoc among the predeclared lattice).
Independent rebuild bag match on every rule: True.

## Agreement cohorts

| Cohort | Cells | Exact | Observational | SQL-visible | Queries changed | Product contribution |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A candidate with B/C disagreement | 1536 | 0.2207 | 0.4473 | 1536 | 6 | +0.0404 |
| A candidate, B=C=KEEP | 75 | 0.2667 | 0.4000 | 75 | 3 | +0.0163 |
| A=B=C candidate | 117 | 0.2479 | 0.6667 | 117 | 2 | +0.0126 |
| A=KEEP with B=C candidate | 15 | 0.0000 | 0.0000 | 0 | 0 | +0.0000 |
| adjudicator agrees with A | 525 | 0.2076 | 0.3962 | 525 | 4 | +0.0274 |
| adjudicator disagrees with A | 369 | 0.0949 | 0.2493 | 250 | 2 | +0.0151 |
| adjudicator selects candidate after A=KEEP | 39 | 0.1538 | 0.2308 | 39 | 0 | +0.0000 |
| candidate/KEEP/candidate splits | 257 | 0.1284 | 0.2996 | 189 | 2 | +0.0081 |
| exactly two candidate votes | 767 | 0.2621 | 0.4928 | 752 | 4 | +0.0312 |
| repaired | 1428 | 0.1155 | 0.2381 | 748 | 4 | +0.0428 |
| three distinct candidate votes | 267 | 0.1685 | 0.3521 | 267 | 1 | -0.0060 |
| unrepaired | 1550 | 0.1516 | 0.3065 | 1052 | 5 | +0.0366 |

## Stored-output reachability

Best shared database over KEEP + A/B/C/J + unique raw-salvage: **0.1457**.
Search starts included plumbing, A, B, C, majority, official, every A-backbone replay, and `prio_A_J_C_B`.
Decisive stored IDs in the search best: {'A': 780, 'C': 764, 'B': 322, 'J': 13}.

## Cost-restricted output reachability

| Available judgments | Causal tokens | Best reachable product | Beats DocETL |
| ------------------- | ------------: | ---------------------: | -----------: |
| A only | 3468542 | 0.1038 | false |
| A + B | 7491088 | 0.1301 | true |
| A + C | 10873912 | 0.1193 | false |
| A + J where J was already generated | 12056166 | 0.1133 | false |
| A + B + C | 10873912 | 0.1457 | true |
| A + B + C + J | 12056166 | 0.1457 | true |

## Interpretation

1. Fixed label-free aggregation beat 0.1235: false (best `prio_A_J_C_B` = 0.1152).
2. Stored judgments contain a realizable assignment above 0.1235: true (best reachable 0.1457).
3. Decisive IDs in the search best came from {'A': 780, 'C': 764, 'B': 322, 'J': 13}.

stored judgments contain a Legal win but aggregation cannot identify it

# Finan coverage-selected program synthesis

**Decision: `coverage-selected program synthesis reproducibly beats DocETL within theta25`**

The official arm is one complete replica chosen by the frozen pre-gold coverage ranking. No union, majority, or adjudication.

Global spend 331564 / 345457. Selected replica 4.

## Retrospective check (zero new model calls)

- Prior program-only repro: coverage rule selects replica 3 (339 accepted, product 0.0910).
- Prior uncertainty arm: coverage rule selects replica 2 (338 accepted, product 0.0866).

These matches are diagnostic only and did not change the frozen ranking rule.

## Pre-gold coverage statistics

| Replica | Tokens | Accepted | SQL-visible | Attributes covered | Abstentions | Empty bags | Selected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 66247 | 230 | 220 | 14 | 949 | 3 |  |
| 2 | 66488 | 262 | 249 | 14 | 917 | 3 |  |
| 3 | 66151 | 279 | 266 | 14 | 900 | 3 |  |
| 4 | 66341 | 328 | 322 | 14 | 851 | 2 | yes |
| 5 | 66337 | 254 | 244 | 14 | 925 | 3 |  |

## Official scores after freeze

| Arm | F2 | Cell F1@0.20 | Product |
| --- | ---: | ---: | ---: |
| plumbing | 0.2891 | 0.0259 | 0.0158 |
| replica 1 | 0.4182 | 0.1248 | 0.0777 |
| replica 2 | 0.4319 | 0.1241 | 0.0784 |
| replica 3 | 0.4182 | 0.1248 | 0.0777 |
| replica 4 | 0.4629 | 0.1598 | 0.0988 |
| replica 5 | 0.4182 | 0.1248 | 0.0777 |
| coverage-selected official | 0.4629 | 0.1598 | 0.0988 |
| DocETL | 0.5367 | 0.1142 | 0.0841 |

## Per-query product deltas

### Replica 1
- `finan_multiagg20:q4`: 0.3750 (Δ +0.2500)
- `finan_filter20:q9`: 0.3704 (Δ +0.3704)
- `finan_filter20:q7`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q18`: 0.0043 (Δ +0.0000)
- `finan_agg20:q4`: 0.3704 (Δ +0.3704)
- `finan_groupby20:q14`: 0.1235 (Δ +0.0000)
- `finan_agg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q9`: 0.0000 (Δ +0.0000)
- `finan_agg20:q13`: 0.0000 (Δ +0.0000)
- `finan_agg20:q17`: 0.0000 (Δ +0.0000)
- `finan_filter20:q8`: 0.0000 (Δ +0.0000)
- `finan_filter20:q11`: 0.0000 (Δ +0.0000)
- `finan_filter20:q15`: 0.0000 (Δ +0.0000)
- `finan_agg20:q3`: 0.0000 (Δ +0.0000)
- `finan_agg20:q14`: 0.0000 (Δ +0.0000)
### Replica 2
- `finan_multiagg20:q4`: 0.3750 (Δ +0.2500)
- `finan_filter20:q9`: 0.3704 (Δ +0.3704)
- `finan_filter20:q7`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q18`: 0.0043 (Δ +0.0000)
- `finan_agg20:q4`: 0.3704 (Δ +0.3704)
- `finan_groupby20:q14`: 0.1340 (Δ +0.0105)
- `finan_agg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q9`: 0.0000 (Δ +0.0000)
- `finan_agg20:q13`: 0.0000 (Δ +0.0000)
- `finan_agg20:q17`: 0.0000 (Δ +0.0000)
- `finan_filter20:q8`: 0.0000 (Δ +0.0000)
- `finan_filter20:q11`: 0.0000 (Δ +0.0000)
- `finan_filter20:q15`: 0.0000 (Δ +0.0000)
- `finan_agg20:q3`: 0.0000 (Δ +0.0000)
- `finan_agg20:q14`: 0.0000 (Δ +0.0000)
### Replica 3
- `finan_multiagg20:q4`: 0.3750 (Δ +0.2500)
- `finan_filter20:q9`: 0.3704 (Δ +0.3704)
- `finan_filter20:q7`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q18`: 0.0043 (Δ +0.0000)
- `finan_agg20:q4`: 0.3704 (Δ +0.3704)
- `finan_groupby20:q14`: 0.1235 (Δ +0.0000)
- `finan_agg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q9`: 0.0000 (Δ +0.0000)
- `finan_agg20:q13`: 0.0000 (Δ +0.0000)
- `finan_agg20:q17`: 0.0000 (Δ +0.0000)
- `finan_filter20:q8`: 0.0000 (Δ +0.0000)
- `finan_filter20:q11`: 0.0000 (Δ +0.0000)
- `finan_filter20:q15`: 0.0000 (Δ +0.0000)
- `finan_agg20:q3`: 0.0000 (Δ +0.0000)
- `finan_agg20:q14`: 0.0000 (Δ +0.0000)
### Replica 4
- `finan_multiagg20:q4`: 0.3750 (Δ +0.2500)
- `finan_filter20:q9`: 0.3704 (Δ +0.3704)
- `finan_filter20:q7`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q18`: 0.0163 (Δ +0.0120)
- `finan_agg20:q4`: 0.3704 (Δ +0.3704)
- `finan_groupby20:q14`: 0.1235 (Δ +0.0000)
- `finan_agg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q9`: 0.0000 (Δ +0.0000)
- `finan_agg20:q13`: 0.0000 (Δ +0.0000)
- `finan_agg20:q17`: 0.0000 (Δ +0.0000)
- `finan_filter20:q8`: 0.0000 (Δ +0.0000)
- `finan_filter20:q11`: 0.0000 (Δ +0.0000)
- `finan_filter20:q15`: 0.0000 (Δ +0.0000)
- `finan_agg20:q3`: 0.0000 (Δ +0.0000)
- `finan_agg20:q14`: 0.3261 (Δ +0.3261)
### Replica 5
- `finan_multiagg20:q4`: 0.3750 (Δ +0.2500)
- `finan_filter20:q9`: 0.3704 (Δ +0.3704)
- `finan_filter20:q7`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q18`: 0.0043 (Δ +0.0000)
- `finan_agg20:q4`: 0.3704 (Δ +0.3704)
- `finan_groupby20:q14`: 0.1235 (Δ +0.0000)
- `finan_agg20:q11`: 0.0000 (Δ +0.0000)
- `finan_multiagg20:q9`: 0.0000 (Δ +0.0000)
- `finan_agg20:q13`: 0.0000 (Δ +0.0000)
- `finan_agg20:q17`: 0.0000 (Δ +0.0000)
- `finan_filter20:q8`: 0.0000 (Δ +0.0000)
- `finan_filter20:q11`: 0.0000 (Δ +0.0000)
- `finan_filter20:q15`: 0.0000 (Δ +0.0000)
- `finan_agg20:q3`: 0.0000 (Δ +0.0000)
- `finan_agg20:q14`: 0.0000 (Δ +0.0000)

Behavior modes by rounded product: {'0.0777': [1, 3, 5], '0.0784': [2], '0.0988': [4]}
Coverage predicts product monotonically: False

## Pairwise selected-candidate agreement

{
  "1-2": {
    "cells_equal": 1103,
    "n": 1179
  },
  "1-3": {
    "cells_equal": 1074,
    "n": 1179
  },
  "1-4": {
    "cells_equal": 1016,
    "n": 1179
  },
  "1-5": {
    "cells_equal": 1135,
    "n": 1179
  },
  "2-3": {
    "cells_equal": 1124,
    "n": 1179
  },
  "2-4": {
    "cells_equal": 999,
    "n": 1179
  },
  "2-5": {
    "cells_equal": 1117,
    "n": 1179
  },
  "3-4": {
    "cells_equal": 1017,
    "n": 1179
  },
  "3-5": {
    "cells_equal": 1090,
    "n": 1179
  },
  "4-5": {
    "cells_equal": 1042,
    "n": 1179
  }
}

## Diagnostics after gold

{
  "replica_1": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 16
    },
    "accepted_cell_accuracy": {
      "n": 230,
      "ok": 19
    }
  },
  "replica_2": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 20
    },
    "accepted_cell_accuracy": {
      "n": 262,
      "ok": 23
    }
  },
  "replica_3": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 14
    },
    "accepted_cell_accuracy": {
      "n": 279,
      "ok": 17
    }
  },
  "replica_4": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 21
    },
    "accepted_cell_accuracy": {
      "n": 328,
      "ok": 24
    }
  },
  "replica_5": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 16
    },
    "accepted_cell_accuracy": {
      "n": 254,
      "ok": 19
    }
  },
  "official": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 21
    },
    "accepted_cell_accuracy": {
      "n": 328,
      "ok": 24
    }
  },
  "error_kinds_official": {
    "wrong_candidate": 55,
    "wrong_period": 36,
    "gold_absent_from_inventory": 233,
    "correct_candidate": 22,
    "wrong_unit": 2,
    "wrong_component": 2
  }
}

**Primary decision:** `coverage-selected program synthesis reproducibly beats DocETL within theta25`


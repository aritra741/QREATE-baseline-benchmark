# Legal transfer of frozen Finan coverage-selected program synthesis

**Decision: `Legal candidate availability is insufficient`**

The frozen Finan method was transferred without Legal-specific policy, prompt, ranking, or candidate-generator changes. No Finan model calls were made.

## Part 1: zero-token Finan fragility audit

Exact token ratio: `331,564 / 1,381,827` = 0.239946.
Absolute lift: +0.014748. Relative lift: +17.54%.
Beats / ties / loses: 5 / 6 / 5.
`finan_agg20:q14` fraction of the overall advantage: 0.8316.
Any single-query removal reverses ordering: True.
See `results/quwarts_finan_coverage_fragility/REPORT.md`. This audit did not change the transfer policy.

## Query-set parity

- Full workload query count: 80
- DocETL manifest count: 16
- QuWARTS compiled count: 16
- Scored intersection: 16
- Exclusions (not compiled): 64 train/unexecuted queries
- Failures: none
- Ordered query-list hash: `47fec3938805fd1b5339747921ce0ab940103db8f5d1533a0968a5780dd4fdf7`

Legal DocETL actual spend: 50,440,043. Frozen Finan absolute cap 345,457 is 0.6849% of that spend.
This run spent 336,798 tokens (0.6677% of Legal DocETL).

Selected replica 3 was recorded before gold. Global spend 336798 / 345457.

## Scores

| Arm | Tokens | Accepted | SQL-visible | F2 | Cell F1@0.20 | Product |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Legal plumbing | 0 | 0 |  | 0.2054 | 0.0365 | 0.0225 |
| replica 1 | 67197 | 1323 | 1323 | 0.2273 | 0.0444 | 0.0356 |
| replica 2 | 67619 | 1304 | 1304 | 0.2276 | 0.0444 | 0.0356 |
| replica 3 | 67442 | 1364 | 1364 | 0.2276 | 0.0444 | 0.0356 |
| replica 4 | 66969 | 1326 | 1326 | 0.2273 | 0.0444 | 0.0356 |
| replica 5 | 67571 | 1115 | 1115 | 0.2233 | 0.0444 | 0.0356 |
| coverage-selected official | 67442 | 1364 | 1364 | 0.2276 | 0.0444 | 0.0356 |
| Legal DocETL | 50440043 |  |  | 0.7892 | 0.1294 | 0.1235 |
| candidate-availability oracle | 0 | 899 |  | 0.2409 | 0.0498 | 0.0368 |
| selection oracle (accepted attrs) | 0 | 899 |  | 0.2409 | 0.0498 | 0.0368 |

## Per-query products and deltas (official vs DocETL)

- `legal_multiagg20:q4`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)
- `legal_filter20:q9`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)
- `legal_filter20:q7`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)
- `legal_multiagg20:q11`: 0.1111 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0159)
- `legal_multiagg20:q18`: 0.0000 (Δ vs DocETL -0.1881; Δ vs plumbing -0.0052)
- `legal_agg20:q4`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)
- `legal_groupby20:q14`: 0.0588 (Δ vs DocETL -0.1912; Δ vs plumbing +0.0000)
- `legal_agg20:q11`: 0.0000 (Δ vs DocETL -1.0000; Δ vs plumbing +0.0000)
- `legal_multiagg20:q9`: 0.0000 (Δ vs DocETL -0.2270; Δ vs plumbing +0.0000)
- `legal_agg20:q13`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)
- `legal_agg20:q17`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)
- `legal_filter20:q8`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)
- `legal_filter20:q11`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)
- `legal_filter20:q15`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)
- `legal_agg20:q3`: 0.4000 (Δ vs DocETL +0.2000; Δ vs plumbing +0.2000)
- `legal_agg20:q14`: 0.0000 (Δ vs DocETL +0.0000; Δ vs plumbing +0.0000)

Behavior modes by rounded product: {'0.0356': [1, 2, 3, 4, 5]}
Coverage predicts product monotonically: True
Accepted-coverage vs product correlation: None

## Pairwise selected-candidate agreement

{
  "1-2": {
    "cells_equal": 2647,
    "n": 2849
  },
  "1-3": {
    "cells_equal": 2441,
    "n": 2849
  },
  "1-4": {
    "cells_equal": 2846,
    "n": 2849
  },
  "1-5": {
    "cells_equal": 2381,
    "n": 2849
  },
  "2-3": {
    "cells_equal": 2641,
    "n": 2849
  },
  "2-4": {
    "cells_equal": 2644,
    "n": 2849
  },
  "2-5": {
    "cells_equal": 2400,
    "n": 2849
  },
  "3-4": {
    "cells_equal": 2438,
    "n": 2849
  },
  "3-5": {
    "cells_equal": 2594,
    "n": 2849
  },
  "4-5": {
    "cells_equal": 2378,
    "n": 2849
  }
}

## Diagnostics after gold

{
  "replica_1": {
    "candidate_set_recall": {
      "n": 2849,
      "present": 899
    },
    "candidate_set_recall_by_attribute": {
      "case_number": {
        "present": 119,
        "n": 485
      },
      "case_type": {
        "present": 0,
        "n": 135
      },
      "defendant_current_status": {
        "present": 57,
        "n": 411
      },
      "first_judge": {
        "present": 249,
        "n": 277
      },
      "hearing_year": {
        "present": 225,
        "n": 267
      },
      "legal_basis_num": {
        "present": 192,
        "n": 538
      },
      "plaintiff_current_status": {
        "present": 57,
        "n": 528
      },
      "verdict": {
        "present": 0,
        "n": 208
      }
    },
    "selector_accuracy_given_present": {
      "n": 899,
      "ok": 270
    },
    "accepted_cell_accuracy": {
      "n": 1323,
      "ok": 270
    }
  },
  "replica_2": {
    "candidate_set_recall": {
      "n": 2849,
      "present": 899
    },
    "candidate_set_recall_by_attribute": {
      "case_number": {
        "present": 119,
        "n": 485
      },
      "case_type": {
        "present": 0,
        "n": 135
      },
      "defendant_current_status": {
        "present": 57,
        "n": 411
      },
      "first_judge": {
        "present": 249,
        "n": 277
      },
      "hearing_year": {
        "present": 225,
        "n": 267
      },
      "legal_basis_num": {
        "present": 192,
        "n": 538
      },
      "plaintiff_current_status": {
        "present": 57,
        "n": 528
      },
      "verdict": {
        "present": 0,
        "n": 208
      }
    },
    "selector_accuracy_given_present": {
      "n": 899,
      "ok": 206
    },
    "accepted_cell_accuracy": {
      "n": 1304,
      "ok": 206
    }
  },
  "replica_3": {
    "candidate_set_recall": {
      "n": 2849,
      "present": 899
    },
    "candidate_set_recall_by_attribute": {
      "case_number": {
        "present": 119,
        "n": 485
      },
      "case_type": {
        "present": 0,
        "n": 135
      },
      "defendant_current_status": {
        "present": 57,
        "n": 411
      },
      "first_judge": {
        "present": 249,
        "n": 277
      },
      "hearing_year": {
        "present": 225,
        "n": 267
      },
      "legal_basis_num": {
        "present": 192,
        "n": 538
      },
      "plaintiff_current_status": {
        "present": 57,
        "n": 528
      },
      "verdict": {
        "present": 0,
        "n": 208
      }
    },
    "selector_accuracy_given_present": {
      "n": 899,
      "ok": 205
    },
    "accepted_cell_accuracy": {
      "n": 1364,
      "ok": 205
    }
  },
  "replica_4": {
    "candidate_set_recall": {
      "n": 2849,
      "present": 899
    },
    "candidate_set_recall_by_attribute": {
      "case_number": {
        "present": 119,
        "n": 485
      },
      "case_type": {
        "present": 0,
        "n": 135
      },
      "defendant_current_status": {
        "present": 57,
        "n": 411
      },
      "first_judge": {
        "present": 249,
        "n": 277
      },
      "hearing_year": {
        "present": 225,
        "n": 267
      },
      "legal_basis_num": {
        "present": 192,
        "n": 538
      },
      "plaintiff_current_status": {
        "present": 57,
        "n": 528
      },
      "verdict": {
        "present": 0,
        "n": 208
      }
    },
    "selector_accuracy_given_present": {
      "n": 899,
      "ok": 270
    },
    "accepted_cell_accuracy": {
      "n": 1326,
      "ok": 270
    }
  },
  "replica_5": {
    "candidate_set_recall": {
      "n": 2849,
      "present": 899
    },
    "candidate_set_recall_by_attribute": {
      "case_number": {
        "present": 119,
        "n": 485
      },
      "case_type": {
        "present": 0,
        "n": 135
      },
      "defendant_current_status": {
        "present": 57,
        "n": 411
      },
      "first_judge": {
        "present": 249,
        "n": 277
      },
      "hearing_year": {
        "present": 225,
        "n": 267
      },
      "legal_basis_num": {
        "present": 192,
        "n": 538
      },
      "plaintiff_current_status": {
        "present": 57,
        "n": 528
      },
      "verdict": {
        "present": 0,
        "n": 208
      }
    },
    "selector_accuracy_given_present": {
      "n": 899,
      "ok": 104
    },
    "accepted_cell_accuracy": {
      "n": 1115,
      "ok": 104
    }
  },
  "official": {
    "candidate_set_recall": {
      "n": 2849,
      "present": 899
    },
    "candidate_set_recall_by_attribute": {
      "case_number": {
        "present": 119,
        "n": 485
      },
      "case_type": {
        "present": 0,
        "n": 135
      },
      "defendant_current_status": {
        "present": 57,
        "n": 411
      },
      "first_judge": {
        "present": 249,
        "n": 277
      },
      "hearing_year": {
        "present": 225,
        "n": 267
      },
      "legal_basis_num": {
        "present": 192,
        "n": 538
      },
      "plaintiff_current_status": {
        "present": 57,
        "n": 528
      },
      "verdict": {
        "present": 0,
        "n": 208
      }
    },
    "selector_accuracy_given_present": {
      "n": 899,
      "ok": 205
    },
    "accepted_cell_accuracy": {
      "n": 1364,
      "ok": 205
    }
  },
  "error_kinds_official": {
    "gold_absent_from_inventory": 699,
    "wrong_candidate": 218,
    "wrong_period": 127,
    "correct_candidate": 205,
    "wrong_unit": 3,
    "wrong_component": 1
  },
  "accepted_attributes_union": [
    "case_number",
    "case_type",
    "defendant_current_status",
    "first_judge",
    "hearing_year",
    "legal_basis_num",
    "plaintiff_current_status",
    "verdict"
  ]
}

Candidate-availability-oracle product: 0.0368.

**Primary decision:** `Legal candidate availability is insufficient`


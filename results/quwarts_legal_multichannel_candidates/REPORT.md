# Legal multi-channel candidate generation

**Decision: `expanded candidate availability remains insufficient`**

Global spend 12595218 / 12610011. Generation 12263034. Selection 332184. Selected replica 1.
Semantic/composed proposal cells attempted: 785. Context modes: {'whole_document': 641, 'retrieved_pack': 144}.

| Arm | Tokens | Candidate cells | Accepted | SQL-visible | F2 | F1@0.20 | Product |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| plumbing | 0 | 0 | 0 | 0 | 0.2054 | 0.0365 | 0.0225 |
| old extractive inventory | 67442 | 2978 | 1364 | 1364 | 0.2276 | 0.0444 | 0.0356 |
| replica 1 | 62768 | 2978 | 1144 | 1144 | 0.4555 | 0.0425 | 0.0329 |
| replica 2 | 68878 | 2978 | 1142 | 1142 | 0.4348 | 0.0336 | 0.0257 |
| replica 3 | 68920 | 2978 | 1128 | 1128 | 0.4618 | 0.0411 | 0.0340 |
| replica 4 | 68977 | 2978 | 1038 | 1038 | 0.4457 | 0.0341 | 0.0271 |
| replica 5 | 62641 | 2978 | 1062 | 1062 | 0.4472 | 0.0411 | 0.0340 |
| selected official | 62768 | 2978 | 1144 | 1144 | 0.4555 | 0.0425 | 0.0329 |
| DocETL | 50440043 |  |  |  | 0.7892 | 0.1294 | 0.1235 |

## Channel-availability oracles (zero new calls)

| surface | 0 |  | 899 |  | 0.2409 | 0.0498 | 0.0368 |
| surface_normalized | 0 |  | 906 |  | 0.2408 | 0.0498 | 0.0368 |
| workload_label | 0 |  | 1015 |  | 0.5068 | 0.0553 | 0.0425 |
| semantic | 0 |  | 151 |  | 0.3251 | 0.0365 | 0.0225 |
| composed | 0 |  | 3 |  | 0.2095 | 0.0365 | 0.0225 |
| all_expanded | 0 |  | 1485 |  | 0.5631 | 0.1225 | 0.0810 |
| loo_surface | 0 |  | 1333 |  | 0.5409 | 0.1352 | 0.0920 |
| loo_normalized | 0 |  | 1482 |  | 0.5632 | 0.1225 | 0.0810 |
| loo_workload_label | 0 |  | 961 |  | 0.4326 | 0.0556 | 0.0449 |
| loo_semantic | 0 |  | 1437 |  | 0.5471 | 0.0940 | 0.0664 |
| loo_composed | 0 |  | 1485 |  | 0.5631 | 0.1225 | 0.0810 |

## Official per-query products

- `legal_multiagg20:q4`: 0.0000
- `legal_filter20:q9`: 0.0000
- `legal_filter20:q7`: 0.0000
- `legal_multiagg20:q11`: 0.1111
- `legal_multiagg20:q18`: 0.0000
- `legal_agg20:q4`: 0.0000
- `legal_groupby20:q14`: 0.2079
- `legal_agg20:q11`: 0.0000
- `legal_multiagg20:q9`: 0.0080
- `legal_agg20:q13`: 0.0000
- `legal_agg20:q17`: 0.0000
- `legal_filter20:q8`: 0.0000
- `legal_filter20:q11`: 0.0000
- `legal_filter20:q15`: 0.0000
- `legal_agg20:q3`: 0.2000
- `legal_agg20:q14`: 0.0000

{
  "candidate_set_recall": {
    "n": 2978,
    "present": 1485
  },
  "candidate_set_recall_by_attribute": {
    "case_number": {
      "present": 201,
      "n": 485
    },
    "case_type": {
      "present": 53,
      "n": 153
    },
    "defendant_current_status": {
      "present": 278,
      "n": 509
    },
    "first_judge": {
      "present": 253,
      "n": 277
    },
    "hearing_year": {
      "present": 277,
      "n": 280
    },
    "legal_basis_num": {
      "present": 321,
      "n": 538
    },
    "plaintiff_current_status": {
      "present": 102,
      "n": 528
    },
    "verdict": {
      "present": 0,
      "n": 208
    }
  },
  "selector_accuracy_given_present": {
    "n": 1485,
    "ok": 178
  },
  "accepted_cell_accuracy": {
    "n": 1144,
    "ok": 178
  }
}

**Primary decision:** `expanded candidate availability remains insufficient`


# Finan uncertainty-triggered program-selection arm

**Decision: `targeted adjudication reproducibly beats DocETL within theta25`**

Global spend 287857 / 345457. Compiler 198734; adjudication 89123.

| Arm | Tokens | Accepted | SQL-visible | F2 | F1@0.20 | Product |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| plumbing | 0 | 0 | 0 | 0.2891 | 0.0259 | 0.0158 |
| compiler replica 1 | 66170 | 322 | 316 | 0.4506 | 0.1465 | 0.0866 |
| compiler replica 2 | 66237 | 338 | 332 | 0.4506 | 0.1465 | 0.0866 |
| compiler replica 3 | 66327 | 244 | 231 | 0.4319 | 0.1241 | 0.0784 |
| majority-only | 198734 | 301 | 295 | 0.4506 | 0.1465 | 0.0866 |
| adjudication-only | 89123 | 18 | 10 | 0.2891 | 0.0259 | 0.0158 |
| official combined | 287857 | 319 | 310 | 0.4506 | 0.1465 | 0.0866 |
| DocETL | 1381827 | — | — | 0.5367 | 0.1142 | 0.0841 |

## Before-gold decision counts

{
  "unanimous_selection": 174,
  "two_of_three_selection": 127,
  "singleton_selection": 57,
  "conflicting_selection": 21,
  "all_abstain": 800,
  "singleton_adjudicator_accept": 17,
  "singleton_adjudicator_reject": 40,
  "conflict_adjudicator_agreement": 2,
  "conflict_adjudicator_disagreement": 1,
  "budget_unattempted_disputes": 0,
  "reason_counts": {
    "primary_none": 58,
    "primary_accept": 17,
    "conflict_agree": 2,
    "conflict_disagree": 1
  },
  "n_dispute_cards": 78
}

## Per-query official deltas vs plumbing

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
- `finan_agg20:q14`: 0.1299 (Δ +0.1299)

Adjudication accepted 19 of 78 disputed cells (17 singleton, 2 verified conflicts) and rejected the rest, with 0 budget-unattempted. Those 19 writes changed official bags versus majority-only but left the 16-query product unchanged at 0.0866. Replica 3 was the weak replica this time (0.0784); majority already captured the two stronger compilers. Adjudication did not restore replica-3-only cells into official score, and it did not harm the majority product.

Selector accuracy given gold present: replica 1 25/189; replica 2 29/189; replica 3 24/189; majority 24/189; official 29/189. Majority cohort 24/67; singleton-adjudicated 5/20; conflict-adjudicated 0/5. Adjudication added five gold-present hits without moving mean query product. Error kinds on official writes: correct 30, wrong-candidate 44, wrong-period 23, wrong-unit 2, wrong-component 1, gold absent from inventory 227.

## Freeze hashes

- Inventory `0fc5a8bb1758aab9ce2092814da8e5c15708890503623171f125bb3c2dce7580`
- Samples `ceabd5b0ac976976b93db253e31070fccc89976abff97bf871e4da35f4dd7ba7`
- Policy `dbff1d566408587b396222683152c0cd7501e7e27764870c169595c37cdcf6c6`
- Cards `1da3c5154e70cdb11dc06d2a4785043be008b23e538d38ebedb4572533b1b8f6`
- Majority bags `6b40b67d61168a092f0add43b846ece946a0a5009d51298a2a997f00a132c78d`
- Adjudication-only bags `58e143638a1dba25cc5705eb756ba46d1ca6ed10ace8dabb97e3a74f86c37806`
- Official bags `265efb2ef68a03f78f948617746562b84d59b317ca1b64bec35731c7ba6921c4`
- Ledger `a86457e3faf9d81adddf331728548adfd673a0594c255b1c5fc21c9b1871ab4b`

## Diagnostics after gold

{
  "replica_1": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 25
    }
  },
  "replica_2": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 29
    }
  },
  "replica_3": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 24
    }
  },
  "majority": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 24
    }
  },
  "official": {
    "candidate_set_recall": {
      "n": 1179,
      "present": 189
    },
    "selector_accuracy_given_present": {
      "n": 189,
      "ok": 29
    }
  },
  "majority_cohort": {
    "n": 301,
    "gold_present": 67,
    "ok": 24
  },
  "singleton_adjudicated": {
    "n": 57,
    "gold_present": 20,
    "ok": 5
  },
  "conflict_adjudicated": {
    "n": 21,
    "gold_present": 5,
    "ok": 0
  },
  "error_kinds": {
    "wrong_candidate": 44,
    "wrong_period": 23,
    "gold_absent_from_inventory": 227,
    "correct_candidate": 30,
    "wrong_unit": 2,
    "wrong_component": 1
  },
  "replica_difference_cells": 78,
  "adjudication_recovered": [
    {
      "document_id": "65",
      "attribute": "auditor",
      "reason": "primary_accept",
      "winner_id": "C8"
    },
    {
      "document_id": "14",
      "attribute": "auditor",
      "reason": "primary_accept",
      "winner_id": "C7"
    },
    {
      "document_id": "9",
      "attribute": "auditor",
      "reason": "primary_accept",
      "winner_id": "C1"
    },
    {
      "document_id": "61",
      "attribute": "auditor",
      "reason": "primary_accept",
      "winner_id": "C1"
    },
    {
      "document_id": "52",
      "attribute": "auditor",
      "reason": "primary_accept",
      "winner_id": "C8"
    },
    {
      "document_id": "29",
      "attribute": "auditor",
      "reason": "primary_accept",
      "winner_id": "C3"
    },
    {
      "document_id": "81",
      "attribute": "auditor",
      "reason": "primary_accept",
      "winner_id": "C5"
    },
    {
      "document_id": "67",
      "attribute": "auditor",
      "reason": "primary_accept",
      "winner_id": "C6"
    },
    {
      "document_id": "83",
      "attribute": "auditor",
      "reason": "primary_accept",
      "winner_id": "C3"
    },
    {
      "document_id": "4",
      "attribute": "auditor",
      "reason": "conflict_agree",
      "winner_id": "C3"
    },
    {
      "document_id": "14",
      "attribute": "exchange_code",
      "reason": "conflict_agree",
      "winner_id": "C2"
    },
    {
      "document_id": "3",
      "attribute": "business_segments_num",
      "reason": "primary_accept",
      "winner_id": "C3"
    },
    {
      "document_id": "94",
      "attribute": "business_segments_num",
      "reason": "primary_accept",
      "winner_id": "C1"
    },
    {
      "document_id": "6",
      "attribute": "business_segments_num",
      "reason": "primary_accept",
      "winner_id": "C1"
    },
    {
      "document_id": "73",
      "attribute": "business_segments_num",
      "reason": "primary_accept",
      "winner_id": "C2"
    },
    {
      "document_id": "19",
      "attribute": "business_segments_num",
      "reason": "primary_accept",
      "winner_id": "C2"
    },
    {
      "document_id": "1",
      "attribute": "dividend_per_share",
      "reason": "primary_accept",
      "winner_id": "C2"
    },
    {
      "document_id": "48",
      "attribute": "dividend_per_share",
      "reason": "primary_accept",
      "winner_id": "C5"
    },
    {
      "document_id": "2",
      "attribute": "dividend_per_share",
      "reason": "primary_accept",
      "winner_id": "C8"
    }
  ],
  "adjudication_rejected": [
    {
      "document_id": "95",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "33",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "30",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "56",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "84",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "76",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "13",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "35",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "96",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "15",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "12",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "83",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "29",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "5",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "46",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "34",
      "attribute": "auditor",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "39",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "98",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "35",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "96",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "68",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "91",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "51",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "85",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "100",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "7",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "57",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "21",
      "attribute": "exchange_code",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "5",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "87",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "98",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "23",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "72",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "95",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "42",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "89",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "57",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "84",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "16",
      "attribute": "major_equity_changes",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "92",
      "attribute": "major_equity_changes",
      "reason": "conflict_disagree",
      "winner_id": null
    },
    {
      "document_id": "96",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "53",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "34",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "100",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "14",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "59",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "75",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "24",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "45",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "50",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "27",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "46",
      "attribute": "business_segments_num",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "35",
      "attribute": "dividend_per_share",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "40",
      "attribute": "dividend_per_share",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "61",
      "attribute": "dividend_per_share",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "11",
      "attribute": "dividend_per_share",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "56",
      "attribute": "dividend_per_share",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "51",
      "attribute": "dividend_per_share",
      "reason": "primary_none",
      "winner_id": null
    },
    {
      "document_id": "99",
      "attribute": "dividend_per_share",
      "reason": "primary_none",
      "winner_id": null
    }
  ]
}

**Primary decision:** `targeted adjudication reproducibly beats DocETL within theta25`


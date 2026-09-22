# Legal conclusion

workload compilation succeeded, but document understanding did not amortize

No further θ25 Legal run is justified. No Legal model process was running. This consolidation made zero model calls and did not modify frozen artifacts.

The 16-query workload does compile. Sixty AST occurrences became 24 canonical observables, reuse 0.60, with separate sidecars for presence, predicates, groups, and numeric contributions. That compilation did not produce a cheaper or more accurate read of the documents. On the documents QuWARTS actually processed, it spent more model calls per document than DocETL and covered 180 of 570 files.

## 1. Execution economics

```text
QuWARTS: 2,878 / 180 = 15.99 calls/document
DocETL: 8,799 / 570 = 15.44 calls/document
```

The 2,878 figure is scheduled entity-bundle steps in `decision_journal.jsonl`. The ledger contains **5,139** model calls, because the selected group and predicate plans are decompose-then-reduce. That is **5,139 / 180 = 28.55 model calls per processed document**.

| | QuWARTS observable acquisition | DocETL |
| --- | ---: | ---: |
| Calls shown above | 2,878 bundle steps | 8,799 model calls |
| Model calls | 5,139 | 8,799 |
| Documents processed | 180 | 570 |
| Calls per processed document | 15.99 bundle steps; 28.55 model calls | 15.44 |
| Tokens | 12,587,883 | 50,440,043 |
| Tokens per processed document | 69,933 | 88,491 |
| Accepted decisions | 965 | one emitted row per call |
| Tokens per accepted decision | 13,044 | 5,732 per call |
| Accepted decisions per model call | 0.188 | not an accept/reject arm |
| Corpus coverage | 180/570 = 0.316 | 570/570 = 1 |
| AST-occurrence reuse | 1 − 24/60 = 0.60 | not applicable |
| Actual model-call reuse | 0 / 5,139 | each query re-reads the corpus |

DocETL's 8,799 calls are 16 query pipelines, about 550 calls each, over all 570 documents. QuWARTS' expression dedup did not change that shape. A bundle is one attribute and one observable class, at most three expressions, and the document is pasted into that call again. Nineteen bundles exist. On the 180 shortest documents the schedule reached, that is still about 16 bundle steps per document, the same order as DocETL's 15.44. Decomposition then doubles the group and predicate steps, so the model-call rate is higher than DocETL's while 390 documents are never read.

There is no shared document representation. Evidence construction made **0** model calls. Deterministic spans were rebuilt inside every decision prompt, so the document tokens were paid on every call.

| Stage | Calls | Tokens |
| --- | ---: | ---: |
| Evidence construction | 0 | 0 |
| Direct | 878 | 2,153,111 |
| Decomposition (extract + reduce) | 4,156 | 10,106,602 |
| Gleaning | 45 | 168,978 |
| Validation (verify + blinded judge) | 60 | 159,192 |
| Total | 5,139 | 12,587,883 |

| Observable type | Calls | Tokens | Attempts | Cited-span accepts | SQL-visible | Exact gold | Observational gold |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Presence | 590 | 1,409,662 | 539 | 220 | 145 | 0 | 0 |
| Predicate | 1,613 | 3,933,098 | 1,260 | 200 | 74 | 0 | 0 |
| Group | 2,580 | 6,275,311 | 1,379 | 406 | 362 | 233 | 233 |
| Numeric | 356 | 969,812 | 420 | 139 | 137 | 5 | 7 |

Cited-span acceptance is the validator's source-offset test. Exact and observational columns are post-freeze comparisons to benchmark gold. They are not the same thing.

## 2. Accuracy funnel

A cited span only shows that the returned string occurs in the document. It does not show that the string is the right entity, role, period, group, or numeric contribution.

| Type | Attempts | Resolved and cited | SQL-visible | Exact | Observational | Queries helped | Queries harmed |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Presence | 539 | 220 | 145 | 0/220 | 0/220 | none | `legal_multiagg20:q11`, judge bags |
| Predicate | 1,260 | 200 | 74 | 0/200 | 0/200 | none | `legal_multiagg20:q11` |
| Group | 1,379 | 406 | 362 | 233/406 | 233/406 | `legal_agg20:q11` | `legal_agg20:q3`, judge bags |
| Numeric | 420 | 139 | 137 | 5/139 | 7/139 | none | `legal_multiagg20:q11`, `legal_agg20:q14` averages |

All 220 presence accepts are `FALSE`. All 145 `first_judge` presence decisions and all 75 `case_number` presence decisions are false on gold: the gold value is present. The cited span was not evidence of absence.

`legal_agg20:q3` fell from 0.2000 to 0.0572. Deleting the `hearing_year` group-key sidecar restores the plumbing bag (5 rows). The live bag has 18 rows. The 70 written labels are document years from 1958 through 2009, including 14 times 2006 and 11 times 2007. Those are cited spans with the wrong period for the hearing-year group key.

`legal_multiagg20:q11` fell from 0.0952 to 0. The plumbing bag is restored only by removing `case_number` presence, `case_number` numeric values, and the verdict predicate together. Presence alone, numeric alone, or the verdict predicate alone does not restore it. The 75 presence decisions are all `FALSE` on gold-present case numbers, and the numeric writes are mostly the wrong integer (5 of 139 numeric accepts match gold exactly).

Judge grouping shrank `legal_agg20:q4` and `legal_agg20:q14` from 145 rows to 101, and `legal_multiagg20:q4` from 55 to 22. Their products stayed 0. Restoring `legal_agg20:q4` requires deleting both `first_judge` sidecars. The group key was usually the digit `1` (61 writes) or `0` (15), not a judge name. The presence sidecar was `FALSE` on 145 gold-present rows. `legal_agg20:q14` stays different after the judge sidecars are removed because `legal_basis_num` numeric writes still change the averages.

The one product gain is `legal_agg20:q11`, from 0 to 0.1852. Deleting the plaintiff group-label sidecar returns that bag to plumbing. F2 rose from 0.2054 to 0.3266 and cell F1@0.20 from 0.0365 to 0.0420, but the mean of per-query products fell from 0.0225 to 0.0192.

## 3. Official pre-gold arms

Best valid pre-gold result on the 16-query DocETL set: **evidence-card official**, product **0.0639**. Pass A at 0.0881 is a component of that arm, not the database the pre-gold rule selected. Reachability and oracle scores are not official.

| Arm | Causal tokens | Query set | F2 | F1@0.20 | Product | Selection | Database |
| --- | ---: | --- | ---: | ---: | ---: | --- | --- |
| Plumbing | 0 | 16-query | 0.2054 | 0.0365 | 0.0225 | baseline | shared base |
| Frozen group policy (`unknown_else_escape`) | 2,614,827 | group holdout, not the 16-query manifest | 0.1623 | 0.0333 | 0.0221 | official pre-gold; live equals its incumbent | query-local sidecars |
| Deterministic selector transfer | 336,798 | 16-query | 0.2276 | 0.0444 | 0.0356 | official pre-gold | shared |
| Expanded candidates | 12,595,218 | 16-query | 0.4555 | 0.0425 | 0.0329 | official pre-gold | shared |
| Evidence-card official | 12,056,166 | 16-query | 0.6692 | 0.0733 | 0.0639 | official pre-gold | shared |
| Pairwise A/B | 9,380,309 | 16-query | 0.3278 | 0.0655 | 0.0500 | official pre-gold | shared |
| Forced binary | 9,674,917 | 16-query | 0.6071 | 0.0642 | 0.0556 | official pre-gold | shared |
| Corpus probe | 7,516,559 | 16-query | 0.4558 | 0.0564 | 0.0376 | official pre-gold | shared |
| Checked extraction | 3,626,478 | 16-query | 0.2054 | 0.0490 | 0.0350 | official pre-gold | shared |
| Repaired checked ranker | 3,626,478 | 16-query | 0.2402 | 0.0490 | 0.0350 | official pre-gold, zero new calls | shared |
| Observable sidecars | 12,587,883 | 16-query | 0.3266 | 0.0420 | 0.0192 | official pre-gold | role sidecars on the shared base |
| DocETL | 50,440,043 | 16-query | 0.7892 | 0.1294 | 0.1235 | external baseline | per-query extraction |

### Diagnostic table

These were not the pre-gold selected database.

| Diagnostic | Product | Why it is not official |
| --- | ---: | --- |
| Shared reachability best | 0.2123 | post-hoc search over frozen candidate IDs |
| Deterministic surface + workload-label assignment | 0.1886 | zero-token feasibility, not a selected policy |
| Stored-output reachability | 0.1457 | gold-scored replay of stored judgments |
| A+B domain | 0.1301 | same diagnostic family |
| Best fixed rule `prio_A_J_C_B` | 0.1152 | post-hoc lattice, below DocETL |
| Pass A alone | 0.0881 | stronger than the official majority, but not the frozen selection rule |
| Corpus-probe program-family ceiling | 0.0446 | measured after the official 0.0376 selection |
| Forced-fill channel oracles | 0.0810 to 0.0920 | not availability ceilings |

## 4. Ruled out

| Mechanism | Strongest measured result | Blocker |
| --- | --- | --- |
| Shared canonical extraction | evidence-card official 0.0639; Pass A component 0.0881 | one cell value cannot serve every SQL role, and the selector does not recover the diagnostic assignment |
| Signatures and UNKNOWN-ELSE repair | group policy live product 0.0221, equal to its incumbent | finite CASE repair did not move the score |
| Deterministic candidate selection | transfer official 0.0356; deterministic feasibility 0.1886 is diagnostic only | the pre-gold selector does not find the feasible assignment |
| Multi-replica coverage selection | five replicas, official 0.0356 | replicas agree and stay near plumbing |
| Corpus-sampled silver supervision | official 0.0376; family ceiling 0.0446 | silver labels are the wrong estimand; 116/768 cells mapped to a candidate |
| Checked candidate supervision | committed observational accuracy 0.7283 on 92 labels; official product 0.0350 | the accurate committed IDs are not what the ranker writes |
| Global deterministic ranking | 0.0350, validation 8/32 against a channel baseline of 19/32 | the ranker loses to a channel rule and does not generalize |
| Pairwise and majority aggregation | pairwise 0.0500; forced binary 0.0556; majority 0.0639 | judges agree on KEEP or replace a better pass with a worse one |
| Role-separated workload observables | compilation 60→24; official product 0.0192 | cited spans are not the right role; 28.55 model calls per processed document |
| Query-result-equivalence labels | training positives inflated to 525 rows and 24 all-positive groups | a no-op substitution was treated as a correct candidate |
| Value-identical label repair | same product 0.0350 after the equivalence bug was removed | the repaired ranker still loses to the channel baseline |

## 5. Resume gate

No further Legal model arm may run unless a preflight, without benchmark gold, shows all of the following:

1. One shared document representation serves every relevant observable.
2. Projected full-corpus cost is within θ25 = 12,610,011.
3. Projected cost is at most 12,610,011 / 570 = 22,123 tokens per document.
4. Projected model calls are about four or fewer per document.
5. Evidence is not regenerated separately for predicates, groups, presence, and aggregates.
6. The plan has a coverage path for all 570 documents.
7. The mechanism is new. Another prompt, vote, ranker, or sidecar variant does not qualify.

The observable arm fails these gates. It spent 69,933 tokens and 28.55 model calls on each processed document, regenerated the document inside every bundle, and stopped at 180 of 570 documents after using 12,587,883 tokens. No tested Legal mechanism meets the gate.

## 6. Source hashes

| Artifact | SHA-256 |
| --- | --- |
| `results/quwarts_legal_observable_sidecar/REPORT.md` | `2a1695c9ccb4747ecb0b8dd5874c4fce57c75becc7fca4e065462d803eef2da4` |
| `results/quwarts_legal_observable_sidecar/generation_frozen.json` | `18cae1671bb2a5682e03aefe39fc4d1f4e556671bc35efc75f45fbee06166513` |
| `results/quwarts_legal_observable_sidecar/live_ledger.json` | `bbf7b6ec8da9d9db8dd416a9ef8968d2dfd07c97b486571de0784904ad100237` |
| `results/quwarts_legal_evidence_card_select/post_freeze.json` | `19cd9c26ec049247fd3a81bc33ec458c732e7a63aa377add495b514d8faa9b06` |
| `results/quwarts_legal_coverage_transfer/legal_coverage_transfer.json` | `ea76e76c7fd0865bf437a021ce916f170cee1cdbdc3819030670792bf6c4e92f` |
| `results/quwarts_legal_multichannel_candidates/legal_multichannel_candidates.json` | `f57318fc8c2b96e0f3fd188c9006bc8006834c87dc43d2e49601a1c93acd7afc` |
| `results/quwarts_legal_corpus_probe/post_freeze.json` | `2fb44c8b8cbdf2dc2280d0f1860fb29f085b87302ba6d91f41b0fb5f396dc821` |
| `results/quwarts_legal_group/freeze.json` | `3d6c2862bc763e1873c6f8b8fc747209cea97a89028c5a9ac3d12ec656589240` |
| `results/quwarts_holdout_group/group_holdout.json` | `d76f7fbd13ef0482563794fb95f563c7ba705cfcdf20352ba50193af5c8b2c2c` |
| `results/docetl_legal_case80/session_token_cost.json` | `b9a0223a3df23c3baade7feba2a96bb91f4f52fd89ec6cbdf75b57d834123441` |

The machine-readable table is `results/quwarts_legal_final_consolidation/table.json`.

workload compilation succeeded, but document understanding did not amortize

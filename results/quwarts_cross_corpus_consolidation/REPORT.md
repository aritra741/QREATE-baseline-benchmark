# QuWARTS cross-corpus consolidation

**Decision: `QuWARTS does not beat DocETL overall`**

Zero model calls. Frozen artifacts were not modified. The full Legal evidence-graph arm was not launched.

Med and Finan each beat DocETL on the official product. Legal does not. The unweighted mean of the three official products is 0.11237552932477357 for QuWARTS and 0.12441849091419088 for DocETL. Winning two corpora is not an overall win.

These are three independently developed arms. They are not one algorithm, and no gold-free controller selected them as a portfolio.

## Official results

Each row is the strongest result that was frozen before gold, scored on the corpus's official query set, accounted for with the causal token ledger, and run with Qwen 2.5 7B. θ25 is `round(DocETL tokens × 0.25)` from `session_token_cost.json`.

| Corpus | QuWARTS method | QuWARTS tokens | θ25 | QuWARTS F2 | QuWARTS F1@0.20 | QuWARTS product | DocETL tokens | DocETL product | Win/loss |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Med | frozen `unknown_else_escape` | 1543772 | 2948971 | 0.4840707538075959 | 0.22845238095238093 | 0.17439887110939742 | 11795885 | 0.16564255550190216 | Win |
| Finan | coverage-selected program synthesis, replica 4 | 331564 | 345457 | 0.46290732942719454 | 0.15984623015873015 | 0.09884778147912206 | 1381827 | 0.08410358973968853 | Win |
| Legal | evidence-card official θ25 database | 12056166 | 12610011 | 0.6691744149996088 | 0.0733047385620915 | 0.06387993538580125 | 50440043 | 0.12350932750098194 | Loss |

Query-set parity holds inside each corpus: Med 20/20, Finan 16/16, Legal 16/16. Finan's causal spend is the five-replica ledger, 331564, not replica 4 alone at 66341. Med's frozen execution cap is 1543790; the scored policy replay added no calls. DocETL Finan is the exact `evaluation.json` mean, 0.08410358973968853. The arm table also stores the rounded 0.0841.

### Stronger components that stay unofficial

* Med `all_else_escape` product 0.17641780733885998. The frozen policy marks it `diagnostic_only`.
* Legal Pass A product 0.08813663898916835 at 3452863 tokens. It is a selector inside the evidence-card arm, not the database the pre-gold θ25 rule selected.

## Aggregates

* Macro / unweighted product: QuWARTS 0.11237552932477357, DocETL 0.12441849091419088, delta −0.012042961589417307.
* Weighted by QuWARTS tokens: QuWARTS 0.07695893557989185, DocETL 0.12724033752576974.
* Weighted by DocETL tokens: QuWARTS 0.0851316782362292, DocETL 0.1304656685379167.
* Corpus wins: 2. Corpus losses: 1.
* Token use versus DocETL: Med 0.1308737750495194, Finan 0.2399461003439649, Legal 0.2390197407246461.
* Product per million tokens: Med 0.11296931872672741 versus 0.014042401693633175; Finan 0.29812579616340146 versus 0.060864051534445726; Legal 0.005298528187634548 versus 0.002448636443489589.
* Matched budget: every official QuWARTS spend is inside θ25. DocETL is scored at its full token total. That is not a DocETL rerun at the same budget.

95% Student-t intervals on the paired per-query product difference (QuWARTS minus DocETL) all include zero:

* Med, n=20: mean 0.008756315607495286, interval [−0.13307289500440106, 0.15058552621939164].
* Finan, n=16: mean 0.014744191739433535, interval [−0.07659216604536902, 0.10608054952423608].
* Legal, n=16: mean −0.05962939211518069, interval [−0.1679836265188589, 0.048724842288497536].

## Method consistency

| Corpus | Mechanism | Frozen before transfer | Developed here | Corpus-specific calls or policy | One controller could select it without gold | Information used before execution |
| --- | --- | --- | --- | --- | --- | --- |
| Med | AST CASE repair, `unknown_else_escape`, on Med signature votes | yes, as a policy | yes | yes | no | Finite CASE sites, direct or two-vote resolution, UNKNOWN escapes to ELSE |
| Finan | Five synthesized programs, one replica kept by coverage rank | no | yes | yes | no | Accepted candidates, SQL-visible fills, attribute coverage, empty bags, tokens |
| Legal | Evidence cards materialized on a frozen θ25 schedule | no | yes | yes | no | Evidence cards and the pre-declared budget schedule |

The Med policy was not the controller for Finan or Legal. The Finan coverage rank was transferred to Legal and the official replica lost. The Legal evidence-card schedule was not used on Med or Finan.

## Diagnostics

These are not official results.

| Diagnostic | Product | Why it is not official |
| --- | --- | --- |
| Med `all_else_escape` | 0.17641780733885998 | Marked diagnostic-only in the frozen policy |
| Med witness better-of | 0.20838251534712512 | Component oracle |
| Legal shared candidate reachability | 0.21234293187418188 | Reachability search |
| Legal cost-aware deterministic candidates | 0.188602227469415 | Feasibility assignment, not a frozen acquisition |
| Legal Pass A | 0.08813663898916835 | Stronger selector, not the selected database |

## Failed arms

| Mechanism | Strongest negative official result | Blocker |
| --- | --- | --- |
| Schema extraction | Finan fresh retrieve-extract, product 0.0 | Structure F2 and cell F1@0.20 are both 0 |
| Signatures | Med generic signature arm, product 0.09025327885622003 | Below DocETL; the official Med win is the later group policy |
| Query witnesses | Med incumbent witness database, product 0.12439887110939743 | Witness support without the frozen group repair loses |
| Candidate selection | Legal coverage-transfer official, product 0.035620915032679744, 336798 tokens | Candidate availability is insufficient |
| Corpus probes | Legal official probe, product 0.03756624217150533, 7516559 tokens | Plans can be ranked; the programs are not enough |
| Checked rankers | Legal checked ranker, product 0.03495590543909872, 3626478 tokens | Accurate checks do not make the ranking succeed |
| Role-separated observables | Legal sidecar, product 0.019153113434933713, 12587883 tokens | Cited spans are the wrong role; product falls below plumbing |
| Shared evidence graph | Preflight only | Affordable, semantically inadequate; no full run |

## Legal stopping record

```text
shared document representation is affordable but semantically inadequate
```

* Projected tokens: 8199915.153846154.
* Mean calls per document: 3.281264057579847.
* Projected coverage: 570/570.
* Workload-weighted resolution: 0.39947916666666666.
* Source-offset validity: 1.0.
* Independent semantic agreement: 0.27692307692307694.
* No full run launched.

Legal may resume only with a new semantic-resolution mechanism, not another prompt, vote, ranker, verifier threshold, or sidecar.

## Provenance

Machine-readable tables, per-query files, and source hashes are in `results/quwarts_cross_corpus_consolidation/`.

# What helps with a small model, and does knowing the workload help? (Qwen 7B, 2026-10-14)

Every setup reads each table once with the union of the realistic queries' columns and answers all of them from that one
table, no representation layer (scripts: `exp_shared_reader.py`, `exp_docetl_arms.py --arm shared*`; report:
`exp_ingredients_report.py`, per-document filter check: `exp_ingredients_filters.py`). Single runs; differences under about
0.03 are within run-to-run noise. Court cases not run (time); artists without L1/L2 (time; a control with no gap).
DocETL with our wording keeps an explicit null as "not stated" (`DOCETL_NULL_OK=1`): our wording says "use null", which
DocETL's type check otherwise rejects (3 retries, then the document is dropped).

## Players (the collection with the large gap): the ladder, mean query score

| Setup | 0% | 5% | 10% | 20% | Tokens | Lost docs | Share of L0-L4 gap at 20% (0%) |
|---|---|---|---|---|---|---|---|
| DocETL per query, as run | 0.063 | 0.072 | 0.086 | 0.105 | | | |
| L0 DocETL, one shared read, harness wording | 0.060 | 0.078 | 0.108 | 0.130 | 3.0M | 39 | |
| L1 + our wording | 0.251 | 0.297 | 0.363 | 0.410 | 2.3M | 8 | 64% (56%) |
| L2 + split documents | 0.296 | 0.338 | 0.423 | 0.482 | 2.4M | 4 | 16% (13%) |
| L3 our reader (plain JSON, a row whatever comes back), as read | 0.376 | 0.415 | 0.478 | 0.544 | 2.1M | 0 | 14% (23%) |
| L4 + our commit step | 0.402 | 0.441 | 0.504 | 0.570 | 2.1M | 0 | 6% (8%) |
| our full system, as run | 0.382 | 0.415 | 0.502 | 0.564 | | | |

- The wording carries most of the edge, and it also prevents most lost documents (39 -> 8): fewer replies fail the strict form.
- One shared read plus commit equals our full system: the planner and representation layer add nothing to accuracy here.
- Reading per query with the query shown does not help DocETL (0.105 vs 0.130 shared).

## Per document: filter matches (wrongly counted / rightly counted)

| Setup | medical (15 filters) | artists (10) | papers (13) |
|---|---|---|---|
| DocETL per query, as run | 51% / 70% | 28% / 79% | 6% / 26% |
| L0 DocETL shared, harness wording | 7% / 24% | 8% / 66% | 2% / 19% |
| L1 + our wording | 15% / 57% | - | 8% / 40% |
| L2 + split documents | 16% / 60% | - | 7% / 38% |
| L3/L4 our reader | 14% / 61% | 12% / 70% | 4% / 35% |
| W1 no use lines | 14% / 63% | 11% / 68% | 3% / 36% |
| W2 every column | 18% / 59% | 13% / 74% | 4% / 37% |
| our full system, as run | 14% / 60% | 12% / 70% | 5% / 38% |

- Showing the query (DocETL per query) makes the small model over-match (medical 51% wrong); DocETL's wording without the
  query under-matches (24% right) and loses documents. Our wording lands in between, in either engine.
- Medical query means are dominated by single numbers flipping 0/1 (Q12, Q15) and are not used for conclusions.

## Does knowing the workload help? Mean query score at 0 / 5 / 10 / 20% (committed)

| Collection | L4 (workload columns, use lines) | W1 no use lines | W2 every schema column |
|---|---|---|---|
| players | 0.402 / 0.441 / 0.504 / 0.570 | 0.360 / 0.386 / 0.445 / 0.496 | 0.333 / 0.363 / 0.433 / 0.508 |
| artists | 0.039 / 0.164 / 0.186 / 0.208 | 0.029 / 0.183 / 0.207 / 0.225 | 0.038 / 0.194 / 0.240 / 0.270 |
| papers | 0.014 / 0.042 / 0.060 / 0.087 | 0.003 / 0.029 / 0.065 / 0.087 | 0.015 / 0.029 / 0.085 / 0.102 |
| medical | (exact-count noise; per document: use lines no effect, every column 14% -> 18% wrong) | | |

- Cost: yes, clearly. Reading the expected columns before queries ask is what turns 32 of 107 no-call queries into 99.
- Accuracy: depends on the collection. On players both workload ingredients help (use lines +0.04 to +0.07; reading only the
  workload's columns +0.06). On medical, reading only the workload's columns lowers wrong matches (18% -> 14%); use lines do
  nothing. On artists reading every column is better (0.270 vs 0.208), on papers about equal. Why players gains and artists
  loses is not yet explained (players: join keys and group-by columns; artists: 26 short-document columns).

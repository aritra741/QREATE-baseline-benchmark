# Router v1/v2 diagnosis (2026-09-26)

Written after the CSPaper (v1) and Art (v2) probe runs. Every claim below is
backed by a file in this repo; nothing here uses benchmark gold.

## What is wrong

### 1. The decision rule conflates two different questions
v1/v2 routed an attribute to per-query maps whenever it was "not extractive"
(answers not verbatim spans). But *whether a value can be shared across queries*
depends only on whether query context changes the answer. *Whether it is a span*
only decides between a deterministic program and a model read.

Evidence: Art `age` gives the same answer under every prompt (share-loss 0.09,
self-noise 0.00, 11 pairs) but is computed from dates, so g = 0.21 and v2 sent it
to fused maps, the most expensive route. It should be read once and shared.

### 2. Agreement was measured with the wrong comparator
The probe compared values as strings. The benchmark (`evaluation/comparators.py`)
splits multi-valued cells on `||` and scores set F1, compares numbers exactly,
and compares strings case-insensitively. Replaying the stored Art outputs with
the benchmark's rules (`eval/router_comparator_replay.py`):

| Attribute | v2 delta (strings) | Share-loss (benchmark comparator) |
|---|---:|---:|
| field | 0.60 | 0.07 |
| style | 0.67 | 0.29 |
| color | 0.42 | 0.23 |

`"Painting"` vs `"Painting ||"` was counted as a conflict.

### 3. The probe cannot resolve its own decisions
Pairs per attribute: 1-5 on CSPaper, 2-11 on Art. The 95% interval on the rate
of large disagreements is typically 0.0-0.5 or wider, so a 0.2 threshold cannot be
decided. The v2 "at least 4 pairs" rule hid this without fixing it.

### 4. The verdict is not a quality estimate
"Coverage" counts query-attribute uses assigned to a non-keep operator. It says
nothing about whether those values will be right, and nothing about kept values.
`predicted_loss` / `workload_served` verdicts were therefore not predictions.

### 5. Constants were guessed
Thresholds (0.5, 0.2, 0.10) and cost parameters (8 calls per program attribute,
fusion width 2, 600-token overhead) were never measured. Freezing them made
runs reproducible, not principled.

### 6. The routes point to operators that do not exist
`canonical_map` and `retrieval_map` were never implemented; the handoff's only
canonical-store test (Legal 6.20) scored 0.035. No plan has been executed, so no
router output has ever been checked against an outcome.

### 7. The budget reference is inconsistent across corpora
Recorded DocETL runs (`results/docetl_*_case80/session_token_cost.json`):

| Corpus | DocETL calls | Queries x docs | Tokens per call | Median doc tokens |
|---|---:|---:|---:|---:|
| Art | 16,000 | 16 x 1,000 | 1,276 | 810 |
| Legal | 8,799 | 16 x 570 | 5,732 | 4,342 |
| Player | 1,874 | mixed tables | 6,846 | 1.8k-17.8k |
| CSPaper | 1,800 | 16 x 200 = 3,200 | 1,452 | 932 |
| Med | 1,123 | mixed tables | 10,503 | 8.4k-11.0k |
| Finan | 112 | 16 x 7 (of 100) | 12,337 | 118,076 |

DocETL read every document for Art and Legal, fewer than expected for CSPaper and
Med, and 7 of 100 filings (at most ~12k tokens of each ~118k-token filing) for
Finan. "25% of DocETL tokens" is therefore 25% of very different amounts of work,
and the router's DocETL-cost estimate was off by 2.5-12x on three corpora.

### 8. The probe measured a hypothetical operator
Probe prompts were my own wording and listed workload labels, which invites the
label copying the handoff identified (9.13). The measured behaviour belongs to
neither DocETL's prompt nor any QuWARTS operator's prompt.

## What the fix has to be

Measure the quantity the benchmark scores, for operators that actually run, with
enough samples to decide, and choose by expected loss per token instead of
thresholds.

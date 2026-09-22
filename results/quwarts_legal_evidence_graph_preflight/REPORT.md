# Gate 1: Legal evidence-graph preflight

**Conclusion: `shared document representation is affordable but semantically inadequate`**

This preflight did not run the full Legal corpus and did not score against benchmark gold.

## Hard targets

```text
maximum model calls per document: 4.00 (cap 4)
mean tokens per document: 14385.8 (cap 22123)
projected total for 570 documents: 8199915 (cap 12610011)
documents with a valid execution path: 570/570
```

## Pass/fail

| Gate | Result |
| --- | --- |
| projected total tokens ≤ 12,610,011 | PASS |
| all 570 documents have a route | PASS |
| no document requires more than four model calls | PASS |
| mean model calls/document ≤ 4 | PASS |
| mean tokens/document ≤ 22,123 | PASS |
| ≥50% of resolved facts support two or more observables | PASS |
| evidence is not regenerated separately for observable classes | PASS |
| source-offset validity ≥ 0.98 | PASS |
| independent source/role validation ≥ 0.80 | FAIL |
| no benchmark gold was accessed | PASS |

## Sample

Frozen 32 documents, seed 20260921, longest included: `506.txt`.
Quartile counts: [8, 8, 8, 8].
Candidate-count mix: {'high': 9, 'low': 12, 'medium': 11}.

## Cost projection

- calls/document mean 3.281, median 3.269, p90 3.333, p95 3.333, max 4.000
- tokens/document mean 14385.8, median 13721.8, p90 21932.0, p95 22695.0, max 25473.0
- projected total tokens 8199915
- documents processed before θ25 exhaustion 570/570
- workload-weighted resolution 0.3995
- facts reused by more than one observable 111/114
- tokens per resolved observable 1374.7

## Source validation

- offset validity 1.0000
- cross-role compatibility 0.9846
- independent source/role agreement 0.2769 (18/65) on a blinded 20% sample of 325 resolved observables
- verifier: `qwen/qwen-2.5-7b-instruct`, one pass, no gold, no adjudication loop
- spot-audit tokens 31,072, recorded on the preflight ledger and not added as a fifth per-document call
- deterministic replay True

The full Legal arm was not launched.

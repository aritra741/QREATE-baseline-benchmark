# Player workload audit and remediation

The four contrast workloads contain 80 SQL/NL pairs. They were audited against
the Player CSVs for SQL validity, NL↔SQL alignment, join coverage, missing-value
semantics, useful group cardinality, and realistic analytical meaning.

## Repairs applied

- Team/player and team/owner comparisons now trim padded names.
- Team/city joins normalize `Brooklyn → New York City` and
  `Washington → Washington, D.C.`, eliminating the known city-key losses.
- Queries that promise “each team” or “each owner” use left joins where zero
  counts or `NULL` maxima are part of the intended answer.
- Questions now say “listed” or “matching” team instead of claiming the
  undated player field represents a current roster.
- NULL-sensitive multi-aggregate queries use one explicit cohort or identify
  the recorded metric being aggregated.
- The malformed owner age and unit-inconsistent GDP field are no longer used
  by the four contrast workloads.
- Career achievements are reported as player attributes (winner counts or
  recorded career totals), not as awards won for a current owner or city.
- Sparse year and pick dimensions use cohorts/bands. Near-unique college,
  ownership, city, and team combinations were replaced or given minimum
  support thresholds.
- Tautological filters and `HAVING COUNT(...) >= 1` are rejected.
- Every generated query executes and returns at least two groups.

## Enforced validation

`build_player_contrast_workloads.py` now fails generation on:

1. duplicate IDs or SQL;
2. empty NL questions or empty result sets;
3. one-group `GROUP BY` outputs;
4. tautological nonnegative filters;
5. tautological `HAVING COUNT >= 1`;
6. use of unnormalized GDP;
7. multi-column groupings whose count output is entirely singleton rows.

## Mixture safety

The original `player_agg20` remains unchanged for case-study reproducibility.
Seven audited baseline queries (`q2`, `q7`, `q10`, `q12`, `q14`, `q16`,
`q19`) are excluded from new mixtures because of incomplete joins, singleton
groupings, malformed owner age, or GDP units.

Mixtures now use mutually exclusive measured SQL strata (`filtered`,
`multigroup`, `multiagg`, and exact join depths 1–3), deterministic per-recipe
seeds, strict duplicate prevention, source hashes, and measured property
summaries.

## Regenerate

```bash
python3 "case study/build_player_contrast_workloads.py"
python3 "case study/mix_player_workloads.py"
python3 "case study/mix_player_workloads.py" \
  --round-robin --size 25 --name mix25_roundrobin
```

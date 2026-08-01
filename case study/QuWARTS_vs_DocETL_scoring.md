# Scoring QuWARTS vs DocETL

I tried a few scoring functions. Here’s what they mean, how they’d look on different tables, and what we get for QuWARTS vs DocETL.

QuWARTS builds one workload-aware database up front. DocETL runs a fresh extraction pipeline per query. Same Player workload, same model family.

---

## What each score means

We separate two questions: did we recover the right groups, and are the numbers right? Then we combine them into one rankable score so neither can hide the other.

### Structure

**Row precision / recall.** Of the predicted groups, how many are real? Of the gold groups, how many did we find?

- precision = matched / (matched + extra predicted groups)
- recall = matched / (matched + missing gold groups)

Unmatched rows never get a value score. Extra junk groups hurt precision; missing groups hurt recall.

**Column precision / recall.** Did we return the right columns for the groups and for the aggregated values? Reported separately for each.

### Values (only on matched groups)

Once groups line up, we look at the aggregated values. Pass@τ and the error histogram only cover matched groups, so we always show **Row Recall** with them. Otherwise a system that gets 2 groups exactly right and misses the other 21 can look perfect on value scores.

- **Rel-err histogram:** share of matched numeric cells in ≤1%, 1–5%, 5–20%, 20–100%, >100%.
- **Pass@τ:** fraction with relative error ≤ τ (we use 0.01, 0.05, and 0.20).
- **Frac catastrophic:** fraction with relative error > 1.
- **Pass by operator:** Pass@τ sliced by COUNT / SUM / AVG / MIN / MAX when we know the operator.
- **zero_true_count:** gold measure is 0; we require an exact match so these cells do not produce huge relative errors.

### Cell-F1@τ

A predicted cell is a true positive only if the column is right, the group is matched, and the value passes (within τ for numbers, or high enough string similarity).

Extra predicted groups are false positives. Missing gold groups are false negatives. We compute Cell-F1 at every τ so we can check that the ranking is stable.

This is the score we rank on.

---

## How this looks on different tables

Toy gold, always the same:

| nation | count |
| --- | ---: |
| USA | 100 |
| Canada | 10 |
| UK | 5 |

### Perfect prediction

Same table back.

Row F1 = 1, Pass@0.05 = 1 (with Row Recall = 1), histogram all in ≤1%, **Cell-F1@0.05 = 1**.

### Right groups, everything 10% high

USA 110, Canada 11, UK 5.5.

Row F1 is still 1. Pass@0.05 is 0; Pass@0.20 is 1. Histogram sits entirely in 5–20%. So **Cell-F1@0.05 = 0** and **Cell-F1@0.20 = 1**. The score changes with τ as expected.

### Three good groups + twelve junk groups

Value scores on the matched rows look perfect. Row precision drops. **Cell-F1@0.05 ≈ 0.4** (3 TP, 12 FP). Extra invented groups cost a lot.

### Wrong measures and placeholder values

Gold: American → 72.1. Pred: American → 305.5, plus a made-up Canadian → -1. Row recall drops when groups do not line up, Pass@τ is 0 on the badly wrong age, and Cell-F1 goes near 0.

---

## What we get: QuWARTS vs DocETL

| Score | QuWARTS | DocETL |
| --- | ---: | ---: |
| **Cell-F1@0.05** | **0.299** | **0.078** |
| Cell-F1@0.01 | 0.166 | 0.074 |
| Cell-F1@0.20 | 0.314 | 0.092 |
| Row Recall | 0.573 | 0.427 |
| Pass@0.05 (on matched cells only) | 0.727 | 0.172 |

The ranking is stable across τ: QuWARTS is ahead. DocETL loses on both missing/extra groups and bad measure values. A correct group label does not rescue a wrong aggregate.

### Cost

QuWARTS used about 2.6M tokens end-to-end for construction (shared extraction ~2.35M, plus intent analysis, pilots, and SQL compile). DocETL used about 54M, roughly **21×** more.

---

## Per-query Cell-F1@0.05

| Query | QuWARTS | DocETL | Winner |
| --- | ---: | ---: | --- |
| q0 | 0.667 | 0.000 | QuWARTS |
| q1 | 0.286 | 0.083 | QuWARTS |
| q6 | 0.036 | 0.000 | QuWARTS |
| q7 | 0.000 | 0.000 | — |
| q8 | 0.000 | 0.000 | — |
| q12 | 0.000 | 0.146 | DocETL |
| q15 | 0.000 | 0.000 | — |
| q17 | 0.207 | 0.250 | DocETL |
| q19 | 0.698 | 0.207 | QuWARTS |
| q26 | 0.400 | 0.000 | QuWARTS |
| q27 | 0.818 | 0.692 | QuWARTS |
| q28 | 0.000 | 0.000 | — |
| q31 | 0.000 | 0.000 | — |
| q35 | 0.000 | 0.000 | — |
| q44 | 0.000 | 0.000 | — |
| q46 | 0.000 | 0.000 | — |
| q48 | 0.000 | 0.000 | — |
| q49 | 0.773 | 0.077 | QuWARTS |
| q50 | 0.000 | 0.000 | — |
| q53 | 0.667 | 0.000 | QuWARTS |
| q54 | 0.667 | 0.000 | QuWARTS |
| q58 | 0.667 | 0.333 | QuWARTS |
| q59 | 1.000 | 0.000 | QuWARTS |

A few worth calling out:

- **q54** (average owner age by nationality): QuWARTS 0.667, right groups with small numeric drift. DocETL 0.000: invents nationalities and produces bad ages (e.g. 305.5).
- **q49** (count by nationality): QuWARTS 0.773 vs DocETL 0.077. DocETL’s Pass@τ on the few groups it hits can look fine, but Row Recall is about 0.13, so Cell-F1 collapses.
- **q12** (max player age by nationality): DocETL 0.146 vs QuWARTS 0.000. DocETL finds more of the groups; QuWARTS produced the wrong ones.

---

## Bottom line

We rank on **Cell-F1@τ**. Structure and values are reported separately, and value scores are always read with Row Recall.

**QuWARTS 0.299 vs DocETL 0.078** at τ = 0.05.

---

## Settings

```text
tau_sweep = [0.01, 0.05, 0.20]
theta     = 0.9
epsilon   = 1e-9
```

Owner ages in gold were fixed to max age in 2026 (as of Dec 31) before we re-ran these numbers. Micky Arison previously had birth year 1949 stored as age.

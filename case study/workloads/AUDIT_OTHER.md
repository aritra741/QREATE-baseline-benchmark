# Contrast-workload realism audit (Art, CSPaper, Finan, Legal, Med, SEC)

Audited the 26 pure/baseline packs (520 SQL/NL pairs) against the same bar used
for Player: would a real user of that domain ask this, and does the English
match the SQL and the field meaning?

Mechanical checks already pass: every query executes, returns at least two
groups, has unique SQL, and has no tautological `HAVING COUNT >= 1`.

## Verdict

Most packs are realistic. CSPaper, Finan, and SEC are the strongest. Art, Legal,
and Med have a smaller set of questions that a real user would not ask, or that
over-claim what the column means.

| Dataset | Overall | Main problem |
|---|---|---|
| **CSPaper** | Strong | One meta phrase; one awkward NL |
| **Finan** | Strong | One misleading “mid-sized” band |
| **SEC** | Strong, with jargon | “Metric filings / filing table / revenue concept” is schema talk |
| **Legal** | Good questions, one wrong label | `first_judge` is not “first-instance” |
| **Art** | Mixed | Zodiac and marital-status questions are not curator questions |
| **Med** | Mixed | Several questions describe the join machinery, not a user need |

## What already meets the bar

These are the kinds of questions a real user would ask:

- **Art:** painters vs sculptors by century; awarded artists by continent;
  artists who died abroad; portrait/landscape/still-life color and tone.
- **CSPaper:** multi-hop vs agent use; reranker vs multi-turn retrieval;
  medical-domain papers; graph retrieval vs knowledge graphs; baseline counts.
- **Finan:** profitable NASDAQ names; dividend payers by auditor; cash vs debt;
  Big Four equity changes; concentrated tech ownership.
- **Legal:** dismissed administrative cases; statutes and precedents by case
  type; applicant nationality in immigration-heavy matters; judges with many
  dismissals.
- **Med:** oral vs injectable drugs; infectious diseases; USA vs non-USA labs;
  prescription-only tablets.
- **SEC:** 10-K vs 10-Q counts; profitable quarterlies; Delaware issuers;
  revenue/net income/OCF by year and company.

## Findings that fail the “real user” test

### 1. Art: zodiac and marital status are not analytical questions

A curator or art historian would not ask these as workload questions:

| Pack | IDs | Why |
|---|---|---|
| `art_agg20` | q2, q11 | Zodiac counts; marital-status census |
| `art_filter20` | q8, q11 | Awarded artists by marriage; European zodiac |
| `art_groupby20` | q11, q14 | Zodiac × teaching; marriage × century |
| `art_multiagg20` | q11, q12 | Same two dimensions with extra aggregates |

`age BETWEEN 25 AND 105` is a data-cleaning cohort. Calling it “plausible
recorded age” (`art_filter20` q3) leaks that fact into the question.

“Field family” (`art_groupby20` q6, q13; `art_multiagg20` q3, q15) is our
internal CASE label, not user language. Say “painters, sculptors,
photographers, or other artists.”

### 2. Legal: `first_judge` is mislabeled

The attribute is “whether it was the first judgment” (1/0), not whether the
judge sat at first instance. Every “first-instance” question is therefore
misaligned:

- `legal_agg20` q4, q14
- `legal_filter20` q3, q6, q16, q19
- `legal_groupby20` q1, q9, q11
- `legal_multiagg20` q4, q14, q15

The rest of the Legal pack is realistic. Evidence 0/1 as “recorded evidence”
matches the dictionary.

### 3. Med: some questions describe the join, not a need

Realistic: “Which oral drugs treat infectious diseases?” and “Which US labs
study a listed disease?”

Not realistic, because a user would not talk this way:

| Pack | IDs | Why |
|---|---|---|
| `med_agg20` | q19 | “Concrete prevention vs a less specific note” is our CASE heuristic |
| `med_join20` | q3, q11, q17 | “Matched drugs” / “drug–disease–institution matches” |
| `med_groupby20` | q15 | “Three-table matches” |
| `med_multiagg20` | q13–q15, q19 | Same join jargon |
| `med_filterjoin20` | q19 | “Among three-table matches at university-affiliated institutions…” |

Room-temperature storage (`med_agg20` q7) is a weak inventory question, not a
research question.

### 4. SEC: schema nouns leaked into the English

The SQL is fine. The English sometimes names tables instead of filings:

- `sec_join20` q0, q2, q4, q6, q10 — “metric filings,” “metric rows,”
  “filing table”
- Revenue-concept questions (q8, q9, q14–q19) are realistic for an XBRL
  analyst, not for a general investor. Keep them only in the join pack.

`sec_filterjoin20` and `sec_agg20` are mostly clean investor/analyst questions.

### 5. Smaller NL issues

| Pack | ID | Issue |
|---|---|---|
| `cspaper_filter20` | q0 | “Known reranker label” is catalog talk. Ask about multi-hop papers. |
| `cspaper_groupby20` | q19 | English counts “combinations”; SQL counts papers. |
| `cspaper_agg20` | q16 | Topic is ~96% RAG, so the question is realistic but almost tautological. |
| `finan_filter20` | q16 | “Mid-sized” is `$10M–$5B` revenue. That is not mid-sized. |
| `finan_agg20` | q5, q6 | “Exchange family” / “activity family” is our jargon. The other Finan
  questions already name NASDAQ/NYSE/ASX or finance/healthcare/technology. |

## Repairs applied

1. **Art:** Replaced zodiac and marriage queries with institution, award-status,
   style, birth-country, and death-abroad questions. Dropped “plausible recorded
   age.” Named field groups as painters, sculptors, photographers, or other
   artists.
2. **Legal:** Relabeled every `first_judge` question as first judgment versus
   later judgments (not first-instance court).
3. **Med:** Rewrote join English as “drugs for a listed disease” / “drugs for
   diseases that a lab also studies.” Dropped “matched” and “three-table
   matches.” Replaced the CASE-heuristic “concrete prevention” question with
   screening versus another recorded measure.
4. **SEC:** Rewrote `sec_join20` English as filings and companies, not metric
   rows or the filing table.
5. **One-offs:** Dropped “known reranker label”; aligned CSPaper q19 English
   with paper counts; replaced “mid-sized” with the actual `$10M–$5B` band;
   named Finan exchange / activity / auditor groups in English.
6. Rebuilt pure packs and mixtures after these changes.

## Second-audit repairs

A second pass found remaining semantic mismatches. These are now applied:

1. **Med join cardinality:** Join queries that ask for drugs, institutions, or
   diseases now use `COUNT(DISTINCT id)` (and distinct `CASE` counts in
   multi-agg). They no longer count relationship rows as entities.
2. **Med wording:** Dropped residual “match,” “linked,” and `pair_count`
   language. Questions describe disease/lab relationships directly.
3. **Art units:** SQL already counted artists. English that said “artworks” or
   “works” now asks about artists (or an artist’s work).
4. **Polish:** `med_agg20` q7 asks about recorded mechanism of action, not
   room-temperature storage. `finan_filter20` q1 asks for average revenue of
   companies audited by each firm. `legal_agg20` q2 asks for cases decided,
   matching `case_count`.
5. Rebuilt Art, Finan, Legal, and Med packs and their mixtures.

## What we would not change

- Family CASE expressions in SQL (exchange, auditor, disease type, industry).
  They keep groups useful. Only the English should name the groups.
- `HAVING COUNT(*) >= N` on sparse keys. Same rule as Player.
- Honest “listed / matching / recorded” wording where the CSV is incomplete.
  That matches the Player audit.
- CSPaper baseline counts derived from `||` in `baseline`. The question is
  still one a reviewer would ask.

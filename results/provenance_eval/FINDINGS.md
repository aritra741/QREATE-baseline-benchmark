# Provenance-based maintenance: synthetic-edit evaluation (2026-09-28)

Code: `core/lineage/` (store, maintain), `eval/router_provenance.py` (capture / plan / apply / history),
`eval/provenance_edits.py` (this evaluation). The run maintained is the benchmark-protocol shared read with
chained long documents (`finan_chain`, `legal_chain`). The source files are never modified: each edit is
an overlay, and each policy works on its own copy of the store.

## Protocol
- **Policies** (how far a change ripples through a chained document):
  - `exact`: a chunk is reused only if its text and the carried note are identical.
  - `facts`: the note only has to state the same numbers and capitalized names.
  - `answers`: as `facts`, and the ripple also ends when an unchanged chunk that was re-read because its note changed gives the same answers as before (that chunk is the probe).
- **`+attr`** (zero extra calls; same reads as its policy): a re-read value that differs from the stored one is committed only if the edit explains it:
  - the stored value is stated verbatim and its number of occurrences changed;
  - or the new value is stated in the added text;
  - or, for a stored value not stated verbatim, the changed text names the field.
- **From scratch:** reading every edited document again with a fresh chunking (the naive recompute of changed documents).
- **Reference:** that from-scratch read, used to measure what a fresh read would say.
- **Samples:**
  - dev: seed 20260928, used while designing;
  - test: a fresh seeded draw, taken after `answers` and `+attr` were fixed.

  Each sample has 6 Finan filings and 12 Legal cases per edit kind (Legal is half chained, half single-read). The tables report the test sample.
- **Queries changed:** workload queries (80 per corpus) whose answers differ after maintenance. Only queries whose column lineage the delta touches are re-executed.

## Finan (test sample; 99 of 100 filings chained, median 118k tokens)

| Edit | Reads from scratch | exact | facts | answers | Cells changed: answers / +attr | Queries changed: answers / +attr | Required change made (+attr / reference) |
|---|---:|---:|---:|---:|---|---|---|
| irrelevant paragraph mid-document | 162 | 56 | 8 | **8** | 2 / **0** | 25 / **0** | |
| value replaced everywhere | 103 | 84 | 77 | **54** | 20 / 11 | 58 / 31 | 4 of 6 / 5 of 6 |
| long neutral block prepended | 68 | 69 | 69 | **15** | 8 / **0** | 34 / **0** | |
| long neutral block appended | 73 | 6 | 6 | **6** | 0 / 0 | 0 / 0 | |
| evidence lines deleted | 94 | 34 | 25 | **26** | 13 / 6 | 26 / 21 | 6 of 6 / 6 of 6 |
| one deleted, a copy of another added | 0 | 0 | 0 | 0 | 0 rows changed; 6 deleted, 6 inserted | 66 | |

Across the five editing kinds, `answers` made 109 reads where reading the edited documents from scratch would take 500 (22%). Irrelevant, prepended and appended text changed no cell and no query answer under `answers+attr`.

## Legal (test sample; 86 of 570 cases chained)

| Edit | Reads from scratch | exact | facts | answers | Cells changed: answers / +attr | Queries changed: answers / +attr | Required change made (+attr / reference) |
|---|---:|---:|---:|---:|---|---|---|
| irrelevant | 20 | 15 | 13 | 12 | 15 / 4 | 43 / 7 | |
| value | 13 | 13 | 13 | 13 | 35 / 25 | 64 / 51 | 9 of 12 / 9 of 12 |
| prepend | 18 | 19 | 19 | 17 | 16 / 4 | 48 / 10 | |
| append | 26 | 12 | 12 | 12 | 15 / 3 | 61 / 15 | |
| evidence | 14 | 14 | 14 | 14 | 48 / 28 | 66 / 61 | 10 of 12 / 11 of 12 |
| copy / delete | 0 | 0 | 0 | 0 | 12 deleted, 12 inserted | 74 | |

Most Legal cases fit one read, so an edited case costs one read whatever the policy. The savings there come from appended text and chained cases, and from making no reads at all for unchanged, deleted and copied documents.

## Findings
1. **Deciding whether to update is exact at the document and chunk level, and cheap.**
   - An unchanged document costs no reads.
   - A deleted document costs no reads; its row is deleted.
   - A copy of a known document costs no reads, because the memo is content-addressed.
   - Text appended past the stored chunks costs one read per document (6 instead of 73 on Finan).
2. **How much to update depends on how far the carried note ripples.**
   - `exact` re-reads everything after an edit whenever the model words the note differently (Finan prepend: 69 of 68 + 1).
   - `facts` helps only when the note's names and numbers stay the same (irrelevant: 8 instead of 56). It does not help after a prepend: the notes are long paraphrases that gain or lose details.
   - `answers` stops the ripple after one probe read in most documents (prepend: 15 reads, 5 probe cutoffs).
3. **Re-reading is noisy, and churn is the real cost of naive maintenance.**
   - A fresh read of an irrelevantly edited document disagrees with the stored cells on 30% of cells in Finan and 13% in Legal.
   - Without attribution, those disagreements are committed and change most query answers (Legal irrelevant: 43 of 80 queries).
   - Attribution keeps a stored value unless its evidence changed. This removes most of that churn (Legal irrelevant: 15 → 4 cells, 43 → 7 queries; Finan: 0 cells).
   - It still commits the edits that matter. Value adoption was the same with and without attribution (Finan 4 of 6 under `answers`, Legal 9 of 12). Deleted evidence changed the target cell in 6 of 6 (Finan) and 10 of 12 (Legal), against 6 and 11 for a fresh read.
4. **Value adoption is bounded by the extractor, not by maintenance.** A fresh read took the new value in 5 of 6 (Finan) and 9 of 12 (Legal); maintenance matched that except for one Finan filing under `answers`.
5. **Query impact is precise.** Only queries whose columns the delta touches are re-executed, and the changed ones are reported. Aggregates over the whole table change with almost any cell change, which is why copy / delete changes most answers.

## Limits
- **Position labels:** reads are keyed without the position label ("part 3 of 12"); this is a declared approximation.
- **`answers`** assumes that a note which leaves one chunk's answers unchanged leaves the following chunks' answers unchanged too. The probe tests one chunk, not all of them.
- **Attribution** relies on verbatim evidence. It can keep a stale value when an edit changes a normalized value (a converted currency, a label) without naming the field. None of the required changes in these samples were lost that way, but the samples are small (6 and 12 documents per kind).
- **Dev sample** (`finan/`, `legal/`): its prepend runs overlapped with a since-fixed race. Two documents sharing a chunk could continue from different notes, which inflated `exact` and `facts` reads there (Finan prepend 156 and 135). The test sample ran after the fix.
- **Disk:** the evaluation folder holds 1.4 GB of store copies and overlays; only reports and edit lists are committed.

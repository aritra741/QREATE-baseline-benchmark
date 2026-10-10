# The system paper: the catalogue planner (v2), what it contains, and how it is evaluated

Date: 2026-10-10. Decision (advisor, relayed 2026-10-10): the paper proposes a system that beats baselines and
carries the insights as its mechanisms; other baselines and frontier models are secondary and are not pursued now.

## 1. The object: a per-column catalogue

Before a column is read for the whole corpus, the system reads a sample of ten documents for it twice, alone and in
its group, and records, per column, without labels:

| statistic | from | used for |
|---|---|---|
| kind (number, yes/no, category, list, free text) | the schema | exemptions, reporting |
| sensitivity: share of sample documents whose value changes between the two contexts | the probe | trust (which cells not to believe), reporting |
| fill rate per context | the probe | the determined context (fill-based choice), reporting |
| grounding: share of served values stated verbatim in their document | the probe | the absence test, trust |
| position: 90th percentile of where the stated values sit | the probe | the read window |
| absence-coded: stated values in fewer than a third of filled cells | the probe | window exemption |
| vocabulary: constants the workload compares the column with (equality, IN, GROUP BY) | the workload seen so far | declared allowed values (single-valued columns) |
| cost per document | token counts | every cost decision |
| repair rate of a stronger reader (optional, needs ten labelled cells) | a labelled sample | second-look routing |

The catalogue is to this system what cardinalities and selectivities are to a relational planner: cheap, computed
once, not a model.

## 2. The planner's decisions, each tied to a finding

1. **Unit of extraction (the cost lemma, I4, I3).** On a table's first on-demand request, the planner reads *all of
   the table's remaining schema columns* in frozen prompts (at most 16 fields each), for the documents the query
   can select, and keeps everything it read. Anticipating a column costs 1–13% of a later read and, under drift, the
   probability that a schema column is needed is far above that, so the lemma says read it; there is no reuse
   history to forecast from, so first come, first served. The prompt is frozen as a byte string (order included).
2. **Windows (I7, I7b).** Columns whose stated values sit in the first third of a document (p90 ≤ 0.35), and that are
   neither lists nor absence-coded, form a separate "head" prompt cut at their largest share. Everything else reads
   the whole document. Windows and grouping are planned together, because a prompt takes the largest share of its
   columns.
3. **Vocabulary (I6).** A single-valued text column that the workload so far compares with two or more constants
   gets those constants as allowed values in its prompt; list columns never do. (The oracle contract with gold's
   labels is the ceiling, already measured: artists +0.02, legal +0.10.)
4. **Second looks (I2, I2b, the column-rate result).** Optional. With ten labelled cells per column, a stronger
   reader's net repair rate is estimated per column; second looks go to columns with a positive rate, cheapest
   documents first, within a budget of 25% of the table's extraction tokens at the stronger reader's price.
5. **Normalization and scope** as recorded (commit-time forms from the workload, documents the filter can select).
6. **The item filter (WHY_AUDIT.md §3).** A list keeps only the items stated verbatim in the document, for the
   columns whose probe shows that unstated items are unstable across contexts (invented) rather than stable
   (paraphrased truths). A stronger reader's repairs of lists are mostly this restraint; the check recovers most of
   them for nothing (recorded run: 0.250 → 0.299 on 11,001 list cells, no column losing more than 8 cells).

What the planner does *not* do, and why: forecast reuse (fails under drift, I4), pace spending (fails on lumpy
spends, I4), choose per-column prompt groups for accuracy (cells gain, queries do not, I5), route second looks by a
label-free verifier (detects under-determination, not repairability, I2b).

## 3. Flags

`QUWARTS_PLANNER=catalogue` turns the planner on in `drift_live`; `QUWARTS_PLANNER_OFF` is a comma list of
components to disable for ablations: `unit` (back to the recorded per-query batching), `windows`, `vocab`, `repair`,
`itemfilter`.
`QUWARTS_REPAIR_LABELS=<file>` supplies the labelled sample for component 4 (ten gold cells per column, drawn once
per corpus with a fixed seed); without it the component is off. The probe's reads go through the same journal as
every other read and are charged to the stream.

## 4. Evaluation

- v2 against the recorded system (v1) and DocETL on the five corpora: the drift curve (levels 0 and 100 first, then
  50, 25, 75) and the budget curve (first come, first served at 25% and 50%).
- Ablations at 100% drift: v2 minus each component, on papers, players and artists in full and on medical and legal
  where time allows.
- Replicates of v2 at 100% on papers and players for the noise floor.
- Every insight of the week appears as the reason a component exists and as the ablation that measures it.

## 5. Order of work

1. `quwarts/core/adapt/catalogue.py`: schema columns with protocol specs, the probe, the statistics, windows with
   exemptions, group planning, workload vocabulary.
2. The planner branch in `drift_live.Stream._step`, with state saved for resumes.
3. Second looks through the 32B server, charged separately.
4. Test on papers (minutes), then queue papers, players, artists, medical, legal at 100% on both jobs; then
   ablations and budgets; then the write-up around the system.

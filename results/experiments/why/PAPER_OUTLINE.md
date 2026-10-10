# Paper outline: a database built by an LLM is a set of measurements, and a planner can treat it as one

Draft structure for the system paper (2026-10-10). Numbers marked [v2] are filled from `V2/summary.json` when the
runs finish; everything else is measured already (KEY_FINDINGS_WHY.md, RESEARCH_DEPTH.md).

## 1. Introduction

- The setting: a database built from documents by an LLM for a workload that drifts; the build reads what the known
  queries need, later queries need columns the build skipped.
- The principle: *reads are not idempotent*. An extracted value is a function of the document and of the prompt it
  was asked in (set of fields: 37–42% of cells change; order: 40–44%; against 5–6% run to run), and this is a
  property of the column that holds across models (rank 0.77 between a 7B and a 32B) and across systems (DocETL).
- Consequences a system must handle: a stored value carries its prompt (materialization), keys must be extracted
  once (joins), the unit of extraction moves cost three- to tenfold where the schedule moves it 0.01 (budgets), and
  a cell can be wrong for two reasons, one of which no reader repairs.
- The system: a per-column catalogue, computed from ten documents without labels, and a planner that uses it to
  decide the unit of extraction, the read window, the vocabulary, and where a stronger reader is worth paying for.
- Results [v2]: against the recorded system and DocETL on five corpora; what each component is worth (ablations).
- Contributions: the principle with its measurements; the catalogue as the planner's statistics; the planner; the
  findings that generalize (Section 7).

## 2. Reads are not idempotent (the measurements that motivate the design)

2.1 Three sources of variation: context (set and order), model, sampling. The intervention on fixed documents.
2.2 Determinacy: the two-prompt disagreement predicts accuracy (−0.7) across models and systems, from ten documents.
2.3 Two kinds of error: under-determination (no reader fixes) and misreading (a stronger reader fixes);
    repairability is a column property, found from ten labelled cells.
2.4 What this means for a store: prompt-keyed values, canonical byte-string prompts, keys read once.

## 3. The catalogue

The statistics (kind, sensitivity, fill per context, grounding, position, absence, vocabulary, cost, repair rate),
how each is computed from ten documents, and what each decides. The analogy to cardinalities and selectivities.

## 4. The planner

4.1 Unit: all remaining schema columns at first touch, frozen prompts, narrow prompts for columns the group
    under-fills (the fill rule), the cost lemma that justifies anticipating, first come first served.
4.2 Windows: head prompts for columns whose values sit in the first third; exemptions (lists, coded absences);
    windows and grouping planned together.
4.3 Vocabulary: a declared label set is a schema input; it fixes form, not selection; never for lists.
4.4 Second looks: per-column repair rate from ten labelled cells, cheapest documents first, a token budget.
4.5 Normalization and scope, as before.
4.6 What the planner deliberately does not do: forecast, pace, group for accuracy, route by a cell-level verifier.

## 5. Evaluation [v2]

5.1 Setup: five corpora, Qwen 2.5 7B (4-bit) as the reader and 32B as the stronger reader, drift levels, budgets,
    the query score, replicates for the noise floor.
5.2 Against the recorded system and DocETL at 100% drift: score and tokens per corpus.
5.3 Ablations: each component off; which corpora each helps and hurts, and why (the findings predict the sign).
5.4 The drift curve (0, 50, 100) and the budget curve (25%, 50%).
5.5 Cost accounting in tokens and dollars, the stronger reader separately.

## 6. What the planner's failures teach (the negative results with mechanisms)

Forecasting under drift; pacing lumpy spends; grouping for accuracy (cells gain, queries do not); the label-free
verifier as a router; windows that cannot establish an absence; vocabularies for lists.

## 7. Findings that generalize

Reads carry their prompt; determinacy from ten documents; repairability from ten labels per column; the unit, not
the schedule; consistency beats per-cell accuracy for joins and grouping; a window cannot establish an absence;
a vocabulary fixes form, not selection; the first field line is answered differently.

## 8. Related work

Semantic query processing (LOTUS, Palimpzest, DocETL, ZenDB, Evaporate), workload-aware design (CliffGuard, robust
designs), cascades (SUPG, LOTUS), prompt sensitivity in NLP (Sclar et al.), prefix-sharing serving (Liu et al.),
incremental extraction (Cyclex), materialized views and caches.

## 9. Limitations

One model family at 4-bit; one benchmark family with self-made drift splits; the labelled sample for second looks;
low absolute scores; filtered aggregates over few rows.

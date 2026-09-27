# Provenance and incremental maintenance in QuWARTS

## What a cell depends on
A shared read computes `cell = LLM(render_prompt(window(doc), field lines), model)`. The window is the document's first `V3["window_tokens"]` Qwen tokens; the field lines are the description plus workload usage.

A cell's exact inputs are therefore the window text, its field spec, and the model. Text outside the window can never change a cell. This is the input fingerprint of build systems (Make, Bazel, Salsa; Mokhov et al., "Build Systems à la Carte"), which also give *early cutoff*: a recomputed value equal to the old one propagates nothing.

## Two kinds of dependency (provenance literature)
- **Local (where-provenance; Buneman, Khanna & Tan 2001).** The value is stated verbatim in the window: a year, a name, a label. Its evidence is the sentence holding it. If the edit does not touch that evidence and does not mention the attribute, the value cannot plausibly change.
- **Global (why-provenance / lineage; Cui & Widom).** The value depends on the whole window: absence ("not mentioned", or a declared absence value), counts ("number of ..."), 0/1 flags, and any value not found verbatim. Any relevant edit anywhere in the window can change it.

## Capture (no LLM calls; backfills existing runs)
- **Document:** its content hash, the window's end offset and token count, and content-defined chunks of the window.
  - Chunking uses gear/Rabin fingerprints (LBFS, rsync), so an insertion changes only nearby chunks.
  - Each chunk stores its hash and a small Bloom filter of its terms. That lets the relevance of *removed* text be tested without keeping old copies of documents.
- **Cell:** the committed value, the raw answer, the field-spec hash, the read (prompt hash), the dependency class, the evidence quote and its number of occurrences, and cue terms. Cue terms come from the attribute name, the description, the evidence and the value.
- **Workload lineage:** the columns each query reads (`templates.column_set`, aliases resolved) and a hash of each query's current answer.

## Change detection
Compare the current corpus with the stored documents:

- **New** documents: insert a row (one read).
- **Deleted** documents: delete the row (no read).
- **Changed** documents: recompute the window. If the window is identical (the edit fell outside it), nothing is stale. Otherwise the chunk diff gives the added text (new chunks) and the removed chunks (with their Bloom filters).

## Per-cell invalidation (reason codes)
**Policy `exact`:** every cell of a document whose window or field spec changed is stale. This is sound with respect to what the system itself would compute.

**Policy `evidence`** (cheaper, heuristic, measured):
- A **local** cell is stale if its evidence quote is gone, if the value's number of occurrences changed, or if the added text or a removed chunk mentions one of its cue terms or its value.
- A **global** cell is stale if the added text or a removed chunk mentions one of its cue terms.
- Any other cell is kept.

A field-spec change makes that field's cells stale in both policies.

## Updating: how much
- **Unit of work: a document.** A read costs about the window's tokens, whatever the number of fields.
- **Full read.** Use the *same* field list and prompt template as the original read, so the extraction semantics are unchanged. Then commit **only the stale cells**. Valid cells keep their values, so read noise does not churn the table.
- **Patch read.** When every stale cell of a document is local and the changed text is small (under 30% of the window), send only the changed regions with context, plus each stale field's old value and evidence. The model returns the current value, or "not in the excerpt", which escalates to a full read. This is the IVM choice between incremental and recompute (Gupta & Mumick).
- **Early cutoff.** A refreshed value equal to the old one is recorded as verified, and no queries are affected.

## Workload-prioritized, deferred maintenance (the QuWARTS twist)
- Each stale cell's priority is the number of workload queries that read its column.
- Under a token budget, documents are refreshed greedily by priority per token (deferred view maintenance; Colby et al. 1996).
- Cells left over are marked stale, and every query that reads a stale column is flagged as possibly stale.
- A column no query reads is never refreshed eagerly; it waits until a query needs it (lazy maintenance).

## Query impact
- The queries affected by a set of changed cells are those whose column lineage includes a changed column; deletes and inserts affect every query on that table.
- Affected queries are re-executed (plain SQL); answers are compared with the stored hashes, and the queries whose answers actually changed are reported.

## Versioning
Every change is appended to a history table with the old value, new value, version, reason and action. The database remains auditable.

## Guarantees and limits
- **`exact`** is sound with respect to QuWARTS's own function: it never keeps a cell whose recorded inputs changed.
- **`evidence`** can miss an update when an edit changes a global value without using any cue term. The evaluation measures that rate.
- Correctness with respect to truth is bounded by the extractor, as for any extraction system.
- Field-spec changes are tracked per field; the effect of one field's spec on other fields' answers (the shared prompt) is not tracked.

## Evaluation (synthetic edits on a copy of the corpus; source files untouched)
Edit types:

| Edit | What it does | Expected refresh |
|---|---|---|
| E1 | irrelevant paragraph inside the window | none |
| E2 | text appended past the window | none, zero reads |
| E3 | the evidence value of a local cell is changed | that cell must be refreshed, to the new value |
| E4 | long neutral text inserted at the start (shifts the window) | window change detected |
| E5 | the evidence sentence is deleted | that cell refreshed |

Metrics, for `exact` and `evidence`:

- reads and tokens, against re-reading every changed document;
- recall of required refreshes (E3, E5);
- unnecessary refreshes (E1);
- how often the refreshed value equals the edited value (E3);
- queries flagged versus queries whose answers actually changed.

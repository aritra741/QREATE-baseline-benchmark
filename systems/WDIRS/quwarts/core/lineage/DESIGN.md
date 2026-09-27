# Provenance and incremental maintenance in QuWARTS (as built, 2026-09-28)

Package `core/lineage/`. Note that `core/provenance.py` is the older entity-id module. CLI: `eval/router_provenance.py`. Evaluation: `eval/provenance_edits.py`; results in `results/provenance_eval/FINDINGS.md`.

## What a cell depends on
- A document that fits the window is read once: `cell = f(prompt(document, field list))`.
- A longer document is read as ordered chunks. Chunk *i*'s read depends on its text, the note carried from chunk *i−1*, and the field list. The cell is a vote over the chunk answers.

## Store (one SQLite file per run: `<run>/provenance/provenance.db`, plus `maintained.db`)
- **`reads`**: a content-addressed memo, the action cache of build systems (Bazel, Salsa; Mokhov et al.).
  - Single reads are keyed by the prompt hash.
  - Chunk reads are keyed by (chunk text, incoming note, field list), without the position label (a declared approximation).
  - Each row keeps the response and the outgoing note.
- **`documents`, `chunks`**: the version each document is at (hash, compressed snapshot, chunk boundaries, the read used per chunk).
- **`cells`**: each committed value and the chunks that voted for it (where-provenance). A value that no chunk states depends on the whole document (why-provenance).
- **`queries`**: tables and columns per query (column-level lineage) and a hash of its answer.
- **`history`, `versions`**: every changed cell with its old and new value, per version.
- **`meta`**: the hash of `maintained.db`. `apply` refuses to run if the database was changed outside it.

## Maintenance (`apply`)
1. **Documents.** Compare content hashes against the current corpus (the source plus an overlay of changed, added and deleted files).
2. **Chunks.** A changed chained document is realigned with its snapshot: old chunks still present verbatim keep their boundaries, and only the text between them is re-chunked. This gives stable boundaries, as content-defined chunking does (LBFS).
3. **Replay.** The document is replayed in order against the memo, and only misses are read.
   - **Early cutoff:** when a re-read passes on an equivalent note, the rest are hits again.
   - **Note equivalence by policy:** `exact` requires the same text; `facts` the same numbers and names; `answers` also accepts the note when the re-read unchanged chunk (the probe) gives the same answers as before.
4. **Attribution (optional, zero calls).** A re-read value that differs from the stored one is committed only if the edit explains it:
   - the stored value's verbatim evidence changed;
   - or the new value is in the added text;
   - or, for a stored value that is not stated verbatim, the diff names the field.

   Otherwise it is treated as read noise and the stored value is kept.
5. **Delta.** Rebuild with the system's own builder over the current reads. Diff against `maintained.db`, write only the delta, and check that the result equals the rebuild (incremental view maintenance correctness; Gupta & Mumick).
6. **Queries.** Re-execute only the queries whose lineage the delta touches, and report those whose answers changed.
7. **Budget and deadline.**
   - Documents are refreshed in order of workload use, cheapest first; those beyond the token budget are left stale and their queries flagged (deferred maintenance; Colby et al.).
   - A deadline stops new reads; every read is memoized, so a later run resumes.

## Recommended setting
`--policy answers --attribute`. On the fresh test sample (Finan) it made 22% of the reads that reading the edited filings from scratch would take. Irrelevant, prepended and appended text changed no cell. Value changes were adopted as often as by a fresh read, give or take one document.

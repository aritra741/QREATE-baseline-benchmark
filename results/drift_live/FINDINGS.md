# Real drift runs: findings (seed 0, template-paired streams; Finan not run)

Code: `systems/WDIRS/quwarts/eval/drift_live.py` (run), `drift_live_report.py` (RESULTS.md, summary.json).
Per-query records: `<corpus>/streams/<axis>_<level>.jsonl` (runtime, calls, input/output tokens, OpenRouter cost,
benchmark and tolerant accuracy, static accuracy, action, documents in scope and read, columns fetched).
Every call's usage: `<corpus>/usage.jsonl`. Reads: `build_reads.jsonl` (the W0-description build read, reused), `patch_reads.jsonl`.
Streams run: attribute/100, value/100 and the three 0% streams. Held: combined/100, the 25/50/75 levels, gradual.
Paid in this run: $4.59 (cspaper 0.17, art 0.36, legal 2.42, player 0.47, med 1.17); the build reads were paid earlier.

## What was measured
Nothing is read ahead. A column's description reaches the system only with the first query that uses it; that query
reads, then and there, the documents it can affect. Compared with the replay's reference (a full read of every
column before the stream, which the protocol does not allow) and with the static build.

## Findings, in plain words
1. Adapting is what keeps drifted queries answerable. On attribute/100 the static build scores 0.000-0.026;
   QuWARTS scores 0.065-0.429 (cspaper 0.108, art 0.283, legal 0.167, player 0.429, med 0.065).
2. Real extraction mostly matches the full-read reference. Live minus reference on attribute/100: art -0.000,
   player +0.033, med -0.018, legal -0.035 (all CIs cover 0); cspaper -0.107 [-0.220, -0.033] is the exception.
   Same-template pairs (drifted minus source): live and reference agree within noise on art, legal, player, med.
3. The cost of drift is real and larger than the replay said. Each new column costs one read of the documents in its
   scope, and most drifted queries have no filter on known columns, so the scope is the whole table. Attribute/100
   costs build + patches = 1.9x (art) to 5.8x (legal) the tokens of one full read. The replay was cheaper because its
   patches fetched every schema column at once, which needs descriptions the protocol withholds.
4. Two extraction failures, both from narrow patch prompts (1-2 fields) and not from drift itself:
   * art.field: the column is literally named "field", and the answer template says {"<field>": ...}; with two fields
     in the prompt the model keys the answer by the description ("primary artistic field"), so the parser drops it
     (0% filled live, 99% in the many-field robust read). A parser bug that any read can hit.
   * cspaper.agent_framework filled 60% live vs 20% robust and 24% gold (answers "Other" instead of null);
     reasoning_depth skews to multi-hop (148/200 live, 112 robust, 109 gold). This explains most of cspaper's gap.
5. Level-0 streams have no drift cost but still trail the reference on med (-0.046) and art (-0.038 value/0):
   the build read (W0's fields only) and the robust read (all fields) extract W0's columns differently.

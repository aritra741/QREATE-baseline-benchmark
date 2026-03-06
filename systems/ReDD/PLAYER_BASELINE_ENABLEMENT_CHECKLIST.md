# ReDD Player Baseline Enablement Checklist

This checklist is for making `systems/ReDD` a fair, runnable baseline under the same evaluation style as:

- `systems/WDIRS/test_player_query_awareness_trend.py`
- `systems/DocETL/test_player_query_awareness_trend_docetl.py`

Goal: run `Player` Q1..Q10 trend queries and produce comparable outputs:
- per-query results
- latency and token costs
- macro precision/recall/F1 using the official evaluator

## 0) Fairness Contract (Do First)

- [ ] Use the same query set: `Query/Player/query_aware_trend_queries.sql`.
- [ ] Use the same ground truth directory: `Data/Player`.
- [ ] Use the same evaluator stack from `evaluation/*` (same as WDIRS/DocETL trend scripts).
- [ ] Save run artifacts in `results/player_query_awareness_trend_redd/run_<timestamp>/...`.
- [ ] Report per-query: success, latency, tokens, rows, macro P/R/F1, errors.

Definition of fair here:
- same input queries
- same output metric definitions
- same scoring toolchain
- no hand-picking queries/runs

## 1) Fix Existing ReDD Entrypoints and Config Wiring

Current repo inconsistencies to resolve before baseline runs:

- [ ] Standardize config path references:
  - Code currently uses `cfg/*.yaml`
  - README references `configs/*.yaml`
  - choose one and align docs + scripts.
- [ ] In `scripts/main_datapop.py`, restore actual data population execution path (currently commented out).
- [ ] In `scripts/main_datapop.py`, keep `--eval` path but make it optional after population.
- [ ] Add a "trend run" mode or separate script so this path is deterministic for benchmark runs.

Suggested file edits:
- `systems/ReDD/scripts/main_datapop.py`
- `systems/ReDD/README.md`

## 2) Add Player Dataset Adapter for ReDD

ReDD is Spider-centric by default. Add a Player adapter so ReDD can read Player source docs and query metadata.

- [ ] Create a loader for Player source docs with deterministic doc IDs:
  - read from `source_data/Player/{player,team,city}/*.txt`
  - track source table and source doc path in metadata.
- [ ] Emit/consume query metadata from `query_aware_trend_queries.sql` parsed into `Q1..Q10`.
- [ ] Support schema artifacts expected by ReDD:
  - query-specific schema JSON
  - doc info mappings

Suggested file additions:
- `systems/ReDD/core/data_loader/data_loader_player.py`
- register in `systems/ReDD/core/data_loader/__init__.py`

## 3) Build ReDD Trend Runner for Player (Main Missing Piece)

Add a dedicated trend script mirroring WDIRS/DocETL harness behavior.

- [ ] Create `systems/ReDD/test_player_query_awareness_trend_redd.py`.
- [ ] Parse Q1..Q10 SQLs from `Query/Player/query_aware_trend_queries.sql`.
- [ ] For each query:
  - run ISD (or load cached schema) for query-specific schema
  - run TDP to produce extracted tabular data for that query
  - produce predicted result rows for the query
  - evaluate with official evaluator
- [ ] Save:
  - `query_tables/Qx.csv` and `Qx.json`
  - `query_results/Qx/acc.json`
  - `trend_metrics.json` and `trend_metrics.csv`
  - `token_cost.json`
  - plots under `plots/`

Mandatory output schema should match existing trend scripts as closely as possible:
- `query_id`, `query_text`, `success`, `latency_s`, `prompt_tokens`, `completion_tokens`,
  `total_tokens`, `result_rows`, `macro_f1`, `macro_precision`, `macro_recall`, `error`.

## 4) Ensure Query-Result Execution Layer is Comparable

Paper separates schema/data extraction from SQL execution focus, but benchmark needs final query result rows.

- [ ] Decide and document execution policy:
  - either SQL over query-local extracted tables in SQLite (recommended),
  - or direct projection/join/filter flow that is equivalent and deterministic.
- [ ] Materialize per-query extracted tables to query-local SQLite DB:
  - `query_eval_dbs/Qx.db`.
- [ ] Execute original SQL against query-local DB (or equivalent deterministic pipeline).
- [ ] Return final rows only from this execution path.

Why this is required:
- avoids evaluator mismatch with doc-level extraction outputs
- matches WDIRS/DocETL trend harness semantics

## 5) Integrate Official Evaluator (Same as Other Systems)

Reuse existing evaluator utilities exactly.

- [ ] Import and use:
  - `evaluation.gt_runner.GtRunner`
  - `evaluation.sql_parser.SqlParser`
  - `evaluation.row_matcher.RowMatcher`
  - `evaluation.config.EvalSettings`
- [ ] Reuse identity-column inference approach from WDIRS trend script.
- [ ] Persist per-query `acc.json` with both quality and cost/latency fields.

## 6) Token Accounting Policy (Fair and Explicit)

ReDD has mixed token accounting paths. Choose one policy and document it in script logs.

- [ ] Preferred: count provider usage tokens when available.
- [ ] Fallback: deterministic approximation (chars/4) only if provider tokens unavailable.
- [ ] Keep policy identical across all Q1..Q10 in a run.
- [ ] Log policy at run start and write to `token_cost.json`.

## 7) ReDD Correction Module Integration (SCAPE/SCAPE-Hyb)

For paper-faithful baseline, correction should be active and reproducible.

- [ ] Add command-line switch for correction mode:
  - `none`
  - `scape`
  - `scape_hyb`
- [ ] Add calibration knobs:
  - `alpha`
  - `lambda` (for hybrid)
  - train/calibration sample sizes
- [ ] Ensure calibration/train split is fixed by seed for reproducibility.
- [ ] Persist correction stats (predicted errors, detected errors, extra cost).

Important:
- current code has conformal analysis functions but not a clean end-to-end benchmark wiring; wire these modes into the Player trend runner.

## 8) Remove Known Blockers in Current ReDD Code

- [ ] Implement mapping fallback in evaluator:
  - `EvalDataPop._load_or_generate_mapping` currently raises `NotImplementedError` if files are absent.
  - add deterministic auto-mapping for Player trend runs.
- [ ] Fill or remove empty `core/evaluation/eval_schemagen.py`.
- [ ] Ensure dataset prep scripts produce filenames expected by active loaders:
  - loaders expect `queries.json`, many folders currently have `queries_drc.json`.

## 9) Reproducibility and Runbook

- [ ] Add a one-command run instruction for the full trend benchmark.
- [ ] Fix random seeds for:
  - Python
  - numpy
  - torch (if used)
- [ ] Log software/model versions and model endpoint.
- [ ] Add a "warm/cold cache" policy note and keep it fixed.

Suggested doc update:
- `systems/ReDD/README.md` add "Player Trend Benchmark" section.

## 10) Acceptance Criteria (Done Definition)

Mark baseline as ready only when all pass:

- [ ] `python systems/ReDD/test_player_query_awareness_trend_redd.py` runs Q1..Q10 end-to-end.
- [ ] Produces run directory with:
  - [ ] `trend_metrics.json`
  - [ ] `trend_metrics.csv`
  - [ ] `token_cost.json`
  - [ ] `plots/query_awareness_trend_summary.png`
  - [ ] per-query `query_results/Qx/acc.json`
- [ ] No missing-query failures in parser or data loader.
- [ ] Evaluator outputs macro P/R/F1 for every query (0 allowed, missing not allowed).
- [ ] Logs clearly state correction mode and token policy.

## 11) Minimal Implementation Order (Fastest Path)

If you want the shortest route to first fair run:

1. [ ] Add `test_player_query_awareness_trend_redd.py` with official evaluator wiring.
2. [ ] Use a query-local extraction path for Player docs (even before full generalized loader).
3. [ ] Materialize query-local SQLite and execute SQL to get final rows.
4. [ ] Emit WDIRS-like metric files and plots.
5. [ ] Add correction mode switches (`none` first, then `scape`, then `scape_hyb`).

This gives a working baseline quickly, then paper-faithful correction options can be layered in.


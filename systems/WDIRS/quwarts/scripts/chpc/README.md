# Drift runs on a GPU machine with Ollama

These scripts run the real drift experiment (`eval/drift_live.py`) with Qwen 2.5 7B, served by a local Ollama. Nothing goes through OpenRouter.

Results go to `results/drift_live_ollama/`, separate from the OpenRouter runs, because the build is read again with the local model.

## Commands (plain Linux, no root)

```bash
git clone --depth 1 -b experiment/drift-design git@github.com:aritra741/QREATE-baseline-benchmark.git UDA-Bench-main
cd UDA-Bench-main
bash systems/WDIRS/quwarts/scripts/chpc/setup_env.sh           # once: Python env, Ollama, model, smoke test
nohup bash systems/WDIRS/quwarts/scripts/chpc/run_drift.sh > logs/run.out 2>&1 &
tail -f logs/drift.log
```

**`setup_env.sh`**:

- creates `~/venvs/quwarts` from a Python 3.10 or newer (if none is installed, it gets one with `uv`);
- installs `requirements-drift.txt`;
- unpacks Ollama into `~/ollama` (the official `ollama-linux-amd64.tar.zst`);
- pulls the model into `OLLAMA_MODELS`, which defaults to `/scratch/general/vast/$USER/ollama_models` if that disk exists, else `~/ollama_models`;
- makes one test call to the model, runs the unit tests, and loads each corpus's design.

It's safe to run again.

**`run_drift.sh [corpora] [streams]`**:

- starts Ollama on a free port;
- runs the experiment (defaults: `cspaper,art,legal,player,med` and `fixed+headline`);
- writes the report.

If it stops, run it again and it resumes from the saved state and the read journals. Add `finan` to the corpus list if you want it; it's the slowest because its documents are long.

Both scripts take options as environment variables:

- `OLLAMA_MODEL` (default `qwen2.5:7b-instruct`);
- `AXES` (default `attribute`; e.g. `attribute,value,combined`);
- `OLLAMA_NUM_PARALLEL` (default 8; concurrent calls per corpus);
- `CORPUS_JOBS` (default: all corpora at once, one process each on the shared server; each job adds `OLLAMA_NUM_PARALLEL` slots, about 7 GB of KV cache at a 16k context, so set 1 on a 16 GB GPU);
- `OLLAMA_NUM_CTX` (default 16384);
- `VENV`, `OLLAMA_DIR` and `OLLAMA_MODELS`.

If you use SLURM, `drift_live_ollama.slurm` (one array task per corpus) and `drift_live_report.slurm` do the same thing.

## What runs

- **Fixed-question levels** (`fixed`): the same test queries at 0/25/50/75/100% drift.
  - The test queries are the `attribute/100` stream.
  - At level p, a seeded, nested p% of them is withheld from the build workload. The rest are in it, so their columns are read at build time.
  - Each level has its own build read. Level 100 is the W0 build.
- **Paired streams** (`fixed+headline`): the paired streams run on OpenRouter (attribute/100, value/100, and the three 0% streams).
  - `all` runs all 18 paired streams.
  - `everything` runs the fixed levels plus all 18.

Per query, the scripts record:

- runtime;
- calls, input tokens and output tokens (Ollama's counts);
- `cost_usd`: the OpenRouter list-price equivalent, for comparison only;
- accuracy (benchmark and tolerant), and the static build's accuracy;
- action, documents read, and whether the build anticipated the query.

Every call is also logged in `usage.jsonl`. `maybe_truncated` flags prompts that came within `num_predict` tokens of the context window, because Ollama cuts longer prompts without an error.

## GPU memory

- **Default model** (`qwen2.5:7b-instruct`, 4-bit, about 5 GB): fits a 16 GB GPU with 8 parallel slots at a 16k context.
- **`qwen2.5:7b-instruct-fp16`** (about 15 GB of weights plus about 7 GB of KV cache): needs a 24 GB+ GPU such as an A5000, A6000, L40S, A100 or H100.
  - These unquantized weights are the closest to what OpenRouter serves, so use them if you want numbers comparable with the OpenRouter runs.
  - Otherwise, compare runs only within the same model.

## Bringing results back

Commit `results/drift_live_ollama/` and push, or `rsync` it back. `RESULTS.md` has the fixed-level tables, and `fixed_levels.csv` has one row per corpus, axis and level.

## Before a long run: the audit (no GPU, minutes)

```bash
bash systems/WDIRS/quwarts/scripts/chpc/audit_oracle.sh cspaper,player
```

This runs the fixed levels against a stand-in extractor whose answers never depend on the prompt. Every level must score the same; any query whose data differs is listed with its cause. After a real run, `python -m quwarts.eval.drift_live_audit --levels cspaper,player` (with `QUWARTS_LLM=ollama`) lists which queries differ between levels and why. See `eval/DRIFT_LIVE_AUDIT.md`.

## Checking the wiring without a GPU

`tests/mock_ollama.py` is a stand-in server. It answers from recorded responses by prompt hash, and returns every field as null otherwise. Run through the Ollama client, the cspaper W0 build plus the attribute/100 stream reproduces the OpenRouter run exactly (0.108, 6 patches).

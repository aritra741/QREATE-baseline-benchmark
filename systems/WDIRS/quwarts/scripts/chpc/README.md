# Drift runs on CHPC with Ollama

These scripts run the real drift experiment (`eval/drift_live.py`) with Qwen 2.5 7B, served by Ollama on a CHPC GPU node. Nothing goes through OpenRouter. Results go to `results/drift_live_ollama/`, separate from the OpenRouter runs, because the build is read again with the local model.

## What runs

- **Fixed-question levels** (`--streams fixed`): the same test queries at 0/25/50/75/100% drift.
  - The test queries are the `attribute/100` stream.
  - At level p, a seeded, nested p% of them is withheld from the build workload. The rest are in it, so their columns are read at build time.
  - Each level has its own build read. Level 100 is the W0 build.
  - Add `AXES=attribute,value,combined` for the other axes. That's five more builds per axis.
- **Paired streams** (`fixed+headline`): the paired streams we ran on OpenRouter (attribute/100, value/100, and the three 0% streams).
  - `all` runs all 18 paired streams.
  - `everything` runs the fixed levels plus all 18.

Per query, the scripts record:

- runtime;
- calls, input tokens and output tokens (Ollama's counts);
- `cost_usd`: what those tokens would cost at the OpenRouter list price, for comparison only;
- accuracy (benchmark and tolerant), and the static build's accuracy;
- action, documents read, and whether the build had anticipated the query.

Every call is also logged in `usage.jsonl`. `maybe_truncated` flags any prompt that got within `num_predict` tokens of the context window, because Ollama cuts longer prompts without an error.

## One-time setup

```bash
git clone -b experiment/drift-design git@github.com:aritra741/QREATE-baseline-benchmark.git UDA-Bench-main
cd UDA-Bench-main
module load python/3.10       # or miniforge; any Python >= 3.10
python3 -m venv ~/venvs/quwarts && source ~/venvs/quwarts/bin/activate
pip install -r systems/WDIRS/quwarts/scripts/chpc/requirements-drift.txt
```

The branch must include this commit and the `results/drift_design` and `results/drift_paired` design files. Push from the laptop first.

## Run

```bash
cd UDA-Bench-main
JOB=$(sbatch --parsable -A <account> -p <gpu-partition> systems/WDIRS/quwarts/scripts/chpc/drift_live_ollama.slurm)
sbatch -A <account> -p <cpu-partition> --dependency=afterany:$JOB systems/WDIRS/quwarts/scripts/chpc/drift_live_report.slurm
```

- **Where to submit from:** submit from the repository root (or set `REPO`). Logs go to `logs/`.
- **What the array covers:** one task per corpus: cspaper, art, legal, player, med. Use `--array=0-5` to add finan, which is the slowest because its documents are long.
- **Options** are environment variables passed to `sbatch --export=ALL,...`:
  - `OLLAMA_MODEL` (default `qwen2.5:7b-instruct`);
  - `STREAMS`;
  - `AXES`;
  - `OLLAMA_NUM_PARALLEL` (default 8);
  - `OLLAMA_NUM_CTX` (default 16384);
  - `OLLAMA_MODELS` (default `/scratch/general/vast/$USER/ollama_models`);
  - `QUWARTS_SCRATCH`;
  - `VENV`.
- **Resuming:** the run is resumable. If a job hits its time limit, submit it again and it continues from the saved state and the read journals.
- **Progress:** the log gets one line per query (a bar, the action, documents read, tokens, seconds, and the stream's running totals). During each build read, it also prints a line every minute.

## GPU memory

- **Default model** (`qwen2.5:7b-instruct`, 4-bit, about 5 GB): fits a 16 GB GPU with 8 parallel slots at a 16k context.
- **`qwen2.5:7b-instruct-fp16`** (about 15 GB of weights plus about 7 GB of KV cache at 8 × 16k): needs a 24 GB+ GPU such as an A5000, A6000, L40S, A100 or H100.
  - These unquantized weights are the closest to what OpenRouter serves, so use them if you want numbers comparable with the OpenRouter runs.
  - Otherwise, compare runs only within the same model.

## Bringing results back

Commit `results/drift_live_ollama/` on CHPC and push, or `rsync` it back. `RESULTS.md` includes the fixed-level tables, and `fixed_levels.csv` has one row per corpus, axis and level.

## Checking the wiring without a GPU

`tests/mock_ollama.py` is a stand-in server. It answers from recorded responses by prompt hash, and returns every field as null otherwise. Run through the Ollama client, the cspaper W0 build plus the attribute/100 stream reproduces the OpenRouter run exactly (0.108, 6 patches).

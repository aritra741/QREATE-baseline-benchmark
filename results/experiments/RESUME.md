# Resuming the experiments on a new Slurm job

Everything is resumable: finished steps are skipped, interrupted steps continue from their journals (no read is paid
twice). Run these from the repository root on the new GPU node.

## 1. Experiment runner (all remaining steps)

```bash
cd ~/Downloads/QREATE-baseline-benchmark
source ~/venvs/quwarts/quwarts.env      # OLLAMA_MODELS=/scratch/general/vast/u1592362/ollama_models, Ollama on PATH
setsid nohup ~/venvs/quwarts/bin/python -u systems/WDIRS/quwarts/scripts/chpc/experiments/runner.py \
    >> results/experiments/runner.out 2>&1 < /dev/null &
```

- It starts its own Ollama servers when none is up (`ensure_server.sh`: `main` for the 4-bit 7B model, one extra for
  the 16-bit / Llama / Qwen 32B steps), checks each is on the GPU, and records them in `results/experiments/servers/`.
- Server sizes follow the GPU (`ensure_server.sh`): with 60 GB or more, main has 16 slots and extra servers 8; under
  60 GB (e.g. an A800 40GB), main has 8 slots, Llama / 16-bit 4 slots at 16k beside it, and the Qwen 32B steps take
  the whole GPU through `gpu_exclusive.sh` (DocETL paused with SIGSTOP, main stopped, both restored afterwards; see
  `results/experiments/logs/gpu_exclusive.log`).
- The first GPU step is the prompt guard (`G0-prompt-guard`, already done; reset it with
  `runner.py --reset G0-prompt-guard` after any change to prompt or field-spec code).
- Status: `python systems/WDIRS/quwarts/scripts/chpc/experiments/runner.py --status` (or `results/experiments/STATUS.md`).
  Events with times, nodes, Slurm jobs, exit codes and log tails: `results/experiments/status.jsonl`. Per-step logs:
  `results/experiments/logs/<step>.log`.
- A step that was running when the job ended shows `running-or-interrupted` and is re-run first in its lane.

## 2. DocETL drift baseline (art and legal unfinished)

DocETL needs an Ollama server with the 4-bit model at a 32k context. After the runner has started its `main` server:

```bash
cd ~/Downloads/QREATE-baseline-benchmark/systems/DocETL
source ~/venvs/quwarts/quwarts.env
eval "$(bash ../WDIRS/quwarts/scripts/chpc/experiments/ensure_server.sh main)"   # exports OLLAMA_HOST
export OLLAMA_MODEL=qwen2.5:7b-instruct OLLAMA_NUM_CTX=32768 QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama
for c in art legal; do
  nohup python -u run_docetl_drift.py --corpus $c --threads 4 >> ../../logs/docetl_$c.log 2>&1 &
done
```

Each query's result is kept (`results/docetl_drift_ollama/<corpus>/per_query.json`); finished queries are skipped.
cspaper, player and med are complete for the drift test queries.

## 3. After results land

- Analyses that read finished runs: `python -m quwarts.eval.exp_analysis policies --corpus <c>`, `querytypes`,
  `accounting` (from `systems/WDIRS` with `PYTHONPATH=$PWD`); the runner also refreshes accounting (`Z-accounting`).
- Findings go to `FINDINGS.md` (log) and `SUMMARY.md` (by research question).

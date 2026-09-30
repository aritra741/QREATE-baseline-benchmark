#!/usr/bin/env bash
# Start Ollama and run the drift experiment, then write the report. Resumable: run it again after a stop.
# Run setup_env.sh once first. Keep it alive after you log out with nohup (or run it inside tmux/screen):
#
#   nohup bash systems/WDIRS/quwarts/scripts/chpc/run_drift.sh > logs/run.out 2>&1 &
#   tail -f logs/drift.log
#
# Arguments (optional): corpora (comma list; default cspaper,art,legal,player,med; add finan if you want it,
# it is the slowest) and streams (default fixed+headline; also fixed, all, everything).
# Environment: AXES (default attribute; e.g. attribute,value,combined), OLLAMA_NUM_PARALLEL (default 8; concurrent calls
# per corpus), CORPUS_JOBS (corpora run at once, each its own process on the shared server; default all of them; every
# job adds OLLAMA_NUM_PARALLEL slots, about 7 GB of KV cache at a 16k context, so use 1 on a 16 GB GPU),
# OLLAMA_NUM_CTX (default 16384), VENV (default ~/venvs/quwarts). Per-corpus output also goes to logs/drift_<corpus>.log.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)
VENV=${VENV:-$HOME/venvs/quwarts}
[ -f "$VENV/quwarts.env" ] || { echo "run setup_env.sh first"; exit 1; }
source "$VENV/quwarts.env"
CORPORA=${1:-cspaper,art,legal,player,med}
STREAMS=${2:-fixed+headline}
AXES=${AXES:-attribute}
PARALLEL=${OLLAMA_NUM_PARALLEL:-8}
NUM_CTX=${OLLAMA_NUM_CTX:-16384}
IFS=, read -ra CORPUS_LIST <<< "$CORPORA"
JOBS=${CORPUS_JOBS:-${#CORPUS_LIST[@]}}
mkdir -p "$REPO/logs"

# Ollama on a free port (other users may share the node), one model loaded, a context window that fits our prompts.
PORT=$(python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
export OLLAMA_HOST=127.0.0.1:$PORT OLLAMA_NUM_PARALLEL=$((PARALLEL * JOBS)) OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=24h \
       OLLAMA_CONTEXT_LENGTH=$NUM_CTX
ollama serve > "$REPO/logs/ollama.log" 2>&1 &
OLPID=$!
trap 'kill $OLPID 2> /dev/null || true' EXIT
for _ in $(seq 1 60); do curl -sf "http://$OLLAMA_HOST/api/tags" > /dev/null && break; sleep 1; done
curl -sf "http://$OLLAMA_HOST/api/tags" > /dev/null || { echo "ollama did not start; see logs/ollama.log"; exit 1; }
# A bare ollama binary without its lib/ollama/cuda_* folder silently falls back to the CPU (hours per call).
if command -v nvidia-smi > /dev/null && ! grep -q 'inference compute.*library=CUDA' "$REPO/logs/ollama.log"; then
  echo "ollama ($(command -v ollama)) found no GPU; see 'inference compute' in logs/ollama.log." \
       "Use a full install (e.g. module load ollama) and fix PATH in $VENV/quwarts.env"; exit 1
fi

cd "$REPO/systems/WDIRS"
export PYTHONPATH=$PWD QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama OLLAMA_NUM_CTX=$NUM_CTX
echo "$(date) corpora=$CORPORA streams=$STREAMS axes=$AXES model=$OLLAMA_MODEL parallel=$PARALLEL jobs=$JOBS" \
    | tee -a "$REPO/logs/drift.log"
# Each corpus keeps its own state folder, so corpora run as independent processes; lines carry the corpus name.
# Track the corpus pipelines by pid: `jobs` and a bare `wait` would also count the ollama server.
PIDS=()
running() { local n=0 p; for p in "${PIDS[@]}"; do kill -0 "$p" 2> /dev/null && n=$((n + 1)); done; echo $n; }
for c in "${CORPUS_LIST[@]}"; do
  while [ "$(running)" -ge "$JOBS" ]; do sleep 10; done
  python -u -m quwarts.eval.drift_live --corpus "$c" --run --streams "$STREAMS" --axes "$AXES" \
      --deadline 0 --workers "$PARALLEL" 2>&1 | grep --line-buffered -v "loaded .* ground-truth\|derived baseline\|\[INFO\]" \
      | tee -a "$REPO/logs/drift_$c.log" "$REPO/logs/drift.log" &
  PIDS+=($!)
done
wait "${PIDS[@]}" || true
python -m quwarts.eval.drift_live --report > "$REPO/logs/report.md" 2> /dev/null
echo "$(date) done: results in results/drift_live_ollama/ (RESULTS.md, fixed_levels.csv); report also in logs/report.md" \
    | tee -a "$REPO/logs/drift.log"

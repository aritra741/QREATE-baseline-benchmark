#!/bin/bash
# QuWARTS real drift runs with a local Qwen 2.5 7B served by Ollama, one corpus per array task.
#   sbatch -A <account> -p <gpu-partition> systems/WDIRS/quwarts/scripts/chpc/drift_live_ollama.slurm
# See README.md next to this file (setup, GPU memory, what gets written).
#SBATCH --job-name=quwarts-drift
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --array=0-4
#SBATCH --output=logs/%x-%A_%a.out
set -euo pipefail

CORPORA=(cspaper art legal player med finan)          # --array=0-5 adds finan (long documents: the slowest)
CORPUS=${CORPUS:-${CORPORA[${SLURM_ARRAY_TASK_ID:-0}]}}
REPO=${REPO:-$SLURM_SUBMIT_DIR}                        # submit from the repository root, or set REPO
MODEL=${OLLAMA_MODEL:-qwen2.5:7b-instruct}             # qwen2.5:7b-instruct-fp16: unquantized, closest to OpenRouter
STREAMS=${STREAMS:-fixed+headline}                     # fixed | fixed+headline | all | everything
AXES=${AXES:-attribute}                                # fixed levels: attribute[,value,combined]
PARALLEL=${OLLAMA_NUM_PARALLEL:-8}                     # concurrent requests (= --workers)
NUM_CTX=${OLLAMA_NUM_CTX:-16384}                       # prompts reach ~12k tokens; Ollama cuts longer ones silently
VENV=${VENV:-$HOME/venvs/quwarts}                      # python env with requirements-drift.txt

mkdir -p "$REPO/logs"
module load ollama
[ -f "$VENV/bin/activate" ] && source "$VENV/bin/activate"

# Ollama on a free port of this node (CHPC's recipe), models outside the 50 GB home quota.
export OLLAMA_MODELS=${OLLAMA_MODELS:-/scratch/general/vast/$USER/ollama_models}
mkdir -p "$OLLAMA_MODELS"
OLPORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
export OLLAMA_HOST=127.0.0.1:$OLPORT
export OLLAMA_NUM_PARALLEL=$PARALLEL OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=24h OLLAMA_CONTEXT_LENGTH=$NUM_CTX
ollama serve > "$REPO/logs/ollama-${SLURM_JOB_ID:-local}-${CORPUS}.log" 2>&1 &
OLPID=$!
trap 'kill $OLPID 2>/dev/null || true' EXIT
for _ in $(seq 1 90); do curl -sf "http://$OLLAMA_HOST/api/tags" > /dev/null && break; sleep 2; done
curl -sf "http://$OLLAMA_HOST/api/tags" > /dev/null || { echo "ollama did not start"; exit 1; }
ollama list | awk '{print $1}' | grep -qx "$MODEL" || ollama pull "$MODEL"
nvidia-smi --query-gpu=name,memory.total --format=csv || true

cd "$REPO/systems/WDIRS"
export PYTHONPATH=$PWD QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama OLLAMA_MODEL=$MODEL OLLAMA_NUM_CTX=$NUM_CTX
export QUWARTS_SCRATCH=${QUWARTS_SCRATCH:-/scratch/general/vast/$USER/quwarts_scratch}
echo "corpus=$CORPUS model=$MODEL streams=$STREAMS axes=$AXES parallel=$PARALLEL num_ctx=$NUM_CTX"
# Resumable: a rerun of the same command continues from the saved state and the read journals.
python3 -u -m quwarts.eval.drift_live --corpus "$CORPUS" --run --streams "$STREAMS" --axes "$AXES" \
    --deadline 0 --workers "$PARALLEL"

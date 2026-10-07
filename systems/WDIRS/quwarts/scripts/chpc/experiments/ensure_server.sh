#!/usr/bin/env bash
# Print `export OLLAMA_HOST=...` for a running Ollama server named NAME, starting one if needed:
#   eval "$(bash ensure_server.sh main)"   # the 4-bit server the recorded runs used (port 46709 if it is up)
#   eval "$(bash ensure_server.sh fp16)"   # a second server for the 16-bit model
# Every server stores models in $OLLAMA_MODELS (quwarts.env: /scratch/general/vast/u1592362/ollama_models), uses the
# recorded runs' settings (16 slots, 32k context, one loaded model), and must report a CUDA device. Its port, pid,
# node and Slurm job go to results/experiments/servers/NAME.json, so a later step (or a resumed run) reuses it.
set -euo pipefail
NAME=${1:?server name}
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../../.." && pwd)
source "${VENV:-$HOME/venvs/quwarts}/quwarts.env"
DIR=$REPO/results/experiments/servers
mkdir -p "$DIR" "$REPO/results/experiments/logs"
INFO=$DIR/$NAME.json
up() { curl -sf "http://$1/api/tags" > /dev/null 2>&1; }

if [ "$NAME" = main ] && up 127.0.0.1:46709; then echo "export OLLAMA_HOST=127.0.0.1:46709"; exit 0; fi
if [ -f "$INFO" ]; then
  HOST=$(python -c "import json; d = json.load(open('$INFO')); print(d['host'] if d['node'] == '$(hostname)' else '')")
  if [ -n "$HOST" ] && up "$HOST"; then echo "export OLLAMA_HOST=$HOST"; exit 0; fi
fi
# One extra server at a time beside main (GPU memory): stop any other non-main server this node started.
for f in "$DIR"/*.json; do
  [ -e "$f" ] || continue
  other=$(basename "$f" .json); case "$other" in main*) continue ;; esac; [ "$other" = "$NAME" ] && continue
  read -r opid onode < <(python -c "import json; d = json.load(open('$f')); print(d['pid'], d['node'])")
  if [ "$onode" = "$(hostname)" ] && kill -0 "$opid" 2> /dev/null; then
    echo "$(date -Is) stopping server $other (pid $opid) to start $NAME" >> "$REPO/results/experiments/logs/ollama_$other.log"
    kill "$opid"; sleep 5
  fi
  rm -f "$f"
done
PORT=$(python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
LOG=$REPO/results/experiments/logs/ollama_$NAME.log
echo "$(date -Is) starting server $NAME on port $PORT (models in $OLLAMA_MODELS)" >> "$LOG"
# Slots (on a GPU of 60 GB or more): 16 as in the recorded runs (main); any other server gets 8, since Ollama sizes 16 slots at 32k beyond the
# GPU memory left beside the main server, and would put the rest on the CPU.
# The 32B model (20 GB at 4-bit, about 8.6 GB of KV cache per slot at 32k) gets 4 slots at a 16k context.
# mainB: the main server's settings on a second node (a second runner there; see steps.py lane gpu2).
PARALLEL=16; CTX=32768; case "$NAME" in main*) ;; *) PARALLEL=8 ;; esac; [ "$NAME" = qwen32b ] && PARALLEL=4 && CTX=16384
# A GPU under 60 GB (e.g. A800 40GB): main gets 8 slots (about 19 GB), Llama / 16-bit 4 slots at 16k beside it, and the
# 32B model the whole GPU (gpu_exclusive.sh stops main and pauses DocETL for its steps).
GPU_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
if [ "${GPU_MB:-0}" -lt 60000 ]; then
  case "$NAME" in
    main) PARALLEL=8 ;;
    qwen32b) PARALLEL=2; CTX=16384 ;;  # 4 slots put 2.4 of 43.5 GB on the CPU on a 40 GB A800
    *) PARALLEL=4; CTX=16384 ;;
  esac
fi
# The 32B model on a GPU of 100 GB or more (H200): 8 slots at 16k (about 55 GB with the weights), matching a stream's 8 workers.
[ "$NAME" = qwen32b ] && [ "${GPU_MB:-0}" -ge 100000 ] && PARALLEL=8
# main2: a second main server pinned to GPU 1 (two-GPU nodes), so the runner and DocETL do not share slots.
GPUS=""; [ "$NAME" = main2 ] && { PARALLEL=8; CTX=32768; GPUS=1; }
CUDA_VISIBLE_DEVICES=${GPUS:-${CUDA_VISIBLE_DEVICES:-}} OLLAMA_HOST=127.0.0.1:$PORT OLLAMA_NUM_PARALLEL=$PARALLEL OLLAMA_CONTEXT_LENGTH=$CTX OLLAMA_MAX_LOADED_MODELS=1 \
  OLLAMA_KEEP_ALIVE=72h OLLAMA_MODELS=$OLLAMA_MODELS setsid nohup ollama serve >> "$LOG" 2>&1 < /dev/null &
PID=$!
for _ in $(seq 1 90); do up "127.0.0.1:$PORT" && break; sleep 1; done
up "127.0.0.1:$PORT" || { echo "server $NAME did not start; see $LOG" >&2; exit 1; }
# Only this start's lines count (the log is appended across starts).
awk -v p="$PORT" 'index($0, "starting server '"$NAME"' on port " p) {on = 1} on' "$LOG" | grep -q 'inference compute.*library=CUDA' || { echo "server $NAME found no GPU; see $LOG" >&2; kill $PID; exit 1; }
python - << EOF
import json
json.dump({"name": "$NAME", "host": "127.0.0.1:$PORT", "pid": $PID, "node": "$(hostname)",
           "slurm_job": "${SLURM_JOB_ID:-}", "num_parallel": $PARALLEL, "context": $CTX, "models_dir": "$OLLAMA_MODELS", "started": "$(date -Is)"},
          open("$INFO", "w"), indent=1)
EOF
echo "export OLLAMA_HOST=127.0.0.1:$PORT"

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
PORT=$(python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
LOG=$REPO/results/experiments/logs/ollama_$NAME.log
echo "$(date -Is) starting server $NAME on port $PORT (models in $OLLAMA_MODELS)" >> "$LOG"
# Slots: 16 as in the recorded runs; the 16-bit model (15 GB) gets 8, since Ollama sizes 16 slots at 32k beyond the
# GPU memory left beside the main server, and would put the rest on the CPU.
PARALLEL=16; [ "$NAME" = fp16 ] && PARALLEL=8
OLLAMA_HOST=127.0.0.1:$PORT OLLAMA_NUM_PARALLEL=$PARALLEL OLLAMA_CONTEXT_LENGTH=32768 OLLAMA_MAX_LOADED_MODELS=1 \
  OLLAMA_KEEP_ALIVE=72h OLLAMA_MODELS=$OLLAMA_MODELS setsid nohup ollama serve >> "$LOG" 2>&1 < /dev/null &
PID=$!
for _ in $(seq 1 90); do up "127.0.0.1:$PORT" && break; sleep 1; done
up "127.0.0.1:$PORT" || { echo "server $NAME did not start; see $LOG" >&2; exit 1; }
# Only this start's lines count (the log is appended across starts).
awk -v p="$PORT" 'index($0, "starting server '"$NAME"' on port " p) {on = 1} on' "$LOG" | grep -q 'inference compute.*library=CUDA' || { echo "server $NAME found no GPU; see $LOG" >&2; kill $PID; exit 1; }
python - << EOF
import json
json.dump({"name": "$NAME", "host": "127.0.0.1:$PORT", "pid": $PID, "node": "$(hostname)",
           "slurm_job": "${SLURM_JOB_ID:-}", "num_parallel": $PARALLEL, "models_dir": "$OLLAMA_MODELS", "started": "$(date -Is)"},
          open("$INFO", "w"), indent=1)
EOF
echo "export OLLAMA_HOST=127.0.0.1:$PORT"

#!/usr/bin/env bash
# Run a command with the whole GPU (for the 32B model on a GPU under 60 GB): pause the DocETL processes (SIGSTOP, so
# no call fails; they resume where they were), stop the main Ollama server, run the command, then restart main and
# resume DocETL, whatever the command's exit status. On a GPU of 60 GB or more it just runs the command.
#   bash gpu_exclusive.sh <command...>
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../../../../../.." && pwd)
GPU_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
if [ "${GPU_MB:-0}" -ge 60000 ]; then exec "$@"; fi
LOG=$REPO/results/experiments/logs/gpu_exclusive.log
PIDS=$(pgrep -u "$USER" -f "run_docetl_drift.py" | tr '\n' ' ')
echo "$(date -Is) pausing DocETL ($PIDS) and stopping main for: $*" >> "$LOG"
[ -n "$PIDS" ] && kill -STOP $PIDS
MAIN=$REPO/results/experiments/servers/main.json
if [ -f "$MAIN" ]; then
  MPID=$(python -c "import json; print(json.load(open('$MAIN'))['pid'])"); kill "$MPID" 2> /dev/null; sleep 5; rm -f "$MAIN"
fi
restore() {
  eval "$(bash "$HERE/ensure_server.sh" main)" >> "$LOG" 2>&1
  [ -n "$PIDS" ] && kill -CONT $PIDS
  echo "$(date -Is) main restarted, DocETL resumed" >> "$LOG"
}
trap restore EXIT
"$@"

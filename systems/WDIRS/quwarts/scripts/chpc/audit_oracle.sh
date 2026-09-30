#!/usr/bin/env bash
# The fixed drift levels against an extractor whose answers never depend on the prompt (no GPU, a few minutes per
# corpus). Every level must score the same; the audit lists any query whose data differs and why.
#   bash systems/WDIRS/quwarts/scripts/chpc/audit_oracle.sh cspaper,player
# The answers are the replay's stored reads (robust_raw.db), rebuilt from results/drift_design/<corpus>/reads.jsonl if missing.
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)
VENV=${VENV:-$HOME/venvs/quwarts}
[ -f "$VENV/bin/activate" ] && source "$VENV/bin/activate"
CORPORA=${1:-cspaper,player}
OUT=${AUDIT_DIR:-$HOME/quwarts_audit}
cd "$REPO/systems/WDIRS"
export PYTHONPATH=$PWD QUWARTS_DRIFT_DESIGN=drift_paired
for c in ${CORPORA//,/ }; do
  # the answers: the replay's stored read of every column, rebuilt from its journal (in git) if not on this machine
  python -c "import sys; from quwarts.eval import drift_run as R; sys.exit(not R.fixed_db('$c', 'robust_raw').exists())" 2> /dev/null \
    || python -m quwarts.eval.drift_run --corpus "$c" --raw > /dev/null 2>&1
  PORT=$(python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
  python quwarts/tests/oracle_ollama.py "$PORT" "$c" > "$OUT.oracle_$c.log" 2>&1 &
  MP=$!
  for _ in $(seq 1 120); do grep -q "oracle ready" "$OUT.oracle_$c.log" 2> /dev/null && break; sleep 1; done
  QUWARTS_LLM=ollama OLLAMA_HOST=127.0.0.1:$PORT QUWARTS_LIVE_ROOT=$OUT/results QUWARTS_SCRATCH=$OUT/scratch QUWARTS_KEEP_VIEWS=1 \
    python -u -m quwarts.eval.drift_live --corpus "$c" --run --streams fixed --deadline 0 --workers 8 2>&1 | grep "done:" || true
  kill $MP 2> /dev/null || true
done
python -m quwarts.eval.drift_live_audit --design 2> /dev/null | tail -1
QUWARTS_LLM=ollama QUWARTS_LIVE_ROOT=$OUT/results QUWARTS_SCRATCH=$OUT/scratch python -m quwarts.eval.drift_live_audit --levels "$CORPORA" 2> /dev/null

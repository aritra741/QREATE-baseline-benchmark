#!/usr/bin/env bash
# Router-v3 on Player at a range of budgets: theta = fraction x DocETL's recorded Player tokens (12,829,901, the
# case80 session total; the registry's definition, 0.25 is the headline). Per fraction: plan with probes (within
# 20% of theta), execute the plan's reads, score. On an Ollama server that is already running (OLLAMA_HOST).
# Resumable per fraction: a fraction with a score.json is skipped.
#
#   OLLAMA_HOST=127.0.0.1:46709 nohup bash systems/WDIRS/quwarts/scripts/chpc/run_player_budget_sweep.sh > logs/budget_sweep.out 2>&1 &
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)
VENV=${VENV:-$HOME/venvs/quwarts}
source "$VENV/quwarts.env"
FRACTIONS=${1:-0.25,0.05,0.10,0.20,0.50,0.75,1.00}
OUT=${OUT:-$REPO/results/quwarts_player_budget_sweep_ollama}
# Same context as any other job on the server: Ollama reloads the model when a request asks for another num_ctx.
export QUWARTS_LLM=ollama OLLAMA_NUM_CTX=${OLLAMA_NUM_CTX:-32768}
cd "$REPO/systems/WDIRS"
export PYTHONPATH=$PWD
# A planner still running (e.g. from an interrupted sweep) finishes first: its probe journal must not be restarted.
while pgrep -u "$USER" -f "^python -u -m quwarts.eval.router_plan_v3" > /dev/null; do sleep 30; done
for f in ${FRACTIONS//,/ }; do
  d=$OUT/f$(printf '%03d' "$(python -c "print(round($f * 100))")")
  [ -f "$d/execute/score.json" ] && { echo "$(date) $f: done"; continue; }
  echo "$(date) $f: plan"
  [ -f "$d/probe/plan.json" ] || python -u -m quwarts.eval.router_plan_v3 --corpus player --fraction "$f" --probe --out "$d"
  echo "$(date) $f: reads + score"
  python -u -m quwarts.eval.router_execute_v3 --corpus player --plan "$d/probe/plan.json" --reads --score --workers "${WORKERS:-16}" \
      --out "$d/execute" | tail -40
done
echo "$(date) sweep done"

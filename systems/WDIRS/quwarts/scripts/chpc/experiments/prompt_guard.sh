#!/usr/bin/env bash
# Prompt guard: replay one recorded budget stream (cspaper, 10% budget, 100% drift) with the current code and model
# calls refused (QUWARTS_LIVE_REPLAY). It passes only if every prompt the stream needs is already in the recorded
# journal and every query scores as recorded, i.e. the default prompts have not changed. Run first in the GPU lane;
# reset it (runner.py --reset G0-prompt-guard) after any edit to prompt or field-spec code.
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../../.." && pwd)
source "${VENV:-$HOME/venvs/quwarts}/quwarts.env"
cd "$REPO/systems/WDIRS"
export PYTHONPATH=$PWD QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama
R=$REPO/results/experiments/G0-prompt-guard/live S=/scratch/general/vast/u1592362/quwarts_exp/G0-prompt-guard
rm -rf "$R" "$S"
python "$REPO/systems/WDIRS/quwarts/scripts/chpc/experiments/clone.py" --mode policy --corpus cspaper \
    --root results/experiments/G0-prompt-guard/live --scratch "$S"
QUWARTS_LIVE_ROOT=$R QUWARTS_SCRATCH=$S QUWARTS_LIVE_REPLAY=1 QUWARTS_LIVE_ONLY=fixed4b010-attribute_pool/100 \
    python -u -m quwarts.eval.drift_live --corpus cspaper --run --streams budget --axes attribute_pool --deadline 0 --workers 4
python - "$REPO" "$R" << 'PY'
import json, sys
repo, root = sys.argv[1], sys.argv[2]
name = "fixed4b010-attribute_pool_100.jsonl"
a = [json.loads(l) for l in open(f"{repo}/results/drift_live_ollama/cspaper/streams/{name}")]
b = [json.loads(l) for l in open(f"{root}/cspaper/streams/{name}")]
bad = [x["pos"] for x, y in zip(a, b) if abs(x["benchmark"] - y["benchmark"]) > 1e-9 or x["action"] != y["action"]]
json.dump({"queries": len(a), "differences": bad}, open(f"{root}/../result.json", "w"))
sys.exit(1 if bad or len(a) != len(b) else 0)
PY

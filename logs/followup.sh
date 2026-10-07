#!/usr/bin/env bash
# After a corpus's re-run (R2) and its replay analyses: budget policies (cap, pace, oracle, knapsack) and the E13/E14
# ablations on the regenerated queries. Old outputs (previous query set) are moved aside first.
# Usage: followup.sh <corpus> [runner-server]   (runner-server: mainB on the H200 node)
set -u
C=$1; SRV=${2:-main}
REPO=/uufs/chpc.utah.edu/common/home/u1592362/Downloads/QREATE-baseline-benchmark
cd $REPO
source ~/venvs/quwarts/quwarts.env
R=systems/WDIRS/quwarts/scripts/chpc/experiments/runner.py
# Wait for this re-run's own analyses: an "ok" for E2.2-patches-<corpus> later than the re-run's "ok" (the status log
# also holds the previous query set's events).
ready() {
  python3 - "$C" << 'PY'
import json, sys
c = sys.argv[1]
r2 = pa = None
for line in open("results/experiments/status.jsonl"):
    x = json.loads(line)
    if x.get("event") != "ok":
        continue
    if x["step"] == f"R2-recorded-{c}":
        r2 = x["time"]
    if x["step"] == f"E2.2-patches-{c}" and r2 and x["time"] > r2:
        pa = x["time"]
sys.exit(0 if pa else 1)
PY
}
until ready; do sleep 120; done
EXP=results/experiments; S=/scratch/general/vast/u1592362/quwarts_exp
POL="cap pace oracle knapsack"; ABL="rawview raw noscope nobatch nodesc nousage head noreuse"; FAC="bprompt bprompt+noscope bfields bgroup"
for d in $(for p in $POL; do echo E3.2-$p; done) $(for a in $ABL; do echo E13-$a; done) $(for f in $FAC; do echo E14-$f; done); do
  if [ -d $EXP/$d/live/$C ]; then mkdir -p $EXP/$d/_superseded_queries; rm -rf $EXP/$d/_superseded_queries/$C; mv $EXP/$d/live/$C $EXP/$d/_superseded_queries/$C; fi
  if [ -d $S/$d/drift_live_ollama/$C ]; then mkdir -p $S/$d/_superseded_queries; rm -rf $S/$d/_superseded_queries/$C; mv $S/$d/drift_live_ollama/$C $S/$d/_superseded_queries/$C; fi
done
cd systems/WDIRS && PYTHONPATH=$PWD QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_analysis knapsack --corpus $C > /dev/null && cd $REPO
IDS=$( (for p in $POL; do echo E3.2-$p-$C; done; for a in $ABL; do echo E13-$a-$C; done; for f in $FAC; do echo E14-$f-$C; done) | paste -sd,)
for s in ${IDS//,/ }; do ~/venvs/quwarts/bin/python $R --reset $s --reason "regenerated queries" > /dev/null; done
QUWARTS_RUNNER_SERVER=$SRV ~/venvs/quwarts/bin/python -u $R --only $IDS --lanes gpu,gpu2,gpu3

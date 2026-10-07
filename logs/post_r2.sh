#!/usr/bin/env bash
# After R2-recorded-<corpus> finishes: archive the old replay of that corpus, then replay it (no calls) and redo its
# per-query analyses. Usage: post_r2.sh <corpus>
set -u
C=$1
REPO=/uufs/chpc.utah.edu/common/home/u1592362/Downloads/QREATE-baseline-benchmark
cd $REPO
source ~/venvs/quwarts/quwarts.env
R=systems/WDIRS/quwarts/scripts/chpc/experiments/runner.py
until grep -q "\"step\": \"R2-recorded-$C\", \"event\": \"ok\"" results/experiments/status.jsonl; do
  grep -q "\"step\": \"R2-recorded-$C\", \"event\": \"fail\"" results/experiments/status.jsonl && { echo "R2 $C failed"; exit 1; }
  sleep 120
done
S=/scratch/general/vast/u1592362/quwarts_exp/E2-replay/drift_live_ollama
A=results/experiments/E2-replay/_superseded_queries
mkdir -p $A $S/_superseded_queries
[ -d results/experiments/E2-replay/live/$C ] && mv results/experiments/E2-replay/live/$C $A/$C
[ -d $S/$C ] && mv $S/$C $S/_superseded_queries/$C
IDS="E2-replay-$C,E2.2-patches-$C,E2.3-order-$C,E2.1-columns-$C,E2.4-components-$C"
for s in ${IDS//,/ }; do ~/venvs/quwarts/bin/python $R --reset $s --reason "regenerated queries" > /dev/null; done
~/venvs/quwarts/bin/python -u $R --only $IDS --lanes cpu

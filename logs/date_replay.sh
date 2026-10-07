#!/usr/bin/env bash
# No-call replay of a corpus's five fixed drift levels with QUWARTS_KEEP_DATES=1; build databases rebuilt from the
# journals so build-time dates are kept too.
set -eu
C=$1
REPO=/uufs/chpc.utah.edu/common/home/u1592362/Downloads/QREATE-baseline-benchmark
cd $REPO/systems/WDIRS
source ~/venvs/quwarts/quwarts.env
export PYTHONPATH=$PWD QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama
ROOT=results/experiments/A-date/live S=/scratch/general/vast/u1592362/quwarts_exp/A-date
python ../../systems/WDIRS/quwarts/scripts/chpc/experiments/clone.py --mode replay --corpus $C --root $ROOT --scratch $S
rm -f $S/drift_live_ollama/$C/build.db $S/drift_live_ollama/$C/static.db
rm -rf $S/drift_live_ollama/$C/builds
QUWARTS_LIVE_ROOT=$REPO/$ROOT QUWARTS_SCRATCH=$S QUWARTS_LIVE_REPLAY=1 QUWARTS_KEEP_DATES=1 \
  python -u -m quwarts.eval.drift_live --corpus $C --run --streams fixed --axes attribute_pool --deadline 0 --workers 8

#!/usr/bin/env bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/QREATE-baseline-benchmark/systems/WDIRS
source ~/venvs/quwarts/quwarts.env
export PYTHONPATH=/uufs/chpc.utah.edu/common/home/u1592362/Downloads/QREATE-baseline-benchmark/systems/WDIRS QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama OLLAMA_NUM_CTX=32768
eval "$(bash quwarts/scripts/chpc/experiments/ensure_server.sh mainB)"
for c in cspaper player art; do ~/venvs/quwarts/bin/python -u -m quwarts.eval.exp_reads alone --corpus $c > ../../logs/a4_$c.log 2>&1; echo "alone $c exit $?"; done
for c in art player; do ~/venvs/quwarts/bin/python -u -m quwarts.eval.exp_reads t2 --corpus $c > ../../logs/a13_$c.log 2>&1; echo "t2 $c exit $?"; done

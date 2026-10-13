#!/usr/bin/env bash
# The realistic workload (Query/Realistic), 2026-10-12. Two queues, one per GPU of a two-A800 node:
#   ours    our system (V3 planner, no re-reads: no correct answers used), three replicates started from the
#           journals of V3, V3-rep1 and V3-rep2 (identical prompts reuse the recorded answers), on server main (GPU 0)
#   docetl  DocETL on every realistic query, on server main2 (GPU 1)
# Usage: bash realistic_queue.sh ours|docetl     (resumable; finished streams and scored queries are skipped)
set -uo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../../.." && pwd)
EXP=$REPO/systems/WDIRS/quwarts/scripts/chpc/experiments
SCR=/scratch/general/vast/u1592362/quwarts_exp
source ~/venvs/quwarts/quwarts.env
cd "$REPO/systems/WDIRS"
export PYTHONPATH=$PWD QUWARTS_LLM=ollama OLLAMA_NUM_CTX=32768 QUWARTS_DRIFT_DESIGN=drift_paired
# QUWARTS_REALISTIC=v2 with RW_PREFIX=RW2: the relational version in its own runs; RW_CLONE_FROM: the runs whose
# journals a replicate starts from (default the recorded V3 runs; for v2 the v1 realistic runs, so their reads are reused)
P=${RW_PREFIX:-RW}
host() { python -c "import json; print(json.load(open('$REPO/results/experiments/servers/$1.json'))['host'])"; }
case "$1" in
  ours)
    export OLLAMA_HOST=$(host main)
    for src in V3 V3-rep1 V3-rep2; do
      for c in cspaper player art med legal; do
        [ -d "$REPO/results/experiments/$src/live/$c" ] || continue
        name=$P-norereads-$src root=results/experiments/$P-norereads-$src/live
        from=${RW_CLONE_FROM:+$RW_CLONE_FROM-$src}; from=${from:-$src}
        echo "$(date -Is) ours $src $c start (from $from)"
        python "$EXP/clone.py" --mode replay --corpus $c --root $root --scratch $SCR/$name \
          --src-root "$REPO/results/experiments/$from/live" --src-scratch $SCR/$from || { echo "clone failed $src $c"; continue; }
        rm -f "$REPO/$root/$c/state/fixed4-realistic_100.json" "$REPO/$root/$c/streams/fixed4-realistic_100.jsonl"
        QUWARTS_KEEP_QUERY_VIEWS=$SCR/RW-qviews/$name \
        QUWARTS_LIVE_ROOT=$REPO/$root QUWARTS_SCRATCH=$SCR/$name QUWARTS_PLANNER=catalogue \
          QUWARTS_PROBE_DOCS=20 QUWARTS_REPAIR_MIN_FIXES=3 QUWARTS_LIVE_ONLY=fixed4-realistic/100 \
          python -u -m quwarts.eval.drift_live --corpus $c --run --streams realistic --deadline 0 --workers 8
        echo "$(date -Is) ours $src $c done"
      done
    done ;;
  reread)  # our system with re-reads (the 32B server on GPU 1, servers/qwen32b.json), each replicate started from its
           # finished no-re-read run, so the 7B reads are reused and only second looks are new; [src ...] default all three
    export OLLAMA_HOST=$(host main)
    shift || true
    for src in ${@:-V3 V3-rep1 V3-rep2}; do
      for c in cspaper player art med legal; do
        [ -d "$REPO/results/experiments/$P-norereads-$src/live/$c" ] || continue
        root=results/experiments/$P-$src/live
        echo "$(date -Is) reread $src $c start"
        python "$EXP/clone.py" --mode replay --corpus $c --root $root --scratch $SCR/$P-$src \
          --src-root "$REPO/results/experiments/$P-norereads-$src/live" --src-scratch $SCR/$P-norereads-$src || { echo "clone failed $src $c"; continue; }
        [ -f "$REPO/results/experiments/$src/live/$c/repair_reads.jsonl" ] && cp -n "$REPO/results/experiments/$src/live/$c/repair_reads.jsonl" "$REPO/$root/$c/" || true
        rm -f "$REPO/$root/$c/state/fixed4-realistic_100.json" "$REPO/$root/$c/streams/fixed4-realistic_100.jsonl"
        QUWARTS_KEEP_QUERY_VIEWS=$SCR/RW-qviews/$P-$src \
        QUWARTS_LIVE_ROOT=$REPO/$root QUWARTS_SCRATCH=$SCR/RW-$src QUWARTS_PLANNER=catalogue \
          QUWARTS_PROBE_DOCS=20 QUWARTS_REPAIR_MIN_FIXES=3 QUWARTS_LIVE_ONLY=fixed4-realistic/100 \
          QUWARTS_REPAIR_LABELS=$REPO/results/experiments/V3/labels20/$c.json \
          python -u -m quwarts.eval.drift_live --corpus $c --run --streams realistic --deadline 0 --workers 8
        echo "$(date -Is) reread $src $c done"
      done
    done ;;
  docetl)  # docetl [server] [corpus ...]: default main2 and every corpus; with WAIT_PID set, start after that process ends
    export OLLAMA_HOST=$(host ${2:-main2}) QUWARTS_WORKLOAD=realistic
    shift; shift || true
    if [ -n "${WAIT_PID:-}" ]; then while kill -0 "$WAIT_PID" 2>/dev/null; do sleep 30; done; fi
    for c in ${@:-cspaper player art med legal}; do
      echo "$(date -Is) docetl $c start"
      python -u "$REPO/systems/DocETL/run_docetl_drift.py" --corpus $c --threads 8
      echo "$(date -Is) docetl $c done"
    done ;;
esac

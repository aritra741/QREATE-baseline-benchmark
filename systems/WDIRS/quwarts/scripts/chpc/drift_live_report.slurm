#!/bin/bash
# The report over every corpus's results (CPU only). Submit after the array finishes:
#   sbatch -A <account> -p <cpu-partition> --dependency=afterany:<array job id> systems/WDIRS/quwarts/scripts/chpc/drift_live_report.slurm
#SBATCH --job-name=quwarts-drift-report
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail
REPO=${REPO:-$SLURM_SUBMIT_DIR}
VENV=${VENV:-$HOME/venvs/quwarts}
[ -f "$VENV/bin/activate" ] && source "$VENV/bin/activate"
cd "$REPO/systems/WDIRS"
export PYTHONPATH=$PWD QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama
export QUWARTS_SCRATCH=${QUWARTS_SCRATCH:-/scratch/general/vast/$USER/quwarts_scratch}
python3 -u -m quwarts.eval.drift_live --report

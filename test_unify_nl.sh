#!/bin/bash
#SBATCH --job-name=test_unify_nl
#SBATCH --partition=general
#SBATCH --time=00:45:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=%x_%j.log

cd /Users/aritramazumder/Documents/UDA-Bench-main

# Load modules if needed
module load python/3.10 || true

# Run test with Unify only, simple queries
python3 run_challenging_queries.py \
  --systems unify \
  --query-types simple \
  --log-level DEBUG



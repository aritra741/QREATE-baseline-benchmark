#!/bin/bash
#SBATCH --job-name=uda_unify_test
#SBATCH --partition=general
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --output=logs/unify_test_%j.log
#SBATCH --error=logs/unify_test_%j.err

# Navigate to project
cd /Users/aritramazumder/Documents/UDA-Bench-main

# Create logs directory
mkdir -p logs

echo "Starting Unify NL test on $(hostname) at $(date)"
echo "Job ID: $SLURM_JOB_ID"
echo "============================================"

# Check if Ollama is running
echo "Checking Ollama..."
curl -s http://localhost:11434/api/tags > /dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: Ollama not running at http://localhost:11434"
    echo "Start with: ollama serve &"
    exit 1
fi
echo "✓ Ollama is running"

# Check if preprocessed data exists
echo "Checking preprocessed data..."
if [ ! -f "preprocess_unify/indexes/Med/disease/preprocessed_data.pkl" ]; then
    echo "ERROR: Preprocessed data not found"
    echo "Run: python systems/Unify/scripts/preprocess_unify_data.py --entities Med disease"
    exit 1
fi
echo "✓ Preprocessed data found"

echo ""
echo "Running Unify tests with NL conversion..."
echo "============================================"

# Run the test
python3 run_challenging_queries.py \
  --systems unify \
  --query-types simple filter projection \
  --log-level DEBUG \
  2>&1 | tee logs/unify_test_output_$(date +%s).log

EXIT_CODE=$?

echo ""
echo "============================================"
echo "Test completed at $(date)"
echo "Exit code: $EXIT_CODE"

exit $EXIT_CODE



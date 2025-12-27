# QUEST on CHPC - Quick Start Guide

## Answer to Your Questions

### 1. Why would `--local` work if I want to use scratch on CHPC?

**Short Answer:** `--local` means "use local filesystem paths" (PROJECT_ROOT/index), not CHPC-specific paths.

**For CHPC Scratch:**
- Remove `--local` flag
- The system will automatically look for indexes on CHPC's default paths
- Indexes may be at: `/scratch/general/vast/u1592362/` or similar CHPC scratch location

**On CHPC, use:**
```bash
python3 run_challenging_queries.py --systems quest --query-ids filter_2
```

NOT:
```bash
python3 run_challenging_queries.py --systems quest --query-ids filter_2 --local
```

---

## 2. Run QUEST filter_2 on CHPC (Simple Command)

Just run this and check results later in the results folder:

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main && \
source quest_venv/bin/activate && \
python3 run_challenging_queries.py --systems quest --query-ids filter_2
```

**Results will be saved to:**
```
results/challenging_queries/TIMESTAMP/results/quest/filter/filter_2/
```

**Check later with:**
```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main && \
TESTDIR=$(ls -td results/challenging_queries/* | head -1) && \
echo "Test directory: $TESTDIR" && \
echo "Result count:" && \
cat $TESTDIR/results/quest/filter/filter_2/metadata.json | grep result_count && \
echo "First 10 rows of result:" && \
head -10 $TESTDIR/results/quest/filter/filter_2/result.csv
```

---

## 3. Requirements.txt for quest_venv

**Already exists!** Located at:
```
systems/quest/requirements.txt
```

**To create a fresh venv on CHPC with these requirements:**

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main && \
python3 -m venv quest_venv_chpc && \
source quest_venv_chpc/bin/activate && \
pip install --upgrade pip && \
pip install -r systems/quest/requirements.txt
```

**Key packages in quest_venv:**
- pandas, numpy, scipy, scikit-learn
- torch, transformers, sentence-transformers
- langchain, langchain-community, langchain-openai
- ollama (for local LLM)
- sqlglot, duckdb (for SQL parsing)
- spacy, nltk (for NLP)
- requests, httpx, aiohttp (for HTTP)
- And many others...

---

## Important Notes

1. **Index Location Difference:**
   - `--local`: Uses `PROJECT_ROOT/index/` (good for local testing)
   - No flag: Uses system default/configured path (good for CHPC scratch)

2. **CHPC Path:** 
   `/uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main`

3. **Results Location:**
   - Automatically saved to `results/challenging_queries/TIMESTAMP/`
   - Check metadata.json for result_count, status, timing
   - Check result.csv for actual results

4. **Performance:** 
   - filter_2 query should complete in ~10-15 minutes
   - Ollama LLM initialization takes ~2-3 minutes first time
   - Subsequent queries faster

---

## Testing the Fix (verify all columns are populated)

After running, check if columns are properly populated:

```bash
TESTDIR=$(ls -td results/challenging_queries/* | head -1)
echo "Checking column count:"
head -1 $TESTDIR/results/quest/filter/filter_2/result.csv | tr ',' '\n' | nl
echo ""
echo "Sample row:"
head -2 $TESTDIR/results/quest/filter/filter_2/result.csv | tail -1 | cut -d',' -f1-5
```

Expected columns: `name,team,position,nationality,draft_year,file_name`

If all columns have data ✅ = Fix is working!
If only position has data ❌ = Need more fixes


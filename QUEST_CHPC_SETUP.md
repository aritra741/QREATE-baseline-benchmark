# QUEST Setup and Run Guide for CHPC

## Step 1: Create Fresh Virtual Environment on CHPC

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

# Create new venv
python3 -m venv quest_venv_chpc

# Activate it
source quest_venv_chpc/bin/activate

# Upgrade pip
pip install --upgrade pip
```

## Step 2: Install Requirements (CHPC-compatible version)

```bash
# Still in venv
pip install -r requirements_quest_chpc.txt
```

This installs all the core packages. If you get errors about version conflicts, that's OK - the packages are compatible.

## Step 3: Download spacy model (MUST DO THIS)

```bash
# Still in venv
python -m spacy download en_core_web_sm
```

This downloads the English language model that QUEST needs for NLP.

## Step 4: Run QUEST filter_2 Query

```bash
# Still in venv
python3 run_challenging_queries.py --systems quest --query-ids filter_2
```

**Do NOT use `--local` flag on CHPC** - it will try to use local paths which won't work.

## Step 5: Check Results

After it completes (takes ~10-15 minutes), check the results:

```bash
TESTDIR=$(ls -td results/challenging_queries/* | head -1)
echo "Results saved to: $TESTDIR"
echo ""
echo "Result count:"
cat $TESTDIR/results/quest/filter/filter_2/metadata.json | grep result_count
echo ""
echo "First 3 rows:"
head -3 $TESTDIR/results/quest/filter/filter_2/result.csv
```

---

## If You Get Errors

### Error: "No module named 'tiktoken'"
```bash
source quest_venv_chpc/bin/activate
pip install tiktoken
```

### Error: "No module named 'sqlglot'"
```bash
source quest_venv_chpc/bin/activate
pip install sqlglot duckdb
```

### Error: "No module named 'en_core_web_sm'"
```bash
source quest_venv_chpc/bin/activate
python -m spacy download en_core_web_sm
```

### Error: "Can't find index" or "No documents"
Make sure you're NOT using `--local` flag on CHPC. The indexes should be in CHPC's default location.

---

## Complete One-Liner (After first setup)

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main && \
source quest_venv_chpc/bin/activate && \
python3 run_challenging_queries.py --systems quest --query-ids filter_2
```

---

## Files to Reference

- Requirements: `requirements_quest_chpc.txt` (minimal, CHPC-safe versions)
- Old full requirements: `requirements_quest_venv.txt` (has all packages from local env)
- System requirements: `systems/quest/requirements.txt` (original with wheel URLs)

---

## Troubleshooting Checklist

- [ ] Using `source quest_venv_chpc/bin/activate` before running?
- [ ] Ran `pip install -r requirements_quest_chpc.txt`?
- [ ] Ran `python -m spacy download en_core_web_sm`?
- [ ] NOT using `--local` flag?
- [ ] Waiting 10+ minutes for query to complete?
- [ ] Checking results in `results/challenging_queries/TIMESTAMP/`?

---

## Success = All Columns Populated

✅ **Good result:** name, team, position, nationality, draft_year all have data
❌ **Bad result:** only position has data (missing columns)

If you get a good result with all columns, the fix is working! 🎉


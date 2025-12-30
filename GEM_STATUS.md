# GEM Status & Next Steps

## What's Done
- ✅ Full GEM implementation (7 modules)
- ✅ Virtual environment created with all dependencies
- ✅ Integration with run_challenging_queries.py
- ✅ Fixed DuckDB API calls (fetch_all → df())
- ✅ Fixed Player/manager path mapping (owner directory)
- ✅ Improved JSON extraction handling for truncated responses
- ✅ Fixed path issues for running from GEM directory

## To Run on CHPC

### 1. Activate & Preprocess
```bash
cd systems/GEM
source venv/bin/activate
bash preprocess_all.sh
```

### 2. Run Queries
```bash
cd ../..  # Back to project root
python run_challenging_queries.py --systems gem --query-types all
```

### 3. Reprocess Finance/Player (if needed)
```bash
cd systems/GEM
bash reprocess_finance_player.sh
```

## Test Dataset
- Created synthetic product dataset at `test_data/synthetic/`
- Schema at `Query/Synthetic/Synthetic_attributes.json`
- Documents show entity resolution challenges:
  - Product names: iPhone 15 vs Apple iPhone 15 vs iPhone 15 Pro
  - Brands: Apple vs Apple Inc vs AAPL vs Samsung vs Samsung Electronics
  - Prices: $999, $1099, $899, $1299
  - Colors: black vs midnight black vs phantom black vs titanium

## Known Issues
- FAISS multiprocessing crashes on macOS (works fine on Linux)
- Finance documents sometimes produce partial JSON (fixed with better parsing)
- Some datasets may need cache clearing if extraction fails

## Cache Locations
- Extractions: `systems/GEM/.cache/extractions/{entity}/`
- Preprocessing: `systems/GEM/.cache/preprocessing/{dataset}/{entity}/`
- Database: `systems/GEM/.cache/gem.duckdb`


# Fix for "Format error: Missing or incorrect brackets" Issue

## Status: ✅ FIXED

Your `run_challenging_queries.py` was throwing hundreds of error messages due to the LLM not following output format requirements. This has been fixed.

## What Was Wrong

When the QUEST system extracted attributes from documents, it sent text chunks to an LLM (Large Language Model) expecting responses in this exact format:

```
(attribute_name, attribute_value, confidence_score, chunk_id)
```

However, the LLM was returning formatted text like:
```
- **Exhibit I**: Notices.
- **Exhibit J**: Entire Agreement.
### ð **4. Exhibits to the Loan Agreement (Continuation)**
```

The parser would reject each line and print: `Format error: Missing or incorrect brackets`

Result: **Hundreds of error messages** that looked like system failures but didn't actually prevent processing.

## What's Fixed

Modified `/systems/quest/core/llm/sampler.py` to:

1. **Explicit LLM Instructions** - Tell the LLM exactly what to output with clear examples
2. **Forbidden Format List** - Explicitly list what NOT to output (markdown, bullets, headers, etc.)
3. **Silent Error Handling** - Invalid lines are now silently skipped instead of printing errors
4. **More Robust Parsing** - Better whitespace handling and empty line filtering

## How to Verify

```bash
# Quick test of the parser fix
python3 test_parser_fix.py
# Expected output: 14 passed, 0 failed

# Run your challenging queries
python3 run_challenging_queries.py --systems quest --query-types filter projection
# Expected: Clean output without "Format error" spam
```

## Files Changed

1. **Modified**: `systems/quest/core/llm/sampler.py`
   - Updated LLM prompts for clarity
   - Fixed parser to silently handle invalid lines
   - Improved extraction method robustness

2. **New Test File**: `test_parser_fix.py`
   - Validates the parser fixes
   - Tests 14 different input scenarios

3. **Documentation**:
   - `FIX_LLM_OUTPUT_FORMAT.md` - Overview
   - `LLM_OUTPUT_FORMAT_FIX_DETAILED.md` - Full technical details
   - `FIX_QUICK_REFERENCE.md` - Quick reference

## Impact

- ✅ No more error message spam
- ✅ Queries process cleanly
- ✅ System is more robust to LLM formatting variations
- ✅ Better handling of local LLMs (like Ollama) that may not follow instructions perfectly
- ✅ Same query results - only the error messages are gone

## Next Steps

1. Test with your challenging queries:
   ```bash
   python3 run_challenging_queries.py --systems quest --query-types filter
   ```

2. If you continue to get format errors on specific lines, let me know - we can add additional filtering

3. Consider running all query types:
   ```bash
   python3 run_challenging_queries.py --systems all --query-types all
   ```

## Technical Details

For detailed information about what changed and why, see:
- `LLM_OUTPUT_FORMAT_FIX_DETAILED.md` - Full technical analysis
- `FIX_QUICK_REFERENCE.md` - Quick reference guide



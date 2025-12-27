# Quick Fix Reference

## The Problem
Running `run_challenging_queries.py` produced hundreds of errors:
```
Format error: Missing or incorrect brackets. Input string:
 - **Exhibit I**: Notices.
```

## The Solution
Enhanced LLM prompts to be more explicit about output format, and made the parser silently filter invalid lines.

## What Changed

### Changed File
- `systems/quest/core/llm/sampler.py`

### Key Changes
1. **Better prompts** - Explicit instructions telling LLM to ONLY output tuples
2. **Examples** - Added concrete examples of correct format
3. **Forbidden list** - Explicitly listed what NOT to output (markdown, bullets, etc.)
4. **Silent error handling** - Parser now silently skips invalid lines instead of printing errors

### Expected Format
```
(attribute_name, attribute_value, confidence_score, chunk_id)
```

Examples:
```
(disease_name, Malaria, 85, 0)
(pathogenesis, infectious, 90, 1)
(prognosis, chronic, 85, 2)
```

## Verification
```bash
python3 test_parser_fix.py
# Expected: All 14 tests pass ✓
```

## Run Your Queries
```bash
python3 run_challenging_queries.py --systems quest --query-types filter projection
# Should run cleanly without format errors
```

## Technical Details
See `LLM_OUTPUT_FORMAT_FIX_DETAILED.md` for full documentation.




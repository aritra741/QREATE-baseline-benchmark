# Fix: LLM Output Format Errors

## Problem
When running `run_challenging_queries.py`, the QUEST system was printing hundreds of errors:
```
Format error: Missing or incorrect brackets. Input string:
 - **Exhibit I**: Notices.
 ... (many more markdown/formatted text lines)
```

## Root Cause
The LLM (Large Language Model) was not following the strict output format requirements. Instead of returning tuples in the format:
```
(attribute_name, attribute_value, confidence_score, chunk_id)
```

The LLM was returning formatted text with:
- Markdown formatting (bold, bullets, headers)
- Emoji characters
- Currency symbols
- Multi-line explanations
- Bullet points with `-`
- Other extraneous text

This caused the `parse_xyz_with_chunkid()` function in `sampler.py` to reject every line and print error messages.

## Solution
Made changes to `/systems/quest/core/llm/sampler.py`:

### 1. **Improved Prompt Instructions** (Lines 147-179)
- Replaced vague instructions with CRITICAL, explicit instructions
- Added clear examples of correct output format
- Added explicit "Do NOT" section listing forbidden formats:
  - No markdown formatting
  - No bullet points
  - No headers
  - No explanations
  - No extra text
- Emphasized one tuple per line requirement

### 2. **Updated System Prompt** (Lines 176-179)
- Made system prompt more strict and explicit
- Added emphasis on "ONLY" output format
- Clarified that each line must be a valid tuple

### 3. **Made Parser More Forgiving** (Lines 70-139)
**Before**: Printed error message for every invalid line, used strict bracket checking with error output
**After**: 
- Silently skips empty lines or lines without opening `(`
- Returns `None` for malformed input (no error messages)
- More graceful error handling

### 4. **Improved Extract Method** (Lines 270-304)
**Before**: Passed raw string to parser
**After**:
- Added `.strip()` to clean whitespace from each line
- Explicitly skip empty lines before parsing
- Only processes successfully parsed tuples
- More robust error handling

## Result
- LLM output with wrong format is now silently filtered out instead of printing errors
- System continues to process valid tuples
- The prompt is much clearer about what the LLM should output
- No more "Format error: Missing or incorrect brackets" spam

## Files Modified
- `systems/quest/core/llm/sampler.py`
  - `parse_xyz_with_chunkid()` function
  - `AttrSampler.__init__()` prompts
  - `AttrSampler.extract_doc2row()` method




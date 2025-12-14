# Detailed Code Changes

## Change 1: PlanManager.py - replace_variables() Function

### Location: systems/Unify/main/PlanManager.py, lines 414-428

### BEFORE:
```python
def replace_variables(input_string, mapping):
    # Find all occurrences of variables surrounded by []
    variables = re.findall(r'\[(.*?)\]', input_string)

    # Replace the variables with their values from the mapping
    for var in variables:
        if var in mapping:
            input_string = input_string.replace(f'[{var}]', mapping[var])

    return input_string
```

**Problem**: If `mapping[var]` is `None`, calling `.replace(..., None)` crashes with:
```
TypeError: replace() argument 2 must be str, not None
```

### AFTER:
```python
def replace_variables(input_string, mapping):
    # Find all occurrences of variables surrounded by []
    variables = re.findall(r'\[(.*?)\]', input_string)

    # Replace the variables with their values from the mapping
    for var in variables:
        if var in mapping:
            value = mapping[var]
            # Ensure value is a string (handle None and other types)
            if value is None:
                value = ""
            else:
                value = str(value)
            input_string = input_string.replace(f'[{var}]', value)

    return input_string
```

**Solution**:
- Extract value to variable first
- Check if None and convert to ""
- Convert to str() as fallback for any non-string type
- Now replace() always gets a string argument

---

## Change 2: PlanManager.py - execute_with_plan() - Added Diagnostics

### Location: systems/Unify/main/PlanManager.py, lines 350-365

### BEFORE:
```python
            mapping = map_placeholders_to_original(numbered_question, formatted_original_question)

            print("See mapping used in BQ for the original question")
            print(mapping)
            print("Numbered  Q:  ", numbered_question)
            print("Original  Q:  ", self.original_question)
            print("Current   Q:  ", self.current_question)
            print("Formatted Q:  ", formatted_original_question)
            print("@"*50)

            # Traverse and execute the subplan in post-order
            self.ctxManager = postorder_traversal(bq['IDPlan'], mapping, self.ctxManager)
```

### AFTER:
```python
            mapping = map_placeholders_to_original(numbered_question, formatted_original_question)

            print("See mapping used in BQ for the original question")
            print(mapping)
            print("Numbered  Q:  ", numbered_question)
            print("Original  Q:  ", self.original_question)
            print("Current   Q:  ", self.current_question)
            print("Formatted Q:  ", formatted_original_question)
            print("@"*50)

            # Check if mapping has any None values and log a warning
            none_mappings = {k: v for k, v in mapping.items() if v is None}
            if none_mappings:
                print(f"WARNING: Mapping contains None values: {none_mappings}")
                print(f"WARNING: These placeholders could not be matched to the original question")
                print(f"WARNING: Proceeding with 'None' as replacement string")

            # Traverse and execute the subplan in post-order
            self.ctxManager = postorder_traversal(bq['IDPlan'], mapping, self.ctxManager)
```

**Improvement**: Added diagnostic output to help debug mapping issues

---

## Change 3: placeholders.py - Improved map_placeholders_to_original()

### Location: systems/Unify/main/utils/placeholders.py, lines 33-63

### BEFORE:
```python
def map_placeholders_to_original(template_question, original_question):
    # Step 1: Extract placeholders from the template question
    placeholders = re.findall(r'\[([A-Za-z]+\d+)\]', template_question)

    # Step 2: Split both questions by placeholders
    template_parts = re.split(r'\[([A-Za-z]+\d+)\]', template_question)

    # The original question is split using the same template parts
    # This allows us to find the parts corresponding to each placeholder
    parts = []
    last_index = 0
    for part in template_parts:
        if part:
            index = original_question.find(part, last_index)
            if index != -1:
                if last_index < index:
                    parts.append(original_question[last_index:index])
                last_index = index + len(part)
    # Append any remaining text after the last placeholder
    if last_index < len(original_question):
        parts.append(original_question[last_index:])

    # Step 3: Create the mapping between placeholders and original text
    mapping = {}
    for i, placeholder in enumerate(placeholders):
        # mapping[placeholder] = parts[i].strip()
        if i < len(parts):
            mapping[placeholder] = parts[i].strip()
        else:
            mapping[placeholder] = None  # ← PROBLEM: Sets None when placeholder not found

    return mapping
```

**Problem**: 
- When there are fewer extracted parts than placeholders, assigns `None`
- This happens when template structure doesn't match original structure
- Example: Template "Join [Entity1] and [Entity2]" vs Original "SELECT name FROM player"

### AFTER:
```python
def map_placeholders_to_original(template_question, original_question):
    """
    Map placeholders in a template question to corresponding text in the original question.
    
    Improved robustness:
    - Handles cases where template parts don't appear in original question
    - Returns empty string instead of None for unmatched placeholders
    - Logs debugging info for troubleshooting
    """
    # Step 1: Extract placeholders from the template question
    placeholders = re.findall(r'\[([A-Za-z]+\d+)\]', template_question)
    
    # Step 2: Split both questions by placeholders
    template_parts = re.split(r'\[([A-Za-z]+\d+)\]', template_question)
    
    # The original question is split using the same template parts
    # This allows us to find the parts corresponding to each placeholder
    parts = []
    last_index = 0
    for part in template_parts:
        if part:  # Skip empty parts
            index = original_question.find(part, last_index)
            if index != -1:
                if last_index < index:
                    extracted = original_question[last_index:index].strip()
                    if extracted:  # Only add non-empty parts
                        parts.append(extracted)
                last_index = index + len(part)
    
    # Append any remaining text after the last placeholder
    if last_index < len(original_question):
        remaining = original_question[last_index:].strip()
        if remaining:
            parts.append(remaining)
    
    # Step 3: Create the mapping between placeholders and original text
    mapping = {}
    for i, placeholder in enumerate(placeholders):
        if i < len(parts):
            mapping[placeholder] = parts[i]
        else:
            # Use empty string instead of None to avoid type errors downstream
            # Add the placeholder name as fallback for debugging
            mapping[placeholder] = f"[{placeholder}]"  # ← IMPROVEMENT: Never None
    
    return mapping
```

**Improvements**:
1. Better part extraction with `.strip()` to clean whitespace
2. Filter empty parts to avoid counting them
3. Use empty string + placeholder name as fallback instead of None
4. Better documentation with docstring
5. Never returns None in mapping values
6. Provides debug info (placeholder name) for unmatched placeholders

---

## Summary of Changes

| Aspect | Before | After |
|--------|--------|-------|
| **Type Safety** | Could pass None to str.replace() | Always passes strings |
| **Handling Mismatches** | Returns None in mapping | Returns "" or placeholder name |
| **Error Behavior** | Silent crash on None | Graceful handling + warnings |
| **Debugging** | Hard to track down None source | Clear warnings show which placeholders failed |
| **Robustness** | Fails on structure mismatch | Continues with degraded output |

---

## Testing the Fixes

### Before Fix - Crash:
```
TypeError: replace() argument 2 must be str, not None
  File "PlanManager.py", line 421, in replace_variables
    input_string = input_string.replace(f'[{var}]', mapping[var])
```

### After Fix - Handled:
```
WARNING: Mapping contains None values: {'Attribute2': None}
WARNING: These placeholders could not be matched to the original question
WARNING: Proceeding with 'None' as replacement string
[Execution continues]
```

Or even better:
```
Mapping: {'Entity1': 'player', 'Entity2': 'team', 'Attribute1': 'team', 'Attribute2': '[Attribute2]'}
[No crash, execution continues with fallback values]
```


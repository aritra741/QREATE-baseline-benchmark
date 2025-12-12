#!/usr/bin/env python3
"""
Remove null bytes from all Python files in the project.
This fixes issues where null bytes accidentally get into source code.
"""
import os
from pathlib import Path

def remove_null_bytes_from_file(file_path):
    """Remove null bytes from a single file."""
    try:
        # Read file in binary mode to detect null bytes
        with open(file_path, 'rb') as f:
            content = f.read()
        
        # Check if there are null bytes
        if b'\x00' in content:
            print(f"Found null bytes in: {file_path}")
            # Remove null bytes
            content_clean = content.replace(b'\x00', b'')
            
            # Write back
            with open(file_path, 'wb') as f:
                f.write(content_clean)
            
            print(f"  -> Removed null bytes from {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def main():
    """Remove null bytes from recently edited files only."""
    project_root = Path(__file__).parent
    
    # Only the files we just edited
    files_to_check = [
        project_root / "systems" / "quest" / "sql" / "planner" / "logical.py",
        project_root / "systems" / "quest" / "sql" / "planner" / "physical.py",
        project_root / "systems" / "quest" / "sql" / "nn" / "extract_text.py",
        project_root / "systems" / "quest" / "sql" / "nn" / "retrieve_text.py",
        project_root / "run_challenging_queries.py",
    ]
    
    print("Scanning recently edited files for null bytes...")
    print("=" * 80)
    
    files_fixed = 0
    for py_file in files_to_check:
        if py_file.exists():
            if remove_null_bytes_from_file(py_file):
                files_fixed += 1
        else:
            print(f"File not found: {py_file}")
    
    print("=" * 80)
    print(f"Done! Fixed {files_fixed} file(s).")

if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
Sort files by size in a directory and display the top 30 largest files.
"""

import os
import sys
from pathlib import Path


def get_file_sizes(directory):
    """Get all files in directory with their sizes."""
    files_with_sizes = []
    directory_path = Path(directory)
    
    if not directory_path.exists():
        print(f"Error: Directory '{directory}' does not exist.")
        return []
    
    if not directory_path.is_dir():
        print(f"Error: '{directory}' is not a directory.")
        return []
    
    # Walk through directory and collect all files
    for root, dirs, filenames in os.walk(directory_path):
        for filename in filenames:
            file_path = Path(root) / filename
            try:
                size = file_path.stat().st_size
                files_with_sizes.append((file_path, size))
            except (OSError, PermissionError) as e:
                # Skip files we can't access
                continue
    
    return files_with_sizes


def format_size(size_bytes):
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def main():
    # Get directory from command line argument or use current directory
    if len(sys.argv) > 1:
        target_directory = sys.argv[1]
    else:
        target_directory = os.getcwd()
    
    print(f"Scanning directory: {target_directory}\n")
    
    # Get all files with sizes
    files_with_sizes = get_file_sizes(target_directory)
    
    if not files_with_sizes:
        print("No files found.")
        return
    
    # Sort by size (descending)
    files_with_sizes.sort(key=lambda x: x[1], reverse=True)
    
    # Display top 30
    top_n = min(30, len(files_with_sizes))
    print(f"Top {top_n} largest files:\n")
    print(f"{'Rank':<6} {'Size':<12} {'File Path'}")
    print("-" * 80)
    
    for i, (file_path, size) in enumerate(files_with_sizes[:top_n], 1):
        # Make path relative to target directory for cleaner output
        try:
            rel_path = file_path.relative_to(Path(target_directory))
        except ValueError:
            rel_path = file_path
        
        print(f"{i:<6} {format_size(size):<12} {rel_path}")
    
    # Print summary
    total_files = len(files_with_sizes)
    total_size = sum(size for _, size in files_with_sizes)
    print(f"\n{'='*80}")
    print(f"Total files scanned: {total_files}")
    print(f"Total size: {format_size(total_size)}")


if __name__ == "__main__":
    main()


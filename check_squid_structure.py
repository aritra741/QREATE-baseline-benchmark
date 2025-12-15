#!/usr/bin/env python3
"""
Debug script to understand SQUiD's expected file structure and paths.
"""

import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SQUID_PATH = PROJECT_ROOT / "systems" / "SQUiD"

print("=" * 80)
print("SQUiD File Structure Analysis")
print("=" * 80)
print()

# 1. Check SQUiD directory structure
print("1. SQUiD Directory Structure:")
print(f"   SQUID_PATH: {SQUID_PATH}")
print(f"   Exists: {SQUID_PATH.exists()}")
print()

# 2. Check configs
configs_dir = SQUID_PATH / "configs"
print(f"2. Configs directory: {configs_dir}")
print(f"   Exists: {configs_dir.exists()}")
if configs_dir.exists():
    print(f"   Files: {list(configs_dir.glob('*'))}")
print()

# 3. Check dataset
dataset_dir = SQUID_PATH / "dataset"
print(f"3. Dataset directory: {dataset_dir}")
print(f"   Exists: {dataset_dir.exists()}")
if dataset_dir.exists():
    print("   Contents:")
    for item in dataset_dir.rglob("*"):
        if item.is_file():
            size_mb = item.stat().st_size / 1024 / 1024
            print(f"      {item.relative_to(dataset_dir)}: {size_mb:.2f} MB")
print()

# 4. Check results
results_dir = SQUID_PATH / "results"
print(f"4. Results directory: {results_dir}")
print(f"   Exists: {results_dir.exists()}")
if results_dir.exists():
    print("   Contents:")
    for item in results_dir.rglob("*"):
        if item.is_file():
            print(f"      {item.relative_to(results_dir)}")
else:
    print("   (Will be created by pipeline)")
print()

# 5. Check preprocess_squid output
preprocess_dir = PROJECT_ROOT / "preprocess_squid"
print(f"5. Preprocess output directory: {preprocess_dir}")
print(f"   Exists: {preprocess_dir.exists()}")
if preprocess_dir.exists():
    print("   Contents:")
    for dataset_subdir in preprocess_dir.iterdir():
        if dataset_subdir.is_dir():
            print(f"      Dataset: {dataset_subdir.name}")
            for entity_dir in dataset_subdir.iterdir():
                if entity_dir.is_dir():
                    print(f"         Entity: {entity_dir.name}")
                    for item in entity_dir.iterdir():
                        if item.is_file():
                            print(f"            {item.name}")
                        elif item.is_dir():
                            file_count = len(list(item.glob("*")))
                            print(f"            {item.name}/ ({file_count} files)")
print()

# 6. Check config.yaml content
print(f"6. config.yaml content:")
config_file = configs_dir / "config.yaml"
if config_file.exists():
    with open(config_file, "r") as f:
        print("   " + "\n   ".join(f.read().split("\n")[:20]))
else:
    print("   NOT FOUND!")
print()

# 7. Check what SQUiD scripts expect
print(f"7. SQUiD Scripts Analysis:")
src_dir = SQUID_PATH / "src"
for script in ["schema_generation.py", "value_identification.py", "value_population.py", "database_generation.py"]:
    script_path = src_dir / script
    if script_path.exists():
        with open(script_path, "r") as f:
            content = f.read()
            # Look for hardcoded paths
            if "load_config" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if "load_config" in line:
                        print(f"   {script}: line {i+1}")
                        print(f"      {line.strip()}")
print()

# 8. Helper scripts
print(f"8. Helper Scripts:")
helpers_dir = SQUID_PATH / "helpers"
if helpers_dir.exists():
    for helper in helpers_dir.glob("*.py"):
        print(f"   {helper.name}")
else:
    print("   helpers/ directory not found!")
print()

print("=" * 80)


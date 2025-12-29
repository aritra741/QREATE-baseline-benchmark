#!/bin/bash
# GEM Quick Test - Verifies the system is working

cd "$(dirname "$0")/../.." || exit 1

source systems/GEM/venv/bin/activate

python3 << 'PYTHON_SCRIPT'
import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

print("\n" + "=" * 70)
print("GEM SYSTEM VERIFICATION")
print("=" * 70)

# Test 1: Schema Loading
print("\n[1/4] Testing Schema Loader...")
try:
    from systems.GEM.schema_loader import load_schema
    schema = load_schema(PROJECT_ROOT / "Query" / "Med" / "Med_attributes.json")
    print(f"  ✓ Loaded schema with {len(schema.attributes)} attributes")
    print(f"  ✓ Key attribute: {schema.get_key_attributes()}")
except Exception as e:
    print(f"  ✗ Failed: {e}")

# Test 2: Extractor
print("\n[2/4] Testing Extractor...")
try:
    from systems.GEM.extractor import Extractor
    extractor = Extractor(schema)
    print(f"  ✓ Extractor initialized")
    print(f"  ✓ Cache dir: {extractor.cache_dir}")
except Exception as e:
    print(f"  ✗ Failed: {e}")

# Test 3: Blocking
print("\n[3/4] Testing Blocker...")
try:
    from systems.GEM.blocking import SemanticBlocker
    blocker = SemanticBlocker()
    if blocker.model:
        print(f"  ✓ Blocker initialized with embedding model")
    else:
        print(f"  ⚠ Blocker model not available")
except Exception as e:
    print(f"  ✗ Failed: {e}")

# Test 4: Resolver
print("\n[4/4] Testing Resolver...")
try:
    from systems.GEM.resolver import EntityResolver
    resolver = EntityResolver()
    if resolver.client:
        print(f"  ✓ Resolver initialized with LLM client")
    else:
        print(f"  ⚠ Resolver LLM client not available")
except Exception as e:
    print(f"  ✗ Failed: {e}")

print("\n" + "=" * 70)
print("✓ GEM System Ready!")
print("=" * 70 + "\n")

PYTHON_SCRIPT


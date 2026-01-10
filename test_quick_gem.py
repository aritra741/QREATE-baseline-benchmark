#!/usr/bin/env python3
"""Quick test to verify GEM components are working."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "systems"))

from GEM.blocking import SemanticBlocker
from GEM.resolver import EntityResolver

# Test data: synonyms and distinct variants
test_drugs = [
    "Promethazine",
    "promethazine",
    "PROMETHAZINE",
    "Aspirin",
    "aspirin",
    "Acetaminophen"
]

print("Testing GEM Resolution Pipeline")
print("=" * 80)
print(f"\nInput: {len(test_drugs)} drug mentions")
for i, drug in enumerate(test_drugs):
    print(f"  [{i}] {drug}")

# Initialize components
blocker = SemanticBlocker()
resolver = EntityResolver()

# Phase 1: Semantic blocking
print("\n" + "=" * 80)
print("PHASE 1: Semantic Blocking")
print("=" * 80)

for drug in test_drugs:
    blocker.add_and_link(drug)

blocks_dict = blocker.get_blocks()
blocks = list(blocks_dict.values())

print(f"\nProduced {len(blocks)} blocks:")
for i, block in enumerate(blocks):
    print(f"  Block {i+1}: {block}")

# Phase 2: LLM Resolution
print("\n" + "=" * 80)
print("PHASE 2: LLM Resolution")
print("=" * 80)

canonical_map = {}
for block in blocks:
    resolved = resolver.resolve_block(block)
    print(f"\nBlock {block} -> {resolved}")
    
    for canonical, variants in resolved.items():
        for variant in variants:
            canonical_map[variant] = canonical

print(f"\n" + "=" * 80)
print("FINAL CANONICAL MAP")
print("=" * 80)
for mention, canonical in canonical_map.items():
    print(f"  '{mention}' -> '{canonical}'")

print(f"\n✓ Test completed! {len(test_drugs)} mentions -> {len(set(canonical_map.values()))} canonical entities")

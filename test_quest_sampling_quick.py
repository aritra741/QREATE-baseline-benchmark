#!/usr/bin/env python
"""
Quick test of QUEST sampling - minimal version to check which datasets work.

This bypasses long operations and just focuses on whether sampling can extract evidence.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

# Set local path
os.environ["QUEST_INDEX_ROOT"] = str(PROJECT_ROOT.parent)

from evaluation.config import load_json

def quick_test():
    """Quick minimal test."""
    print("\n" + "=" * 70)
    print("QUEST SAMPLING QUICK TEST")
    print("=" * 70)
    
    # Test 1: Can we load the indexer?
    print("\n[TEST 1] Loading indexer...")
    try:
        from quest.db.indexer.indexer import load_all_indexer
        gb_indexer = load_all_indexer(table_to_type=None)
        available = list(gb_indexer.table_to_indexer.keys())
        print(f"✓ Indexer loaded. Available tables: {available}")
    except Exception as e:
        print(f"✗ Failed to load indexer: {e}")
        return
    
    # Test 2: Can we load Player schema?
    print("\n[TEST 2] Loading Player schema...")
    try:
        attr_path = PROJECT_ROOT / "Query/Player/Player_attributes.json"
        player_attrs = load_json(attr_path)
        player_entity_attrs = player_attrs.get("player", {})
        print(f"✓ Loaded {len(player_entity_attrs)} Player attributes")
        for attr in list(player_entity_attrs.keys())[:5]:
            print(f"  - {attr}")
        print(f"  ... ({len(player_entity_attrs) - 5} more)")
    except Exception as e:
        print(f"✗ Failed to load schema: {e}")
        return
    
    # Test 3: Can we initialize sampler?
    print("\n[TEST 3] Initializing sampler...")
    try:
        from quest.core.llm.sampler import AttrSampler
        
        # Build schema prompt
        attr_lines = []
        for attr_name, attr_info in player_entity_attrs.items():
            description = attr_info.get("description", "") if isinstance(attr_info, dict) else ""
            attr_lines.append(f"{attr_name}: {description}")
        prompt_str = "\n".join(attr_lines)
        
        sampler = AttrSampler(schema=prompt_str)
        print(f"✓ Sampler initialized")
    except Exception as e:
        print(f"✗ Failed to initialize sampler: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test 4: Get indexer for player entity
    print("\n[TEST 4] Getting player indexer...")
    try:
        indexer_obj, _ = gb_indexer.get_indexer("player")
        doc_ids = indexer_obj.get_docs_id()
        print(f"✓ Player indexer has {len(doc_ids)} documents")
        print(f"  First 5 doc IDs: {doc_ids[:5]}")
    except Exception as e:
        print(f"✗ Failed to get player indexer: {e}")
        return
    
    # Test 5: Try sampling (quick version)
    print("\n[TEST 5] Attempting sampling on player entity...")
    try:
        from quest.core.llm.llm_query import TextLLMQuerier
        
        querier = TextLLMQuerier(prompt=prompt_str)
        print(f"  Initialized querier")
        print(f"  Starting sampling...")
        sys.stdout.flush()
        
        # Try sampling (this might take a while!)
        import time
        start = time.time()
        print(f"  [Sampling started at {time.ctime()}]")
        sys.stdout.flush()
        
        sampler.try_sample(indexer_obj, prompt_str)
        
        elapsed = time.time() - start
        print(f"✓ Sampling completed in {elapsed:.1f}s!")
        sys.stdout.flush()
        
        # Check results
        success_count = 0
        for attr, evidence in sampler.map_attr_evidence.items():
            if evidence:
                success_count += 1
                evidence_len = len(evidence) if isinstance(evidence, str) else len(str(evidence))
                print(f"  ✓ {attr}: {evidence_len} chars")
            else:
                print(f"  ✗ {attr}: NO EVIDENCE")
        
        print(f"\nSUCCESS RATE: {success_count}/{len(sampler.map_attr_evidence)} attributes")
        sys.stdout.flush()
        
    except Exception as e:
        print(f"✗ Sampling failed: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        return
    
    # Test 6: Try Med dataset
    print("\n" + "=" * 70)
    print("[TEST 6] Testing Med/disease entity...")
    print("=" * 70)
    
    try:
        # Load Med schema
        attr_path = PROJECT_ROOT / "Query/Med/Med_attributes.json"
        med_attrs = load_json(attr_path)
        disease_attrs = med_attrs.get("disease", {})
        print(f"✓ Loaded {len(disease_attrs)} disease attributes")
        
        # Get disease indexer
        indexer_obj, _ = gb_indexer.get_indexer("disease")
        doc_ids = indexer_obj.get_docs_id()
        print(f"✓ Disease indexer has {len(doc_ids)} documents")
        
        # Initialize sampler for disease
        attr_lines = []
        for attr_name, attr_info in disease_attrs.items():
            description = attr_info.get("description", "") if isinstance(attr_info, dict) else ""
            attr_lines.append(f"{attr_name}: {description}")
        prompt_str = "\n".join(attr_lines)
        
        disease_sampler = AttrSampler(schema=prompt_str)
        print(f"✓ Disease sampler initialized")
        
        # Try sampling
        print(f"  Starting sampling on disease...")
        sys.stdout.flush()
        import time
        start = time.time()
        print(f"  [Disease sampling started at {time.ctime()}]")
        sys.stdout.flush()
        
        disease_sampler.try_sample(indexer_obj, prompt_str)
        
        elapsed = time.time() - start
        print(f"✓ Disease sampling completed in {elapsed:.1f}s!")
        sys.stdout.flush()
        
        # Check results
        success_count = 0
        for attr, evidence in disease_sampler.map_attr_evidence.items():
            if evidence:
                success_count += 1
        
        print(f"SUCCESS RATE: {success_count}/{len(disease_sampler.map_attr_evidence)} attributes")
        sys.stdout.flush()
        
    except Exception as e:
        print(f"✗ Med/disease test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    quick_test()


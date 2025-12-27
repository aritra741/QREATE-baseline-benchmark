#!/usr/bin/env python3
"""
Direct test: Compare ground truth labels vs indexed documents.
No pandas required - just CSV reading.
"""

import os
import sys
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

os.environ["QUEST_INDEX_ROOT"] = str(PROJECT_ROOT.parent)

def compare_ground_truth():
    """Compare ground truth vs indexed documents."""
    print("\n" + "=" * 80)
    print("GROUND TRUTH VS INDEXED DOCUMENTS COMPARISON")
    print("=" * 80)
    
    # Step 1: Load ground truth
    print("\n[1] Loading ground truth disease data...")
    gt_path = PROJECT_ROOT / "Data" / "Med" / "disease.csv"
    
    if not gt_path.exists():
        print(f"✗ Ground truth file not found: {gt_path}")
        return
    
    try:
        gt_rows = []
        with open(gt_path, 'r') as f:
            reader = csv.DictReader(f)
            gt_rows = list(reader)
        
        print(f"✓ Loaded ground truth with {len(gt_rows)} disease records")
        if gt_rows:
            cols = list(gt_rows[0].keys())
            print(f"   Columns: {cols[:5]}... ({len(cols)} total)")
            print(f"\n   Sample records:")
            for idx in range(min(3, len(gt_rows))):
                row = gt_rows[idx]
                print(f"     [{idx+1}] disease_name={row.get('disease_name', 'N/A')}, "
                      f"disease_type={row.get('disease_type', 'N/A')}")
    except Exception as e:
        print(f"✗ Failed to load ground truth: {e}")
        return
    
    # Step 2: Load indexed documents
    print("\n[2] Loading indexed disease documents...")
    try:
        from quest.db.indexer.indexer import load_all_indexer
        gb_indexer = load_all_indexer(table_to_type=None)
        indexer_obj, _ = gb_indexer.get_indexer("disease")
        doc_ids = indexer_obj.get_docs_id()
        print(f"✓ Loaded {len(doc_ids)} indexed disease documents")
        
        # Show sample IDs
        sorted_ids = sorted([int(d) for d in doc_ids])
        print(f"   First 10 IDs: {sorted_ids[:10]}")
        print(f"   Last 10 IDs: {sorted_ids[-10:]}")
        print(f"   ID range: {min(sorted_ids)}-{max(sorted_ids)}")
    except Exception as e:
        print(f"✗ Failed to load indexer: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 3: Compare
    print("\n[3] Comparing...")
    
    indexed_ids = set(int(d) for d in doc_ids)
    # The CSV should have rows 1 to len(gt_rows)
    gt_ids = set(range(1, len(gt_rows) + 1))
    
    print(f"\n   Expected ground truth IDs: 1-{len(gt_rows)} ({len(gt_ids)} total)")
    print(f"   Actual indexed IDs: {min(indexed_ids)}-{max(indexed_ids)} ({len(indexed_ids)} total)")
    
    # Check overlap
    overlap = indexed_ids & gt_ids
    only_in_gt = gt_ids - indexed_ids
    only_in_index = indexed_ids - gt_ids
    
    print(f"\n   ✓ Overlap (in both): {len(overlap)} documents ({100*len(overlap)/len(gt_ids):.1f}%)")
    print(f"   ✗ Missing from index: {len(only_in_gt)} documents ({100*len(only_in_gt)/len(gt_ids):.1f}%)")
    print(f"   ✗ Extra in index: {len(only_in_index)} documents ({100*len(only_in_index)/len(indexed_ids):.1f}%)")
    
    if only_in_gt:
        print(f"\n   Missing IDs sample: {sorted(list(only_in_gt))[:10]}")
    if only_in_index:
        print(f"   Extra IDs sample: {sorted(list(only_in_index))[:10]}")
    
    # Step 4: Sample and inspect
    print("\n[4] Sampling indexed documents to inspect content...")
    
    import random
    sample_size = min(5, len(doc_ids))
    sample_ids = random.sample(sorted(list(doc_ids)), sample_size)
    
    for i, doc_id in enumerate(sample_ids, 1):
        try:
            doc_text = indexer_obj.get_text_by_id(doc_id)
            if doc_text:
                preview = str(doc_text)[:150]
                # Replace newlines for readability
                preview = preview.replace('\n', ' ').strip()
                print(f"\n   [{doc_id}] {preview}...")
            else:
                print(f"\n   [{doc_id}] (empty document)")
        except Exception as e:
            print(f"\n   [{doc_id}] Error: {e}")
    
    # Step 5: Conclusion
    print(f"\n{'=' * 80}")
    print("CONCLUSIVE ANALYSIS")
    print('=' * 80)
    
    mismatch_ratio = len(only_in_index) / max(1, len(indexed_ids))
    missing_ratio = len(only_in_gt) / max(1, len(gt_ids))
    
    print(f"\nDocument Mismatch Statistics:")
    print(f"  Ground truth: {len(gt_rows)} curated disease documents")
    print(f"  Indexed: {len(indexed_ids)} documents")
    print(f"  Expected match: ~100%")
    print(f"  Actual match: {100*len(overlap)/len(gt_ids):.1f}%")
    
    if mismatch_ratio > 0.5 or missing_ratio > 0.5:
        print(f"\n❌ HYPOTHESIS CONFIRMED: Index has wrong documents!")
        print(f"   The index was built from the wrong dataset subset.")
        print(f"   → {100*missing_ratio:.1f}% of ground truth documents are missing from index")
        print(f"   → {100*mismatch_ratio:.1f}% of indexed documents are NOT in ground truth")
        print(f"\n   EXPLANATION: Index likely built from the 100K healthcare sample,")
        print(f"   but ground truth only covers the 6,100 curated disease/drug/institution docs.")
        return True
    elif mismatch_ratio > 0.1 or missing_ratio > 0.1:
        print(f"\n⚠️  PARTIAL MISMATCH:")
        print(f"   Some documents don't match ground truth.")
        print(f"   But majority ({100*len(overlap)/len(gt_ids):.1f}%) are correct.")
        return False
    else:
        print(f"\n✓ Index appears to match ground truth!")
        return False

if __name__ == "__main__":
    result = compare_ground_truth()
    sys.exit(0 if result else 1)

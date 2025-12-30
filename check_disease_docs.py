#!/usr/bin/env python3
"""Check what's actually in the disease documents."""
import os
import sys

# Add quest to path
sys.path.insert(0, '/uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main/systems')
sys.path.insert(0, '/uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main/systems/quest')

# Set environment
os.environ["QUEST_INDEX_ROOT"] = "/uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main"

from quest.db.indexer.indexer import load_all_indexer

# Load disease indexer
print("Loading disease indexer...")
gb_indexer = load_all_indexer(table_to_type=None)
indexer_obj, _ = gb_indexer.get_indexer("disease")

# Get first 10 documents
doc_ids = list(indexer_obj.get_docs_id())[:10]
print(f"\nChecking first 10 disease documents (IDs: {doc_ids})...")

for doc_id in doc_ids:
    # Get document text
    doc_text = indexer_obj.get_doc_text(doc_id)
    
    # Extract first 500 chars
    preview = doc_text[:500] if len(doc_text) > 500 else doc_text
    
    print(f"\n{'='*80}")
    print(f"Document ID: {doc_id}")
    print(f"Length: {len(doc_text)} chars")
    print(f"Preview (first 500 chars):")
    print(preview)
    print(f"{'='*80}")
    
    # Check for target disease names
    target_diseases = ['Type 2 Diabetes Mellitus', 'Tuberculosis', 'Fibromyalgia', 'Asthma', 'Depression']
    found = [d for d in target_diseases if d.lower() in doc_text.lower()]
    if found:
        print(f"✓ Contains target disease(s): {found}")
    
    # Check for Trigeminal Neuralgia
    if 'trigeminal neuralgia' in doc_text.lower():
        print(f"⚠ Contains 'Trigeminal Neuralgia'")


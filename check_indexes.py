#!/usr/bin/env python3
"""Quick diagnostic script to check QUEST index status."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

from quest.db.indexer.indexer import load_all_indexer

def check_indexes():
    """Check all QUEST indexes for document counts."""
    
    datasets = {
        'disease': 'TextDoc',
        'drug': 'TextDoc',
        'institution': 'TextDoc',
        'player': 'TextDoc',
        'team': 'TextDoc',
        'manager': 'TextDoc',
        'city': 'TextDoc',
        'art': 'TextDoc',
        'legal_case': 'TextDoc',
        'finance': 'TextDoc',
    }
    
    print("=" * 80)
    print("QUEST Index Status Check")
    print("=" * 80)
    
    for table_name in datasets:
        try:
            table_to_type = {table_name: datasets[table_name]}
            indexer = load_all_indexer(table_to_type=table_to_type)
            
            if table_name in indexer.table_to_indexer:
                idx = indexer.table_to_indexer[table_name]
                doc_ids = idx.get_docs_id()
                
                print(f"\n✓ {table_name:15} : {len(doc_ids):4} documents")
                
                if len(doc_ids) == 0:
                    print(f"  ⚠️  WARNING: Index is EMPTY!")
                elif len(doc_ids) <= 3:
                    print(f"  Document IDs: {doc_ids}")
                else:
                    print(f"  First 3 IDs: {doc_ids[:3]}")
                    print(f"  Last 3 IDs: {doc_ids[-3:]}")
            else:
                print(f"\n✗ {table_name:15} : NOT FOUND in indexer")
                
        except FileNotFoundError as e:
            print(f"\n✗ {table_name:15} : Index files not found")
            print(f"  Error: {e}")
        except Exception as e:
            print(f"\n✗ {table_name:15} : Error loading index")
            print(f"  Error: {e}")
    
    print("\n" + "=" * 80)
    print("Summary:")
    print("- If all indexes show 0 documents, run: python build_quest_indexes.py")
    print("- Check QUEST_INDEX_ROOT environment variable is set correctly")
    print("=" * 80)

if __name__ == "__main__":
    check_indexes()




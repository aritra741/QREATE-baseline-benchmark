#!/usr/bin/env python3
"""
Debug QUEST's document retrieval for filter_2 query
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))

os.chdir(PROJECT_ROOT)

# Suppress warnings
import warnings
warnings.filterwarnings("ignore")

def debug_quest_retrieval():
    """Debug QUEST's document retrieval."""
    
    print("\n" + "=" * 80)
    print("DEBUGGING QUEST DOCUMENT RETRIEVAL FOR FILTER_2")
    print("=" * 80)
    
    print("\n[1] Loading QUEST system...")
    try:
        from quest.db.indexer.indexer import load_all_indexer
        from quest.core.llm.sampler import AttrSampler
        import quest.conf.settings as settings
        print("✓ Loaded QUEST modules")
    except Exception as e:
        print(f"✗ Failed to load: {e}")
        return
    
    print("\n[2] Loading Player indices...")
    try:
        indexers = load_all_indexer(
            index_path=str(PROJECT_ROOT / "index" / "hnsw"),
            dataset="Player"
        )
        print(f"✓ Loaded indexers: {list(indexers.keys())}")
        
        # Get player indexer
        player_indexer = indexers.get("player")
        if not player_indexer:
            print("✗ No player indexer found!")
            return
        
        print(f"✓ Player indexer loaded")
        
        # Check how many documents
        print(f"\n[3] Checking indexed documents...")
        docs_meta_file = PROJECT_ROOT / "index" / "hnsw" / "player" / "docs_meta.json"
        if docs_meta_file.exists():
            import json
            with open(docs_meta_file) as f:
                docs_meta = json.load(f)
            print(f"✓ Found {len(docs_meta)} documents in index")
            print(f"  Sample doc_ids: {list(docs_meta.keys())[:10]}")
        
    except Exception as e:
        print(f"✗ Failed to load indices: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n[4] Checking query evidence...")
    try:
        # Create sampler
        attr_schema = """name: Player's full name
birth_date: Birth date in YYYY/M/D format
nationality: Player's country of origin
team: Current or most recent team name
position: Player's position (e.g., Frontcourt, Backcourt)
draft_year: Year player was drafted"""
        
        sampler = AttrSampler(schema=attr_schema)
        
        # The query is: WHERE position = 'Frontcourt'
        # In QUEST, the evidence for this query would be related to "position" attribute
        print("✓ Sampler created")
        print(f"  Schema: {attr_schema}")
        
        # The nl_query is: "Get Frontcourt player documents with names, teams, positions, nationalities, and draft years"
        evidence = "Frontcourt players"
        print(f"\n  Query evidence (NL query): {evidence}")
        
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n[5] Attempting semantic search for 'position' or 'Frontcourt'...")
    try:
        # Try semantic search using the indexer
        # This is what QUEST would do to find relevant documents
        
        # Search for "Frontcourt" as evidence
        results = player_indexer.get_top_docs_for_text_query("Frontcourt position", topk=10)
        print(f"✓ Semantic search results for 'Frontcourt position':")
        print(f"  Found {len(results)} documents")
        for i, (doc_id, score) in enumerate(results[:10]):
            print(f"    {i+1}. doc_id={doc_id}, score={score:.4f}")
        
        if results:
            print(f"\n✓ QUEST retrieval works! It can find documents semantically.")
        else:
            print(f"\n✗ No documents found - semantic search failed!")
        
    except AttributeError:
        print("✗ Indexer doesn't have get_top_docs_for_text_query method")
        print("  Checking available methods...")
        print(f"  Available methods: {[m for m in dir(player_indexer) if not m.startswith('_')]}")
    except Exception as e:
        print(f"✗ Semantic search failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n[6] Checking document content...")
    try:
        # Check a sample document that SHOULD match "Frontcourt"
        sample_doc_ids = [1, 2, 10, 20, 50, 100]
        for doc_id in sample_doc_ids:
            doc_path = PROJECT_ROOT / "source_data" / "Player" / "player" / f"{doc_id}.txt"
            if doc_path.exists():
                with open(doc_path) as f:
                    content = f.read()
                has_frontcourt = "Frontcourt" in content
                print(f"  doc {doc_id}: has 'Frontcourt'? {has_frontcourt}")
                if has_frontcourt:
                    print(f"    Preview: {content[:200]}...")
                    break
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_quest_retrieval()


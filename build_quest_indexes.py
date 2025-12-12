#!/usr/bin/env python3
"""
Build QUEST indexes from raw unstructured documents.

This script reads raw documents from the raw/datasets/ directory,
builds document-level and segment-level embeddings indexes,
and saves them for QUEST to use when executing queries.

Usage:
    python build_quest_indexes.py                    # Build all indexes
    python build_quest_indexes.py --dataset Player   # Build only Player indexes
    python build_quest_indexes.py --debug            # Debug mode (2 docs per table)
"""

import argparse
import os
import sys
from pathlib import Path
import json

# CRITICAL: Parse args BEFORE importing torch/QUEST to set CPU mode
parser_early = argparse.ArgumentParser(add_help=False)
parser_early.add_argument("--cpu", action="store_true")
args_early, _ = parser_early.parse_known_args()

# Force CPU mode by disabling CUDA visibility BEFORE any imports
if args_early.cpu:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    print("🔧 FORCING CPU MODE (CUDA disabled)")
    print("   This will be slower but guaranteed to work\n")

# Add project paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

# ==============================================================================
# RAW DOCUMENT PATHS - Maps to your raw/ folder structure
# ==============================================================================

RAW_DATA_DIR = PROJECT_ROOT / "raw" / "datasets"

# Maps dataset/table names to their document directories
DOCUMENT_PATHS = {
    "Healthcare": {
        "disease": RAW_DATA_DIR / "Healthcare" / "disease_small",
        "drug": RAW_DATA_DIR / "Healthcare" / "drug_small",
        "institution": RAW_DATA_DIR / "Healthcare" / "institutes_small",
    },
    "Player": {
        "player": RAW_DATA_DIR / "Player" / "player",
        "team": RAW_DATA_DIR / "Player" / "team",
        "manager": RAW_DATA_DIR / "Player" / "owner",  # owner = manager in raw data
        "city": RAW_DATA_DIR / "Player" / "city",
    },
    "Art": {
        "art": RAW_DATA_DIR / "Art" / "wikiart",
    },
    "Legal": {
        "legal_case": RAW_DATA_DIR / "Legal" / "legal_case",
    },
    "Finance": {
        "finance": RAW_DATA_DIR / "Finance" / "finance",
    },
}

def check_directories():
    """Check which document directories exist."""
    print("\n" + "="*70)
    print("CHECKING RAW DOCUMENT DIRECTORIES")
    print("="*70 + "\n")
    
    available = {}
    for dataset, tables in DOCUMENT_PATHS.items():
        available[dataset] = {}
        print(f"📁 {dataset}:")
        for table, path in tables.items():
            if path.exists():
                txt_files = list(path.glob("*.txt"))
                available[dataset][table] = len(txt_files)
                print(f"   ✅ {table}: {len(txt_files)} documents at {path}")
            else:
                available[dataset][table] = 0
                print(f"   ❌ {table}: NOT FOUND at {path}")
        print()
    
    return available


def rebuild_global_config():
    """
    Rebuild the global index config file to include ALL available table indices.
    
    This is necessary because build_all_indexer() is called once per dataset,
    and each call overwrites the global config. This function consolidates all
    tables that have been indexed into a single global config file.
    """
    from quest.conf import settings
    
    # Get the HNSW directory where all table indices are stored
    HNSW_DIR = os.path.join(settings.INDEX_ROOT_DIR, "hnsw")
    CONFIG_FILE = settings.GLOBAL_INDEX_CONFIG
    
    if not os.path.exists(HNSW_DIR):
        print(f"   ⚠️  HNSW directory not found: {HNSW_DIR}")
        return
    
    # Find all table directories
    table_dirs = [d for d in os.listdir(HNSW_DIR) 
                  if os.path.isdir(os.path.join(HNSW_DIR, d))]
    table_dirs.sort()
    
    if not table_dirs:
        print(f"   ⚠️  No table indices found in {HNSW_DIR}")
        return
    
    print(f"   📊 Found {len(table_dirs)} table indices:")
    for table in table_dirs:
        print(f"      - {table}")
    
    # Create consolidated table_to_type mapping
    table_to_type = {table: "TextDoc" for table in table_dirs}
    
    # Write the consolidated config
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(table_to_type, f, ensure_ascii=False, indent=2)
    
    print(f"   ✅ Global config consolidated with {len(table_to_type)} tables")
    print(f"      Config: {CONFIG_FILE}")


def build_indexes(dataset: str = None, debug: bool = False, force_cpu: bool = False):
    """Build QUEST indexes for specified dataset(s)."""
    
    print("\n" + "="*70)
    print("BUILDING QUEST INDEXES")
    print("="*70 + "\n")
    
    # Import QUEST indexer components
    try:
        from quest.db.indexer.indexer import build_all_indexer, GlobalIndexer
        from quest.core.embedding.e5Embedding import batchedE5Embeddings
        from quest.core.chunker.chunker import TokenTextChunker
        import torch
        
        # Setup embedding model - force CPU if requested or if CUDA is problematic
        if force_cpu:
            device = "cpu"
            print(f"🔧 Using device: CPU (forced)")
        else:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"🔧 Using device: {device}")
        
        embedding_model = batchedE5Embeddings(
            model_path="sentence-transformers/all-MiniLM-L6-v2",
            device=device,
            batch_size=32
        )
        print(f"✅ Embedding model loaded: all-MiniLM-L6-v2")
        
        chunker = TokenTextChunker(chunk_size=512, chunk_overlap=64)
        print(f"✅ Chunker configured: 512 tokens, 64 overlap\n")
        
    except ImportError as e:
        print(f"❌ Failed to import QUEST modules: {e}")
        print("   Make sure you have all dependencies installed.")
        sys.exit(1)
    
    # Determine which datasets to build
    if dataset:
        datasets_to_build = {dataset: DOCUMENT_PATHS.get(dataset, {})}
        if not datasets_to_build[dataset]:
            print(f"❌ Unknown dataset: {dataset}")
            print(f"   Available: {list(DOCUMENT_PATHS.keys())}")
            sys.exit(1)
    else:
        datasets_to_build = DOCUMENT_PATHS
    
    # Build indexes for each dataset
    for ds_name, tables in datasets_to_build.items():
        print(f"\n{'='*50}")
        print(f"📊 Building indexes for: {ds_name}")
        print(f"{'='*50}\n")
        
        doc_dirs = []
        table_names = []
        types = []
        
        for table_name, doc_path in tables.items():
            if doc_path.exists():
                txt_count = len(list(doc_path.glob("*.txt")))
                if txt_count > 0:
                    doc_dirs.append(str(doc_path))
                    table_names.append(table_name)
                    types.append("TextDoc")
                    print(f"   📄 {table_name}: {txt_count} documents")
        
        if not doc_dirs:
            print(f"   ⚠️  No documents found for {ds_name}, skipping...")
            continue
        
        print(f"\n   🔨 Building index for {len(doc_dirs)} tables...")
        
        try:
            global_indexer = build_all_indexer(
                doc_dirs=doc_dirs,
                tables_name=table_names,
                types=types,
                debug_flag=debug,
                chunker=chunker,
                embedding_model=embedding_model
            )
            
            # Save the indexer
            print(f"\n   💾 Saving indexes...")
            global_indexer.save_indexer()
            print(f"   ✅ Indexes saved successfully!")
            
        except Exception as e:
            print(f"   ❌ Failed to build index for {ds_name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print("\n" + "="*70)
    print("✨ INDEX BUILDING COMPLETE!")
    print("="*70)
    
    # CRITICAL FIX: Rebuild the global config to include ALL tables from all datasets
    # Each dataset build overwrites the config, so we need to consolidate them
    print("\n🔧 Consolidating global index config with ALL tables...")
    rebuild_global_config()
    
    print("\nYou can now run queries with:")
    print("   python run_challenging_queries.py --systems quest")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Build QUEST indexes from raw documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python build_quest_indexes.py                    # Build all indexes
    python build_quest_indexes.py --dataset Player   # Build only Player indexes  
    python build_quest_indexes.py --check            # Check available documents
    python build_quest_indexes.py --debug            # Debug mode (few docs)
        """
    )
    
    parser.add_argument(
        "--dataset",
        choices=["Healthcare", "Player", "Art", "Legal", "Finance"],
        help="Build index for specific dataset only"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check which documents are available"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debug mode - only process 2 documents per table"
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU mode (use this if you get CUDA errors)"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("QUEST INDEX BUILDER")
    print("="*70)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Raw data dir: {RAW_DATA_DIR}")
    
    # Check directories first
    available = check_directories()
    
    if args.check:
        # Just checking, don't build
        total_docs = sum(
            count 
            for ds in available.values() 
            for count in ds.values()
        )
        print(f"Total documents available: {total_docs}")
        return
    
    # Build indexes
    build_indexes(dataset=args.dataset, debug=args.debug, force_cpu=args.cpu)


if __name__ == "__main__":
    main()


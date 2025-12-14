"""
Preprocess data for Unify system and save indexes offline.

This script performs offline preprocessing as described in the Unify paper:
1. Load text documents from source_data
2. Chunk documents into segments
3. Generate embeddings for chunks
4. Build and save HNSW indexes
5. Save metadata and embeddings for reuse during queries

Requirements:
- Python 3.10+
- Unify dependencies (see requirements.txt)
- Models in: main/models/tokenizer and main/models/embedding
- Compatible with x86_64 architecture (CHPC)

Note: If you encounter numpy version errors, upgrade numpy:
    pip install --upgrade numpy

Usage:
    # From UDA-Bench-main directory:
    python systems/Unify/scripts/preprocess_unify_data.py --datasets all
    
    # Or from systems/Unify directory:
    python scripts/preprocess_unify_data.py --datasets all
    
    # Preprocess specific datasets
    python systems/Unify/scripts/preprocess_unify_data.py --datasets Med Player
    
    # Preprocess specific entities
    python systems/Unify/scripts/preprocess_unify_data.py --entities Med disease
"""

import argparse
import json
import os
import sys
import time
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import traceback

# Determine project root (UDA-Bench-main directory)
# Script is in: systems/Unify/scripts/preprocess_unify_data.py
# So PROJECT_ROOT should be 3 levels up
SCRIPT_DIR = Path(__file__).parent.resolve()
UNIFY_DIR = SCRIPT_DIR.parent  # systems/Unify
SYSTEMS_DIR = UNIFY_DIR.parent  # systems
PROJECT_ROOT = SYSTEMS_DIR.parent  # UDA-Bench-main

# Add paths for imports
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(UNIFY_DIR / "main"))

import numpy as np
# pandas not needed for preprocessing

# Configure logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==============================================================================
# DATA MAPPINGS
# ==============================================================================

# Map dataset/entity to source_data directory paths (relative to PROJECT_ROOT)
SOURCE_DATA_MAP = {
    ("Med", "disease"): PROJECT_ROOT / "source_data" / "Healthcare" / "disease_small",
    ("Med", "drug"): PROJECT_ROOT / "source_data" / "Healthcare" / "drug_small",
    ("Med", "institution"): PROJECT_ROOT / "source_data" / "Healthcare" / "institutes_small",
    ("Player", "player"): PROJECT_ROOT / "source_data" / "Player" / "player",
    ("Player", "city"): PROJECT_ROOT / "source_data" / "Player" / "city",
    ("Player", "team"): PROJECT_ROOT / "source_data" / "Player" / "team",
    ("Player", "owner"): PROJECT_ROOT / "source_data" / "Player" / "owner",
    ("Art", "art"): PROJECT_ROOT / "source_data" / "Art" / "wikiart",
    ("Legal", "legal_case"): PROJECT_ROOT / "source_data" / "Legal" / "legal_case",
    ("Finan", "finance"): PROJECT_ROOT / "source_data" / "Finance" / "finance",
}

# Output directory for preprocessed data (relative to PROJECT_ROOT)
PREPROCESS_OUTPUT_DIR = PROJECT_ROOT / "preprocess_unify" / "indexes"


# ==============================================================================
# PREPROCESSING CLASS
# ==============================================================================

class UnifyPreprocessor:
    """Handles offline preprocessing of data for Unify."""
    
    def __init__(self, output_dir: Path = PREPROCESS_OUTPUT_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.unify_main_dir = UNIFY_DIR / "main"
        
        # Initialize Unify modules
        self._initialize_unify()
    
    def _initialize_unify(self):
        """Load Unify modules."""
        try:
            # Change to Unify main directory for imports
            original_cwd = os.getcwd()
            os.chdir(self.unify_main_dir)
            
            # vllm is imported but not used in chunking - make it optional
            try:
                import vllm
            except ImportError:
                # Create a dummy vllm module if not available (not needed for preprocessing)
                import sys
                from types import ModuleType
                vllm = ModuleType('vllm')
                sys.modules['vllm'] = vllm
                logger.warning("vllm not available, using dummy module (not needed for preprocessing)")
            
            from chunk import ChunkExtractor, load_process_data_chunks
            from embed import EmbedModel
            from index import indexHNSW
            
            self.ChunkExtractor = ChunkExtractor
            self.load_process_data_chunks = load_process_data_chunks
            self.EmbedModel = EmbedModel
            self.indexHNSW = indexHNSW
            
            # Restore original directory
            os.chdir(original_cwd)
            
            logger.info("✓ Unify modules loaded successfully")
        except Exception as e:
            logger.error(f"✗ Failed to load Unify modules: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def get_data_path(self, dataset: str, entity: str) -> Optional[Path]:
        """Get source data path for a dataset/entity combination."""
        key = (dataset, entity.lower())
        
        for (ds, ent), path in SOURCE_DATA_MAP.items():
            if ds.lower() == dataset.lower() and ent.lower() == entity.lower():
                if path.exists():
                    txt_files = list(path.glob("*.txt"))
                    if txt_files:
                        return path
                    else:
                        logger.warning(f"No .txt files in {path}")
                        return None
                else:
                    logger.warning(f"Path does not exist: {path}")
                    return None
        
        return None
    
    def preprocess_entity(self, dataset: str, entity: str) -> Dict:
        """Preprocess a single dataset/entity combination."""
        logger.info(f"\n{'='*70}")
        logger.info(f"Preprocessing {dataset}/{entity}...")
        logger.info(f"{'='*70}")
        
        result = {
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat(),
            "status": "pending",
            "errors": []
        }
        
        original_cwd = os.getcwd()
        
        try:
            start_time = time.time()
            
            # 1. Get data path
            data_path = self.get_data_path(dataset, entity)
            if not data_path:
                result["status"] = "failed"
                result["errors"].append(f"No data path found for {dataset}/{entity}")
                logger.error(f"✗ {result['errors'][-1]}")
                return result
            
            txt_files = list(data_path.glob("*.txt"))
            logger.info(f"✓ Found {len(txt_files)} text files in {data_path}")
            
            # 2. Initialize models
            logger.info("Initializing embedding model...")
            try:
                # Use paths relative to Unify main directory
                tokenizer_path = self.unify_main_dir / "models" / "tokenizer"
                embedding_path = self.unify_main_dir / "models" / "embedding"
                
                if not tokenizer_path.exists():
                    raise FileNotFoundError(f"Tokenizer model not found: {tokenizer_path}")
                if not embedding_path.exists():
                    raise FileNotFoundError(f"Embedding model not found: {embedding_path}")
                
                # Change to Unify main directory for model loading
                os.chdir(self.unify_main_dir)
                
                embed_model = self.EmbedModel(
                    tokenizer_path=str(tokenizer_path),
                    sentence_model_path=str(embedding_path)
                )
                logger.info(f"✓ Embedding model initialized from {embedding_path}")
            except Exception as e:
                result["status"] = "failed"
                result["errors"].append(f"Failed to initialize embedding model: {e}")
                logger.error(f"✗ {result['errors'][-1]}")
                logger.error(f"  Make sure models are in: {self.unify_main_dir / 'models'}")
                os.chdir(original_cwd)
                return result
            
            chunk_extractor = self.ChunkExtractor()
            logger.info("✓ Chunk extractor initialized")
            
            # 3. Load and chunk data
            logger.info(f"Loading and chunking data from {data_path}...")
            try:
                all_file_data, all_chunks, all_ids, all_embeds, all_chunk_locs = self.load_process_data_chunks(
                    embed_model, chunk_extractor, str(data_path)
                )
                logger.info(f"✓ Loaded {len(all_file_data)} files")
                logger.info(f"✓ Created {len(all_chunks)} chunks")
                logger.info(f"✓ Generated {len(all_embeds)} embeddings")
            except Exception as e:
                result["status"] = "failed"
                result["errors"].append(f"Failed to load and chunk data: {e}")
                logger.error(f"✗ {result['errors'][-1]}")
                logger.error(traceback.format_exc())
                os.chdir(original_cwd)
                return result
            
            # 4. Build HNSW index
            logger.info("Building HNSW index...")
            try:
                index = self.indexHNSW(all_chunks, all_embeds, all_ids, all_chunk_locs)
                logger.info(f"✓ HNSW index built with {len(all_chunks)} items")
            except Exception as e:
                result["status"] = "failed"
                result["errors"].append(f"Failed to build index: {e}")
                logger.error(f"✗ {result['errors'][-1]}")
                logger.error(traceback.format_exc())
                os.chdir(original_cwd)
                return result
            
            # 5. Save preprocessed data
            output_subdir = self.output_dir / dataset / entity
            output_subdir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Saving preprocessed data to {output_subdir}...")
            
            try:
                # Save all components as pickle for easy reloading
                preprocessed_data = {
                    "all_file_data": all_file_data,
                    "all_chunks": all_chunks,
                    "all_ids": all_ids,
                    "all_embeds": all_embeds,
                    "all_chunk_locs": all_chunk_locs,
                    "index": index,
                }
                
                with open(output_subdir / "preprocessed_data.pkl", "wb") as f:
                    pickle.dump(preprocessed_data, f)
                logger.info(f"✓ Saved preprocessed data to preprocessed_data.pkl")
                
                # Save metadata as JSON
                metadata = {
                    "dataset": dataset,
                    "entity": entity,
                    "num_files": len(all_file_data),
                    "num_chunks": len(all_chunks),
                    "num_embeddings": len(all_embeds),
                    "embedding_dim": int(all_embeds[0].shape[0]) if len(all_embeds) > 0 else None,
                    "index_class": str(type(index).__name__),
                    "created_at": datetime.now().isoformat(),
                    "data_path": str(data_path),
                }
                
                with open(output_subdir / "metadata.json", "w") as f:
                    json.dump(metadata, f, indent=2)
                logger.info(f"✓ Saved metadata to metadata.json")
                
            except Exception as e:
                result["status"] = "failed"
                result["errors"].append(f"Failed to save preprocessed data: {e}")
                logger.error(f"✗ {result['errors'][-1]}")
                logger.error(traceback.format_exc())
                os.chdir(original_cwd)
                return result
            
            elapsed = time.time() - start_time
            result["status"] = "completed"
            result["elapsed_seconds"] = elapsed
            result["output_dir"] = str(output_subdir)
            
            logger.info(f"✓ Preprocessing completed in {elapsed:.2f}s")
            logger.info(f"✓ Output saved to: {output_subdir}")
            
            os.chdir(original_cwd)
            return result
            
        except Exception as e:
            result["status"] = "failed"
            result["errors"].append(f"Unexpected error: {e}")
            logger.error(f"✗ {result['errors'][-1]}")
            logger.error(traceback.format_exc())
            os.chdir(original_cwd)
            return result
    
    def preprocess_all(self) -> Dict:
        """Preprocess all available datasets."""
        results = {
            "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "started_at": datetime.now().isoformat(),
            "datasets": {}
        }
        
        # Group by dataset
        datasets = {}
        for (ds, ent) in SOURCE_DATA_MAP.keys():
            if ds not in datasets:
                datasets[ds] = []
            datasets[ds].append(ent)
        
        # Process each dataset/entity
        total = sum(len(entities) for entities in datasets.values())
        current = 0
        
        for dataset in sorted(datasets.keys()):
            for entity in sorted(datasets[dataset]):
                current += 1
                logger.info(f"\n[{current}/{total}] Processing {dataset}/{entity}...")
                result = self.preprocess_entity(dataset, entity)
                
                if dataset not in results["datasets"]:
                    results["datasets"][dataset] = {}
                results["datasets"][dataset][entity] = result
        
        results["completed_at"] = datetime.now().isoformat()
        
        return results


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Preprocess data for Unify system and save offline indexes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preprocess all datasets
  python systems/Unify/scripts/preprocess_unify_data.py --datasets all
  
  # Preprocess specific datasets
  python systems/Unify/scripts/preprocess_unify_data.py --datasets Med Player
  
  # Preprocess specific entities
  python systems/Unify/scripts/preprocess_unify_data.py --entities Med disease Med drug Player player
  
  # Specify custom output directory
  python systems/Unify/scripts/preprocess_unify_data.py --datasets all --output-dir /path/to/indexes
        """
    )
    
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=list(set(ds for ds, _ in SOURCE_DATA_MAP.keys())) + ["all"],
        default=["all"],
        help="Datasets to preprocess (default: all)"
    )
    
    parser.add_argument(
        "--entities",
        nargs="+",
        help="Specific dataset/entity combinations (e.g., Med disease Player player)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PREPROCESS_OUTPUT_DIR,
        help=f"Output directory for preprocessed indexes (default: {PREPROCESS_OUTPUT_DIR})"
    )
    
    args = parser.parse_args()
    
    # Initialize preprocessor
    preprocessor = UnifyPreprocessor(output_dir=args.output_dir)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"UNIFY DATA PREPROCESSING")
    logger.info(f"{'='*70}")
    logger.info(f"Project root: {PROJECT_ROOT}")
    logger.info(f"Unify directory: {UNIFY_DIR}")
    logger.info(f"Output directory: {args.output_dir}")
    
    # Determine what to preprocess
    if args.entities:
        # Preprocess specific entities
        logger.info(f"Mode: Preprocess specific entities")
        
        # Parse entity arguments (format: Dataset entity Dataset entity ...)
        entities_to_process = []
        for i in range(0, len(args.entities), 2):
            if i + 1 < len(args.entities):
                dataset = args.entities[i]
                entity = args.entities[i + 1]
                entities_to_process.append((dataset, entity))
        
        results = {
            "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "started_at": datetime.now().isoformat(),
            "datasets": {}
        }
        
        for dataset, entity in entities_to_process:
            result = preprocessor.preprocess_entity(dataset, entity)
            if dataset not in results["datasets"]:
                results["datasets"][dataset] = {}
            results["datasets"][dataset][entity] = result
        
        results["completed_at"] = datetime.now().isoformat()
    
    elif "all" in args.datasets:
        # Preprocess all
        logger.info(f"Mode: Preprocess all datasets")
        results = preprocessor.preprocess_all()
    
    else:
        # Preprocess specific datasets
        logger.info(f"Mode: Preprocess specific datasets: {args.datasets}")
        
        results = {
            "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "started_at": datetime.now().isoformat(),
            "datasets": {}
        }
        
        for dataset in sorted(args.datasets):
            entities = sorted(set(ent for ds, ent in SOURCE_DATA_MAP.keys() if ds == dataset))
            for entity in entities:
                result = preprocessor.preprocess_entity(dataset, entity)
                if dataset not in results["datasets"]:
                    results["datasets"][dataset] = {}
                results["datasets"][dataset][entity] = result
        
        results["completed_at"] = datetime.now().isoformat()
    
    # Print summary
    logger.info(f"\n{'='*70}")
    logger.info(f"SUMMARY")
    logger.info(f"{'='*70}")
    
    total_completed = 0
    total_failed = 0
    
    for dataset, entities in results["datasets"].items():
        for entity, result in entities.items():
            status = result.get("status", "unknown")
            if status == "completed":
                total_completed += 1
                elapsed = result.get("elapsed_seconds", 0)
                logger.info(f"✓ {dataset}/{entity}: {elapsed:.2f}s")
            else:
                total_failed += 1
                errors = result.get("errors", [])
                logger.error(f"✗ {dataset}/{entity}: {status}")
                for error in errors:
                    logger.error(f"  - {error}")
    
    logger.info(f"\nTotal completed: {total_completed}")
    logger.info(f"Total failed: {total_failed}")
    logger.info(f"Indexes saved to: {args.output_dir}")
    
    # Save results summary
    summary_file = args.output_dir / "preprocessing_summary.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"\nResults saved to: {summary_file}")
    
    logger.info(f"{'='*70}\n")
    
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


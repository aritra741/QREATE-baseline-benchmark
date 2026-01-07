"""
Preprocess raw unstructured data from source_data/ into proper UQE format.

This creates embeddings directly from raw unstructured text, NOT from cleaned JSON.
This is critical for research integrity - to match the UQE paper's design.

Pipeline:
  source_data/[dataset]/[files].txt 
    → Extract raw text as "description" 
    → Generate embeddings from description
    → Create JSON with proper structure
    → Cluster embeddings
    → Save for UQE queries
"""

import os
import json
import numpy as np
from pathlib import Path
import logging
from typing import Dict, List, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('UQE.preprocess')

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    logger.warning("sentence-transformers not available, will need to install it")
    EMBEDDINGS_AVAILABLE = False


def load_raw_text_data(data_dir: str) -> List[Dict]:
    """
    Load all raw text files from a directory.
    Each file = one row, with the file content as the "description".
    
    Args:
        data_dir: Directory containing .txt files
        
    Returns:
        List of dicts with 'id' and 'description' keys
    """
    rows = []
    txt_files = sorted(Path(data_dir).glob('*.txt'))
    
    logger.info(f"Found {len(txt_files)} text files in {data_dir}")
    
    for idx, file_path in enumerate(txt_files):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
            
            if content:  # Only add non-empty files
                rows.append({
                    'id': idx,
                    'filename': file_path.stem,
                    'description': content
                })
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
    
    logger.info(f"Loaded {len(rows)} non-empty documents")
    return rows


def generate_embeddings(texts: List[str], model_name: str = "all-MiniLM-L6-v2") -> np.ndarray:
    """
    Generate embeddings from raw text using sentence-transformers.
    
    Args:
        texts: List of text strings to embed
        model_name: Name of the sentence-transformers model
        
    Returns:
        numpy array of embeddings (n_samples, embedding_dim)
    """
    if not EMBEDDINGS_AVAILABLE:
        raise ImportError("Please install sentence-transformers: pip install sentence-transformers")
    
    logger.info(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)
    
    logger.info(f"Generating embeddings for {len(texts)} texts...")
    embeddings = model.encode(texts, show_progress_bar=True)
    
    logger.info(f"Generated embeddings shape: {embeddings.shape}")
    return embeddings


def create_dataset_json(rows: List[Dict], output_path: str):
    """
    Create JSON file in UQE format from raw data.
    
    Args:
        rows: List of dicts with id, description
        output_path: Where to save the JSON
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2)
    
    logger.info(f"Saved dataset JSON to {output_path}")


def preprocess_dataset(source_dir: str, output_dir: str, dataset_name: str, 
                      generate_embeddings_flag: bool = True):
    """
    Preprocess a complete dataset from raw text to UQE format.
    
    Args:
        source_dir: Directory with raw .txt files (from source_data/)
        output_dir: Where to save JSON and embeddings
        dataset_name: Name of dataset (for logging)
        generate_embeddings_flag: Whether to generate embeddings
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"Preprocessing {dataset_name} dataset")
    logger.info(f"{'='*70}")
    
    # Step 1: Load raw text data
    logger.info("\nStep 1: Loading raw text data...")
    rows = load_raw_text_data(source_dir)
    
    if not rows:
        logger.error(f"No data found in {source_dir}")
        return
    
    # Step 2: Create JSON
    logger.info("\nStep 2: Creating dataset JSON...")
    json_path = os.path.join(output_dir, 'dataset.json')
    create_dataset_json(rows, json_path)
    
    # Step 3: Generate embeddings if requested
    if generate_embeddings_flag:
        logger.info("\nStep 3: Generating embeddings from raw descriptions...")
        descriptions = [row['description'] for row in rows]
        
        try:
            embeddings = generate_embeddings(descriptions)
            
            # Save embeddings
            embeddings_path = os.path.join(output_dir, 'embeddings.npy')
            os.makedirs(os.path.dirname(embeddings_path), exist_ok=True)
            np.save(embeddings_path, embeddings)
            
            logger.info(f"Saved embeddings to {embeddings_path}")
            logger.info(f"Embeddings shape: {embeddings.shape}")
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            logger.info("Continuing without embeddings...")
    
    logger.info(f"\n✓ Preprocessing complete for {dataset_name}")
    logger.info(f"  - JSON: {json_path}")
    logger.info(f"  - Embeddings: {os.path.join(output_dir, 'embeddings.npy')}")
    logger.info(f"  - Total rows: {len(rows)}")


def main():
    """
    Preprocess all datasets.
    Auto-detects paths relative to script location.
    """
    # Get paths relative to this script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    
    base_source = os.path.join(project_root, 'source_data')
    base_output = os.path.join(script_dir, 'data')
    
    logger.info(f"Script directory: {script_dir}")
    logger.info(f"Project root: {project_root}")
    logger.info(f"Source base: {base_source}")
    logger.info(f"Output base: {base_output}")
    
    # Define datasets to preprocess
    datasets = [
        {
            'name': 'disease',
            'source': os.path.join(base_source, 'Healthcare/disease_small'),
            'output': os.path.join(base_output, 'disease')
        },
        {
            'name': 'drug',
            'source': os.path.join(base_source, 'Healthcare/drug_small'),
            'output': os.path.join(base_output, 'drug')
        },
        {
            'name': 'institutes',
            'source': os.path.join(base_source, 'Healthcare/institutes_small'),
            'output': os.path.join(base_output, 'institutes')
        },
        {
            'name': 'player',
            'source': os.path.join(base_source, 'Player/player'),
            'output': os.path.join(base_output, 'nba')
        },
        {
            'name': 'team',
            'source': os.path.join(base_source, 'Player/team'),
            'output': os.path.join(base_output, 'team')
        },
        {
            'name': 'city',
            'source': os.path.join(base_source, 'Player/city'),
            'output': os.path.join(base_output, 'city')
        },
        {
            'name': 'owner',
            'source': os.path.join(base_source, 'Player/owner'),
            'output': os.path.join(base_output, 'manager')
        },
    ]
    
    # Preprocess each dataset
    processed_count = 0
    failed_count = 0
    
    for dataset in datasets:
        if os.path.exists(dataset['source']):
            try:
                preprocess_dataset(
                    source_dir=dataset['source'],
                    output_dir=dataset['output'],
                    dataset_name=dataset['name'],
                    generate_embeddings_flag=True
                )
                processed_count += 1
            except Exception as e:
                logger.error(f"Failed to preprocess {dataset['name']}: {e}")
                failed_count += 1
        else:
            logger.warning(f"Source directory not found: {dataset['source']}")
            failed_count += 1
    
    logger.info(f"\n{'='*70}")
    logger.info(f"Preprocessing Summary")
    logger.info(f"{'='*70}")
    logger.info(f"✓ Successfully processed: {processed_count} datasets")
    logger.info(f"✗ Failed/skipped: {failed_count} datasets")
    logger.info(f"Total: {len(datasets)} datasets")
    
    if processed_count == 0:
        logger.error("No datasets were successfully processed!")
        return False
    elif failed_count > 0:
        logger.warning(f"Preprocessing completed with {failed_count} failures")
    else:
        logger.info("All datasets preprocessed successfully!")
    
    logger.info(f"{'='*70}\n")
    
    return processed_count > 0


if __name__ == '__main__':
    main()

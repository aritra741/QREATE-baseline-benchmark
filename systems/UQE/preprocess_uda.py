"""
Preprocess UDA benchmark datasets for UQE.
Converts CSV files to JSON format and generates embeddings for stratified sampling.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from repository import ModelRepository
from gen_embeds import get_text_embeds, get_image_embeds
import config_uqe

# UDA dataset paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "Data"
UQE_DATA_DIR = Path(__file__).parent / "data"

# Dataset mappings: (dataset_name, entity_name, entity_file)
DATASETS = {
    "Med": [
        ("disease", "disease.csv"),
        ("drug", "drug.csv"),
        ("institutes", "institution.csv"),
    ],
    "Player": [
        ("nba", "player.csv"),
        ("team", "team.csv"),
        ("manager", "manager.csv"),
        ("city", "city.csv"),
    ],
    "Art": [
        ("Wikiart", "Art.csv"),
    ],
    "Legal": [
        ("LCR", "Legal.csv"),
    ],
    "Finan": [
        ("Finance", "Finan.csv"),
    ],
}

# Column mappings: dataset -> entity -> {csv_col: json_key}
# Use the 'description' column (or text representation) for embeddings
TEXT_COLUMNS = {
    "Med": {
        "disease": ["disease_name", "pathogenesis", "etiology", "diagnostic_methods", 
                   "common_symptoms", "complications", "treatments", "prognosis"],
        "drug": ["generic_name", "brand_name", "mechanism_of_action", "indication", 
                "side_effects", "dosage"],
        "institutes": ["institution_name", "research_fields", "key_technologies"],
    },
    "Player": {
        "nba": ["name", "nationality", "position", "college"],
        "team": ["team_name", "championships", "founded_year"],
        "manager": ["name", "nationality"],
        "city": ["city_name", "state_name"],
    },
    "Art": {
        "Wikiart": ["Name", "Style", "Theme", "Object", "Color", "Tone", "Composition", "Image_Genre"],
    },
    "Legal": {
        "LCR": ["judge_name", "plaintiff", "defendant", "charges", "verdict"],
    },
    "Finan": {
        "Finance": ["company_name", "principal_activities", "business_risks"],
    },
}


def convert_csv_to_json(dataset: str, entity: str, csv_file: Path) -> list:
    """Convert CSV file to JSON array format for UQE."""
    print(f"  Converting {dataset}/{entity} from CSV to JSON...")
    
    df = pd.read_csv(csv_file)
    
    # Drop ID column if it exists
    if "ID" in df.columns:
        df = df.drop("ID", axis=1)
    
    # Convert each row to a dictionary with all columns plus text description
    data = []
    for idx, row in df.iterrows():
        # Create ID from index
        item_id = f"{entity}_{idx}"
        
        # Create description by concatenating text columns
        text_parts = []
        for col in TEXT_COLUMNS.get(dataset, {}).get(entity, df.columns):
            if col in df.columns:
                val = row[col]
                if pd.notna(val):
                    text_parts.append(f"{col}: {val}")
        
        description = " || ".join(text_parts)
        
        # Start with id and description
        item_data = {
            "id": item_id,
            "description": description
        }
        
        # Add all CSV columns to the item
        for col in df.columns:
            val = row[col]
            # Convert to native Python types for JSON serialization
            if pd.isna(val):
                item_data[col] = None
            elif isinstance(val, (int, float)):
                item_data[col] = val if not pd.isna(val) else None
            else:
                item_data[col] = str(val)
        
        data.append(item_data)
    
    return data


def generate_embeddings(data: list, entity: str, repository: ModelRepository) -> np.ndarray:
    """Generate embeddings for all items."""
    print(f"  Generating embeddings for {len(data)} items...")
    
    # Extract descriptions
    descriptions = [item["description"] for item in data]
    
    # Generate text embeddings
    text_model = repository.get_text_model()
    embeddings = get_text_embeds(descriptions, text_model)
    
    return embeddings


def preprocess_dataset(dataset_name: str, entity_name: str, csv_file: Path) -> dict:
    """Preprocess a single dataset entity."""
    
    # Create output directory
    entity_dir = UQE_DATA_DIR / entity_name
    entity_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nProcessing {dataset_name}/{entity_name}...")
    
    # 1. Convert CSV to JSON
    data = convert_csv_to_json(dataset_name, entity_name, csv_file)
    
    # 2. Save JSON
    json_path = entity_dir / "dataset.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  ✓ Saved {len(data)} items to {json_path}")
    
    # 3. Generate embeddings
    repository = ModelRepository()
    embeddings = generate_embeddings(data, entity_name, repository)
    
    # 4. Save embeddings
    embeddings_path = entity_dir / "embeddings.npy"
    np.save(embeddings_path, embeddings)
    print(f"  ✓ Saved embeddings shape {embeddings.shape} to {embeddings_path}")
    
    return {
        "entity": entity_name,
        "dataset": dataset_name,
        "items": len(data),
        "embedding_shape": embeddings.shape,
        "json_path": str(json_path),
        "embeddings_path": str(embeddings_path)
    }


def main():
    """Main preprocessing pipeline."""
    
    print("=" * 80)
    print("UQE Preprocessing for UDA Benchmark Datasets")
    print("=" * 80)
    
    # Create data directory
    UQE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {UQE_DATA_DIR}\n")
    
    results = []
    
    # Process each dataset
    for dataset_name, entities in DATASETS.items():
        dataset_dir = DATA_DIR / dataset_name
        
        if not dataset_dir.exists():
            print(f"⚠ Warning: Dataset directory not found: {dataset_dir}")
            continue
        
        print(f"\n{'=' * 60}")
        print(f"Dataset: {dataset_name}")
        print(f"{'=' * 60}")
        
        for entity_name, csv_file_name in entities:
            csv_path = dataset_dir / csv_file_name
            
            if not csv_path.exists():
                print(f"⚠ Warning: CSV file not found: {csv_path}")
                continue
            
            try:
                result = preprocess_dataset(dataset_name, entity_name, csv_path)
                results.append(result)
            except Exception as e:
                print(f"  ✗ Error processing {dataset_name}/{entity_name}: {e}")
                import traceback
                traceback.print_exc()
    
    # Summary
    print(f"\n{'=' * 80}")
    print("Preprocessing Complete!")
    print(f"{'=' * 80}")
    print(f"\nProcessed {len(results)} entities:")
    
    for result in results:
        print(f"  ✓ {result['dataset']}/{result['entity']}: "
              f"{result['items']} items, embeddings {result['embedding_shape']}")
    
    # Save summary
    summary_path = UQE_DATA_DIR / "preprocessing_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSummary saved to: {summary_path}")


if __name__ == "__main__":
    main()


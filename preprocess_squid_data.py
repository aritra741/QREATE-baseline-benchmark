"""
Preprocessing script for SQUiD system.

SQUiD takes unstructured text as input and generates relational databases.
This script converts CSV ground truth data into natural language text documents
that can be used to test SQUiD.

Usage:
    python preprocess_squid_data.py --dataset Med --entities disease drug institution
    python preprocess_squid_data.py --dataset all  # Process all datasets
"""

import argparse
import json
import os
import sys
import pandas as pd
import pickle
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import hashlib

# Add project paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.logging_utils import setup_logger
from evaluation.config import dump_json, load_json


# ==============================================================================
# DATA PATHS & CONFIGURATION
# ==============================================================================

DATA_PATHS = {
    "Med": {
        "disease": PROJECT_ROOT / "Data" / "Med" / "disease.csv",
        "drug": PROJECT_ROOT / "Data" / "Med" / "drug.csv",
        "institution": PROJECT_ROOT / "Data" / "Med" / "institution.csv",
    },
    "Player": {
        "player": PROJECT_ROOT / "Data" / "Player" / "player.csv",
        "team": PROJECT_ROOT / "Data" / "Player" / "team.csv",
        "manager": PROJECT_ROOT / "Data" / "Player" / "manager.csv",
        "city": PROJECT_ROOT / "Data" / "Player" / "city.csv",
    },
    "Art": {
        "art": PROJECT_ROOT / "Data" / "Art" / "Art.csv",
    },
    "Legal": {
        "legal_case": PROJECT_ROOT / "Data" / "Legal" / "Legal.csv",
    },
    "Finan": {
        "finance": PROJECT_ROOT / "Data" / "Finan" / "Finan.csv",
    }
}

# Schema definitions for each dataset - used to generate structured documents
SCHEMAS = {
    "Med": {
        "disease": [
            {"table_name": "disease", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "disease_name", "type": "TEXT"},
                {"name": "disease_type", "type": "TEXT"},
                {"name": "etiology", "type": "TEXT"},
                {"name": "diagnostic_methods", "type": "TEXT"},
                {"name": "common_symptoms", "type": "TEXT"},
                {"name": "treatments", "type": "TEXT"},
                {"name": "prognosis", "type": "TEXT"},
                {"name": "pathogenesis", "type": "TEXT"},
                {"name": "treatment_challenges", "type": "TEXT"},
            ]}
        ]
    },
    "Player": {
        "player": [
            {"table_name": "player", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "name", "type": "TEXT"},
                {"name": "position", "type": "TEXT"},
                {"name": "nationality", "type": "TEXT"},
                {"name": "draft_year", "type": "INTEGER"},
                {"name": "team", "type": "TEXT"},
                {"name": "college", "type": "TEXT"},
                {"name": "nba_championships", "type": "INTEGER"},
                {"name": "mvp_awards", "type": "INTEGER"},
                {"name": "olympic_gold_medals", "type": "INTEGER"},
            ]}
        ]
    },
    "Art": {
        "art": [
            {"table_name": "art", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "artist", "type": "TEXT"},
                {"name": "title", "type": "TEXT"},
                {"name": "year", "type": "INTEGER"},
                {"name": "style", "type": "TEXT"},
            ]}
        ]
    },
    "Legal": {
        "legal_case": [
            {"table_name": "legal_case", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "case_name", "type": "TEXT"},
                {"name": "year", "type": "INTEGER"},
                {"name": "court", "type": "TEXT"},
                {"name": "judge", "type": "TEXT"},
                {"name": "ruling", "type": "TEXT"},
            ]}
        ]
    },
    "Finan": {
        "finance": [
            {"table_name": "finance", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "company_name", "type": "TEXT"},
                {"name": "principal_activities", "type": "TEXT"},
                {"name": "revenue", "type": "REAL"},
                {"name": "net_profit_or_loss", "type": "REAL"},
                {"name": "total_assets", "type": "REAL"},
                {"name": "business_risks", "type": "TEXT"},
            ]}
        ]
    }
}


# ==============================================================================
# PREPROCESSING UTILITIES
# ==============================================================================

def csv_row_to_document(row: pd.Series, schema_cols: List[Dict]) -> str:
    """
    Convert a CSV row to a natural language document.
    
    Args:
        row: A pandas Series representing one row
        schema_cols: List of column definitions from schema
    
    Returns:
        A natural language description of the row
    """
    sentences = []
    
    for col_def in schema_cols:
        col_name = col_def["name"]
        if col_name not in row.index:
            continue
            
        value = row[col_name]
        
        # Skip null/empty values
        if pd.isna(value) or value == "" or value == "#":
            continue
        
        # Convert value to string
        value_str = str(value).strip()
        
        # Skip numeric columns with 0 or placeholder values
        if col_def["type"] in ["INTEGER", "REAL"]:
            try:
                num_val = float(value_str)
                if num_val == 0 or num_val == -1:
                    continue
            except (ValueError, TypeError):
                pass
        
        # Create natural language sentence
        # Remove underscores and make more readable
        readable_name = col_name.replace("_", " ")
        sentences.append(f"{readable_name}: {value_str}")
    
    # Join sentences with periods
    if not sentences:
        return "No information available."
    
    doc = ". ".join(sentences) + "."
    return doc


def preprocess_dataset(dataset: str, entity: str, output_dir: Path, logger) -> Dict[str, Any]:
    """
    Preprocess a single dataset/entity combination for SQUiD.
    
    Args:
        dataset: Dataset name (e.g., "Med")
        entity: Entity name (e.g., "disease")
        output_dir: Output directory for preprocessed data
        logger: Logger instance
    
    Returns:
        Metadata dictionary with preprocessing info
    """
    logger.info(f"Preprocessing {dataset}/{entity}...")
    
    # Check if CSV exists
    if dataset not in DATA_PATHS or entity not in DATA_PATHS[dataset]:
        logger.error(f"No data path found for {dataset}/{entity}")
        return {"status": "failed", "error": f"No data path for {dataset}/{entity}"}
    
    csv_path = DATA_PATHS[dataset][entity]
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return {"status": "failed", "error": f"File not found: {csv_path}"}
    
    # Load CSV
    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} rows from {csv_path.name}")
    except Exception as e:
        logger.error(f"Failed to load CSV: {e}")
        return {"status": "failed", "error": str(e)}
    
    # Get schema
    if dataset not in SCHEMAS or entity not in SCHEMAS[dataset]:
        logger.error(f"No schema found for {dataset}/{entity}")
        return {"status": "failed", "error": f"No schema for {dataset}/{entity}"}
    
    schema = SCHEMAS[dataset][entity]
    schema_cols = schema[0]["columns"]
    
    # Create output directories
    output_entity_dir = output_dir / dataset / entity
    output_entity_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate documents and metadata
    documents = []
    ground_truth = []
    metadata_list = []
    
    for idx, row in df.iterrows():
        # Generate natural language document
        doc = csv_row_to_document(row, schema_cols)
        
        # Store document with metadata
        documents.append(doc)
        
        # Store ground truth row data as dict
        gt_row = row.to_dict()
        ground_truth.append(gt_row)
        
        # Create metadata for this row
        doc_metadata = {
            "idx": idx,
            "dataset": dataset,
            "entity": entity,
            "hash": hashlib.md5(doc.encode()).hexdigest()[:8]
        }
        metadata_list.append(doc_metadata)
    
    # Save documents as individual text files (SQUiD expects separate files)
    docs_dir = output_entity_dir / "documents"
    docs_dir.mkdir(exist_ok=True)
    
    for idx, doc in enumerate(documents):
        doc_path = docs_dir / f"doc_{idx:04d}.txt"
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(doc)
    
    logger.info(f"Saved {len(documents)} documents to {docs_dir}")
    
    # Save consolidated data for easier processing
    consolidated_data = {
        "dataset": dataset,
        "entity": entity,
        "documents": documents,
        "ground_truth": ground_truth,
        "schema": schema,
        "metadata": metadata_list,
        "count": len(documents)
    }
    
    # Save as JSON
    json_path = output_entity_dir / "preprocessed_data.json"
    dump_json(consolidated_data, json_path)
    logger.info(f"Saved consolidated data to {json_path}")
    
    # Save as pickle for efficiency
    pkl_path = output_entity_dir / "preprocessed_data.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(consolidated_data, f)
    logger.info(f"Saved pickled data to {pkl_path}")
    
    # Create summary
    summary = {
        "status": "completed",
        "dataset": dataset,
        "entity": entity,
        "count": len(documents),
        "csv_path": str(csv_path),
        "output_dir": str(output_entity_dir),
        "documents_dir": str(docs_dir),
        "timestamp": datetime.now().isoformat()
    }
    
    # Save summary
    dump_json(summary, output_entity_dir / "summary.json")
    
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Preprocess data for SQUiD system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preprocess a specific dataset/entity
  python preprocess_squid_data.py --dataset Med --entities disease drug
  
  # Preprocess all datasets
  python preprocess_squid_data.py --dataset all
  
  # Preprocess all entities in a dataset
  python preprocess_squid_data.py --dataset Med
        """
    )
    
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        choices=list(DATA_PATHS.keys()) + ["all"],
        help="Dataset to preprocess (or 'all')"
    )
    
    parser.add_argument(
        "--entities",
        nargs="+",
        default=None,
        help="Specific entities to preprocess (if not specified, preprocess all)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "preprocess_squid",
        help="Output directory for preprocessed data"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_file = args.output_dir / "preprocessing.log"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger("preprocess_squid", level=args.log_level, log_file=log_file)
    
    logger.info("=" * 80)
    logger.info("SQUiD Data Preprocessing")
    logger.info("=" * 80)
    
    # Determine which datasets to process
    datasets_to_process = []
    if args.dataset == "all":
        datasets_to_process = list(DATA_PATHS.keys())
    else:
        datasets_to_process = [args.dataset]
    
    # Process each dataset
    all_results = []
    for dataset in datasets_to_process:
        logger.info(f"\nProcessing dataset: {dataset}")
        
        # Determine which entities to process
        if args.entities:
            entities_to_process = args.entities
        else:
            entities_to_process = list(DATA_PATHS[dataset].keys())
        
        for entity in entities_to_process:
            try:
                result = preprocess_dataset(dataset, entity, args.output_dir, logger)
                all_results.append(result)
                logger.info(f"✓ {dataset}/{entity}: {result.get('count', 0)} documents")
            except Exception as e:
                logger.error(f"✗ {dataset}/{entity}: {e}")
                all_results.append({
                    "status": "failed",
                    "dataset": dataset,
                    "entity": entity,
                    "error": str(e)
                })
    
    # Save summary
    summary = {
        "total_results": len(all_results),
        "successful": len([r for r in all_results if r.get("status") == "completed"]),
        "failed": len([r for r in all_results if r.get("status") == "failed"]),
        "results": all_results,
        "timestamp": datetime.now().isoformat()
    }
    
    dump_json(summary, args.output_dir / "summary.json")
    
    logger.info("\n" + "=" * 80)
    logger.info("Preprocessing Summary")
    logger.info("=" * 80)
    logger.info(f"Total: {summary['total_results']}")
    logger.info(f"Successful: {summary['successful']}")
    logger.info(f"Failed: {summary['failed']}")
    logger.info(f"Output: {args.output_dir}")
    logger.info("=" * 80)
    
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


"""
Preprocessing script for SQUiD system with LLM-based document generation.

SQUiD takes unstructured text as input and generates relational databases.
This script converts CSV ground truth data into natural language text documents
by using an LLM to generate creative, conversational stories while preserving
all data points (as per SQUiD paper methodology).

The documents are generated using system/user prompts from the SQUiD paper
which instruct the LLM to rephrase structured data into engaging narratives.

Usage:
    python preprocess_squid_data.py --dataset Med --entities disease drug
    python preprocess_squid_data.py --dataset all
    python preprocess_squid_data.py --dataset Med --no-llm  # Use structured sentences only
"""

import argparse
import json
import os
import sys
import pandas as pd
import pickle
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import hashlib

# Add project paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.logging_utils import setup_logger
from evaluation.config import dump_json, load_json

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


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
        ],
        "drug": [
            {"table_name": "drug", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "drug_name", "type": "TEXT"},
                {"name": "generic_name", "type": "TEXT"},
                {"name": "drug_type", "type": "TEXT"},
                {"name": "indication", "type": "TEXT"},
                {"name": "mechanism_of_action", "type": "TEXT"},
                {"name": "side_effects", "type": "TEXT"},
                {"name": "dosage", "type": "TEXT"},
                {"name": "manufacturer", "type": "TEXT"},
                {"name": "approval_status", "type": "TEXT"},
            ]}
        ],
        "institution": [
            {"table_name": "institution", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "institution_name", "type": "TEXT"},
                {"name": "institution_type", "type": "TEXT"},
                {"name": "location", "type": "TEXT"},
                {"name": "specialties", "type": "TEXT"},
                {"name": "bed_count", "type": "INTEGER"},
                {"name": "accreditation", "type": "TEXT"},
                {"name": "founding_year", "type": "INTEGER"},
                {"name": "director", "type": "TEXT"},
                {"name": "contact_info", "type": "TEXT"},
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
        ],
        "team": [
            {"table_name": "team", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "team_name", "type": "TEXT"},
                {"name": "city", "type": "TEXT"},
                {"name": "founded_year", "type": "INTEGER"},
                {"name": "coach", "type": "TEXT"},
                {"name": "championships", "type": "INTEGER"},
                {"name": "conference", "type": "TEXT"},
                {"name": "arena", "type": "TEXT"},
                {"name": "owner", "type": "TEXT"},
                {"name": "player_count", "type": "INTEGER"},
            ]}
        ],
        "manager": [
            {"table_name": "manager", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "manager_name", "type": "TEXT"},
                {"name": "team", "type": "TEXT"},
                {"name": "years_coaching", "type": "INTEGER"},
                {"name": "championships_won", "type": "INTEGER"},
                {"name": "total_wins", "type": "INTEGER"},
                {"name": "total_losses", "type": "INTEGER"},
                {"name": "coaching_style", "type": "TEXT"},
                {"name": "nationality", "type": "TEXT"},
                {"name": "notable_achievements", "type": "TEXT"},
            ]}
        ],
        "city": [
            {"table_name": "city", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "city_name", "type": "TEXT"},
                {"name": "state", "type": "TEXT"},
                {"name": "population", "type": "INTEGER"},
                {"name": "region", "type": "TEXT"},
                {"name": "nba_teams", "type": "INTEGER"},
                {"name": "founding_year", "type": "INTEGER"},
                {"name": "major_attractions", "type": "TEXT"},
                {"name": "climate", "type": "TEXT"},
                {"name": "economy_type", "type": "TEXT"},
            ]}
        ]
    },
    "Art": {
        "art": [
            {"table_name": "art", "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "title", "type": "TEXT"},
                {"name": "artist", "type": "TEXT"},
                {"name": "year", "type": "INTEGER"},
                {"name": "style", "type": "TEXT"},
                {"name": "medium", "type": "TEXT"},
                {"name": "period", "type": "TEXT"},
                {"name": "technique", "type": "TEXT"},
                {"name": "subject", "type": "TEXT"},
                {"name": "cultural_significance", "type": "TEXT"},
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
                {"name": "parties_involved", "type": "TEXT"},
                {"name": "jurisdiction", "type": "TEXT"},
                {"name": "case_type", "type": "TEXT"},
                {"name": "significance", "type": "TEXT"},
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
                {"name": "sector", "type": "TEXT"},
                {"name": "employees", "type": "INTEGER"},
                {"name": "founded_year", "type": "INTEGER"},
            ]}
        ]
    }
}


# ==============================================================================
# LLM UTILITIES
# ==============================================================================

def get_llm_client(llm_model: str, logger) -> Optional[Tuple]:
    """Get or create LLM client based on model specification.
    
    Args:
        llm_model: Model name (e.g., 'gpt-4', 'ollama/qwen2.5', 'ollama/llama2')
        logger: Logger instance
    
    Returns:
        Tuple of (client, model_name) or None if failed
    """
    if not HAS_OPENAI:
        logger.error("OpenAI client not available. Install with: pip install openai")
        return None
    
    try:
        if llm_model.startswith("ollama/"):
            # Local Ollama model
            model_name = llm_model.replace("ollama/", "")
            logger.info(f"Using local Ollama model: {model_name}")
            return OpenAI(
                api_key="ollama",
                base_url="http://localhost:11434/v1"
            ), model_name
        else:
            # OpenAI model
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY environment variable not set")
                return None
            logger.info(f"Using OpenAI model: {llm_model}")
            return OpenAI(api_key=api_key), llm_model
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}")
        return None


# ==============================================================================
# DOCUMENT GENERATION
# ==============================================================================

def csv_row_to_sentence(row: pd.Series, schema_cols: List[Dict]) -> str:
    """Convert a CSV row to a structured sentence for LLM rephrasing.
    
    This creates a sentence in the format: "attr1 is $value1$, attr2 is $value2$, ..."
    The special markers ($...$) help the LLM preserve exact values.
    
    Args:
        row: A pandas Series representing one row
        schema_cols: List of column definitions from schema
    
    Returns:
        A structured sentence describing the row (before LLM rephrasing)
    """
    parts = []
    
    for col_def in schema_cols:
        col_name = col_def["name"]
        if col_name not in row.index:
            continue
            
        value = row[col_name]
        
        # Skip null/empty values and mark as 'nan' for LLM to skip
        if pd.isna(value) or value == "" or value == "#":
            value = "nan"
        else:
            value = str(value).strip()
        
        # Create readable sentence part with value markers
        readable_name = col_name.replace("_", " ")
        parts.append(f"{readable_name} is ${value}$")
    
    # Join parts with commas
    if not parts:
        return ""
    
    sentence = ", ".join(parts)
    return sentence


def generate_llm_document(sentence: str, llm_client, model_name: str, logger) -> Optional[str]:
    """Generate a creative document from a structured sentence using LLM.
    
    Uses the prompt format from SQUiD paper (Figures 6-7) to rephrase
    structured data into engaging, conversational stories while preserving
    all datapoints.
    
    Args:
        sentence: Structured sentence with markers (e.g., "name is $John$, age is $30$")
        llm_client: OpenAI client instance
        model_name: Name of the model to use
        logger: Logger instance
    
    Returns:
        Generated natural language document or None if generation failed
    """
    if not llm_client or not sentence:
        return None
    
    # System prompt from SQUiD paper (Figure 6)
    system_prompt = """You are a creative AI that rephrases given sentences into engaging, conversational stories while incorporating all provided datapoints.
- Ensure that no information is omitted or added, and skip any datapoints labeled as 'nan'.
- Do not rephrase the object of a sentence. For example, if the sentence is 'start date is $9/22/2023$', do not change the date to a different format.
- Respond only with the rephrased sentence without any additional commentary."""
    
    # User prompt from SQUiD paper (Figure 7)
    user_prompt = f"""Rephrase the following sentence into a conversational story, ensuring all data points are included while skipping 'nan' values.
Do not introduce any extra or false details.
Original sentence: {sentence}
Creative sentence:"""
    
    try:
        response = llm_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=256,
            timeout=30
        )
        
        generated_text = response.choices[0].message.content.strip()
        return generated_text
    
    except Exception as e:
        logger.debug(f"LLM generation failed: {e}")
        return None


def csv_row_to_document(row: pd.Series, schema_cols: List[Dict], llm_client=None, 
                       model_name: str = "", logger=None) -> str:
    """Convert a CSV row to a natural language document.
    
    First converts row to structured sentence, then uses LLM to generate
    a creative, conversational document if LLM is available.
    
    Args:
        row: A pandas Series representing one row
        schema_cols: List of column definitions from schema
        llm_client: Optional LLM client for document generation
        model_name: Name of the model to use
        logger: Logger instance
    
    Returns:
        A natural language description of the row
    """
    sentence = csv_row_to_sentence(row, schema_cols)
    
    if not sentence:
        return "No information available."
    
    # Try LLM generation if available
    if llm_client and model_name:
        generated = generate_llm_document(sentence, llm_client, model_name, logger)
        if generated:
            return generated
    
    # Fallback: return structured sentence if LLM fails
    return sentence


def preprocess_dataset(dataset: str, entity: str, output_dir: Path, logger, 
                      llm_client=None, model_name: str = "") -> Dict[str, Any]:
    """
    Preprocess a single dataset/entity combination for SQUiD.
    
    Args:
        dataset: Dataset name (e.g., "Med")
        entity: Entity name (e.g., "disease")
        output_dir: Output directory for preprocessed data
        logger: Logger instance
        llm_client: Optional LLM client for document generation
        model_name: Name of the model to use
    
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
    generation_errors = 0
    
    for idx, row in df.iterrows():
        try:
            # Generate natural language document
            doc = csv_row_to_document(row, schema_cols, llm_client, model_name, logger)
            
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
            
            if idx % max(1, len(df) // 10) == 0:
                logger.debug(f"Processed {idx}/{len(df)} documents")
        
        except Exception as e:
            logger.warning(f"Error processing row {idx}: {e}")
            generation_errors += 1
            # Still add a placeholder
            documents.append(f"Error generating document for row {idx}")
            gt_row = row.to_dict()
            ground_truth.append(gt_row)
            metadata_list.append({
                "idx": idx,
                "dataset": dataset,
                "entity": entity,
                "error": str(e)
            })
    
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
        "count": len(documents),
        "generation_errors": generation_errors
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
        "generation_errors": generation_errors,
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
        description="Preprocess data for SQUiD system using LLM document generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preprocess with default LLM (qwen2.5-7b-instruct via Ollama)
  python preprocess_squid_data.py --dataset all
  
  # Preprocess specific dataset with LLM
  python preprocess_squid_data.py --dataset Med
  
  # Preprocess without LLM (fallback to structured sentences)
  python preprocess_squid_data.py --dataset Med --no-llm
  
  # Specific entities with LLM
  python preprocess_squid_data.py --dataset Med --entities disease drug
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
        "--llm-model",
        type=str,
        default="ollama/qwen2.5-7b-instruct",
        help="LLM model to use for document generation (default: ollama/qwen2.5-7b-instruct)"
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
    logger.info("SQUiD Data Preprocessing (LLM-based Document Generation)")
    logger.info("=" * 80)
    
    # Initialize LLM client (always required)
    logger.info(f"Initializing LLM client with model: {args.llm_model}")
    result = get_llm_client(args.llm_model, logger)
    if not result:
        logger.error("Failed to initialize LLM client")
        return 1
    
    llm_client, model_name = result
    logger.info("✓ LLM client initialized successfully")
    
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
                result = preprocess_dataset(dataset, entity, args.output_dir, logger, 
                                          llm_client, model_name)
                all_results.append(result)
                
                doc_count = result.get('count', 0)
                gen_errors = result.get('generation_errors', 0)
                
                if gen_errors > 0:
                    logger.info(f"✓ {dataset}/{entity}: {doc_count} documents ({gen_errors} generation errors)")
                else:
                    logger.info(f"✓ {dataset}/{entity}: {doc_count} documents")
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


#!/usr/bin/env python3
"""
Complete SQUiD preprocessing pipeline.

Converts CSV ground truth data into a fully processed relational database through
the SQUiD pipeline:
1. LLM-based document generation (CSV → natural language)
2. Schema generation (text → database schema)
3. Value identification (symbolic + LLM methods)
4. Value population (TS, TST, TST-L ensemble methods)
5. Database generation (SQL creation)
6. Ensemble (combine results)

Usage:
    # Full preprocessing pipeline
    python preprocess_squid_data.py --dataset all
    
    # Specific dataset with LLM documents only (skip SQUiD pipeline)
    python preprocess_squid_data.py --dataset Med --skip-pipeline
    
    # Specific entities
    python preprocess_squid_data.py --dataset Med --entities disease drug
"""

import argparse
import json
import os
import sys
import pandas as pd
import pickle
import subprocess
import traceback
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

# Schema definitions for each dataset
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
    """Get or create LLM client based on model specification."""
    if not HAS_OPENAI:
        logger.error("OpenAI client not available. Install with: pip install openai")
        return None
    
    try:
        if llm_model.startswith("ollama/"):
            model_name = llm_model.replace("ollama/", "")
            logger.info(f"Using local Ollama model: {model_name}")
            return OpenAI(
                api_key="ollama",
                base_url="http://localhost:11434/v1"
            ), model_name
        else:
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
    """Convert a CSV row to a structured sentence for LLM rephrasing."""
    parts = []
    
    for col_def in schema_cols:
        col_name = col_def["name"]
        if col_name not in row.index:
            continue
            
        value = row[col_name]
        
        if pd.isna(value) or value == "" or value == "#":
            value = "nan"
        else:
            value = str(value).strip()
        
        readable_name = col_name.replace("_", " ")
        parts.append(f"{readable_name} is ${value}$")
    
    if not parts:
        return ""
    
    sentence = ", ".join(parts)
    return sentence


def generate_llm_document(sentence: str, llm_client, model_name: str, logger) -> Optional[str]:
    """Generate a creative document from a structured sentence using LLM."""
    if not llm_client or not sentence:
        return None
    
    system_prompt = """You are a creative AI that rephrases given sentences into engaging, conversational stories while incorporating all provided datapoints.
- Ensure that no information is omitted or added, and skip any datapoints labeled as 'nan'.
- Do not rephrase the object of a sentence. For example, if the sentence is 'start date is $9/22/2023$', do not change the date to a different format.
- Respond only with the rephrased sentence without any additional commentary."""
    
    user_prompt = f"""Rephrase the following sentence into a conversational story, ensuring all data points are included while skipping 'nan' values.
Do not introduce any extra or false details.
Original sentence: {sentence}
Creative sentence:"""
    
    try:
        stream = llm_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=512,
            stream=True
        )
        
        generated_text = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                generated_text += chunk.choices[0].delta.content
        
        return generated_text.strip()
    
    except Exception as e:
        logger.error(f"LLM generation failed for sentence: {sentence[:100]}... | Error: {e}")
        return None


def csv_row_to_document(row: pd.Series, schema_cols: List[Dict], llm_client=None, 
                       model_name: str = "", logger=None) -> str:
    """Convert a CSV row to a natural language document."""
    if not llm_client or not model_name:
        raise RuntimeError("LLM client and model_name are required for document generation")
    
    sentence = csv_row_to_sentence(row, schema_cols)
    
    if not sentence:
        return "No information available."
    
    generated = generate_llm_document(sentence, llm_client, model_name, logger)
    if not generated:
        raise RuntimeError(f"Failed to generate document for: {sentence[:100]}")
    
    return generated


def preprocess_llm_documents(dataset: str, entity: str, output_dir: Path, logger, 
                            llm_client=None, model_name: str = "") -> Dict[str, Any]:
    """Preprocess a single dataset/entity to generate LLM documents."""
    logger.info(f"Generating LLM documents for {dataset}/{entity}...")
    
    if dataset not in DATA_PATHS or entity not in DATA_PATHS[dataset]:
        logger.error(f"No data path found for {dataset}/{entity}")
        return {"status": "failed", "error": f"No data path for {dataset}/{entity}"}
    
    csv_path = DATA_PATHS[dataset][entity]
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return {"status": "failed", "error": f"File not found: {csv_path}"}
    
    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} rows from {csv_path.name}")
    except Exception as e:
        logger.error(f"Failed to load CSV: {e}")
        return {"status": "failed", "error": str(e)}
    
    if dataset not in SCHEMAS or entity not in SCHEMAS[dataset]:
        logger.error(f"No schema found for {dataset}/{entity}")
        return {"status": "failed", "error": f"No schema for {dataset}/{entity}"}
    
    schema = SCHEMAS[dataset][entity]
    schema_cols = schema[0]["columns"]
    
    output_entity_dir = output_dir / dataset / entity
    output_entity_dir.mkdir(parents=True, exist_ok=True)
    
    documents = []
    ground_truth = []
    metadata_list = []
    generation_errors = 0
    
    for idx, row in df.iterrows():
        try:
            doc = csv_row_to_document(row, schema_cols, llm_client, model_name, logger)
            documents.append(doc)
            ground_truth.append(row.to_dict())
            metadata_list.append({
                "idx": idx,
                "dataset": dataset,
                "entity": entity,
                "hash": hashlib.md5(doc.encode()).hexdigest()[:8]
            })
            
            if idx % max(1, len(df) // 10) == 0:
                logger.debug(f"Processed {idx}/{len(df)} documents")
        
        except Exception as e:
            logger.warning(f"Error processing row {idx}: {e}")
            generation_errors += 1
            documents.append(f"Error generating document for row {idx}")
            ground_truth.append(row.to_dict())
            metadata_list.append({
                "idx": idx,
                "dataset": dataset,
                "entity": entity,
                "error": str(e)
            })
    
    docs_dir = output_entity_dir / "documents"
    docs_dir.mkdir(exist_ok=True)
    
    for idx, doc in enumerate(documents):
        doc_path = docs_dir / f"doc_{idx:04d}.txt"
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(doc)
    
    logger.info(f"Saved {len(documents)} documents to {docs_dir}")
    
    # Create SQUiD-compatible JSON format
    squid_format_data = []
    for idx, (doc, gt) in enumerate(zip(documents, ground_truth)):
        squid_entry = {
            "text": doc,
            "ground_truth_entities": [entity],  # Entity this document belongs to
            "ground_truth_key_value": gt,  # The CSV row as key-value pairs
            "domain": dataset,
            "difficulty": "medium"  # Default difficulty
        }
        squid_format_data.append(squid_entry)
    
    # Save in SQUiD-compatible format at the location SQUiD expects
    # SQUiD looks for: ../../preprocess_squid/{dataset}/{entity}.json
    squid_json_path = output_dir / dataset / f"{entity}.json"
    dump_json(squid_format_data, squid_json_path)
    logger.info(f"Saved SQUiD-compatible JSON to {squid_json_path}")
    
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
    
    json_path = output_entity_dir / "preprocessed_data.json"
    dump_json(consolidated_data, json_path)
    logger.info(f"Saved consolidated data to {json_path}")
    
    pkl_path = output_entity_dir / "preprocessed_data.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(consolidated_data, f)
    logger.info(f"Saved pickled data to {pkl_path}")
    
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
    
    dump_json(summary, output_entity_dir / "summary.json")
    
    return summary


# ==============================================================================
# SQUiD PIPELINE
# ==============================================================================

def run_squid_pipeline_step(step_name: str, args: list, squid_path: Path, logger, is_helper: bool = False) -> bool:
    """Run a single step of the SQUiD pipeline.
    
    Args:
        step_name: Name of the step/script
        args: Arguments to pass to the script
        squid_path: Path to SQUiD directory
        logger: Logger instance
        is_helper: If True, script is in helpers/ directory, not src/
    """
    if is_helper:
        cmd = ["python", f"helpers/{step_name}.py"] + args
    else:
        cmd = ["python", f"src/{step_name}.py"] + args
    
    logger.info(f"[PIPELINE] Running: {' '.join(cmd)}")
    logger.debug(f"[PIPELINE] Working directory: {squid_path}")
    
    try:
        # Create environment with PYTHONPATH set to squid_path/src
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{squid_path}/src:{env.get('PYTHONPATH', '')}"
        
        result = subprocess.run(
            cmd, 
            cwd=str(squid_path),  # Convert to string to ensure path is correct
            capture_output=True, 
            text=True, 
            timeout=600,
            env=env
        )
        
        if result.returncode == 0:
            logger.info(f"[PIPELINE] ✓ {step_name} completed successfully")
            return True
        else:
            logger.error(f"[PIPELINE] ✗ {step_name} failed with return code {result.returncode}")
            if result.stderr:
                logger.error(f"[PIPELINE] stderr: {result.stderr[-1000:]}")  # Increased to 1000 chars
            if result.stdout:
                logger.debug(f"[PIPELINE] stdout: {result.stdout[-500:]}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"[PIPELINE] ✗ {step_name} timed out (>600s)")
        return False
    except Exception as e:
        logger.error(f"[PIPELINE] ✗ {step_name} error: {e}")
        logger.error(f"[PIPELINE] Traceback:\n{traceback.format_exc()}")
        return False


def update_config_for_dataset(dataset: str, entity: str, squid_path: Path, logger) -> bool:
    """Update config.yaml for processing a specific dataset/entity with deterministic paths."""
    try:
        import yaml
        
        config_path = squid_path / "configs" / "config.yaml"
        datapath = f"{dataset}/{entity}"
        num_entries = 100
        
        # Deterministic file naming based on pipeline parameters
        # schema_generation with --method text --prompt_type direct --model_name qwen creates:
        METHOD = "text"
        PROMPT_TYPE = "direct"
        MODEL_NAME = "qwen"
        
        schema_file_base = f"{METHOD}_{PROMPT_TYPE}_{MODEL_NAME}"
        
        # Read current config
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        # Update all stages with deterministic paths
        if "schema_generation" in config:
            config["schema_generation"]["datapath"] = datapath
            config["schema_generation"]["num_of_entries"] = num_entries
            config["schema_generation"]["model_name"] = MODEL_NAME
            config["schema_generation"]["method"] = METHOD
            config["schema_generation"]["prompt_type"] = PROMPT_TYPE
        
        if "value_identification" in config:
            config["value_identification"]["datapath"] = f"{datapath}/text_cot_{MODEL_NAME}"
            config["value_identification"]["num_of_entries"] = num_entries
            config["value_identification"]["model_name"] = MODEL_NAME
            # Exact path to schema file created by schema_generation
            config["value_identification"]["schema_path"] = f"results/schema_generation/{datapath}/{schema_file_base}.json"
        
        if "value_population" in config:
            config["value_population"]["datapath"] = f"{datapath}/text_cot_{MODEL_NAME}"
            config["value_population"]["num_of_entries"] = num_entries
            config["value_population"]["model_name"] = MODEL_NAME
            # Symbolic results path
            config["value_population"]["symbolic_path"] = f"results/value_identification/symbolic/{datapath}/result.json"
        
        if "database_generation" in config:
            config["database_generation"]["datapath"] = f"{datapath}/text_cot_{MODEL_NAME}"
            config["database_generation"]["num_of_entries"] = num_entries
            config["database_generation"]["model_name"] = MODEL_NAME
            # Exact path to schema mapping file
            config["database_generation"]["schema_path"] = f"results/schema_generation/{datapath}/{schema_file_base}_schema.json"
        
        if "baseline" in config:
            config["baseline"]["datapath"] = datapath
            config["baseline"]["num_of_entries"] = num_entries
            config["baseline"]["model_name"] = MODEL_NAME
        
        # Write updated config
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"[PIPELINE] Updated config for {dataset}/{entity}")
        logger.debug(f"[PIPELINE] Schema file: results/schema_generation/{datapath}/{schema_file_base}.json")
        logger.debug(f"[PIPELINE] Schema mapping: results/schema_generation/{datapath}/{schema_file_base}_schema.json")
        return True
        
    except Exception as e:
        logger.error(f"[PIPELINE] Failed to update config: {e}")
        logger.error(f"[PIPELINE] Traceback:\n{traceback.format_exc()}")
        return False


def run_squid_pipeline(skip_pipeline: bool, datasets_to_process: List[str], logger) -> bool:
    """Run the complete SQUiD pipeline for all datasets/entities."""
    if skip_pipeline:
        logger.info("[PIPELINE] Skipping SQUiD pipeline (--skip-pipeline flag set)")
        return True
    
    squid_path = PROJECT_ROOT / "systems" / "SQUiD"
    
    logger.info("\n" + "="*80)
    logger.info("Running SQUiD Pipeline for all datasets")
    logger.info("="*80)
    
    # Map datasets to their entities
    dataset_entities = {
        "Med": ["disease", "drug", "institution"],
        "Player": ["player", "team", "manager", "city"],
        "Art": ["art"],
        "Legal": ["legal_case"],
        "Finan": ["finance"]
    }
    
    # Run pipeline for each dataset/entity combination
    for dataset in datasets_to_process:
        if dataset not in dataset_entities:
            logger.warning(f"[PIPELINE] Unknown dataset: {dataset}")
            continue
        
        for entity in dataset_entities[dataset]:
            logger.info(f"\n{'='*80}")
            logger.info(f"Processing {dataset}/{entity}")
            logger.info(f"{'='*80}")
            
            # Update config for this dataset/entity
            if not update_config_for_dataset(dataset, entity, squid_path, logger):
                logger.warning(f"[PIPELINE] Failed to update config for {dataset}/{entity}")
                continue
            
            # Step 1: Schema Generation
            logger.info(f"\n[PIPELINE] Step 1: Schema Generation ({dataset}/{entity})")
            if not run_squid_pipeline_step("schema_generation", [
                "--model_name", "qwen",
                "--method", "text",
                "--prompt_type", "direct"
            ], squid_path, logger):
                logger.warning(f"[PIPELINE] Schema generation failed for {dataset}/{entity}, continuing...")
            
            # Step 2a: Value Identification - Symbolic
            logger.info(f"\n[PIPELINE] Step 2a: Value Identification - Symbolic ({dataset}/{entity})")
            if not run_squid_pipeline_step("value_identification", [
                "--model_name", "qwen",
                "--method", "symbolic"
            ], squid_path, logger):
                logger.warning(f"[PIPELINE] Value identification (symbolic) failed for {dataset}/{entity}, continuing...")
            
            # Step 2b: Value Identification - LLM
            logger.info(f"\n[PIPELINE] Step 2b: Value Identification - LLM ({dataset}/{entity})")
            if not run_squid_pipeline_step("value_identification", [
                "--model_name", "qwen",
                "--method", "llm"
            ], squid_path, logger):
                logger.warning(f"[PIPELINE] Value identification (LLM) failed for {dataset}/{entity}, continuing...")
            
            # Step 3: Value Population (all three methods)
            methods = ["TS", "TST", "TST-L"]
            for method in methods:
                logger.info(f"\n[PIPELINE] Step 3: Value Population ({method}) ({dataset}/{entity})")
                if not run_squid_pipeline_step("value_population", [
                    "--model_name", "qwen",
                    "--method", method
                ], squid_path, logger):
                    logger.warning(f"[PIPELINE] Value population ({method}) failed for {dataset}/{entity}, continuing...")
            
            # Step 4: Database Generation (all three methods)
            for method in methods:
                logger.info(f"\n[PIPELINE] Step 4: Database Generation ({method}) ({dataset}/{entity})")
                if not run_squid_pipeline_step("database_generation", [
                    "--model_name", "qwen",
                    "--method", method
                ], squid_path, logger):
                    logger.warning(f"[PIPELINE] Database generation ({method}) failed for {dataset}/{entity}, continuing...")
    
    # Step 5: Ensemble (runs once for all datasets)
    logger.info(f"\n[PIPELINE] Step 5: Ensemble (all datasets)")
    if not run_squid_pipeline_step("ensemble", [], squid_path, logger, is_helper=True):
        logger.warning("[PIPELINE] Ensemble failed")
    
    logger.info("\n[PIPELINE] ✓ SQUiD Pipeline Complete")
    logger.info(f"[PIPELINE] Results saved to: {squid_path / 'results'}")
    
    return True


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Complete SQUiD preprocessing: LLM documents + full pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full preprocessing (LLM documents + SQUiD pipeline)
  python preprocess_squid_data.py --dataset all
  
  # LLM documents only (skip SQUiD pipeline)
  python preprocess_squid_data.py --dataset all --skip-pipeline
  
  # Specific dataset
  python preprocess_squid_data.py --dataset Med
  
  # Specific entities
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
        default="ollama/qwen2.5:7b-instruct",
        help="LLM model to use (default: ollama/qwen2.5:7b-instruct)"
    )
    
    parser.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="Generate LLM documents only, skip SQUiD pipeline"
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
    logger.info("SQUiD Complete Preprocessing Pipeline")
    logger.info("=" * 80)
    
    # Initialize LLM client
    logger.info(f"Initializing LLM client with model: {args.llm_model}")
    result = get_llm_client(args.llm_model, logger)
    if not result:
        logger.error("Failed to initialize LLM client")
        return 1
    
    llm_client, model_name = result
    logger.info("✓ LLM client initialized successfully")
    
    # Determine datasets and entities
    datasets_to_process = []
    if args.dataset == "all":
        datasets_to_process = list(DATA_PATHS.keys())
    else:
        datasets_to_process = [args.dataset]
    
    # Phase 1: Generate LLM documents
    logger.info("\n" + "="*80)
    logger.info("Phase 1: LLM Document Generation")
    logger.info("="*80)
    
    all_results = []
    for dataset in datasets_to_process:
        logger.info(f"\nProcessing dataset: {dataset}")
        
        entities_to_process = args.entities if args.entities else list(DATA_PATHS[dataset].keys())
        
        for entity in entities_to_process:
            try:
                result = preprocess_llm_documents(dataset, entity, args.output_dir, logger,
                                                 llm_client, model_name)
                all_results.append(result)
                
                doc_count = result.get('count', 0)
                gen_errors = result.get('generation_errors', 0)
                
                if gen_errors > 0:
                    logger.info(f"✓ {dataset}/{entity}: {doc_count} documents ({gen_errors} errors)")
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
    
    # Phase 2: Run SQUiD pipeline
    logger.info("\n" + "="*80)
    logger.info("Phase 2: SQUiD Pipeline (if not skipped)")
    logger.info("="*80)
    
    if not run_squid_pipeline(args.skip_pipeline, datasets_to_process, logger):
        logger.warning("SQUiD pipeline had errors")
    
    # Summary
    summary = {
        "total_results": len(all_results),
        "successful": len([r for r in all_results if r.get("status") == "completed"]),
        "failed": len([r for r in all_results if r.get("status") == "failed"]),
        "results": all_results,
        "timestamp": datetime.now().isoformat()
    }
    
    dump_json(summary, args.output_dir / "summary.json")
    
    logger.info("\n" + "=" * 80)
    logger.info("Preprocessing Complete")
    logger.info("=" * 80)
    logger.info(f"Total: {summary['total_results']}")
    logger.info(f"Successful: {summary['successful']}")
    logger.info(f"Failed: {summary['failed']}")
    logger.info(f"Output: {args.output_dir}")
    logger.info("=" * 80)
    
    logger.info("\nNext: python run_challenging_queries.py --systems squid")
    
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

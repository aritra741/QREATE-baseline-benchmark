#!/usr/bin/env python3
"""
Test script to compare LLM extraction quality across different models for Med dataset.

Run on CHPC with:
  cd /path/to/UDA-Bench-main
  source quest_venv/bin/activate
  python3 test_med_llm_extraction_multimodel.py --model qwen2.5:7b-instruct
  python3 test_med_llm_extraction_multimodel.py --model qwen3:235b
"""

import sys
from pathlib import Path
import json
import random
import argparse

# Setup paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

# Import QUEST components
from quest.core.llm.llm_query import TextLLMQuerier, parse_result
from quest.core.embedding.e5Embedding import batchedE5Embeddings
import pandas as pd


def load_sample_documents():
    """Load sample drug and disease documents.
    
    Tries multiple paths for both local and CHPC systems:
    - Local: /Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare/
    - CHPC: /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main/source_data/Healthcare/
    """
    # Try multiple possible paths in order of preference
    possible_paths = [
        PROJECT_ROOT / "source_data" / "Healthcare",      # Both local and CHPC (relative)
        Path("/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare"),  # Local absolute
        Path("/uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main/source_data/Healthcare"),  # CHPC absolute
        PROJECT_ROOT / "preprocess_squid" / "Med",        # Alternative
    ]
    
    drug_dir = None
    disease_dir = None
    found_path = None
    
    # Try to find drug_small and disease_small first
    for base_path in possible_paths:
        drug_candidate = base_path / "drug_small"
        disease_candidate = base_path / "disease_small"
        if drug_candidate.exists() and disease_candidate.exists():
            drug_dir = drug_candidate
            disease_dir = disease_candidate
            found_path = base_path
            print(f"✓ Found documents at: {found_path}")
            break
    
    # Fallback to drug and disease (without _small suffix)
    if not drug_dir:
        for base_path in possible_paths:
            drug_candidate = base_path / "drug"
            disease_candidate = base_path / "disease"
            if drug_candidate.exists() and disease_candidate.exists():
                drug_dir = drug_candidate
                disease_dir = disease_candidate
                found_path = base_path
                print(f"✓ Found documents at: {found_path}")
                break
    
    drugs = []
    diseases = []
    
    if drug_dir and drug_dir.exists():
        txt_files = sorted(list(drug_dir.glob("*.txt")))[:5]  # First 5 drugs
        print(f"  Loading {len(txt_files)} drug documents from {drug_dir}")
        for txt_file in txt_files:
            try:
                with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                    drugs.append({
                        'id': txt_file.stem,
                        'text': f.read()[:2000],  # First 2000 chars
                        'filename': txt_file.name
                    })
            except Exception as e:
                print(f"  Warning: Could not read {txt_file}: {e}")
    
    if disease_dir and disease_dir.exists():
        txt_files = sorted(list(disease_dir.glob("*.txt")))[:5]  # First 5 diseases
        print(f"  Loading {len(txt_files)} disease documents from {disease_dir}")
        for txt_file in txt_files:
            try:
                with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                    diseases.append({
                        'id': txt_file.stem,
                        'text': f.read()[:2000],  # First 2000 chars
                        'filename': txt_file.name
                    })
            except Exception as e:
                print(f"  Warning: Could not read {txt_file}: {e}")
    
    return drugs, diseases


def test_llm_extraction(model_name):
    """Test LLM extraction of disease_name from Med documents."""
    
    print("\n" + "="*80)
    print(f"TESTING LLM EXTRACTION FOR MED DATASET - Model: {model_name}")
    print("="*80 + "\n")
    
    # Load sample documents
    drugs, diseases = load_sample_documents()
    
    if not drugs or not diseases:
        print("ERROR: Could not load sample documents!")
        print(f"  Tried paths:")
        print(f"    - {PROJECT_ROOT / 'source_data' / 'Healthcare'}")
        print(f"    - /Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare")
        print(f"    - /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main/source_data/Healthcare")
        print(f"    - {PROJECT_ROOT / 'preprocess_squid' / 'Med'}")
        print(f"\n  Loaded {len(drugs)} drugs and {len(diseases)} diseases")
        return
    
    print(f"✓ Loaded {len(drugs)} drug documents and {len(diseases)} disease documents\n")
    
    # Initialize LLM querier with specified model
    print(f"Initializing LLM querier (ollama/{model_name})...")
    # Create querier with the specified model
    querier = TextLLMQuerier(prompt="", llm=f"ollama/{model_name}")
    print(f"✓ LLM querier initialized with model: {querier.llm}\n")
    
    # Test 1: Extract disease_name from DRUG documents
    print("-" * 80)
    print("TEST 1: Extracting disease_name from DRUG documents")
    print("-" * 80)
    
    drug_texts = [doc['text'] for doc in drugs]
    drug_ids = list(range(1, len(drugs) + 1))
    
    print(f"\nSending {len(drug_texts)} drug documents to LLM...")
    print("Streaming responses:\n")
    
    try:
        drug_results = querier.extract_attribute(
            textList=drug_texts,
            doc_idList=drug_ids,
            attributeList=['disease_name']
        )
        print("\nDrug extraction results:")
        print(drug_results)
    except Exception as e:
        print(f"\n❌ ERROR during drug extraction: {type(e).__name__}: {str(e)[:200]}")
        print("   Model may not be responding or may be too large for timeout")
        return
    
    # Test 2: Extract disease_name from DISEASE documents
    print("-" * 80)
    print("TEST 2: Extracting disease_name from DISEASE documents")
    print("-" * 80)
    
    disease_texts = [doc['text'] for doc in diseases]
    disease_ids = list(range(1, len(diseases) + 1))
    
    print(f"\nSending {len(disease_texts)} disease documents to LLM...")
    print("Streaming responses:\n")
    
    try:
        disease_results = querier.extract_attribute(
            textList=disease_texts,
            doc_idList=disease_ids,
            attributeList=['disease_name']
        )
        print("\nDisease extraction results:")
        print(disease_results)
    except Exception as e:
        print(f"\n❌ ERROR during disease extraction: {type(e).__name__}: {str(e)[:200]}")
        print("   Model may not be responding or may be too large for timeout")
        return
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    # Count TRUE successful extractions (non-null AND non-whitespace)
    drug_true_success = drug_results['disease_name'].apply(
        lambda x: x is not None and isinstance(x, str) and x.strip() != ''
    ).sum()
    disease_true_success = disease_results['disease_name'].apply(
        lambda x: x is not None and isinstance(x, str) and x.strip() != ''
    ).sum()
    
    print(f"\nModel: {model_name}")
    print(f"Drug documents:    {drug_true_success}/{len(drug_results)} successful extractions ({100*drug_true_success/len(drug_results):.1f}%)")
    print(f"Disease documents: {disease_true_success}/{len(disease_results)} successful extractions ({100*disease_true_success/len(disease_results):.1f}%)")
    
    if drug_true_success == 0 and disease_true_success == 0:
        print("\n❌ LLM EXTRACTION IS COMPLETELY FAILING for Med dataset")
        print("   This explains why join_1 returns 0 rows")
    elif drug_true_success < len(drug_results) * 0.5 or disease_true_success < len(disease_results) * 0.5:
        print("\n⚠️  LLM EXTRACTION IS UNRELIABLE (< 50% success rate)")
        print("   This is likely causing join_1 to return few or no rows")
        print(f"\n   Actual extractions (non-empty):")
        drug_extracts = drug_results[drug_results['disease_name'].astype(str).str.strip() != '']['disease_name'].unique()
        disease_extracts = disease_results[disease_results['disease_name'].astype(str).str.strip() != '']['disease_name'].unique()
        print(f"     Drugs: {drug_extracts}")
        print(f"     Diseases: {disease_extracts}")
    else:
        print("\n✓ LLM extraction appears to be working reasonably well")
    
    print("\n" + "="*80 + "\n")
    
    return {
        'model': model_name,
        'drug_success_rate': 100*drug_true_success/len(drug_results),
        'disease_success_rate': 100*disease_true_success/len(disease_results),
        'drug_count': drug_true_success,
        'disease_count': disease_true_success,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test LLM extraction for Med dataset with different models')
    parser.add_argument('--model', type=str, default='qwen2.5:7b-instruct', 
                        help='LLM model to test (e.g., qwen2.5:7b-instruct or qwen3:235b)')
    args = parser.parse_args()
    
    result = test_llm_extraction(args.model)

#!/usr/bin/env python3
"""
Test script to isolate LLM extraction quality for Med dataset.
Tests whether the LLM can extract disease_name from drug and disease documents.

Run on CHPC with:
  cd /path/to/UDA-Bench-main
  source quest_venv/bin/activate
  python3 test_med_llm_extraction.py
"""

import sys
from pathlib import Path
import json
import random

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


def test_llm_extraction():
    """Test LLM extraction of disease_name from Med documents."""
    
    print("\n" + "="*80)
    print("TESTING LLM EXTRACTION FOR MED DATASET")
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
    
    # Initialize LLM querier
    print("Initializing LLM querier (ollama/qwen2.5:7b-instruct)...")
    querier = TextLLMQuerier(prompt="")
    print("✓ LLM querier initialized\n")
    
    # Test 1: Extract disease_name from DRUG documents
    print("-" * 80)
    print("TEST 1: Extracting disease_name from DRUG documents")
    print("-" * 80)
    
    drug_texts = [doc['text'] for doc in drugs]
    drug_ids = list(range(1, len(drugs) + 1))
    
    print(f"\nSending {len(drug_texts)} drug documents to LLM...")
    print("Sample drug document (first 500 chars):")
    print(drugs[0]['text'][:500])
    print("\n")
    
    drug_results = querier.extract_attribute(
        textList=drug_texts,
        doc_idList=drug_ids,
        attributeList=['disease_name']
    )
    
    print("\nDrug extraction results:")
    print(drug_results)
    print(f"\nNon-null disease_name count: {drug_results['disease_name'].notna().sum()} / {len(drug_results)}")
    print(f"Sample extracted values:\n{drug_results['disease_name'].unique()[:5]}\n")
    
    # Test 2: Extract disease_name from DISEASE documents
    print("-" * 80)
    print("TEST 2: Extracting disease_name from DISEASE documents")
    print("-" * 80)
    
    disease_texts = [doc['text'] for doc in diseases]
    disease_ids = list(range(1, len(diseases) + 1))
    
    print(f"\nSending {len(disease_texts)} disease documents to LLM...")
    print("Sample disease document (first 500 chars):")
    print(diseases[0]['text'][:500])
    print("\n")
    
    disease_results = querier.extract_attribute(
        textList=disease_texts,
        doc_idList=disease_ids,
        attributeList=['disease_name']
    )
    
    print("\nDisease extraction results:")
    print(disease_results)
    print(f"\nNon-null disease_name count: {disease_results['disease_name'].notna().sum()} / {len(disease_results)}")
    print(f"Sample extracted values:\n{disease_results['disease_name'].unique()[:5]}\n")
    
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
    
    print(f"\nDrug documents:    {drug_true_success}/{len(drug_results)} successful extractions ({100*drug_true_success/len(drug_results):.1f}%)")
    print(f"Disease documents: {disease_true_success}/{len(disease_results)} successful extractions ({100*disease_true_success/len(disease_results):.1f}%)")
    
    if drug_true_success == 0 and disease_true_success == 0:
        print("\n❌ LLM EXTRACTION IS COMPLETELY FAILING for Med dataset")
        print("   This explains why join_1 returns 0 rows")
    elif drug_true_success < len(drug_results) * 0.5 or disease_true_success < len(disease_results) * 0.5:
        print("\n⚠️  LLM EXTRACTION IS UNRELIABLE (< 50% success rate)")
        print("   This is likely causing join_1 to return few or no rows")
        print(f"\n   Actual extractions (non-empty):")
        print(f"     Drugs: {drug_results[drug_results['disease_name'].str.strip() != '']['disease_name'].unique()}")
        print(f"     Diseases: {disease_results[disease_results['disease_name'].str.strip() != '']['disease_name'].unique()}")
    else:
        print("\n✓ LLM extraction appears to be working reasonably well")
    
    print("\n" + "="*80 + "\n")


if __name__ == '__main__':
    test_llm_extraction()

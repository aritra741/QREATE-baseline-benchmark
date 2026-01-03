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
    """Load sample drug and disease documents."""
    raw_dir = PROJECT_ROOT / "raw" / "datasets" / "Med"
    
    # Load drug documents
    drug_dir = raw_dir / "drug_small"
    disease_dir = raw_dir / "disease_small"
    
    drugs = []
    diseases = []
    
    if drug_dir.exists():
        for txt_file in sorted(list(drug_dir.glob("*.txt")))[:5]:  # First 5 drugs
            with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                drugs.append({
                    'id': txt_file.stem,
                    'text': f.read()[:2000],  # First 2000 chars
                    'filename': txt_file.name
                })
    
    if disease_dir.exists():
        for txt_file in sorted(list(disease_dir.glob("*.txt")))[:5]:  # First 5 diseases
            with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                diseases.append({
                    'id': txt_file.stem,
                    'text': f.read()[:2000],  # First 2000 chars
                    'filename': txt_file.name
                })
    
    return drugs, diseases


def test_llm_extraction():
    """Test LLM extraction of disease_name from Med documents."""
    
    print("\n" + "="*80)
    print("TESTING LLM EXTRACTION FOR MED DATASET")
    print("="*80 + "\n")
    
    # Load sample documents
    drugs, diseases = load_sample_documents()
    
    if not drugs or not diseases:
        print("ERROR: Could not load sample documents from raw/datasets/Med/")
        print(f"  Drug dir: {PROJECT_ROOT / 'raw' / 'datasets' / 'Med' / 'drug_small'}")
        print(f"  Disease dir: {PROJECT_ROOT / 'raw' / 'datasets' / 'Med' / 'disease_small'}")
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
    
    drug_success = drug_results['disease_name'].notna().sum()
    disease_success = disease_results['disease_name'].notna().sum()
    
    print(f"\nDrug documents:    {drug_success}/{len(drug_results)} successful extractions ({100*drug_success/len(drug_results):.1f}%)")
    print(f"Disease documents: {disease_success}/{len(disease_results)} successful extractions ({100*disease_success/len(disease_results):.1f}%)")
    
    if drug_success == 0 and disease_success == 0:
        print("\n❌ LLM EXTRACTION IS COMPLETELY FAILING for Med dataset")
        print("   This explains why join_1 returns 0 rows")
    elif drug_success < len(drug_results) * 0.5 or disease_success < len(disease_results) * 0.5:
        print("\n⚠️  LLM EXTRACTION IS UNRELIABLE (< 50% success rate)")
        print("   This is likely causing join_1 to return few or no rows")
    else:
        print("\n✓ LLM extraction appears to be working reasonably well")
    
    print("\n" + "="*80 + "\n")


if __name__ == '__main__':
    test_llm_extraction()

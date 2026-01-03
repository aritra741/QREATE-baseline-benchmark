#!/usr/bin/env python3
"""
Test script to compare LLM extraction quality across different models for Med dataset.
Uses direct Ollama API with streaming to show real-time progress.

Run on CHPC with:
  cd /path/to/UDA-Bench-main
  python3 -u test_med_llm_extraction_multimodel.py --model qwen3:235b 2>&1 | tee results.txt
"""

import sys
from pathlib import Path
import json
import argparse
import requests
import time

# Setup paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

import pandas as pd


def load_sample_documents():
    """Load sample drug and disease documents."""
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


def extract_with_ollama(model_name, text, doc_id, api_base="http://localhost:11434"):
    """Extract disease_name from text using Ollama with streaming."""
    
    prompt = f"""Extract the disease_name from the following document.
Return ONLY in this format: disease_name: <value>

If no disease name is found, return: disease_name: NONE

Document:
{text}

Answer:"""
    
    try:
        response = requests.post(
            f"{api_base}/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": True,
                "temperature": 0,
                "num_predict": 50,
            },
            timeout=300,  # 5 minute timeout
        )
        response.raise_for_status()
        
        # Stream and collect response
        full_response = ""
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                chunk = data.get("response", "")
                if chunk:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                    full_response += chunk
                if data.get("done", False):
                    break
        
        sys.stdout.write(f" [doc_id={doc_id}]\n")
        sys.stdout.flush()
        
        return full_response.strip()
    
    except requests.exceptions.Timeout:
        print(f"\n⏱️  TIMEOUT for doc_id={doc_id} (model too large or slow)")
        return "TIMEOUT"
    except Exception as e:
        print(f"\n❌ ERROR for doc_id={doc_id}: {str(e)[:100]}")
        return f"ERROR: {str(e)[:50]}"


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
        return
    
    print(f"✓ Loaded {len(drugs)} drug documents and {len(diseases)} disease documents\n")
    
    # Test 1: Extract disease_name from DRUG documents
    print("-" * 80)
    print("TEST 1: Extracting disease_name from DRUG documents")
    print("-" * 80 + "\n")
    
    drug_results = []
    for i, drug in enumerate(drugs, 1):
        print(f"Drug {i}/5: ", end="", flush=True)
        result = extract_with_ollama(model_name, drug['text'], i)
        drug_results.append({'doc_id': i, 'text': result})
    
    print()
    
    # Test 2: Extract disease_name from DISEASE documents
    print("-" * 80)
    print("TEST 2: Extracting disease_name from DISEASE documents")
    print("-" * 80 + "\n")
    
    disease_results = []
    for i, disease in enumerate(diseases, 1):
        print(f"Disease {i}/5: ", end="", flush=True)
        result = extract_with_ollama(model_name, disease['text'], i)
        disease_results.append({'doc_id': i, 'text': result})
    
    print()
    
    # Parse results
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    def count_successful(results):
        """Count extractions that have actual disease names."""
        count = 0
        for r in results:
            text = r['text']
            # Extract value after "disease_name: "
            if "disease_name:" in text.lower():
                parts = text.lower().split("disease_name:")
                if len(parts) > 1:
                    value = parts[1].strip()
                    if value and value.lower() != "none" and not value.startswith("error") and not value.startswith("timeout"):
                        count += 1
        return count
    
    drug_success = count_successful(drug_results)
    disease_success = count_successful(disease_results)
    
    print(f"\nModel: {model_name}")
    print(f"Drug documents:    {drug_success}/{len(drug_results)} successful extractions ({100*drug_success/len(drug_results):.1f}%)")
    print(f"Disease documents: {disease_success}/{len(disease_results)} successful extractions ({100*disease_success/len(disease_results):.1f}%)")
    
    print(f"\nDrug results:")
    for r in drug_results:
        print(f"  Doc {r['doc_id']}: {r['text'][:80]}")
    
    print(f"\nDisease results:")
    for r in disease_results:
        print(f"  Doc {r['doc_id']}: {r['text'][:80]}")
    
    if drug_success == 0 and disease_success == 0:
        print("\n❌ LLM EXTRACTION IS COMPLETELY FAILING for Med dataset")
    elif drug_success < len(drug_results) * 0.5 or disease_success < len(disease_results) * 0.5:
        print("\n⚠️  LLM EXTRACTION IS UNRELIABLE (< 50% success rate)")
    else:
        print("\n✓ LLM extraction appears to be working reasonably well")
    
    print("\n" + "="*80 + "\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test LLM extraction for Med dataset with different models')
    parser.add_argument('--model', type=str, default='qwen2.5:7b-instruct', 
                        help='LLM model to test (e.g., qwen2.5:7b-instruct or qwen3:235b)')
    args = parser.parse_args()
    
    test_llm_extraction(args.model)

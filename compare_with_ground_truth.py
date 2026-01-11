#!/usr/bin/env python3
"""
Compare GEM results with ground truth data.

Metrics:
- Precision: correct extractions / total extractions
- Recall: correct extractions / total ground truth
- F1 Score: harmonic mean of precision and recall
- Entity coverage: % of ground truth entities found
"""

import json
import csv
import sys
import requests
import pandas as pd
from pathlib import Path
from collections import defaultdict

def normalize_value(val):
    """Normalize a value for comparison."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    val_str = str(val).strip().lower()
    # Remove common filler words that interfere with matching
    for filler in ["the ", "a ", "an "]:
        if val_str.startswith(filler):
            val_str = val_str[len(filler):]
    val_str = " ".join(val_str.split())
    return val_str

def llm_ask_if_same_entity(val1: str, val2: str) -> bool:
    """Ask LLM if two values refer to the same entity or concept."""
    try:
        # Generic principle: handle specific vs general instances without domain-specific examples
        prompt = f"""Do these two values refer to the same entity, concept, or is one a specific instance/variant of the other?
If they represent the same core concept (even if one has more modifiers or is a sub-type), they should be considered a match.

Value 1: {val1}
Value 2: {val2}

Answer with ONLY "yes" or "no" (lowercase)."""
        
        response = requests.post(
            "http://localhost:11434/v1/chat/completions",
            json={
                "model": "qwen2.5:7b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            answer = result["choices"][0]["message"]["content"].strip().lower()
            return "yes" in answer
    except Exception:
        pass
    
    return False

def values_match(val1, val2):
    """Check if two values match using two-stage matching."""
    norm1 = normalize_value(val1)
    norm2 = normalize_value(val2)
    
    if not norm1 or not norm2:
        return norm1 == norm2
    
    # Exact match
    if norm1 == norm2:
        return True
    
    # Split by || and try cross-matching
    values1 = [v.strip() for v in norm1.split('||') if v.strip()]
    values2 = [v.strip() for v in norm2.split('||') if v.strip()]
    
    for v1 in values1:
        for v2 in values2:
            if v1 == v2:
                return True
            
            # Try numeric comparison
            try:
                if abs(float(v1) - float(v2)) < 0.001:
                    return True
            except ValueError:
                pass
            
            # Try semantic matching with LLM verification directly
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, v1, v2).ratio()
            # Lower threshold to 0.6 to capture more semantic candidates
            if ratio >= 0.6 or (v1 in v2) or (v2 in v1):
                if llm_ask_if_same_entity(v1, v2):
                    return True
    
    return False

PROJECT_ROOT = Path(__file__).parent
CACHE_DIR = PROJECT_ROOT / "systems" / "GEM" / ".cache"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Med"
RESULTS_FILE = CACHE_DIR / "query_results.json"
EXTRACTED_FILE = CACHE_DIR / "extracted_entities.json"

# Ground truth files
GT_FILES = {
    "drug": GROUND_TRUTH_DIR / "drug.csv",
    "disease": GROUND_TRUTH_DIR / "disease.csv",
    "institution": GROUND_TRUTH_DIR / "institution.csv"
}


def load_ground_truth(entity_type):
    """Load ground truth CSV."""
    if entity_type not in GT_FILES or not GT_FILES[entity_type].exists():
        print(f"⚠ Ground truth file not found: {GT_FILES.get(entity_type, 'N/A')}")
        return []
    
    records = []
    with open(GT_FILES[entity_type], 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    
    return records


def load_extracted(entity_type):
    """Load extracted entities from cache."""
    if not EXTRACTED_FILE.exists():
        print(f"⚠ Extracted file not found: {EXTRACTED_FILE}")
        return []
    
    with open(EXTRACTED_FILE, 'r') as f:
        data = json.load(f)
    
    return data.get(entity_type, [])


def get_key_field(entity_type):
    """Get the key field for each entity type."""
    key_fields = {
        "drug": "generic_name",
        "disease": "disease_name",
        "institution": "institution_name"
    }
    return key_fields.get(entity_type)


def compare_entities(entity_type):
    """Compare extracted entities with ground truth."""
    print()
    print("=" * 100)
    print(f"COMPARISON: {entity_type.upper()}")
    print("=" * 100)
    print()
    
    ground_truth = load_ground_truth(entity_type)
    extracted = load_extracted(entity_type)
    key_field = get_key_field(entity_type)
    
    print(f"Ground truth records: {len(ground_truth)}")
    print(f"Extracted records: {len(extracted)}")
    print()
    
    # Build sets of unique key values from GT
    gt_keys = set()
    for record in ground_truth:
        raw_key = record.get(key_field, "")
        if raw_key:
            for variant in raw_key.split("||"):
                v = variant.strip()
                if v:
                    gt_keys.add(v)
    
    # Build list of unique key values from extracted
    extracted_keys = set()
    for record in extracted:
        raw_key = record.get(key_field, "")
        if raw_key:
            for variant in raw_key.split("||"):
                v = variant.strip()
                if v:
                    extracted_keys.add(v)
    
    # Calculate metrics with semantic matching
    true_positives = 0
    matched_gt_keys = set()
    matched_extracted_keys = set()
    
    # Check each extracted key against ground truth
    for extracted_key in extracted_keys:
        found_match = False
        for gt_key in gt_keys:
            if values_match(extracted_key, gt_key):
                # Only log successful matches if they were fuzzy
                if extracted_key != gt_key:
                    print(f"  [MATCH] '{extracted_key}' matched GT '{gt_key}'")
                true_positives += 1
                matched_gt_keys.add(gt_key)
                matched_extracted_keys.add(extracted_key)
                found_match = True
                break
    
    false_positives = len(extracted_keys) - true_positives
    false_negatives = len(gt_keys) - len(matched_gt_keys)
    
    precision = true_positives / len(extracted_keys) if extracted_keys else 0
    recall = len(matched_gt_keys) / len(gt_keys) if gt_keys else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"True Positives (extracted & matched in GT): {true_positives}")
    print(f"False Positives (extracted but no match in GT): {false_positives}")
    print(f"False Negatives (in GT but not extracted): {false_negatives}")
    print()
    print(f"Precision: {precision:.2%}")
    print(f"Recall: {recall:.2%}")
    print(f"F1 Score: {f1:.4f}")
    print()
    
    # Show examples of missing entities
    if 0 < false_negatives <= 10:
        print("Missing entities (not extracted):")
        for key in sorted(gt_keys - matched_gt_keys):
            print(f"  - {key}")
        print()
    
    # Show examples of extra entities
    if 0 < false_positives <= 10:
        print("Extra entities (extracted but not in GT):")
        for key in sorted(extracted_keys - matched_extracted_keys):
            print(f"  - {key}")
        print()
    
    return {
        "entity_type": entity_type,
        "gt_count": len(gt_keys),
        "extracted_count": len(extracted_keys),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1
    }


def compare_query_results():
    """Compare query results."""
    if not RESULTS_FILE.exists():
        print("⚠ Query results file not found. Run test_gem_complete_system.py first.")
        return
    
    with open(RESULTS_FILE, 'r') as f:
        results = json.load(f)
    
    print()
    print("=" * 100)
    print("QUERY EXECUTION RESULTS")
    print("=" * 100)
    print()
    
    total_queries = len(results)
    successful_queries = sum(1 for r in results.values() if r.get("success"))
    total_rows = sum(r.get("rows", 0) for r in results.values())
    
    binary_queries_rows = sum(
        r.get("rows", 0) for qid, r in results.items() 
        if int(qid.split('_')[1]) <= 10
    )
    multi_table_queries_rows = sum(
        r.get("rows", 0) for qid, r in results.items() 
        if int(qid.split('_')[1]) > 10
    )
    
    print(f"Total queries: {total_queries}")
    print(f"Successful: {successful_queries}/{total_queries}")
    print(f"Success rate: {successful_queries/total_queries*100:.1f}%")
    print()
    print(f"Binary JOIN queries (drug-disease):")
    print(f"  Rows: {binary_queries_rows}")
    print(f"  Average per query: {binary_queries_rows/10:.1f}")
    print()
    print(f"Multi-table JOIN queries (drug-disease-institution):")
    print(f"  Rows: {multi_table_queries_rows}")
    print(f"  Average per query: {multi_table_queries_rows/10:.1f}")
    print()
    print(f"Total rows across all queries: {total_rows}")
    print()


def main():
    """Main comparison."""
    print()
    print("=" * 100)
    print("GEM vs GROUND TRUTH COMPARISON")
    print("=" * 100)
    
    metrics = {}
    for entity_type in ["drug", "disease", "institution"]:
        metrics[entity_type] = compare_entities(entity_type)
    
    compare_query_results()
    
    # Summary
    print()
    print("=" * 100)
    print("OVERALL SUMMARY")
    print("=" * 100)
    print()
    print(f"{'Entity Type':<20} {'Precision':<15} {'Recall':<15} {'F1 Score':<15}")
    print("-" * 65)
    for entity_type, m in metrics.items():
        print(f"{entity_type:<20} {m['precision']:<14.2%} {m['recall']:<14.2%} {m['f1']:<14.4f}")
    
    avg_f1 = sum(m['f1'] for m in metrics.values()) / len(metrics)
    avg_precision = sum(m['precision'] for m in metrics.values()) / len(metrics)
    avg_recall = sum(m['recall'] for m in metrics.values()) / len(metrics)
    
    print("-" * 65)
    print(f"{'AVERAGE':<20} {avg_precision:<14.2%} {avg_recall:<14.2%} {avg_f1:<14.4f}")
    print()
    
    # Save metrics
    metrics_file = CACHE_DIR / "comparison_metrics.json"
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"✓ Metrics saved to {metrics_file}")
    print()


if __name__ == "__main__":
    main()

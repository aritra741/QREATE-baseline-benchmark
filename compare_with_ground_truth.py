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
from pathlib import Path
from collections import defaultdict

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
    
    # Build sets of key values
    gt_keys = set()
    gt_key_to_record = {}
    for record in ground_truth:
        key = record.get(key_field, "").strip().lower()
        if key:
            gt_keys.add(key)
            gt_key_to_record[key] = record
    
    extracted_keys = set()
    extracted_key_to_record = {}
    for record in extracted:
        key = record.get(key_field, "").strip().lower()
        if key:
            extracted_keys.add(key)
            extracted_key_to_record[key] = record
    
    # Calculate metrics
    true_positives = len(gt_keys & extracted_keys)  # Found in both
    false_positives = len(extracted_keys - gt_keys)  # Extracted but not in GT
    false_negatives = len(gt_keys - extracted_keys)  # In GT but not extracted
    
    precision = true_positives / len(extracted_keys) if extracted_keys else 0
    recall = true_positives / len(gt_keys) if gt_keys else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"True Positives (extracted & in GT): {true_positives}")
    print(f"False Positives (extracted but not in GT): {false_positives}")
    print(f"False Negatives (in GT but not extracted): {false_negatives}")
    print()
    print(f"Precision: {precision:.2%}")
    print(f"Recall: {recall:.2%}")
    print(f"F1 Score: {f1:.4f}")
    print()
    
    # Show examples of missing entities
    if false_negatives > 0 and false_negatives <= 10:
        print("Missing entities (not extracted):")
        for key in sorted(gt_keys - extracted_keys):
            print(f"  - {key}")
        print()
    
    # Show examples of extra entities
    if false_positives > 0 and false_positives <= 10:
        print("Extra entities (extracted but not in GT):")
        for key in sorted(extracted_keys - gt_keys):
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

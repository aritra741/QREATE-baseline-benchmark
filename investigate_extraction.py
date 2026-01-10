#!/usr/bin/env python3
"""
Investigation: Compare extracted vs ground truth to understand extraction quality.

Shows:
- What we extracted that's in ground truth (correct)
- What we extracted that's NOT in ground truth (false positives - what are they?)
- What we missed from ground truth (false negatives - what are they?)
"""

import json
import csv
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent
CACHE_DIR = PROJECT_ROOT / "systems" / "GEM" / ".cache"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Med"
EXTRACTED_FILE = CACHE_DIR / "extracted_entities.json"

GT_FILES = {
    "drug": GROUND_TRUTH_DIR / "drug.csv",
    "disease": GROUND_TRUTH_DIR / "disease.csv",
    "institution": GROUND_TRUTH_DIR / "institution.csv"
}


def load_ground_truth(entity_type):
    """Load ground truth CSV."""
    if entity_type not in GT_FILES or not GT_FILES[entity_type].exists():
        return []
    
    records = []
    with open(GT_FILES[entity_type], 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    
    return records


def load_extracted(entity_type):
    """Load extracted entities."""
    if not EXTRACTED_FILE.exists():
        return []
    
    with open(EXTRACTED_FILE, 'r') as f:
        data = json.load(f)
    
    return data.get(entity_type, [])


def get_key_field(entity_type):
    """Get key field for entity type."""
    return {
        "drug": "generic_name",
        "disease": "disease_name",
        "institution": "institution_name"
    }.get(entity_type)


def investigate_entity_type(entity_type):
    """Investigate extractions for a single entity type."""
    print()
    print("=" * 120)
    print(f"INVESTIGATION: {entity_type.upper()}")
    print("=" * 120)
    print()
    
    ground_truth = load_ground_truth(entity_type)
    extracted = load_extracted(entity_type)
    key_field = get_key_field(entity_type)
    
    # Normalize keys
    gt_keys = {}  # normalized -> original
    for record in ground_truth:
        key = record.get(key_field, "").strip().lower()
        if key:
            gt_keys[key] = record.get(key_field, "")
    
    extracted_keys = {}  # normalized -> original
    extracted_full = {}  # normalized -> full record
    for record in extracted:
        key = record.get(key_field, "").strip().lower()
        if key:
            extracted_keys[key] = record.get(key_field, "")
            extracted_full[key] = record
    
    # Categorize
    correct = gt_keys.keys() & extracted_keys.keys()
    false_positives = extracted_keys.keys() - gt_keys.keys()
    false_negatives = gt_keys.keys() - extracted_keys.keys()
    
    print(f"Ground Truth: {len(gt_keys)} unique entities")
    print(f"Extracted: {len(extracted_keys)} unique entities")
    print()
    print(f"✓ Correct (in both): {len(correct)}")
    print(f"✗ False Positives (extracted but not in GT): {len(false_positives)}")
    print(f"✗ False Negatives (in GT but not extracted): {len(false_negatives)}")
    print()
    
    # Show correct extractions
    print("-" * 120)
    print(f"CORRECT EXTRACTIONS ({len(correct)} examples, showing first 10):")
    print("-" * 120)
    for i, key in enumerate(sorted(correct)):
        if i >= 10:
            print(f"... and {len(correct) - 10} more")
            break
        print(f"  ✓ {gt_keys[key]}")
    print()
    
    # Show false positives (what are we extracting that shouldn't be there?)
    print("-" * 120)
    print(f"FALSE POSITIVES - WHAT ARE WE EXTRACTING INCORRECTLY? ({len(false_positives)} examples):")
    print("-" * 120)
    print("These are extracted but NOT in ground truth. What are they?")
    print()
    for i, key in enumerate(sorted(false_positives)):
        if i >= 20:
            print(f"... and {len(false_positives) - 20} more")
            break
        
        extracted_record = extracted_full[key]
        
        # Show key + sample other fields
        print(f"{i+1}. {extracted_keys[key]}")
        
        # Show a few other fields for context
        other_fields = {k: v for k, v in extracted_record.items() if k != key_field and v}
        for field, value in list(other_fields.items())[:2]:
            # Truncate long values
            value_str = str(value)[:80]
            print(f"   - {field}: {value_str}")
        print()
    
    # Show false negatives (what did we miss?)
    print("-" * 120)
    print(f"FALSE NEGATIVES - WHAT DID WE MISS FROM GROUND TRUTH? ({len(false_negatives)} examples):")
    print("-" * 120)
    print("These are in ground truth but we didn't extract them. Why?")
    print()
    for i, key in enumerate(sorted(false_negatives)):
        if i >= 20:
            print(f"... and {len(false_negatives) - 20} more")
            break
        print(f"{i+1}. {gt_keys[key]}")
    print()
    
    # Statistics on extracted record completeness
    print("-" * 120)
    print(f"EXTRACTION QUALITY:")
    print("-" * 120)
    
    # Check how many fields are filled per extracted record
    fields_per_record = []
    for record in extracted:
        filled_fields = sum(1 for v in record.values() if v and str(v).strip())
        fields_per_record.append(filled_fields)
    
    if fields_per_record:
        print(f"Average fields per extracted record: {sum(fields_per_record) / len(fields_per_record):.1f}")
        print(f"Min fields: {min(fields_per_record)}")
        print(f"Max fields: {max(fields_per_record)}")
    print()


def main():
    """Main investigation."""
    print()
    print("=" * 120)
    print("GEM EXTRACTION INVESTIGATION")
    print("Understanding what we're extracting vs what ground truth expects")
    print("=" * 120)
    
    for entity_type in ["drug", "disease", "institution"]:
        investigate_entity_type(entity_type)
    
    print("=" * 120)
    print("NEXT STEPS:")
    print("=" * 120)
    print()
    print("1. Review the FALSE POSITIVES above:")
    print("   - Are they variants/synonyms we should resolve?")
    print("   - Are they completely wrong extractions (LLM hallucination)?")
    print("   - Are they legitimate entities but not in ground truth?")
    print()
    print("2. Review the FALSE NEGATIVES above:")
    print("   - Are these entities not mentioned in source files?")
    print("   - Are they mentioned but in a form we don't recognize?")
    print("   - Do we need to adjust extraction prompts?")
    print()
    print("3. Recommendations:")
    print("   - Make extraction prompts MORE STRICT (only extract if explicitly stated)")
    print("   - Add confidence scoring to filter low-confidence extractions")
    print("   - Investigate if false positives are actually correct but missing from GT")
    print()


if __name__ == "__main__":
    main()

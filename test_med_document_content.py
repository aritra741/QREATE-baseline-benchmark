#!/usr/bin/env python
"""
Test to determine if Med dataset documents actually contain disease attributes.

This script will:
1. Load the Med index
2. Sample random documents from the disease table
3. Inspect their actual content
4. Check if they contain disease-related fields
5. Prove/disprove the "wrong document category" hypothesis
"""

import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

# Set local path
os.environ["QUEST_INDEX_ROOT"] = str(PROJECT_ROOT.parent)

def inspect_documents():
    """Load index and inspect actual document content."""
    print("\n" + "=" * 80)
    print("DOCUMENT CONTENT INSPECTION TEST")
    print("=" * 80)
    
    # Load indexer
    print("\n[1] Loading disease indexer...")
    try:
        from quest.db.indexer.indexer import load_all_indexer
        gb_indexer = load_all_indexer(table_to_type=None)
        indexer_obj, _ = gb_indexer.get_indexer("disease")
        doc_ids = indexer_obj.get_docs_id()
        print(f"✓ Loaded disease indexer with {len(doc_ids)} documents")
    except Exception as e:
        print(f"✗ Failed: {e}")
        return
    
    # Sample documents
    import random
    sample_size = min(10, len(doc_ids))  # Sample up to 10 documents
    sample_ids = random.sample(doc_ids, sample_size)
    
    print(f"\n[2] Sampling {sample_size} random documents...")
    
    disease_keywords = {
        'disease_name': ['disease', 'diabetes', 'arthritis', 'cancer', 'syndrome', 'condition', 'disorder'],
        'disease_type': ['autoimmune', 'infectious', 'genetic', 'inflammatory', 'psychiatric', 'metabolic'],
        'etiology': ['cause', 'etiology', 'pathogen', 'genetic factor', 'origin'],
        'symptoms': ['symptom', 'sign', 'presentation', 'manifestation', 'complaint'],
        'diagnostic': ['diagnosis', 'test', 'imaging', 'biopsy', 'scan', 'examination'],
        'treatment': ['treatment', 'therapy', 'drug', 'medication', 'surgery', 'intervention'],
    }
    
    results = {
        'total_docs': len(sample_ids),
        'disease_docs': 0,
        'non_disease_docs': 0,
        'documents': []
    }
    
    for i, doc_id in enumerate(sample_ids, 1):
        print(f"\n{'─' * 80}")
        print(f"[Document {i}/{sample_size}] ID: {doc_id}")
        print('─' * 80)
        
        try:
            # Retrieve document text
            doc_text = indexer_obj.get_text_by_id(doc_id)
            
            if doc_text is None:
                print("⚠️  Document text is None")
                continue
            
            # Get first 500 characters
            preview = doc_text[:500] if isinstance(doc_text, str) else str(doc_text)[:500]
            print(f"Preview (first 500 chars):\n{preview}...\n")
            
            # Check for disease-related keywords
            text_lower = doc_text.lower() if isinstance(doc_text, str) else str(doc_text).lower()
            
            keyword_matches = {}
            for field, keywords in disease_keywords.items():
                matches = [kw for kw in keywords if kw in text_lower]
                if matches:
                    keyword_matches[field] = matches
            
            # Determine if this is a disease document
            is_disease_doc = len(keyword_matches) >= 3  # At least 3 disease-related fields
            
            print(f"Keyword Matches: {keyword_matches}")
            print(f"Classification: {'✓ DISEASE DOCUMENT' if is_disease_doc else '✗ NON-DISEASE DOCUMENT'}")
            
            if is_disease_doc:
                results['disease_docs'] += 1
            else:
                results['non_disease_docs'] += 1
            
            results['documents'].append({
                'doc_id': doc_id,
                'is_disease': is_disease_doc,
                'preview': preview[:200],
                'keyword_matches': keyword_matches,
                'text_length': len(doc_text) if isinstance(doc_text, str) else len(str(doc_text))
            })
            
        except Exception as e:
            print(f"✗ Error retrieving document: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print('=' * 80)
    print(f"Total documents sampled: {results['total_docs']}")
    print(f"Disease documents: {results['disease_docs']} ({100*results['disease_docs']/max(1, results['total_docs']):.1f}%)")
    print(f"Non-disease documents: {results['non_disease_docs']} ({100*results['non_disease_docs']/max(1, results['total_docs']):.1f}%)")
    
    # Save detailed results
    output_file = PROJECT_ROOT / "test_med_document_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to: {output_file}")
    
    # Conclusion
    print(f"\n{'=' * 80}")
    print("CONCLUSION")
    print('=' * 80)
    
    if results['disease_docs'] < results['total_docs'] * 0.5:
        print(f"❌ HYPOTHESIS CONFIRMED: Less than 50% of indexed 'disease' documents are actually disease documents")
        print(f"   This explains the F1=0.0 - the index contains the wrong document category!")
    else:
        print(f"✓ Most documents appear to be disease-related")
        print(f"   The problem might be with LLM extraction format, not document category")

if __name__ == "__main__":
    inspect_documents()


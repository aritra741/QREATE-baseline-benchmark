#!/usr/bin/env python3
"""
Quick test for semantic validation of extracted entities.
"""

import logging
from systems.GEM.extractor import LLMExtractor

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_validation():
    """Test the semantic validation on obvious cases."""
    
    extractor = LLMExtractor(
        model="qwen2.5:7b-instruct",
        validator_model="qwen2.5:1.5b-instruct-q8_0"
    )
    
    test_cases = [
        # (entity_type, value, chunk, should_pass)
        ("disease", "Allergic Rhinitis", "Patients with allergic rhinitis experience nasal congestion.", True),
        ("disease", "25 mg", "The patient took 25 mg of the medication.", False),
        ("disease", "Tuesday", "He came to the hospital on Tuesday.", False),
        ("institution", "Harvard University", "Harvard University is a leading research institution.", True),
        ("institution", "2025", "The study was conducted in 2025.", False),
        ("drug", "Aspirin", "Aspirin is commonly used to treat pain and fever.", True),
        ("drug", "1000 tablets", "Each box contains 1000 tablets of the medication.", False),
    ]
    
    print("\n" + "="*80)
    print("SEMANTIC VALIDATION TEST")
    print("="*80 + "\n")
    
    passed = 0
    failed = 0
    
    for entity_type, value, chunk, should_pass in test_cases:
        result = extractor.validate_extraction(entity_type, value, chunk)
        status = "✓" if result == should_pass else "✗"
        result_str = "PASS" if result else "FAIL"
        expected_str = "PASS" if should_pass else "FAIL"
        
        match = "✓" if result == should_pass else "✗ WRONG"
        print(f"{status} {entity_type:12} | {value:25} | Got: {result_str:4} | Expected: {expected_str:4} {match}")
        
        if result == should_pass:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "="*80)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*80 + "\n")

if __name__ == "__main__":
    test_validation()

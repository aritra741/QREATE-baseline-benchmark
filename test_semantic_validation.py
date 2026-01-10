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
        validator_model="qwen2.5:7b-instruct"  # Use 7B for better discrimination
    )
    
    test_cases = [
        # (entity_type, value, chunk, should_pass, description)
        # Clear valid cases
        ("disease", "Allergic Rhinitis", "Patients with allergic rhinitis experience nasal congestion.", True, "Named disease"),
        ("institution", "Harvard University", "Harvard University is a leading research institution.", True, "Named institution"),
        ("drug", "Aspirin", "Aspirin is commonly used to treat pain and fever.", True, "Named drug"),
        
        # Clear invalid cases
        ("disease", "Tuesday", "He came to the hospital on Tuesday.", False, "Time reference, not disease"),
        
        # Context-dependent: should be VALID when extracting these types
        ("dosage", "25 mg", "The patient took 25 mg of the medication.", True, "Measurement as dosage entity"),
        ("year", "2025", "The study was conducted in 2025.", True, "Year as entity"),
        ("color", "red", "The car is painted red.", True, "Adjective as color entity"),
        
        # Context-dependent: should be INVALID for these types
        ("disease", "25 mg", "The patient took 25 mg of the medication.", False, "Measurement, not disease"),
        ("institution", "2025", "The study was conducted in 2025.", False, "Year, not institution"),
        ("drug", "red", "The pills are red in color.", False, "Color, not drug"),
    ]
    
    print("\n" + "="*80)
    print("SEMANTIC VALIDATION TEST")
    print("="*80 + "\n")
    
    passed = 0
    failed = 0
    
    for entity_type, value, chunk, should_pass, description in test_cases:
        result = extractor.validate_extraction(entity_type, value, chunk)
        status = "✓" if result == should_pass else "✗"
        result_str = "PASS" if result else "FAIL"
        expected_str = "PASS" if should_pass else "FAIL"
        
        match = "✓" if result == should_pass else "✗ WRONG"
        print(f"{status} {entity_type:12} | {value:20} | Got: {result_str:4} | Expected: {expected_str:4} | {description:40} {match}")
        
        if result == should_pass:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "="*80)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*80 + "\n")

if __name__ == "__main__":
    test_validation()

#!/usr/bin/env python3
"""
Quick test to verify SQUiD integration is working.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    required_modules = [
        ("pandas", "pd"),
        ("openai", "OpenAI"),
        ("stanza", "stanza"),
    ]
    
    all_ok = True
    for module_name, import_name in required_modules:
        try:
            if import_name == "OpenAI":
                from openai import OpenAI
            elif import_name == "stanza":
                import stanza
            else:
                __import__(module_name)
            print(f"✓ {module_name}")
        except ImportError as e:
            print(f"✗ {module_name}: {e}")
            all_ok = False
    
    return all_ok

def test_squid_paths():
    """Test that SQUiD paths exist."""
    print("\nTesting SQUiD paths...")
    squid_path = PROJECT_ROOT / "systems" / "SQUiD"
    
    if not squid_path.exists():
        print(f"✗ SQUiD directory not found: {squid_path}")
        return False
    print(f"✓ SQUiD directory: {squid_path}")
    
    src_path = squid_path / "src"
    if not src_path.exists():
        print(f"✗ SQUiD src directory not found: {src_path}")
        return False
    print(f"✓ SQUiD src directory: {src_path}")
    
    required_scripts = [
        "schema_generation.py",
        "value_identification.py",
        "value_population.py",
        "database_generation.py"
    ]
    
    for script in required_scripts:
        script_path = src_path / script
        if not script_path.exists():
            print(f"✗ Missing script: {script}")
            return False
        print(f"✓ {script}")
    
    return True

def test_preprocessing_output():
    """Test that preprocessing output exists."""
    print("\nTesting preprocessing output...")
    preprocess_dir = PROJECT_ROOT / "preprocess_squid"
    
    if not preprocess_dir.exists():
        print(f"⚠ Preprocessing directory not created yet: {preprocess_dir}")
        print("  Run: python preprocess_squid_data.py --dataset all")
        return True  # Not an error, just not ready yet
    
    datasets = ["Med", "Player", "Art", "Legal", "Finan"]
    found_any = False
    
    for dataset in datasets:
        dataset_dir = preprocess_dir / dataset
        if dataset_dir.exists():
            subdirs = list(dataset_dir.iterdir())
            if subdirs:
                print(f"✓ {dataset}: {len(subdirs)} entity(ies)")
                found_any = True
    
    if not found_any:
        print("⚠ No preprocessed data found")
        print("  Run: python preprocess_squid_data.py --dataset all")
    
    return True

def test_corenlp():
    """Test CoreNLP availability for symbolic triplet extraction."""
    print("\nTesting CoreNLP...")
    try:
        import stanza
        print("✓ stanza module found")
        
        # CoreNLP is lazily downloaded on first use, so we can't test it directly
        # But we can check if it's already installed
        import os
        corenlp_home = os.path.expanduser("~/.stanza_resources")
        if os.path.exists(corenlp_home):
            print(f"✓ CoreNLP resources found at {corenlp_home}")
            return True
        else:
            print("⚠ CoreNLP resources not yet downloaded")
            print("  They will be downloaded on first use (may take a few minutes)")
            return True  # Not an error, just not cached yet
    except ImportError as e:
        print(f"✗ stanza not installed: {e}")
        print("  Install with: pip install stanza")
        return False

def test_ollama():
    """Test Ollama connection."""
    print("\nTesting Ollama connection...")
    try:
        from openai import OpenAI
        client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
        
        # Try to list models
        models = client.models.list()
        print(f"✓ Connected to Ollama at http://localhost:11434/v1")
        print(f"  Available models: {[m.id for m in models.data]}")
        
        # Check for qwen2.5
        model_ids = [m.id for m in models.data]
        if "qwen2.5:7b-instruct" in model_ids:
            print("✓ qwen2.5:7b-instruct found")
        else:
            print("⚠ qwen2.5:7b-instruct not found")
            print("  Pull with: ollama pull qwen2.5:7b-instruct")
        
        return True
    except Exception as e:
        print(f"✗ Ollama connection failed: {e}")
        print("  Make sure Ollama is running: ollama serve")
        return False

def main():
    print("=" * 60)
    print("SQUiD Integration Test")
    print("=" * 60)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("SQUiD paths", test_squid_paths()))
    results.append(("CoreNLP", test_corenlp()))
    results.append(("Preprocessing", test_preprocessing_output()))
    results.append(("Ollama", test_ollama()))
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed! Ready to run SQUiD queries.")
        print("\nRun with:")
        print("  python run_challenging_queries.py --systems squid --query-types projection")
    else:
        print("Some tests failed. Check output above for details.")
    print("=" * 60)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())


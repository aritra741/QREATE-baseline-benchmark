"""
Validation script for SQUiD integration.

This script checks that all necessary components are in place
without requiring execution.
"""

import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).parent

def check_preprocessing_script():
    """Check if preprocessing script exists."""
    script_path = PROJECT_ROOT / "preprocess_squid_data.py"
    if script_path.exists():
        print("✓ preprocess_squid_data.py exists")
        with open(script_path, 'r') as f:
            content = f.read()
            if "def preprocess_dataset" in content and "def main" in content:
                print("  ✓ Contains required functions")
                return True
            else:
                print("  ✗ Missing required functions")
                return False
    else:
        print("✗ preprocess_squid_data.py not found")
        return False

def check_runner_integration():
    """Check if SQUiDRunner is integrated into run_challenging_queries.py."""
    runner_path = PROJECT_ROOT / "run_challenging_queries.py"
    if runner_path.exists():
        print("✓ run_challenging_queries.py exists")
        with open(runner_path, 'r') as f:
            content = f.read()
            
            checks = [
                ("SQUiDRunner class", "class SQUiDRunner(SystemRunner):"),
                ("squid in AVAILABLE_SYSTEMS", '"squid"' in content and "AVAILABLE_SYSTEMS" in content),
                ("squid in _get_runner", 'system == "squid"' in content),
                ("squid dependencies", '"squid":' in content and "SYSTEM_DEPENDENCIES" in content),
            ]
            
            all_pass = True
            for check_name, check_expr in checks:
                if isinstance(check_expr, str):
                    if check_expr in content:
                        print(f"  ✓ {check_name}")
                    else:
                        print(f"  ✗ {check_name}")
                        all_pass = False
                else:
                    if check_expr:
                        print(f"  ✓ {check_name}")
                    else:
                        print(f"  ✗ {check_name}")
                        all_pass = False
            
            return all_pass
    else:
        print("✗ run_challenging_queries.py not found")
        return False

def check_squid_system():
    """Check if SQUiD system directory exists."""
    squid_path = PROJECT_ROOT / "systems" / "SQUiD"
    if squid_path.exists():
        print("✓ systems/SQUiD directory exists")
        
        required_files = [
            "squid.md",
            "requirements.txt",
            "src/database_generation.py",
            "src/utils.py",
            "src/model.py"
        ]
        
        all_present = True
        for req_file in required_files:
            file_path = squid_path / req_file
            if file_path.exists():
                print(f"  ✓ {req_file}")
            else:
                print(f"  ✗ {req_file} not found")
                all_present = False
        
        return all_present
    else:
        print("✗ systems/SQUiD directory not found")
        return False

def check_data_paths():
    """Check if ground truth data exists."""
    print("✓ Checking ground truth data paths:")
    
    data_paths = {
        "Med": ["disease.csv", "drug.csv", "institution.csv"],
        "Player": ["player.csv", "team.csv", "owner.csv", "city.csv"],
        "Art": ["Art.csv"],
        "Legal": ["Legal.csv"],
        "Finan": ["Finan.csv"],
    }
    
    all_present = True
    for dataset, entities in data_paths.items():
        dataset_path = PROJECT_ROOT / "Data" / dataset
        if dataset_path.exists():
            for entity_file in entities:
                file_path = dataset_path / entity_file
                if file_path.exists():
                    print(f"  ✓ Data/{dataset}/{entity_file}")
                else:
                    print(f"  ✗ Data/{dataset}/{entity_file} not found")
                    all_present = False
        else:
            print(f"  ✗ Data/{dataset} directory not found")
            all_present = False
    
    return all_present

def check_guide():
    """Check if integration guide exists."""
    guide_path = PROJECT_ROOT / "SQUID_INTEGRATION_GUIDE.md"
    if guide_path.exists():
        print("✓ SQUID_INTEGRATION_GUIDE.md exists")
        return True
    else:
        print("✗ SQUID_INTEGRATION_GUIDE.md not found")
        return False

def main():
    print("=" * 70)
    print("SQUiD System Integration Validation")
    print("=" * 70)
    print()
    
    results = {
        "preprocessing_script": check_preprocessing_script(),
        "runner_integration": check_runner_integration(),
        "squid_system": check_squid_system(),
        "data_paths": check_data_paths(),
        "integration_guide": check_guide(),
    }
    
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    
    for component, result in results.items():
        status = "✓" if result else "✗"
        print(f"{status} {component}: {'PASS' if result else 'FAIL'}")
    
    print()
    all_pass = all(results.values())
    
    if all_pass:
        print("=" * 70)
        print("✓ All checks passed! SQUiD integration is ready.")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Preprocess data: python preprocess_squid_data.py --dataset all")
        print("2. Run SQUiD queries: python run_challenging_queries.py --systems squid")
        print()
        print("For details, see: SQUID_INTEGRATION_GUIDE.md")
        return 0
    else:
        print("=" * 70)
        print("✗ Some checks failed. Please review the errors above.")
        print("=" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(main())



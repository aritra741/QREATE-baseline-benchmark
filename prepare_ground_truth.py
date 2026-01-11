"""
Ground Truth Preparation Script for Healthcare Join Query Evaluation

Following UDA-Bench Section 3.3 methodology:
"We hire a total of 30 graduate students to manually label these attributes, 
spending approximately 10,000 human hours."

For evaluation purposes, this shows the structure needed.
"""

import json
from pathlib import Path

# This demonstrates the expected ground truth structure
# for the 20 Healthcare join queries

GROUND_TRUTH_STRUCTURE = {
    # Query 1: binary_join (drug, disease)
    # SELECT disease.diagnostic_methods, drug.manufacturer, 
    #        drug.brand_name, disease.disease_name 
    # FROM drug JOIN disease ON drug.disease_name = disease.disease_name;
    
    "query_1": [
        {
            "disease_name": "Rheumatoid Arthritis",
            "diagnostic_methods": "clinical_evaluation || laboratory_test || imaging",
            "manufacturer": "Ajanta Pharma",
            "brand_name": "Super Kamagra"
        },
        {
            "disease_name": "Diabetes Mellitus",
            "diagnostic_methods": "laboratory_test || functional_test",
            "manufacturer": "Some Pharma Inc",
            "brand_name": "Drug Name"
        },
        # ... more joined tuples
    ],
    
    # Query 2: binary_join (drug, disease)
    "query_2": [
        {
            "disease_name": "Hypertension",
            "mechanism_of_action": "inhibits ACE enzyme",
            "storage_conditions": "store at room temperature",
            "diagnosis_challenges": "nonspecific symptoms",
        },
        # ... more tuples
    ],
    
    # ... Queries 3-20
}

QUERY_DESCRIPTIONS = {
    1: {
        "type": "Select+Join",
        "tables": ["drug", "disease"],
        "join_key": "disease_name",
        "select_columns": ["disease.diagnostic_methods", "drug.manufacturer", 
                          "drug.brand_name", "disease.disease_name"],
        "filters": None,
        "aggregation": None,
    },
    2: {
        "type": "Select+Join",
        "tables": ["drug", "disease"],
        "join_key": "disease_name",
        "select_columns": ["drug.mechanism_of_action", "drug.storage_conditions",
                          "disease.diagnosis_challenges", "disease.disease_name"],
    },
    3: {
        "type": "Select+Join",
        "tables": ["drug", "disease"],
        "join_key": "disease_name",
        "select_columns": ["drug.single_dose", "disease.pathogenesis",
                          "drug.recommended_usage", "disease.diagnosis_challenges"],
    },
    4: {
        "type": "Select+Join",
        "tables": ["disease", "drug"],
        "join_key": "disease_name",
        "select_columns": ["disease.treatments", "disease.epidemiology",
                          "drug.prescription_status", "drug.storage_conditions"],
    },
    5: {
        "type": "Select+Join",
        "tables": ["disease", "drug"],
        "join_key": "disease_name",
        "select_columns": ["disease.diagnostic_methods", "disease.preventive_measures",
                          "drug.mechanism_of_action", "drug.recommended_usage"],
    },
    6: {
        "type": "Select+Join",
        "tables": ["drug", "disease"],
        "join_key": "disease_name",
        "select_columns": ["drug.manufacturer", "disease.complications",
                          "drug.pharmaceutical_form", "disease.preventive_measures"],
    },
    7: {
        "type": "Select+Join",
        "tables": ["drug", "disease"],
        "join_key": "disease_name",
        "select_columns": ["drug.brand_name", "drug.unsuitable_population",
                          "disease.preventive_measures", "disease.diagnosis_challenges"],
    },
    8: {
        "type": "Select+Join",
        "tables": ["drug", "disease"],
        "join_key": "disease_name",
        "select_columns": ["drug.administration_route", "disease.pathogenesis",
                          "disease.etiology", "drug.mechanism_of_action"],
    },
    9: {
        "type": "Select+Join",
        "tables": ["disease", "drug"],
        "join_key": "disease_name",
        "select_columns": ["disease.epidemiology", "disease.sequelae",
                          "drug.indication", "drug.activation_conditions"],
    },
    10: {
        "type": "Select+Join",
        "tables": ["disease", "drug"],
        "join_key": "disease_name",
        "select_columns": ["disease.treatment_challenges", "disease.diagnostic_methods",
                          "drug.administration_route", "drug.generic_name"],
    },
    11: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
        "where": "disease.name = institution.research_diseases",
        "select_columns": ["disease.treatments", "institution.establishment_year",
                          "institution.parent_organization", "institution.number_of_staff",
                          "drug.unsuitable_population"],
    },
    12: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
    },
    13: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
    },
    14: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
    },
    15: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
    },
    16: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
    },
    17: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
    },
    18: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
    },
    19: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
    },
    20: {
        "type": "Select+Join+Aggregation",
        "tables": ["disease", "drug", "institution"],
        "join_key": "disease_name",
    },
}


def prepare_ground_truth_directory():
    """
    Create the ground_truth directory structure.
    
    This is a template - actual values would come from manual labeling.
    """
    output_dir = Path("ground_truth/Healthcare")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a template for each query
    for query_id in range(1, 21):
        template = {
            f"query_{query_id}": [
                # Template tuple - actual values would be manually labeled
                {
                    "note": "Template tuple - replace with actual labeled data",
                    "query_id": query_id,
                    "type": QUERY_DESCRIPTIONS[query_id]["type"],
                }
            ]
        }
        
        output_file = output_dir / f"query_{query_id}_gt.json"
        
        if not output_file.exists():
            with open(output_file, 'w') as f:
                json.dump(template, f, indent=2)
            print(f"Created {output_file}")
        else:
            print(f"Skipped {output_file} (already exists)")


def prepare_sample_ground_truth():
    """
    Create a small sample of ground truth with realistic structure.
    
    For documentation purposes.
    """
    sample = {
        "query_1": [
            {
                "disease_name": "Rheumatoid Arthritis",
                "diagnostic_methods": "clinical_evaluation || laboratory_test || imaging",
                "manufacturer": "Ajanta Pharma",
                "brand_name": "Sildenafil with Dapoxetine"
            },
            {
                "disease_name": "Type 2 Diabetes Mellitus",
                "diagnostic_methods": "laboratory_test",
                "manufacturer": "Novo Nordisk",
                "brand_name": "Ozempic"
            },
        ],
        "query_2": [
            {
                "disease_name": "Hypertension",
                "mechanism_of_action": "ACE inhibitor",
                "storage_conditions": "store at room temperature",
                "diagnosis_challenges": "Often asymptomatic until complications develop",
            },
            {
                "disease_name": "Chronic Obstructive Pulmonary Disease",
                "mechanism_of_action": "Beta-2 agonist",
                "storage_conditions": "avoid freezing",
                "diagnosis_challenges": "Similar symptoms to asthma",
            },
        ],
    }
    
    return sample


def validate_ground_truth_format():
    """
    Validate that ground truth files have correct structure for evaluation.
    """
    output_dir = Path("ground_truth/Healthcare")
    
    if not output_dir.exists():
        print(f"Ground truth directory {output_dir} does not exist")
        return False
    
    all_valid = True
    
    for query_id in range(1, 21):
        gt_file = output_dir / f"query_{query_id}_gt.json"
        
        if not gt_file.exists():
            print(f"Missing: {gt_file}")
            all_valid = False
            continue
        
        try:
            with open(gt_file) as f:
                data = json.load(f)
            
            # Check structure
            if not isinstance(data, dict):
                print(f"Invalid format in {gt_file}: expected dict")
                all_valid = False
                continue
            
            key = f"query_{query_id}"
            if key not in data:
                print(f"Missing key '{key}' in {gt_file}")
                all_valid = False
                continue
            
            tuples = data[key]
            if not isinstance(tuples, list):
                print(f"Invalid format in {gt_file}: tuples should be list")
                all_valid = False
                continue
            
            print(f"✓ {gt_file}: {len(tuples)} tuples")
        
        except json.JSONDecodeError as e:
            print(f"JSON error in {gt_file}: {e}")
            all_valid = False
        except Exception as e:
            print(f"Error reading {gt_file}: {e}")
            all_valid = False
    
    return all_valid


if __name__ == "__main__":
    import sys
    
    print("Ground Truth Preparation for Healthcare Join Queries\n")
    
    # Create directory structure
    print("Step 1: Creating directory structure...")
    prepare_ground_truth_directory()
    
    # Validate
    print("\nStep 2: Validating ground truth format...")
    valid = validate_ground_truth_format()
    
    if valid:
        print("\n✓ Ground truth directory is ready for evaluation")
    else:
        print("\n✗ Some issues found - see above")
    
    # Show sample structure
    print("\nSample ground truth structure:")
    print("="*60)
    sample = prepare_sample_ground_truth()
    for query_id, tuples in sample.items():
        print(f"\n{query_id}:")
        for tuple_data in tuples:
            print(f"  {tuple_data}")
    
    print("\n" + "="*60)
    print("\nNOTE: The ground_truth/Healthcare/query_*_gt.json files")
    print("contain template structures. Replace with actual manually")
    print("labeled tuples from the UDA-Bench dataset or your own labeling.")

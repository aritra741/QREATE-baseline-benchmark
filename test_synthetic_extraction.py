#!/usr/bin/env python3
"""
Synthetic test for GEM extraction - demonstrates the full pipeline with known data.
"""

import json
import logging
import sys
from pathlib import Path
import tempfile

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "systems"))

from GEM.blocking import SemanticBlocker
from GEM.resolver import EntityResolver
from GEM.db_engine import DBEngine
from GEM.ingest import InlineDeduplicator
from GEM.schema_loader import SchemaLoader
from GEM.llm import LLMClient
from GEM.extractor import EntityExtractor
from GEM.config import CACHE_DIR


def create_synthetic_documents():
    """Create synthetic test documents with known drug-disease relationships."""
    
    documents = {
        "drug_1.txt": """
Metformin is a first-line oral antidiabetic medication used to treat Type 2 Diabetes Mellitus.
Generic Name: Metformin
Brand Names: Glucophage, Fortamet
Disease: Type 2 Diabetes Mellitus
Mechanism: Metformin reduces hepatic glucose production and increases insulin sensitivity.
Side Effects: Gastrointestinal distress, lactic acidosis in rare cases
Manufacturer: Multiple generic manufacturers
""",
        "drug_2.txt": """
Lisinopril is an ACE inhibitor commonly prescribed for Hypertension management.
Generic Name: Lisinopril
Brand Names: Prinivil, Zestril
Disease Treated: Hypertension
Administration Route: Oral tablet
Mechanism of Action: Inhibits ACE enzyme, reducing angiotensin II formation
Side Effects: Cough, dizziness, hyperkalemia
""",
        "disease_1.txt": """
Type 2 Diabetes Mellitus is a metabolic disorder characterized by insulin resistance.
Disease Name: Type 2 Diabetes Mellitus
Alternative Names: Non-insulin-dependent diabetes, Type 2 DM
Pathogenesis: Insulin resistance in muscle and liver cells
Etiology: Obesity, sedentary lifestyle, genetic predisposition
Common Symptoms: Polyuria, polydipsia, fatigue, blurred vision
Complications: Retinopathy, nephropathy, neuropathy, cardiovascular disease
Treatments: Oral medications (Metformin, Sulfonylureas), insulin, lifestyle modification
Prognosis: Chronic condition, manageable with treatment
""",
        "disease_2.txt": """
Hypertension, also known as high blood pressure, is a major cardiovascular risk factor.
Disease Name: Hypertension
Alternate Names: High Blood Pressure, HTN
Pathogenesis: Increased peripheral vascular resistance
Etiology: Sodium intake, obesity, stress, genetics
Common Symptoms: Often asymptomatic, may cause headache, chest pain
Complications: Myocardial infarction, stroke, kidney disease, heart failure
Treatments: ACE inhibitors, beta-blockers, diuretics, lifestyle changes
Diagnostic Methods: Blood pressure measurement, ambulatory BP monitoring
Prognosis: Chronic condition requiring long-term management
""",
        "institution_1.txt": """
The Diabetes Research Institute focuses on understanding and treating Type 2 Diabetes Mellitus.
Institution Name: Diabetes Research Institute
Institution Type: University-affiliated research center
Institution Country: United States
Institution City: Miami, Florida
Research Diseases: Type 2 Diabetes Mellitus, Type 1 Diabetes, Gestational Diabetes
Key Technologies: Islet transplantation, beta cell regeneration
Key Achievements: First successful insulin-producing cell transplant
""",
        "institution_2.txt": """
The Cardiovascular Health Center conducts research on Hypertension and heart disease.
Institution Name: Cardiovascular Health Center
Institution Type: Public research institute
Institution Country: United States
Institution City: Boston, Massachusetts
Research Diseases: Hypertension, Coronary Artery Disease, Heart Failure
Key Technologies: Advanced imaging, genetic screening
Key Achievements: Discovery of novel hypertension biomarkers
"""
    }
    
    return documents


def test_synthetic_extraction():
    """Test extraction on synthetic documents."""
    print("=" * 100)
    print("SYNTHETIC TEST: GEM Extraction Pipeline")
    print("=" * 100)
    print()
    
    # Create temporary directory with synthetic documents
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Write synthetic documents
        docs = create_synthetic_documents()
        for filename, content in docs.items():
            (tmpdir / filename).write_text(content)
        
        print("Created synthetic documents:")
        for filename in docs.keys():
            print(f"  - {filename}")
        print()
        
        # Initialize extractor
        extractor = EntityExtractor()
        
        # Extract entities
        print("=" * 100)
        print("EXTRACTION RESULTS")
        print("=" * 100)
        print()
        
        # Extract drugs
        drug_file = tmpdir / "drug_1.txt"
        drugs = extractor.extract_from_file(drug_file, "drug")
        print(f"[DRUGS] Extracted {len(drugs)} drug entities:")
        for i, drug in enumerate(drugs, 1):
            print(f"  Drug {i}:")
            for k, v in drug.items():
                if v:
                    print(f"    {k}: {v}")
        print()
        
        # Extract diseases
        disease_file = tmpdir / "disease_1.txt"
        diseases = extractor.extract_from_file(disease_file, "disease")
        print(f"[DISEASES] Extracted {len(diseases)} disease entities:")
        for i, disease in enumerate(diseases, 1):
            print(f"  Disease {i}:")
            for k, v in disease.items():
                if v:
                    print(f"    {k}: {v}")
        print()
        
        # Extract institutions
        inst_file = tmpdir / "institution_1.txt"
        institutions = extractor.extract_from_file(inst_file, "institution")
        print(f"[INSTITUTIONS] Extracted {len(institutions)} institution entities:")
        for i, inst in enumerate(institutions, 1):
            print(f"  Institution {i}:")
            for k, v in inst.items():
                if v:
                    print(f"    {k}: {v}")
        print()
        
        # Check if drug disease_name matches disease disease_name
        print("=" * 100)
        print("SEMANTIC MATCHING CHECK")
        print("=" * 100)
        print()
        
        if drugs and diseases:
            drug_disease = drugs[0].get("disease_name", "")
            disease_name = diseases[0].get("disease_name", "")
            
            print(f"Drug mentions disease: '{drug_disease}'")
            print(f"Disease name in DB: '{disease_name}'")
            print()
            
            if drug_disease and disease_name:
                if drug_disease.lower() == disease_name.lower():
                    print("✓ MATCH: Drug and disease names match!")
                else:
                    print("✗ NO MATCH: Names don't match exactly")
                    print(f"  Need semantic similarity matching or normalization")
        print()


if __name__ == "__main__":
    try:
        test_synthetic_extraction()
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)

#!/usr/bin/env python3
"""
Realistic test for GEM extraction - uses messy, unstructured healthcare documents.
"""

import logging
import sys
from pathlib import Path
import tempfile

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "systems"))

from GEM.extractor import EntityExtractor


def create_realistic_documents():
    """Create realistic messy test documents similar to actual healthcare data."""
    
    documents = {
        "drug_realistic_1.txt": """
Metformin is one of the most commonly prescribed medications for managing Type 2 Diabetes Mellitus. 
Also known by brand names such as Glucophage, Fortamet, and Riomet, this medication has been a 
cornerstone of diabetes treatment for decades.

The drug works by reducing the amount of glucose your liver produces and improves how your body 
uses insulin. It's typically prescribed as an oral tablet and comes in various strengths. Many 
patients report gastrointestinal side effects initially, though these often subside over time. 
Lactic acidosis is a rare but serious side effect that occurs primarily in patients with kidney 
problems.

Metformin is manufactured by multiple pharmaceutical companies globally. The generic versions are 
widely available and affordable. Patients should take this medication exactly as prescribed by their 
physician. Common dosages range from 500mg to 2000mg daily, usually split into two or three doses.

Some people experience vitamin B12 deficiency with long-term use, so periodic monitoring is recommended.
""",
        "disease_realistic_1.txt": """
Type 2 Diabetes Mellitus represents one of the most prevalent metabolic disorders in the world today.
This chronic condition develops when the body becomes resistant to insulin or doesn't produce enough 
of it to maintain normal glucose levels.

The pathophysiology involves complex interactions between genetic factors and environmental triggers.
Common symptoms include increased thirst, frequent urination, unexplained weight loss, and chronic fatigue.
Some patients remain asymptomatic for years before diagnosis.

Complications of uncontrolled Type 2 Diabetes Mellitus include diabetic retinopathy (eye damage), 
nephropathy (kidney disease), neuropathy (nerve damage), and significantly increased risk of 
cardiovascular disease and stroke. The prognosis is generally good with proper management and lifestyle 
modifications, though it remains a chronic condition requiring lifelong attention.

Treatment approaches include oral medications like Metformin as first-line therapy, combined with 
dietary changes, regular exercise, and weight loss. More severe cases may require insulin therapy.
Preventive measures include maintaining healthy weight, regular physical activity, and dietary management 
of carbohydrates and sodium intake.
""",
        "institution_realistic_1.txt": """
The National Institute of Diabetes and Digestive and Kidney Diseases (NIDDK) is a premier research 
organization dedicated to understanding and treating metabolic disorders. Located in Bethesda, Maryland, 
it serves as a major hub for diabetes research in the United States.

The institution conducts groundbreaking research on Type 2 Diabetes Mellitus and related conditions. 
Key research areas include beta cell function, insulin resistance mechanisms, and novel therapeutic 
approaches. The center employs cutting-edge technologies including genomic sequencing, metabolic imaging, 
and advanced biomarker analysis.

Notable achievements include the identification of genetic markers for diabetes susceptibility and 
the development of several treatment guidelines now used worldwide. The NIDDK collaborates with 
international research institutions and receives substantial government funding for its research initiatives.

Staff includes hundreds of researchers, clinicians, and support personnel working toward better 
understanding and treatment of Type 2 Diabetes Mellitus and related kidney diseases.
"""
    }
    
    return documents


def test_realistic_extraction():
    """Test extraction on realistic messy documents."""
    print("=" * 100)
    print("REALISTIC TEST: GEM Extraction from Messy Healthcare Documents")
    print("=" * 100)
    print()
    
    # Create temporary directory with realistic documents
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Write realistic documents
        docs = create_realistic_documents()
        for filename, content in docs.items():
            (tmpdir / filename).write_text(content)
        
        print("Created realistic messy healthcare documents:")
        for filename, content in docs.items():
            print(f"  - {filename} ({len(content)} chars)")
        print()
        
        # Initialize extractor
        extractor = EntityExtractor()
        
        # Extract entities
        print("=" * 100)
        print("EXTRACTION RESULTS")
        print("=" * 100)
        print()
        
        # Extract drugs
        drug_file = tmpdir / "drug_realistic_1.txt"
        drugs = extractor.extract_from_file(drug_file, "drug")
        print(f"[DRUGS] Extracted {len(drugs)} drug entities from messy text:")
        if drugs:
            for i, drug in enumerate(drugs, 1):
                print(f"\n  Drug {i}:")
                for k, v in sorted(drug.items()):
                    if v:  # Only print non-empty fields
                        print(f"    {k}: {v}")
        else:
            print("  No drugs extracted")
        print()
        
        # Extract diseases
        disease_file = tmpdir / "disease_realistic_1.txt"
        diseases = extractor.extract_from_file(disease_file, "disease")
        print(f"[DISEASES] Extracted {len(diseases)} disease entities from messy text:")
        if diseases:
            for i, disease in enumerate(diseases, 1):
                print(f"\n  Disease {i}:")
                for k, v in sorted(disease.items()):
                    if v:  # Only print non-empty fields
                        print(f"    {k}: {v}")
        else:
            print("  No diseases extracted")
        print()
        
        # Extract institutions
        inst_file = tmpdir / "institution_realistic_1.txt"
        institutions = extractor.extract_from_file(inst_file, "institution")
        print(f"[INSTITUTIONS] Extracted {len(institutions)} institution entities from messy text:")
        if institutions:
            for i, inst in enumerate(institutions, 1):
                print(f"\n  Institution {i}:")
                for k, v in sorted(inst.items()):
                    if v:  # Only print non-empty fields
                        print(f"    {k}: {v}")
        else:
            print("  No institutions extracted")
        print()
        
        # Check semantic matching
        print("=" * 100)
        print("SEMANTIC MATCHING CHECK")
        print("=" * 100)
        print()
        
        if drugs and diseases:
            drug_diseases = [d.get("disease_name", "") for d in drugs if d.get("disease_name")]
            disease_names = [d.get("disease_name", "") for d in diseases if d.get("disease_name")]
            
            print(f"Drug mentions these diseases:")
            for disease in drug_diseases:
                print(f"  - '{disease}'")
            print()
            
            print(f"Disease table contains:")
            for disease in disease_names:
                print(f"  - '{disease}'")
            print()
            
            # Check for matches (case-insensitive partial match)
            matches = []
            for drug_disease in drug_diseases:
                for disease_name in disease_names:
                    if drug_disease.lower() in disease_name.lower() or disease_name.lower() in drug_disease.lower():
                        matches.append((drug_disease, disease_name))
                        print(f"✓ MATCH: '{drug_disease}' <-> '{disease_name}'")
            
            if not matches:
                print("✗ NO SEMANTIC MATCHES FOUND")
                print("  This explains why JOIN queries return 0 rows")
        else:
            print("Could not perform matching - missing data")
        print()


if __name__ == "__main__":
    try:
        test_realistic_extraction()
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)

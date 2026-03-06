#!/usr/bin/env python
"""
Test QUEST evidence sampling across different datasets.

This is a focused experiment to identify which datasets QUEST can successfully sample evidence from.
Instead of running full queries, we just test the sampling phase.

Usage:
    python test_quest_evidence_sampling.py --dataset Med
    python test_quest_evidence_sampling.py --dataset Player
    python test_quest_evidence_sampling.py --datasets all
"""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple

# Add project paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

# Check for required dependencies
try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas is required. Install with: pip install pandas")
    sys.exit(1)

from evaluation.logging_utils import setup_logger
from evaluation.config import load_json, dump_json

# Dataset configuration
DATASETS = {
    "Med": {
        "entities": ["disease", "drug", "institution"],
        "attr_file": "Query/Med/Med_attributes.json",
        "csv_files": {
            "disease": "Data/Med/disease.csv",
            "drug": "Data/Med/drug.csv", 
            "institution": "Data/Med/institution.csv",
        }
    },
    "Player": {
        "entities": ["player", "team", "owner", "city"],
        "attr_file": "Query/Player/Player_attributes.json",
        "csv_files": {
            "player": "Data/Player/player.csv",
            "team": "Data/Player/team.csv",
            "owner": "Data/Player/owner.csv",
            "city": "Data/Player/city.csv",
        }
    },
    "Art": {
        "entities": ["art"],
        "attr_file": "Query/Art/Art_attributes.json",
        "csv_files": {
            "art": "Data/Art/Art.csv",
        }
    },
    "Legal": {
        "entities": ["legal_case"],
        "attr_file": "Query/Legal/Legal_attributes.json",
        "csv_files": {
            "legal_case": "Data/Legal/Legal.csv",
        }
    },
    "Finan": {
        "entities": ["finance"],
        "attr_file": "Query/Finan/Finan_attributes.json",
        "csv_files": {
            "finance": "Data/Finan/Finan.csv",
        }
    }
}


class QuestSamplingTester:
    """Test QUEST's evidence sampling on different datasets."""
    
    def __init__(self, output_dir: Path = None):
        self.project_root = PROJECT_ROOT
        self.output_dir = output_dir or PROJECT_ROOT / "results" / "sampling_tests"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = setup_logger(
            "sampling_test",
            level="INFO",
            log_file=self.output_dir / f"sampling_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        
        self._initialized = False
        self.logger.info(f"Sampling test initialized, output: {self.output_dir}")
    
    def _ensure_init(self):
        """Initialize QUEST modules."""
        if self._initialized:
            return
        
        try:
            from quest.db.indexer.indexer import load_all_indexer
            from quest.core.llm.sampler import AttrSampler
            from quest.core.llm.llm_query import TextLLMQuerier
            
            self.load_all_indexer = load_all_indexer
            self.AttrSampler = AttrSampler
            self.TextLLMQuerier = TextLLMQuerier
            self._initialized = True
            self.logger.info("[QUEST] Modules loaded successfully")
        except ImportError as e:
            self.logger.error(f"[QUEST] Failed to import: {e}")
            raise
    
    def load_attributes(self, dataset: str) -> Optional[Dict]:
        """Load attribute definitions for a dataset."""
        attr_path = self.project_root / DATASETS[dataset]["attr_file"]
        if attr_path.exists():
            return load_json(attr_path)
        return None
    
    def load_csv_data(self, dataset: str, entity: str) -> Optional[pd.DataFrame]:
        """Load CSV data for an entity."""
        csv_path = self.project_root / DATASETS[dataset]["csv_files"][entity]
        if csv_path.exists():
            return pd.read_csv(csv_path)
        return None
    
    def test_sampling(self, dataset: str, entity: str, max_docs: int = 10, timeout_sec: int = 120) -> Dict:
        """Test sampling for a single dataset/entity on a subset of documents.
        
        Args:
            dataset: Dataset name
            entity: Entity name
            max_docs: Maximum number of documents to sample from (default: 10)
            timeout_sec: Timeout in seconds for sampling (default: 120)
        """
        self._ensure_init()
        
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info(f"Testing QUEST sampling: {dataset}/{entity}")
        self.logger.info(f"(max {max_docs} docs, {timeout_sec}s timeout)")
        self.logger.info("=" * 70)
        
        result = {
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat(),
            "status": "pending",
            "max_docs_tested": max_docs
        }
        
        try:
            # Load attributes
            attributes = self.load_attributes(dataset)
            if not attributes:
                self.logger.error(f"No attributes file found for {dataset}")
                result["status"] = "failed"
                result["error"] = f"No attributes file for {dataset}"
                return result
            
            # Get entity attributes
            entity_attrs = None
            for key in attributes:
                if key.lower() == entity.lower():
                    entity_attrs = attributes[key]
                    break
            
            if entity_attrs is None:
                self.logger.error(f"No attributes found for entity {entity}")
                result["status"] = "failed"
                result["error"] = f"No attributes for {entity}"
                return result
            
            self.logger.info(f"Found {len(entity_attrs)} attributes for {entity}")
            
            # Build schema prompt (use all attributes)
            attr_lines = []
            for attr_name, attr_info in entity_attrs.items():
                description = attr_info.get("description", "") if isinstance(attr_info, dict) else ""
                attr_lines.append(f"{attr_name}: {description}")
            prompt_str = "\n".join(attr_lines)
            
            self.logger.info(f"Schema built with {len(attr_lines)} attributes:")
            for line in attr_lines[:3]:
                self.logger.info(f"  - {line[:75]}...")
            if len(attr_lines) > 3:
                self.logger.info(f"  ... ({len(attr_lines) - 3} more)")
            
            # Try loading indexer
            self.logger.info("Loading QUEST indexer...")
            try:
                gb_indexer = self.load_all_indexer(table_to_type=None)
                self.logger.info(f"Indexer loaded. Available tables: {list(gb_indexer.table_to_indexer.keys())}")
                
                # Check if entity is in indexer
                if entity not in gb_indexer.table_to_indexer:
                    self.logger.warning(f"Entity '{entity}' not found in indexer!")
                    self.logger.warning(f"Available tables: {list(gb_indexer.table_to_indexer.keys())}")
                    result["status"] = "index_missing"
                    result["error"] = f"Entity not found in index"
                    return result
                
                # Get indexer for entity
                indexer_obj, _ = gb_indexer.get_indexer(entity)
                doc_ids = indexer_obj.get_docs_id()
                total_docs = len(doc_ids)
                self.logger.info(f"Index has {total_docs} documents total")
                
                # Limit to max_docs
                docs_to_test = min(max_docs, total_docs)
                self.logger.info(f"Testing on {docs_to_test} documents (first {docs_to_test} of {total_docs})")
                
            except FileNotFoundError as e:
                self.logger.error(f"Index not found: {e}")
                result["status"] = "index_missing"
                result["error"] = str(e)
                return result
            
            # Initialize sampler and querier
            self.logger.info("Initializing sampler and querier...")
            gb_sampler = self.AttrSampler(schema=prompt_str)
            gb_querier = self.TextLLMQuerier(prompt=prompt_str)
            
            # Try sampling with timeout
            self.logger.info(f"Starting sampling (will timeout after {timeout_sec}s)...")
            
            start_time = datetime.now()
            try:
                # Use try_sample (standard sampling, not exhaustive)
                # This should be much faster than try_sample_all_docs
                gb_sampler.try_sample(indexer_obj, prompt_str)
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info(f"Sampling completed in {elapsed:.1f} seconds")
                
                # Check if we timed out
                if elapsed > timeout_sec:
                    self.logger.warning(f"Sampling exceeded timeout ({elapsed:.1f}s > {timeout_sec}s)")
                    result["timed_out"] = True
                
            except Exception as e:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.error(f"Sampling failed after {elapsed:.1f}s: {e}")
                # Don't return - try to analyze what we got
                if elapsed > timeout_sec:
                    result["timed_out"] = True
            
            # Analyze results
            self.logger.info("")
            self.logger.info("=" * 70)
            self.logger.info("SAMPLING RESULTS")
            self.logger.info("=" * 70)
            
            result["attributes_collected"] = len(gb_sampler.map_attr_evidence)
            result["evidence_details"] = {}
            
            success_count = 0
            for attr, evidence in gb_sampler.map_attr_evidence.items():
                if evidence:
                    success_count += 1
                    evidence_len = len(evidence) if isinstance(evidence, str) else len(str(evidence))
                    result["evidence_details"][attr] = {
                        "found": True,
                        "evidence_length": evidence_len,
                        "evidence_preview": str(evidence)[:150]
                    }
                    self.logger.info(f"✓ {attr}: {evidence_len} chars")
                else:
                    result["evidence_details"][attr] = {
                        "found": False,
                        "evidence_length": 0
                    }
                    self.logger.warning(f"✗ {attr}: NO EVIDENCE")
            
            # Load CSV to compare
            csv_data = self.load_csv_data(dataset, entity)
            if csv_data is not None:
                result["csv_rows"] = len(csv_data)
                result["csv_columns"] = len(csv_data.columns)
                self.logger.info(f"\nCSV reference: {len(csv_data)} rows, {len(csv_data.columns)} columns")
            
            # Summary
            success_rate = (success_count / len(gb_sampler.map_attr_evidence) * 100) if gb_sampler.map_attr_evidence else 0
            self.logger.info("")
            self.logger.info(f"SUCCESS RATE: {success_count}/{len(gb_sampler.map_attr_evidence)} attributes ({success_rate:.1f}%)")
            
            result["status"] = "completed"
            result["attributes_found"] = success_count
            result["attributes_total"] = len(gb_sampler.map_attr_evidence)
            result["success_rate"] = success_rate
            
        except Exception as e:
            self.logger.error(f"Test failed: {e}")
            self.logger.error(f"Traceback:\n{traceback.format_exc()}")
            result["status"] = "failed"
            result["error"] = str(e)
        
        return result
    
    def run_all(self, datasets: list = None, max_docs: int = 10, timeout_sec: int = 120):
        """Run sampling tests on all datasets.
        
        Args:
            datasets: List of datasets to test
            max_docs: Maximum documents per entity
            timeout_sec: Timeout in seconds per entity
        """
        if datasets is None:
            datasets = list(DATASETS.keys())
        elif datasets == ["all"]:
            datasets = list(DATASETS.keys())
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "max_docs": max_docs,
                "timeout_sec": timeout_sec
            },
            "datasets": {}
        }
        
        for dataset in datasets:
            if dataset not in DATASETS:
                self.logger.error(f"Unknown dataset: {dataset}")
                continue
            
            self.logger.info("")
            self.logger.info("#" * 70)
            self.logger.info(f"# DATASET: {dataset}")
            self.logger.info("#" * 70)
            
            dataset_results = {}
            for entity in DATASETS[dataset]["entities"]:
                entity_result = self.test_sampling(dataset, entity, max_docs=max_docs, timeout_sec=timeout_sec)
                dataset_results[entity] = entity_result
            
            results["datasets"][dataset] = dataset_results
        
        # Save results
        results_file = self.output_dir / f"sampling_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        dump_json(results, results_file)
        self.logger.info(f"\nResults saved to {results_file}")
        
        # Print summary
        self._print_summary(results)
        
        return results
    
    def _print_summary(self, results: Dict):
        """Print a summary of all results."""
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("OVERALL SUMMARY")
        self.logger.info("=" * 70)
        
        for dataset, entities in results["datasets"].items():
            self.logger.info(f"\n{dataset}:")
            for entity, result in entities.items():
                status = result.get("status", "unknown")
                if status == "completed":
                    rate = result.get("success_rate", 0)
                    self.logger.info(f"  {entity}: SUCCESS - {rate:.0f}% attributes found")
                else:
                    error = result.get("error", "unknown error")
                    self.logger.info(f"  {entity}: {status.upper()} - {error}")


def main():
    parser = argparse.ArgumentParser(
        description="Test QUEST evidence sampling across datasets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test single dataset
  python test_quest_evidence_sampling.py --dataset Med
  
  # Test all datasets
  python test_quest_evidence_sampling.py --datasets all
  
  # Test specific datasets
  python test_quest_evidence_sampling.py --datasets Med Player Art
        """
    )
    
    parser.add_argument(
        "--dataset",
        type=str,
        help="Single dataset to test"
    )
    
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=list(DATASETS.keys()) + ["all"],
        help="Datasets to test (default: all)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for results"
    )
    
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local indexes instead of scratch"
    )
    
    parser.add_argument(
        "--max-docs",
        type=int,
        default=10,
        help="Maximum documents to test per entity (default: 10)"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds per entity (default: 120)"
    )
    
    args = parser.parse_args()
    
    # Handle --dataset vs --datasets
    if args.dataset:
        datasets = [args.dataset]
    elif args.datasets:
        datasets = args.datasets
    else:
        datasets = ["all"]
    
    # Set local index path if needed
    if args.local:
        os.environ["QUEST_INDEX_ROOT"] = str(PROJECT_ROOT.parent)
        print(f"Using local indexes at: {PROJECT_ROOT}/index")
    
    # Run tests
    tester = QuestSamplingTester(output_dir=args.output_dir)
    results = tester.run_all(datasets, max_docs=args.max_docs, timeout_sec=args.timeout)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


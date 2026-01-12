"""
Healthcare Dataset Evaluation System for DocETL
Following the UDA-Bench paper's evaluation methodology exactly.

Key metrics tracked:
1. Accuracy: Precision, Recall, F1-score
2. Cost: Average tokens (in thousands) per document per query
3. Latency: Mean execution time in seconds per document per query
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HealthcareEvaluationSystem:
    """
    Implements evaluation system matching UDA-Bench paper Section 4.1
    """
    
    def __init__(self, 
                 data_dir: str = "source_data/Healthcare",
                 attributes_file: str = "Query/Med/Med_attributes.json",
                 queries_file: str = "Query/Med/Join/join_queries.sql",
                 ground_truth_dir: str = "ground_truth/Healthcare"):
        """
        Initialize evaluation system.
        
        Args:
            data_dir: Path to Healthcare source documents
            attributes_file: Path to Med_attributes.json defining schema
            queries_file: Path to join_queries.sql
            ground_truth_dir: Path to ground truth labels
        """
        self.data_dir = Path(data_dir)
        self.attributes_file = Path(attributes_file)
        self.queries_file = Path(queries_file)
        self.ground_truth_dir = Path(ground_truth_dir)
        
        # Load attributes schema
        with open(self.attributes_file) as f:
            self.attributes = json.load(f)
        
        # Document categories in Healthcare (from uda-new.md Section 3.2)
        # Note: directory is named "institutes_small" but internally we call it "institution"
        self.categories = ["disease", "drug", "institution"]
        self.dir_mapping = {  # Map internal names to directory names
            "disease": "disease_small",
            "drug": "drug_small", 
            "institution": "institutes_small"
        }
        
        # Load documents by category
        self.documents = self._load_documents()
        
        # Load ground truth
        self.ground_truth = self._load_ground_truth()
        
        # Metrics storage
        self.results = {
            "queries": {},  # query_id -> results
            "summary": {
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "cost_per_doc": 0.0,  # tokens in thousands
                "latency_per_doc": 0.0,  # seconds
            }
        }
    
    def _load_documents(self) -> Dict[str, List[Dict]]:
        """Load healthcare documents by category."""
        docs = {}
        for category in self.categories:
            dir_name = self.dir_mapping.get(category, f"{category}_small")
            category_path = self.data_dir / dir_name
            docs[category] = []
            
            if category_path.exists():
                for file_path in sorted(category_path.glob("*")):
                    if file_path.is_file():
                        doc = {
                            "id": file_path.stem,
                            "filename": file_path.name,
                            "category": category,
                            "path": str(file_path),
                        }
                        # Load content - handle different formats
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                doc["content"] = f.read()
                        except:
                            logger.warning(f"Could not read {file_path}")
                            continue
                        
                        docs[category].append(doc)
                        logger.info(f"Loaded {category} doc: {doc['id']}")
            
            logger.info(f"Total {category} documents: {len(docs[category])}")
        
        return docs
    
    def _load_ground_truth(self) -> Dict[str, Any]:
        """
        Load ground truth from CSV files.
        """
        import csv
        
        ground_truth = {"disease": {}, "drug": {}, "institution": {}}
        
        # Load disease ground truth
        disease_csv = Path("Data/Med/disease.csv")
        if disease_csv.exists():
            with open(disease_csv) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    doc_id = row.get("ID", "")
                    if doc_id:
                        ground_truth["disease"][doc_id] = row
        
        # Load drug ground truth
        drug_csv = Path("Data/Med/drug.csv")
        if drug_csv.exists():
            with open(drug_csv) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    doc_id = row.get("ID", "")
                    if doc_id:
                        ground_truth["drug"][doc_id] = row
        
        logger.info(f"Loaded {len(ground_truth['disease'])} disease GT entries")
        logger.info(f"Loaded {len(ground_truth['drug'])} drug GT entries")
        
        return ground_truth
    
    def execute_query(self, query_id: int, query_sql: str) -> Tuple[Dict, float, float]:
        """
        Execute a single query using DocETL and measure metrics.
        
        Returns:
            (results_dict with accuracy metrics, cost_tokens, latency_seconds)
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Executing Query {query_id}")
        logger.info(f"SQL: {query_sql[:100]}...")
        logger.info(f"{'='*60}")
        
        start_time = time.time()
        
        # Parse query to understand what it's doing
        query_type = self._parse_query_type(query_sql)
        logger.info(f"Query type: {query_type}")
        
        # Execute query with DocETL
        extracted_results = self._execute_with_docetl(query_sql)
        
        latency = time.time() - start_time
        
        # Estimate cost (tokens used)
        cost = self._estimate_cost(extracted_results)
        
        # Add accuracy metrics based on query type
        if "Join" in query_type:
            extracted_results = self._evaluate_accuracy_for_tuples(query_id, extracted_results, query_sql)
        else:
            # For filter/extract-only queries, evaluate attribute extraction accuracy
            extracted_results = self._evaluate_filter_query_accuracy(query_id, extracted_results, query_sql)
        
        return extracted_results, cost, latency
    
    def _evaluate_accuracy_for_tuples(self, query_id: int, results: Dict, query_sql: str) -> Dict:
        """
        Evaluate accuracy (Precision, Recall, F1) for extracted join tuples.
        Compares extracted tuples against ground truth tuples using semantic matching.
        """
        extracted_tuples = results.get("tuples", [])
        
        # Get ground truth tuples for this query (generated from CSVs)
        gt_tuples = self._get_ground_truth_tuples_for_query(query_id, query_sql)
        
        logger.info(f"Evaluating {len(extracted_tuples)} extracted tuples against {len(gt_tuples)} GT tuples")
        
        # Semantic matching: for each extracted tuple, find matches in GT
        matched_extracted = []
        matched_gt = set()
        
        for ext_tuple in extracted_tuples:
            for gt_idx, gt_tuple in enumerate(gt_tuples):
                if self._tuple_matches_semantically(ext_tuple, gt_tuple):
                    matched_extracted.append(ext_tuple)
                    matched_gt.add(gt_idx)
                    break
        
        # Calculate metrics
        precision = len(matched_extracted) / len(extracted_tuples) if extracted_tuples else 0.0
        recall = len(matched_gt) / len(gt_tuples) if gt_tuples else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        logger.info(f"Accuracy: P={precision:.3f}, R={recall:.3f}, F1={f1:.3f} ({len(matched_gt)}/{len(gt_tuples)} GT tuples matched)")
        
        results["precision"] = precision
        results["recall"] = recall
        results["f1"] = f1
        results["matched_pairs"] = len(matched_gt)
        results["extracted_pairs_count"] = len(extracted_tuples)
        results["gt_pairs_count"] = len(gt_tuples)
        
        return results
    
    def _get_ground_truth_tuples_for_query(self, query_id: int, query_sql: str) -> List[Dict]:
        """
        Generate ground truth tuples for a join query by selecting from CSVs.
        """
        # Parse the SELECT clause to get the attributes being queried
        from docetl_query_executor import DocETLHealthcareQueryExecutor
        executor = DocETLHealthcareQueryExecutor(attributes_file=str(self.attributes_file))
        parsed = executor._parse_sql_query(query_sql)
        select_attributes = parsed.get("select_attributes", [])
        
        # For join queries, we need to generate tuples by matching disease names
        gt_tuples = []
        
        # Get disease ground truth
        disease_gt = self.ground_truth.get("disease", {})
        drug_gt = self.ground_truth.get("drug", {})
        
        # For each disease, find matching drugs and create result tuples
        for dis_id, dis_row in disease_gt.items():
            disease_name = dis_row.get("disease_name", "").strip()
            if not disease_name:
                continue
            
            # Find drugs that treat this disease
            for drug_id, drug_row in drug_gt.items():
                drug_diseases = drug_row.get("disease_name", "").strip()
                if not drug_diseases:
                    continue
                
                # Check if this disease is in the drug's disease list
                diseases_match = False
                for disease in drug_diseases.split("||"):
                    if disease.strip().lower() == disease_name.lower():
                        diseases_match = True
                        break
                
                if diseases_match:
                    # Create a ground truth tuple with the selected attributes
                    gt_tuple = {}
                    for attr in select_attributes:
                        attr_clean = attr.strip()
                        if "disease." in attr_clean:
                            field = attr_clean.replace("disease.", "")
                            gt_tuple[attr_clean] = dis_row.get(field, "Not found")
                        elif "drug." in attr_clean:
                            field = attr_clean.replace("drug.", "")
                            gt_tuple[attr_clean] = drug_row.get(field, "Not found")
                    
                    gt_tuples.append(gt_tuple)
        
        return gt_tuples
    
    def _tuple_matches_semantically(self, extracted: Dict, ground_truth: Dict) -> bool:
        """
        Check if extracted tuple matches ground truth tuple semantically.
        Uses fuzzy matching for text values.
        
        Key insight: If GT has empty/missing value, we don't require exact match.
        We only check attributes where GT has actual content.
        """
        # For all keys in ground truth, check if extracted values match
        for key, gt_value in ground_truth.items():
            ext_value = extracted.get(key, "Not found")
            
            # Normalize values
            ext_norm = self._normalize_value(ext_value) if ext_value else ""
            gt_norm = self._normalize_value(gt_value) if gt_value else ""
            
            # If GT is empty, skip this attribute (it's not informative)
            if not gt_norm:
                continue
            
            # If GT has a value but extracted is "not found", it's a mismatch
            if gt_norm and ext_norm == "not found":
                return False
            
            # Check for semantic match on non-empty GT values
            if gt_norm and not self._values_match(ext_norm, gt_norm):
                return False
        
        return True
    
    def _evaluate_filter_query_accuracy(self, query_id: int, results: Dict, query_sql: str) -> Dict:
        """
        For filter queries (extract+filter only), evaluate extracted records against ground truth.
        """
        extracted_tuples = results.get("tuples", [])
        
        # Determine which table this query is on
        query_upper = query_sql.upper()
        if "FROM DISEASE" in query_upper:
            table = "disease"
            gt_records = self.ground_truth.get("disease", {})
        elif "FROM DRUG" in query_upper:
            table = "drug"
            gt_records = self.ground_truth.get("drug", {})
        else:
            logger.warning(f"Could not determine table from query: {query_sql}")
            results["precision"] = 0.0
            results["recall"] = 0.0
            results["f1"] = 0.0
            return results
        
        if not gt_records:
            logger.warning(f"No ground truth records for {table}")
            results["precision"] = 0.0
            results["recall"] = 0.0
            results["f1"] = 0.0
            return results
        
        # Check if extracted records match GT records
        correct_tuples = 0
        for ext_tuple in extracted_tuples:
            for gt_record in gt_records.values():
                if self._tuple_matches_gt_record(ext_tuple, gt_record):
                    correct_tuples += 1
                    break
        
        precision = correct_tuples / len(extracted_tuples) if extracted_tuples else 0.0
        recall = correct_tuples / len(gt_records) if gt_records else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        results["precision"] = precision
        results["recall"] = recall
        results["f1"] = f1
        
        logger.info(f"Filter accuracy: P={precision:.3f}, R={recall:.3f}, F1={f1:.3f} ({correct_tuples}/{len(extracted_tuples)} correct)")
        
        return results
    
    def _tuple_matches_gt_record(self, extracted_tuple: Dict, gt_record: Dict) -> bool:
        """Check if an extracted tuple matches a ground truth record."""
        # Check if all extracted attributes match GT values
        for key, ext_value in extracted_tuple.items():
            gt_value = gt_record.get(key)
            if not self._values_match(ext_value, gt_value):
                return False
        return True
    
    def _normalize_value(self, val: str) -> str:
        """Normalize a value for comparison."""
        if not val:
            return ""
        return str(val).strip().lower()
    
    def _values_match(self, val1: str, val2: str) -> bool:
        """Check if two values match using the official UDA-Bench logic."""
        # Normalize values
        norm1 = self._normalize_value(val1) if val1 else ""
        norm2 = self._normalize_value(val2) if val2 else ""
        
        # Both empty
        if not norm1 or not norm2:
            return norm1 == norm2
        
        # Exact match after normalization
        if norm1 == norm2:
            return True
        
        # Split by || and try cross-matching (for multi-value fields)
        values1 = [v.strip() for v in norm1.split('||') if v.strip()]
        values2 = [v.strip() for v in norm2.split('||') if v.strip()]
        
        for v1 in values1:
            for v2 in values2:
                # Exact match
                if v1 == v2:
                    return True
                
                # Numeric match (within tolerance)
                try:
                    if abs(float(v1) - float(v2)) < 0.001:
                        return True
                except ValueError:
                    pass
                
                # Substring match or high similarity
                if (v1 in v2) or (v2 in v1):
                    return True
                
                # String similarity (using difflib)
                from difflib import SequenceMatcher
                ratio = SequenceMatcher(None, v1, v2).ratio()
                if ratio >= 0.6:
                    return True
        
        return False
    
    def _parse_query_type(self, query_sql: str) -> str:
        """Parse query to determine type: Extract, Filter, Join, Agg, etc."""
        query_upper = query_sql.upper()
        
        if "WHERE" in query_upper and "JOIN" in query_upper:
            return "Select+Filter+Join"
        elif "GROUP BY" in query_upper and "JOIN" in query_upper:
            return "Select+Join+Aggregation"
        elif "WHERE" in query_upper:
            return "Select+Filter"
        elif "GROUP BY" in query_upper:
            return "Select+Aggregation"
        elif "JOIN" in query_upper:
            return "Select+Join"
        else:
            return "Select"
    
    def _execute_with_docetl(self, query_sql: str) -> Dict:
        from docetl_query_executor import DocETLHealthcareQueryExecutor
        
        executor = DocETLHealthcareQueryExecutor(
            attributes_file=str(self.attributes_file),
            model="ollama/gemma3:27b"
        )
        
        disease_docs = self.documents.get("disease", [])
        drug_docs = self.documents.get("drug", [])
        institution_docs = self.documents.get("institution", [])
        
        # Determine if this is a join or filter query
        query_upper = query_sql.upper()
        if "JOIN" in query_upper:
            results = executor.execute_join_query(
                query_sql,
                disease_docs,
                drug_docs,
                institution_docs
            )
        else:
            # Filter query
            results = executor.execute_filter_query(
                query_sql,
                disease_docs,
                drug_docs,
                institution_docs
            )
        
        return results
    
    def _estimate_cost(self, results: Dict) -> float:
        """
        Estimate token cost as per UDA-Bench: 
        average tokens (in thousands) per document per query
        """
        num_docs = results.get("num_documents_processed", 1)
        tokens = results.get("token_count", 0)
        
        if num_docs == 0:
            return 0.0
        
        # Return in thousands of tokens as per paper
        return (tokens / 1000.0) / num_docs
    
    def generate_report(self) -> Dict:
        """
        Generate evaluation report matching UDA-Bench format.
        """
        if not self.results["queries"]:
            logger.error("No queries executed - cannot generate report")
            return {}
        
        # Calculate averages
        precisions = []
        recalls = []
        f1_scores = []
        costs = []
        latencies = []
        
        for query_results in self.results["queries"].values():
            if "precision" in query_results:
                precisions.append(query_results["precision"])
                recalls.append(query_results["recall"])
                f1_scores.append(query_results["f1"])
            if "cost" in query_results:
                costs.append(query_results["cost"])
            if "latency" in query_results:
                latencies.append(query_results["latency"])
        
        report = {
            "model": "ollama/gemma3:27b",
            "dataset": "Healthcare",
            "num_queries": len(self.results["queries"]),
            "metrics": {
                "precision": sum(precisions) / len(precisions) if precisions else 0.0,
                "recall": sum(recalls) / len(recalls) if recalls else 0.0,
                "f1_score": sum(f1_scores) / len(f1_scores) if f1_scores else 0.0,
                "cost_per_doc_query": sum(costs) / len(costs) if costs else 0.0,
                "latency_per_doc_query": sum(latencies) / len(latencies) if latencies else 0.0,
            },
            "query_results": self.results["queries"]
        }
        
        return report
    
    def print_results(self):
        """Print results in table format matching UDA-Bench tables."""
        report = self.generate_report()
        
        print("\n" + "="*80)
        print("DocETL EVALUATION RESULTS - Healthcare Dataset")
        print("="*80)
        print(f"\nModel: {report['model']}")
        print(f"Dataset: {report['dataset']}")
        print(f"Queries executed: {report['num_queries']}")
        print("\nMetrics (following UDA-Bench evaluation):")
        print(f"  Precision:  {report['metrics']['precision']:.4f}")
        print(f"  Recall:     {report['metrics']['recall']:.4f}")
        print(f"  F1-score:   {report['metrics']['f1_score']:.4f}")
        print(f"  Cost (k-tokens/doc/query): {report['metrics']['cost_per_doc_query']:.2f}")
        print(f"  Latency (sec/doc/query):   {report['metrics']['latency_per_doc_query']:.2f}")
        print("="*80 + "\n")


def run_evaluation():
    """Main evaluation runner."""
    
    # Initialize evaluation system
    evaluator = HealthcareEvaluationSystem(
        data_dir="source_data/Healthcare",
        attributes_file="Query/Med/Med_attributes.json",
        queries_file="Query/Med/Join/join_queries.sql",
        ground_truth_dir="ground_truth/Healthcare"
    )
    
    logger.info(f"Loaded {len(evaluator.documents)} document categories")
    for category, docs in evaluator.documents.items():
        logger.info(f"  {category}: {len(docs)} documents")
    
    # Load queries
    with open(evaluator.queries_file) as f:
        queries_text = f.read()
    
    # Parse queries
    queries = [q.strip() for q in queries_text.split(';') if q.strip()]
    logger.info(f"Loaded {len(queries)} queries")
    
    # Execute each query
    for query_id, query_sql in enumerate(queries, 1):
        try:
            results, cost, latency = evaluator.execute_query(query_id, query_sql)
            
            # Store results
            evaluator.results["queries"][query_id] = {
                "sql": query_sql[:100],
                "precision": results.get("precision", 0.0),
                "recall": results.get("recall", 0.0),
                "f1": results.get("f1", 0.0),
                "cost": cost,
                "latency": latency,
                "num_tuples": len(results.get("tuples", [])),
            }
            
            logger.info(f"Query {query_id}: P={results.get('precision', 0):.4f}, R={results.get('recall', 0):.4f}, F1={results.get('f1', 0):.4f}, Cost={cost:.2f}k, Latency={latency:.2f}s")
        
        except Exception as e:
            logger.error(f"Error executing query {query_id}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Print results
    evaluator.print_results()
    
    return evaluator


if __name__ == "__main__":
    evaluator = run_evaluation()

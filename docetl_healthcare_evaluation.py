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
        self.categories = ["disease", "drug", "institution"]
        
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
            category_path = self.data_dir / f"{category}_small"
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
        Load ground truth labels for evaluation.
        
        Following UDA-Bench Section 3.3: manually labeled attribute values
        Ground truth format: {query_id: {"precision": [...], "recall": [...]}}
        """
        ground_truth = {}
        
        if self.ground_truth_dir.exists():
            for gt_file in self.ground_truth_dir.glob("*.json"):
                with open(gt_file) as f:
                    ground_truth.update(json.load(f))
        
        return ground_truth
    
    def execute_query(self, query_id: int, query_sql: str) -> Tuple[Dict, float, float]:
        """
        Execute a single query using DocETL and measure metrics.
        
        Returns:
            (results_dict, cost_tokens, latency_seconds)
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
        # This will call your DocETL implementation
        extracted_results = self._execute_with_docetl(query_sql)
        
        latency = time.time() - start_time
        
        # Estimate cost (tokens used)
        # Cost = (avg input tokens per document * num docs processed)
        cost = self._estimate_cost(extracted_results)
        
        return extracted_results, cost, latency
    
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
            model="ollama/qwen2.5:7b-instruct"
        )
        
        disease_docs = self.documents.get("disease", [])
        drug_docs = self.documents.get("drug", [])
        institution_docs = self.documents.get("institution", [])
        
        results = executor.execute_join_query(
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
    
    def evaluate_accuracy(self, query_id: int, extracted_tuples: List[Dict]) -> Tuple[float, float, float]:
        if query_id not in self.ground_truth:
            logger.warning(f"No ground truth for query {query_id}")
            return 0.0, 0.0, 0.0
        
        # Extract ground truth tuples
        gt_tuples = self.ground_truth[query_id]
        matches = 0
        for extracted in extracted_tuples:
            for gt in gt_tuples:
                if self._tuple_matches(extracted, gt):
                    matches += 1
                    break
        
        precision = matches / len(extracted_tuples) if extracted_tuples else 0.0
        recall = matches / len(gt_tuples) if gt_tuples else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        return precision, recall, f1
    
    def _tuple_matches(self, extracted: Dict, ground_truth: Dict) -> bool:
        """Check if extracted tuple matches ground truth tuple."""
        # Simple exact match on all fields
        return extracted == ground_truth
    
    def generate_report(self) -> Dict:
        """
        Generate evaluation report matching UDA-Bench format.
        
        Reports:
        - Precision, Recall, F1-score (average across all queries)
        - Cost per document per query (tokens in thousands)
        - Latency per document per query (seconds)
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
            "model": "ollama/qwen2.5:7b-instruct",
            "dataset": "Healthcare",
            "num_queries": len(self.results["queries"]),
            "metrics": {
                "precision": sum(precisions) / len(precisions) if precisions else 0.0,
                "recall": sum(recalls) / len(recalls) if recalls else 0.0,
                "f1_score": sum(f1_scores) / len(f1_scores) if f1_scores else 0.0,
                "cost_per_doc_query": sum(costs) / len(costs) if costs else 0.0,  # thousands of tokens
                "latency_per_doc_query": sum(latencies) / len(latencies) if latencies else 0.0,  # seconds
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
        
        # Print per-query results
        print("Per-Query Results:")
        print("-"*80)
        for qid, qresults in report['query_results'].items():
            print(f"Query {qid}:")
            print(f"  Precision: {qresults.get('precision', 'N/A'):.4f}")
            print(f"  Recall:    {qresults.get('recall', 'N/A'):.4f}")
            print(f"  F1-score:  {qresults.get('f1', 'N/A'):.4f}")
            print(f"  Cost:      {qresults.get('cost', 'N/A'):.2f}k tokens")
            print(f"  Latency:   {qresults.get('latency', 'N/A'):.2f}s")
        print("-"*80 + "\n")


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
    
    # Parse queries (simple SQL parsing)
    queries = [q.strip() for q in queries_text.split(';') if q.strip()]
    logger.info(f"Loaded {len(queries)} queries")
    
    # Execute each query
    for query_id, query_sql in enumerate(queries, 1):
        try:
            results, cost, latency = evaluator.execute_query(query_id, query_sql)
            
            # Evaluate accuracy (requires ground truth)
            extracted_tuples = results.get("tuples", [])
            precision, recall, f1 = evaluator.evaluate_accuracy(query_id, extracted_tuples)
            
            # Store results
            evaluator.results["queries"][query_id] = {
                "sql": query_sql[:100],  # Truncate for display
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "cost": cost,
                "latency": latency,
                "num_tuples": len(extracted_tuples),
            }
            
            logger.info(f"Query {query_id}: P={precision:.4f}, R={recall:.4f}, F1={f1:.4f}, Cost={cost:.2f}k, Latency={latency:.2f}s")
        
        except Exception as e:
            logger.error(f"Error executing query {query_id}: {e}")
            continue
    
    # Print results
    evaluator.print_results()
    
    return evaluator


if __name__ == "__main__":
    evaluator = run_evaluation()

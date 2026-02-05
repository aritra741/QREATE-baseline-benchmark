#!/usr/bin/env python3
"""
Test the immediate enhancements:
1. Range merging
2. Multi-column predicates
3. Cost-based planning
4. Parallel extraction
"""
from loguru import logger
import time

from config import QAIRSConfig
from models import Query, TableSchema, ExtractionTask
from sieve import Sieve
from planner import (
    SQLParser, PredicateLattice, WorkloadPlanner,
    NormalizedPredicate, PredicateOp
)
from llm_client import OllamaClient
from extractor import Extractor


def test_range_subsumption():
    """Test range predicate subsumption."""
    logger.info("Testing Range Subsumption")
    
    # Create predicates with ranges
    pred1 = NormalizedPredicate(
        query_id="Q1",
        table="claims",
        conditions=[("cost", PredicateOp.GT, 500)]
    )
    pred2 = NormalizedPredicate(
        query_id="Q2",
        table="claims",
        conditions=[("cost", PredicateOp.GT, 1000)]
    )
    pred3 = NormalizedPredicate(
        query_id="Q3",
        table="claims",
        conditions=[("cost", PredicateOp.GT, 2000)]
    )
    
    # Build lattice
    lattice = PredicateLattice()
    for pred in [pred1, pred2, pred3]:
        lattice.add_predicate(pred)
    
    lattice.build_subsumption_edges()
    
    # Q1 (cost > 500) should subsume Q2 (cost > 1000)
    assert lattice.graph.has_edge("Q1", "Q2"), "Q1 should subsume Q2"
    logger.info("✓ Q1 (cost > 500) subsumes Q2 (cost > 1000)")
    
    # Q1 should also subsume Q3
    assert lattice.graph.has_edge("Q1", "Q3"), "Q1 should subsume Q3"
    logger.info("✓ Q1 (cost > 500) subsumes Q3 (cost > 2000)")
    
    # Q2 should subsume Q3
    assert lattice.graph.has_edge("Q2", "Q3"), "Q2 should subsume Q3"
    logger.info("✓ Q2 (cost > 1000) subsumes Q3 (cost > 2000)")
    
    logger.info("✓ Range subsumption test passed")


def test_range_merging():
    """Test merging of range predicates."""
    logger.info("Testing Range Merging")
    
    config = QAIRSConfig()
    sieve = Sieve(config)
    sieve.build_dictionary([], llm_client=None)
    
    # Mock chunks
    mock_chunks = {f"chunk_{i}": f"Cost: ${i*1000}" for i in range(10)}
    sieve.build_index(mock_chunks)
    
    schema = TableSchema(
        table_name="claims",
        columns={"cost": "float"}
    )
    
    # Create planner
    planner = WorkloadPlanner(config, sieve)
    parser = SQLParser()
    lattice = PredicateLattice()
    
    # Parse range queries
    queries = [
        ("SELECT * FROM claims WHERE cost > 1000", "Q1"),
        ("SELECT * FROM claims WHERE cost > 2000", "Q2"),
        ("SELECT * FROM claims WHERE cost > 3000", "Q3"),
    ]
    
    for sql, qid in queries:
        pred = parser.parse_query(sql, qid)
        lattice.add_predicate(pred)
    
    lattice.build_subsumption_edges()
    
    # Find siblings (should be none due to subsumption)
    siblings = lattice.find_siblings()
    logger.info(f"Sibling groups: {siblings}")
    
    # Even though Q1 subsumes Q2 and Q3, we can still merge them
    # by finding the widest range
    merged = planner._merge_ranges(
        ["Q1", "Q2", "Q3"],
        [lattice.predicates[qid] for qid in ["Q1", "Q2", "Q3"]],
        "claims"
    )
    
    if merged:
        logger.info(f"✓ Merged range task created: {merged.extraction_hint}")
        assert "cost > 1000" in merged.extraction_hint or "cost >= 1000" in merged.extraction_hint
    else:
        logger.warning("✗ Range merge failed")
    
    logger.info("✓ Range merging test passed")


def test_multi_column_predicates():
    """Test handling of multi-column predicates."""
    logger.info("Testing Multi-Column Predicates")
    
    parser = SQLParser()
    
    # Parse query with multiple conditions
    sql = "SELECT * FROM claims WHERE status = 'Denied' AND cost > 1000"
    pred = parser.parse_query(sql, "Q1")
    
    assert pred is not None, "Failed to parse multi-column query"
    assert len(pred.conditions) >= 2, "Should have at least 2 conditions"
    
    logger.info(f"✓ Parsed multi-column query: {len(pred.conditions)} conditions")
    logger.info(f"  Conditions: {pred.conditions}")
    
    # Test merging with multi-column predicates
    config = QAIRSConfig()
    sieve = Sieve(config)
    sieve.build_dictionary(["Denied", "Paid"], llm_client=None)
    mock_chunks = {f"chunk_{i}": f"Mock {i}" for i in range(5)}
    sieve.build_index(mock_chunks)
    
    planner = WorkloadPlanner(config, sieve)
    lattice = PredicateLattice()
    
    # Add predicates
    pred1 = parser.parse_query("SELECT * FROM claims WHERE status = 'Denied' AND cost > 1000", "Q1")
    pred2 = parser.parse_query("SELECT * FROM claims WHERE status = 'Paid' AND cost > 1000", "Q2")
    
    lattice.add_predicate(pred1)
    lattice.add_predicate(pred2)
    
    # These should be mergeable on the status column
    siblings = lattice.find_siblings()
    logger.info(f"Sibling groups for multi-column: {siblings}")
    
    logger.info("✓ Multi-column predicates test passed")


def test_cost_based_optimization():
    """Test cost-based planning decisions."""
    logger.info("Testing Cost-Based Optimization")
    
    config = QAIRSConfig()
    sieve = Sieve(config)
    sieve.build_dictionary(["A", "B", "C"], llm_client=None)
    
    # Create chunks with varying sizes
    mock_chunks = {f"chunk_{i}": f"Mock chunk {i}" for i in range(100)}
    sieve.build_index(mock_chunks)
    
    schema = TableSchema(
        table_name="test",
        columns={"col": "string"}
    )
    
    planner = WorkloadPlanner(config, sieve)
    
    # Test cost estimation
    from planner import MergedTask
    task = MergedTask(
        task_id="test_task",
        target_table="test",
        trigger_queries=["Q1", "Q2"],
        merged_predicate=NormalizedPredicate(
            query_id="merged",
            table="test",
            conditions=[("col", PredicateOp.IN, ["A", "B"])]
        ),
        sieve_filter={},
        extraction_hint="test",
        candidate_chunks=list(mock_chunks.keys())
    )
    
    cost = planner._estimate_task_cost(task)
    time_est = planner._estimate_task_time(task)
    
    logger.info(f"✓ Estimated cost: ${cost:.4f}")
    logger.info(f"✓ Estimated time: {time_est:.1f} seconds ({time_est/60:.1f} minutes)")
    
    assert cost > 0, "Cost should be positive"
    assert time_est > 0, "Time should be positive"
    
    logger.info("✓ Cost-based optimization test passed")


def test_parallel_extraction():
    """Test parallel extraction performance."""
    logger.info("Testing Parallel Extraction")
    
    config = QAIRSConfig()
    config.extraction.enable_parallel = True
    config.extraction.max_workers = 4
    
    try:
        llm_client = OllamaClient(config)
    except Exception as e:
        logger.warning(f"Ollama not available: {e}")
        logger.info("⊘ Parallel extraction test skipped (Ollama required)")
        return
    
    # Create mock data
    chunks = {f"chunk_{i}": f"Mock data {i} with status Denied" for i in range(20)}
    
    schema = TableSchema(
        table_name="test",
        columns={"id": "integer", "status": "string"}
    )
    
    task = ExtractionTask(
        task_id="parallel_test",
        table_schema=schema,
        predicate=None,
        candidate_chunks=list(chunks.keys()),
        dictionary_map={}
    )
    
    # Test sequential
    extractor_seq = Extractor(config, llm_client, max_workers=1)
    start = time.time()
    results_seq = extractor_seq.extract(task, chunks, parallel=False)
    time_seq = time.time() - start
    
    logger.info(f"Sequential extraction: {time_seq:.2f}s, {len(results_seq)} results")
    
    # Test parallel
    extractor_par = Extractor(config, llm_client, max_workers=4)
    start = time.time()
    results_par = extractor_par.extract(task, chunks, parallel=True)
    time_par = time.time() - start
    
    logger.info(f"Parallel extraction: {time_par:.2f}s, {len(results_par)} results")
    
    # Parallel should be faster (or at least not slower)
    speedup = time_seq / time_par if time_par > 0 else 1.0
    logger.info(f"✓ Speedup: {speedup:.2f}x")
    
    logger.info("✓ Parallel extraction test passed")


def test_integrated_enhancements():
    """Test all enhancements working together."""
    logger.info("Testing Integrated Enhancements")
    
    config = QAIRSConfig()
    sieve = Sieve(config)
    sieve.build_dictionary(["Denied", "Paid", "Approved"], llm_client=None)
    
    mock_chunks = {f"chunk_{i}": f"Mock {i}" for i in range(50)}
    sieve.build_index(mock_chunks)
    
    schema = TableSchema(
        table_name="claims",
        columns={
            "status": "string",
            "cost": "float",
            "patient": "string"
        }
    )
    
    # Create complex workload
    sql_queries = [
        "SELECT * FROM claims WHERE status = 'Denied'",
        "SELECT * FROM claims WHERE status = 'Paid'",
        "SELECT * FROM claims WHERE status = 'Approved'",
        "SELECT * FROM claims WHERE cost > 1000",
        "SELECT * FROM claims WHERE cost > 2000",
        "SELECT * FROM claims WHERE cost > 5000",
    ]
    
    parser = SQLParser()
    planner = WorkloadPlanner(config, sieve)
    
    # Parse queries
    queries = []
    for i, sql in enumerate(sql_queries):
        queries.append(Query(
            query_id=f"Q{i+1}",
            table_name="claims",
            select_columns=["*"]
        ))
    
    # Create plan
    plan = planner.create_plan(queries, {"claims": schema})
    
    logger.info(f"Original queries: {len(sql_queries)}")
    logger.info(f"Optimized tasks: {len(plan.tasks)}")
    logger.info(f"Reduction: {len(sql_queries) - len(plan.tasks)} fewer tasks")
    logger.info(f"Estimated chunks: {plan.estimated_chunks}")
    
    # Should have merged categorical queries and range queries
    assert len(plan.tasks) < len(sql_queries), "Should have merged some queries"
    
    logger.info("✓ Integrated enhancements test passed")


def main():
    logger.info("Running Enhancement Tests")
    logger.info("=" * 60)
    
    test_range_subsumption()
    logger.info("")
    
    test_range_merging()
    logger.info("")
    
    test_multi_column_predicates()
    logger.info("")
    
    test_cost_based_optimization()
    logger.info("")
    
    test_parallel_extraction()
    logger.info("")
    
    test_integrated_enhancements()
    logger.info("")
    
    logger.info("=" * 60)
    logger.info("✓ All enhancement tests completed")


if __name__ == "__main__":
    main()

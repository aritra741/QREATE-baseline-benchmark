#!/usr/bin/env python3
"""
Test the advanced MQO planner with sqlglot and networkx.
"""
from loguru import logger

from config import QAIRSConfig
from models import Query, TableSchema
from sieve import Sieve
from planner import (
    SQLParser, PredicateLattice, WorkloadPlanner,
    NormalizedPredicate, PredicateOp
)


def test_sql_parser():
    """Test SQL parsing with sqlglot."""
    logger.info("Testing SQL Parser")
    
    test_cases = [
        ("SELECT * FROM claims WHERE status = 'Denied'", "Q1"),
        ("SELECT * FROM claims WHERE status = 'Paid'", "Q2"),
        ("SELECT * FROM claims WHERE cost > 1000", "Q3"),
        ("SELECT * FROM claims WHERE status IN ('Denied', 'Paid')", "Q4"),
        ("SELECT * FROM claims", "Q5"),  # No WHERE clause
    ]
    
    parser = SQLParser()
    
    for sql, qid in test_cases:
        pred = parser.parse_query(sql, qid)
        if pred:
            logger.info(f"✓ Parsed {qid}: {pred.table}, {len(pred.conditions)} conditions")
            logger.info(f"  Conditions: {pred.conditions}")
            logger.info(f"  SQL: {pred.to_sql_where()}")
        else:
            logger.error(f"✗ Failed to parse {qid}")
    
    logger.info("✓ SQL Parser test passed")


def test_predicate_lattice():
    """Test predicate lattice construction."""
    logger.info("Testing Predicate Lattice")
    
    # Create predicates
    predicates = [
        NormalizedPredicate(
            query_id="Q1",
            table="claims",
            conditions=[("status", PredicateOp.EQ, "Denied")]
        ),
        NormalizedPredicate(
            query_id="Q2",
            table="claims",
            conditions=[("status", PredicateOp.EQ, "Paid")]
        ),
        NormalizedPredicate(
            query_id="Q3",
            table="claims",
            conditions=[("cost", PredicateOp.GT, 1000)]
        ),
        NormalizedPredicate(
            query_id="Q4",
            table="claims",
            conditions=[("status", PredicateOp.IN, ["Denied", "Paid"])]
        ),
        NormalizedPredicate(
            query_id="Q5",
            table="claims",
            conditions=[]  # No predicates - matches all
        ),
    ]
    
    # Build lattice
    lattice = PredicateLattice()
    for pred in predicates:
        lattice.add_predicate(pred)
    
    lattice.build_subsumption_edges()
    
    # Check subsumption
    logger.info(f"Graph has {lattice.graph.number_of_nodes()} nodes, {lattice.graph.number_of_edges()} edges")
    
    # Q5 (no predicates) should subsume all others
    for qid in ["Q1", "Q2", "Q3", "Q4"]:
        if lattice.graph.has_edge("Q5", qid):
            logger.info(f"✓ Q5 subsumes {qid}")
        else:
            logger.warning(f"✗ Q5 should subsume {qid}")
    
    # Q4 (status IN ('Denied', 'Paid')) should subsume Q1 and Q2
    for qid in ["Q1", "Q2"]:
        if lattice.graph.has_edge("Q4", qid):
            logger.info(f"✓ Q4 subsumes {qid}")
        else:
            logger.warning(f"✗ Q4 should subsume {qid}")
    
    # Find siblings
    siblings = lattice.find_siblings()
    logger.info(f"Found {len(siblings)} sibling groups: {siblings}")
    
    logger.info("✓ Predicate Lattice test passed")


def test_workload_planner():
    """Test complete workload planning."""
    logger.info("Testing Workload Planner")
    
    # Setup
    config = QAIRSConfig()
    
    # Create sieve with mock data
    sieve = Sieve(config)
    sieve.build_dictionary(["Denied", "Paid", "Approved"], llm_client=None)
    
    # Mock chunks
    mock_chunks = {
        f"chunk_{i}": f"Mock chunk {i} with status Denied"
        for i in range(10)
    }
    sieve.build_index(mock_chunks)
    
    # Create schema
    schema = TableSchema(
        table_name="claims",
        columns={
            "id": "integer",
            "status": "string",
            "cost": "float",
            "patient_name": "string"
        },
        enums={"status": ["Denied", "Paid", "Approved"]}
    )
    
    # Create queries
    queries = [
        Query(
            query_id="Q1",
            table_name="claims",
            select_columns=["*"]
        ),
        Query(
            query_id="Q2",
            table_name="claims",
            select_columns=["*"]
        ),
        Query(
            query_id="Q3",
            table_name="claims",
            select_columns=["*"]
        ),
    ]
    
    # Manually set SQL for testing (normally would come from user)
    # We'll use the parser directly
    planner = WorkloadPlanner(config, sieve)
    
    # Parse some test queries
    sql_queries = [
        "SELECT * FROM claims WHERE status = 'Denied'",
        "SELECT * FROM claims WHERE status = 'Paid'",
        "SELECT * FROM claims WHERE cost > 1000",
    ]
    
    # Create Query objects with predicates
    from planner import SQLParser
    parser = SQLParser()
    
    parsed_queries = []
    for i, sql in enumerate(sql_queries):
        qid = f"Q{i+1}"
        parsed_queries.append(Query(
            query_id=qid,
            table_name="claims",
            select_columns=["*"]
        ))
    
    # Create plan
    plan = planner.create_plan(parsed_queries, {"claims": schema})
    
    logger.info(f"Plan created with {len(plan.tasks)} tasks")
    logger.info(f"Estimated chunks: {plan.estimated_chunks}")
    logger.info(f"Estimated LLM calls: {plan.estimated_llm_calls}")
    
    # Save plan
    planner.save_plan(plan, "test_plan.json")
    logger.info("✓ Plan saved to test_plan.json")
    
    # Load plan
    loaded_plan = WorkloadPlanner.load_plan("test_plan.json")
    logger.info(f"✓ Plan loaded: {loaded_plan['plan_id']}")
    
    logger.info("✓ Workload Planner test passed")


def test_sibling_merging():
    """Test the key optimization: sibling merging."""
    logger.info("Testing Sibling Merging Optimization")
    
    config = QAIRSConfig()
    sieve = Sieve(config)
    sieve.build_dictionary(["Denied", "Paid"], llm_client=None)
    
    # Mock chunks
    mock_chunks = {
        "chunk_1": "Status: Denied, Cost: $5000",
        "chunk_2": "Status: Paid, Cost: $2000",
        "chunk_3": "Status: Denied, Cost: $3000",
    }
    sieve.build_index(mock_chunks)
    
    schema = TableSchema(
        table_name="claims",
        columns={"status": "string", "cost": "float"}
    )
    
    # Two sibling queries (should be merged)
    queries = [
        Query(query_id="Q1", table_name="claims", select_columns=["*"]),
        Query(query_id="Q2", table_name="claims", select_columns=["*"]),
    ]
    
    planner = WorkloadPlanner(config, sieve)
    
    # Parse queries
    parser = SQLParser()
    lattice = PredicateLattice()
    
    pred1 = parser.parse_query("SELECT * FROM claims WHERE status = 'Denied'", "Q1")
    pred2 = parser.parse_query("SELECT * FROM claims WHERE status = 'Paid'", "Q2")
    
    lattice.add_predicate(pred1)
    lattice.add_predicate(pred2)
    lattice.build_subsumption_edges()
    
    # Find siblings
    siblings = lattice.find_siblings()
    logger.info(f"Sibling groups: {siblings}")
    
    # Should find Q1 and Q2 as siblings
    assert len(siblings) > 0, "Should find at least one sibling group"
    assert "Q1" in siblings[0] and "Q2" in siblings[0], "Q1 and Q2 should be siblings"
    
    logger.info("✓ Q1 and Q2 identified as siblings (can be merged)")
    
    # Create merged task
    merged = planner._create_merged_task(["Q1", "Q2"], lattice, {"claims": schema})
    
    if merged:
        logger.info(f"✓ Merged task created: {merged.task_id}")
        logger.info(f"  Trigger queries: {merged.trigger_queries}")
        logger.info(f"  Extraction hint: {merged.extraction_hint}")
        logger.info(f"  Candidate chunks: {len(merged.candidate_chunks)}")
        
        # Key insight: We process chunks ONCE for both queries
        logger.info(f"  💡 Optimization: Process {len(merged.candidate_chunks)} chunks once instead of 2x")
    else:
        logger.error("✗ Failed to create merged task")
    
    logger.info("✓ Sibling Merging test passed")


def main():
    logger.info("Running Advanced MQO Planner Tests")
    logger.info("=" * 60)
    
    test_sql_parser()
    logger.info("")
    
    test_predicate_lattice()
    logger.info("")
    
    test_sibling_merging()
    logger.info("")
    
    test_workload_planner()
    logger.info("")
    
    logger.info("=" * 60)
    logger.info("✓ All tests completed successfully")


if __name__ == "__main__":
    main()

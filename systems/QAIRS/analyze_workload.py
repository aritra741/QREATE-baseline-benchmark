#!/usr/bin/env python3
"""
Analyze a SQL workload file and generate an optimized execution plan.

This demonstrates the offline planning phase of QAIRS.
"""
import argparse
import json
from pathlib import Path
from loguru import logger

from config import QAIRSConfig
from models import Query, TableSchema
from sieve import Sieve
from planner import WorkloadPlanner, SQLParser, PredicateLattice


def load_workload(path: str) -> list[str]:
    """
    Load SQL queries from a workload file.
    
    Assumes queries are separated by semicolons.
    """
    with open(path, 'r') as f:
        content = f.read()
    
    # Split by semicolon and filter out comments/empty lines
    queries = []
    for line in content.split(';'):
        line = line.strip()
        # Remove comments
        if '--' in line:
            line = line[:line.index('--')]
        line = line.strip()
        
        if line and not line.startswith('--'):
            queries.append(line)
    
    return queries


def analyze_workload(
    workload_path: str,
    schema: TableSchema,
    config: QAIRSConfig,
    output_path: str = "execution_plan.json"
):
    """
    Analyze a workload and generate an optimized execution plan.
    """
    logger.info(f"Loading workload from: {workload_path}")
    sql_queries = load_workload(workload_path)
    logger.info(f"Loaded {len(sql_queries)} queries")
    
    # Parse queries
    parser = SQLParser()
    lattice = PredicateLattice()
    
    for i, sql in enumerate(sql_queries):
        qid = f"Q{i+1}"
        pred = parser.parse_query(sql, qid)
        if pred:
            lattice.add_predicate(pred)
            logger.info(f"  {qid}: {pred.to_sql_where() or '(no filter)'}")
    
    # Build subsumption graph
    logger.info("\nBuilding predicate lattice...")
    lattice.build_subsumption_edges()
    logger.info(f"  Nodes: {lattice.graph.number_of_nodes()}")
    logger.info(f"  Edges: {lattice.graph.number_of_edges()}")
    
    # Analyze subsumption
    logger.info("\nSubsumption relationships:")
    for edge in lattice.graph.edges():
        parent, child = edge
        logger.info(f"  {parent} subsumes {child}")
    
    # Find siblings
    logger.info("\nSibling groups (merge candidates):")
    siblings = lattice.find_siblings()
    for i, group in enumerate(siblings):
        logger.info(f"  Group {i+1}: {group}")
        # Show what they'll be merged into
        if len(group) > 1:
            predicates = [lattice.predicates[qid] for qid in group]
            # Find common column
            common_cols = None
            for pred in predicates:
                from planner import PredicateOp
                cols = {col for col, op, _ in pred.conditions if op in (PredicateOp.EQ, PredicateOp.IN)}
                if common_cols is None:
                    common_cols = cols
                else:
                    common_cols &= cols
            
            if common_cols:
                col = list(common_cols)[0]
                all_vals = set()
                for pred in predicates:
                    all_vals.update(pred.get_categorical_values(col))
                logger.info(f"    → Will merge into: {col} IN ({', '.join(map(str, all_vals))})")
    
    # Create mock sieve for planning
    logger.info("\nInitializing Sieve...")
    sieve = Sieve(config)
    
    # Extract dictionary terms from all queries
    dict_terms = set()
    for pred in lattice.predicates.values():
        from planner import PredicateOp
        for col, op, val in pred.conditions:
            if op == PredicateOp.EQ and isinstance(val, str):
                dict_terms.add(val)
            elif op == PredicateOp.IN:
                dict_terms.update([str(v) for v in val if isinstance(v, str)])
    
    logger.info(f"  Dictionary terms: {dict_terms}")
    sieve.build_dictionary(list(dict_terms), llm_client=None)
    
    # Create planner
    planner = WorkloadPlanner(config, sieve)
    
    # Convert to Query objects
    queries = []
    for qid in lattice.predicates.keys():
        queries.append(Query(
            query_id=qid,
            table_name=schema.table_name,
            select_columns=["*"]
        ))
    
    # Create plan
    logger.info("\nGenerating execution plan...")
    plan = planner.create_plan(queries, {schema.table_name: schema})
    
    logger.info(f"\n{'='*60}")
    logger.info("EXECUTION PLAN SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Original queries: {len(sql_queries)}")
    logger.info(f"Optimized tasks: {len(plan.tasks)}")
    logger.info(f"Reduction: {len(sql_queries) - len(plan.tasks)} fewer extraction passes")
    logger.info(f"Estimated chunks: {plan.estimated_chunks}")
    logger.info(f"Estimated LLM calls: {plan.estimated_llm_calls}")
    
    # Save plan
    planner.save_plan(plan, output_path)
    logger.info(f"\n✓ Plan saved to: {output_path}")
    
    return plan


def main():
    parser = argparse.ArgumentParser(
        description="Analyze SQL workload and generate optimized execution plan"
    )
    parser.add_argument(
        "--workload",
        required=True,
        help="Path to SQL workload file"
    )
    parser.add_argument(
        "--output",
        default="execution_plan.json",
        help="Output path for execution plan"
    )
    parser.add_argument(
        "--table",
        default="claims",
        help="Target table name"
    )
    
    args = parser.parse_args()
    
    # Create config
    config = QAIRSConfig()
    
    # Create schema (in production, this would be loaded from DB)
    schema = TableSchema(
        table_name=args.table,
        columns={
            "id": "integer",
            "status": "string",
            "cost": "float",
            "insurer": "string",
            "patient_name": "string",
            "diagnosis": "string"
        },
        enums={
            "status": ["Denied", "Paid", "Approved", "Pending"]
        }
    )
    
    # Analyze
    analyze_workload(args.workload, schema, config, args.output)


if __name__ == "__main__":
    main()

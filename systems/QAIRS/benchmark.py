#!/usr/bin/env python3
"""
Benchmark script to demonstrate the performance improvements from enhancements.
"""
import time
import argparse
from typing import Dict, List
from loguru import logger

from config import QAIRSConfig
from models import Query, TableSchema
from sieve import Sieve
from planner import WorkloadPlanner, SQLParser


def create_benchmark_workload(workload_type: str) -> List[str]:
    """Create different types of workloads for benchmarking."""
    
    if workload_type == "categorical":
        # Workload with many categorical queries (good for merging)
        return [
            "SELECT * FROM claims WHERE status = 'Denied'",
            "SELECT * FROM claims WHERE status = 'Paid'",
            "SELECT * FROM claims WHERE status = 'Approved'",
            "SELECT * FROM claims WHERE status = 'Pending'",
            "SELECT * FROM claims WHERE status = 'Rejected'",
            "SELECT * FROM claims WHERE insurer = 'Cigna'",
            "SELECT * FROM claims WHERE insurer = 'Aetna'",
            "SELECT * FROM claims WHERE insurer = 'BlueCross'",
        ]
    
    elif workload_type == "range":
        # Workload with range queries (good for subsumption)
        return [
            "SELECT * FROM claims WHERE cost > 500",
            "SELECT * FROM claims WHERE cost > 1000",
            "SELECT * FROM claims WHERE cost > 2000",
            "SELECT * FROM claims WHERE cost > 5000",
            "SELECT * FROM claims WHERE cost > 10000",
            "SELECT * FROM claims WHERE cost < 1000",
            "SELECT * FROM claims WHERE cost < 500",
        ]
    
    elif workload_type == "mixed":
        # Mixed workload
        return [
            "SELECT * FROM claims WHERE status = 'Denied'",
            "SELECT * FROM claims WHERE status = 'Paid'",
            "SELECT * FROM claims WHERE cost > 1000",
            "SELECT * FROM claims WHERE cost > 5000",
            "SELECT * FROM claims WHERE insurer = 'Cigna'",
            "SELECT * FROM claims WHERE insurer = 'Aetna'",
            "SELECT * FROM claims WHERE status = 'Approved' AND cost > 2000",
            "SELECT * FROM claims WHERE status = 'Pending' AND cost > 1000",
        ]
    
    elif workload_type == "large":
        # Large workload to stress test
        queries = []
        statuses = ["Denied", "Paid", "Approved", "Pending", "Rejected"]
        insurers = ["Cigna", "Aetna", "BlueCross", "UnitedHealth", "Humana"]
        
        for status in statuses:
            queries.append(f"SELECT * FROM claims WHERE status = '{status}'")
        
        for insurer in insurers:
            queries.append(f"SELECT * FROM claims WHERE insurer = '{insurer}'")
        
        for threshold in [500, 1000, 2000, 5000, 10000]:
            queries.append(f"SELECT * FROM claims WHERE cost > {threshold}")
        
        return queries
    
    else:
        raise ValueError(f"Unknown workload type: {workload_type}")


def benchmark_planning(
    workload: List[str],
    config: QAIRSConfig,
    num_chunks: int = 1000
) -> Dict:
    """Benchmark the planning phase."""
    
    logger.info(f"Benchmarking with {len(workload)} queries, {num_chunks} chunks")
    
    # Setup
    sieve = Sieve(config)
    
    # Extract dictionary terms from workload
    parser = SQLParser()
    all_terms = set()
    for sql in workload:
        # Simple extraction of quoted strings
        import re
        terms = re.findall(r"'([^']+)'", sql)
        all_terms.update(terms)
    
    sieve.build_dictionary(list(all_terms), llm_client=None)
    
    # Create mock chunks
    mock_chunks = {f"chunk_{i}": f"Mock chunk {i}" for i in range(num_chunks)}
    sieve.build_index(mock_chunks)
    
    # Create schema
    schema = TableSchema(
        table_name="claims",
        columns={
            "id": "integer",
            "status": "string",
            "cost": "float",
            "insurer": "string",
            "patient": "string"
        }
    )
    
    # Create queries
    queries = []
    for i, sql in enumerate(workload):
        queries.append(Query(
            query_id=f"Q{i+1}",
            table_name="claims",
            select_columns=["*"]
        ))
    
    # Benchmark planning
    planner = WorkloadPlanner(config, sieve)
    
    start = time.time()
    plan = planner.create_plan(queries, {"claims": schema})
    planning_time = time.time() - start
    
    # Calculate metrics
    naive_llm_calls = len(workload) * num_chunks
    optimized_llm_calls = plan.estimated_llm_calls
    reduction = (naive_llm_calls - optimized_llm_calls) / naive_llm_calls * 100
    
    naive_cost = (naive_llm_calls * planner.tokens_per_chunk / 1_000_000) * planner.cost_per_1m_tokens
    optimized_cost = sum(
        planner._estimate_task_cost(
            next(mt for mt in [planner._create_individual_task(q.query_id, p, {}) 
                              for q, p in zip(queries, [parser.parse_query(sql, f"Q{i+1}") 
                              for i, sql in enumerate(workload)])] if mt)
        ) if len(plan.tasks) > 0 else 0
        for _ in range(len(plan.tasks))
    )
    
    # Simplified cost calculation
    optimized_cost = (optimized_llm_calls * planner.tokens_per_chunk / 1_000_000) * planner.cost_per_1m_tokens
    cost_savings = naive_cost - optimized_cost
    
    results = {
        "workload_size": len(workload),
        "num_chunks": num_chunks,
        "planning_time": planning_time,
        "original_tasks": len(workload),
        "optimized_tasks": len(plan.tasks),
        "task_reduction": len(workload) - len(plan.tasks),
        "naive_llm_calls": naive_llm_calls,
        "optimized_llm_calls": optimized_llm_calls,
        "call_reduction_pct": reduction,
        "naive_cost": naive_cost,
        "optimized_cost": optimized_cost,
        "cost_savings": cost_savings,
        "cost_savings_pct": (cost_savings / naive_cost * 100) if naive_cost > 0 else 0,
    }
    
    return results


def print_results(results: Dict, workload_type: str):
    """Print benchmark results in a nice format."""
    
    print("\n" + "=" * 70)
    print(f"BENCHMARK RESULTS: {workload_type.upper()} WORKLOAD")
    print("=" * 70)
    
    print(f"\nWorkload:")
    print(f"  Queries: {results['workload_size']}")
    print(f"  Chunks: {results['num_chunks']}")
    print(f"  Planning time: {results['planning_time']:.3f}s")
    
    print(f"\nOptimization:")
    print(f"  Original tasks: {results['original_tasks']}")
    print(f"  Optimized tasks: {results['optimized_tasks']}")
    print(f"  Task reduction: {results['task_reduction']} ({results['task_reduction']/results['original_tasks']*100:.1f}%)")
    
    print(f"\nLLM Calls:")
    print(f"  Naive: {results['naive_llm_calls']:,}")
    print(f"  Optimized: {results['optimized_llm_calls']:,}")
    print(f"  Reduction: {results['naive_llm_calls'] - results['optimized_llm_calls']:,} ({results['call_reduction_pct']:.1f}%)")
    
    print(f"\nCost (USD):")
    print(f"  Naive: ${results['naive_cost']:.2f}")
    print(f"  Optimized: ${results['optimized_cost']:.2f}")
    print(f"  Savings: ${results['cost_savings']:.2f} ({results['cost_savings_pct']:.1f}%)")
    
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Benchmark QAIRS enhancements")
    parser.add_argument(
        "--workload",
        choices=["categorical", "range", "mixed", "large", "all"],
        default="all",
        help="Type of workload to benchmark"
    )
    parser.add_argument(
        "--chunks",
        type=int,
        default=1000,
        help="Number of chunks to simulate"
    )
    
    args = parser.parse_args()
    
    config = QAIRSConfig()
    
    workload_types = ["categorical", "range", "mixed", "large"] if args.workload == "all" else [args.workload]
    
    all_results = []
    
    for wtype in workload_types:
        logger.info(f"\nBenchmarking {wtype} workload...")
        workload = create_benchmark_workload(wtype)
        results = benchmark_planning(workload, config, args.chunks)
        results["workload_type"] = wtype
        all_results.append(results)
        print_results(results, wtype)
    
    # Summary
    if len(all_results) > 1:
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        
        total_savings = sum(r["cost_savings"] for r in all_results)
        avg_reduction = sum(r["call_reduction_pct"] for r in all_results) / len(all_results)
        
        print(f"\nTotal cost savings: ${total_savings:.2f}")
        print(f"Average call reduction: {avg_reduction:.1f}%")
        
        print("\nPer-workload breakdown:")
        for r in all_results:
            print(f"  {r['workload_type']:12s}: {r['task_reduction']:2d} tasks merged, "
                  f"{r['call_reduction_pct']:5.1f}% fewer calls, "
                  f"${r['cost_savings']:6.2f} saved")


if __name__ == "__main__":
    main()

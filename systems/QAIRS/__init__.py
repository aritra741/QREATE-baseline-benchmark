"""
QAIRS: Query-Aware Incremental Relational Synthesis

A workload-driven text-to-database extraction system using Qwen 2.5.

Enhancements:
- Range merging: Merge range predicates (e.g., cost > 500, cost > 1000)
- Multi-column predicates: Handle complex WHERE clauses
- Cost-based planning: Optimize based on estimated LLM costs
- Parallel extraction: Process chunks concurrently for better throughput
"""

from .config import QAIRSConfig
from .models import (
    TableSchema, Predicate, Query, ExtractionTask,
    MaterializationStatus, SieveEntry
)
from .sieve import Sieve
from .registry import Registry
from .llm_client import OllamaClient
from .extractor import Extractor
from .planner import (
    WorkloadPlanner, SQLParser, PredicateLattice,
    NormalizedPredicate, PredicateOp, MergedTask
)
from .query_engine import QueryEngine

__version__ = "0.2.0"

__all__ = [
    "QAIRSConfig",
    "TableSchema",
    "Predicate",
    "Query",
    "ExtractionTask",
    "MaterializationStatus",
    "SieveEntry",
    "Sieve",
    "Registry",
    "OllamaClient",
    "Extractor",
    "WorkloadPlanner",
    "SQLParser",
    "PredicateLattice",
    "NormalizedPredicate",
    "PredicateOp",
    "MergedTask",
    "QueryEngine",
]

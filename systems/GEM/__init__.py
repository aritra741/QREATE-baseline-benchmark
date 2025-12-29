"""
Global Entity Manager (GEM) - Unstructured Data Analysis System

A Python-based system for extracting structured data from raw text files,
resolving entity identities globally using semantic blocking, and answering
SQL queries with high accuracy.

Architecture:
- Schema Induction: Loads attribute definitions from JSON
- Extraction: LLM-based extraction with chunking and caching
- Blocking: Semantic blocking using sentence embeddings
- Resolution: Global entity resolution using LLM
- Storage: DuckDB with normalized data
- Query: SQL query execution with semantic rewriting
"""

from .gem_runner import GEMRunner

__all__ = ["GEMRunner"]
__version__ = "0.1.0"


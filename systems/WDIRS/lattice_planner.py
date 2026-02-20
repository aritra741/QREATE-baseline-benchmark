"""
Workload Lattice Planner for WDIRS.
Implements MQO (Multi-Query Optimization) and semantic type identification.
"""

import json
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import re

import sqlglot
from sqlglot import parse_one, exp

from config import SEMANTIC_TYPES, OLLAMA_MODEL, OLLAMA_URL

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class ColumnInfo:
    """Information about a column in the workload."""
    table_name: str
    column_name: str
    semantic_type: str = "OTHER"
    predicates: Set[str] = field(default_factory=set)
    # Raw literal values seen in equality predicates across the whole workload.
    # e.g. WHERE country = 'USA' AND country = 'Canada'  →  {'USA', 'Canada'}
    # These are used as normalization hints during extraction so the LLM stores
    # values in exactly the form the queries expect.
    predicate_literals: Set[str] = field(default_factory=set)
    is_join_key: bool = False
    is_group_by: bool = False
    is_aggregated: bool = False

@dataclass
class TableInfo:
    """Information about a table in the workload."""
    table_name: str
    columns: Dict[str, ColumnInfo] = field(default_factory=dict)
    predicates: List[str] = field(default_factory=list)
    referenced_in_joins: bool = False

@dataclass
class WorkloadLattice:
    """Represents the lattice of extraction objectives."""
    tables: Dict[str, TableInfo] = field(default_factory=dict)
    join_pairs: List[Tuple[str, str]] = field(default_factory=list)
    subsumption_graph: Dict[str, List[str]] = field(default_factory=dict)


# ============================================================================
# Workload Lattice Planner
# ============================================================================

class LatticePlanner:
    """
    Analyzes SQL workload to build extraction lattice.
    Implements MQO to minimize redundant LLM calls.
    """
    
    def __init__(self, llm_client=None):
        """Initialize planner with optional LLM client."""
        self.llm_client = llm_client
        self.lattice = WorkloadLattice()
    
    def parse_workload(
        self,
        sql_queries: List[str],
        identify_types: bool = True
    ) -> WorkloadLattice:
        """
        Parse SQL workload and build lattice.

        Args:
            sql_queries: List of SQL query strings
            identify_types: If True (default), call the LLM to classify column
                semantic types.  Pass False when restoring the lattice in Phase 2
                (tables already exist in DB, type info is not needed for SQL exec).

        Returns:
            WorkloadLattice with all tables, columns, and predicates
        """
        logger.info(f"Parsing workload with {len(sql_queries)} queries")

        # Reset lattice so we don't accumulate stale state on restore
        self.lattice = WorkloadLattice()

        for query_idx, query in enumerate(sql_queries):
            try:
                self._parse_query(query, query_idx)
            except Exception as e:
                logger.warning(f"Failed to parse query {query_idx}: {e}")
                logger.debug(f"Query: {query}")

        # Build subsumption graph
        self._build_subsumption_graph()

        if identify_types:
            self._identify_semantic_types()
        else:
            logger.info("Skipping LLM semantic type identification (restore mode)")

        logger.info(f"Parsed workload: {len(self.lattice.tables)} tables, "
                   f"{sum(len(t.columns) for t in self.lattice.tables.values())} columns")

        return self.lattice
    
    def _parse_query(self, query: str, query_idx: int) -> None:
        """Parse a single SQL query and update lattice."""
        try:
            # Parse SQL using sqlglot
            parsed = parse_one(query, dialect="postgres")
            
            # Extract tables
            tables = self._extract_tables(parsed)
            
            # Extract columns
            columns = self._extract_columns(parsed)
            
            # Extract predicates
            predicates = self._extract_predicates(parsed)
            
            # Extract joins
            joins = self._extract_joins(parsed)
            
            # Update lattice
            for table_name in tables:
                if table_name not in self.lattice.tables:
                    self.lattice.tables[table_name] = TableInfo(table_name=table_name)
            
            # Add columns to tables
            for table_name, col_name in columns:
                if table_name not in self.lattice.tables:
                    self.lattice.tables[table_name] = TableInfo(table_name=table_name)
                
                table_info = self.lattice.tables[table_name]
                
                if col_name not in table_info.columns:
                    table_info.columns[col_name] = ColumnInfo(
                        table_name=table_name,
                        column_name=col_name
                    )
            
            # Add predicates
            for table_name, col_name, predicate in predicates:
                if table_name in self.lattice.tables:
                    table_info = self.lattice.tables[table_name]
                    
                    if col_name in table_info.columns:
                        table_info.columns[col_name].predicates.add(predicate)
                    
                    table_info.predicates.append(predicate)
            
            # Add joins
            for left_table, right_table in joins:
                if (left_table, right_table) not in self.lattice.join_pairs:
                    self.lattice.join_pairs.append((left_table, right_table))
                
                # Mark tables as referenced in joins
                if left_table in self.lattice.tables:
                    self.lattice.tables[left_table].referenced_in_joins = True
                if right_table in self.lattice.tables:
                    self.lattice.tables[right_table].referenced_in_joins = True
            
            # Identify aggregations and group by
            self._extract_aggregations(parsed)
            
        except Exception as e:
            logger.error(f"Error parsing query {query_idx}: {e}")
            raise
    
    def _extract_tables(self, parsed: exp.Expression) -> Set[str]:
        """Extract table names from parsed query."""
        tables = set()
        
        for table in parsed.find_all(exp.Table):
            table_name = table.name
            if table_name:
                tables.add(table_name.lower())
        
        return tables
    
    def _extract_columns(self, parsed: exp.Expression) -> List[Tuple[str, str]]:
        """Extract (table, column) pairs from parsed query."""
        columns = []
        
        # First, get the primary table from FROM clause
        primary_table = None
        for table in parsed.find_all(exp.Table):
            primary_table = table.name.lower() if table.name else None
            break  # Use first table as primary
        
        # Get columns from SELECT clause
        for select in parsed.find_all(exp.Select):
            for projection in select.expressions:
                if isinstance(projection, exp.Column):
                    table = projection.table if projection.table else primary_table
                    column = projection.name
                    if table and column:
                        columns.append((table.lower(), column.lower()))
                elif isinstance(projection, exp.Star):
                    # SELECT * - we'll handle this by not adding specific columns
                    # The system will extract all columns it finds in the text
                    pass
        
        # Get columns from WHERE clause
        for where in parsed.find_all(exp.Where):
            for column in where.find_all(exp.Column):
                table = column.table if column.table else primary_table
                col_name = column.name
                if table and col_name:
                    columns.append((table.lower(), col_name.lower()))
        
        return columns
    
    def _extract_predicates(
        self,
        parsed: exp.Expression
    ) -> List[Tuple[str, str, str]]:
        """
        Extract predicates from WHERE clause.
        Returns: List of (table, column, predicate_string)
        """
        predicates = []
        
        # Get the primary table from FROM clause
        primary_table = None
        for table in parsed.find_all(exp.Table):
            primary_table = table.name.lower() if table.name else None
            break  # Use first table as primary
        
        for where in parsed.find_all(exp.Where):
            # Find all comparison expressions
            for comparison in where.find_all(exp.EQ, exp.GT, exp.LT, exp.GTE, exp.LTE, exp.NEQ):
                left = comparison.left
                right = comparison.right
                
                if isinstance(left, exp.Column):
                    table = left.table if left.table else primary_table
                    column = left.name
                    
                    if table and column:
                        # Build predicate string
                        operator = self._get_operator(comparison)
                        value = self._get_value(right)
                        
                        predicate = f"{column} {operator} {value}"
                        predicates.append((table.lower(), column.lower(), predicate))

                        # For equality predicates, record the raw literal so
                        # the extractor can normalize extracted values to match.
                        if isinstance(comparison, exp.EQ) and isinstance(right, exp.Literal):
                            literal_val = right.this  # raw string without quotes
                            tbl_key = table.lower()
                            col_key = column.lower()
                            if tbl_key in self.lattice.tables:
                                col_info = self.lattice.tables[tbl_key].columns.get(col_key)
                                if col_info is not None:
                                    col_info.predicate_literals.add(literal_val)

        return predicates
    
    def _get_operator(self, comparison: exp.Expression) -> str:
        """Get operator string from comparison expression."""
        if isinstance(comparison, exp.EQ):
            return "="
        elif isinstance(comparison, exp.GT):
            return ">"
        elif isinstance(comparison, exp.LT):
            return "<"
        elif isinstance(comparison, exp.GTE):
            return ">="
        elif isinstance(comparison, exp.LTE):
            return "<="
        elif isinstance(comparison, exp.NEQ):
            return "!="
        else:
            return "="
    
    def _get_value(self, expr: exp.Expression) -> str:
        """Extract value from expression."""
        if isinstance(expr, exp.Literal):
            return expr.this
        elif isinstance(expr, exp.Column):
            return expr.name
        else:
            return str(expr)
    
    def _extract_joins(self, parsed: exp.Expression) -> List[Tuple[str, str]]:
        """Extract join pairs from query."""
        joins = []
        
        for join in parsed.find_all(exp.Join):
            # Get left and right tables
            left_table = None
            right_table = None
            
            # Find tables in join condition
            for column in join.find_all(exp.Column):
                table = column.table
                if table:
                    if left_table is None:
                        left_table = table.lower()
                    elif right_table is None and table.lower() != left_table:
                        right_table = table.lower()
            
            if left_table and right_table:
                joins.append((left_table, right_table))
        
        return joins
    
    def _extract_aggregations(self, parsed: exp.Expression) -> None:
        """Identify aggregated columns and group by columns."""
        # Find aggregation functions
        for agg in parsed.find_all(exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max):
            for column in agg.find_all(exp.Column):
                table = column.table if column.table else None
                col_name = column.name
                
                if table and col_name and table.lower() in self.lattice.tables:
                    table_info = self.lattice.tables[table.lower()]
                    if col_name.lower() in table_info.columns:
                        table_info.columns[col_name.lower()].is_aggregated = True
        
        # Find GROUP BY columns
        for group_by in parsed.find_all(exp.Group):
            for column in group_by.find_all(exp.Column):
                table = column.table if column.table else None
                col_name = column.name
                
                if table and col_name and table.lower() in self.lattice.tables:
                    table_info = self.lattice.tables[table.lower()]
                    if col_name.lower() in table_info.columns:
                        table_info.columns[col_name.lower()].is_group_by = True
    
    def _build_subsumption_graph(self) -> None:
        """
        Build subsumption graph to identify redundant extraction objectives.
        If Q1 filters on 'Status' and Q2 filters on 'Status', merge them.
        """
        logger.info("Building subsumption graph")
        
        # For each table, group columns by their predicates
        for table_name, table_info in self.lattice.tables.items():
            column_groups = defaultdict(list)
            
            for col_name, col_info in table_info.columns.items():
                # Group by predicate set
                pred_key = frozenset(col_info.predicates)
                column_groups[pred_key].append(col_name)
            
            # Build subsumption relationships
            for pred_key, columns in column_groups.items():
                if len(columns) > 1:
                    # These columns can be extracted together
                    base_col = columns[0]
                    self.lattice.subsumption_graph[f"{table_name}.{base_col}"] = [
                        f"{table_name}.{col}" for col in columns[1:]
                    ]
        
        logger.info(f"Built subsumption graph with {len(self.lattice.subsumption_graph)} groups")
    
    def _identify_semantic_types(self) -> None:
        """
        Identify semantic types for columns using LLM.
        Uses simple heuristics if LLM is not available.
        """
        logger.info("Identifying semantic types")
        
        for table_name, table_info in self.lattice.tables.items():
            for col_name, col_info in table_info.columns.items():
                # Use heuristics first
                semantic_type = self._heuristic_semantic_type(col_name)
                
                # If LLM is available and heuristic is uncertain, use LLM
                if semantic_type == "OTHER" and self.llm_client:
                    semantic_type = self._llm_semantic_type(col_name, table_name)
                
                col_info.semantic_type = semantic_type
        
        logger.info("Semantic type identification complete")
    
    def _heuristic_semantic_type(self, column_name: str) -> str:
        """Use heuristics to identify semantic type."""
        col_lower = column_name.lower()
        
        # Person names
        if any(keyword in col_lower for keyword in ['name', 'patient', 'doctor', 'physician', 'person', 'author']):
            return "PERSON"
        
        # Organizations
        if any(keyword in col_lower for keyword in ['company', 'organization', 'org', 'institution', 'hospital']):
            return "ORG"
        
        # Dates
        if any(keyword in col_lower for keyword in ['date', 'time', 'year', 'month', 'day', 'timestamp']):
            return "DATE"
        
        # Locations
        if any(keyword in col_lower for keyword in ['city', 'state', 'country', 'location', 'address', 'place']):
            return "GPE"
        
        # Codes
        if any(keyword in col_lower for keyword in ['code', 'id', 'identifier', 'number', 'icd']):
            return "CODE"
        
        # Money
        if any(keyword in col_lower for keyword in ['price', 'cost', 'amount', 'salary', 'revenue', 'payment']):
            return "MONEY"
        
        # Quantities
        if any(keyword in col_lower for keyword in ['count', 'quantity', 'total', 'sum', 'average']):
            return "QUANTITY"
        
        return "OTHER"
    
    def _llm_semantic_type(self, column_name: str, table_name: str) -> str:
        """Use LLM to identify semantic type."""
        if not self.llm_client:
            return "OTHER"
        
        try:
            prompt = f"""Given a database column, identify its semantic type.

Column: {column_name}
Table: {table_name}

Semantic types:
- PERSON: Names of people
- ORG: Organizations, companies, institutions
- DATE: Dates, times, timestamps
- GPE: Locations, cities, countries
- CODE: Codes, identifiers, IDs
- MONEY: Monetary values
- QUANTITY: Numeric quantities
- PRODUCT: Products, items
- EVENT: Events, activities
- OTHER: Other types

Respond with only the semantic type (one word).
"""
            
            response = self.llm_client.generate(prompt, max_tokens=10, temperature=0.0)
            semantic_type = response.strip().upper()
            
            if semantic_type in SEMANTIC_TYPES:
                return semantic_type
            else:
                return "OTHER"
        
        except Exception as e:
            logger.warning(f"LLM semantic type identification failed: {e}")
            return "OTHER"
    
    # ========================================================================
    # Query Methods
    # ========================================================================
    
    def get_extraction_plan(self) -> Dict[str, Any]:
        """
        Generate extraction plan from lattice.
        Returns a structured plan for extraction.
        """
        plan = {
            "tables": {},
            "join_pairs": self.lattice.join_pairs,
            "subsumption_groups": self.lattice.subsumption_graph
        }
        
        for table_name, table_info in self.lattice.tables.items():
            plan["tables"][table_name] = {
                "columns": {},
                "predicates": table_info.predicates,
                "referenced_in_joins": table_info.referenced_in_joins
            }
            
            for col_name, col_info in table_info.columns.items():
                plan["tables"][table_name]["columns"][col_name] = {
                    "semantic_type": col_info.semantic_type,
                    "predicates": list(col_info.predicates),
                    "is_join_key": col_info.is_join_key,
                    "is_group_by": col_info.is_group_by,
                    "is_aggregated": col_info.is_aggregated
                }
        
        return plan
    
    def get_table_schema(self, table_name: str) -> Dict[str, str]:
        """
        Get schema for a table (column -> semantic_type mapping).
        """
        if table_name not in self.lattice.tables:
            return {}
        
        table_info = self.lattice.tables[table_name]
        schema = {}
        
        for col_name, col_info in table_info.columns.items():
            schema[col_name] = col_info.semantic_type
        
        return schema
    
    def get_required_columns(self, table_name: str) -> List[str]:
        """Get list of required columns for a table."""
        if table_name not in self.lattice.tables:
            return []
        
        return list(self.lattice.tables[table_name].columns.keys())
    
    def get_predicates_for_column(
        self,
        table_name: str,
        column_name: str
    ) -> Set[str]:
        """Get all predicates for a specific column."""
        if table_name not in self.lattice.tables:
            return set()
        
        table_info = self.lattice.tables[table_name]
        if column_name not in table_info.columns:
            return set()
        
        return table_info.columns[column_name].predicates

    def get_predicate_literals(
        self,
        table_name: str,
        column_name: str
    ) -> Set[str]:
        """
        Return the set of raw equality-predicate literal values for a column.
        e.g. if queries have WHERE country = 'USA' and WHERE country = 'Canada'
        this returns {'USA', 'Canada'}.
        """
        if table_name not in self.lattice.tables:
            return set()
        table_info = self.lattice.tables[table_name]
        if column_name not in table_info.columns:
            return set()
        return table_info.columns[column_name].predicate_literals

    def get_normalization_hints(self, table_name: str) -> Dict[str, List[str]]:
        """
        Build a column → [expected literal values] map for all columns in a table
        that have equality predicates in the workload.  Used by the extractor to
        guide value normalization at extraction time.
        """
        if table_name not in self.lattice.tables:
            return {}
        hints: Dict[str, List[str]] = {}
        for col_name, col_info in self.lattice.tables[table_name].columns.items():
            if col_info.predicate_literals:
                hints[col_name] = sorted(col_info.predicate_literals)
        return hints
    
    def should_extract_together(
        self,
        table_name: str,
        columns: List[str]
    ) -> bool:
        """
        Check if columns should be extracted together based on subsumption.
        """
        # Check if any column is in subsumption graph
        for col in columns:
            key = f"{table_name}.{col}"
            if key in self.lattice.subsumption_graph:
                return True
        
        return False


# ============================================================================
# Workload Parser Utilities
# ============================================================================

def parse_sql_file(file_path: str) -> List[str]:
    """
    Parse SQL file and extract individual queries.
    Handles comments and multi-line queries.
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Remove comments
    content = re.sub(r'--.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # Split by semicolon
    queries = [q.strip() for q in content.split(';') if q.strip()]
    
    return queries


def load_workload_from_directory(directory: str) -> List[str]:
    """
    Load all SQL queries from a directory.
    """
    import os
    from pathlib import Path
    
    queries = []
    dir_path = Path(directory)
    
    for sql_file in dir_path.glob("**/*.sql"):
        file_queries = parse_sql_file(str(sql_file))
        queries.extend(file_queries)
    
    logger.info(f"Loaded {len(queries)} queries from {directory}")
    
    return queries

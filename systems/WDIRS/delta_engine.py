"""
Delta Engine for WDIRS.
Implements runtime incremental query execution with row and column deltas.
"""

import json
import logging
import time
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
import uuid

import sqlglot
from sqlglot import parse_one, exp

from data_layer import DataLayer, TextChunk
from lattice_planner import LatticePlanner
from extractor import ConstrainedExtractor
from entity_resolver import EntityResolver, EntityMention, extract_mentions_from_records, apply_canonical_map
from config import STATUS_PARTIAL, STATUS_FULL

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class DeltaType(Enum):
    """Type of delta required."""
    CACHE_HIT = "cache_hit"  # Query can be answered from existing data
    ROW_DELTA = "row_delta"  # Need to extract new rows
    COLUMN_DELTA = "column_delta"  # Need to enrich existing rows
    MIXED_DELTA = "mixed_delta"  # Need both new rows and new columns
    JOIN_ALIGNMENT = "join_alignment"  # Need to align join keys

@dataclass
class DeltaPlan:
    """Plan for executing a query with deltas."""
    delta_type: DeltaType
    missing_columns: List[str]
    missing_predicates: List[str]
    tables_involved: List[str]
    requires_extraction: bool
    requires_enrichment: bool
    requires_join_alignment: bool
    estimated_cost: float

@dataclass
class DeltaExecutionResult:
    """Result of delta execution."""
    success: bool
    rows_extracted: int
    rows_enriched: int
    execution_time: float
    error: Optional[str] = None


# ============================================================================
# Delta Engine
# ============================================================================

class DeltaEngine:
    """
    Implements runtime incremental query execution.
    Calculates and executes deltas to answer queries efficiently.
    """
    
    def __init__(
        self,
        data_layer: DataLayer,
        lattice_planner: LatticePlanner,
        extractor: ConstrainedExtractor,
        entity_resolver: EntityResolver
    ):
        """Initialize delta engine."""
        self.data_layer = data_layer
        self.lattice_planner = lattice_planner
        self.extractor = extractor
        self.entity_resolver = entity_resolver
        
        logger.info("DeltaEngine initialized")
    
    # ========================================================================
    # Query Analysis
    # ========================================================================
    
    def analyze_query(self, query: str) -> DeltaPlan:
        """
        Analyze query and determine delta plan.
        
        Args:
            query: SQL query string
            
        Returns:
            DeltaPlan with execution strategy
        """
        logger.info("Analyzing query for delta calculation")
        
        # Parse query
        try:
            parsed = parse_one(query, dialect="postgres")
        except Exception as e:
            logger.error(f"Failed to parse query: {e}")
            raise
        
        # Extract query components
        tables = self._extract_tables(parsed)
        columns = self._extract_columns(parsed)
        predicates = self._extract_predicates(parsed)
        joins = self._extract_joins(parsed)
        
        logger.debug(f"Query components: tables={tables}, columns={len(columns)}, "
                    f"predicates={len(predicates)}, joins={len(joins)}")
        
        # Check materialization for each table
        missing_columns_all = []
        missing_predicates_all = []
        
        for table_name in tables:
            # Get required columns for this table
            table_columns = [col for tbl, col in columns if tbl == table_name]
            table_predicates = [pred for tbl, pred in predicates if tbl == table_name]
            
            # Check metadata registry
            is_complete, missing_cols, missing_preds = self.data_layer.check_materialization(
                table_name,
                table_columns,
                table_predicates
            )
            
            missing_columns_all.extend(missing_cols)
            missing_predicates_all.extend(missing_preds)
        
        # Determine delta type
        delta_type = self._determine_delta_type(
            missing_columns_all,
            missing_predicates_all,
            joins
        )
        
        # Build delta plan
        plan = DeltaPlan(
            delta_type=delta_type,
            missing_columns=missing_columns_all,
            missing_predicates=missing_predicates_all,
            tables_involved=list(tables),
            requires_extraction=delta_type in [DeltaType.ROW_DELTA, DeltaType.MIXED_DELTA],
            requires_enrichment=delta_type in [DeltaType.COLUMN_DELTA, DeltaType.MIXED_DELTA],
            requires_join_alignment=delta_type == DeltaType.JOIN_ALIGNMENT or len(joins) > 0,
            estimated_cost=self._estimate_cost(delta_type, missing_columns_all, missing_predicates_all)
        )
        
        logger.info(f"Delta plan: {plan.delta_type.value}, "
                   f"missing_cols={len(missing_columns_all)}, "
                   f"missing_preds={len(missing_predicates_all)}")
        
        return plan
    
    def _extract_tables(self, parsed: exp.Expression) -> Set[str]:
        """Extract table names from parsed query."""
        tables = set()
        for table in parsed.find_all(exp.Table):
            if table.name:
                tables.add(table.name.lower())
        return tables
    
    def _extract_columns(self, parsed: exp.Expression) -> List[Tuple[str, str]]:
        """Extract (table, column) pairs."""
        columns = []
        
        for select in parsed.find_all(exp.Select):
            for projection in select.expressions:
                if isinstance(projection, exp.Column):
                    table = projection.table if projection.table else None
                    column = projection.name
                    if table and column:
                        columns.append((table.lower(), column.lower()))
        
        for where in parsed.find_all(exp.Where):
            for column in where.find_all(exp.Column):
                table = column.table if column.table else None
                col_name = column.name
                if table and col_name:
                    columns.append((table.lower(), col_name.lower()))
        
        return columns
    
    def _extract_predicates(self, parsed: exp.Expression) -> List[Tuple[str, str]]:
        """Extract (table, predicate) pairs."""
        predicates = []
        
        for where in parsed.find_all(exp.Where):
            for comparison in where.find_all(exp.EQ, exp.GT, exp.LT, exp.GTE, exp.LTE, exp.NEQ):
                left = comparison.left
                right = comparison.right
                
                if isinstance(left, exp.Column):
                    table = left.table if left.table else None
                    column = left.name
                    
                    if table and column:
                        operator = self._get_operator(comparison)
                        value = self._get_value(right)
                        predicate = f"{column} {operator} {value}"
                        predicates.append((table.lower(), predicate))
        
        return predicates
    
    def _extract_joins(self, parsed: exp.Expression) -> List[Tuple[str, str, str]]:
        """Extract join information as (left_table, right_table, join_column)."""
        joins = []
        
        for join in parsed.find_all(exp.Join):
            left_table = None
            right_table = None
            join_column = None
            
            for column in join.find_all(exp.Column):
                table = column.table
                col_name = column.name
                
                if table:
                    if left_table is None:
                        left_table = table.lower()
                        join_column = col_name.lower()
                    elif right_table is None and table.lower() != left_table:
                        right_table = table.lower()
            
            if left_table and right_table and join_column:
                joins.append((left_table, right_table, join_column))
        
        return joins
    
    def _get_operator(self, comparison: exp.Expression) -> str:
        """Get operator string."""
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
        return "="
    
    def _get_value(self, expr: exp.Expression) -> str:
        """Extract value from expression."""
        if isinstance(expr, exp.Literal):
            return expr.this
        elif isinstance(expr, exp.Column):
            return expr.name
        return str(expr)
    
    def _determine_delta_type(
        self,
        missing_columns: List[str],
        missing_predicates: List[str],
        joins: List[Tuple[str, str, str]]
    ) -> DeltaType:
        """Determine type of delta required."""
        has_missing_columns = len(missing_columns) > 0
        has_missing_predicates = len(missing_predicates) > 0
        has_joins = len(joins) > 0
        
        if not has_missing_columns and not has_missing_predicates:
            if has_joins:
                return DeltaType.JOIN_ALIGNMENT
            return DeltaType.CACHE_HIT
        
        if has_missing_columns and has_missing_predicates:
            return DeltaType.MIXED_DELTA
        
        if has_missing_columns:
            return DeltaType.COLUMN_DELTA
        
        if has_missing_predicates:
            return DeltaType.ROW_DELTA
        
        return DeltaType.CACHE_HIT
    
    def _estimate_cost(
        self,
        delta_type: DeltaType,
        missing_columns: List[str],
        missing_predicates: List[str]
    ) -> float:
        """Estimate execution cost."""
        if delta_type == DeltaType.CACHE_HIT:
            return 0.1
        
        if delta_type == DeltaType.ROW_DELTA:
            return len(missing_predicates) * 2.0
        
        if delta_type == DeltaType.COLUMN_DELTA:
            return len(missing_columns) * 1.5
        
        if delta_type == DeltaType.MIXED_DELTA:
            return len(missing_columns) * 1.5 + len(missing_predicates) * 2.0
        
        if delta_type == DeltaType.JOIN_ALIGNMENT:
            return 3.0
        
        return 1.0
    
    # ========================================================================
    # Delta Execution
    # ========================================================================
    
    def execute_delta(
        self,
        plan: DeltaPlan,
        query: str
    ) -> DeltaExecutionResult:
        """
        Execute delta plan to materialize missing data.
        
        Args:
            plan: Delta plan
            query: Original SQL query
            
        Returns:
            DeltaExecutionResult
        """
        logger.info(f"Executing delta: {plan.delta_type.value}")
        start_time = time.time()
        
        rows_extracted = 0
        rows_enriched = 0
        
        try:
            if plan.delta_type == DeltaType.CACHE_HIT:
                # No delta needed
                logger.info("Cache hit - no delta execution needed")
            
            elif plan.delta_type == DeltaType.ROW_DELTA:
                # Execute row delta
                rows_extracted = self._execute_row_delta(
                    plan.tables_involved,
                    plan.missing_predicates
                )
            
            elif plan.delta_type == DeltaType.COLUMN_DELTA:
                # Execute column delta
                rows_enriched = self._execute_column_delta(
                    plan.tables_involved,
                    plan.missing_columns
                )
            
            elif plan.delta_type == DeltaType.MIXED_DELTA:
                # Execute both deltas
                rows_extracted = self._execute_row_delta(
                    plan.tables_involved,
                    plan.missing_predicates
                )
                rows_enriched = self._execute_column_delta(
                    plan.tables_involved,
                    plan.missing_columns
                )
            
            elif plan.delta_type == DeltaType.JOIN_ALIGNMENT:
                # Execute join alignment
                self._execute_join_alignment(query)
            
            execution_time = time.time() - start_time
            
            return DeltaExecutionResult(
                success=True,
                rows_extracted=rows_extracted,
                rows_enriched=rows_enriched,
                execution_time=execution_time
            )
        
        except Exception as e:
            logger.error(f"Delta execution failed: {e}")
            execution_time = time.time() - start_time
            
            return DeltaExecutionResult(
                success=False,
                rows_extracted=rows_extracted,
                rows_enriched=rows_enriched,
                execution_time=execution_time,
                error=str(e)
            )
    
    def _execute_row_delta(
        self,
        tables: List[str],
        missing_predicates: List[str]
    ) -> int:
        """
        Execute row delta: extract new rows matching missing predicates.
        
        Returns:
            Number of rows extracted
        """
        logger.info(f"Executing row delta for {len(tables)} tables")
        
        total_rows = 0
        
        for table_name in tables:
            # Get candidate chunks
            candidate_chunk_ids = self.data_layer.get_candidates(table_name)
            
            if not candidate_chunk_ids:
                logger.warning(f"No candidate chunks for {table_name}")
                continue
            
            # Get chunks
            chunks = self.data_layer.get_chunks_by_ids(candidate_chunk_ids)
            
            # Filter chunks for missing predicates
            filtered_chunks = self._filter_chunks_by_predicates(
                chunks,
                missing_predicates
            )
            
            if not filtered_chunks:
                logger.info(f"No chunks match missing predicates for {table_name}")
                continue
            
            # Get schema
            schema = self.lattice_planner.get_table_schema(table_name)
            
            # Get stabilized schema
            stabilized = self.extractor.get_stabilized_schema(table_name)
            constrained_keys = stabilized.frozen_keys if stabilized else None
            
            # Extract from filtered chunks
            chunk_texts = [c.content for c in filtered_chunks]
            chunk_ids = [c.chunk_id for c in filtered_chunks]
            
            results = self.extractor.extract_batch(
                chunk_texts,
                chunk_ids,
                table_name,
                schema,
                constrained_keys
            )
            
            # Insert into database
            for result in results:
                for record in result.records:
                    row_id = str(uuid.uuid4())
                    
                    # Insert record (would need SQL generation here)
                    # For now, just count
                    total_rows += 1
                    
                    # Insert provenance
                    self.data_layer.insert_provenance(
                        row_id,
                        table_name,
                        [result.chunk_id]
                    )
            
            # Update metadata registry
            for predicate in missing_predicates:
                self.data_layer.update_metadata(
                    table_name,
                    predicate.split()[0],  # Extract column name
                    [predicate],
                    STATUS_PARTIAL,
                    total_rows
                )
        
        logger.info(f"Row delta complete: {total_rows} rows extracted")
        return total_rows
    
    def _execute_column_delta(
        self,
        tables: List[str],
        missing_columns: List[str]
    ) -> int:
        """
        Execute column delta: enrich existing rows with missing columns.
        
        Returns:
            Number of rows enriched
        """
        logger.info(f"Executing column delta for {len(tables)} tables")
        
        total_rows = 0
        
        for table_name in tables:
            # Get existing rows (would query from SQL table)
            # For now, simulate
            
            # Get provenance for existing rows
            provenance_records = self.data_layer.get_provenance(table_name=table_name)
            
            if not provenance_records:
                logger.warning(f"No provenance records for {table_name}")
                continue
            
            # Get chunks for these rows
            all_chunk_ids = []
            for prov in provenance_records:
                all_chunk_ids.extend(prov.chunk_ids)
            
            chunks = self.data_layer.get_chunks_by_ids(all_chunk_ids)
            
            # Get schema
            schema = self.lattice_planner.get_table_schema(table_name)
            
            # Enrich records (would need to load existing records from SQL)
            # For now, just count
            total_rows += len(provenance_records)
            
            # Update metadata registry
            for column in missing_columns:
                self.data_layer.update_metadata(
                    table_name,
                    column,
                    [],
                    STATUS_FULL,
                    total_rows
                )
        
        logger.info(f"Column delta complete: {total_rows} rows enriched")
        return total_rows
    
    def _execute_join_alignment(self, query: str) -> None:
        """Execute JIT join alignment."""
        logger.info("Executing join alignment")
        
        # Parse query to find joins
        parsed = parse_one(query, dialect="postgres")
        joins = self._extract_joins(parsed)
        
        for left_table, right_table, join_column in joins:
            # Get values from both tables (would query from SQL)
            # For now, simulate
            left_values = []
            right_values = []
            
            # Align join keys
            canonical_map = self.entity_resolver.align_join_keys(
                left_values,
                right_values,
                left_table,
                right_table,
                join_column
            )
            
            # Update tables with aligned values (would update SQL tables)
            logger.info(f"Aligned {len(canonical_map)} join keys")
    
    def _filter_chunks_by_predicates(
        self,
        chunks: List[TextChunk],
        predicates: List[str]
    ) -> List[TextChunk]:
        """Filter chunks that might contain data for missing predicates."""
        if not predicates:
            return chunks
        
        # Extract keywords from predicates
        keywords = set()
        for predicate in predicates:
            # Simple keyword extraction
            parts = predicate.split()
            for part in parts:
                if part not in ['=', '>', '<', '>=', '<=', '!=', 'AND', 'OR']:
                    keywords.add(part.lower().strip("'\""))
        
        # Filter chunks
        filtered = []
        for chunk in chunks:
            content_lower = chunk.content.lower()
            
            # Check if any keyword is in chunk
            if any(keyword in content_lower for keyword in keywords):
                filtered.append(chunk)
        
        return filtered
    
    # ========================================================================
    # Query Execution
    # ========================================================================
    
    def execute_query(self, query: str) -> Tuple[List[Dict[str, Any]], DeltaExecutionResult]:
        """
        Execute query with delta calculation.
        
        Args:
            query: SQL query string
            
        Returns:
            (results, delta_execution_result)
        """
        logger.info("Executing query with delta engine")
        
        # Analyze query
        plan = self.analyze_query(query)
        
        # Execute delta if needed
        delta_result = self.execute_delta(plan, query)
        
        if not delta_result.success:
            logger.error("Delta execution failed")
            return [], delta_result
        
        # Execute SQL query (would use actual SQL engine here)
        # For now, return empty results
        results = []
        
        return results, delta_result


# ============================================================================
# Utility Functions
# ============================================================================

def build_insert_statement(
    table_name: str,
    record: Dict[str, Any]
) -> str:
    """Build SQL INSERT statement."""
    columns = list(record.keys())
    values = list(record.values())
    
    columns_str = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(values))
    
    sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
    
    return sql


def build_update_statement(
    table_name: str,
    record: Dict[str, Any],
    row_id: str
) -> str:
    """Build SQL UPDATE statement."""
    set_clauses = [f"{col} = %s" for col in record.keys()]
    set_str = ", ".join(set_clauses)
    
    sql = f"UPDATE {table_name} SET {set_str} WHERE row_id = '{row_id}'"
    
    return sql

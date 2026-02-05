"""
Workload Planner: Multi-Query Optimization (MQO) using Predicate Lattice.

This module implements a rigorous MQO strategy inspired by the Harinarayan
Data Cube lattice paper, adapted for LLM-based extraction optimization.

Key Innovation: Minimize LLM invocations per chunk (not disk I/O).
"""
import json
from typing import List, Dict, Set, Optional, Tuple, Any
from collections import defaultdict
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path

import sqlglot
from sqlglot import exp, parse_one
from sqlglot.optimizer.normalize import normalize
import networkx as nx
from loguru import logger

from models import Query, Predicate, ExtractionTask, WorkloadPlan, TableSchema
from config import QAIRSConfig
from sieve import Sieve


# ============================================================================
# Data Structures for Predicate Analysis
# ============================================================================

class PredicateOp(str, Enum):
    """Predicate operation types."""
    EQ = "eq"           # =
    NEQ = "neq"         # !=
    GT = "gt"           # >
    GTE = "gte"         # >=
    LT = "lt"           # <
    LTE = "lte"         # <=
    IN = "in"           # IN (...)
    LIKE = "like"       # LIKE
    AND = "and"         # AND
    OR = "or"           # OR


@dataclass
class NormalizedPredicate:
    """
    A normalized predicate in DNF (Disjunctive Normal Form).
    
    DNF: OR of ANDs, e.g., (A AND B) OR (C AND D)
    """
    query_id: str
    table: str
    conditions: List[Tuple[str, PredicateOp, Any]]  # [(column, op, value), ...]
    is_dnf: bool = True
    
    def __hash__(self):
        return hash((self.query_id, self.table, tuple(self.conditions)))
    
    def to_sql_where(self) -> str:
        """Convert back to SQL WHERE clause."""
        if not self.conditions:
            return ""
        
        parts = []
        for col, op, val in self.conditions:
            if op == PredicateOp.EQ:
                parts.append(f"{col} = {self._format_value(val)}")
            elif op == PredicateOp.NEQ:
                parts.append(f"{col} != {self._format_value(val)}")
            elif op == PredicateOp.GT:
                parts.append(f"{col} > {self._format_value(val)}")
            elif op == PredicateOp.GTE:
                parts.append(f"{col} >= {self._format_value(val)}")
            elif op == PredicateOp.LT:
                parts.append(f"{col} < {self._format_value(val)}")
            elif op == PredicateOp.LTE:
                parts.append(f"{col} <= {self._format_value(val)}")
            elif op == PredicateOp.IN:
                vals = ", ".join([self._format_value(v) for v in val])
                parts.append(f"{col} IN ({vals})")
            elif op == PredicateOp.LIKE:
                parts.append(f"{col} LIKE {self._format_value(val)}")
        
        return " AND ".join(parts)
    
    def _format_value(self, val: Any) -> str:
        """Format value for SQL."""
        if isinstance(val, str):
            return f"'{val}'"
        return str(val)
    
    def get_categorical_values(self, column: str) -> Set[Any]:
        """Extract categorical values for a column (from EQ or IN predicates)."""
        values = set()
        for col, op, val in self.conditions:
            if col == column:
                if op == PredicateOp.EQ:
                    values.add(val)
                elif op == PredicateOp.IN:
                    values.update(val)
        return values


@dataclass
class MergedTask:
    """
    Represents a merged extraction task after optimization.
    """
    task_id: str
    target_table: str
    trigger_queries: List[str]  # Original query IDs
    merged_predicate: NormalizedPredicate
    sieve_filter: Dict[str, Any]
    extraction_hint: str
    candidate_chunks: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0  # Estimated LLM cost in USD
    estimated_time: float = 0.0  # Estimated time in seconds


# ============================================================================
# SQL Parser
# ============================================================================

class SQLParser:
    """
    Parse SQL queries using sqlglot and extract normalized predicates.
    """
    
    @staticmethod
    def parse_query(sql: str, query_id: str) -> Optional[NormalizedPredicate]:
        """
        Parse SQL query and extract normalized predicate.
        
        Args:
            sql: SQL query string
            query_id: Unique identifier for the query
        
        Returns:
            NormalizedPredicate or None if parsing fails
        """
        try:
            # Parse SQL
            parsed = parse_one(sql, read="postgres")
            
            # Extract table
            table_node = parsed.find(exp.Table)
            if not table_node:
                logger.warning(f"No table found in query: {sql}")
                return None
            table = table_node.name
            
            # Extract WHERE clause
            where_node = parsed.find(exp.Where)
            if not where_node:
                # No WHERE clause - matches all rows
                return NormalizedPredicate(
                    query_id=query_id,
                    table=table,
                    conditions=[]
                )
            
            # Normalize to DNF
            normalized = normalize(where_node.this)
            
            # Extract conditions
            conditions = SQLParser._extract_conditions(normalized)
            
            return NormalizedPredicate(
                query_id=query_id,
                table=table,
                conditions=conditions
            )
        
        except Exception as e:
            logger.error(f"Failed to parse query '{sql}': {e}")
            return None
    
    @staticmethod
    def _extract_conditions(node: exp.Expression) -> List[Tuple[str, PredicateOp, Any]]:
        """
        Recursively extract conditions from AST node.
        
        Returns list of (column, operator, value) tuples.
        """
        conditions = []
        
        if isinstance(node, exp.EQ):
            col, val = SQLParser._extract_binary_op(node)
            if col and val is not None:
                conditions.append((col, PredicateOp.EQ, val))
        
        elif isinstance(node, exp.NEQ):
            col, val = SQLParser._extract_binary_op(node)
            if col and val is not None:
                conditions.append((col, PredicateOp.NEQ, val))
        
        elif isinstance(node, exp.GT):
            col, val = SQLParser._extract_binary_op(node)
            if col and val is not None:
                conditions.append((col, PredicateOp.GT, val))
        
        elif isinstance(node, exp.GTE):
            col, val = SQLParser._extract_binary_op(node)
            if col and val is not None:
                conditions.append((col, PredicateOp.GTE, val))
        
        elif isinstance(node, exp.LT):
            col, val = SQLParser._extract_binary_op(node)
            if col and val is not None:
                conditions.append((col, PredicateOp.LT, val))
        
        elif isinstance(node, exp.LTE):
            col, val = SQLParser._extract_binary_op(node)
            if col and val is not None:
                conditions.append((col, PredicateOp.LTE, val))
        
        elif isinstance(node, exp.In):
            col = SQLParser._get_column_name(node.this)
            vals = SQLParser._extract_in_values(node.expressions)
            if col and vals:
                conditions.append((col, PredicateOp.IN, vals))
        
        elif isinstance(node, exp.Like):
            col, val = SQLParser._extract_binary_op(node)
            if col and val is not None:
                conditions.append((col, PredicateOp.LIKE, val))
        
        elif isinstance(node, exp.And):
            # Recursively extract from both sides
            for child in node.args.values():
                if isinstance(child, exp.Expression):
                    conditions.extend(SQLParser._extract_conditions(child))
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, exp.Expression):
                            conditions.extend(SQLParser._extract_conditions(item))
        
        elif isinstance(node, exp.Or):
            # For OR, we need to handle this differently
            # For now, we extract all conditions (simplified)
            for child in node.args.values():
                if isinstance(child, exp.Expression):
                    conditions.extend(SQLParser._extract_conditions(child))
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, exp.Expression):
                            conditions.extend(SQLParser._extract_conditions(item))
        
        return conditions
    
    @staticmethod
    def _extract_binary_op(node: exp.Expression) -> Tuple[Optional[str], Optional[Any]]:
        """Extract column and value from binary operation."""
        left = node.this
        right = node.expression
        
        col = SQLParser._get_column_name(left)
        val = SQLParser._get_literal_value(right)
        
        return col, val
    
    @staticmethod
    def _get_column_name(node: exp.Expression) -> Optional[str]:
        """Extract column name from node."""
        if isinstance(node, exp.Column):
            return node.name
        elif isinstance(node, exp.Identifier):
            return node.name
        return None
    
    @staticmethod
    def _get_literal_value(node: exp.Expression) -> Optional[Any]:
        """Extract literal value from node."""
        if isinstance(node, exp.Literal):
            val = node.this
            # Try to convert to appropriate type
            if node.is_string:
                return val
            elif node.is_int:
                return int(val)
            elif node.is_number:
                return float(val)
            return val
        return None
    
    @staticmethod
    def _extract_in_values(nodes: List[exp.Expression]) -> List[Any]:
        """Extract values from IN clause."""
        values = []
        for node in nodes:
            val = SQLParser._get_literal_value(node)
            if val is not None:
                values.append(val)
        return values


# ============================================================================
# Predicate Lattice Builder
# ============================================================================

class PredicateLattice:
    """
    Build and analyze the predicate subsumption lattice using NetworkX.
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()
        self.predicates: Dict[str, NormalizedPredicate] = {}
    
    def add_predicate(self, pred: NormalizedPredicate) -> None:
        """Add a predicate to the lattice."""
        self.predicates[pred.query_id] = pred
        self.graph.add_node(pred.query_id, predicate=pred)
    
    def build_subsumption_edges(self) -> None:
        """
        Build edges representing subsumption relationships.
        
        Edge A -> B means A subsumes B (A is more general).
        """
        query_ids = list(self.predicates.keys())
        
        for i, qid1 in enumerate(query_ids):
            for qid2 in query_ids[i+1:]:
                pred1 = self.predicates[qid1]
                pred2 = self.predicates[qid2]
                
                # Only compare predicates on same table
                if pred1.table != pred2.table:
                    continue
                
                # Check subsumption
                if self._subsumes(pred1, pred2):
                    self.graph.add_edge(qid1, qid2)
                elif self._subsumes(pred2, pred1):
                    self.graph.add_edge(qid2, qid1)
    
    def _subsumes(self, p1: NormalizedPredicate, p2: NormalizedPredicate) -> bool:
        """
        Check if p1 subsumes p2 (p1 is more general than p2).
        
        Examples:
        - No predicates subsumes everything
        - "cost > 500" subsumes "cost > 1000"
        - "status IN ('A', 'B', 'C')" subsumes "status = 'A'"
        """
        # Empty predicate subsumes all
        if not p1.conditions:
            return True
        if not p2.conditions:
            return False
        
        # Group conditions by column
        p1_by_col = defaultdict(list)
        p2_by_col = defaultdict(list)
        
        for col, op, val in p1.conditions:
            p1_by_col[col].append((op, val))
        for col, op, val in p2.conditions:
            p2_by_col[col].append((op, val))
        
        # Check if p1 subsumes p2 for each column
        for col in p2_by_col:
            if col not in p1_by_col:
                return False
            
            # Check subsumption for this column
            if not self._subsumes_column(p1_by_col[col], p2_by_col[col]):
                return False
        
        return True
    
    def _subsumes_column(
        self,
        conds1: List[Tuple[PredicateOp, Any]],
        conds2: List[Tuple[PredicateOp, Any]]
    ) -> bool:
        """Check if conditions on a single column subsume."""
        # Extract values for EQ/IN operations
        vals1 = set()
        vals2 = set()
        
        for op, val in conds1:
            if op == PredicateOp.EQ:
                vals1.add(val)
            elif op == PredicateOp.IN:
                vals1.update(val)
        
        for op, val in conds2:
            if op == PredicateOp.EQ:
                vals2.add(val)
            elif op == PredicateOp.IN:
                vals2.update(val)
        
        # If both are categorical, check set containment
        if vals1 and vals2:
            return vals2.issubset(vals1)
        
        # Range subsumption logic
        # Extract range conditions
        ranges1 = self._extract_ranges(conds1)
        ranges2 = self._extract_ranges(conds2)
        
        if ranges1 and ranges2:
            return self._range_subsumes(ranges1, ranges2)
        
        return False
    
    def _extract_ranges(self, conds: List[Tuple[PredicateOp, Any]]) -> Dict[str, Any]:
        """Extract range bounds from conditions."""
        ranges = {'min': None, 'max': None, 'min_inclusive': True, 'max_inclusive': True}
        
        for op, val in conds:
            try:
                val_num = float(val)
            except (ValueError, TypeError):
                continue
            
            if op == PredicateOp.GT:
                if ranges['min'] is None or val_num > ranges['min']:
                    ranges['min'] = val_num
                    ranges['min_inclusive'] = False
            elif op == PredicateOp.GTE:
                if ranges['min'] is None or val_num > ranges['min']:
                    ranges['min'] = val_num
                    ranges['min_inclusive'] = True
            elif op == PredicateOp.LT:
                if ranges['max'] is None or val_num < ranges['max']:
                    ranges['max'] = val_num
                    ranges['max_inclusive'] = False
            elif op == PredicateOp.LTE:
                if ranges['max'] is None or val_num < ranges['max']:
                    ranges['max'] = val_num
                    ranges['max_inclusive'] = True
        
        return ranges if ranges['min'] is not None or ranges['max'] is not None else {}
    
    def _range_subsumes(self, r1: Dict[str, Any], r2: Dict[str, Any]) -> bool:
        """
        Check if range r1 subsumes r2 (r1 is wider).
        
        Example: cost > 500 subsumes cost > 1000
        """
        # Check lower bound
        if r2['min'] is not None:
            if r1['min'] is None:
                return False
            if r1['min'] > r2['min']:
                return False
            if r1['min'] == r2['min'] and not r1['min_inclusive'] and r2['min_inclusive']:
                return False
        
        # Check upper bound
        if r2['max'] is not None:
            if r1['max'] is None:
                return False
            if r1['max'] < r2['max']:
                return False
            if r1['max'] == r2['max'] and not r1['max_inclusive'] and r2['max_inclusive']:
                return False
        
        return True
    
    def find_siblings(self) -> List[List[str]]:
        """
        Find sibling nodes (queries with no subsumption relationship).
        
        These are candidates for merging.
        """
        siblings = []
        processed = set()
        
        # Group by table
        by_table = defaultdict(list)
        for qid, pred in self.predicates.items():
            by_table[pred.table].append(qid)
        
        # For each table, find siblings
        for table, qids in by_table.items():
            # Find nodes with no edges between them
            for i, qid1 in enumerate(qids):
                if qid1 in processed:
                    continue
                
                group = [qid1]
                for qid2 in qids[i+1:]:
                    if qid2 in processed:
                        continue
                    
                    # Check if they're siblings (no edge in either direction)
                    if not self.graph.has_edge(qid1, qid2) and \
                       not self.graph.has_edge(qid2, qid1):
                        # Check if they can be merged
                        if self._can_merge(qid1, qid2):
                            group.append(qid2)
                
                if len(group) > 1:
                    siblings.append(group)
                    processed.update(group)
        
        return siblings
    
    def _can_merge(self, qid1: str, qid2: str) -> bool:
        """
        Check if two queries can be merged.
        
        Criteria: 
        1. Same table
        2. Same column(s)
        3. Compatible predicates (categorical or overlapping ranges)
        """
        pred1 = self.predicates[qid1]
        pred2 = self.predicates[qid2]
        
        if pred1.table != pred2.table:
            return False
        
        # Check for categorical predicates on same column
        cols1 = {col for col, op, _ in pred1.conditions if op in (PredicateOp.EQ, PredicateOp.IN)}
        cols2 = {col for col, op, _ in pred2.conditions if op in (PredicateOp.EQ, PredicateOp.IN)}
        
        if cols1 & cols2:
            return True
        
        # Check for range predicates on same column
        range_cols1 = {col for col, op, _ in pred1.conditions 
                       if op in (PredicateOp.GT, PredicateOp.GTE, PredicateOp.LT, PredicateOp.LTE)}
        range_cols2 = {col for col, op, _ in pred2.conditions 
                       if op in (PredicateOp.GT, PredicateOp.GTE, PredicateOp.LT, PredicateOp.LTE)}
        
        return bool(range_cols1 & range_cols2)


# ============================================================================
# Workload Planner
# ============================================================================

class WorkloadPlanner:
    """
    The Workload Planner analyzes a set of queries and creates an optimized
    extraction plan using Multi-Query Optimization (MQO).
    
    Key optimization: Merge sibling predicates to minimize LLM invocations.
    """
    
    def __init__(self, config: QAIRSConfig, sieve: Sieve):
        self.config = config
        self.sieve = sieve
        self.parser = SQLParser()
        
        # Cost model parameters (configurable)
        self.tokens_per_chunk = 1000  # Average tokens per chunk
        self.cost_per_1m_tokens = 0.0001  # Cost in USD
        self.tokens_per_second = 50  # LLM throughput
    
    def create_plan(
        self,
        queries: List[Query],
        schemas: Dict[str, TableSchema]
    ) -> WorkloadPlan:
        """
        Create an optimized extraction plan for a workload.
        
        Args:
            queries: List of queries to optimize
            schemas: Dictionary mapping table_name -> TableSchema
        
        Returns:
            WorkloadPlan with merged tasks
        """
        logger.info(f"Creating workload plan for {len(queries)} queries")
        
        # Step 1: Parse queries into normalized predicates
        lattice = PredicateLattice()
        query_map = {}
        
        for query in queries:
            sql = query.to_sql()
            pred = self.parser.parse_query(sql, query.query_id)
            if pred:
                lattice.add_predicate(pred)
                query_map[query.query_id] = query
        
        # Step 2: Build subsumption graph
        lattice.build_subsumption_edges()
        
        # Step 3: Find sibling groups for merging
        sibling_groups = lattice.find_siblings()
        logger.info(f"Found {len(sibling_groups)} sibling groups for merging")
        
        # Step 4: Create merged tasks
        merged_tasks = []
        processed_queries = set()
        
        for group in sibling_groups:
            merged_task = self._create_merged_task(group, lattice, schemas)
            if merged_task:
                merged_tasks.append(merged_task)
                processed_queries.update(group)
        
        # Step 5: Create individual tasks for non-merged queries
        for qid, pred in lattice.predicates.items():
            if qid not in processed_queries:
                task = self._create_individual_task(qid, pred, schemas)
                if task:
                    merged_tasks.append(task)
        
        # Step 6: Estimate costs for each merged task
        for mtask in merged_tasks:
            mtask.estimated_cost = self._estimate_task_cost(mtask)
            mtask.estimated_time = self._estimate_task_time(mtask)
        
        # Step 7: Apply cost-based optimization
        optimized_tasks = self._cost_based_optimization(merged_tasks, lattice)
        
        # Step 8: Convert to ExtractionTask objects
        extraction_tasks = []
        for mtask in optimized_tasks:
            task = self._merged_to_extraction_task(mtask, schemas)
            if task:
                extraction_tasks.append(task)
        
        # Calculate estimates
        total_chunks = sum(len(task.candidate_chunks) for task in extraction_tasks)
        total_cost = sum(mtask.estimated_cost for mtask in optimized_tasks)
        total_time = sum(mtask.estimated_time for mtask in optimized_tasks)
        
        plan = WorkloadPlan(
            plan_id=f"plan_{len(queries)}q",
            tasks=extraction_tasks,
            estimated_chunks=total_chunks,
            estimated_llm_calls=total_chunks,
            merged_predicates={
                mtask.target_table: [mtask.merged_predicate.to_sql_where()]
                for mtask in optimized_tasks
            }
        )
        
        logger.info(f"Plan created: {len(extraction_tasks)} tasks, ~{total_chunks} chunks")
        logger.info(f"Estimated cost: ${total_cost:.2f}, time: {total_time/60:.1f} min")
        return plan
    
    def _create_merged_task(
        self,
        query_ids: List[str],
        lattice: PredicateLattice,
        schemas: Dict[str, TableSchema]
    ) -> Optional[MergedTask]:
        """
        Create a merged task from sibling queries.
        
        This implements the "Sibling Merging" heuristic for both
        categorical and range predicates.
        """
        if not query_ids:
            return None
        
        # Get predicates
        predicates = [lattice.predicates[qid] for qid in query_ids]
        table = predicates[0].table
        
        # Try categorical merge first
        merged = self._merge_categorical(query_ids, predicates, table)
        if merged:
            return merged
        
        # Try range merge
        merged = self._merge_ranges(query_ids, predicates, table)
        if merged:
            return merged
        
        return None
    
    def _merge_categorical(
        self,
        query_ids: List[str],
        predicates: List[NormalizedPredicate],
        table: str
    ) -> Optional[MergedTask]:
        """Merge categorical predicates (EQ/IN)."""
        # Find common column
        common_cols = None
        for pred in predicates:
            cols = {col for col, op, _ in pred.conditions if op in (PredicateOp.EQ, PredicateOp.IN)}
            if common_cols is None:
                common_cols = cols
            else:
                common_cols &= cols
        
        if not common_cols:
            return None
        
        # Use first common column
        merge_col = list(common_cols)[0]
        
        # Collect all categorical values
        all_values = set()
        for pred in predicates:
            all_values.update(pred.get_categorical_values(merge_col))
        
        if not all_values:
            return None
        
        # Create merged predicate
        merged_pred = NormalizedPredicate(
            query_id=f"merged_{'_'.join(query_ids)}",
            table=table,
            conditions=[(merge_col, PredicateOp.IN, list(all_values))]
        )
        
        # Query sieve
        dict_terms = [str(v) for v in all_values if isinstance(v, str)]
        candidate_chunks = self.sieve.query(dict_tags=dict_terms if dict_terms else None)
        
        # Create hint
        values_str = ", ".join([f"'{v}'" for v in all_values])
        hint = f"Extract rows where {merge_col} IN ({values_str})"
        
        return MergedTask(
            task_id=f"task_merged_{'_'.join(query_ids[:2])}",
            target_table=table,
            trigger_queries=query_ids,
            merged_predicate=merged_pred,
            sieve_filter={"dict_keys": dict_terms, "types": []},
            extraction_hint=hint,
            candidate_chunks=candidate_chunks
        )
    
    def _merge_ranges(
        self,
        query_ids: List[str],
        predicates: List[NormalizedPredicate],
        table: str
    ) -> Optional[MergedTask]:
        """Merge range predicates (GT/GTE/LT/LTE)."""
        # Find common column with range predicates
        common_cols = None
        for pred in predicates:
            cols = {col for col, op, _ in pred.conditions 
                   if op in (PredicateOp.GT, PredicateOp.GTE, PredicateOp.LT, PredicateOp.LTE)}
            if common_cols is None:
                common_cols = cols
            else:
                common_cols &= cols
        
        if not common_cols:
            return None
        
        # Use first common column
        merge_col = list(common_cols)[0]
        
        # Find the widest range that covers all queries
        overall_min = None
        overall_max = None
        min_inclusive = True
        max_inclusive = True
        
        for pred in predicates:
            for col, op, val in pred.conditions:
                if col != merge_col:
                    continue
                
                try:
                    val_num = float(val)
                except (ValueError, TypeError):
                    continue
                
                if op in (PredicateOp.GT, PredicateOp.GTE):
                    if overall_min is None or val_num < overall_min:
                        overall_min = val_num
                        min_inclusive = (op == PredicateOp.GTE)
                elif op in (PredicateOp.LT, PredicateOp.LTE):
                    if overall_max is None or val_num > overall_max:
                        overall_max = val_num
                        max_inclusive = (op == PredicateOp.LTE)
        
        if overall_min is None and overall_max is None:
            return None
        
        # Create merged predicate with widest range
        conditions = []
        if overall_min is not None:
            op = PredicateOp.GTE if min_inclusive else PredicateOp.GT
            conditions.append((merge_col, op, overall_min))
        if overall_max is not None:
            op = PredicateOp.LTE if max_inclusive else PredicateOp.LT
            conditions.append((merge_col, op, overall_max))
        
        merged_pred = NormalizedPredicate(
            query_id=f"merged_{'_'.join(query_ids)}",
            table=table,
            conditions=conditions
        )
        
        # Query sieve (ranges typically need type masks)
        candidate_chunks = self.sieve.query(type_masks={"has_money": True})
        
        # Create hint
        hint_parts = []
        if overall_min is not None:
            op_str = ">=" if min_inclusive else ">"
            hint_parts.append(f"{merge_col} {op_str} {overall_min}")
        if overall_max is not None:
            op_str = "<=" if max_inclusive else "<"
            hint_parts.append(f"{merge_col} {op_str} {overall_max}")
        hint = f"Extract rows where {' AND '.join(hint_parts)}"
        
        return MergedTask(
            task_id=f"task_merged_range_{'_'.join(query_ids[:2])}",
            target_table=table,
            trigger_queries=query_ids,
            merged_predicate=merged_pred,
            sieve_filter={"dict_keys": [], "types": ["has_money"]},
            extraction_hint=hint,
            candidate_chunks=candidate_chunks
        )
    
    def _create_individual_task(
        self,
        query_id: str,
        pred: NormalizedPredicate,
        schemas: Dict[str, TableSchema]
    ) -> Optional[MergedTask]:
        """Create a task for a single query."""
        # Extract dictionary terms
        dict_terms = []
        for col, op, val in pred.conditions:
            if op == PredicateOp.EQ and isinstance(val, str):
                dict_terms.append(val)
            elif op == PredicateOp.IN:
                dict_terms.extend([str(v) for v in val if isinstance(v, str)])
        
        # Query sieve
        candidate_chunks = self.sieve.query(dict_tags=dict_terms if dict_terms else None)
        
        return MergedTask(
            task_id=f"task_{query_id}",
            target_table=pred.table,
            trigger_queries=[query_id],
            merged_predicate=pred,
            sieve_filter={"dict_keys": dict_terms, "types": []},
            extraction_hint=pred.to_sql_where(),
            candidate_chunks=candidate_chunks
        )
    
    def _merged_to_extraction_task(
        self,
        mtask: MergedTask,
        schemas: Dict[str, TableSchema]
    ) -> Optional[ExtractionTask]:
        """Convert MergedTask to ExtractionTask."""
        if mtask.target_table not in schemas:
            logger.warning(f"Schema not found for table: {mtask.target_table}")
            return None
        
        # Convert to Predicate model
        predicate = Predicate(
            table_name=mtask.target_table,
            conditions=[mtask.merged_predicate.to_sql_where()]
        )
        
        return ExtractionTask(
            task_id=mtask.task_id,
            table_schema=schemas[mtask.target_table],
            predicate=predicate,
            candidate_chunks=mtask.candidate_chunks,
            dictionary_map=self.sieve.dictionary_map
        )
    
    def save_plan(self, plan: WorkloadPlan, path: str) -> None:
        """Save execution plan to JSON file (for offline analysis)."""
        plan_dict = {
            "plan_id": plan.plan_id,
            "estimated_chunks": plan.estimated_chunks,
            "estimated_llm_calls": plan.estimated_llm_calls,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "table": task.table_schema.table_name,
                    "predicate": task.predicate.to_sql_where() if task.predicate else None,
                    "num_chunks": len(task.candidate_chunks)
                }
                for task in plan.tasks
            ],
            "merged_predicates": plan.merged_predicates
        }
        
        with open(path, 'w') as f:
            json.dump(plan_dict, f, indent=2)
        
        logger.info(f"Plan saved to {path}")
    
    def _estimate_task_cost(self, task: MergedTask) -> float:
        """
        Estimate the cost of executing a task.
        
        Returns cost in USD.
        """
        num_chunks = len(task.candidate_chunks)
        total_tokens = num_chunks * self.tokens_per_chunk
        cost = (total_tokens / 1_000_000) * self.cost_per_1m_tokens
        return cost
    
    def _estimate_task_time(self, task: MergedTask) -> float:
        """
        Estimate the time to execute a task.
        
        Returns time in seconds.
        """
        num_chunks = len(task.candidate_chunks)
        total_tokens = num_chunks * self.tokens_per_chunk
        time_seconds = total_tokens / self.tokens_per_second
        return time_seconds
    
    def _cost_based_optimization(
        self,
        merged_tasks: List[MergedTask],
        lattice: PredicateLattice
    ) -> List[MergedTask]:
        """
        Apply cost-based optimization to decide whether to merge or split tasks.
        
        Strategy: If merging increases cost significantly but doesn't reduce
        much work, consider keeping tasks separate.
        """
        optimized = []
        
        for task in merged_tasks:
            # If task only has one query, keep it
            if len(task.trigger_queries) == 1:
                optimized.append(task)
                continue
            
            # Calculate cost of merged vs separate
            merged_cost = task.estimated_cost
            
            # Estimate cost if we kept them separate
            separate_cost = 0.0
            for qid in task.trigger_queries:
                pred = lattice.predicates[qid]
                # Estimate chunks for individual query (simplified)
                individual_chunks = len(task.candidate_chunks) // len(task.trigger_queries)
                separate_cost += (individual_chunks * self.tokens_per_chunk / 1_000_000) * self.cost_per_1m_tokens
            
            # Decision: If merged cost is > 1.5x separate cost, split
            # (This means merging is pulling in too many irrelevant chunks)
            if merged_cost > 1.5 * separate_cost:
                logger.info(f"Splitting task {task.task_id}: merged=${merged_cost:.2f} > 1.5*separate=${separate_cost:.2f}")
                # Split into individual tasks
                for qid in task.trigger_queries:
                    pred = lattice.predicates[qid]
                    individual_task = self._create_individual_task(qid, pred, {})
                    if individual_task:
                        individual_task.estimated_cost = self._estimate_task_cost(individual_task)
                        individual_task.estimated_time = self._estimate_task_time(individual_task)
                        optimized.append(individual_task)
            else:
                # Keep merged
                optimized.append(task)
        
        return optimized
    
    @classmethod
    def load_plan(cls, path: str) -> Dict[str, Any]:
        """Load execution plan from JSON file."""
        with open(path, 'r') as f:
            return json.load(f)

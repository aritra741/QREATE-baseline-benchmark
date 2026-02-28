"""
Delta Engine for WDIRS.
Implements runtime incremental query execution with row and column deltas.
"""

import json
import logging
import time
import re
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
        # Populated by WDIRSRunner; used to avoid row-delta duplicate explosions
        # by upserting on known identity columns instead of blind inserts.
        self.identity_columns: Dict[str, Optional[str]] = {}
        
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
    
    def _primary_table(self, parsed: exp.Expression) -> Optional[str]:
        """Return the first table name found in the FROM clause (for unqualified columns)."""
        for table in parsed.find_all(exp.Table):
            if table.name:
                return table.name.lower()
        return None

    def _extract_columns(self, parsed: exp.Expression) -> List[Tuple[str, str]]:
        """Extract (table, column) pairs, inferring table from FROM for unqualified columns."""
        columns = []
        primary_table = self._primary_table(parsed)

        for select in parsed.find_all(exp.Select):
            for projection in select.expressions:
                if isinstance(projection, exp.Column):
                    table = (projection.table or primary_table)
                    column = projection.name
                    if table and column:
                        columns.append((table.lower(), column.lower()))

        for where in parsed.find_all(exp.Where):
            for column in where.find_all(exp.Column):
                table = (column.table or primary_table)
                col_name = column.name
                if table and col_name:
                    columns.append((table.lower(), col_name.lower()))

        return columns

    def _extract_predicates(self, parsed: exp.Expression) -> List[Tuple[str, str]]:
        """Extract (table, predicate) pairs, inferring table from FROM for unqualified columns."""
        predicates = []
        primary_table = self._primary_table(parsed)

        for where in parsed.find_all(exp.Where):
            for comparison in where.find_all(exp.EQ, exp.GT, exp.LT, exp.GTE, exp.LTE, exp.NEQ):
                left = comparison.left
                right = comparison.right

                if isinstance(left, exp.Column):
                    table = (left.table or primary_table)
                    column = left.name

                    if table and column:
                        operator = self._get_operator(comparison)
                        value = self._get_value(right)
                        predicate = f"{column} {operator} {value}"
                        predicates.append((table.lower(), predicate))
        
        return predicates
    
    def _extract_joins(self, parsed: exp.Expression) -> List[Tuple[str, str, str, str]]:
        """
        Extract join information as:
            (left_table, left_column, right_table, right_column)

        We only extract explicit column-to-column equality joins
        (e.g. a.x = b.y), because join alignment requires both side-specific
        column names and table names.
        """
        joins: List[Tuple[str, str, str, str]] = []
        seen: Set[Tuple[str, str, str, str]] = set()

        for join in parsed.find_all(exp.Join):
            on_expr = join.args.get("on")
            if on_expr is None:
                continue

            for eq in on_expr.find_all(exp.EQ):
                left = eq.left
                right = eq.right
                if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                    continue
                if not left.table or not right.table:
                    continue

                key = (
                    left.table.lower(),
                    left.name.lower(),
                    right.table.lower(),
                    right.name.lower(),
                )
                if key not in seen:
                    seen.add(key)
                    joins.append(key)

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
        joins: List[Tuple[str, str, str, str]]
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
                logger.info("Cache hit - no delta execution needed")
            
            elif plan.delta_type == DeltaType.ROW_DELTA:
                rows_extracted = self._execute_row_delta(
                    plan.tables_involved,
                    plan.missing_predicates
                )
            
            elif plan.delta_type == DeltaType.COLUMN_DELTA:
                rows_enriched = self._execute_column_delta(
                    plan.tables_involved,
                    plan.missing_columns
                )
            
            elif plan.delta_type == DeltaType.MIXED_DELTA:
                rows_extracted = self._execute_row_delta(
                    plan.tables_involved,
                    plan.missing_predicates
                )
                rows_enriched = self._execute_column_delta(
                    plan.tables_involved,
                    plan.missing_columns
                )
            
            elif plan.delta_type == DeltaType.JOIN_ALIGNMENT:
                self._execute_join_alignment(query)

            if plan.requires_join_alignment and plan.delta_type != DeltaType.JOIN_ALIGNMENT:
                logger.info("Running join alignment after extraction/enrichment")
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
    
    def _build_runtime_normalization_hints(
        self,
        missing_predicates: List[str]
    ) -> Dict[str, List[str]]:
        """
        Build normalization hints from runtime query predicate literals.

        For a runtime predicate like 'country = UK', the extractor must be told
        to store 'UK' — not 'United Kingdom' or any other form.  These hints are
        derived solely from the runtime query, NOT from the workload, so they
        reflect exactly what the query expects to find in the DB.
        """
        hints: Dict[str, List[str]] = {}
        for pred in missing_predicates:
            # Only equality predicates define an expected stored value.
            # Predicates like "age > 25" don't constrain string form.
            if "=" not in pred or "!=" in pred or ">=" in pred or "<=" in pred:
                continue
            col, _, val = pred.partition("=")
            col = col.strip()
            val = val.strip().strip("'\"")
            if col and val:
                hints.setdefault(col, [])
                if val not in hints[col]:
                    hints[col].append(val)
        return hints

    def _execute_row_delta(
        self,
        tables: List[str],
        missing_predicates: List[str]
    ) -> int:
        """
        Execute row delta: extract new rows matching missing predicates.
        Normalization hints are built from the RUNTIME predicate literals so the
        extractor stores values in exactly the form the query expects (e.g. 'UK',
        not 'United Kingdom').

        Returns:
            Number of rows extracted
        """
        logger.info(f"Executing row delta for {len(tables)} tables")

        # Build normalization hints from runtime predicate literals — this is the
        # key difference from preprocessing: we use the query's own literals, not
        # the workload's.
        runtime_hints = self._build_runtime_normalization_hints(missing_predicates)
        if runtime_hints:
            logger.info(f"Runtime normalization hints: {runtime_hints}")

        total_rows = 0

        for table_name in tables:
            candidate_chunk_ids = self.data_layer.get_candidates(table_name)
            if not candidate_chunk_ids:
                logger.warning(f"No candidate chunks for {table_name}")
                continue

            chunks = self.data_layer.get_chunks_by_ids(candidate_chunk_ids)

            # Keyword-filter chunks to those likely relevant to missing predicates
            filtered_chunks = self._filter_chunks_by_predicates(chunks, missing_predicates)
            if not filtered_chunks:
                logger.info(f"No chunks match missing predicates for {table_name}")
                continue

            schema = self.lattice_planner.get_table_schema(table_name)
            stabilized = self.extractor.get_stabilized_schema(table_name)
            constrained_keys = stabilized.frozen_keys if stabilized else None

            chunk_texts = [c.content for c in filtered_chunks]
            chunk_ids_list = [c.chunk_id for c in filtered_chunks]
            chunk_doc_map = {c.chunk_id: c.doc_id for c in filtered_chunks}
            chunk_text_map = {c.chunk_id: c.content for c in filtered_chunks}

            results = self.extractor.extract_batch_with_predicates(
                chunk_texts,
                chunk_ids_list,
                table_name,
                schema,
                constrained_keys,
                missing_predicates,
                runtime_hints        # ← runtime query literals, not workload literals
            )

            # Ensure the dynamic table exists before inserting
            from wdirs_runner import semantic_to_sql_type
            sql_schema = {col: semantic_to_sql_type(sem_type)
                          for col, sem_type in schema.items()}
            self.data_layer.create_dynamic_table(table_name, sql_schema)

            # Prefer identity-key upsert when available to avoid inserting
            # duplicate rows for the same entity across many chunks.
            identity_col = (self.identity_columns or {}).get(table_name)
            if identity_col:
                triples: List[tuple] = []
                dropped_invalid = 0
                for result in results:
                    if result.error:
                        logger.warning(
                            f"Skipping chunk {result.chunk_id} in row delta: {result.error}"
                        )
                        continue
                    doc_id = chunk_doc_map.get(result.chunk_id, "")
                    chunk_text = chunk_text_map.get(result.chunk_id, "")
                    for record in result.records:
                        rec = dict(record)
                        ent = rec.get(identity_col)
                        ent_str = str(ent).strip() if ent is not None else ""
                        if not self._is_valid_identity_value(ent_str, chunk_text):
                            dropped_invalid += 1
                            continue
                        rec["_entity"] = ent_str
                        triples.append((rec, result.chunk_id, doc_id))

                table_rows = 0
                if triples:
                    row_pv, cell_pv = self.data_layer.upsert_by_entity(
                        table_name, identity_col, triples
                    )
                    self.data_layer.bulk_insert_provenance(table_name, row_pv)
                    self.data_layer.bulk_insert_cell_provenance(cell_pv)
                    table_rows = len({rid for rid, _ in row_pv})
                if dropped_invalid:
                    logger.info(
                        f"[RowDelta] Dropped {dropped_invalid} records with invalid "
                        f"identity for {table_name}.{identity_col}"
                    )
            else:
                table_rows = 0
                for result in results:
                    if result.error:
                        logger.warning(
                            f"Skipping chunk {result.chunk_id} in row delta: {result.error}"
                        )
                        continue
                    for record in result.records:
                        row_id = self.data_layer.insert_record(table_name, record)
                        self.data_layer.insert_provenance(
                            row_id, table_name, [result.chunk_id]
                        )
                        table_rows += 1

            total_rows += table_rows
            logger.info(f"Row delta inserted {table_rows} rows into {table_name}")

            # Mark these predicates as materialized in the registry
            for predicate in missing_predicates:
                col = predicate.split()[0].strip()
                self.data_layer.update_metadata(
                    table_name,
                    col,
                    [predicate],
                    STATUS_PARTIAL,
                    table_rows
                )

        logger.info(f"Row delta complete: {total_rows} rows extracted")
        return total_rows

    @staticmethod
    def _normalize_text(s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"[^\w\s]", " ", s)
        return " ".join(s.split())

    def _is_valid_identity_value(self, value: str, chunk_text: str) -> bool:
        """
        Generic identity validation for runtime row-delta:
        - non-empty / non-placeholder
        - not numeric-only
        - must be grounded in source chunk text (exact or normalized)
        """
        v = (value or "").strip()
        if not v:
            return False
        norm_v = self._normalize_text(v)
        if norm_v in {"name", "id", "label", "title", "unknown", "none", "null", "n a"}:
            return False
        if re.fullmatch(r"\d+", v):
            return False
        chunk = chunk_text or ""
        if v.lower() in chunk.lower():
            return True
        return norm_v in self._normalize_text(chunk)
    
    def _execute_column_delta(
        self,
        tables: List[str],
        missing_columns: List[str]
    ) -> int:
        """
        Execute column delta: enrich existing rows with missing column values.

        For each existing row we:
          1. Retrieve its source chunks via Row_Provenance.
          2. Ask the LLM to extract ONLY the missing columns from those chunks,
             providing the row's existing values as context so the LLM knows
             which entity to focus on.
          3. UPDATE the existing DB row with the newly extracted values.

        Returns:
            Number of rows enriched
        """
        logger.info(f"Executing column delta: missing columns={missing_columns}")

        import json as _json

        total_enriched = 0

        for table_name in tables:
            # Load all existing rows from the dynamic table
            try:
                existing_rows = self.data_layer.get_all_records(table_name)
            except Exception as e:
                raise RuntimeError(
                    f"Column delta failed: cannot read rows from '{table_name}': {e}"
                ) from e

            if not existing_rows:
                logger.warning(f"No existing rows in '{table_name}' to enrich")
                continue

            schema = self.lattice_planner.get_table_schema(table_name)
            system_cols = {"row_id", "created_at"}

            for row in existing_rows:
                row_id = row["row_id"]

                # Skip if row already has all missing columns populated
                already_filled = all(
                    row.get(col) not in (None, "", "null")
                    for col in missing_columns
                    if col in row
                )
                if already_filled and all(col in row for col in missing_columns):
                    continue

                # Retrieve source chunks for this row via provenance
                provenance_list = self.data_layer.get_provenance(row_ids=[row_id])
                if not provenance_list:
                    logger.warning(f"No provenance for row {row_id} in '{table_name}'")
                    continue

                chunk_ids_for_row = []
                for prov in provenance_list:
                    chunk_ids_for_row.extend(_json.loads(prov.chunk_ids))

                chunks = self.data_layer.get_chunks_by_ids(list(dict.fromkeys(chunk_ids_for_row)))
                if not chunks:
                    logger.warning(f"Source chunks missing for row {row_id}")
                    continue

                # Build context string from existing non-null values
                existing_context = {
                    k: v for k, v in row.items()
                    if k not in system_cols and v not in (None, "", "null")
                    and k not in missing_columns
                }
                context_str = ", ".join(
                    f'{k}="{v}"' for k, v in existing_context.items()
                )

                # For each source chunk, run a targeted extraction prompt
                # asking only for the missing columns for this specific entity.
                merged_values: Dict[str, Any] = {}
                for chunk in chunks:
                    missing_keys_str = ", ".join(f'"{c}"' for c in missing_columns)
                    prompt = (
                        f"You are extracting data for table '{table_name}'.\n"
                        f"We already have this record: {context_str}\n"
                        f"From the text below, extract ONLY these missing fields: [{missing_keys_str}] "
                        f"for the entity described above.\n"
                        f"Return a JSON object with only those keys. "
                        f"If a value is not present, use null.\n\n"
                        f"Text:\n{chunk.content}\n\n"
                        f"Output (JSON only):"
                    )

                    try:
                        response = self.extractor.llm_client.generate(
                            prompt,
                            max_tokens=512,
                            temperature=0.0
                        )
                        json_str = self.extractor._extract_json(response)
                        if json_str:
                            extracted = _json.loads(json_str)
                            if isinstance(extracted, dict):
                                for col in missing_columns:
                                    if col in extracted and extracted[col] not in (None, "", "null"):
                                        # First non-null value wins across chunks
                                        if col not in merged_values:
                                            merged_values[col] = extracted[col]
                    except Exception as e:
                        logger.warning(f"Column delta LLM call failed for row {row_id}: {e}")
                        continue

                if not merged_values:
                    logger.warning(f"No values extracted for row {row_id} missing cols {missing_columns}")
                    continue

                # Update only the columns we actually extracted
                self.data_layer.update_record(table_name, row_id, merged_values)
                total_enriched += 1

            logger.info(f"Column delta enriched {total_enriched} rows in '{table_name}'")

            # Mark columns as materialized in the registry
            for column in missing_columns:
                self.data_layer.update_metadata(
                    table_name,
                    column,
                    [],
                    STATUS_FULL,
                    total_enriched
                )

        logger.info(f"Column delta complete: {total_enriched} rows enriched")
        return total_enriched
    
    def _execute_join_alignment(self, query: str) -> None:
        """
        JIT join alignment: resolve entity references across join-key columns
        so that SQL joins produce correct matches.
        """
        logger.info("Executing JIT join alignment")

        parsed = parse_one(query, dialect="postgres")
        joins = self._extract_joins(parsed)

        for left_table, left_column, right_table, right_column in joins:
            logger.info(
                f"Aligning join: {left_table}.{left_column} ↔ {right_table}.{right_column}"
            )

            # Query actual distinct values from both tables
            left_values = self.data_layer.get_distinct_values(left_table, left_column)
            right_values = self.data_layer.get_distinct_values(right_table, right_column)

            if not left_values or not right_values:
                logger.warning(
                    f"Skipping join alignment for {left_table}↔{right_table}: "
                    f"one side has no values"
                )
                continue

            logger.info(
                f"  {left_table}.{left_column}: {len(left_values)} values, "
                f"  {right_table}.{right_column}: {len(right_values)} values"
            )

            # Pass 1 (deterministic): normalized exact matching across both sides.
            # This is robust for common formatting drift (case, punctuation, spacing).
            left_norm: Dict[str, List[str]] = {}
            right_norm: Dict[str, List[str]] = {}
            for v in left_values:
                n = self._normalize_text(v)
                if n:
                    left_norm.setdefault(n, []).append(v)
            for v in right_values:
                n = self._normalize_text(v)
                if n:
                    right_norm.setdefault(n, []).append(v)

            overlap_norms = set(left_norm.keys()) & set(right_norm.keys())
            canonical_map: Dict[str, str] = {}
            for n in overlap_norms:
                # Prefer a stable canonical form from the right side (join target),
                # choosing the shortest non-empty variant.
                right_variants = sorted(
                    [x for x in right_norm[n] if x and x.strip()],
                    key=lambda s: (len(s.strip()), s.lower()),
                )
                canonical = right_variants[0] if right_variants else right_norm[n][0]
                for raw in left_norm[n]:
                    canonical_map[raw] = canonical
                for raw in right_norm[n]:
                    canonical_map[raw] = canonical

            logger.info(
                "  Normalized exact overlap: %d key group(s), %d mapped values",
                len(overlap_norms),
                len(canonical_map),
            )

            # Pass 2 (semantic): only for values not matched by normalized overlap.
            unresolved_left = [v for v in left_values if v not in canonical_map]
            unresolved_right = [v for v in right_values if v not in canonical_map]
            if unresolved_left and unresolved_right:
                semantic_map = self.entity_resolver.align_join_keys(
                    unresolved_left,
                    unresolved_right,
                    left_table,
                    right_table,
                    f"{left_column}↔{right_column}"
                )
                canonical_map.update(semantic_map)

            if not canonical_map:
                logger.info(f"No join key mismatches found for {left_table}↔{right_table}")
                continue

            # Apply canonical forms to both tables
            self.data_layer.update_column_values(left_table, left_column, canonical_map)
            self.data_layer.update_column_values(right_table, right_column, canonical_map)

            logger.info(
                f"Aligned {len(canonical_map)} join key(s) between "
                f"{left_table} and {right_table}"
            )
    
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

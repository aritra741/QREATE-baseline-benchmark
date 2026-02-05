"""
Query Engine: Main interface for executing queries.
"""
import sqlparse
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text
from loguru import logger

from models import (
    Query, Predicate, TableSchema, MaterializationStatus,
    ExtractionTask
)
from config import QAIRSConfig
from registry import Registry
from sieve import Sieve
from extractor import Extractor
from llm_client import OllamaClient


class QueryEngine:
    """
    The Query Engine is the main entry point for executing queries.
    It implements the Router logic with subsumption checking.
    """
    
    def __init__(
        self,
        config: QAIRSConfig,
        registry: Registry,
        sieve: Sieve,
        extractor: Extractor
    ):
        self.config = config
        self.registry = registry
        self.sieve = sieve
        self.extractor = extractor
        
        # Database connection for executing SQL
        self.engine = create_engine(config.database.connection_string)
    
    def execute(
        self,
        sql: str,
        chunks: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a SQL query.
        
        Args:
            sql: SQL query string
            chunks: Optional corpus chunks (required if extraction needed)
        
        Returns:
            Query results as list of dictionaries
        """
        logger.info(f"Executing query: {sql}")
        
        # Parse SQL
        query = self._parse_sql(sql)
        
        # Check registry for subsumption
        status = self.registry.check_predicate(query.predicate) if query.predicate else None
        
        if status == MaterializationStatus.MATERIALIZED:
            # Data already extracted - execute SQL directly
            logger.info("Query satisfied by materialized data")
            return self._execute_sql(sql)
        
        elif status == MaterializationStatus.PENDING or status is None:
            # Need to extract data
            logger.info("Data not materialized - triggering extraction")
            
            if chunks is None:
                raise ValueError("Corpus chunks required for extraction")
            
            # Get schema
            schema = self._get_schema(query.table_name)
            if not schema:
                raise ValueError(f"Schema not found for table: {query.table_name}")
            
            # Extract data
            self._extract_and_materialize(query, schema, chunks)
            
            # Now execute SQL
            return self._execute_sql(sql)
        
        else:
            raise ValueError(f"Unexpected materialization status: {status}")
    
    def _parse_sql(self, sql: str) -> Query:
        """
        Parse SQL query into Query object.
        
        This is a simplified parser. A production system would use
        a proper SQL parser like sqlparse or sqlglot.
        """
        parsed = sqlparse.parse(sql)[0]
        
        # Extract table name
        table_name = None
        for token in parsed.tokens:
            if token.ttype is None and isinstance(token, sqlparse.sql.Identifier):
                table_name = str(token)
                break
            elif token.ttype is None:
                # Look for FROM clause
                if 'FROM' in str(token).upper():
                    parts = str(token).split()
                    if len(parts) > 1:
                        table_name = parts[1].strip()
                        break
        
        # Extract WHERE clause
        where_clause = None
        for token in parsed.tokens:
            if isinstance(token, sqlparse.sql.Where):
                where_clause = str(token)[6:].strip()  # Remove "WHERE "
                break
        
        # Create predicate
        predicate = None
        if where_clause:
            predicate = Predicate(
                table_name=table_name,
                conditions=[where_clause]
            )
        
        return Query(
            query_id="query_" + str(hash(sql)),
            table_name=table_name,
            predicate=predicate
        )
    
    def _get_schema(self, table_name: str) -> Optional[TableSchema]:
        """
        Get schema for a table.
        
        In a real system, this would query a schema registry.
        For now, we try to infer from database.
        """
        from models import get_table_schema_from_db
        return get_table_schema_from_db(
            self.config.database.connection_string,
            table_name
        )
    
    def _extract_and_materialize(
        self,
        query: Query,
        schema: TableSchema,
        chunks: Dict[str, str]
    ) -> None:
        """
        Extract data and materialize it in the database.
        """
        logger.info(f"Extracting data for: {query.predicate.to_sql_where() if query.predicate else 'ALL'}")
        
        # Register predicate
        if query.predicate:
            self.registry.register_predicate(
                query.predicate,
                MaterializationStatus.PENDING
            )
        
        # Query sieve for candidate chunks
        dict_terms = []
        if query.predicate:
            for cond in query.predicate.conditions:
                # Extract terms (simplified)
                import re
                matches = re.findall(r"'([^']+)'", cond)
                dict_terms.extend(matches)
        
        candidate_chunks = self.sieve.query(dict_tags=dict_terms if dict_terms else None)
        logger.info(f"Found {len(candidate_chunks)} candidate chunks")
        
        # Create extraction task
        task = ExtractionTask(
            task_id=f"task_{query.query_id}",
            table_schema=schema,
            predicate=query.predicate,
            candidate_chunks=candidate_chunks,
            dictionary_map=self.sieve.dictionary_map
        )
        
        # Execute extraction (with parallel processing if enabled)
        results = self.extractor.extract(
            task, 
            chunks, 
            parallel=self.config.extraction.enable_parallel
        )
        
        # Insert data into database
        total_rows = 0
        for result in results:
            if result.data:
                self._insert_rows(schema.table_name, result.data)
                total_rows += len(result.data)
            
            # Mark chunk as processed
            if query.predicate:
                # Get predicate ID
                # (simplified - in production, query registry for ID)
                self.registry.mark_chunk_processed(
                    result.chunk_id,
                    predicate_id=1,  # Placeholder
                    has_more=result.has_more
                )
        
        # Update registry
        if query.predicate:
            self.registry.update_status(
                query.predicate,
                MaterializationStatus.MATERIALIZED,
                chunks_processed=len(results),
                rows_extracted=total_rows
            )
        
        logger.info(f"Materialized {total_rows} rows")
    
    def _insert_rows(self, table_name: str, rows: List[Dict[str, Any]]) -> None:
        """
        Insert rows into database.
        """
        if not rows:
            return
        
        # Build INSERT statement
        columns = list(rows[0].keys())
        placeholders = ", ".join([f":{col}" for col in columns])
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        
        with self.engine.connect() as conn:
            conn.execute(text(sql), rows)
            conn.commit()
    
    def _execute_sql(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute SQL and return results.
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = result.fetchall()
            
            # Convert to list of dicts
            columns = result.keys()
            return [dict(zip(columns, row)) for row in rows]

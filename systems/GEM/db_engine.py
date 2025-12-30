"""
Database Engine - Storage and Query Execution

Manages DuckDB storage and execution of SQL queries with semantic rewriting
to handle entity resolution lookups.
"""

import logging
import re
from typing import List, Dict, Optional, Any
from pathlib import Path

try:
    import duckdb
    import pandas as pd
except ImportError:
    duckdb = None
    pd = None

from .config import DB_PATH
from .schema_loader import Schema
from .resolver import EntityResolver


logger = logging.getLogger(__name__)


class DBEngine:
    """DuckDB database engine for GEM."""
    
    def __init__(self, db_path: Optional[Path] = None, logger: Optional[logging.Logger] = None):
        """Initialize database engine.
        
        Args:
            db_path: Path to DuckDB file
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.conn = None
        self.resolver: Optional[EntityResolver] = None
        self.schema: Optional[Schema] = None
        self._init_db()
    
    def _init_db(self):
        """Initialize DuckDB connection."""
        if duckdb is None:
            self.logger.warning("DuckDB not available")
            return
        
        try:
            # Create cache directory if needed
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Connect to DuckDB
            self.conn = duckdb.connect(str(self.db_path))
            self.logger.info(f"Connected to DuckDB: {self.db_path}")
        except Exception as e:
            self.logger.error(f"Failed to initialize DuckDB: {e}")
            self.conn = None
    
    def set_resolver(self, resolver: EntityResolver):
        """Set entity resolver for query rewriting.
        
        Args:
            resolver: EntityResolver instance
        """
        self.resolver = resolver
    
    def set_schema(self, schema: Schema):
        """Set schema for type information.
        
        Args:
            schema: Schema instance
        """
        self.schema = schema
    
    def _get_sql_type(self, attr_type: str) -> str:
        """Convert schema type to SQL type.
        
        Args:
            attr_type: Attribute type from schema
            
        Returns:
            SQL type string
        """
        type_lower = attr_type.lower()
        
        if type_lower in ["int", "integer"]:
            return "INTEGER"
        elif type_lower in ["float", "double", "decimal"]:
            return "DOUBLE"
        elif type_lower in ["bool", "boolean"]:
            return "BOOLEAN"
        elif type_lower in ["date"]:
            return "DATE"
        elif type_lower in ["timestamp", "datetime"]:
            return "TIMESTAMP"
        else:  # string, text, etc.
            return "VARCHAR"
    
    def create_table(self, table_name: str, schema: Schema):
        """Create a table in DuckDB based on schema.
        
        Args:
            table_name: Name of table to create
            schema: Schema object
        """
        if self.conn is None:
            self.logger.warning("Database not initialized")
            return
        
        # Build CREATE TABLE statement
        columns = []
        for attr in schema.attributes:
            sql_type = self._get_sql_type(attr.type)
            columns.append(f"{attr.name} {sql_type}")
        
        columns_str = ", ".join(columns)
        create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_str})"
        
        try:
            self.conn.execute(create_sql)
            self.logger.info(f"Created table {table_name}")
        except Exception as e:
            self.logger.error(f"Failed to create table {table_name}: {e}")
    
    def insert_records(self, table_name: str, records: List[Dict]):
        """Insert records into table.
        
        Args:
            table_name: Name of table
            records: List of record dictionaries
        """
        if self.conn is None:
            self.logger.warning("Database not initialized")
            return
        
        if not records:
            self.logger.warning("No records to insert")
            return
        
        try:
            if pd is None:
                self.logger.warning("pandas not available for batch insert")
                return
            
            # Convert to DataFrame
            df = pd.DataFrame(records)
            
            # Cast numeric columns based on schema BEFORE inserting
            if self.schema:
                for attr in self.schema.attributes:
                    if attr.name in df.columns:
                        type_lower = attr.type.lower()
                        try:
                            if type_lower in ["int", "integer", "int_value"]:
                                # Convert to numeric, coercing errors to NaN
                                df[attr.name] = pd.to_numeric(df[attr.name], errors='coerce').astype('Int64')
                            elif type_lower in ["float", "double", "float_value"]:
                                df[attr.name] = pd.to_numeric(df[attr.name], errors='coerce').astype('float64')
                        except Exception as e:
                            self.logger.warning(f"Failed to cast {attr.name} to {attr.type}: {e}")
            
            # Handle None/NULL values
            df = df.where(pd.notnull(df), None)
            
            # Insert - DuckDB will respect pandas dtypes
            self.conn.from_df(df).insert_into(table_name)
            self.logger.info(f"Inserted {len(records)} records into {table_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to insert records: {e}")
    
    def _rewrite_sql_with_canonical_map(self, sql: str) -> str:
        """Rewrite SQL to use canonical names instead of input variations.
        
        This implements the semantic shim that intercepts string literals
        and replaces them with their canonical forms.
        
        Args:
            sql: Original SQL query
            
        Returns:
            Rewritten SQL
        """
        if self.resolver is None or not self.resolver.canonical_map:
            return sql
        
        # Find all string literals in the SQL (between single quotes)
        # Pattern: 'string_value'
        pattern = r"'([^']*?)'"
        
        def replace_literal(match):
            """Replace a string literal with its canonical form if available."""
            value = match.group(1)
            
            # Check if this value has a canonical mapping
            canonical = self.resolver.get_canonical(value)
            
            if canonical != value:
                self.logger.debug(f"Rewrote '{value}' -> '{canonical}'")
                return f"'{canonical}'"
            
            return match.group(0)
        
        rewritten_sql = re.sub(pattern, replace_literal, sql)
        
        if rewritten_sql != sql:
            self.logger.debug(f"SQL rewritten:\n  Original:  {sql}\n  Rewritten: {rewritten_sql}")
        
        return rewritten_sql
    
    def execute_query(self, sql: str) -> Optional[pd.DataFrame]:
        """Execute SQL query with semantic rewriting.
        
        Args:
            sql: SQL query
            
        Returns:
            Result as DataFrame or None
        """
        if self.conn is None:
            self.logger.warning("Database not initialized")
            return None
        
        try:
            # Rewrite SQL with canonical map
            rewritten_sql = self._rewrite_sql_with_canonical_map(sql)
            
            # Execute query
            result = self.conn.execute(rewritten_sql)
            
            # Fetch results - DuckDB returns a relation object
            # Use df() to convert directly to pandas DataFrame
            if pd is None:
                self.logger.warning("pandas not available, returning raw results")
                return None
            
            df = result.df()
            self.logger.info(f"Query returned {len(df)} rows")
            return df
            
        except Exception as e:
            self.logger.error(f"Query execution failed: {e}")
            return None
    
    def drop_table(self, table_name: str):
        """Drop a table.
        
        Args:
            table_name: Name of table
        """
        if self.conn is None:
            return
        
        try:
            self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            self.logger.info(f"Dropped table {table_name}")
        except Exception as e:
            self.logger.warning(f"Failed to drop table {table_name}: {e}")
    
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists.
        
        Args:
            table_name: Name of table
            
        Returns:
            True if table exists
        """
        if self.conn is None:
            return False
        
        try:
            result = self.conn.execute(
                f"SELECT 1 FROM information_schema.tables WHERE table_name = '{table_name}'"
            ).fetchone()
            return result is not None
        except Exception:
            return False
    
    def get_table_info(self, table_name: str) -> Optional[Dict]:
        """Get table information.
        
        Args:
            table_name: Name of table
            
        Returns:
            Dictionary with table info or None
        """
        if self.conn is None:
            return None
        
        try:
            # Get row count
            row_count = self.conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            
            # Get columns
            columns_result = self.conn.execute(f"DESCRIBE {table_name}").fetchall()
            
            return {
                "row_count": row_count,
                "columns": [col[0] for col in columns_result]
            }
        except Exception as e:
            self.logger.warning(f"Failed to get table info: {e}")
            return None
    
    def close(self):
        """Close database connection."""
        if self.conn is not None:
            try:
                self.conn.close()
                self.logger.info("Closed database connection")
            except Exception as e:
                self.logger.warning(f"Error closing connection: {e}")


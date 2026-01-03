"""
Database Engine - Storage and Query Execution

Manages SQLite storage and execution of SQL queries with semantic rewriting
to handle entity resolution lookups.
"""

import logging
import re
import sqlite3
from typing import List, Dict, Optional, Any
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None

from .config import DB_PATH
from .schema_loader import Schema
from .resolver import EntityResolver


logger = logging.getLogger(__name__)


class DBEngine:
    """SQLite database engine for GEM."""
    
    def __init__(self, db_path: Optional[Path] = None, logger: Optional[logging.Logger] = None):
        """Initialize database engine.
        
        Args:
            db_path: Path to SQLite database file
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.conn = None
        self.resolver: Optional[EntityResolver] = None
        self.schema: Optional[Schema] = None
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite connection."""
        try:
            # Create cache directory if needed
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Connect to SQLite
            self.conn = sqlite3.connect(str(self.db_path))
            # Enable returning rows as dictionaries
            self.conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.logger.info(f"Connected to SQLite: {self.db_path}")
        except Exception as e:
            self.logger.error(f"Failed to initialize SQLite: {e}")
            self.conn = None
    
    def set_resolver(self, resolver: EntityResolver):
        """Set the entity resolver for semantic rewriting.
        
        Args:
            resolver: EntityResolver instance
        """
        self.resolver = resolver
    
    def set_schema(self, schema: Schema):
        """Set the schema for the current entity.
        
        Args:
            schema: Schema instance
        """
        self.schema = schema
    
    def _get_sql_type(self, attr_type: str) -> str:
        """Map attribute type to SQLite type.
        
        Args:
            attr_type: Attribute type from schema
            
        Returns:
            SQL type string
        """
        type_lower = attr_type.lower()
        
        if type_lower in ["int", "integer"]:
            return "INTEGER"
        elif type_lower in ["float", "double", "decimal"]:
            return "REAL"
        elif type_lower in ["bool", "boolean"]:
            return "INTEGER"  # SQLite uses 0/1 for booleans
        elif type_lower in ["date"]:
            return "TEXT"  # SQLite stores dates as TEXT
        elif type_lower in ["timestamp", "datetime"]:
            return "TEXT"
        else:  # string, text, etc.
            return "TEXT"
    
    def create_table(self, table_name: str, schema: Schema):
        """Create a table in SQLite based on schema.
        
        Args:
            table_name: Name of table to create
            schema: Schema object
        """
        if self.conn is None:
            self.logger.warning("Database not initialized")
            return
        
        # Drop table if it exists (to ensure clean state)
        try:
            self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            self.logger.debug(f"[CREATE TABLE] Dropped existing table {table_name}")
        except Exception as e:
            self.logger.debug(f"[CREATE TABLE] Could not drop table: {e}")
        
        # Build CREATE TABLE statement
        columns = []
        for attr in schema.attributes:
            sql_type = self._get_sql_type(attr.type)
            columns.append(f"{attr.name} {sql_type}")
            self.logger.info(f"[CREATE TABLE] {attr.name}: schema_type='{attr.type}' -> SQL_type='{sql_type}'")
        
        columns_str = ", ".join(columns)
        create_sql = f"CREATE TABLE {table_name} ({columns_str})"
        
        try:
            self.conn.execute(create_sql)
            self.conn.commit()
            self.logger.info(f"Created table {table_name}")
            self.logger.info(f"[CREATE TABLE] SQL: {create_sql}")
        except Exception as e:
            self.logger.error(f"Failed to create table {table_name}: {e}")
    
    def insert_records(self, table_name: str, records: List[Dict]):
        """Insert records into table using pandas.to_sql().
        
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
            self.logger.info(f"[INSERT] DataFrame shape: {df.shape}, columns: {df.columns.tolist()}")
            
            # Use pandas to_sql with sqlite3 connection
            # append mode adds to existing table, if_exists='append' to add to existing table
            df.to_sql(table_name, self.conn, if_exists='append', index=False)
            
            self.logger.info(f"Inserted {len(records)} records into {table_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to insert records: {e}")
            import traceback
            traceback.print_exc()
    
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
            # Rewrite SQL to use canonical names
            rewritten_sql = self._rewrite_sql_with_canonical_map(sql)
            
            self.logger.debug(f"Executing SQL: {rewritten_sql}")
            
            # Execute query and fetch results as DataFrame
            df = pd.read_sql_query(rewritten_sql, self.conn)
            
            return df
            
        except Exception as e:
            self.logger.error(f"Query execution failed: {e}")
            return None
    
    def close(self):
        """Close database connection."""
        if self.conn:
            try:
                self.conn.close()
                self.logger.info("Closed database connection")
            except Exception as e:
                self.logger.error(f"Error closing connection: {e}")
            self.conn = None

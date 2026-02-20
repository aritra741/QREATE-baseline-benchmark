"""
Data Layer & State Management for WDIRS.
Implements PostgreSQL schema, metadata registry, and provenance tracking.
"""

import json
import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

from sqlalchemy import (
    create_engine, Table, Column, String, Integer, Text, JSON,
    MetaData, DateTime, ForeignKey, Index, Boolean, select, insert, update, delete, text
)
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from config import (
    DATABASE_URI, STATUS_PARTIAL, STATUS_FULL,
    CHUNK_SIZE, CHUNK_OVERLAP, CHUNK_SEPARATORS
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class TextChunk:
    """Represents a chunk of text from source documents."""
    chunk_id: str
    doc_id: str
    content: str
    chunk_index: int
    metadata: Dict[str, Any]

@dataclass
class MetadataEntry:
    """Represents an entry in the metadata registry."""
    table_name: str
    column_name: str
    predicate_scope: List[str]
    status: str
    last_updated: datetime
    record_count: int

@dataclass
class ProvenanceRecord:
    """Links extracted rows to source chunks."""
    row_id: str
    table_name: str
    chunk_ids: List[str]


# ============================================================================
# Database Schema Manager
# ============================================================================

class DataLayer:
    """
    Manages all database operations for WDIRS.
    Handles text storage, metadata registry, and dynamic table creation.
    """
    
    def __init__(self, connection_uri: str = DATABASE_URI):
        """Initialize database connection and schema."""
        self.engine = create_engine(
            connection_uri,
            poolclass=NullPool,
            echo=False,
            connect_args={'check_same_thread': False} if 'sqlite' in connection_uri else {}
        )
        self.metadata = MetaData()
        self.Session = sessionmaker(bind=self.engine)
        
        # Define core tables
        self._define_core_tables()
        
        # Create all tables
        self.metadata.create_all(self.engine)
        
        logger.info("DataLayer initialized successfully")
    
    def _define_core_tables(self):
        """Define the core WDIRS tables."""
        
        # Raw_Chunks: Stores chunked text from source documents
        self.raw_chunks = Table(
            'raw_chunks',
            self.metadata,
            Column('chunk_id', String(36), primary_key=True),
            Column('doc_id', String(500), nullable=False, index=True),
            Column('content', Text, nullable=False),
            Column('chunk_index', Integer, nullable=False),
            Column('metadata', JSON, default='{}'),
            Column('created_at', DateTime, default=datetime.utcnow),
            Index('idx_doc_chunk', 'doc_id', 'chunk_index')
        )
        
        # Metadata_Registry: Tracks completeness of synthesized tables
        self.metadata_registry = Table(
            'metadata_registry',
            self.metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('table_name', String(200), nullable=False),
            Column('column_name', String(200), nullable=False),
            Column('predicate_scope', JSON, default='[]'),
            Column('status', String(20), nullable=False),
            Column('last_updated', DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
            Column('record_count', Integer, default=0),
            Index('idx_table_column', 'table_name', 'column_name'),
            Index('idx_status', 'status')
        )
        
        # Row_Provenance: Links extracted rows to source chunks
        self.row_provenance = Table(
            'row_provenance',
            self.metadata,
            Column('row_id', String(36), primary_key=True),
            Column('table_name', String(200), nullable=False, index=True),
            Column('chunk_ids', JSON, nullable=False),
            Column('created_at', DateTime, default=datetime.utcnow)
        )
        
        # Candidate_Index: Stores sieve filtering results
        self.candidate_index = Table(
            'candidate_index',
            self.metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('table_name', String(200), nullable=False, index=True),
            Column('chunk_id', String(36), nullable=False),
            Column('relevance_score', Integer, default=1),
            Column('created_at', DateTime, default=datetime.utcnow),
            Index('idx_table_chunk', 'table_name', 'chunk_id', unique=True)
        )
    
    # ========================================================================
    # Text Chunk Operations
    # ========================================================================
    
    def insert_chunks(self, chunks: List[TextChunk]) -> int:
        """Insert text chunks into database."""
        with self.Session() as session:
            try:
                # Prepare chunk data for bulk insert
                chunk_data = []
                for chunk in chunks:
                    chunk_data.append({
                        'chunk_id': str(chunk.chunk_id),
                        'doc_id': chunk.doc_id,
                        'content': chunk.content,
                        'chunk_index': chunk.chunk_index,
                        'metadata': json.dumps(chunk.metadata) if chunk.metadata else '{}'
                    })
                
                # Batch insert in chunks to avoid parameter limit
                batch_size = 500
                for i in range(0, len(chunk_data), batch_size):
                    batch = chunk_data[i:i + batch_size]
                    session.execute(insert(self.raw_chunks), batch)
                
                session.commit()
                logger.info(f"Inserted {len(chunks)} chunks")
                return len(chunks)
            except Exception as e:
                session.rollback()
                logger.error(f"Error inserting chunks: {e}")
                raise
    
    def get_chunks_by_doc(self, doc_id: str) -> List[TextChunk]:
        """Retrieve all chunks for a document."""
        with self.Session() as session:
            stmt = select(self.raw_chunks).where(
                self.raw_chunks.c.doc_id == doc_id
            ).order_by(self.raw_chunks.c.chunk_index)
            
            result = session.execute(stmt)
            rows = result.fetchall()
            
            return [
                TextChunk(
                    chunk_id=str(row.chunk_id),
                    doc_id=row.doc_id,
                    content=row.content,
                    chunk_index=row.chunk_index,
                    metadata=json.loads(row.metadata) if isinstance(row.metadata, str) else (row.metadata or {})
                )
                for row in rows
            ]
    
    def get_chunks_by_ids(self, chunk_ids: List[str]) -> List[TextChunk]:
        """Retrieve chunks by their IDs."""
        if not chunk_ids:
            return []
        
        # Batch requests to avoid SQLite parameter limit
        batch_size = 900  # Safe for SQLite (limit is usually 999)
        all_chunks = []
        
        with self.Session() as session:
            for i in range(0, len(chunk_ids), batch_size):
                batch_ids = chunk_ids[i:i + batch_size]
                str_ids = [str(cid) for cid in batch_ids]
                
                stmt = select(self.raw_chunks).where(
                    self.raw_chunks.c.chunk_id.in_(str_ids)
                )
                
                result = session.execute(stmt)
                rows = result.fetchall()
                
                for row in rows:
                    all_chunks.append(TextChunk(
                        chunk_id=str(row.chunk_id),
                        doc_id=row.doc_id,
                        content=row.content,
                        chunk_index=row.chunk_index,
                        metadata=row.metadata or {}
                    ))
            
            return all_chunks
    
    def get_all_chunks(self, limit: Optional[int] = None) -> List[TextChunk]:
        """Retrieve all chunks, optionally limited."""
        with self.Session() as session:
            stmt = select(self.raw_chunks).order_by(
                self.raw_chunks.c.doc_id,
                self.raw_chunks.c.chunk_index
            )
            
            if limit:
                stmt = stmt.limit(limit)
            
            result = session.execute(stmt)
            rows = result.fetchall()
            
            return [
                TextChunk(
                    chunk_id=str(row.chunk_id),
                    doc_id=row.doc_id,
                    content=row.content,
                    chunk_index=row.chunk_index,
                    metadata=json.loads(row.metadata) if isinstance(row.metadata, str) else (row.metadata or {})
                )
                for row in rows
            ]
    
    def count_chunks(self) -> int:
        """Count total chunks in database."""
        with self.Session() as session:
            stmt = select(self.raw_chunks)
            result = session.execute(stmt)
            return len(result.fetchall())
    
    # ========================================================================
    # Metadata Registry Operations
    # ========================================================================
    
    def update_metadata(
        self,
        table_name: str,
        column_name: str,
        predicate_scope: List[str],
        status: str,
        record_count: int = 0
    ) -> None:
        """Update or insert metadata registry entry."""
        with self.Session() as session:
            try:
                # Check if entry exists
                stmt = select(self.metadata_registry).where(
                    (self.metadata_registry.c.table_name == table_name) &
                    (self.metadata_registry.c.column_name == column_name)
                )
                result = session.execute(stmt)
                existing = result.fetchone()
                
                if existing:
                    # Update existing entry
                    update_stmt = update(self.metadata_registry).where(
                        (self.metadata_registry.c.table_name == table_name) &
                        (self.metadata_registry.c.column_name == column_name)
                    ).values(
                        predicate_scope=json.dumps(predicate_scope),
                        status=status,
                        record_count=record_count,
                        last_updated=datetime.utcnow()
                    )
                    session.execute(update_stmt)
                else:
                    # Insert new entry
                    insert_stmt = insert(self.metadata_registry).values(
                        table_name=table_name,
                        column_name=column_name,
                        predicate_scope=json.dumps(predicate_scope),
                        status=status,
                        record_count=record_count
                    )
                    session.execute(insert_stmt)
                
                session.commit()
                logger.debug(f"Updated metadata for {table_name}.{column_name}")
            except Exception as e:
                session.rollback()
                logger.error(f"Error updating metadata: {e}")
                raise
    
    def get_metadata(
        self,
        table_name: Optional[str] = None,
        column_name: Optional[str] = None
    ) -> List[MetadataEntry]:
        """Retrieve metadata entries."""
        with self.Session() as session:
            stmt = select(self.metadata_registry)
            
            if table_name:
                stmt = stmt.where(self.metadata_registry.c.table_name == table_name)
            if column_name:
                stmt = stmt.where(self.metadata_registry.c.column_name == column_name)
            
            result = session.execute(stmt)
            rows = result.fetchall()
            
            return [
                MetadataEntry(
                    table_name=row.table_name,
                    column_name=row.column_name,
                    predicate_scope=json.loads(row.predicate_scope) if isinstance(row.predicate_scope, str) else (row.predicate_scope or []),
                    status=row.status,
                    last_updated=row.last_updated,
                    record_count=row.record_count
                )
                for row in rows
            ]
    
    def check_materialization(
        self,
        table_name: str,
        columns: List[str],
        predicates: List[str]
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Check if requested columns and predicates are materialized.
        Returns: (is_complete, missing_columns, missing_predicates)
        """
        metadata_entries = self.get_metadata(table_name=table_name)
        
        # Build lookup
        column_map = {}
        for entry in metadata_entries:
            if entry.column_name not in column_map:
                column_map[entry.column_name] = {
                    'status': entry.status,
                    'predicates': set(entry.predicate_scope)
                }
        
        # Check columns
        missing_columns = []
        for col in columns:
            if col not in column_map:
                missing_columns.append(col)
        
        # Check predicates
        missing_predicates = []
        for pred in predicates:
            # Extract column from predicate (simple parsing)
            pred_col = pred.split('=')[0].strip() if '=' in pred else pred.split()[0].strip()

            if pred_col in column_map:
                col_entry = column_map[pred_col]
                # STATUS_FULL means ALL rows were extracted for this column —
                # any predicate value is already covered, no re-extraction needed.
                if col_entry['status'] == STATUS_FULL:
                    continue
                if pred not in col_entry['predicates']:
                    missing_predicates.append(pred)
            else:
                missing_predicates.append(pred)
        
        is_complete = len(missing_columns) == 0 and len(missing_predicates) == 0
        
        return is_complete, missing_columns, missing_predicates
    
    # ========================================================================
    # Provenance Operations
    # ========================================================================
    
    def insert_provenance(
        self,
        row_id: str,
        table_name: str,
        chunk_ids: List[str]
    ) -> None:
        """Insert provenance record."""
        with self.Session() as session:
            try:
                stmt = insert(self.row_provenance).values(
                    row_id=str(row_id),
                    table_name=table_name,
                    chunk_ids=json.dumps(chunk_ids)
                )
                session.execute(stmt)
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"Error inserting provenance: {e}")
                raise

    def update_provenance_chunks(
        self,
        row_id: str,
        chunk_ids: List[str]
    ) -> None:
        """Replace the chunk_ids for an existing provenance record."""
        with self.Session() as session:
            try:
                stmt = text(
                    "UPDATE row_provenance SET chunk_ids = :chunk_ids WHERE row_id = :row_id"
                )
                session.execute(stmt, {"chunk_ids": json.dumps(chunk_ids), "row_id": row_id})
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"Error updating provenance chunks for {row_id}: {e}")
                raise

    def delete_provenance(self, row_id: str) -> None:
        """Delete provenance record for a row."""
        with self.Session() as session:
            try:
                stmt = text("DELETE FROM row_provenance WHERE row_id = :row_id")
                session.execute(stmt, {"row_id": row_id})
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"Error deleting provenance for {row_id}: {e}")
                raise
    
    def get_provenance(
        self,
        row_ids: Optional[List[str]] = None,
        table_name: Optional[str] = None
    ) -> List[ProvenanceRecord]:
        """Retrieve provenance records."""
        with self.Session() as session:
            stmt = select(self.row_provenance)
            
            if table_name:
                stmt = stmt.where(self.row_provenance.c.table_name == table_name)
            
            if row_ids:
                # Batch queries to avoid parameter limit
                batch_size = 900
                all_records = []
                
                for i in range(0, len(row_ids), batch_size):
                    batch_ids = row_ids[i:i + batch_size]
                    str_ids = [str(rid) for rid in batch_ids]
                    
                    batch_stmt = stmt.where(self.row_provenance.c.row_id.in_(str_ids))
                    result = session.execute(batch_stmt)
                    rows = result.fetchall()
                    
                    for row in rows:
                        all_records.append(ProvenanceRecord(
                            row_id=str(row.row_id),
                            table_name=row.table_name,
                            chunk_ids=json.loads(row.chunk_ids) if isinstance(row.chunk_ids, str) else (row.chunk_ids or [])
                        ))
                
                return all_records
            else:
                result = session.execute(stmt)
                rows = result.fetchall()
                
                return [
                    ProvenanceRecord(
                        row_id=str(row.row_id),
                        table_name=row.table_name,
                        chunk_ids=json.loads(row.chunk_ids) if isinstance(row.chunk_ids, str) else (row.chunk_ids or [])
                    )
                    for row in rows
                ]
    
    # ========================================================================
    # Candidate Index Operations
    # ========================================================================
    
    def insert_candidates(
        self,
        table_name: str,
        chunk_ids: List[str],
        relevance_scores: Optional[List[int]] = None
    ) -> int:
        """Insert candidate chunks for a table."""
        with self.Session() as session:
            try:
                if relevance_scores is None:
                    relevance_scores = [1] * len(chunk_ids)
                
                # Get existing chunk_ids to avoid duplicates
                existing_ids = set()
                existing_result = session.execute(
                    select(self.candidate_index.c.chunk_id).where(
                        self.candidate_index.c.table_name == table_name
                    )
                ).fetchall()
                existing_ids = {str(row.chunk_id) for row in existing_result}
                
                # Prepare new candidates (filter out existing)
                new_candidates = []
                for chunk_id, score in zip(chunk_ids, relevance_scores):
                    chunk_id_str = str(chunk_id)
                    if chunk_id_str not in existing_ids:
                        new_candidates.append({
                            'table_name': table_name,
                            'chunk_id': chunk_id_str,
                            'relevance_score': score
                        })
                
                # Batch insert in chunks to avoid SQLite parameter limit (999)
                batch_size = 500  # Safe batch size for SQLite
                inserted_count = 0
                
                for i in range(0, len(new_candidates), batch_size):
                    batch = new_candidates[i:i + batch_size]
                    if batch:
                        session.execute(insert(self.candidate_index), batch)
                        inserted_count += len(batch)
                
                session.commit()
                logger.info(f"Inserted {inserted_count} new candidates for {table_name} (skipped {len(chunk_ids) - inserted_count} duplicates)")
                return inserted_count
            except Exception as e:
                session.rollback()
                logger.error(f"Error inserting candidates: {e}")
                raise
    
    def get_candidates(self, table_name: str) -> List[str]:
        """Retrieve candidate chunk IDs for a table."""
        with self.Session() as session:
            stmt = select(self.candidate_index.c.chunk_id).where(
                self.candidate_index.c.table_name == table_name
            ).order_by(self.candidate_index.c.relevance_score.desc())
            
            result = session.execute(stmt)
            rows = result.fetchall()
            
            return [str(row.chunk_id) for row in rows]
    
    # ========================================================================
    # Dynamic Table Management
    # ========================================================================
    
    def create_dynamic_table(
        self,
        table_name: str,
        schema: Dict[str, str]
    ) -> None:
        """
        Create a dynamic table for extracted data.
        schema: {column_name: sql_type}
        """
        with self.engine.connect() as conn:
            try:
                # Build CREATE TABLE statement
                columns = [
                    f"{col_name} {col_type}"
                    for col_name, col_type in schema.items()
                ]
                
                # Add standard columns
                columns.insert(0, "row_id TEXT PRIMARY KEY")
                columns.append("created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                
                create_stmt = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    {', '.join(columns)}
                )
                """
                
                conn.execute(text(create_stmt))
                conn.commit()
                
                logger.info(f"Created table: {table_name}")
            except Exception as e:
                logger.error(f"Error creating table {table_name}: {e}")
                raise
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name = :table_name
            """), {"table_name": table_name})
            return result.fetchone() is not None
    
    def execute_sql(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute an arbitrary read-only SQL query against the DB and return
        results as a list of dicts.  Raises RuntimeError on failure.
        """
        with self.engine.connect() as conn:
            try:
                result = conn.execute(text(query))
                col_names = list(result.keys())
                return [dict(zip(col_names, row)) for row in result.fetchall()]
            except Exception as e:
                logger.error(f"SQL execution failed: {e}")
                raise RuntimeError(f"SQL execution failed: {e}") from e

    def close(self):
        """Close database connections."""
        self.engine.dispose()
        logger.info("DataLayer connections closed")


# ============================================================================
# Text Chunking Utilities
# ============================================================================

class RecursiveCharacterSplitter:
    """
    Implements recursive character splitting for text chunking.
    Based on LangChain's RecursiveCharacterTextSplitter.
    """
    
    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        separators: List[str] = CHUNK_SEPARATORS
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators
    
    def split_text(self, text: str) -> List[str]:
        """Split text into chunks recursively."""
        return self._split_text_recursive(text, self.separators)
    
    def _split_text_recursive(
        self,
        text: str,
        separators: List[str]
    ) -> List[str]:
        """Recursively split text using separators."""
        if not separators:
            return self._split_by_length(text)
        
        separator = separators[0]
        remaining_separators = separators[1:]
        
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)
        
        # Merge small splits and recursively split large ones
        chunks = []
        current_chunk = ""
        
        for split in splits:
            if len(current_chunk) + len(split) <= self.chunk_size:
                current_chunk += split + separator
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                if len(split) > self.chunk_size:
                    # Recursively split large chunk
                    sub_chunks = self._split_text_recursive(split, remaining_separators)
                    chunks.extend(sub_chunks)
                    current_chunk = ""
                else:
                    current_chunk = split + separator
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return self._merge_with_overlap(chunks)
    
    def _split_by_length(self, text: str) -> List[str]:
        """Split text by fixed length."""
        chunks = []
        for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
            chunks.append(text[i:i + self.chunk_size])
        return chunks
    
    def _merge_with_overlap(self, chunks: List[str]) -> List[str]:
        """Add overlap between chunks."""
        if not chunks or self.chunk_overlap == 0:
            return chunks
        
        merged = []
        for i, chunk in enumerate(chunks):
            if i > 0 and self.chunk_overlap > 0:
                # Add overlap from previous chunk
                prev_chunk = chunks[i - 1]
                overlap = prev_chunk[-self.chunk_overlap:]
                chunk = overlap + chunk
            merged.append(chunk)
        
        return merged
    
    def get_distinct_values(self, table_name: str, column_name: str) -> List[str]:
        """Get all distinct values from a column in a dynamic table."""
        with self.Session() as session:
            try:
                # Query the dynamic table
                stmt = text(f"SELECT DISTINCT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL")
                result = session.execute(stmt)
                values = [str(row[0]) for row in result.fetchall()]
                return values
            except Exception as e:
                logger.error(f"Error getting distinct values from {table_name}.{column_name}: {e}")
                return []
    
    def update_column_values(
        self,
        table_name: str,
        column_name: str,
        value_map: Dict[str, str]
    ) -> int:
        """
        Update column values based on a mapping.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column to update
            value_map: Dictionary mapping old_value -> new_value
            
        Returns:
            Number of rows updated
        """
        with self.Session() as session:
            try:
                updated_count = 0
                for old_value, new_value in value_map.items():
                    # Use parameterized query to prevent SQL injection
                    stmt = text(
                        f"UPDATE {table_name} SET {column_name} = :new_value "
                        f"WHERE {column_name} = :old_value"
                    )
                    result = session.execute(
                        stmt,
                        {"new_value": new_value, "old_value": old_value}
                    )
                    updated_count += result.rowcount
                
                session.commit()
                logger.info(f"Updated {updated_count} rows in {table_name}.{column_name}")
                return updated_count
            except Exception as e:
                session.rollback()
                logger.error(f"Error updating column values in {table_name}.{column_name}: {e}")
                raise
    
    def insert_record(
        self,
        table_name: str,
        record: Dict[str, Any]
    ) -> str:
        """
        Insert a record into a dynamic table.
        Returns the generated row_id.
        """
        with self.engine.connect() as conn:
            try:
                row_id = str(uuid.uuid4())
                
                # Add row_id to record
                full_record = {"row_id": row_id, **record}
                
                # Build INSERT statement - handle None values explicitly
                columns = list(full_record.keys())
                values = [full_record[col] for col in columns]
                
                columns_str = ", ".join(columns)
                placeholders = ", ".join([f":{col}" for col in columns])
                
                sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                
                # Create parameter dict - convert None to NULL-compatible value
                params = {}
                for col, val in zip(columns, values):
                    if val is None:
                        params[col] = None
                    elif isinstance(val, (list, dict)):
                        params[col] = json.dumps(val)
                    else:
                        params[col] = val
                
                conn.execute(text(sql), params)
                conn.commit()
                
                return row_id
            except Exception as e:
                logger.error(f"Error inserting record into {table_name}: {e}")
                raise

    def get_all_records(self, table_name: str) -> List[Dict[str, Any]]:
        """Return all rows from a dynamic table as a list of dicts."""
        with self.engine.connect() as conn:
            try:
                result = conn.execute(text(f"SELECT * FROM {table_name}"))
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
            except Exception as e:
                logger.error(f"Error fetching all records from {table_name}: {e}")
                raise

    def update_record(
        self,
        table_name: str,
        row_id: str,
        data: Dict[str, Any]
    ) -> None:
        """Update specific fields of an existing row identified by row_id."""
        if not data:
            return
        with self.engine.connect() as conn:
            try:
                set_clauses = ", ".join([f"{col} = :{col}" for col in data.keys()])
                params = {col: (json.dumps(val) if isinstance(val, (list, dict)) else val)
                          for col, val in data.items()}
                params["_row_id"] = row_id
                sql = f"UPDATE {table_name} SET {set_clauses} WHERE row_id = :_row_id"
                conn.execute(text(sql), params)
                conn.commit()
            except Exception as e:
                logger.error(f"Error updating record {row_id} in {table_name}: {e}")
                raise

    def delete_record(self, table_name: str, row_id: str) -> None:
        """Delete a row from a dynamic table by row_id."""
        with self.engine.connect() as conn:
            try:
                conn.execute(
                    text(f"DELETE FROM {table_name} WHERE row_id = :row_id"),
                    {"row_id": row_id}
                )
                conn.commit()
            except Exception as e:
                logger.error(f"Error deleting record {row_id} from {table_name}: {e}")
                raise

    def create_chunks(
        self,
        text: str,
        doc_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[TextChunk]:
        """Create TextChunk objects from text."""
        splits = self.split_text(text)
        
        chunks = []
        for idx, content in enumerate(splits):
            chunk = TextChunk(
                chunk_id=str(uuid.uuid4()),
                doc_id=doc_id,
                content=content,
                chunk_index=idx,
                metadata=metadata or {}
            )
            chunks.append(chunk)
        
        return chunks

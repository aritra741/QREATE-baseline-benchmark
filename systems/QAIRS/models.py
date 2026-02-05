"""
Data models for QAIRS system.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, JSON, Text,
    create_engine, MetaData, Table, Enum as SQLEnum
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ============================================================================
# Enums
# ============================================================================

class MaterializationStatus(str, Enum):
    """Status of predicate materialization."""
    PENDING = "pending"
    PARTIAL = "partial"
    MATERIALIZED = "materialized"
    FAILED = "failed"


# ============================================================================
# SQLAlchemy Models (Database Tables)
# ============================================================================

class MetadataRegistry(Base):
    """
    Tracks which predicates have been materialized.
    This is the core of the subsumption logic.
    """
    __tablename__ = "metadata_registry"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(255), nullable=False, index=True)
    predicate_scope = Column(Text, nullable=False)  # SQL WHERE clause
    status = Column(SQLEnum(MaterializationStatus), nullable=False, default=MaterializationStatus.PENDING)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Statistics
    chunks_processed = Column(Integer, default=0)
    rows_extracted = Column(Integer, default=0)
    
    # Metadata
    metadata_json = Column(JSON, nullable=True)  # Additional info


class ChunkMetadata(Base):
    """
    Stores metadata about processed chunks.
    Tracks which predicates have been applied to each chunk.
    """
    __tablename__ = "chunk_metadata"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String(255), nullable=False, unique=True, index=True)
    
    # Processing history
    predicates_applied = Column(JSON, default=list)  # List of predicate IDs
    last_processed = Column(DateTime, default=datetime.utcnow)
    
    # Flags
    has_more_data = Column(Boolean, default=False)  # LLM indicated incomplete extraction
    needs_reprocessing = Column(Boolean, default=False)


# ============================================================================
# Pydantic Models (Data Transfer Objects)
# ============================================================================

class SieveEntry(BaseModel):
    """
    Represents a single entry in the Sieve index.
    """
    chunk_id: str
    dict_tags: List[str] = Field(default_factory=list)
    type_mask: Dict[str, bool] = Field(default_factory=dict)
    
    # Optional: entity mentions
    entities: Dict[str, List[str]] = Field(default_factory=dict)  # {"PERSON": ["John"], ...}


class TableSchema(BaseModel):
    """
    Represents a table schema for extraction.
    """
    table_name: str
    columns: Dict[str, str]  # column_name -> type
    primary_key: Optional[List[str]] = None
    foreign_keys: Dict[str, str] = Field(default_factory=dict)  # column -> referenced_table.column
    
    # Optional: value constraints
    enums: Dict[str, List[str]] = Field(default_factory=dict)  # column -> allowed_values
    
    def to_prompt_string(self) -> str:
        """Generate schema description for LLM prompt."""
        lines = [f"Table: {self.table_name}"]
        lines.append("Columns:")
        for col, dtype in self.columns.items():
            enum_info = f" (enum: {self.enums[col]})" if col in self.enums else ""
            lines.append(f"  - {col}: {dtype}{enum_info}")
        return "\n".join(lines)


class Predicate(BaseModel):
    """
    Represents a WHERE clause predicate.
    """
    table_name: str
    conditions: List[str]  # List of condition strings, e.g., ["status = 'Denied'", "cost > 100"]
    
    def to_sql_where(self) -> str:
        """Convert to SQL WHERE clause."""
        return " AND ".join(self.conditions)
    
    def __hash__(self):
        return hash((self.table_name, tuple(sorted(self.conditions))))


class Query(BaseModel):
    """
    Represents a user query.
    """
    query_id: str
    table_name: str
    predicate: Optional[Predicate] = None
    select_columns: List[str] = Field(default_factory=lambda: ["*"])
    
    def to_sql(self) -> str:
        """Generate SQL query string."""
        cols = ", ".join(self.select_columns)
        sql = f"SELECT {cols} FROM {self.table_name}"
        if self.predicate:
            sql += f" WHERE {self.predicate.to_sql_where()}"
        return sql


class ExtractionTask(BaseModel):
    """
    Represents a task for the extraction engine.
    """
    task_id: str
    table_schema: TableSchema
    predicate: Optional[Predicate] = None
    candidate_chunks: List[str]  # List of chunk IDs to process
    
    # Dictionary mapping for this task
    dictionary_map: Dict[str, str] = Field(default_factory=dict)  # synonym -> canonical


class ExtractionResult(BaseModel):
    """
    Result from LLM extraction.
    """
    chunk_id: str
    data: List[Dict[str, Any]]  # List of extracted rows
    has_more: bool = False  # LLM indicates incomplete extraction
    confidence: Optional[float] = None
    error: Optional[str] = None


class WorkloadPlan(BaseModel):
    """
    Represents an optimized extraction plan for a workload.
    """
    plan_id: str
    tasks: List[ExtractionTask]
    estimated_chunks: int
    estimated_llm_calls: int
    
    # Optimization metadata
    merged_predicates: Dict[str, List[str]] = Field(default_factory=dict)  # table -> predicates


# ============================================================================
# Helper Functions
# ============================================================================

def create_tables(connection_string: str) -> None:
    """Create all database tables."""
    engine = create_engine(connection_string)
    Base.metadata.create_all(engine)


def get_table_schema_from_db(connection_string: str, table_name: str) -> Optional[TableSchema]:
    """
    Extract schema from existing database table.
    """
    engine = create_engine(connection_string)
    metadata = MetaData()
    metadata.reflect(bind=engine)
    
    if table_name not in metadata.tables:
        return None
    
    table = metadata.tables[table_name]
    columns = {col.name: str(col.type) for col in table.columns}
    pk = [col.name for col in table.primary_key.columns]
    
    return TableSchema(
        table_name=table_name,
        columns=columns,
        primary_key=pk if pk else None
    )

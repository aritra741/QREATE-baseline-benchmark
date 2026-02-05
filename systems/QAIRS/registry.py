"""
Metadata Registry: Tracks materialization state of predicates.
"""
from typing import List, Optional, Dict
from datetime import datetime
from sqlalchemy import create_engine, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from models import (
    MetadataRegistry, ChunkMetadata, MaterializationStatus,
    Predicate, Base
)
from config import QAIRSConfig


class Registry:
    """
    The Metadata Registry tracks which predicates have been materialized.
    This is the core of the subsumption logic.
    """
    
    def __init__(self, config: QAIRSConfig):
        self.config = config
        self.engine = create_engine(config.database.connection_string)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)
        logger.info("Registry initialized")
    
    def check_predicate(self, predicate: Predicate) -> Optional[MaterializationStatus]:
        """
        Check if a predicate has been materialized.
        
        Returns:
            MaterializationStatus if found, None otherwise
        """
        with self.SessionLocal() as session:
            entry = session.query(MetadataRegistry).filter(
                and_(
                    MetadataRegistry.table_name == predicate.table_name,
                    MetadataRegistry.predicate_scope == predicate.to_sql_where()
                )
            ).first()
            
            return entry.status if entry else None
    
    def register_predicate(
        self,
        predicate: Predicate,
        status: MaterializationStatus = MaterializationStatus.PENDING
    ) -> int:
        """
        Register a new predicate in the registry.
        
        Returns:
            Registry entry ID
        """
        with self.SessionLocal() as session:
            # Check if already exists
            existing = session.query(MetadataRegistry).filter(
                and_(
                    MetadataRegistry.table_name == predicate.table_name,
                    MetadataRegistry.predicate_scope == predicate.to_sql_where()
                )
            ).first()
            
            if existing:
                logger.warning(f"Predicate already registered: {predicate.to_sql_where()}")
                return existing.id
            
            # Create new entry
            entry = MetadataRegistry(
                table_name=predicate.table_name,
                predicate_scope=predicate.to_sql_where(),
                status=status
            )
            session.add(entry)
            session.commit()
            
            logger.info(f"Registered predicate: {predicate.to_sql_where()}")
            return entry.id
    
    def update_status(
        self,
        predicate: Predicate,
        status: MaterializationStatus,
        chunks_processed: int = 0,
        rows_extracted: int = 0
    ) -> None:
        """
        Update the status of a predicate.
        """
        with self.SessionLocal() as session:
            entry = session.query(MetadataRegistry).filter(
                and_(
                    MetadataRegistry.table_name == predicate.table_name,
                    MetadataRegistry.predicate_scope == predicate.to_sql_where()
                )
            ).first()
            
            if not entry:
                logger.error(f"Predicate not found in registry: {predicate.to_sql_where()}")
                return
            
            entry.status = status
            entry.last_updated = datetime.utcnow()
            
            if chunks_processed > 0:
                entry.chunks_processed += chunks_processed
            if rows_extracted > 0:
                entry.rows_extracted += rows_extracted
            
            session.commit()
            logger.info(f"Updated predicate status: {status}")
    
    def get_materialized_predicates(self, table_name: str) -> List[str]:
        """
        Get all materialized predicates for a table.
        
        Returns:
            List of predicate WHERE clauses
        """
        with self.SessionLocal() as session:
            entries = session.query(MetadataRegistry).filter(
                and_(
                    MetadataRegistry.table_name == table_name,
                    MetadataRegistry.status == MaterializationStatus.MATERIALIZED
                )
            ).all()
            
            return [entry.predicate_scope for entry in entries]
    
    def find_subsumption(self, predicate: Predicate) -> Optional[str]:
        """
        Check if the predicate is subsumed by an existing materialized predicate.
        
        This is a simplified version. A full implementation would parse SQL
        and check logical subsumption (e.g., "status='Denied'" subsumes nothing,
        but "status IN ('Denied', 'Paid')" subsumes both).
        
        Returns:
            Subsuming predicate if found, None otherwise
        """
        materialized = self.get_materialized_predicates(predicate.table_name)
        
        # Simple exact match check
        predicate_str = predicate.to_sql_where()
        if predicate_str in materialized:
            return predicate_str
        
        # TODO: Implement proper subsumption logic
        # For now, just return None if no exact match
        return None
    
    def mark_chunk_processed(
        self,
        chunk_id: str,
        predicate_id: int,
        has_more: bool = False
    ) -> None:
        """
        Mark a chunk as processed for a specific predicate.
        """
        with self.SessionLocal() as session:
            chunk_meta = session.query(ChunkMetadata).filter(
                ChunkMetadata.chunk_id == chunk_id
            ).first()
            
            if not chunk_meta:
                chunk_meta = ChunkMetadata(chunk_id=chunk_id)
                session.add(chunk_meta)
            
            # Update processing history
            if predicate_id not in chunk_meta.predicates_applied:
                chunk_meta.predicates_applied.append(predicate_id)
            
            chunk_meta.last_processed = datetime.utcnow()
            chunk_meta.has_more_data = has_more
            
            session.commit()
    
    def get_chunk_history(self, chunk_id: str) -> Optional[ChunkMetadata]:
        """
        Get processing history for a chunk.
        """
        with self.SessionLocal() as session:
            return session.query(ChunkMetadata).filter(
                ChunkMetadata.chunk_id == chunk_id
            ).first()
    
    def get_statistics(self) -> Dict:
        """
        Get registry statistics.
        """
        with self.SessionLocal() as session:
            total = session.query(MetadataRegistry).count()
            materialized = session.query(MetadataRegistry).filter(
                MetadataRegistry.status == MaterializationStatus.MATERIALIZED
            ).count()
            pending = session.query(MetadataRegistry).filter(
                MetadataRegistry.status == MaterializationStatus.PENDING
            ).count()
            
            total_rows = session.query(
                MetadataRegistry
            ).with_entities(
                MetadataRegistry.rows_extracted
            ).all()
            
            return {
                'total_predicates': total,
                'materialized': materialized,
                'pending': pending,
                'total_rows_extracted': sum(r[0] for r in total_rows if r[0])
            }
    
    def reset(self) -> None:
        """
        Reset the registry (for testing).
        """
        with self.SessionLocal() as session:
            session.query(MetadataRegistry).delete()
            session.query(ChunkMetadata).delete()
            session.commit()
        logger.warning("Registry reset")

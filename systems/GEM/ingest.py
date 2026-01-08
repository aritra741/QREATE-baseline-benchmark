"""
Ingest Module - One-Pass Ingestion with Integrated HNSW-Union-Find

Implements streaming blocking with discriminative LLM resolution:
1. For each mention, use Blocker.add_and_link() for incremental HNSW-Union-Find
2. Get all blocks from Blocker.get_blocks()
3. For each block, call LLM.resolve_block() for discriminative clustering
4. Register canonical names with semantic shim
"""

import logging
from typing import List, Dict, Optional, Tuple
import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

from .blocking import SemanticBlocker, UnionFind
from .resolver import EntityResolver
from .db_engine import DBEngine
from .schema_loader import Schema
from .llm import LLMClient
from .config import SIMILARITY_THRESHOLD, TOP_K_NEIGHBORS


logger = logging.getLogger(__name__)


class InlineDeduplicator:
    """Performs inline deduplication using integrated HNSW-Union-Find blocking and LLM resolution."""
    
    def __init__(self, 
                 blocker: SemanticBlocker,
                 resolver: EntityResolver,
                 db_engine: DBEngine,
                 schema: Schema,
                 logger: Optional[logging.Logger] = None):
        """Initialize deduplicator.
        
        Args:
            blocker: SemanticBlocker instance with integrated HNSW-Union-Find
            resolver: EntityResolver instance
            db_engine: DBEngine instance
            schema: Schema for the entity
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.blocker = blocker
        self.resolver = resolver
        self.db_engine = db_engine
        self.schema = schema
        self.llm_client = LLMClient(logger=logger)
        
        self.records = []  # Store all records
        self.canonical_map = {}  # Map mention_text -> canonical_name
        self.mention_to_records = {}  # Map mention_text -> list of record indices
    
    def ingest_mention(self, mention_text: str, record_idx: int):
        """Ingest a single mention using integrated HNSW-Union-Find blocking.
        
        Args:
            mention_text: The mention text to add to blocker
            record_idx: Index of the record containing this mention
        """
        if not mention_text:
            return
        
        # Add to blocker with streaming
        blocker_idx = self.blocker.add_and_link(mention_text)
        
        # Track mention -> records mapping
        if mention_text not in self.mention_to_records:
            self.mention_to_records[mention_text] = []
        self.mention_to_records[mention_text].append(record_idx)
    
    def ingest_batch(self, records: List[Dict], key_attributes: List[str]) -> Tuple[List[Dict], Dict]:
        """Ingest batch of records using streaming HNSW-Union-Find blocking.
        
        Args:
            records: List of records to ingest
            key_attributes: Attributes to use for blocking
            
        Returns:
            Tuple of (final_records, canonical_map)
        """
        self.logger.info(f"Ingesting {len(records)} records with streaming HNSW-Union-Find")
        
        self.records = records.copy()
        
        # Phase 1: Stream mentions through blocker with ad-hoc HNSW-Union-Find
        self.logger.info("Phase 1: Streaming mentions through HNSW-Union-Find blocker")
        for record_idx, record in enumerate(records):
            # Extract key values (mentions)
            mentions = []
            for attr in key_attributes:
                val = record.get(attr)
                if val is not None:
                    mention_text = str(val).strip()
                    if mention_text:
                        mentions.append(mention_text)
            
            # Add each mention to blocker
            for mention_text in mentions:
                self.ingest_mention(mention_text, record_idx)
            
            if (record_idx + 1) % 100 == 0:
                self.logger.info(f"Streamed {record_idx + 1}/{len(records)} records")
        
        # Phase 2: Get blocks from Union-Find
        self.logger.info("Phase 2: Extracting blocks from Union-Find")
        mention_blocks = self.blocker.get_blocks()
        self.logger.info(f"Extracted {len(mention_blocks)} blocks")
        
        # Phase 3: Discriminative LLM resolution
        self.logger.info("Phase 3: Resolving blocks with discriminative LLM")
        self.canonical_map = {}
        
        for block_idx, (representative, mentions_in_block) in enumerate(mention_blocks.items()):
            # Resolve block with LLM
            resolution = self.llm_client.resolve_block(mentions_in_block)
            
            # Update canonical map with multi-entity resolution
            for canonical_name, synonyms in resolution.items():
                for synonym in synonyms:
                    self.canonical_map[synonym] = canonical_name
            
            if (block_idx + 1) % 10 == 0:
                self.logger.info(f"Resolved {block_idx + 1}/{len(mention_blocks)} blocks")
        
        self.logger.info(f"Built canonical map with {len(self.canonical_map)} mention -> canonical mappings")
        
        # Phase 4: Update resolver with canonical map
        self.resolver.canonical_map = self.canonical_map
        self.db_engine.set_resolver(self.resolver)
        
        return self.records, self.canonical_map
    
    def finalize(self) -> List[Dict]:
        """Finalize by normalizing records with canonical names.
        
        Returns:
            Records normalized with canonical entity names
        """
        if not self.records:
            self.logger.warning("No records to finalize")
            return []
        
        self.logger.info("Finalizing records with canonical normalization")
        
        key_attributes = [attr.name for attr in self.schema.attributes if attr.is_key_attribute]
        
        # Normalize records using canonical map
        final_records = []
        for record in self.records:
            normalized_record = self.resolver.normalize_record(record, key_attributes, self.schema)
            final_records.append(normalized_record)
        
        self.logger.info(f"Finalized {len(final_records)} records")
        
        return final_records

"""
Ingest Module - One-Pass Ingestion with Inline Deduplication

Implements the "Search-before-Add" deduplication strategy:
1. For each new mention, query the HNSW index (K=1) to find nearest neighbor
2. If similarity > 0.98: exact duplicate, skip insertion
3. If similarity > 0.85: potential synonym, insert and link in Union-Find
4. Otherwise: new entity, insert and create new component
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
from .config import SIMILARITY_THRESHOLD, TOP_K_NEIGHBORS


logger = logging.getLogger(__name__)


class InlineDeduplicator:
    """Performs inline deduplication during ingestion using HNSW index."""
    
    def __init__(self, 
                 blocker: SemanticBlocker,
                 resolver: EntityResolver,
                 db_engine: DBEngine,
                 schema: Schema,
                 logger: Optional[logging.Logger] = None):
        """Initialize deduplicator.
        
        Args:
            blocker: SemanticBlocker instance
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
        
        self.index = None  # HNSW index
        self.embeddings = []  # Store all embeddings
        self.records = []  # Store all records
        self.union_find = None  # Union-Find for candidate blocks
        self.component_map = {}  # Map record_idx -> canonical_id
        
        # Thresholds
        self.exact_threshold = 0.98  # Exact duplicate
        self.synonym_threshold = 0.85  # Potential synonym
    
    def _build_index(self):
        """Build or rebuild FAISS index from current embeddings."""
        if not self.embeddings or len(self.embeddings) == 0:
            self.logger.debug("No embeddings to index")
            self.index = None
            return
        
        try:
            embeddings_array = np.array(self.embeddings).astype('float32')
            
            # Create L2 index
            self.index = faiss.IndexFlatL2(embeddings_array.shape[1])
            self.index.add(embeddings_array)
            
            self.logger.debug(f"Built FAISS index with {len(self.embeddings)} embeddings")
        except Exception as e:
            self.logger.error(f"Failed to build index: {e}")
            self.index = None
    
    def _search_nearest_neighbor(self, embedding: np.ndarray) -> Tuple[float, int]:
        """Search for nearest neighbor in index.
        
        Args:
            embedding: Query embedding
            
        Returns:
            Tuple of (similarity, record_index) or (0.0, -1) if no index
        """
        if self.index is None or len(self.embeddings) == 0:
            return 0.0, -1
        
        try:
            # Convert to float32
            query = np.array([embedding]).astype('float32')
            
            # Search for K=1 nearest neighbor
            distances, indices = self.index.search(query, k=1)
            
            # Convert L2 distance to similarity (0-1 scale)
            # similarity = 1 / (1 + distance)
            distance = distances[0][0]
            similarity = 1.0 / (1.0 + distance)
            neighbor_idx = indices[0][0]
            
            return similarity, neighbor_idx
        except Exception as e:
            self.logger.error(f"Failed to search index: {e}")
            return 0.0, -1
    
    def ingest_record(self, record: Dict, key_attributes: List[str]) -> int:
        """Ingest a single record with deduplication.
        
        Implements the "Search-before-Add" algorithm:
        1. Query index for nearest neighbor (K=1)
        2. Based on similarity:
           - > 0.98: exact duplicate, map to neighbor
           - > 0.85: synonym, insert and link
           - <= 0.85: new entity, insert
        
        Args:
            record: Record to ingest
            key_attributes: Attributes to use for deduplication
            
        Returns:
            Component ID for this record
        """
        # Extract key value for embedding
        key_value = " ".join(str(record.get(attr, "")) for attr in key_attributes if attr in record)
        
        if not key_value.strip():
            self.logger.warning(f"Record has no key values: {record}")
            return -1
        
        # Encode the key value
        embedding = self.blocker.encode_texts([key_value])
        if len(embedding) == 0:
            self.logger.warning(f"Failed to encode key value: {key_value}")
            return -1
        
        embedding = embedding[0]
        record_idx = len(self.records)
        
        # Initialize Union-Find if needed
        if self.union_find is None:
            self.union_find = UnionFind(10000)  # Start with 10k capacity
        
        # Deduplication Logic (K=1 Search)
        similarity, neighbor_idx = self._search_nearest_neighbor(embedding)
        
        if neighbor_idx >= 0:
            self.logger.debug(f"Record {record_idx}: NN similarity={similarity:.3f}")
            
            if similarity > self.exact_threshold:
                # Exact duplicate
                self.logger.info(f"Record {record_idx}: EXACT DUPLICATE of {neighbor_idx} (sim={similarity:.3f}), skipping insert")
                neighbor_component = self.component_map.get(neighbor_idx, neighbor_idx)
                self.component_map[record_idx] = neighbor_component
                return neighbor_component
            
            elif similarity > self.synonym_threshold:
                # Potential synonym
                self.logger.info(f"Record {record_idx}: SYNONYM of {neighbor_idx} (sim={similarity:.3f}), inserting and linking")
                self.union_find.union(record_idx, neighbor_idx)
                # Will be inserted below
            
            else:
                # New entity
                self.logger.debug(f"Record {record_idx}: NEW ENTITY (NN sim={similarity:.3f}), inserting")
        else:
            # No neighbors yet
            self.logger.debug(f"Record {record_idx}: First record or empty index")
        
        # Insert into database
        self.records.append(record)
        self.embeddings.append(embedding)
        self.component_map[record_idx] = record_idx
        
        # Rebuild index with new embedding
        self._build_index()
        
        return record_idx
    
    def ingest_batch(self, records: List[Dict], key_attributes: List[str]) -> Tuple[List[Dict], Dict]:
        """Ingest a batch of records with inline deduplication.
        
        Args:
            records: List of records to ingest
            key_attributes: Attributes to use for deduplication
            
        Returns:
            Tuple of (deduplicated_records, component_map)
        """
        self.logger.info(f"Ingesting {len(records)} records with inline deduplication")
        
        component_ids = []
        for i, record in enumerate(records):
            component_id = self.ingest_record(record, key_attributes)
            component_ids.append(component_id)
            
            if (i + 1) % 100 == 0:
                self.logger.info(f"Ingested {i + 1}/{len(records)} records")
        
        # Get candidate blocks from Union-Find
        candidate_blocks = self.union_find.get_clusters() if self.union_find else {}
        self.logger.info(f"Formed {len(candidate_blocks)} candidate blocks")
        
        # Filter records: only keep one record per component (deduplication)
        final_records = []
        seen_components = set()
        
        for i, record in enumerate(self.records):
            component = self.component_map.get(i, i)
            
            if component not in seen_components:
                final_records.append(record)
                seen_components.add(component)
            else:
                self.logger.debug(f"Record {i}: Deduplicated (component {component} already seen)")
        
        self.logger.info(f"After deduplication: {len(records)} -> {len(final_records)} records")
        
        return final_records, self.component_map
    
    def finalize(self) -> List[Dict]:
        """Finalize ingestion by resolving candidate blocks with LLM.
        
        Updates canonical names in records based on LLM resolution.
        
        Returns:
            Final deduplicated records with canonical names
        """
        if not self.records:
            self.logger.warning("No records to finalize")
            return []
        
        self.logger.info("Finalizing ingestion with LLM resolution")
        
        # Get candidate blocks from Union-Find
        if self.union_find:
            candidate_blocks = self.union_find.get_clusters()
            self.logger.info(f"Processing {len(candidate_blocks)} candidate blocks")
        else:
            candidate_blocks = {i: [i] for i in range(len(self.records))}
        
        # Resolve blocks and build canonical map
        key_attributes = [attr.name for attr in self.schema.attributes if attr.is_key_attribute]
        self.resolver.resolve_blocks(self.records, list(candidate_blocks.values()), key_attributes)
        
        # Apply canonical names to records
        final_records = []
        seen_components = set()
        
        for i, record in enumerate(self.records):
            component = self.component_map.get(i, i)
            
            if component not in seen_components:
                # Normalize record with canonical names
                normalized_record = self.resolver.normalize_record(record, key_attributes, self.schema)
                final_records.append(normalized_record)
                seen_components.add(component)
        
        self.logger.info(f"Finalized: {len(self.records)} records -> {len(final_records)} records")
        
        return final_records

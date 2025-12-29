"""
Blocking Module - Semantic Blocking for Entity Resolution

Clusters potentially identical entity mentions using:
- Sentence embeddings for vectorization
- FAISS for efficient nearest neighbor search
- Union-Find for clustering similar entities
"""

import logging
from typing import List, Dict, Set, Tuple
from collections import defaultdict

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    import faiss
except ImportError:
    np = None
    SentenceTransformer = None
    faiss = None

from .config import (
    EMBEDDING_MODEL, SIMILARITY_THRESHOLD, TOP_K_NEIGHBORS
)


logger = logging.getLogger(__name__)


class UnionFind:
    """Disjoint set (Union-Find) data structure for clustering."""
    
    def __init__(self, size: int):
        """Initialize Union-Find.
        
        Args:
            size: Number of elements
        """
        self.parent = list(range(size))
        self.rank = [0] * size
    
    def find(self, x: int) -> int:
        """Find root of element with path compression.
        
        Args:
            x: Element index
            
        Returns:
            Root element
        """
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x: int, y: int) -> bool:
        """Union two sets.
        
        Args:
            x: First element
            y: Second element
            
        Returns:
            True if sets were merged, False if already in same set
        """
        root_x = self.find(x)
        root_y = self.find(y)
        
        if root_x == root_y:
            return False
        
        # Union by rank
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1
        
        return True
    
    def get_clusters(self) -> Dict[int, List[int]]:
        """Get all clusters.
        
        Returns:
            Dictionary mapping root to list of elements in that cluster
        """
        clusters = defaultdict(list)
        for i in range(len(self.parent)):
            root = self.find(i)
            clusters[root].append(i)
        return clusters


class SemanticBlocker:
    """Performs semantic blocking on entity mentions."""
    
    def __init__(self, embedding_model: str = EMBEDDING_MODEL, logger: logging.Logger = None):
        """Initialize blocker.
        
        Args:
            embedding_model: Sentence transformer model name
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.embedding_model_name = embedding_model
        self.model = None
        self.index = None
        self._init_model()
    
    def _init_model(self):
        """Initialize sentence transformer model."""
        if SentenceTransformer is None:
            self.logger.warning("sentence-transformers not available, blocking will be skipped")
            return
        
        try:
            self.logger.info(f"Loading embedding model: {self.embedding_model_name}")
            self.model = SentenceTransformer(self.embedding_model_name)
            self.logger.info("Embedding model loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load embedding model: {e}")
            self.model = None
    
    def encode_texts(self, texts: List[str]) -> np.ndarray:
        """Encode texts to embeddings.
        
        Args:
            texts: List of texts to encode
            
        Returns:
            Array of embeddings (n, embedding_dim)
        """
        if self.model is None:
            self.logger.warning("Model not initialized")
            return np.array([])
        
        if not texts:
            return np.array([])
        
        try:
            embeddings = self.model.encode(texts, show_progress_bar=False)
            return embeddings
        except Exception as e:
            self.logger.error(f"Failed to encode texts: {e}")
            return np.array([])
    
    def build_index(self, embeddings: np.ndarray) -> faiss.Index:
        """Build FAISS index from embeddings.
        
        Args:
            embeddings: Array of embeddings (n, embedding_dim)
            
        Returns:
            FAISS index
        """
        if faiss is None:
            self.logger.warning("faiss not available")
            return None
        
        if embeddings.size == 0:
            self.logger.warning("No embeddings to index")
            return None
        
        try:
            # Ensure embeddings are float32
            embeddings = embeddings.astype(np.float32)
            
            # Create L2 index (faiss uses L2 distance, we'll convert to cosine similarity)
            dimension = embeddings.shape[1]
            index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity
            
            # Normalize vectors for cosine similarity
            faiss.normalize_L2(embeddings)
            index.add(embeddings)
            
            self.logger.info(f"Built FAISS index with {index.ntotal} vectors, dimension {dimension}")
            return index
        except Exception as e:
            self.logger.error(f"Failed to build FAISS index: {e}")
            return None
    
    def find_similar_items(self, embeddings: np.ndarray, k: int = TOP_K_NEIGHBORS,
                           threshold: float = SIMILARITY_THRESHOLD) -> List[List[int]]:
        """Find k nearest neighbors for each embedding.
        
        Args:
            embeddings: Array of embeddings (n, embedding_dim)
            k: Number of neighbors to return
            threshold: Similarity threshold (0-1)
            
        Returns:
            List of neighbor lists (per embedding)
        """
        if faiss is None or self.index is None:
            self.logger.warning("Index not available")
            return []
        
        try:
            # Normalize for cosine similarity
            embeddings = embeddings.astype(np.float32)
            faiss.normalize_L2(embeddings)
            
            # Search
            distances, indices = self.index.search(embeddings, k + 1)  # +1 because first result is self
            
            # Filter by threshold and remove self
            similar_items = []
            for i in range(len(indices)):
                neighbors = []
                for j in range(1, len(indices[i])):  # Skip first (self)
                    idx = int(indices[i][j])
                    dist = float(distances[i][j])
                    if dist >= threshold:
                        neighbors.append(idx)
                similar_items.append(neighbors)
            
            return similar_items
        except Exception as e:
            self.logger.error(f"Failed to find similar items: {e}")
            return []
    
    def block_entities(self, records: List[Dict], key_attributes: List[str]) -> List[Set[int]]:
        """Block (cluster) entity records.
        
        Args:
            records: List of extracted records
            key_attributes: Attribute names to use as entity keys for blocking
            
        Returns:
            List of sets, where each set contains indices of records in the same block
        """
        if not records or not key_attributes:
            self.logger.warning("No records or key attributes")
            return []
        
        if self.model is None:
            self.logger.warning("Model not initialized, returning singleton blocks")
            return [{i} for i in range(len(records))]
        
        # Extract key values
        key_values = []
        for record in records:
            # Concatenate key attributes
            values = []
            for attr in key_attributes:
                val = record.get(attr)
                if val is not None:
                    values.append(str(val))
            key_values.append(" ".join(values) if values else "")
        
        # Remove empty values
        if not any(key_values):
            self.logger.warning("All key values are empty")
            return [{i} for i in range(len(records))]
        
        # Encode
        self.logger.info(f"Encoding {len(key_values)} entity mentions")
        embeddings = self.encode_texts(key_values)
        
        if embeddings.size == 0:
            return [{i} for i in range(len(records))]
        
        # Build index
        self.index = self.build_index(embeddings)
        if self.index is None:
            return [{i} for i in range(len(records))]
        
        # Find similar items
        self.logger.info(f"Finding neighbors (k={TOP_K_NEIGHBORS}, threshold={SIMILARITY_THRESHOLD})")
        similar_items = self.find_similar_items(embeddings, k=TOP_K_NEIGHBORS, threshold=SIMILARITY_THRESHOLD)
        
        # Cluster using Union-Find
        self.logger.info("Clustering with Union-Find")
        uf = UnionFind(len(records))
        
        for i, neighbors in enumerate(similar_items):
            for j in neighbors:
                uf.union(i, j)
        
        # Convert to list of sets
        clusters = uf.get_clusters()
        blocks = list(clusters.values())
        
        self.logger.info(f"Blocked {len(records)} records into {len(blocks)} blocks")
        
        return blocks


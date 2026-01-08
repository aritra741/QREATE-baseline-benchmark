"""
Blocking Module - Semantic Blocking for Entity Resolution

Clusters potentially identical entity mentions using:
- Sentence embeddings for vectorization
- FAISS for efficient nearest neighbor search
- Union-Find for clustering similar entities
"""

import logging
from typing import List, Dict, Set, Tuple, TYPE_CHECKING
from collections import defaultdict

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    import faiss
except ImportError:
    np = None
    SentenceTransformer = None
    faiss = None

if TYPE_CHECKING:
    import numpy as np

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
    """Performs semantic blocking on entity mentions with integrated HNSW-Union-Find."""
    
    def __init__(self, embedding_model: str = EMBEDDING_MODEL, logger: logging.Logger = None, blocking_threshold: float = SIMILARITY_THRESHOLD):
        """Initialize blocker.
        
        Args:
            embedding_model: Sentence transformer model name
            logger: Logger instance
            blocking_threshold: Similarity threshold for linking mentions (0-1)
        """
        self.logger = logger or logging.getLogger(__name__)
        self.embedding_model_name = embedding_model
        self.model = None
        self.index = None
        self.blocking_threshold = blocking_threshold
        self.similarity_threshold = blocking_threshold  # Alias for compatibility
        
        # HNSW-Union-Find integration state
        self.mention_texts = []  # List of mention strings
        self.embeddings = []  # List of embeddings
        self.mention_to_idx = {}  # Map: mention_text -> index in lists
        self.union_find = None  # Union-Find structure for connected components
        self.next_idx = 0  # Counter for mention indices
        
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
    
    def add_and_link(self, mention_text: str) -> int:
        """Add a mention to the index and link it to similar existing mentions.
        
        Implements the "Search-before-Add" algorithm:
        1. Encode the mention text
        2. Search index for K=1 nearest neighbor
        3. If similarity >= blocking_threshold, union with neighbor
        4. Add embedding to FAISS index
        
        Args:
            mention_text: Text of the mention to add
            
        Returns:
            Index of the added mention
        """
        if not mention_text or not isinstance(mention_text, str):
            self.logger.warning(f"Invalid mention text: {mention_text}")
            return -1
        
        mention_text = mention_text.strip()
        
        # Check if already added
        if mention_text in self.mention_to_idx:
            self.logger.debug(f"Mention already indexed: '{mention_text}'")
            return self.mention_to_idx[mention_text]
        
        # Initialize Union-Find if needed
        if self.union_find is None:
            self.union_find = UnionFind(10000)  # Start with capacity for 10k mentions
        
        # Encode the mention
        embedding = self.encode_texts([mention_text])
        if len(embedding) == 0:
            self.logger.warning(f"Failed to encode mention: '{mention_text}'")
            return -1
        
        embedding = embedding[0]
        current_idx = self.next_idx
        
        # Search for nearest neighbor BEFORE adding
        if self.index is not None and self.next_idx > 0:
            try:
                # Prepare query embedding
                query_embedding = embedding.astype(np.float32).reshape(1, -1)
                faiss.normalize_L2(query_embedding)
                
                # Search for K=1 nearest neighbor
                distances, indices = self.index.search(query_embedding, k=1)
                
                if len(indices) > 0 and len(indices[0]) > 0:
                    neighbor_idx = int(indices[0][0])
                    neighbor_similarity = float(distances[0][0])
                    
                    self.logger.debug(f"Mention '{mention_text}': NN similarity={neighbor_similarity:.3f}")
                    
                    # Link if similarity is above threshold
                    if neighbor_similarity >= self.blocking_threshold:
                        self.logger.info(f"Linking '{mention_text}' with neighbor (idx={neighbor_idx}, sim={neighbor_similarity:.3f})")
                        self.union_find.union(current_idx, neighbor_idx)
                    
            except Exception as e:
                self.logger.warning(f"Failed to search index: {e}")
        
        # Add to FAISS index (regardless of union result)
        try:
            if self.index is None:
                # Create new index
                embedding_normalized = embedding.astype(np.float32).reshape(1, -1)
                faiss.normalize_L2(embedding_normalized)
                dimension = embedding_normalized.shape[1]
                self.index = faiss.IndexFlatIP(dimension)
                self.index.add(embedding_normalized)
            else:
                # Add to existing index
                embedding_normalized = embedding.astype(np.float32).reshape(1, -1)
                faiss.normalize_L2(embedding_normalized)
                self.index.add(embedding_normalized)
        except Exception as e:
            self.logger.error(f"Failed to add to FAISS index: {e}")
            return -1
        
        # Store mention and embedding
        self.mention_texts.append(mention_text)
        self.embeddings.append(embedding)
        self.mention_to_idx[mention_text] = current_idx
        self.next_idx += 1
        
        self.logger.debug(f"Added mention #{current_idx}: '{mention_text}'")
        return current_idx
    
    def get_blocks(self) -> Dict[str, List[str]]:
        """Get all blocks (connected components) from Union-Find structure.
        
        Returns a dictionary mapping representative mention to list of mentions in block.
        
        Returns:
            Dictionary mapping block representative to list of mentions
        """
        if self.union_find is None or self.next_idx == 0:
            self.logger.warning("No mentions indexed yet")
            return {}
        
        # Get clusters from Union-Find
        clusters = self.union_find.get_clusters()
        
        # Convert index clusters to mention clusters
        mention_blocks = {}
        for root_idx, member_indices in clusters.items():
            if root_idx < len(self.mention_texts):
                representative = self.mention_texts[root_idx]
                mentions_in_block = [self.mention_texts[idx] for idx in member_indices if idx < len(self.mention_texts)]
                mention_blocks[representative] = mentions_in_block
        
        self.logger.info(f"Got {len(mention_blocks)} blocks from {self.next_idx} mentions")
        return mention_blocks
    
    def encode_texts(self, texts: List[str]) -> "np.ndarray":
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
    
    def build_index(self, embeddings: "np.ndarray") -> "faiss.Index":
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
    
    def find_similar_items(self, embeddings: "np.ndarray", k: int = TOP_K_NEIGHBORS,
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


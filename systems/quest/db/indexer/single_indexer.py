from typing import List
from quest.db.indexer.preprocessor.preprocessor import DocPreprocessor
import json
import os
import numpy as np
try:
    from quest.db.indexer.storage.hnsw_text_index_storage import HNSWTextIndexStorage
except ImportError:
    HNSWTextIndexStorage = None
from quest.db.indexer.storage.text_index_storage import VectorDBTextIndexStorage
from quest.db.querier.querier import OpenGaussQuerier
from quest.core.datapack.doc import Doc
from quest.core.chunker.chunker import RecursiveCharacterTextChunker, GrammarSemanticChunker, SentenceTransformerTokenTextChunker
from quest.core.embedding.e5Embedding import batchedE5Embeddings
from quest.conf import settings
from numpy.typing import NDArray

class SingleIndexer:
    """
    Indexer for a single table; handles indexing for one collection.
    """

    def __init__(self, table_name: str, type: str, chunker = None, **kwargs):
        """
        Initialize a SingleIndexer instance.

        Args:
            table_name: Table name used for index file path / DB table.
            type: Index type indicating document type such as "TextDoc", "PdfDoc".
            **kwargs: Additional parameters.
        """
        self.table_name = table_name
        self.type = type
        self.docs_meta = {}
        self.preprocessor = None
        self.querier = None

        def get_file_name_by_id(self, doc_id: int) -> str:
            pass

        def get_docs_id(self) -> list[int]:
            pass

        def get_relative_chunks_text(self, doc_id: int, query: str, topk: int) -> List[str]:
            pass


class TextDocIndexer(SingleIndexer):
    def __init__(self, table_name: str, type: str = "TextDoc", chunker = None, embedding_model = None, **kwargs):
        super().__init__(table_name, type, **kwargs)
        
        self.use_hnsw = HNSWTextIndexStorage is not None
        self.embedding_model = embedding_model
        
        # Base directory for HNSW storage
        base_dir = os.path.join(settings.INDEX_ROOT_DIR, "hnsw", table_name.lower())
        self.docs_meta_path = os.path.join(base_dir, "docs_meta.json")
        self.doc_embeddings_path = os.path.join(base_dir, "doc_embeddings.npz")
        self.doc_content_path = os.path.join(base_dir, "doc_content.json")
        self.index_meta_path = os.path.join(base_dir, "index_meta.json")
        
        # Determine embedding size: from model if available, else try to load from saved metadata
        if embedding_model is not None:
            self.embedding_size = embedding_model.emb_size
        elif self.use_hnsw and os.path.exists(self.index_meta_path):
            # Load embedding size from saved index metadata
            with open(self.index_meta_path, "r") as f:
                meta = json.load(f)
                self.embedding_size = meta.get("embedding_size", 384)  # default to MiniLM size
        else:
            self.embedding_size = 384  # default fallback

        # Choose storage: prefer HNSW if available, else fall back to PG/pgvector
        if self.use_hnsw:
            self.storage = HNSWTextIndexStorage(table_name, embedding_size=self.embedding_size)
            self.querier = None  # no DB when using HNSW
        else:
            self.storage = VectorDBTextIndexStorage(table_name, embedding_size=self.embedding_size)
            self.querier = OpenGaussQuerier(embedding_size=self.embedding_size)
        
        self.preprocessor = DocPreprocessor(chunker=chunker, embedding_model=embedding_model) if embedding_model else None
        
        # Cache query embeddings to avoid recomputation
        self.query_embedding_cache = {}

    def get_chunks_by_docid(self, doc_id) -> list[str]:
        return self.storage.get_chunks_by_docid(doc_id)

    def get_file_name_by_id(self, doc_id: int) -> str:
        """
        Get the file name associated with a document ID.

        Args:
            doc_id: Document ID.

        Returns:
            str: File name, or empty string if not present.
        """
        if doc_id in self.docs_meta:
            return self.docs_meta[doc_id].get("file_name", "")
        return ""


    def get_docs_id(self) -> list[int]:
        """
        Get all document IDs stored for this table.

        Returns:
            list[int]: Document ID list.
        """
        doc_ids = list(self.docs_meta.keys())
        if not doc_ids:
            print(f"[WARNING] get_docs_id returned EMPTY for table '{self.table_name}'!")
            print(f"[WARNING] docs_meta keys: {list(self.docs_meta.keys())}")
            print(f"[WARNING] docs_meta size: {len(self.docs_meta)}")
            if hasattr(self, 'docs_meta_path'):
                print(f"[WARNING] docs_meta_path: {self.docs_meta_path}")
                print(f"[WARNING] docs_meta_path exists: {os.path.exists(self.docs_meta_path)}")
        return doc_ids

    def build_indexer(self, docs: List[Doc]) -> None:
        """
        Build indexes for provided documents.

        Args:
            docs: List of documents.
        """
        # 1. Use preprocessor to produce chunks, embeddings, and metadata
        doc2chunks, doc2embeddings, docs_meta, doc_2_whole_doc_embedding = self.preprocessor.preprocess_documents(docs)

        # 2. Store document metadata and embeddings (can later be used for clustering)
        self.docs_meta = docs_meta
        self.doc_2_whole_doc_embedding = doc_2_whole_doc_embedding

        # 3. Build document content map (for full-text search)
        doc_2_content = {}
        for doc in docs:
            doc_id = doc.doc_id
            if hasattr(doc, 'content') and doc.content:
                doc_2_content[doc_id] = doc.content       

        # 3. Build vector index via storage
        self.storage.build_index(doc2chunks, doc2embeddings)

        # 4. Persist metadata
        if self.use_hnsw:
            os.makedirs(os.path.dirname(self.docs_meta_path), exist_ok=True)
            with open(self.docs_meta_path, "w", encoding="utf-8") as f:
                json.dump(self.docs_meta, f, ensure_ascii=False)
            # save doc-level embeddings
            np.savez(self.doc_embeddings_path, **{str(k): v for k, v in self.doc_2_whole_doc_embedding.items()})
            with open(self.doc_content_path, "w", encoding="utf-8") as f:
                json.dump(doc_2_content, f, ensure_ascii=False)
            # save index metadata (embedding size, table name, etc.)
            with open(self.index_meta_path, "w", encoding="utf-8") as f:
                json.dump({
                    "table_name": self.table_name,
                    "embedding_size": self.embedding_size,
                    "doc_count": len(docs_meta)
                }, f)
        else:
            # Use querier to build cache tables and persist metadata to DB
            # jztodo: store a separate doc-level embedding field in the cache table.
            self.querier.build_cache_table(self.table_name, docs_meta, doc_2_whole_doc_embedding, doc_2_content)

    def _get_cached_query_embedding(self, query: str):
        """
        Retrieve query embedding from cache; compute and cache if missing.
        
        Args:
            query: Query string.
            
        Returns:
            Embedding vector for the query.
        """
        cache_key = query[:256]  # Use first 256 characters as cache key
        
        if cache_key not in self.query_embedding_cache:
            # 计算embedding并缓存
            self.query_embedding_cache[cache_key] = self.preprocessor.embedding_model.embed_query(query)
        
        return self.query_embedding_cache[cache_key]

    def get_relative_chunks_text_with_id_and_embedding(self, doc_id: int, query: str, topk: int) -> List[tuple[str, int, NDArray]]:
        """
        Query the most relevant text chunks in a document, returning text, chunk id, and embedding.

        Args:
            doc_id: Document ID.
            query: Query string.
            topk: Number of chunks to return.

        Returns:
            List of tuples (chunk_text, chunk_id, chunk_embedding).
            Chunk IDs are unique within a document.
        """
        # 1. Convert query to embedding (cached)
        query_embedding = self._get_cached_query_embedding(query)

        # 2. Query storage for similar text chunks
        results = self.storage.query_chunk_with_id_and_embedding(
            doc_id=doc_id,
            topk=topk,
            query_embedding=query_embedding
        )

        # 3. Extract chunk content and return
        chunk_texts_with_id_and_embedding = [(result[0], result[3], result[4]) for result in results]  # result format: (chunk_text, similarity_score, doc_id, chunk_id, chunk_embedding)
        return chunk_texts_with_id_and_embedding  # (chunk_text, chunk_id, chunk_embedding)


    def full_text_search_related_docs(self, queries: List[str], threshold: float = 0.1) -> List[List[int]]:
        """
        Full-text search for related documents.

        Args:
            queries: List of query strings.
            threshold: Similarity threshold.

        Returns:
            For each query, a list of matching document IDs.
        """
        if hasattr(self, 'querier') and self.querier:
            return self.querier.full_text_search_related_doc_ids(
                self.table_name, 
                queries, 
                threshold
            )
        else:
            return [[] for _ in queries]



    def get_relative_chunks_text_with_id(self, doc_id: int, query: str, topk: int) -> List[tuple[str, int]]:
        """
        Query the most relevant text chunks in a document, returning text and chunk id.

        Args:
            doc_id: Document ID.
            query: Query string.
            topk: Number of chunks to return.

        Returns:
            List of tuples (chunk_text, chunk_id); IDs are unique per document.
        """
        # 1. Convert query to embedding (cached)
        query_embedding = self._get_cached_query_embedding(query)

        # 2. Query storage for similar text chunks
        results = self.storage.query_chunk_with_id(
            doc_id=doc_id,
            topk=topk,
            query_embedding=query_embedding
        )

        # 3. Extract chunk content and return
        chunk_texts_with_id = [(result[0], result[3]) for result in results]  # result format: (chunk_text, similarity_score, doc_id, chunk_id)
        return chunk_texts_with_id  # (chunk_text, chunk_id)


    def get_relative_chunks_text(self, doc_id: int, query: str, topk: int) -> List[str]:
        """
        Query the most relevant text chunks in a document, returning only chunk text.

        Args:
            doc_id: Document ID.
            query: Query string.
            topk: Number of chunks to return.

        Returns:
            List of chunk texts.
        """
        # 1. Convert query to embedding (cached)
        query_embedding = self._get_cached_query_embedding(query)

        # 2. Query storage for similar text chunks
        results = self.storage.query(
            doc_id=doc_id,
            topk=topk,
            query_embedding=query_embedding
        )

        # 3. Extract chunk content and return
        chunk_texts = [result[0] for result in results]  # result format: (chunk_text, similarity_score, doc_id)
        return chunk_texts
    
    def get_relative_chunks_lenght(self, doc_id_list: List[int], query: str, topk: int) -> int:
        """
        Calculate total token length of top-k relevant chunks for given documents.

        Args:
            doc_id_list: List of document IDs.
            query: Query string.
            topk: Number of chunks to consider.

        Returns:
            Sum of token counts across retrieved chunks.
        """
        # 1. Convert query to embedding (cached)
        query_embedding = self._get_cached_query_embedding(query)

        # 2. Query storage for similar text chunks

        res = 0
        for id in doc_id_list:
            results = self.storage.query(
                doc_id=id,
                topk=topk,
                query_embedding=query_embedding
            )

            # 3. Sum token counts for returned chunks
            for result in results:
                res += len(settings.enc.encode(result[0]))
            
        return res

    def save_indexer(self) -> None:
        """
        Save index to disk.
        """
        self.storage.save_index()

    def get_doc_embedding(self, doc_id)  -> NDArray :
        return self.doc_2_whole_doc_embedding[doc_id]

    def load_indexer(self) -> None:
        """
        Load index from disk.
        """
        # 1. Load document metadata from database
        if self.use_hnsw:
            # load from local files
            print(f"[DEBUG load_indexer] Loading HNSW index for table: {self.table_name}")
            print(f"[DEBUG load_indexer] docs_meta_path: {self.docs_meta_path}")
            
            if not os.path.exists(self.docs_meta_path):
                print(f"[ERROR] docs_meta.json NOT FOUND at: {self.docs_meta_path}")
                print(f"[ERROR] Please check if INDEX_ROOT_DIR is correctly set!")
                raise FileNotFoundError(f"docs_meta.json not found for table '{self.table_name}' at {self.docs_meta_path}")
            
            with open(self.docs_meta_path, "r", encoding="utf-8") as f:
                self.docs_meta = json.load(f)
            
            print(f"[DEBUG load_indexer] Loaded docs_meta with {len(self.docs_meta)} documents")
            
            # load embeddings
            if os.path.exists(self.doc_embeddings_path):
                emb_data = np.load(self.doc_embeddings_path)
                self.doc_2_whole_doc_embedding = {int(k): emb_data[k] for k in emb_data}
            else:
                print(f"[WARNING] doc_embeddings not found at {self.doc_embeddings_path}")
                self.doc_2_whole_doc_embedding = {}
        else:
            self.docs_meta = self.querier.load_docs_meta(self.table_name)
            self.doc_2_whole_doc_embedding = self.querier.load_docs_embedding(self.table_name)

        # 2. Load vector index
        load_flag = False
        load_flag = self.storage.load_index()
        if load_flag:
            print(f"Successfully loaded index: {self.table_name}")
        else:
            print(f"Index not found: {self.table_name}")
            raise ValueError(f"Index not found: {self.table_name}")


class HierarchicalTextDocIndexer(SingleIndexer):
    def __init__():
        pass



def bottom():
    pass


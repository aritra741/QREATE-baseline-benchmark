"""
HNSW-based text index storage (no database required).

Stores embeddings in an on-disk hnswlib index plus lightweight metadata files.
All artifacts are written under settings.INDEX_ROOT_DIR.
"""
from __future__ import annotations

import json
import os
from typing import List, Tuple, Optional

import numpy as np

from quest.conf import settings
from .index_storage import IndexStorage


class HNSWTextIndexStorage(IndexStorage):
    def __init__(self, table_name: str, embedding_size: int, index_root: Optional[str] = None):
        super().__init__()
        self.table_name = table_name.lower()
        self.embedding_size = embedding_size
        self.index_root = index_root or settings.INDEX_ROOT_DIR
        self.base_dir = os.path.join(self.index_root, "hnsw", self.table_name)
        self.index_path = os.path.join(self.base_dir, "index.bin")
        self.meta_path = os.path.join(self.base_dir, "meta.json")
        self.embeddings_path = os.path.join(self.base_dir, "embeddings.npy")
        self.doc_ids_path = os.path.join(self.base_dir, "doc_ids.npy")
        self.chunk_orders_path = os.path.join(self.base_dir, "chunk_orders.npy")
        self._index = None
        self._chunk_texts: List[str] = []
        self._embeddings: Optional[np.ndarray] = None
        self._doc_ids: Optional[np.ndarray] = None
        self._chunk_orders: Optional[np.ndarray] = None

        try:
            import hnswlib  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "hnswlib is required for HNSWTextIndexStorage. Install with `pip install hnswlib`."
            ) from e

    # ------------------------------------------------------------------ build
    def build_index(
        self,
        doc2chunks: dict[int, list[str]],
        doc2embeddings: dict[int, list[np.ndarray]],
    ) -> None:
        import hnswlib

        os.makedirs(self.base_dir, exist_ok=True)

        embeddings: List[np.ndarray] = []
        doc_ids: List[int] = []
        chunk_orders: List[int] = []
        chunk_texts: List[str] = []

        # Flatten docs -> rows
        for doc_id, chunks in doc2chunks.items():
            embs = doc2embeddings[doc_id]
            for idx, (chunk_text, emb) in enumerate(zip(chunks, embs), start=1):
                embeddings.append(np.asarray(emb, dtype=np.float32))
                doc_ids.append(int(doc_id))
                chunk_orders.append(int(idx))
                chunk_texts.append(chunk_text)

        if not embeddings:
            raise ValueError("No embeddings provided to build HNSW index.")

        data = np.vstack(embeddings).astype(np.float32)
        labels = np.arange(len(data))

        index = hnswlib.Index(space="cosine", dim=self.embedding_size)
        # ef_construction/ M are kept small for build speed; can be tuned later
        index.init_index(max_elements=len(data), ef_construction=200, M=16)
        index.add_items(data, labels)
        index.set_ef(64)
        index.save_index(self.index_path)

        # Persist side data
        np.save(self.embeddings_path, data)
        np.save(self.doc_ids_path, np.asarray(doc_ids, dtype=np.int32))
        np.save(self.chunk_orders_path, np.asarray(chunk_orders, dtype=np.int32))
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump({"chunk_texts": chunk_texts}, f, ensure_ascii=False)

        # Keep in-memory for immediate use
        self._index = index
        self._chunk_texts = chunk_texts
        self._embeddings = data
        self._doc_ids = np.asarray(doc_ids, dtype=np.int32)
        self._chunk_orders = np.asarray(chunk_orders, dtype=np.int32)

    # ------------------------------------------------------------------ query helpers
    def _ensure_loaded(self):
        if self._index is not None:
            return
        import hnswlib

        if not (os.path.exists(self.index_path) and os.path.exists(self.meta_path)):
            raise FileNotFoundError(f"HNSW index for {self.table_name} not found at {self.base_dir}")

        with open(self.meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        self._chunk_texts = meta["chunk_texts"]
        self._embeddings = np.load(self.embeddings_path)
        self._doc_ids = np.load(self.doc_ids_path)
        self._chunk_orders = np.load(self.chunk_orders_path)

        index = hnswlib.Index(space="cosine", dim=self.embedding_size)
        index.load_index(self.index_path)
        index.set_ef(64)
        self._index = index

    def _search(self, query_embedding: np.ndarray, topk: int, doc_id: Optional[int], need_emb: bool):
        self._ensure_loaded()
        q = np.asarray(query_embedding, dtype=np.float32).reshape(1, -1)
        labels, distances = self._index.knn_query(q, k=min(topk * 5, len(self._chunk_texts)))
        labels = labels[0]
        distances = distances[0]
        results = []
        for lbl, dist in zip(labels, distances):
            i = int(lbl)
            if doc_id is not None and int(self._doc_ids[i]) != int(doc_id):
                continue
            sim = 1.0 - dist  # cosine -> similarity
            item = (
                self._chunk_texts[i],
                float(sim),
                int(self._doc_ids[i]),
                int(self._chunk_orders[i]),
            )
            if need_emb:
                item = item + (self._embeddings[i],)
            results.append(item)
            if len(results) >= topk:
                break
        return results

    # ------------------------------------------------------------------ public API
    def query(
        self,
        doc_id: Optional[int],
        topk: int,
        query_embedding: np.ndarray,
    ) -> List[Tuple[str, float, int]]:
        if query_embedding is None:
            raise ValueError("query_embedding is required")
        return self._search(query_embedding, topk, doc_id, need_emb=False)

    def query_chunk_with_id(
        self,
        doc_id: Optional[int],
        topk: int,
        query_embedding: np.ndarray,
    ) -> List[Tuple[str, float, int, int]]:
        if query_embedding is None:
            raise ValueError("query_embedding is required")
        return self._search(query_embedding, topk, doc_id, need_emb=False)

    def query_chunk_with_id_and_embedding(
        self,
        doc_id: Optional[int],
        topk: int,
        query_embedding: np.ndarray,
    ) -> List[Tuple[str, float, int, int, np.ndarray]]:
        if query_embedding is None:
            raise ValueError("query_embedding is required")
        return self._search(query_embedding, topk, doc_id, need_emb=True)

    def get_chunks_by_docid(self, doc_id: int) -> list[str]:
        self._ensure_loaded()
        mask = self._doc_ids == int(doc_id)
        idxs = np.where(mask)[0]
        ordered = sorted(idxs, key=lambda i: self._chunk_orders[i])
        return [self._chunk_texts[i] for i in ordered]

    # ------------------------------------------------------------------ persistence
    def save_index(self) -> None:
        # Already persisted during build_index; nothing extra to do.
        return

    def load_index(self) -> bool:
        try:
            self._ensure_loaded()
            return True
        except FileNotFoundError:
            return False



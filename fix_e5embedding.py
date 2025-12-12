#!/usr/bin/env python3
"""
Rewrite systems/quest/core/embedding/e5Embedding.py with clean content.
Run from repo root on CHPC.
"""
import pathlib

TARGET = pathlib.Path("systems/quest/core/embedding/e5Embedding.py")

CLEAN_CONTENT = '''from typing import List, Union
import numpy as np
from numpy.typing import NDArray
from langchain_core.embeddings import Embeddings
from transformers import AutoModel, AutoTokenizer
import torch
from tqdm import tqdm
import os

# Use HuggingFace model IDs - they will be auto-downloaded and cached
E5_EMBEDDING_PATH = os.environ.get("E5_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2")
BGE_EMBEDDING_PATH = os.environ.get("BGE_MODEL_PATH", "BAAI/bge-small-en-v1.5")

class batchedBGEEmbeddings(Embeddings):
    def __init__(self, model_path: str = BGE_EMBEDDING_PATH, device: str = "cuda", batch_size: int = 1):
        """Initialize local BGE embedding model."""
        self.batch_size = batch_size
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModel.from_pretrained(model_path).to(device)
        self.emb_size = self.model.config.hidden_size
        self.device = device

    def embed_documents(self, texts: List[str]) -> List[NDArray]:
        """Batch embed documents."""
        return self._embed(texts)
    
    def embed_query(self, text: str) -> NDArray:
        """Embed single query."""
        return self._embed([text])[0]
    
    def __call__(self, text: Union[str, List[str]]):
        if isinstance(text, str):
            return self.embed_query(text)
        return self.embed_documents(text)

    def _embed(self, sentences: List[str]) -> NDArray:
        """Optimized batch embedding logic."""
        batch_size = self.batch_size
        all_embeddings = []
        for i in tqdm(range(0, len(sentences), batch_size), desc="BGE Embedding", unit="batch"):
            batch = sentences[i:i + batch_size]
            inputs = self.tokenizer(
                batch, 
                return_tensors='pt', 
                truncation=True, 
                padding='longest',
                max_length=8192
            ).to(self.device)
            with torch.no_grad():
                outputs = self.model(**inputs)
            cls_embeddings = outputs.last_hidden_state[:, 0, :]
            all_embeddings.append(cls_embeddings.cpu().numpy())
        return np.concatenate(all_embeddings, axis=0)

class batchedE5Embeddings(Embeddings):
    def __init__(self, model_path: str = E5_EMBEDDING_PATH, device: str = "cuda", batch_size: int = 32):
        """Initialize local E5 embedding model."""
        self.batch_size = batch_size
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModel.from_pretrained(model_path).to(device)
        self.emb_size = self.model.config.hidden_size
        self.device = device

    def embed_documents(self, texts: List[str]) -> List[NDArray]:
        """Batch embed documents."""
        return self._embed(texts)
    
    def embed_query(self, text: str) -> NDArray:
        """Embed single query."""
        return self._embed([text])[0]
    
    def __call__(self, text: Union[str, List[str]]):
        if isinstance(text, str):
            return self.embed_query(text)
        return self.embed_documents(text)

    def _embed(self, sentences: List[str]) -> NDArray:
        """Optimized batch embedding logic."""
        batch_size = self.batch_size
        all_embeddings = []
        for i in tqdm(range(0, len(sentences), batch_size), desc="E5 Embedding", unit="batch"):
            batch = sentences[i:i + batch_size]
            inputs = self.tokenizer(
                batch, 
                return_tensors='pt', 
                truncation=True, 
                padding='longest',
                max_length=512
            ).to(self.device)
            with torch.no_grad():
                outputs = self.model(**inputs)
            cls_embeddings = outputs.last_hidden_state[:, 0, :]
            all_embeddings.append(cls_embeddings.cpu().numpy())
        return np.concatenate(all_embeddings, axis=0)

class E5Embeddings(Embeddings):
    def __init__(self, model_path: str = E5_EMBEDDING_PATH, device: str = "cuda"):
        """Initialize local E5 embedding model."""
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModel.from_pretrained(model_path).to(device)
        self.emb_size = self.model.config.hidden_size
        self.device = device

    def embed_documents(self, texts: List[str]) -> List[NDArray]:
        """Batch embed documents."""
        return self._embed(texts)
    
    def embed_query(self, text: str) -> NDArray:
        """Embed single query."""
        return self._embed([text])[0]
    
    def __call__(self, text: Union[str, List[str]]):
        if isinstance(text, str):
            return self.embed_query(text)
        return self.embed_documents(text)

    def _embed(self, sentences: List[str]) -> List[NDArray]:
        """Actual embedding logic."""
        embeddings = []
        for x in sentences:
            inputs = self.tokenizer(x, return_tensors='pt', truncation=True, padding=True, max_length=512)
            inputs = {k: v.to('cuda') for k, v in inputs.items()}
            with torch.no_grad():
                outputs = self.model(**inputs)
            embedding = outputs.last_hidden_state[:, 0, :].squeeze().cpu().numpy()
            embeddings.append(embedding)
        return np.array(embeddings)
'''

if __name__ == "__main__":
    backup = TARGET.with_suffix(".py.bak2")
    if TARGET.exists():
        TARGET.rename(backup)
        print(f"Backed up to {backup}")
    TARGET.write_text(CLEAN_CONTENT, encoding="utf-8")
    print(f"Wrote clean {TARGET}")



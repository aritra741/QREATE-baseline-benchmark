#!/usr/bin/env python3
"""
Rewrite systems/quest/db/indexer/indexer.py with clean content.
Run from repo root on CHPC.
"""
import pathlib

TARGET = pathlib.Path("systems/quest/db/indexer/indexer.py")

CLEAN_CONTENT = '''import json
import os
from typing import Tuple, Dict
from quest.core.datapack.doc import Doc, TextDoc, ZenDBDoc
from quest.db.indexer.single_indexer import SingleIndexer, TextDocIndexer
from quest.db.indexer.zendb_indexer import ZenDBDocIndexer
from quest.conf.settings import RELATIVE_PROJECT_ROOT_PATH
from quest.db.indexer.preprocessor.load_documents import load_TextDocs_from_directory, load_ZenDBDoc_from_directory

from quest.core.embedding.e5Embedding import batchedE5Embeddings
import torch
_device = "cuda" if torch.cuda.is_available() else "cpu"
USED_EMBEDDING_MODEL = batchedE5Embeddings(model_path="sentence-transformers/all-MiniLM-L6-v2",
                                           device=_device, batch_size=32)

from quest.core.chunker.chunker import GrammarSemanticChunker, SentenceTransformerTokenTextChunker, RecursiveTokenTextChunker, TokenTextChunker
TOKEN_CHUNKER = TokenTextChunker(chunk_size=20000, chunk_overlap=128)
RECURSIVE_TOKEN_CHUNKER = RecursiveTokenTextChunker(chunk_size=512, chunk_overlap=128)
GRAMMAR_SEMANTIC_CHUNKER = GrammarSemanticChunker(USED_EMBEDDING_MODEL, min_chunk_size=128, max_chunk_size=512)
USED_CHUNKER = TOKEN_CHUNKER

class GlobalIndexer:
    """Global indexer for managing all table indexes."""

    def __init__(self, config_save_path: str = os.path.join(RELATIVE_PROJECT_ROOT_PATH, "data/global_index/global_index.json"), chunker = None, embedding_model = None):
        """Initialize GlobalIndexer instance."""
        self.config_path = config_save_path
        self.embedding_model = embedding_model
        self.chunker = chunker
        self.table_to_type: Dict[str, str] = {}
        self.table_to_indexer: Dict[str, SingleIndexer] = {}
        self.indexer_classes = {
            "TextDoc": TextDocIndexer,
            "ZenDBDoc": ZenDBDocIndexer,
        }

    def get_indexer(self, table_name: str) -> Tuple[SingleIndexer, str]:
        """Get indexer for specified table."""
        table_name = table_name.lower()
        if table_name not in self.table_to_indexer:
            raise KeyError(f"Indexer for table '{table_name}' does not exist")
        indexer = self.table_to_indexer[table_name]
        indexer_type = self.table_to_type[table_name]
        return indexer, indexer_type

    def build_indexer(self, tables_name: list[str], types: list[str], table2docs: dict[str, list[Doc]]):
        """Build global index."""
        chunker = self.chunker
        embedding_model = self.embedding_model
        if len(tables_name) != len(types):
            raise ValueError("tables_name and types must have same length")
        self.table_to_type.clear()
        self.table_to_indexer.clear()
        for table_name, indexer_type in zip(tables_name, types):
            if indexer_type not in self.indexer_classes:
                raise ValueError(f"Unsupported indexer type: {indexer_type}")
            self.table_to_type[table_name] = indexer_type
            indexer_class = self.indexer_classes[indexer_type]
            indexer = indexer_class(table_name=table_name, type=indexer_type, chunker = chunker, embedding_model = embedding_model)
            self.table_to_indexer[table_name] = indexer
            if table_name in table2docs:
                docs = table2docs[table_name]
                if docs:
                    indexer.build_indexer(docs)
        self.save_indexer()

    def get_global_doc_id2file_name(self) -> Dict[int, str]:
        """Return global doc_id to file_name mapping."""
        global_doc_id2file_name = {}
        for table_name, indexer in self.table_to_indexer.items():
            doc_ids = indexer.get_docs_id()
            for doc_id in doc_ids:
                file_name = indexer.get_file_name_by_id(doc_id)
                global_doc_id2file_name[doc_id] = file_name
        return global_doc_id2file_name

    def save_indexer(self):
        """Save indexer config to disk."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.table_to_type, f, ensure_ascii=False, indent=2)
        for table_name, indexer in self.table_to_indexer.items():
            indexer.save_indexer()

    def load_indexer(self, table_to_type = None):
        """Load indexer config from disk."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file '{self.config_path}' does not exist")
        if table_to_type is None:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.table_to_type = json.load(f)
        else:
            self.table_to_type = table_to_type
            self.table_to_type = {k.lower(): v for k, v in self.table_to_type.items()}
        self.table_to_indexer.clear()
        for table_name, indexer_type in self.table_to_type.items():
            if indexer_type not in self.indexer_classes:
                raise ValueError(f"Unsupported indexer type: {indexer_type}")
            indexer_class = self.indexer_classes[indexer_type]
            indexer = indexer_class(table_name=table_name, type=indexer_type, chunker = self.chunker, embedding_model = self.embedding_model)
            self.table_to_indexer[table_name] = indexer
            indexer.load_indexer()


def load_all_indexer(table_to_type = None, chunker = USED_CHUNKER, embedding_model=USED_EMBEDDING_MODEL) -> GlobalIndexer:
    """Load all indexers."""
    global_indexer = GlobalIndexer(chunker=chunker, embedding_model=embedding_model)
    global_indexer.load_indexer(table_to_type)
    return global_indexer

def build_all_indexer(doc_dirs : list[str], tables_name: list[str], types = ["TextDoc", "TextDoc"], debug_flag = False, chunker = USED_CHUNKER ,embedding_model = USED_EMBEDDING_MODEL) -> GlobalIndexer:
    """Build all indexers."""
    table2docs = {}
    if len(doc_dirs) != len(tables_name):
        raise ValueError("doc_dirs and table_names must have same length")
    global_indexer = GlobalIndexer(chunker=chunker, embedding_model=embedding_model)
    new_tables_name = []
    for  table_name in tables_name:
        new_tables_name.append(table_name.lower())
    tables_name = new_tables_name
    doc_id = 1
    for doc_dir, table_name, type in zip(doc_dirs, tables_name, types):
        if type == "TextDoc":
            load_docs_func = load_TextDocs_from_directory
        elif type == "ZenDBDoc":
            load_docs_func = load_ZenDBDoc_from_directory
        docs, next_doc_id = load_docs_func(doc_dir, table_name, start_doc_id=doc_id, debug_flag=debug_flag)
        if debug_flag:
            docs = docs[0:5]
        table2docs[table_name] = docs
        doc_id = next_doc_id
    global_indexer.build_indexer(tables_name, types, table2docs)
    return global_indexer
'''

if __name__ == "__main__":
    backup = TARGET.with_suffix(".py.bak2")
    if TARGET.exists():
        TARGET.rename(backup)
        print(f"Backed up to {backup}")
    TARGET.write_text(CLEAN_CONTENT, encoding="utf-8")
    print(f"Wrote clean {TARGET}")




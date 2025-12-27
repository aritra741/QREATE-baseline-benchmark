import json
import os
from typing import Tuple, Dict
from quest.core.datapack.doc import Doc, TextDoc, ZenDBDoc
from quest.db.indexer.single_indexer import SingleIndexer, TextDocIndexer
from quest.db.indexer.zendb_indexer import ZenDBDocIndexer

from quest.conf import settings
from quest.db.indexer.preprocessor.load_documents import load_TextDocs_from_directory, load_ZenDBDoc_from_directory


from quest.core.embedding.e5Embedding import batchedE5Embeddings, batchedBGEEmbeddings, SentenceTransformerEmbedding
from quest.core.embedding.apiEmbedding import ApiEmbeddings

# SingleIndexer默认使用的Embedding方法:
# Use local E5 embedding model (auto-downloads from HuggingFace)
# Set device to "cpu" to avoid macOS ARM64 segfault
import torch
import os

# Disable threading to avoid macOS ARM64 segfault with PyTorch
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'
torch.set_num_threads(1)

_device = "cpu"  # Force CPU on macOS to avoid segfaults

# Lazy load embedding model to avoid macOS segfault on import
_local_emb_model = None

def get_local_emb_model():
    """Lazily load the embedding model to avoid segfault on macOS during import."""
    global _local_emb_model
    if _local_emb_model is None:
        _local_emb_model = batchedE5Embeddings(device=_device, batch_size=32)
        print(f"[INFO] Loaded E5 embedding model on device: {_device}")
    return _local_emb_model

# SingleIndexer默认使用的chunker方法
from quest.core.chunker.chunker import GrammarSemanticChunker, SentenceTransformerTokenTextChunker, RecursiveTokenTextChunker, TokenTextChunker
TOKEN_CHUNKER = TokenTextChunker(chunk_size=20000, chunk_overlap=128)

RECURSIVE_TOKEN_CHUNKER = RecursiveTokenTextChunker(chunk_size=512, chunk_overlap=128)

USED_EMBEDDING_MODEL = None  # Will use get_local_emb_model() lazily

GRAMMAR_SEMANTIC_CHUNKER = None  # Will be initialized lazily with the embedding model

USED_CHUNKER = TOKEN_CHUNKER

class GlobalIndexer:
    """
    全局索引器类，负责管理所有表的索引
    """

    def __init__(self, config_save_path: str = settings.GLOBAL_INDEX_CONFIG, chunker = None, embedding_model = None):
        """
        初始化GlobalIndexer实例

        Args:
            config_path: 索引器配置文件路径，用于保存和加载table_name到type的映射
        """
        self.config_path = config_save_path
        self.embedding_model = embedding_model
        self.chunker = chunker
        # 存储table_name到type的映射
        self.table_to_type: Dict[str, str] = {}
        # 存储table_name到SingleIndexer实例的映射
        self.table_to_indexer: Dict[str, SingleIndexer] = {}
        # 索引器类型到类的映射
        self.indexer_classes = {
            "TextDoc": TextDocIndexer,
            "ZenDBDoc": ZenDBDocIndexer,
            # 未来可以添加其他类型: "PdfDoc": PdfDocIndexer, "HierarchicalTextDoc": HierarchicalTextDocIndexer
        }

    def get_indexer(self, table_name: str) -> Tuple[SingleIndexer, str]:
        """
        获取指定表的索引器

        Args:
            table_name: 表名

        Returns:
            对应的SingleIndexer实例和索引类型type
        """
        table_name = table_name.lower()
        if table_name not in self.table_to_indexer:
            raise KeyError(f"'{table_name}' indexer not found")

        indexer = self.table_to_indexer[table_name]
        indexer_type = self.table_to_type[table_name]

        return indexer, indexer_type

    def build_indexer(self, tables_name: list[str], types: list[str], table2docs: dict[str, list[Doc]]):
        """
        建立全局索引

        Args:
            tables_name: 表名列表
            types: 表对应的索引类型列表，顺序与tables_name对应
            table2docs: 表到文档集合的映射
        """
        chunker = self.chunker
        embedding_model = self.embedding_model

        if len(tables_name) != len(types):
            raise ValueError("tables_name和types的长度必须相同")

        # 清空现有映射
        self.table_to_type.clear()
        self.table_to_indexer.clear()

        # 建立table_name到type的映射，并创建对应的SingleIndexer实例
        for table_name, indexer_type in zip(tables_name, types):
            # 检查索引器类型是否支持
            if indexer_type not in self.indexer_classes:
                raise ValueError(f"不支持的索引器类型: {indexer_type}")

            # 存储映射关系
            self.table_to_type[table_name] = indexer_type

            # 创建对应的SingleIndexer实例
            indexer_class = self.indexer_classes[indexer_type]
            indexer = indexer_class(table_name=table_name, type=indexer_type, chunker = chunker, embedding_model = embedding_model) # jztodo
            self.table_to_indexer[table_name] = indexer

            # 如果该表有对应的文档，则构建索引
            if table_name in table2docs:
                docs = table2docs[table_name]
                if docs:  # 确保文档列表不为空
                    indexer.build_indexer(docs)
        self.save_indexer()

    def get_global_doc_id2file_name(self) -> Dict[int, str]:
        """
        返回全局doc_id到file_name的映射字典
        """
        global_doc_id2file_name = {}
        for table_name, indexer in self.table_to_indexer.items():
            doc_ids = indexer.get_docs_id()
            for doc_id in doc_ids:
                file_name = indexer.get_file_name_by_id(doc_id)
                global_doc_id2file_name[doc_id] = file_name
        return global_doc_id2file_name


    def save_indexer(self):
        """
        保存索引器配置到磁盘

        功能：
        - 存储table_name到type的映射到磁盘上
        - 依次调用每个表的SingleIndexer的save_indexer方法，将索引存储到磁盘上
        """

        # 保存之前先创建路径
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

        # 1. 保存table_name到type的映射到配置文件
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.table_to_type, f, ensure_ascii=False, indent=2)

        # 2. 依次调用每个表的SingleIndexer的save_indexer方法
        for table_name, indexer in self.table_to_indexer.items():
            indexer.save_indexer()

    def load_indexer(self, table_to_type = None):
        """
        从磁盘加载索引器配置

        功能：
        - 从磁盘加载构建dict[table_name, type]，然后根据type信息构建dict[table_name, SingleIndexer]
        - 依次调用各个表的SingleIndexer的load_indexer
        """
        # 1. 从配置文件加载table_name到type的映射
        print(f"[DEBUG GlobalIndexer.load_indexer] Config path: {self.config_path}")
        print(f"[DEBUG GlobalIndexer.load_indexer] Config exists: {os.path.exists(self.config_path)}")
        
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f" '{self.config_path}'")

        if table_to_type is None:
            print(f"[DEBUG GlobalIndexer.load_indexer] Loading table_to_type from config file...")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.table_to_type = json.load(f)
            print(f"[DEBUG GlobalIndexer.load_indexer] Loaded {len(self.table_to_type)} tables from config: {list(self.table_to_type.keys())}")
        else:
            print(f"[DEBUG GlobalIndexer.load_indexer] Using provided table_to_type: {list(table_to_type.keys())}")
            self.table_to_type = table_to_type
            # 把self.table_to_type的key全部转化为小写
            self.table_to_type = {k.lower(): v for k, v in self.table_to_type.items()}

        # 2. 根据type信息构建dict[table_name, SingleIndexer]
        self.table_to_indexer.clear()
        print(f"[DEBUG GlobalIndexer.load_indexer] Creating indexers for tables: {list(self.table_to_type.keys())}")
        
        for table_name, indexer_type in self.table_to_type.items():
            # 检查索引器类型是否支持
            if indexer_type not in self.indexer_classes:
                raise ValueError(f"不支持的索引器类型: {indexer_type}")

            print(f"[DEBUG GlobalIndexer.load_indexer] Loading indexer for table '{table_name}' (type: {indexer_type})")
            
            # 创建对应的SingleIndexer实例
            indexer_class = self.indexer_classes[indexer_type]
            indexer = indexer_class(table_name=table_name, type=indexer_type, chunker = self.chunker, embedding_model = self.embedding_model)
            self.table_to_indexer[table_name] = indexer

            # 调用SingleIndexer的load_indexer方法
            indexer.load_indexer()
            
        print(f"[DEBUG GlobalIndexer.load_indexer] Successfully loaded {len(self.table_to_indexer)} indexers")


def load_all_indexer(table_to_type = None, chunker = USED_CHUNKER, embedding_model=USED_EMBEDDING_MODEL) -> GlobalIndexer:
    """加载所有索引器"""
    if embedding_model is None:
        embedding_model = get_local_emb_model()
    global_indexer = GlobalIndexer(chunker=chunker, embedding_model=embedding_model)
    global_indexer.load_indexer(table_to_type)
    return global_indexer

def build_all_indexer(doc_dirs : list[str], tables_name: list[str], types = ["TextDoc", "TextDoc"], debug_flag = False, chunker = USED_CHUNKER ,embedding_model = USED_EMBEDDING_MODEL) -> GlobalIndexer:
    """构建所有索引器"""
    if embedding_model is None:
        embedding_model = get_local_emb_model()
    table2docs = {}
    if len(doc_dirs) != len(tables_name):
        raise ValueError("doc_dirs和table_names的长度必须相同")
    global_indexer = GlobalIndexer(chunker=chunker, embedding_model=embedding_model)

    new_tables_name = []
    # tables_name全转小写
    for  table_name in tables_name:
        new_tables_name.append(table_name.lower())
    tables_name = new_tables_name

    doc_id = 1


    for doc_dir, table_name, type in zip(doc_dirs, tables_name, types):
        # 加载文档
        if type == "TextDoc":
            load_docs_func = load_TextDocs_from_directory
        elif type == "ZenDBDoc":
            load_docs_func = load_ZenDBDoc_from_directory
        docs, next_doc_id = load_docs_func(doc_dir, table_name, start_doc_id=doc_id, debug_flag=debug_flag)
        if debug_flag:
            docs = docs[0:5]
        table2docs[table_name] = docs
        doc_id = next_doc_id
        # 构建索引
    global_indexer.build_indexer(tables_name, types, table2docs)
    # global_indexer.get_global_doc_id2file_name()

    return global_indexer


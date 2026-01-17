import os
import re
from typing import List, Dict, Any
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings

class QREATEChunker:
    def __init__(self, embedding_model_name: str = "intfloat/e5-large-v2"):
        self.embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)
        self.semantic_splitter = SemanticChunker(self.embeddings)
        self.sentence_regex = re.compile(r'[^.!?]*[.!?]')

    def get_last_sentences(self, text: str, n: int = 2) -> str:
        sentences = self.sentence_regex.findall(text)
        if not sentences:
            return ""
        return " ".join(sentences[-n:]).strip()

    def chunk_document(self, file_path: str, doc_id: str) -> List[Dict[str, Any]]:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.strip():
            return []

        global_context = content[:250].replace('\n', ' ')
        chunks = self.semantic_splitter.split_text(content)
        
        processed_chunks = []
        prev_chunk_text = ""
        entity_focus_state = [] # This will be updated by the runner/miner in the orchestration phase

        for i, chunk_text in enumerate(chunks):
            header_lines = [
                f"[DOCUMENT_ID: {doc_id}]",
                f"[ENTITY_FOCUS_STATE: {', '.join(entity_focus_state)}]",
                f"[GLOBAL_CONTEXT: {global_context}]",
                "--- START CHUNK ---"
            ]
            header = "\n".join(header_lines)
            
            # Overlap Logic: Manually append the last 2 sentences of the previous chunk to the start
            overlap = ""
            if i > 0:
                overlap = self.get_last_sentences(prev_chunk_text, 2)
            
            full_chunk_text = f"{header}\n{overlap}\n{chunk_text}".strip()
            
            processed_chunks.append({
                "chunk_id": f"{doc_id}_{i}",
                "text": full_chunk_text,
                "raw_text": chunk_text,
                "overlap": overlap,
                "metadata": {
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "entity_focus_state": list(entity_focus_state)
                }
            })
            prev_chunk_text = chunk_text
            
        return processed_chunks

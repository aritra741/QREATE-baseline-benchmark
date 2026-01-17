import os
import json
import uuid
import re
from typing import List, Dict
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

def get_embeddings():
    # Using BGE-M3 as specified in the requirements
    return HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

def split_sentences(text: str) -> List[str]:
    # Simple sentence splitter
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return sentences

def process_documents(input_dir: str) -> List[Dict]:
    embeddings = get_embeddings()
    semantic_splitter = SemanticChunker(
        embeddings, 
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=0.99
    )
    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=8000,
        chunk_overlap=0
    )
    
    all_chunks = []
    
    for filename in os.listdir(input_dir):
        if filename.endswith(".txt"):
            filepath = os.path.join(input_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Semantic splitting
            chunks = semantic_splitter.split_text(content)
            
            final_chunks_for_file = []
            for chunk in chunks:
                # Safety check: recursive split if too large
                if len(chunk) > 8000:
                    sub_chunks = fallback_splitter.split_text(chunk)
                    final_chunks_for_file.extend(sub_chunks)
                else:
                    final_chunks_for_file.append(chunk)
            
            # Context Injection
            processed_chunks = []
            for i, chunk_text in enumerate(final_chunks_for_file):
                if i > 0:
                    prev_chunk = final_chunks_for_file[i-1]
                    prev_sentences = split_sentences(prev_chunk)
                    last_3 = " ".join(prev_sentences[-3:])
                    
                    injected_text = f"<<CONTEXT_PREAMBLE>>\n{last_3}\n<<END_CONTEXT>>\n{chunk_text}"
                else:
                    injected_text = chunk_text
                
                processed_chunks.append({
                    "id": str(uuid.uuid4()),
                    "source_file": filename,
                    "text": injected_text
                })
            
            all_chunks.extend(processed_chunks)
            
    return all_chunks

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ingest.py <input_dir>")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    chunks = process_documents(input_dir)
    
    with open("chunks.json", "w") as f:
        json.dump(chunks, f, indent=2)
    
    print(f"Processed {len(chunks)} chunks and saved to chunks.json")

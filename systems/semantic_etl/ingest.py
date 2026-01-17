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
    # Semantic splitting with percentile threshold
    semantic_splitter = SemanticChunker(
        embeddings, 
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=0.99
    )
    # Hard 2k token limit (approx 8000 chars)
    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=8000, 
        chunk_overlap=0
    )
    
    all_chunks = []
    
    # Process files
    files = [f for f in os.listdir(input_dir) if f.endswith(".txt")]
    for filename in files:
        filepath = os.path.join(input_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Initial semantic splitting
        raw_chunks = semantic_splitter.split_text(content)
        
        final_chunks_for_file = []
        for chunk in raw_chunks:
            # Enforce 2k token limit
            if len(chunk) > 8000:
                sub_chunks = fallback_splitter.split_text(chunk)
                final_chunks_for_file.extend(sub_chunks)
            else:
                final_chunks_for_file.append(chunk)
        
        # Shadow Context: Store context in metadata, do not prepend
        for i, chunk_text in enumerate(final_chunks_for_file):
            prev_context = ""
            if i > 0:
                # Take last 3 sentences from previous chunk as shadow context
                prev_text = final_chunks_for_file[i-1]
                sentences = split_sentences(prev_text)
                prev_context = " ".join(sentences[-3:])
            
            all_chunks.append({
                "id": str(uuid.uuid4()),
                "source_file": filename,
                "text": chunk_text,
                "previous_context": prev_context
            })
            
    return all_chunks

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        # Default to qreate/input_test if no path provided
        input_path = "../qreate/input_test"
    else:
        input_path = sys.argv[1]
    
    if not os.path.exists(input_path):
        print(f"Error: Path {input_path} does not exist.")
        sys.exit(1)

    print(f"Ingesting from {input_path}...")
    chunks = process_documents(input_path)
    
    with open("chunks.json", "w") as f:
        json.dump(chunks, f, indent=2)
    
    print(f"Processed {len(chunks)} chunks and saved to chunks.json (Shadow Context version)")

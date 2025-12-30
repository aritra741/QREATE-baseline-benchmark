"""
Extractor Module - LLM-based Data Extraction

Extracts structured data from raw text files using an LLM with:
- Document chunking for long texts
- Caching to avoid re-running extraction
- JSON validation and error handling
- Rate limiting for LLM calls
"""

import json
import hashlib
import time
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_API_KEY, CACHE_DIR,
    EXTRACTION_TIMEOUT, EXTRACTION_MAX_RETRIES,
    CHUNK_TOKENIZER, CHUNK_SIZE, CHUNK_OVERLAP
)
from .schema_loader import Schema


logger = logging.getLogger(__name__)


class TextChunker:
    """Splits long documents into overlapping chunks."""
    
    def __init__(self, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        """Initialize chunker.
        
        Args:
            chunk_size: Maximum tokens per chunk
            overlap: Token overlap between chunks
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._token_count_cache = {}
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation: 1 token ≈ 4 chars)."""
        return len(text) // 4
    
    def chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks.
        
        Args:
            text: Input text
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
        
        # Check if text is short enough to not need chunking
        token_count = self.estimate_tokens(text)
        if token_count <= self.chunk_size:
            return [text]
        
        # Split by sentences first for better boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        stride = self.chunk_size - self.overlap
        
        for sentence in sentences:
            sentence_tokens = self.estimate_tokens(sentence)
            
            if current_tokens + sentence_tokens > self.chunk_size and current_chunk:
                # Flush current chunk
                chunks.append(" ".join(current_chunk))
                
                # Keep last few sentences for overlap
                overlap_count = 0
                overlap_tokens = 0
                for sent in reversed(current_chunk):
                    overlap_tokens += self.estimate_tokens(sent)
                    if overlap_tokens > self.overlap:
                        break
                    overlap_count += 1
                
                # Start new chunk with overlap
                current_chunk = current_chunk[-overlap_count:] if overlap_count > 0 else []
                current_tokens = sum(self.estimate_tokens(s) for s in current_chunk)
            
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
        
        # Add final chunk
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks if chunks else [text]


class Extractor:
    """Extracts structured data from text files using LLM."""
    
    def __init__(self, schema: Schema, logger: Optional[logging.Logger] = None):
        """Initialize extractor.
        
        Args:
            schema: Schema object defining what to extract
            logger: Logger instance
        """
        self.schema = schema
        self.logger = logger or logging.getLogger(__name__)
        self.chunker = TextChunker()
        self.client = self._init_client()
        self.cache_dir = CACHE_DIR / "extractions" / schema.entity_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_client(self) -> Optional[Any]:
        """Initialize OpenAI client for Ollama."""
        if OpenAI is None:
            self.logger.warning("OpenAI client not available, extraction will be skipped")
            return None
        
        try:
            client = OpenAI(
                api_key=OLLAMA_API_KEY,
                base_url=OLLAMA_URL
            )
            return client
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI client: {e}")
            return None
    
    def _get_cache_path(self, filepath: Path) -> Path:
        """Get cache file path for a source file.
        
        Args:
            filepath: Source file path
            
        Returns:
            Cache file path
        """
        # Hash filename to get cache key
        file_hash = hashlib.md5(str(filepath).encode()).hexdigest()[:8]
        return self.cache_dir / f"{filepath.stem}_{file_hash}.json"
    
    def _read_cache(self, filepath: Path) -> Optional[List[Dict]]:
        """Read cached extraction results.
        
        Args:
            filepath: Source file path
            
        Returns:
            Cached records or None
        """
        cache_path = self._get_cache_path(filepath)
        if cache_path.exists():
            try:
                with open(cache_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to read cache {cache_path}: {e}")
        return None
    
    def _write_cache(self, filepath: Path, records: List[Dict]):
        """Write extraction results to cache.
        
        Args:
            filepath: Source file path
            records: Extracted records
        """
        cache_path = self._get_cache_path(filepath)
        try:
            with open(cache_path, "w") as f:
                json.dump(records, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to write cache {cache_path}: {e}")
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for extraction.
        
        Returns:
            System prompt text
        """
        schema_text = self.schema.to_prompt_str()
        return f"""You are a data extraction engine. Extract structured data from unstructured text.

{schema_text}

INSTRUCTIONS:
1. Return ONLY valid JSON - no explanation or commentary
2. Extract only fields you can identify with confidence
3. Omit fields if data is not found (do NOT invent values)
4. If multiple records exist, return a JSON array [{{...}}, {{...}}]
5. If no matching data, return empty object {{}}
6. All output MUST be valid JSON

CRITICAL: Start output with {{ or [ only. No other text."""
    
    def _extract_from_text(self, text: str) -> List[Dict]:
        """Extract structured data from a single text chunk using LLM.
        
        Args:
            text: Text to extract from
            
        Returns:
            List of extracted records
        """
        if self.client is None:
            self.logger.warning("Client not initialized, returning empty results")
            return []
        
        system_prompt = self._build_system_prompt()
        
        # Retry logic with backoff
        for attempt in range(EXTRACTION_MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=OLLAMA_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text[:8000]}  # Limit text to 8000 chars
                    ],
                    temperature=0.1,  # Low temperature for consistency
                    timeout=EXTRACTION_TIMEOUT
                )
                
                # Extract JSON from response
                response_text = response.choices[0].message.content.strip()
                
                # Try multiple parsing strategies
                records = self._parse_json_response(response_text)
                return records
                
            except json.JSONDecodeError as e:
                self.logger.warning(f"JSON parse error (attempt {attempt + 1}): {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                self.logger.error(f"Extraction error (attempt {attempt + 1}): {e}")
                time.sleep(2 ** attempt)
        
        return []
    
    def _parse_json_response(self, response_text: str) -> List[Dict]:
        """Parse JSON from LLM response with multiple fallback strategies.
        
        Args:
            response_text: Raw LLM response
            
        Returns:
            List of extracted records
        """
        if not response_text:
            return []
        
        # Strategy 1: Direct parse
        try:
            if response_text.startswith('['):
                return json.loads(response_text)
            elif response_text.startswith('{'):
                obj = json.loads(response_text)
                return [obj] if obj else []
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Try to fix truncated JSON by closing it
        try:
            if response_text.startswith('['):
                # Try to close the array
                fixed = response_text.rstrip() + ']'
                if fixed.count('[') > fixed.count(']'):
                    fixed = response_text.rstrip() + '}]'
                records = json.loads(fixed)
                return records if isinstance(records, list) else [records]
            elif response_text.startswith('{'):
                # Try to close the object
                fixed = response_text.rstrip() + '}'
                if fixed.count('[') > fixed.count(']'):
                    fixed = fixed.rstrip() + ']'
                obj = json.loads(fixed)
                return [obj] if obj else []
        except json.JSONDecodeError:
            pass
        
        # Strategy 3: Extract JSON from text
        # Look for {...} or [...]
        for pattern in [r'\[[\s\S]*', r'\{[\s\S]*']:
            try:
                match = re.search(pattern, response_text)
                if match:
                    json_str = match.group()
                    # Try to close it
                    if json_str.startswith('['):
                        try:
                            records = json.loads(json_str + ']')
                            return records if isinstance(records, list) else [records]
                        except:
                            pass
                    else:
                        try:
                            obj = json.loads(json_str + '}')
                            return [obj] if obj else []
                        except:
                            pass
            except:
                continue
        
        # No valid JSON found
        self.logger.warning(f"Could not extract JSON from response: {response_text[:80]}")
        return []
    
    def extract_from_file(self, filepath: Path, use_cache: bool = True) -> List[Dict]:
        """Extract structured data from a file.
        
        Args:
            filepath: Path to text file
            use_cache: Whether to use cached results
            
        Returns:
            List of extracted records
        """
        filepath = Path(filepath)
        if not filepath.exists():
            self.logger.warning(f"File not found: {filepath}")
            return []
        
        # Check cache
        if use_cache:
            cached = self._read_cache(filepath)
            if cached is not None:
                self.logger.debug(f"Using cached extraction for {filepath.name}")
                return cached
        
        # Read file
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception as e:
            self.logger.error(f"Failed to read file {filepath}: {e}")
            return []
        
        if not text.strip():
            self.logger.warning(f"File is empty: {filepath}")
            return []
        
        # Chunk and extract
        chunks = self.chunker.chunk_text(text)
        all_records = []
        
        for i, chunk in enumerate(chunks):
            self.logger.debug(f"Extracting chunk {i+1}/{len(chunks)} from {filepath.name}")
            records = self._extract_from_text(chunk)
            all_records.extend(records)
            time.sleep(0.5)  # Rate limiting
        
        # Write cache
        self._write_cache(filepath, all_records)
        
        return all_records
    
    def extract_from_directory(self, directory: Path, pattern: str = "*.txt") -> Tuple[List[Dict], Dict[str, int]]:
        """Extract from all files in a directory.
        
        Args:
            directory: Directory containing text files
            pattern: File pattern to match
            
        Returns:
            Tuple of (all_records, stats)
        """
        directory = Path(directory)
        if not directory.exists():
            self.logger.warning(f"Directory not found: {directory}")
            return [], {}
        
        all_records = []
        stats = {"total_files": 0, "successful_files": 0, "total_records": 0}
        
        files = sorted(list(directory.glob(pattern)))
        self.logger.info(f"Extracting from {len(files)} files in {directory}")
        
        for i, filepath in enumerate(files):
            self.logger.info(f"[{i+1}/{len(files)}] Extracting {filepath.name}...")
            records = self.extract_from_file(filepath)
            
            stats["total_files"] += 1
            if records:
                stats["successful_files"] += 1
                stats["total_records"] += len(records)
                all_records.extend(records)
        
        self.logger.info(f"Extraction complete: {stats['total_records']} records from {stats['successful_files']}/{stats['total_files']} files")
        
        return all_records, stats


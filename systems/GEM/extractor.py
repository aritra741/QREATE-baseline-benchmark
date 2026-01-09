"""
Text Extraction Pipeline - LLM-based Entity and Attribute Extraction

Two-stage pipeline:
1. LLM-as-Judge: Binary classification to detect if chunk contains entity info
2. LLM-as-Extractor: Structured extraction of attributes from relevant chunks
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logger = logging.getLogger(__name__)


class TextChunker:
    """Split text into overlapping chunks."""
    
    def __init__(self, chunk_size: int = 5, overlap: int = 2):
        """
        Args:
            chunk_size: Number of sentences per chunk
            overlap: Number of overlapping sentences between chunks
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences (simple approach)."""
        # Simple sentence splitting on periods, newlines
        sentences = []
        current = ""
        
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Split by periods but keep sentence together
            parts = line.split('. ')
            for i, part in enumerate(parts):
                if i < len(parts) - 1:
                    sentences.append(part + '.')
                else:
                    current += part + ' '
        
        if current.strip():
            sentences.append(current.strip())
        
        return [s.strip() for s in sentences if s.strip()]
    
    def chunk(self, text: str) -> List[str]:
        """Create overlapping chunks of sentences."""
        sentences = self.split_into_sentences(text)
        
        if len(sentences) <= self.chunk_size:
            return [' '.join(sentences)]
        
        chunks = []
        for i in range(0, len(sentences), self.chunk_size - self.overlap):
            chunk_sentences = sentences[i:i + self.chunk_size]
            if chunk_sentences:
                chunks.append(' '.join(chunk_sentences))
        
        return chunks


class LLMExtractor:
    """LLM-based entity and attribute extraction."""
    
    def __init__(self, model: str = "qwen2.5:7b-instruct", base_url: str = "http://localhost:11434/v1"):
        """
        Args:
            model: Model name (default: Ollama qwen2.5)
            base_url: LLM API base URL
        """
        self.model = model
        self.base_url = base_url
        
        if OpenAI is None:
            logger.warning("OpenAI client not available")
            self.client = None
        else:
            self.client = OpenAI(api_key="not-needed", base_url=base_url)
    
    def judge_chunk(self, text: str, entity_type: str) -> bool:
        """
        Stage 1: Judge if chunk contains entity information.
        
        Args:
            text: Text chunk to judge
            entity_type: "drug", "disease", or "institution"
            
        Returns:
            True if chunk likely contains entity info, False otherwise
        """
        if self.client is None:
            logger.error("LLM client not initialized")
            return False
        
        prompt = f"""Analyze this text. Does it contain specific information about a {entity_type}?
Consider: names, properties, treatments, symptoms, manufacturers, locations, etc.

Text: {text[:500]}

Answer with only: yes or no"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=10
            )
            
            answer = response.choices[0].message.content.strip().lower()
            return "yes" in answer
        
        except Exception as e:
            logger.error(f"Judge failed: {e}")
            return False
    
    def extract_attributes(self, text: str, entity_type: str, 
                          attributes: List[str]) -> List[Dict[str, Any]]:
        """
        Stage 2: Extract structured attributes from chunk.
        
        Always returns a list of entities (even if just one), where:
        - Each entry is a distinct entity
        - Multi-values for same entity are pipe-delimited
        - Unrelated entities get separate list entries
        
        Args:
            text: Text chunk to extract from
            entity_type: "drug", "disease", or "institution"
            attributes: List of attribute names to extract
            
        Returns:
            List of dicts, each representing one entity with extracted values
        """
        if self.client is None:
            logger.error("LLM client not initialized")
            return []
        
        attributes_str = ", ".join(attributes)
        
        prompt = f"""Extract information from this text about {entity_type} entities.

IMPORTANT: Always return a JSON array, even if there's only ONE entity.
Each array element is a separate {entity_type} entity.
For multi-valued fields within the SAME entity, use pipe-delimiter (||).
For DIFFERENT entities, create separate array entries.

Fields to extract: {attributes_str}

Text: {text[:1000]}

Example format:
[
  {{"name": "Entity1", "field1": "value1", "field2": "value2a||value2b"}},
  {{"name": "Entity2", "field1": "value3", "field2": "value4"}}
]

Return ONLY valid JSON array, no markdown."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=800
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Remove markdown code fence if present
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            result = json.loads(result_text.strip())
            
            # Ensure it's a list
            if not isinstance(result, list):
                result = [result] if result else []
            
            # Process each entity
            processed_entities = []
            for entity in result:
                if not isinstance(entity, dict):
                    continue
                
                # Filter to only requested attributes and ensure strings
                processed = {}
                for k, v in entity.items():
                    if k not in attributes:
                        continue
                    
                    # Convert lists to pipe-delimited strings
                    if isinstance(v, list):
                        v = "||".join(str(item).strip() for item in v if item)
                    elif v is not None:
                        v = str(v).strip()
                    
                    # Only keep non-empty values
                    if v:
                        processed[k] = v
                
                # Only add if we extracted something meaningful (at least 2 fields with values)
                if len(processed) >= 1:
                    processed_entities.append(processed)
            
            return processed_entities
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return []
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return []


class EntityExtractor:
    """High-level entity extraction from raw text files."""
    
    def __init__(self, llm_extractor: Optional[LLMExtractor] = None):
        """
        Args:
            llm_extractor: LLMExtractor instance (creates default if None)
        """
        self.chunker = TextChunker(chunk_size=5, overlap=2)
        self.llm = llm_extractor or LLMExtractor()
        
        # Define attributes for each entity type
        self.entity_attributes = {
            "drug": [
                "generic_name", "brand_name", "disease_name", "indication",
                "manufacturer", "mechanism_of_action", "side_effects",
                "pharmaceutical_form", "administration_route", "dosage_frequency"
            ],
            "disease": [
                "disease_name", "disease_type", "etiology", "pathogenesis",
                "common_symptoms", "complications", "diagnostic_methods",
                "treatments", "prognosis", "risk_factors", "preventive_measures"
            ],
            "institution": [
                "institution_name", "institution_type", "institution_country",
                "institution_city", "research_diseases", "key_technologies",
                "key_achievements", "number_of_staff"
            ]
        }
    
    def extract_from_text(self, text: str, entity_type: str) -> List[Dict[str, Any]]:
        """
        Extract entities from raw text using two-stage LLM pipeline.
        
        Args:
            text: Raw text to process
            entity_type: "drug", "disease", or "institution"
            
        Returns:
            List of extracted entity records (each can have multiple entities per chunk)
        """
        if entity_type not in self.entity_attributes:
            logger.error(f"Unknown entity type: {entity_type}")
            return []
        
        logger.info(f"Extracting {entity_type} entities from text...")
        
        # Step 1: Chunk text
        chunks = self.chunker.chunk(text)
        logger.info(f"Created {len(chunks)} chunks")
        
        # Step 2: Judge and extract
        all_entities = []
        
        for i, chunk in enumerate(chunks):
            # Judge if chunk contains entity info
            if not self.llm.judge_chunk(chunk, entity_type):
                logger.debug(f"Chunk {i}: Skipped (no relevant info)")
                continue
            
            logger.debug(f"Chunk {i}: Relevant, extracting...")
            
            # Extract attributes (returns list of entities)
            attributes = self.entity_attributes[entity_type]
            entities = self.llm.extract_attributes(chunk, entity_type, attributes)
            
            if entities:
                all_entities.extend(entities)
                logger.debug(f"Chunk {i}: Extracted {len(entities)} entities")
        
        logger.info(f"Extracted {len(all_entities)} total entities from text")
        return all_entities
    
    def extract_from_file(self, file_path: Path, entity_type: str) -> List[Dict[str, Any]]:
        """
        Extract entities from a file.
        
        Args:
            file_path: Path to text file
            entity_type: "drug", "disease", or "institution"
            
        Returns:
            List of extracted entity records
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            return self.extract_from_text(text, entity_type)
        
        except Exception as e:
            logger.error(f"Failed to extract from {file_path}: {e}")
            return []
    
    def extract_from_directory(self, dir_path: Path, entity_type: str,
                             max_files: int = None) -> List[Dict[str, Any]]:
        """
        Extract entities from all files in a directory.
        
        Args:
            dir_path: Path to directory
            entity_type: "drug", "disease", or "institution"
            max_files: Maximum number of files to process
            
        Returns:
            List of all extracted entity records
        """
        if not dir_path.exists():
            logger.error(f"Directory not found: {dir_path}")
            return []
        
        txt_files = sorted(list(dir_path.glob("*.txt")))
        if max_files:
            txt_files = txt_files[:max_files]
        
        logger.info(f"Processing {len(txt_files)} files from {dir_path}")
        
        all_entities = []
        
        for i, file_path in enumerate(txt_files, 1):
            logger.info(f"[{i}/{len(txt_files)}] Processing {file_path.name}...")
            entities = self.extract_from_file(file_path, entity_type)
            all_entities.extend(entities)
        
        logger.info(f"Total extracted: {len(all_entities)} entities")
        return all_entities

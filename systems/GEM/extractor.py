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

try:
    from langchain_text_splitters import SemanticChunker
except ImportError:
    SemanticChunker = None

logger = logging.getLogger(__name__)


class TextChunker:
    """Split text into semantically meaningful chunks using LangChain's SemanticChunker."""
    
    def __init__(self, chunk_size: int = 500):
        """
        Args:
            chunk_size: Target size for semantic chunks (approximate)
        """
        self.chunk_size = chunk_size
        
        if SemanticChunker is None:
            logger.warning("LangChain SemanticChunker not available, using fallback")
            self.chunker = None
        else:
            try:
                # Use Ollama with MiniLM embeddings (same as SemanticBlocker for consistency)
                from langchain_community.embeddings import OllamaEmbeddings
                embeddings = OllamaEmbeddings(
                    model="sentence-transformers/all-MiniLM-L6-v2",
                    base_url="http://localhost:11434"
                )
                self.chunker = SemanticChunker(embeddings=embeddings, breakpoint_threshold_type="percentile")
            except Exception as e:
                logger.warning(f"Failed to initialize SemanticChunker: {e}. Using fallback.")
                self.chunker = None
    
    def chunk(self, text: str) -> List[str]:
        """Create semantically meaningful chunks of text."""
        if self.chunker:
            try:
                return self.chunker.split_text(text)
            except Exception as e:
                logger.warning(f"SemanticChunker failed: {e}. Using fallback.")
                return self._fallback_chunk(text)
        else:
            return self._fallback_chunk(text)
    
    def _fallback_chunk(self, text: str) -> List[str]:
        """Fallback: RecursiveCharacterTextSplitter for semantic boundaries."""
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=100,
                separators=["\n\n", "\n", ". ", " ", ""]
            )
            return splitter.split_text(text)
        except Exception as e:
            logger.warning(f"RecursiveCharacterTextSplitter also failed: {e}. Using basic chunking.")
            # Ultimate fallback: simple character-based chunking
            chunks = []
            for i in range(0, len(text), self.chunk_size - 100):
                chunks.append(text[i:i + self.chunk_size])
            return [c for c in chunks if c.strip()]


class LLMExtractor:
    """LLM-based entity and attribute extraction."""
    
    def __init__(self, model: str = "qwen2.5:7b-instruct", base_url: str = "http://localhost:11434/v1",
                 validator_model: str = "qwen2.5:7b-instruct"):
        """
        Args:
            model: Model name for extraction (default: Ollama qwen2.5 7b)
            base_url: LLM API base URL
            validator_model: Model name for validation (default: Ollama qwen2.5 1.5b)
        """
        self.model = model
        self.validator_model = validator_model
        self.base_url = base_url
        
        if OpenAI is None:
            logger.warning("OpenAI client not available")
            self.client = None
        else:
            self.client = OpenAI(api_key="not-needed", base_url=base_url)
    
    def judge_chunk(self, text: str, entity_type: str) -> bool:
        """
        Stage 1: Judge if chunk contains entity information.
        
        Generic binary classification: Does this text contain structured/extractable information?
        Works for any entity type by looking for patterns of entity-like information.
        
        Args:
            text: Text chunk to judge
            entity_type: "drug", "disease", or "institution" (used only for logging)
            
        Returns:
            True if chunk likely contains entity info, False otherwise
        """
        if self.client is None:
            logger.error("LLM client not initialized")
            return False
        
        # Generic prompt that works for any entity type
        prompt = f"""Does this text contain extractable information about entities?
Look for: named entities, attributes, properties, relationships, or structured data.
This could be about anything - products, people, organizations, concepts, etc.

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
            result = "yes" in answer
            logger.debug(f"Judge: response='{answer}' -> {result}")
            return result
        
        except Exception as e:
            logger.error(f"Judge failed: {e}")
            return False
    
    def validate_extraction(self, entity_type: str, value: str, chunk: str) -> bool:
        """
        Semantic validation using Qwen 7B: Does this value make sense as this entity type?
        
        Args:
            entity_type: Type of entity ("drug", "disease", "institution", etc.)
            value: Extracted value to validate
            chunk: Source text chunk (for context)
            
        Returns:
            True if value is valid for entity_type, False otherwise
        """
        if self.client is None:
            logger.debug(f"Validation skipped (no client): {entity_type}='{value}'")
            return True
        
        # Quick filter: reject empty/too short
        if not value or len(value.strip()) < 1:
            logger.info(f"[VALIDATION] REJECTED: {entity_type}='{value}' (empty)")
            return False
        
        # Use LLM for semantic validation with a stricter prompt
        prompt = f"""Validate if this extracted value matches the expected field type.

Field: {entity_type}
Value: "{value}"
Context: {chunk[:200]}

Rules:
- disease_name expects: disease/condition names (e.g., "Diabetes", "COVID-19")
  NOT: measurements, dates, times, generic words
- drug expects: drug/medication names (e.g., "Aspirin", "Metformin")
  NOT: colors, measurements, generic adjectives
- institution expects: organization names (e.g., "Harvard", "WHO")
  NOT: numbers alone, dates, generic words
- dosage expects: measurements with units (e.g., "25 mg", "10 ml")
- year expects: year numbers (e.g., "2025", "1995")
- color expects: color names (e.g., "red", "blue")

Does "{value}" match what {entity_type} expects?
Answer only: yes or no"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.validator_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=5
            )
            
            answer = response.choices[0].message.content.strip().lower()
            is_valid = "yes" in answer
            
            if not is_valid:
                logger.info(f"[VALIDATION] REJECTED: {entity_type}='{value}' (LLM said: '{answer}')")
            else:
                logger.debug(f"[VALIDATION] ACCEPTED: {entity_type}='{value}'")
            
            return is_valid
        
        except Exception as e:
            logger.debug(f"Validation error for {entity_type}='{value}': {e}")
            return True  # Default to accepting on error
    
    def extract_attributes(self, text: str, entity_type: str, 
                          attributes: List[str], schema_guidance: Optional[Dict] = None) -> List[Dict[str, Any]]:
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
            schema_guidance: Optional dict mapping field names to their descriptions/constraints
            
        Returns:
            List of dicts, each representing one entity with extracted values
        """
        if self.client is None:
            logger.error("LLM client not initialized")
            return []
        
        attributes_str = ", ".join(attributes)
        
        # Build schema guidance section for prompt
        guidance_section = ""
        if schema_guidance:
            guidance_lines = []
            for attr, guidance in schema_guidance.items():
                guidance_lines.append(f"  - {attr}: {guidance}")
            guidance_section = "FIELD CONSTRAINTS:\n" + "\n".join(guidance_lines) + "\n\n"
        
        prompt = f"""You are extracting structured entities from a text chunk.

Output contract (STRICT):
- Return ONLY a valid JSON array (no markdown, no prose).
- Each array element is ONE distinct {entity_type} entity.
- Only include keys from: {attributes_str}
- Omit any field that is not explicitly supported by the text.
- Do not guess, infer, or use world knowledge.

Grounding requirements (CRITICAL):
- For every value you output, it MUST be directly supported by an explicit span in the text.
- Do not output standalone properties/modifiers as entities.
- Do not output fragments or context-dependent references (e.g., leading articles, vague noun phrases, dangling descriptors).
- Numeric and unit values ARE valid for attribute fields (e.g., quantities, years, measurements).
- But do not use numeric/unit-only values as primary entity identifiers unless they are explicitly named as such in the text.
- If a value's meaning depends entirely on context (e.g., "12.5 mg" only makes sense as a dose of something), ground it to its parent entity.

Canonicalization rules:
- Prefer the shortest self-contained surface form that still uniquely identifies the entity in the text.
- If multiple surface forms refer to the same entity within this chunk, output only ONE entry and prefer the most informative canonical form present in the text.

Multi-value rules:
- If a single entity truly has multiple values for one field, join them with '||' in ONE string.
- If the text mentions multiple distinct entities, they must be separate array elements (do NOT merge them into one field value).

Schema constraints (apply when present; especially for fixed-vocabulary fields):
{guidance_section}Fields to extract: {attributes_str}

Text (verbatim excerpt):
{text[:1000]}

Return ONLY valid JSON array. Example shape (keys are illustrative only):
[
  {{"<fieldA>": \"...\", "<fieldB>": \"...\"}},
  {{"<fieldA>": \"...\"}}
]"""
        
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
                
                # Only add if we extracted something meaningful
                if len(processed) >= 1:
                    # Validate key fields (typically first attribute is the primary key)
                    if attributes:
                        primary_key = attributes[0]
                        if primary_key in processed:
                            if not self.validate_extraction(entity_type, processed[primary_key], text):
                                logger.debug(f"Skipped entity: {processed} (validation failed for {primary_key}='{processed[primary_key]}')")
                                continue
                    
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
    
    def __init__(self, llm_extractor: Optional[LLMExtractor] = None, schema: Optional[Dict] = None):
        """
        Args:
            llm_extractor: LLMExtractor instance (creates default if None)
            schema: Optional schema dict with field descriptions (e.g., from Med_attributes.json)
                   Format: {entity_type: {field_name: {description, is_fixed, ...}}}
        """
        # Use LangChain's semantic chunking (500 chars per chunk, 100 chars overlap)
        self.chunker = TextChunker(chunk_size=500, overlap=100)
        self.llm = llm_extractor or LLMExtractor()
        self.schema = schema or {}
        
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
    
    def _get_field_guidance(self, entity_type: str, field_name: str) -> Optional[str]:
        """
        Get field guidance from schema if available.
        
        Returns the description and choice options for fields with is_fixed=true.
        """
        if entity_type not in self.schema:
            return None
        
        if field_name not in self.schema[entity_type]:
            return None
        
        field_info = self.schema[entity_type][field_name]
        description = field_info.get("description", "")
        is_fixed = field_info.get("is_fixed", False)
        
        # If field has controlled vocabulary, include it in guidance
        if is_fixed and description:
            return description
        
        return None
    
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
            
            # Build schema guidance for LLM
            schema_guidance = {}
            for attr in attributes:
                guidance = self._get_field_guidance(entity_type, attr)
                if guidance:
                    schema_guidance[attr] = guidance
            
            entities = self.llm.extract_attributes(chunk, entity_type, attributes, schema_guidance)
            
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

"""
The Sieve: Preprocessing index for fast chunk filtering.
"""
import re
import pickle
from pathlib import Path
from typing import Dict, List, Set, Optional
from collections import defaultdict
from flashtext import KeywordProcessor
from loguru import logger
from tqdm import tqdm

from models import SieveEntry
from config import QAIRSConfig


class Sieve:
    """
    The Sieve is a lightweight structural index that enables fast filtering
    of chunks without LLM calls. It uses:
    - Dictionary matching (FlashText/Aho-Corasick)
    - Type detection (Regex)
    - Optional entity recognition (NER)
    """
    
    def __init__(self, config: QAIRSConfig):
        self.config = config
        self.index: Dict[str, SieveEntry] = {}
        
        # Dictionary processor
        self.keyword_processor = KeywordProcessor(case_sensitive=False)
        self.dictionary_map: Dict[str, str] = {}  # synonym -> canonical
        
        # Compiled regex patterns
        self.regex_patterns = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in config.sieve.regex_patterns.items()
        }
        
        # Optional: NER model
        self.ner_model = None
        if config.sieve.enable_ner:
            try:
                import spacy
                self.ner_model = spacy.load("en_core_web_sm")
                logger.info("Loaded spacy NER model")
            except Exception as e:
                logger.warning(f"Failed to load NER model: {e}")
    
    def build_dictionary(self, terms: List[str], llm_client=None) -> None:
        """
        Build dictionary with optional LLM-based synonym expansion.
        
        Args:
            terms: List of canonical terms (e.g., ["USA", "Denied", "Paid"])
            llm_client: Optional LLM client for synonym generation
        """
        logger.info(f"Building dictionary with {len(terms)} terms")
        
        for term in terms:
            # Add canonical term
            self.keyword_processor.add_keyword(term, term)
            self.dictionary_map[term.lower()] = term
            
            # Expand with synonyms if LLM available
            if llm_client and self.config.sieve.dictionary_expansion:
                synonyms = self._generate_synonyms(term, llm_client)
                for syn in synonyms:
                    self.keyword_processor.add_keyword(syn, term)
                    self.dictionary_map[syn.lower()] = term
                    logger.debug(f"Added synonym: {syn} -> {term}")
        
        logger.info(f"Dictionary built with {len(self.dictionary_map)} total entries")
    
    def _generate_synonyms(self, term: str, llm_client, max_synonyms: int = 10) -> List[str]:
        """
        Use LLM to generate synonyms for a term.
        """
        prompt = f"""Generate {max_synonyms} common synonyms or alternative phrasings for the term: "{term}"

Requirements:
- Only return synonyms that would appear in real text
- Include common misspellings or variations
- Return as a comma-separated list
- Do not include the original term

Synonyms:"""
        
        try:
            response = llm_client.generate(prompt, max_tokens=200)
            synonyms = [s.strip() for s in response.split(',')]
            return synonyms[:max_synonyms]
        except Exception as e:
            logger.warning(f"Failed to generate synonyms for '{term}': {e}")
            return []
    
    def build_index(self, chunks: Dict[str, str]) -> None:
        """
        Build the Sieve index from corpus chunks.
        
        Args:
            chunks: Dictionary mapping chunk_id -> chunk_text
        """
        logger.info(f"Building Sieve index for {len(chunks)} chunks")
        
        for chunk_id, text in tqdm(chunks.items(), desc="Building Sieve"):
            entry = self._process_chunk(chunk_id, text)
            self.index[chunk_id] = entry
        
        logger.info(f"Sieve index built with {len(self.index)} entries")
    
    def _process_chunk(self, chunk_id: str, text: str) -> SieveEntry:
        """
        Process a single chunk and create Sieve entry.
        """
        entry = SieveEntry(chunk_id=chunk_id)
        
        # Dictionary matching
        if self.config.sieve.enable_dictionary:
            keywords_found = self.keyword_processor.extract_keywords(text)
            entry.dict_tags = list(set(keywords_found))  # Deduplicate
        
        # Type detection via regex
        if self.config.sieve.enable_regex:
            for type_name, pattern in self.regex_patterns.items():
                entry.type_mask[type_name] = bool(pattern.search(text))
        
        # Entity recognition
        if self.config.sieve.enable_ner and self.ner_model:
            doc = self.ner_model(text[:1000])  # Limit length for speed
            for ent in doc.ents:
                if ent.label_ not in entry.entities:
                    entry.entities[ent.label_] = []
                entry.entities[ent.label_].append(ent.text)
        
        return entry
    
    def query(
        self,
        dict_tags: Optional[List[str]] = None,
        type_masks: Optional[Dict[str, bool]] = None,
        entity_types: Optional[List[str]] = None
    ) -> List[str]:
        """
        Query the Sieve to get candidate chunk IDs.
        
        Args:
            dict_tags: Required dictionary tags (OR logic)
            type_masks: Required type masks (AND logic)
            entity_types: Required entity types (OR logic)
        
        Returns:
            List of chunk IDs matching the criteria
        """
        candidates = []
        
        for chunk_id, entry in self.index.items():
            # Check dictionary tags (OR logic)
            if dict_tags:
                if not any(tag in entry.dict_tags for tag in dict_tags):
                    continue
            
            # Check type masks (AND logic)
            if type_masks:
                if not all(entry.type_mask.get(k, False) == v for k, v in type_masks.items()):
                    continue
            
            # Check entity types (OR logic)
            if entity_types:
                if not any(etype in entry.entities for etype in entity_types):
                    continue
            
            candidates.append(chunk_id)
        
        return candidates
    
    def save(self, path: Optional[str] = None) -> None:
        """Save Sieve index to disk."""
        save_path = path or self.config.sieve.sieve_path
        logger.info(f"Saving Sieve index to {save_path}")
        
        data = {
            'index': self.index,
            'dictionary_map': self.dictionary_map,
            'config': self.config.sieve.model_dump()
        }
        
        with open(save_path, 'wb') as f:
            pickle.dump(data, f)
        
        logger.info(f"Sieve saved ({len(self.index)} entries)")
    
    @classmethod
    def load(cls, path: str, config: QAIRSConfig) -> "Sieve":
        """Load Sieve index from disk."""
        logger.info(f"Loading Sieve index from {path}")
        
        with open(path, 'rb') as f:
            data = pickle.load(f)
        
        sieve = cls(config)
        sieve.index = data['index']
        sieve.dictionary_map = data['dictionary_map']
        
        # Rebuild keyword processor
        for synonym, canonical in sieve.dictionary_map.items():
            sieve.keyword_processor.add_keyword(synonym, canonical)
        
        logger.info(f"Sieve loaded ({len(sieve.index)} entries)")
        return sieve
    
    def get_statistics(self) -> Dict:
        """Get statistics about the Sieve index."""
        stats = {
            'total_chunks': len(self.index),
            'dict_tag_distribution': defaultdict(int),
            'type_mask_distribution': defaultdict(int),
        }
        
        for entry in self.index.values():
            for tag in entry.dict_tags:
                stats['dict_tag_distribution'][tag] += 1
            for type_name, present in entry.type_mask.items():
                if present:
                    stats['type_mask_distribution'][type_name] += 1
        
        return dict(stats)

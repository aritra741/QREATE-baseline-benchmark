"""
Resolver Module - Global Entity Resolution

Resolves entity identities globally by finding canonical names for each block.
Uses LLM to determine the most standard representation of each entity cluster.
"""

import json
import logging
import time
from typing import List, Dict, Set, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_API_KEY,
    RESOLUTION_TIMEOUT, RESOLUTION_MAX_RETRIES
)


logger = logging.getLogger(__name__)


class EntityResolver:
    """Resolves entity identities to canonical forms."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize resolver.
        
        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.client = self._init_client()
        self.canonical_map: Dict[str, str] = {}
    
    def _init_client(self) -> Optional[object]:
        """Initialize OpenAI client for Ollama."""
        if OpenAI is None:
            self.logger.warning("OpenAI client not available")
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
    
    def _get_canonical_for_block(self, mentions: List[str]) -> str:
        """Get canonical name for a block of mentions using discriminative clustering.
        
        This implements the "Splitter Pattern" - it identifies distinct entities within a block
        and only merges true synonyms, keeping different variants/versions separate.
        
        Args:
            mentions: List of entity mentions (strings)
            
        Returns:
            Canonical name (or if multiple distinct entities detected, uses best-match)
        """
        # Remove duplicates and empty strings
        unique_mentions = list(set(m for m in mentions if m and isinstance(m, str)))
        
        if not unique_mentions:
            return ""
        
        if len(unique_mentions) == 1:
            return unique_mentions[0]
        
        if self.client is None:
            self.logger.warning("Client not initialized, using first mention as canonical")
            return unique_mentions[0]
        
        # Call LLM with discriminative instructions - SPLITTER PATTERN
        prompt = f"""You are an expert at distinguishing synonyms from distinct variants.

Here is a list of entity mentions that were deemed similar by embedding-based blocking:
{json.dumps(sorted(unique_mentions), indent=2)}

TASK: Group these mentions into entities. Keep SYNONYMS together but KEEP DISTINCT VARIANTS SEPARATE.

Rules:
1. SAME ENTITY: Synonyms, case variations, abbreviations of the SAME product/variant
   - Example: "iPhone 15" and "iphone 15" and "iPhone15" are the SAME
2. DIFFERENT ENTITIES: Different products, versions, tiers, sizes, capacities, generations
   - Example: "iPhone 15 Pro" vs "iPhone 15 Pro Max" are DIFFERENT
   - Example: "Pro 256GB" vs "Pro 512GB" are DIFFERENT
3. Better to under-merge (keep separate) than over-merge (lose information).

Return ONLY a JSON map in this exact format:
{{
  "Canonical Name 1": ["variant1", "variant2"],
  "Canonical Name 2": ["variant3", "variant4"]
}}

If all are synonyms of one entity, return one group with that canonical name."""
        
        for attempt in range(RESOLUTION_MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=OLLAMA_MODEL,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,  # Deterministic
                    timeout=RESOLUTION_TIMEOUT
                )
                
                response_text = response.choices[0].message.content.strip()
                
                if not response_text:
                    self.logger.warning("Empty response from LLM, using first mention")
                    return unique_mentions[0]
                
                # Try to parse JSON response
                try:
                    groups = json.loads(response_text)
                    
                    # Find which group has the most mentions (primary entity)
                    primary_canonical = unique_mentions[0]
                    max_variants = 0
                    
                    for canonical, variants in groups.items():
                        if len(variants) > max_variants:
                            max_variants = len(variants)
                            primary_canonical = canonical
                    
                    self.logger.debug(f"LLM resolved {len(groups)} distinct entity groups")
                    return primary_canonical
                    
                except json.JSONDecodeError:
                    # If JSON parsing fails, fall back to first mention
                    self.logger.warning(f"Failed to parse LLM JSON response: {response_text}")
                    return unique_mentions[0]
                
            except Exception as e:
                self.logger.warning(f"Resolution error (attempt {attempt + 1}): {e}")
                time.sleep(2 ** attempt)
        
        # Fallback to first mention
        self.logger.warning("Failed to resolve canonically, using first mention")
        return unique_mentions[0]
    
    def resolve_blocks(self, records: List[Dict], blocks: List[Set[int]],
                       key_attributes: List[str]) -> Dict[str, str]:
        """Resolve all blocks to canonical names.
        
        Args:
            records: List of extracted records
            blocks: List of blocks (sets of record indices)
            key_attributes: Attributes to use for determining canonical names
            
        Returns:
            Canonical map: mapping variation -> canonical_name
        """
        self.canonical_map = {}
        
        if not blocks:
            self.logger.warning("No blocks to resolve")
            return self.canonical_map
        
        self.logger.info(f"Resolving {len(blocks)} blocks to canonical names")
        
        for block_idx, block in enumerate(blocks):
            # Extract mentions from block
            mentions = []
            for record_idx in block:
                if record_idx < len(records):
                    record = records[record_idx]
                    # Concatenate key attributes
                    for attr in key_attributes:
                        val = record.get(attr)
                        if val is not None:
                            mentions.append(str(val))
            
            if not mentions:
                self.logger.debug(f"Block {block_idx}: No mentions found")
                continue
            
            # Get canonical name
            canonical = self._get_canonical_for_block(mentions)
            
            # Map all variations to canonical
            for mention in mentions:
                if mention:
                    # Map lowercase version to canonical
                    self.canonical_map[mention.lower()] = canonical
                    self.canonical_map[mention] = canonical
            
            if (block_idx + 1) % 10 == 0:
                self.logger.info(f"Resolved {block_idx + 1}/{len(blocks)} blocks")
        
        self.logger.info(f"Resolution complete: {len(self.canonical_map)} mappings")
        return self.canonical_map
    
    def get_canonical(self, mention: str) -> str:
        """Get canonical name for a mention.
        
        Args:
            mention: Entity mention
            
        Returns:
            Canonical name or original if not found
        """
        if not mention:
            return mention
        
        # Try exact match
        if mention in self.canonical_map:
            return self.canonical_map[mention]
        
        # Try lowercase match
        lowercase = mention.lower()
        if lowercase in self.canonical_map:
            return self.canonical_map[lowercase]
        
        # Return original
        return mention
    
    def normalize_record(self, record: Dict, key_attributes: List[str], schema: Optional[object] = None) -> Dict:
        """Normalize a record by replacing key values with canonical forms and converting types.
        
        Args:
            record: Record to normalize
            key_attributes: Attributes to normalize (entity resolution)
            schema: Schema object for type information (optional)
            
        Returns:
            Normalized record with canonical names and proper types
        """
        normalized = record.copy()
        
        # First: Replace with canonical forms for key attributes
        for attr in key_attributes:
            if attr in normalized:
                val = normalized[attr]
                if val is not None:
                    canonical = self.get_canonical(str(val))
                    normalized[attr] = canonical
        
        # Second: Apply type conversions based on schema
        if schema:
            for attr in schema.attributes:
                if attr.name in normalized and normalized[attr.name] is not None:
                    val = normalized[attr.name]
                    type_lower = attr.type.lower()
                    
                    try:
                        if type_lower in ["int", "integer", "int_value"]:
                            # Convert to int
                            normalized[attr.name] = int(float(str(val)))
                        elif type_lower in ["float", "double", "float_value"]:
                            # Convert to float
                            normalized[attr.name] = float(str(val))
                        elif type_lower in ["bool", "boolean"]:
                            # Convert to bool
                            if isinstance(val, bool):
                                normalized[attr.name] = val
                            else:
                                normalized[attr.name] = str(val).lower() in ["true", "1", "yes"]
                        # For string types, keep as-is
                    except (ValueError, TypeError) as e:
                        self.logger.debug(f"Failed to convert {attr.name}={val} to {attr.type}: {e}")
                        # Keep original value if conversion fails
        
        return normalized
    
    def normalize_records(self, records: List[Dict], key_attributes: List[str], schema: Optional[object] = None, deduplicate: bool = True) -> List[Dict]:
        """Normalize all records by applying canonical mapping and type conversion.
        
        Args:
            records: Records to normalize
            key_attributes: Attributes to normalize (entity resolution)
            schema: Schema object for type information (optional)
            deduplicate: Whether to deduplicate records based on key attributes (default: True)
            
        Returns:
            Normalized records with canonical names and proper types
        """
        self.logger.info(f"Normalizing {len(records)} records")
        normalized = [self.normalize_record(r, key_attributes, schema) for r in records]
        
        if deduplicate:
            # Deduplicate: keep only one record per unique key attribute combination
            seen = {}
            unique_records = []
            
            for record in normalized:
                # Create a key from the key attributes
                key_tuple = tuple(record.get(attr) for attr in key_attributes)
                
                if key_tuple not in seen:
                    seen[key_tuple] = True
                    unique_records.append(record)
            
            self.logger.info(f"Deduplication: {len(normalized)} records -> {len(unique_records)} unique records")
            normalized = unique_records
        
        self.logger.info("Normalization complete")
        return normalized
    
    def save_canonical_map(self, filepath: str):
        """Save canonical map to JSON file.
        
        Args:
            filepath: Path to save to
        """
        try:
            with open(filepath, "w") as f:
                json.dump(self.canonical_map, f, indent=2)
            self.logger.info(f"Saved canonical map to {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to save canonical map: {e}")
    
    def load_canonical_map(self, filepath: str):
        """Load canonical map from JSON file.
        
        Args:
            filepath: Path to load from
        """
        try:
            with open(filepath, "r") as f:
                self.canonical_map = json.load(f)
            self.logger.info(f"Loaded canonical map from {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to load canonical map: {e}")


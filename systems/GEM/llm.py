"""
LLM Resolution Module - Discriminative Entity Resolution

Uses LLM to resolve candidate blocks by identifying distinct entities
within a block and preventing over-merging of distinct variants.
"""

import json
import logging
import time
from typing import List, Dict, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_API_KEY,
    RESOLUTION_TIMEOUT, RESOLUTION_MAX_RETRIES
)


logger = logging.getLogger(__name__)


class LLMClient:
    """Client for LLM-based entity resolution."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize LLM client.
        
        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.client = self._init_client()
    
    def _init_client(self) -> Optional[object]:
        """Initialize OpenAI client for Ollama.
        
        Returns:
            OpenAI client or None if initialization fails
        """
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
    
    def resolve_block(self, mentions: List[str]) -> Dict[str, List[str]]:
        """Resolve a candidate block using discriminative LLM clustering.
        
        Determines which mentions are synonyms (should merge) and which are
        distinct entities (should remain separate).
        
        Args:
            mentions: List of entity mentions in the block
            
        Returns:
            Dictionary mapping canonical name to list of synonyms
            Example: {
                "iPhone 15 Pro": ["iphone 15 pro", "15 pro"],
                "iPhone 15 Pro Max": ["iphone 15 pro max", "15 pro max"]
            }
        """
        # Remove duplicates and empty strings
        unique_mentions = list(set(m for m in mentions if m and isinstance(m, str)))
        
        if not unique_mentions:
            self.logger.warning("No unique mentions to resolve")
            return {}
        
        if len(unique_mentions) == 1:
            # Single mention, no resolution needed
            return {unique_mentions[0]: unique_mentions}
        
        if self.client is None:
            self.logger.warning("Client not initialized, returning single group")
            # Return all as one group
            canonical = unique_mentions[0]
            return {canonical: unique_mentions}
        
        # Call LLM with discriminative instructions
        prompt = f"""You are an expert at distinguishing synonyms from distinct product variants.

Here is a block of entity mentions that were clustered as semantically similar:
{json.dumps(sorted(unique_mentions), indent=2)}

CRITICAL TASK: Determine if these represent ONE entity or MULTIPLE DISTINCT entities.

RULES FOR GROUPING:
1. SAME ENTITY (merge into one canonical name):
   - Case variations: "iPhone 15 Pro" vs "iphone 15 pro" → SAME
   - Abbreviations: "iPhone 15 Pro" vs "i15 Pro" → SAME
   - Short forms: "iPhone 15 Pro" vs "15 Pro" → SAME
   - Common synonyms: "Advil" vs "Ibuprofen" → SAME

2. DIFFERENT ENTITIES (keep separate):
   - Different product versions: "iPhone 15 Pro" vs "iPhone 15 Pro Max" → DIFFERENT
   - Different capacities: "Pro 256GB" vs "Pro 512GB" → DIFFERENT
   - Different tiers: "Galaxy S24" vs "Galaxy S24 Ultra" → DIFFERENT
   - Different generations: "iPhone 14 Pro" vs "iPhone 15 Pro" → DIFFERENT

3. PRIORITY: Better to under-merge (keep separate) than over-merge (lose data).

OUTPUT FORMAT - Return ONLY valid JSON, nothing else:
{{
  "Canonical Name 1": ["synonym1", "synonym2", "synonym3"],
  "Canonical Name 2": ["synonym4", "synonym5"],
  "Canonical Name 3": ["synonym6"]
}}

Use the MOST COMMON OR STANDARD NAME as the canonical name for each group.
If a group has only one mention, that mention is its canonical name."""
        
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
                    self.logger.warning("Empty response from LLM")
                    canonical = unique_mentions[0]
                    return {canonical: unique_mentions}
                
                # Try to parse JSON
                try:
                    result = json.loads(response_text)
                    
                    if not isinstance(result, dict):
                        self.logger.warning(f"Invalid response format: {response_text}")
                        canonical = unique_mentions[0]
                        return {canonical: unique_mentions}
                    
                    self.logger.info(f"LLM resolved {len(unique_mentions)} mentions into {len(result)} entity groups")
                    return result
                    
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Failed to parse JSON response: {response_text[:100]}... ({e})")
                    # Try to extract JSON from response
                    try:
                        start = response_text.find('{')
                        end = response_text.rfind('}') + 1
                        if start >= 0 and end > start:
                            json_str = response_text[start:end]
                            result = json.loads(json_str)
                            self.logger.info(f"Extracted and parsed JSON from response")
                            return result
                    except:
                        pass
                    
                    # Fallback: return all as one group
                    canonical = unique_mentions[0]
                    return {canonical: unique_mentions}
                
            except Exception as e:
                self.logger.warning(f"Resolution error (attempt {attempt + 1}/{RESOLUTION_MAX_RETRIES}): {e}")
                time.sleep(2 ** attempt)
        
        # Fallback: return all as one group
        self.logger.warning("Failed to resolve with LLM, returning single group")
        canonical = unique_mentions[0]
        return {canonical: unique_mentions}
    
    def resolve_blocks(self, blocks: Dict[str, List[str]]) -> Dict[str, Dict[str, List[str]]]:
        """Resolve multiple blocks.
        
        Args:
            blocks: Dictionary mapping block representative to list of mentions
            
        Returns:
            Dictionary mapping block representative to its LLM resolution
        """
        resolutions = {}
        
        for block_idx, (representative, mentions) in enumerate(blocks.items()):
            self.logger.info(f"Resolving block {block_idx + 1}/{len(blocks)}: {representative} ({len(mentions)} mentions)")
            
            resolution = self.resolve_block(mentions)
            resolutions[representative] = resolution
        
        return resolutions

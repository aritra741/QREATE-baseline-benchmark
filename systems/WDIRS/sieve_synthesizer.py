"""
Programmatic Sieve Synthesis for WDIRS.
Generates filtering functions using spaCy, FlashText, and regex.
"""

import json
import logging
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Iterator, Tuple, Set, Optional, Callable, Any
from dataclasses import dataclass
from pathlib import Path

from flashtext import KeywordProcessor
import spacy

from config import (
    SIEVE_SAMPLE_SIZE,
    SIEVE_REFINEMENT_ITERATIONS,
    SIEVE_TEST_SIZE,
    SIEVE_DIR
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class SieveResult:
    """Result of sieve synthesis."""
    table_name: str
    sieve_function: str  # Python code as string
    accuracy: float
    keywords: List[str]
    patterns: List[str]
    entity_types: List[str]


# ============================================================================
# Sieve Synthesizer
# ============================================================================

class SieveSynthesizer:
    """
    Synthesizes programmatic sieves for filtering relevant chunks.
    Uses spaCy for NER, FlashText for keywords, and regex for patterns.
    """
    
    def __init__(self, llm_client, spacy_model: str = "en_core_web_sm"):
        """
        Initialize sieve synthesizer.
        
        Args:
            llm_client: LLM client for code generation
            spacy_model: spaCy model to use
        """
        self.llm_client = llm_client
        
        # Load spaCy model - REQUIRED, no fallback
        try:
            self.nlp = spacy.load(spacy_model)
            logger.info(f"Loaded spaCy model: {spacy_model}")
        except OSError as e:
            logger.error(f"spaCy model {spacy_model} not found. Please install it with: python -m spacy download {spacy_model}")
            raise RuntimeError(f"Required spaCy model '{spacy_model}' not found. Install it with: python -m spacy download {spacy_model}") from e
        
        # Create sieve directory
        SIEVE_DIR.mkdir(parents=True, exist_ok=True)
    
    def synthesize_sieve(
        self,
        table_name: str,
        schema: Dict[str, str],
        sample_chunks: List[str],
        positive_examples: Optional[List[str]] = None
    ) -> SieveResult:
        """
        Synthesize a sieve function for a table.
        
        Args:
            table_name: Name of the table
            schema: Column schema (column_name -> semantic_type)
            sample_chunks: Sample text chunks for synthesis
            positive_examples: Optional positive examples
            
        Returns:
            SieveResult with synthesized function
        """
        logger.info(f"Synthesizing sieve for table: {table_name}")
        
        # Step 1: Analyze sample chunks to extract patterns
        keywords, patterns, entity_types = self._analyze_samples(
            sample_chunks,
            schema
        )
        
        # Step 2: Generate initial sieve function using LLM
        sieve_code = self._generate_sieve_code(
            table_name,
            schema,
            keywords,
            patterns,
            entity_types
        )
        
        # Step 3: Refine sieve through iterative testing
        refined_code, accuracy = self._refine_sieve(
            sieve_code,
            sample_chunks,
            positive_examples
        )
        
        # Step 4: Save sieve to file
        self._save_sieve(table_name, refined_code)
        
        result = SieveResult(
            table_name=table_name,
            sieve_function=refined_code,
            accuracy=accuracy,
            keywords=keywords,
            patterns=patterns,
            entity_types=entity_types
        )
        
        logger.info(f"Sieve synthesis complete for {table_name} (accuracy: {accuracy:.2%})")
        
        return result
    
    def _analyze_samples(
        self,
        sample_chunks: List[str],
        schema: Dict[str, str]
    ) -> tuple[List[str], List[str], List[str]]:
        """
        Analyze sample chunks to extract keywords, patterns, and entity types.
        """
        keywords = set()
        patterns = set()
        entity_types = set()
        
        for chunk in sample_chunks:
            # Extract entities using spaCy
            doc = self.nlp(chunk)
            
            for ent in doc.ents:
                entity_types.add(ent.label_)
                keywords.add(ent.text.lower())
            
            # Extract keywords based on schema
            for col_name, semantic_type in schema.items():
                # Look for column name variations in text
                col_variations = self._generate_column_variations(col_name)
                
                for variation in col_variations:
                    if variation.lower() in chunk.lower():
                        keywords.add(variation.lower())
            
            # Extract common patterns
            # Dates
            date_patterns = [
                r'\d{1,2}/\d{1,2}/\d{2,4}',
                r'\d{4}-\d{2}-\d{2}',
                r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b'
            ]
            
            for pattern in date_patterns:
                if re.search(pattern, chunk):
                    patterns.add(pattern)
            
            # IDs and codes
            if re.search(r'\b[A-Z]\d{3,}\b', chunk):
                patterns.add(r'\b[A-Z]\d{3,}\b')
            
            # Money
            if re.search(r'\$\d+(?:,\d{3})*(?:\.\d{2})?', chunk):
                patterns.add(r'\$\d+(?:,\d{3})*(?:\.\d{2})?')
        
        return list(keywords), list(patterns), list(entity_types)
    
    def _generate_column_variations(self, column_name: str) -> List[str]:
        """Generate variations of column name."""
        variations = [column_name]
        
        # Split by underscore
        parts = column_name.split('_')
        if len(parts) > 1:
            variations.append(' '.join(parts))
            variations.append(''.join(p.capitalize() for p in parts))
        
        # Add singular/plural
        if column_name.endswith('s'):
            variations.append(column_name[:-1])
        else:
            variations.append(column_name + 's')
        
        return variations
    
    def _generate_sieve_code(
        self,
        table_name: str,
        schema: Dict[str, str],
        keywords: List[str],
        patterns: List[str],
        entity_types: List[str]
    ) -> str:
        """Generate sieve function code using LLM."""
        prompt = f"""Generate a Python function called `is_relevant(text)` that returns True if a text chunk contains potential data for a database table.

Table: {table_name}
Schema: {json.dumps(schema, indent=2)}

Relevant keywords: {', '.join(keywords[:20])}
Relevant patterns: {', '.join(patterns[:10])}
Relevant entity types: {', '.join(entity_types)}

Requirements:
1. Use keyword matching with FlashText, regex patterns with re, and/or spaCy NER
2. Import necessary libraries at the top
3. Be conservative - prefer false positives over false negatives
4. Return True if text likely contains data for this table, False otherwise
5. IMPORTANT: Use correct Python syntax - do NOT use any() with a single boolean expression
6. IMPORTANT: Check if variables are None before iterating over them

Example structure:
```python
import re
from flashtext import KeywordProcessor
import spacy

nlp = spacy.load("en_core_web_sm")

def is_relevant(text: str) -> bool:
    # Keyword matching
    keyword_processor = KeywordProcessor()
    keyword_processor.add_keywords_from_list(["keyword1", "keyword2"])
    keywords_found = keyword_processor.extract_keywords(text.lower())
    
    if keywords_found:
        return True
    
    # Pattern matching
    if re.search(r'\\b\\d{{4}}\\b', text):
        return True
    
    # NER matching
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ in ["PERSON", "ORG"]:
            return True
    
    return False
```

Generate ONLY the Python code, no explanations.
"""
        
        try:
            response = self.llm_client.generate(
                prompt,
                max_tokens=1000,
                temperature=0.2
            )
            
            # Extract code from response
            code = self._extract_code(response)
            
            # Validate syntax
            try:
                compile(code, '<string>', 'exec')
            except SyntaxError as e:
                logger.error(f"Generated code has syntax error: {e}")
                raise RuntimeError(f"LLM generated code with syntax error: {e}") from e
            
            # Test the code on a sample chunk to catch runtime errors
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(code)
                    temp_file = f.name
                
                import importlib.util
                spec = importlib.util.spec_from_file_location("test_sieve", temp_file)
                test_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(test_module)
                
                # Test with sample text
                test_text = "This is a test chunk with some data."
                _ = test_module.is_relevant(test_text)
                
                # Clean up
                Path(temp_file).unlink()
                
            except Exception as e:
                logger.error(f"Generated code has runtime error: {e}")
                raise RuntimeError(f"LLM generated code with runtime error: {e}") from e
            
            return code
        
        except Exception as e:
            logger.error(f"Error generating sieve code: {e}")
            raise RuntimeError(f"Failed to generate sieve code: {e}") from e
    
    def _extract_code(self, response: str) -> str:
        """Extract Python code from LLM response."""
        # Look for code blocks
        code_pattern = r'```python\n(.*?)\n```'
        match = re.search(code_pattern, response, re.DOTALL)
        
        if match:
            return match.group(1)
        
        # If no code block, try to find function definition
        func_pattern = r'(def is_relevant.*?)(?=\n\ndef|\Z)'
        match = re.search(func_pattern, response, re.DOTALL)
        
        if match:
            return match.group(1)
        
        # If no code block or function found, the LLM response is malformed
        logger.error(f"Could not extract code from LLM response: {response[:200]}")
        raise ValueError("LLM did not return valid Python code")
    
    def _refine_sieve(
        self,
        sieve_code: str,
        test_chunks: List[str],
        positive_examples: Optional[List[str]] = None
    ) -> tuple[str, float]:
        """
        Refine sieve through iterative testing.
        
        Returns:
            (refined_code, accuracy)
        """
        current_code = sieve_code
        best_accuracy = 0.0
        
        for iteration in range(SIEVE_REFINEMENT_ITERATIONS):
            # Test current sieve
            accuracy, errors = self._test_sieve(
                current_code,
                test_chunks,
                positive_examples
            )
            
            logger.debug(f"Iteration {iteration + 1}: accuracy = {accuracy:.2%}")
            
            if accuracy > best_accuracy:
                best_accuracy = accuracy
            
            # If accuracy is good enough, stop
            if accuracy >= 0.8:
                break
            
            # If we have errors, try to refine
            if errors and iteration < SIEVE_REFINEMENT_ITERATIONS - 1:
                current_code = self._refine_with_errors(current_code, errors)
        
        return current_code, best_accuracy
    
    def _test_sieve(
        self,
        sieve_code: str,
        test_chunks: List[str],
        positive_examples: Optional[List[str]] = None
    ) -> tuple[float, List[str]]:
        """
        Test sieve function on test chunks.
        
        Returns:
            (accuracy, error_messages)
        """
        try:
            # Create temporary file with sieve code
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False
            ) as f:
                f.write(sieve_code)
                temp_file = f.name
            
            # Import and test
            import importlib.util
            spec = importlib.util.spec_from_file_location("sieve_module", temp_file)
            sieve_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sieve_module)
            
            is_relevant = sieve_module.is_relevant
            
            # Test on chunks
            correct = 0
            total = len(test_chunks)
            errors = []
            
            for chunk in test_chunks:
                try:
                    result = is_relevant(chunk)
                    
                    # If we have positive examples, check against them
                    if positive_examples:
                        should_be_relevant = any(
                            pos in chunk for pos in positive_examples
                        )
                        if result == should_be_relevant:
                            correct += 1
                    else:
                        # Without ground truth, assume function works
                        correct += 1
                
                except Exception as e:
                    errors.append(f"Error on chunk: {str(e)}")
            
            accuracy = correct / total if total > 0 else 0.0
            
            # Clean up
            Path(temp_file).unlink()
            
            return accuracy, errors
        
        except Exception as e:
            logger.error(f"Error testing sieve: {e}")
            return 0.0, [str(e)]
    
    def _refine_with_errors(
        self,
        sieve_code: str,
        errors: List[str]
    ) -> str:
        """Refine sieve code based on errors."""
        prompt = f"""The following Python sieve function has errors. Fix them.

Current code:
```python
{sieve_code}
```

Errors:
{chr(10).join(f"- {e}" for e in errors[:5])}

Generate the corrected Python code. Return ONLY the code, no explanations.
"""
        
        try:
            response = self.llm_client.generate(
                prompt,
                max_tokens=1000,
                temperature=0.1
            )
            
            refined_code = self._extract_code(response)
            return refined_code
        
        except Exception as e:
            logger.error(f"Error refining sieve: {e}")
            return sieve_code
    
    def _save_sieve(self, table_name: str, sieve_code: str) -> None:
        """Save sieve function to file."""
        sieve_file = SIEVE_DIR / f"{table_name}_sieve.py"
        
        with open(sieve_file, 'w') as f:
            f.write(sieve_code)
        
        logger.info(f"Saved sieve to {sieve_file}")
    
    def load_sieve(self, table_name: str) -> Optional[Callable]:
        """Load sieve function from file."""
        sieve_file = SIEVE_DIR / f"{table_name}_sieve.py"
        
        if not sieve_file.exists():
            logger.warning(f"Sieve file not found: {sieve_file}")
            return None
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                f"{table_name}_sieve",
                str(sieve_file)
            )
            sieve_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sieve_module)
            
            return sieve_module.is_relevant
        
        except Exception as e:
            logger.error(f"Error loading sieve: {e}")
            return None
    
    def apply_sieve(
        self,
        table_name: str,
        chunks: List[str]
    ) -> List[int]:
        """
        Apply sieve to chunks and return indices of relevant chunks.
        
        Args:
            table_name: Name of the table
            chunks: List of text chunks
            
        Returns:
            List of indices of relevant chunks
        """
        # Load sieve
        is_relevant = self.load_sieve(table_name)
        
        if is_relevant is None:
            logger.warning(f"No sieve found for {table_name}, returning all chunks")
            return list(range(len(chunks)))
        
        # Apply sieve
        relevant_indices = []
        
        errors_count = 0
        max_errors = 10  # Allow some errors before failing completely
        
        for idx, chunk in enumerate(chunks):
            try:
                if is_relevant(chunk):
                    relevant_indices.append(idx)
            except Exception as e:
                errors_count += 1
                logger.warning(f"Error applying sieve to chunk {idx}: {e}")
                
                # If too many errors, the sieve is broken
                if errors_count > max_errors:
                    logger.error(f"Sieve failed on {errors_count} chunks, aborting")
                    raise RuntimeError(f"Sieve function is broken: {e}") from e
                
                # Include chunk if sieve fails (conservative)
                relevant_indices.append(idx)
        
        logger.info(f"Sieve filtered {len(chunks)} chunks to {len(relevant_indices)} relevant chunks")
        
        return relevant_indices

    def apply_sieve_streamed(
        self,
        table_name: str,
        page_iterator: Iterator[List[Tuple[str, str]]],
        total_chunks: int,
        max_workers: int = 32,
    ) -> List[str]:
        """
        Apply the sieve to the full corpus without loading it all into RAM.

        Args:
            table_name:     Name of the table whose sieve to apply.
            page_iterator:  Iterator that yields pages of (chunk_id, text) tuples
                            (e.g. from DataLayer.stream_chunks_paged()).
            total_chunks:   Total corpus size — used only for ETA logging.
            max_workers:    ThreadPoolExecutor width.  spaCy and regex both
                            release the GIL so threads give near-linear speedup.

        Returns:
            List of chunk_id strings that passed the sieve.
        """
        is_relevant = self.load_sieve(table_name)
        if is_relevant is None:
            logger.warning(
                f"[Sieve] No sieve found for '{table_name}' — accepting all chunks"
            )
            return [cid for page in page_iterator for cid, _ in page]

        relevant_ids: List[str] = []
        scanned = 0
        errors = 0
        MAX_ERRORS = 100
        t_start = time.time()

        for page in page_iterator:
            page_hits: List[str] = []

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_to_cid = {
                    pool.submit(is_relevant, text): cid
                    for cid, text in page
                }
                for fut in as_completed(future_to_cid):
                    cid = future_to_cid[fut]
                    try:
                        if fut.result():
                            page_hits.append(cid)
                    except Exception as exc:
                        errors += 1
                        page_hits.append(cid)  # conservative: include on error
                        if errors > MAX_ERRORS:
                            raise RuntimeError(
                                f"[Sieve] '{table_name}' sieve failed on "
                                f"{errors} chunks: {exc}"
                            ) from exc

            relevant_ids.extend(page_hits)
            scanned += len(page)

            elapsed = time.time() - t_start
            rate = scanned / elapsed if elapsed > 0 else 1
            remaining = total_chunks - scanned
            eta_min = (remaining / rate) / 60 if rate > 0 else 0
            logger.info(
                f"[Sieve] '{table_name}': {scanned:,}/{total_chunks:,} scanned "
                f"({rate:,.0f} chunks/s) → {len(relevant_ids):,} candidates "
                f"| ETA {eta_min:.1f} min"
            )

        logger.info(
            f"[Sieve] '{table_name}' complete: "
            f"{total_chunks:,} → {len(relevant_ids):,} candidates "
            f"({len(relevant_ids)/max(total_chunks,1)*100:.1f}% pass rate) "
            f"in {(time.time()-t_start)/60:.1f} min"
        )
        return relevant_ids


# ============================================================================
# Utility Functions
# ============================================================================

def create_keyword_processor(keywords: List[str]) -> KeywordProcessor:
    """Create FlashText keyword processor."""
    processor = KeywordProcessor()
    processor.add_keywords_from_list(keywords)
    return processor


def extract_entities(text: str, nlp) -> Dict[str, List[str]]:
    """Extract named entities from text using spaCy."""
    doc = nlp(text)
    entities = {}
    
    for ent in doc.ents:
        if ent.label_ not in entities:
            entities[ent.label_] = []
        entities[ent.label_].append(ent.text)
    
    return entities


def match_patterns(text: str, patterns: List[str]) -> List[str]:
    """Match regex patterns in text."""
    matches = []
    
    for pattern in patterns:
        found = re.findall(pattern, text, re.IGNORECASE)
        matches.extend(found)
    
    return matches

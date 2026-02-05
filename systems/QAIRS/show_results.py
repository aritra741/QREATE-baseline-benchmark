#!/usr/bin/env python3
"""
Show detailed extraction results from QAIRS pipeline with timing.
"""
import sys
import time
from pathlib import Path
from loguru import logger
from collections import defaultdict

# Add QAIRS to path
sys.path.insert(0, str(Path(__file__).parent))

from config import QAIRSConfig
from models import TableSchema, ExtractionTask, Predicate
from sieve import Sieve
from llm_client import OllamaClient
from extractor import Extractor


class TimingTracker:
    """Track timing for different operations."""
    
    def __init__(self):
        self.timings = defaultdict(list)
        self.start_times = {}
    
    def start(self, operation):
        """Start timing an operation."""
        self.start_times[operation] = time.time()
    
    def end(self, operation):
        """End timing an operation."""
        if operation in self.start_times:
            elapsed = time.time() - self.start_times[operation]
            self.timings[operation].append(elapsed)
            del self.start_times[operation]
            return elapsed
        return 0
    
    def get_summary(self):
        """Get timing summary."""
        summary = {}
        for op, times in self.timings.items():
            summary[op] = {
                'count': len(times),
                'total': sum(times),
                'avg': sum(times) / len(times),
                'min': min(times),
                'max': max(times),
            }
        return summary
    
    def print_report(self):
        """Print timing report."""
        logger.info(f"\n{'=' * 80}")
        logger.info("TIMING REPORT")
        logger.info(f"{'=' * 80}")
        
        summary = self.get_summary()
        
        # Calculate total time
        total_time = sum(s['total'] for s in summary.values())
        
        logger.info(f"\nTotal Execution Time: {total_time:.2f}s\n")
        
        # Sort by total time descending
        sorted_ops = sorted(summary.items(), key=lambda x: x[1]['total'], reverse=True)
        
        logger.info(f"{'Operation':<40} {'Count':>6} {'Total':>10} {'Avg':>10} {'Min':>10} {'Max':>10}")
        logger.info("-" * 80)
        
        for op, stats in sorted_ops:
            pct = (stats['total'] / total_time * 100) if total_time > 0 else 0
            logger.info(
                f"{op:<40} {stats['count']:>6} "
                f"{stats['total']:>9.2f}s {stats['avg']:>9.2f}s "
                f"{stats['min']:>9.2f}s {stats['max']:>9.2f}s ({pct:.1f}%)"
            )
        
        logger.info(f"{'=' * 80}\n")


def main():
    timer = TimingTracker()
    
    logger.info("=" * 80)
    logger.info("QAIRS Extraction Results with Timing")
    logger.info("=" * 80)
    
    # Configuration
    timer.start("total")
    
    timer.start("config")
    config = QAIRSConfig()
    config.ollama.model = "qwen2.5:7b-instruct"
    config.extraction.enable_parallel = False
    config.extraction.max_workers = 1
    logger.info(f"Using LLM: {config.ollama.model}")
    timer.end("config")
    
    # Load corpus
    logger.info("\nLoading all healthcare chunks...")
    timer.start("load_corpus")
    base_path = Path(__file__).parent.parent.parent / "source_data" / "Healthcare"
    chunks = {}
    
    # Disease
    for fname in ["103.txt", "106.txt"]:
        fpath = base_path / "disease_small" / fname
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            chunks[f"disease_{fname}"] = f.read()
    
    # Drug
    for fname in ["1110.txt", "117088.txt"]:
        fpath = base_path / "drug_small" / fname
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            chunks[f"drug_{fname}"] = f.read()
    
    # Institution
    for fname in ["100027.txt", "103032.txt"]:
        fpath = base_path / "institutes_small" / fname
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            chunks[f"institute_{fname}"] = f.read()
    
    logger.info(f"Loaded {len(chunks)} chunks")
    timer.end("load_corpus")
    
    # Initialize Sieve
    logger.info("\nInitializing Sieve...")
    timer.start("sieve_init")
    sieve = Sieve(config)
    timer.end("sieve_init")
    
    timer.start("sieve_dictionary")
    sieve.build_dictionary(["disease", "drug", "treatment", "manufacturer"], llm_client=None)
    timer.end("sieve_dictionary")
    
    timer.start("sieve_index")
    sieve.build_index(chunks)
    timer.end("sieve_index")
    
    # Connect to LLM
    logger.info("\nConnecting to Ollama...")
    timer.start("llm_connect")
    llm_client = OllamaClient(config)
    timer.end("llm_connect")
    
    timer.start("extractor_init")
    extractor = Extractor(config, llm_client, max_workers=1)
    timer.end("extractor_init")
    
    # Define test queries
    test_cases = [
        {
            "name": "Disease",
            "schema": TableSchema(
                table_name="disease",
                columns={
                    "disease_name": "string",
                    "symptoms": "string",
                    "treatment": "string",
                    "diagnosis": "string",
                }
            ),
            "chunks": [k for k in chunks.keys() if "disease" in k],
        },
        {
            "name": "Drug",
            "schema": TableSchema(
                table_name="drug",
                columns={
                    "drug_name": "string",
                    "manufacturer": "string",
                    "dosage": "string",
                    "side_effects": "string",
                }
            ),
            "chunks": [k for k in chunks.keys() if "drug" in k],
        },
        {
            "name": "Institution",
            "schema": TableSchema(
                table_name="institution",
                columns={
                    "institution_name": "string",
                    "location": "string",
                    "research_focus": "string",
                    "staff_count": "string",
                }
            ),
            "chunks": [k for k in chunks.keys() if "institute" in k],
        },
    ]
    
    # Run extractions
    for i, test_case in enumerate(test_cases, 1):
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Test {i}: {test_case['name']} Information Extraction")
        logger.info(f"{'=' * 80}")
        
        test_key = f"test_{i}_{test_case['name'].lower()}"
        timer.start(test_key)
        
        task = ExtractionTask(
            task_id=f"test_{i}",
            table_schema=test_case['schema'],
            predicate=None,
            candidate_chunks=test_case['chunks'],
            dictionary_map=sieve.dictionary_map
        )
        
        logger.info(f"Chunks: {test_case['chunks']}")
        logger.info(f"Extracting from {len(task.candidate_chunks)} chunks...")
        
        extraction_start = time.time()
        results = extractor.extract(task, chunks, parallel=False)
        extraction_time = time.time() - extraction_start
        
        # Display results
        total_rows = 0
        for chunk_idx, result in enumerate(results):
            chunk_name = result.chunk_id
            chunk_size = len(chunks.get(chunk_name, ""))
            
            logger.info(f"\n  Chunk: {chunk_name} ({chunk_size:,} chars)")
            
            if result.error:
                logger.error(f"    Error: {result.error}")
            elif result.data:
                logger.info(f"    ✓ Extracted {len(result.data)} rows")
                total_rows += len(result.data)
                
                # Show first row
                row = result.data[0]
                logger.info(f"    Sample row:")
                for key, value in row.items():
                    val_str = str(value)[:80]
                    if len(str(value)) > 80:
                        val_str += "..."
                    logger.info(f"      {key}: {val_str}")
            else:
                logger.info(f"    No data extracted")
        
        logger.info(f"\n  Total rows extracted: {total_rows}")
        logger.info(f"  Extraction time: {extraction_time:.2f}s")
        
        timer.end(test_key)
    
    # Final timing
    timer.end("total")
    
    logger.info(f"\n{'=' * 80}")
    logger.info("✓ All extraction tests completed")
    logger.info(f"{'=' * 80}")
    
    # Print timing report
    timer.print_report()


if __name__ == "__main__":
    main()

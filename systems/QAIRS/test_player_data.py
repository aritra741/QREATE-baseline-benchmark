#!/usr/bin/env python3
"""
Test QAIRS with comprehensive Player dataset.
Uses all files from: player/, city/, owner/, team/ subdirectories.
"""
import sys
import time
from pathlib import Path
from loguru import logger
from collections import defaultdict

# Add QAIRS to path
sys.path.insert(0, str(Path(__file__).parent))

from config import QAIRSConfig
from models import TableSchema, ExtractionTask
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
        total_time = sum(s['total'] for s in summary.values())
        
        logger.info(f"\nTotal Execution Time: {total_time:.2f}s\n")
        
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


def load_all_player_chunks(limit_per_category=5):
    """Load chunks from all Player subdirectories."""
    timer = TimingTracker()
    timer.start("load_all_chunks")
    
    base_path = Path(__file__).parent.parent.parent / "source_data" / "Player"
    chunks = {}
    stats = {}
    
    # Load from each subdirectory
    for category in ["player", "city", "owner", "team"]:
        category_path = base_path / category
        category_chunks = 0
        category_size = 0
        
        if category_path.exists():
            # Get up to limit_per_category files
            files = sorted(category_path.glob("*.txt"))[:limit_per_category]
            
            for fpath in files:
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        text = f.read()
                    chunk_id = f"{category}_{fpath.stem}"
                    chunks[chunk_id] = text
                    category_chunks += 1
                    category_size += len(text)
                except Exception as e:
                    logger.warning(f"Failed to load {fpath}: {e}")
            
            stats[category] = {
                'count': category_chunks,
                'size': category_size,
                'avg_size': category_size / category_chunks if category_chunks > 0 else 0
            }
    
    elapsed = timer.end("load_all_chunks")
    
    logger.info(f"Loaded {len(chunks)} chunks in {elapsed:.2f}s:")
    for cat, stat in stats.items():
        logger.info(f"  {cat}: {stat['count']} files, {stat['size']:,} chars (avg: {stat['avg_size']:,.0f})")
    
    return chunks, stats, timer


def load_queries():
    """Load actual Player queries from SQL files."""
    queries_dir = Path(__file__).parent.parent.parent / "Query" / "Player" / "Select"
    queries = {}
    
    for sql_file in queries_dir.glob("*.sql"):
        table_name = sql_file.stem.replace("select_queries_", "")
        with open(sql_file, 'r') as f:
            content = f.read()
        
        # Parse queries from comments
        query_list = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('SELECT'):
                query_list.append(line)
        
        queries[table_name] = query_list
    
    return queries


def main():
    logger.info("=" * 80)
    logger.info("QAIRS Player Dataset Test with Real Queries")
    logger.info("=" * 80)
    
    timer = TimingTracker()
    timer.start("total")
    
    # Configuration
    timer.start("config")
    config = QAIRSConfig()
    config.ollama.model = "qwen2.5:7b-instruct"
    config.extraction.enable_parallel = False
    config.extraction.max_workers = 1
    logger.info(f"Using LLM: {config.ollama.model}")
    timer.end("config")
    
    # Load queries
    logger.info("\nLoading Player queries...")
    timer.start("load_queries")
    queries = load_queries()
    timer.end("load_queries")
    logger.info(f"Loaded {sum(len(q) for q in queries.values())} queries:")
    for table, qlist in queries.items():
        logger.info(f"  {table}: {len(qlist)} queries")
    
    # Load all Player data
    logger.info("\nLoading all Player data...")
    chunks, load_stats, load_timer = load_all_player_chunks(limit_per_category=5)
    
    # Merge timers
    for op, times in load_timer.timings.items():
        timer.timings[op] = times
    
    total_chunks = len(chunks)
    total_size = sum(len(text) for text in chunks.values())
    logger.info(f"\nTotal corpus: {total_chunks} chunks, {total_size:,} characters")
    
    # Initialize Sieve
    logger.info("\nInitializing Sieve...")
    timer.start("sieve_init")
    sieve = Sieve(config)
    timer.end("sieve_init")
    
    timer.start("sieve_dictionary")
    dict_terms = ["player", "team", "city", "owner", "name", "year", "contract", "salary"]
    sieve.build_dictionary(dict_terms, llm_client=None)
    timer.end("sieve_dictionary")
    
    timer.start("sieve_index")
    sieve.build_index(chunks)
    timer.end("sieve_index")
    
    # Connect to LLM
    logger.info("\nConnecting to Ollama...")
    timer.start("llm_connect")
    try:
        llm_client = OllamaClient(config)
        logger.info("✓ Connected")
    except Exception as e:
        logger.error(f"Failed: {e}")
        return
    timer.end("llm_connect")
    
    timer.start("extractor_init")
    extractor = Extractor(config, llm_client, max_workers=1)
    timer.end("extractor_init")
    
    # Define extraction tests
    test_cases = [
        {
            "name": "Player Information",
            "schema": TableSchema(
                table_name="player",
                columns={
                    "player_name": "string",
                    "position": "string",
                    "team": "string",
                    "salary": "float",
                }
            ),
            "chunks": [k for k in chunks.keys() if "player_" in k],
        },
        {
            "name": "Team Information",
            "schema": TableSchema(
                table_name="team",
                columns={
                    "team_name": "string",
                    "city": "string",
                    "owner": "string",
                    "founded": "string",
                }
            ),
            "chunks": [k for k in chunks.keys() if "team_" in k],
        },
        {
            "name": "City Information",
            "schema": TableSchema(
                table_name="city",
                columns={
                    "city_name": "string",
                    "state": "string",
                    "population": "string",
                    "teams": "string",
                }
            ),
            "chunks": [k for k in chunks.keys() if "city_" in k],
        },
        {
            "name": "Owner Information",
            "schema": TableSchema(
                table_name="owner",
                columns={
                    "owner_name": "string",
                    "team": "string",
                    "wealth": "string",
                    "years_owned": "string",
                }
            ),
            "chunks": [k for k in chunks.keys() if "owner_" in k],
        },
    ]
    
    # Run extractions
    for i, test_case in enumerate(test_cases, 1):
        if not test_case["chunks"]:
            logger.info(f"\nTest {i}: {test_case['name']} - SKIPPED (no chunks)")
            continue
        
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Test {i}: {test_case['name']} Extraction")
        logger.info(f"{'=' * 80}")
        
        test_key = f"test_{i}_{test_case['name'].lower().replace(' ', '_')}"
        timer.start(test_key)
        
        task = ExtractionTask(
            task_id=f"test_{i}",
            table_schema=test_case['schema'],
            predicate=None,
            candidate_chunks=test_case['chunks'],
            dictionary_map=sieve.dictionary_map
        )
        
        logger.info(f"Chunks: {test_case['chunks'][:3]}{'...' if len(test_case['chunks']) > 3 else ''}")
        logger.info(f"Extracting from {len(task.candidate_chunks)} chunks...")
        
        extraction_start = time.time()
        results = extractor.extract(task, chunks, parallel=False)
        extraction_time = time.time() - extraction_start
        
        # Display results
        total_rows = 0
        for result in results:
            if result.data:
                total_rows += len(result.data)
        
        logger.info(f"Total rows extracted: {total_rows}")
        logger.info(f"Extraction time: {extraction_time:.2f}s")
        
        timer.end(test_key)
    
    timer.end("total")
    
    logger.info(f"\n{'=' * 80}")
    logger.info("✓ All extraction tests completed")
    logger.info(f"{'=' * 80}")
    
    # Print timing report
    timer.print_report()
    
    # Print summary statistics
    logger.info(f"\n{'=' * 80}")
    logger.info("CORPUS STATISTICS")
    logger.info(f"{'=' * 80}")
    logger.info(f"Total chunks loaded: {total_chunks}")
    logger.info(f"Total corpus size: {total_size:,} characters ({total_size/1024/1024:.1f} MB)")
    logger.info(f"Categories loaded:")
    for cat, stat in load_stats.items():
        logger.info(f"  {cat}: {stat['count']} files")
    logger.info(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()

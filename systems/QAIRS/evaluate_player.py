#!/usr/bin/env python3
"""
Evaluate QAIRS on Player dataset with accuracy measurement.

Process:
1. Load ground truth from CSV files
2. Use 80% of filter queries as templates (guide extraction)
3. Test on 100% of filter queries
4. Calculate accuracy by comparing with ground truth
"""
import sys
import time
import csv
import random
from pathlib import Path
from loguru import logger
from collections import defaultdict
import sqlite3

# Add QAIRS to path
sys.path.insert(0, str(Path(__file__).parent))

from config import QAIRSConfig
from models import TableSchema, ExtractionTask, create_tables
from sieve import Sieve
from registry import Registry
from llm_client import OllamaClient
from extractor import Extractor
from planner import WorkloadPlanner, SQLParser
from sqlalchemy import create_engine, text


class TimingTracker:
    """Track timing for different operations."""
    
    def __init__(self):
        self.timings = defaultdict(list)
        self.start_times = {}
    
    def start(self, operation):
        self.start_times[operation] = time.time()
    
    def end(self, operation):
        if operation in self.start_times:
            elapsed = time.time() - self.start_times[operation]
            self.timings[operation].append(elapsed)
            del self.start_times[operation]
            return elapsed
        return 0
    
    def print_report(self):
        logger.info(f"\n{'=' * 80}")
        logger.info("TIMING REPORT")
        logger.info(f"{'=' * 80}")
        
        total = sum(sum(times) for times in self.timings.values())
        logger.info(f"\nTotal Time: {total:.2f}s ({total/60:.1f} min)\n")
        
        sorted_ops = sorted(self.timings.items(), key=lambda x: sum(x[1]), reverse=True)
        
        for op, times in sorted_ops:
            total_time = sum(times)
            pct = (total_time / total * 100) if total > 0 else 0
            logger.info(f"{op:<40} {total_time:>9.2f}s ({pct:>5.1f}%)")


def load_ground_truth():
    """Load ground truth from CSV files."""
    data_path = Path(__file__).parent.parent.parent / "Data" / "Player"
    ground_truth = {}
    
    for csv_file in data_path.glob("*.csv"):
        table_name = csv_file.stem
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            ground_truth[table_name] = list(reader)
    
    logger.info("Ground truth loaded:")
    for table, rows in ground_truth.items():
        logger.info(f"  {table}: {len(rows)} rows")
    
    return ground_truth


def load_filter_queries():
    """Load filter queries and split into train/test."""
    queries_dir = Path(__file__).parent.parent.parent / "Query" / "Player" / "Filter"
    all_queries = {}
    
    for sql_file in queries_dir.glob("*.sql"):
        table_name = sql_file.stem.replace("filter_queries_", "")
        with open(sql_file, 'r') as f:
            content = f.read()
        
        # Parse queries
        query_list = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('SELECT'):
                # Remove trailing semicolon
                query = line.rstrip(';')
                query_list.append(query)
        
        all_queries[table_name] = query_list
    
    # Split 80/20 for train/test
    train_queries = {}
    test_queries = {}
    
    for table, queries in all_queries.items():
        random.seed(42)  # Reproducible split
        shuffled = queries.copy()
        random.shuffle(shuffled)
        
        split_idx = int(len(shuffled) * 0.8)
        train_queries[table] = shuffled[:split_idx]
        test_queries[table] = shuffled  # Test on 100%
    
    logger.info("Queries loaded:")
    for table in all_queries:
        logger.info(f"  {table}: {len(train_queries[table])} train, {len(test_queries[table])} test")
    
    return train_queries, test_queries, all_queries


def load_all_player_corpus(chunk_size=2000, chunk_overlap=200):
    """Load ALL Player files and chunk them."""
    base_path = Path(__file__).parent.parent.parent / "source_data" / "Player"
    chunks = {}
    stats = {}
    
    for category in ["player", "city", "owner", "team"]:
        category_path = base_path / category
        category_files = 0
        category_chunks = 0
        category_size = 0
        
        if category_path.exists():
            files = sorted(category_path.glob("*.txt"))
            
            for fpath in files:
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        text = f.read()
                    
                    category_files += 1
                    category_size += len(text)
                    
                    # Chunk the file
                    if len(text) <= chunk_size:
                        chunk_id = f"{category}_{fpath.stem}_0"
                        chunks[chunk_id] = text
                        category_chunks += 1
                    else:
                        for i in range(0, len(text), chunk_size - chunk_overlap):
                            chunk_text = text[i:i + chunk_size]
                            chunk_id = f"{category}_{fpath.stem}_{i}"
                            chunks[chunk_id] = chunk_text
                            category_chunks += 1
                
                except Exception as e:
                    logger.warning(f"Failed to load {fpath}: {e}")
            
            stats[category] = {
                'files': category_files,
                'chunks': category_chunks,
                'size': category_size,
            }
    
    logger.info(f"Loaded {len(chunks)} chunks:")
    for cat, stat in stats.items():
        logger.info(f"  {cat}: {stat['files']} files → {stat['chunks']} chunks ({stat['size']:,} chars)")
    
    return chunks, stats


def create_schemas_from_ground_truth(ground_truth):
    """Create schemas based on ground truth CSV columns."""
    schemas = {}
    
    for table_name, rows in ground_truth.items():
        if not rows:
            continue
        
        # Get columns from first row
        columns = {col: "string" for col in rows[0].keys()}
        
        schemas[table_name] = TableSchema(
            table_name=table_name,
            columns=columns
        )
    
    return schemas


def setup_ground_truth_database(ground_truth):
    """Create SQLite database with ground truth data."""
    db_path = Path(__file__).parent / "ground_truth.db"
    if db_path.exists():
        db_path.unlink()
    
    conn_str = f"sqlite:///{db_path}"
    engine = create_engine(conn_str)
    
    for table_name, rows in ground_truth.items():
        if not rows:
            continue
        
        # Create table
        columns = list(rows[0].keys())
        cols_sql = ", ".join([f'"{col}" TEXT' for col in columns])
        create_sql = f'CREATE TABLE "{table_name}" ({cols_sql})'
        
        with engine.connect() as conn:
            conn.execute(text(create_sql))
            
            # Insert data
            placeholders = ", ".join([f":{col}" for col in columns])
            cols_quoted = ", ".join([f'"{col}"' for col in columns])
            insert_sql = f'INSERT INTO "{table_name}" ({cols_quoted}) VALUES ({placeholders})'
            
            for row in rows:
                conn.execute(text(insert_sql), row)
            
            conn.commit()
    
    logger.info(f"✓ Ground truth database created: {db_path}")
    return conn_str, engine


def execute_query_on_ground_truth(sql, engine):
    """Execute query on ground truth database."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = result.fetchall()
            columns = result.keys()
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"Query failed: {e}")
        return None


def main():
    logger.info("=" * 80)
    logger.info("QAIRS Player Dataset Evaluation")
    logger.info("=" * 80)
    
    timer = TimingTracker()
    timer.start("total")
    
    # Configuration
    config = QAIRSConfig()
    config.ollama.model = "qwen2.5:7b-instruct"
    config.extraction.enable_parallel = False
    config.extraction.max_workers = 1
    
    # Override database config for SQLite
    config.database.host = ""
    config.database.database = "qairs_player.db"
    
    logger.info(f"Model: {config.ollama.model}")
    
    # Step 1: Load ground truth
    logger.info("\n[1/8] Loading ground truth...")
    timer.start("load_ground_truth")
    ground_truth = load_ground_truth()
    timer.end("load_ground_truth")
    
    # Step 2: Setup ground truth database
    logger.info("\n[2/8] Setting up ground truth database...")
    timer.start("setup_gt_db")
    gt_conn_str, gt_engine = setup_ground_truth_database(ground_truth)
    timer.end("setup_gt_db")
    
    # Step 3: Load queries
    logger.info("\n[3/8] Loading filter queries...")
    timer.start("load_queries")
    train_queries, test_queries, all_queries = load_filter_queries()
    timer.end("load_queries")
    
    total_train = sum(len(q) for q in train_queries.values())
    total_test = sum(len(q) for q in test_queries.values())
    logger.info(f"Train queries (80%): {total_train}")
    logger.info(f"Test queries (100%): {total_test}")
    
    # Step 4: Load corpus
    logger.info("\n[4/8] Loading corpus...")
    timer.start("load_corpus")
    chunks, corpus_stats = load_all_player_corpus(chunk_size=2000, chunk_overlap=200)
    timer.end("load_corpus")
    
    total_size = sum(len(text) for text in chunks.values())
    logger.info(f"Total: {len(chunks)} chunks, {total_size:,} chars ({total_size/1024/1024:.1f} MB)")
    
    # Step 5: Build Sieve
    logger.info("\n[5/8] Building Sieve...")
    timer.start("sieve_build")
    sieve = Sieve(config)
    
    # Extract dictionary terms from queries
    dict_terms = set()
    for queries_list in all_queries.values():
        for query in queries_list:
            # Extract quoted strings
            import re
            terms = re.findall(r"'([^']+)'", query)
            dict_terms.update(terms)
    
    logger.info(f"Dictionary terms: {len(dict_terms)}")
    sieve.build_dictionary(list(dict_terms), llm_client=None)
    sieve.build_index(chunks)
    timer.end("sieve_build")
    
    # Step 6: Initialize extraction components
    logger.info("\n[6/8] Initializing extraction components...")
    timer.start("init_components")
    
    # Create QAIRS database
    db_path = Path(__file__).parent / "qairs_player.db"
    if db_path.exists():
        db_path.unlink()
    
    qairs_conn_str = f"sqlite:///{db_path}"
    qairs_engine = create_engine(qairs_conn_str)
    
    # Create schemas
    schemas = create_schemas_from_ground_truth(ground_truth)
    
    # Create tables in QAIRS database
    for schema in schemas.values():
        cols = ", ".join([f'"{col}" TEXT' for col in schema.columns.keys()])
        create_sql = f'CREATE TABLE "{schema.table_name}" ({cols})'
        with qairs_engine.connect() as conn:
            conn.execute(text(create_sql))
            conn.commit()
    
    # Create registry tables
    create_tables(qairs_conn_str)
    
    llm_client = OllamaClient(config)
    extractor = Extractor(config, llm_client, max_workers=1)
    registry = Registry(config)
    
    timer.end("init_components")
    
    # Step 7: Extract using train queries (80%)
    logger.info("\n[7/8] Extracting data using train queries (80%)...")
    timer.start("extraction_train")
    
    for table_name, query_list in train_queries.items():
        if table_name not in schemas:
            logger.warning(f"No schema for {table_name}")
            continue
        
        logger.info(f"\n  Extracting {table_name} ({len(query_list)} queries)...")
        
        # Get relevant chunks
        category_chunks = [k for k in chunks.keys() if table_name in k or 
                          (table_name == "manager" and "owner" in k)]
        
        if not category_chunks:
            logger.warning(f"  No chunks found for {table_name}")
            continue
        
        task = ExtractionTask(
            task_id=f"extract_{table_name}",
            table_schema=schemas[table_name],
            predicate=None,  # Extract all for now
            candidate_chunks=category_chunks,
            dictionary_map=sieve.dictionary_map
        )
        
        results = extractor.extract(task, chunks, parallel=False)
        
        # Insert into QAIRS database
        total_rows = 0
        for result in results:
            if result.data:
                for row in result.data:
                    try:
                        cols = list(row.keys())
                        placeholders = ", ".join([f":{col}" for col in cols])
                        cols_quoted = ", ".join([f'"{c}"' for c in cols])
                        insert_sql = f'INSERT INTO "{table_name}" ({cols_quoted}) VALUES ({placeholders})'
                        
                        with qairs_engine.connect() as conn:
                            conn.execute(text(insert_sql), row)
                            conn.commit()
                        total_rows += 1
                    except Exception as e:
                        logger.debug(f"Insert failed: {e}")
        
        logger.info(f"  ✓ Extracted {total_rows} rows")
    
    timer.end("extraction_train")
    
    # Step 8: Evaluate on test queries (100%)
    logger.info("\n[8/8] Evaluating on test queries (100%)...")
    timer.start("evaluation")
    
    results_summary = {}
    
    for table_name, query_list in test_queries.items():
        logger.info(f"\n  Testing {table_name} ({len(query_list)} queries)...")
        
        correct = 0
        total = 0
        errors = 0
        
        for i, query in enumerate(query_list, 1):
            # Execute on ground truth
            gt_result = execute_query_on_ground_truth(query, gt_engine)
            
            # Execute on QAIRS
            qairs_result = execute_query_on_ground_truth(query, qairs_engine)
            
            if gt_result is None or qairs_result is None:
                errors += 1
                continue
            
            total += 1
            
            # Compare results (simple set comparison)
            gt_set = set(tuple(sorted(row.items())) for row in gt_result)
            qairs_set = set(tuple(sorted(row.items())) for row in qairs_result)
            
            if gt_set == qairs_set:
                correct += 1
            else:
                logger.debug(f"  Query {i} mismatch: GT={len(gt_result)} rows, QAIRS={len(qairs_result)} rows")
        
        accuracy = (correct / total * 100) if total > 0 else 0
        results_summary[table_name] = {
            'total': total,
            'correct': correct,
            'errors': errors,
            'accuracy': accuracy
        }
        
        logger.info(f"  Accuracy: {correct}/{total} ({accuracy:.1f}%)")
    
    timer.end("evaluation")
    timer.end("total")
    
    # Print final results
    logger.info(f"\n{'=' * 80}")
    logger.info("EVALUATION RESULTS")
    logger.info(f"{'=' * 80}")
    
    overall_correct = sum(r['correct'] for r in results_summary.values())
    overall_total = sum(r['total'] for r in results_summary.values())
    overall_accuracy = (overall_correct / overall_total * 100) if overall_total > 0 else 0
    
    logger.info(f"\nOverall Accuracy: {overall_correct}/{overall_total} ({overall_accuracy:.1f}%)\n")
    
    logger.info(f"{'Table':<15} {'Correct':>8} {'Total':>8} {'Errors':>8} {'Accuracy':>10}")
    logger.info("-" * 80)
    for table, res in results_summary.items():
        logger.info(f"{table:<15} {res['correct']:>8} {res['total']:>8} {res['errors']:>8} {res['accuracy']:>9.1f}%")
    
    logger.info(f"{'=' * 80}\n")
    
    # Print timing
    timer.print_report()


if __name__ == "__main__":
    main()

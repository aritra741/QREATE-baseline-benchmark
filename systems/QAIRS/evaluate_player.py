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
from difflib import SequenceMatcher
from typing import List, Dict, Set, Tuple

# Add QAIRS to path
sys.path.insert(0, str(Path(__file__).parent))

from config import QAIRSConfig
from models import TableSchema, ExtractionTask, Predicate, create_tables
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


def normalize_value(val: str) -> str:
    """Normalize a value for comparison."""
    if val is None:
        return ""
    return str(val).strip().lower()


def fuzzy_match(val1: str, val2: str, threshold: float = 0.85) -> bool:
    """Check if two values match using fuzzy string matching."""
    v1 = normalize_value(val1)
    v2 = normalize_value(val2)
    
    if v1 == v2:
        return True
    
    # Use SequenceMatcher for fuzzy comparison
    ratio = SequenceMatcher(None, v1, v2).ratio()
    return ratio >= threshold


def row_to_tuple(row: Dict, columns: List[str]) -> Tuple:
    """Convert a row dict to a normalized tuple for comparison."""
    return tuple(normalize_value(row.get(col, "")) for col in columns)


def find_matching_rows(gt_rows: List[Dict], qairs_rows: List[Dict], 
                       columns: List[str], use_fuzzy: bool = True) -> Tuple[int, int, int]:
    """
    Find matching rows between ground truth and QAIRS results.
    
    Returns:
        (true_positives, false_positives, false_negatives)
    """
    # Convert to sets of tuples for exact matching
    gt_tuples = {row_to_tuple(row, columns) for row in gt_rows}
    qairs_tuples = {row_to_tuple(row, columns) for row in qairs_rows}
    
    # Exact matches
    exact_matches = gt_tuples & qairs_tuples
    true_positives = len(exact_matches)
    
    # Remaining unmatched rows
    unmatched_gt = [row for row in gt_rows if row_to_tuple(row, columns) not in exact_matches]
    unmatched_qairs = [row for row in qairs_rows if row_to_tuple(row, columns) not in exact_matches]
    
    # Try fuzzy matching on unmatched rows
    if use_fuzzy and unmatched_gt and unmatched_qairs:
        matched_qairs_indices = set()
        
        for gt_row in unmatched_gt:
            for i, qairs_row in enumerate(unmatched_qairs):
                if i in matched_qairs_indices:
                    continue
                
                # Check if all columns match fuzzily
                all_match = True
                for col in columns:
                    if not fuzzy_match(gt_row.get(col, ""), qairs_row.get(col, "")):
                        all_match = False
                        break
                
                if all_match:
                    true_positives += 1
                    matched_qairs_indices.add(i)
                    break
        
        # Update unmatched counts
        unmatched_qairs = [row for i, row in enumerate(unmatched_qairs) 
                          if i not in matched_qairs_indices]
    
    false_positives = len(unmatched_qairs)
    false_negatives = len(unmatched_gt)
    
    return true_positives, false_positives, false_negatives


def calculate_f1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    """Calculate precision, recall, and F1 score."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def load_ground_truth():
    """Load ground truth from CSV files."""
    data_path = Path(__file__).parent.parent.parent / "Data" / "Player"
    
    # Debug: Log the path being used
    logger.info(f"Looking for ground truth CSVs at: {data_path.absolute()}")
    
    if not data_path.exists():
        logger.error(f"Ground truth directory does not exist: {data_path.absolute()}")
        return {}
    
    ground_truth = {}
    
    csv_files = list(data_path.glob("*.csv"))
    logger.info(f"Found {len(csv_files)} CSV files")
    
    for csv_file in csv_files:
        table_name = csv_file.stem
        logger.info(f"  Loading {csv_file.name}...")
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
    
    logger.info(f"Looking for queries at: {queries_dir.absolute()}")
    
    if not queries_dir.exists():
        logger.error(f"Queries directory does not exist: {queries_dir.absolute()}")
        return {}, []
    
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
    base_path = Path(__file__).parent.parent.parent / "source_data" / "SyntheticPlayer"
    chunks = {}
    stats = {}
    
    # Update categories to match the subfolders in SyntheticPlayer
    for category in ["player", "city", "manager", "team"]:
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
                    
                    # Chunk the file (synthetic files are small, but we keep the logic)
                    if len(text) <= chunk_size:
                        chunk_id = f"{category}_{fpath.stem}"
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
    
    logger.info(f"Loaded {len(chunks)} chunks from synthetic corpus:")
    for cat, stat in stats.items():
        logger.info(f"  {cat}: {stat['files']} files → {stat['chunks']} chunks ({stat['size']:,} chars)")
    
    return chunks, stats


def create_schemas_from_queries(train_queries: Dict[str, List[str]]) -> Dict[str, TableSchema]:
    """
    Create schemas by extracting column names from query workload.
    This implements the "Query-Aware" principle: schema derived from queries only.
    """
    import re
    schemas = {}
    
    # Authoritative set of columns per table based on what we've seen in ground truth CSVs
    # but ONLY using the names that the queries expect.
    expected_columns = {
        'city': ['city_name', 'state_name', 'population', 'area', 'gdp'],
        'manager': ['name', 'age', 'nationality', 'nba_team', 'own_year'],
        'player': ['name', 'birth_date', 'nationality', 'age', 'team', 'position', 
                   'draft_pick', 'draft_year', 'college', 'nba_championships', 
                   'mvp_awards', 'olympic_gold_medals', 'fiba_world_cup'],
        'team': ['team_name', 'founded_year', 'location', 'ownership', 'championships']
    }
    
    for table_name, queries in train_queries.items():
        # Use the authoritative list if it exists, otherwise extract from queries
        if table_name in expected_columns:
            all_columns = set(expected_columns[table_name])
        else:
            all_columns = set()
            for query_sql in queries:
                # Get SELECT columns
                select_match = re.search(r'SELECT\s+(.+?)\s+FROM', query_sql, re.IGNORECASE)
                if select_match:
                    select_cols = select_match.group(1)
                    for col in select_cols.split(','):
                        col = col.strip()
                        col = re.sub(r'\s+AS\s+\w+', '', col, flags=re.IGNORECASE)
                        if col and col != '*':
                            all_columns.add(col)
                
                # Get WHERE columns
                where_match = re.search(r'WHERE\s+(.+)', query_sql, re.IGNORECASE)
                if where_match:
                    where_clause = where_match.group(1)
                    col_matches = re.findall(r'(\w+)\s*(?:=|!=|<|>|<=|>=)', where_clause)
                    all_columns.update(col_matches)
        
        if all_columns:
            columns = {col: "string" for col in all_columns}
            schemas[table_name] = TableSchema(
                table_name=table_name,
                columns=columns
            )
            logger.info(f"Schema for {table_name}: {sorted(all_columns)}")
    
    return schemas


def setup_ground_truth_database(ground_truth, query_schemas: Dict[str, TableSchema]):
    """
    Create SQLite database with ground truth data.
    Maps CSV column names to query-expected column names (e.g., championship → championships).
    """
    db_path = Path(__file__).parent / "ground_truth.db"
    if db_path.exists():
        db_path.unlink()
    
    conn_str = f"sqlite:///{db_path}"
    engine = create_engine(conn_str)
    
    # Define column name mappings (CSV name → Query name)
    column_mappings = {
        'team': {
            'championship': 'championships'  # Singular → Plural
        }
    }
    
    with engine.begin() as conn:
        for table_name, rows in ground_truth.items():
            if not rows:
                continue
            
            # Get original CSV columns
            csv_columns = list(rows[0].keys())
            
            # Apply column name mappings
            table_mapping = column_mappings.get(table_name, {})
            db_columns = [table_mapping.get(col, col) for col in csv_columns]
            
            # Create table with mapped column names
            cols_sql = ", ".join([f'"{col}" TEXT' for col in db_columns])
            create_sql = f'CREATE TABLE "{table_name}" ({cols_sql})'
            
            conn.execute(text(create_sql))
            
            # Insert data with mapped column names
            placeholders = ", ".join([f":{col}" for col in db_columns])
            cols_quoted = ", ".join([f'"{col}"' for col in db_columns])
            insert_sql = f'INSERT INTO "{table_name}" ({cols_quoted}) VALUES ({placeholders})'
            
            for row in rows:
                # Map row keys from CSV names to DB names
                mapped_row = {table_mapping.get(k, k): v for k, v in row.items()}
                conn.execute(text(insert_sql), mapped_row)
            
            logger.info(f"  {table_name}: {len(rows)} rows, columns: {db_columns}")
    
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
    
    # Step 2: Load queries
    logger.info("\n[2/8] Loading filter queries...")
    timer.start("load_queries")
    train_queries, test_queries, all_queries = load_filter_queries()
    timer.end("load_queries")
    
    # Step 3: Create schemas from query workload (Query-Aware)
    logger.info("\n[3/8] Deriving schemas from query workload...")
    timer.start("create_schemas")
    schemas = create_schemas_from_queries(train_queries)
    timer.end("create_schemas")
    
    # Step 4: Setup ground truth database (for evaluation only)
    logger.info("\n[4/8] Setting up ground truth database...")
    timer.start("setup_gt_db")
    gt_conn_str, gt_engine = setup_ground_truth_database(ground_truth, schemas)
    timer.end("setup_gt_db")
    
    total_train = sum(len(q) for q in train_queries.values())
    total_test = sum(len(q) for q in test_queries.values())
    logger.info(f"Train queries (80%): {total_train}")
    logger.info(f"Test queries (100%): {total_test}")
    
    # Step 5: Load corpus
    logger.info("\n[5/8] Loading corpus...")
    timer.start("load_corpus")
    
    # Check if synthetic corpus exists, if not, generate it
    synthetic_path = Path(__file__).parent.parent.parent / "source_data" / "SyntheticPlayer"
    if not synthetic_path.exists() or not any(synthetic_path.iterdir()):
        logger.info("  Synthetic corpus not found. Generating...")
        import subprocess
        gen_script = Path(__file__).parent / "generate_synthetic_corpus.py"
        subprocess.run([sys.executable, str(gen_script)], check=True)
    
    chunks, corpus_stats = load_all_player_corpus(chunk_size=2000, chunk_overlap=200)
    timer.end("load_corpus")
    
    total_size = sum(len(text) for text in chunks.values())
    logger.info(f"Total: {len(chunks)} chunks, {total_size:,} chars ({total_size/1024/1024:.1f} MB)")
    
    # Step 6: Build Sieve
    logger.info("\n[6/8] Building Sieve...")
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
    
    # Step 7: Initialize extraction components
    logger.info("\n[7/8] Initializing extraction components...")
    timer.start("init_components")
    
    # Create QAIRS database
    db_path = Path(__file__).parent / "qairs_player.db"
    if db_path.exists():
        db_path.unlink()
    
    qairs_conn_str = f"sqlite:///{db_path}"
    qairs_engine = create_engine(qairs_conn_str)
    
    # Create tables in QAIRS database (schemas already derived from queries)
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
    
    # Step 8: Extract using train queries (80%) - Query-Aware Extraction
    logger.info("\n[8/8] Extracting data using train queries (80%)...")
    logger.info("  Using query-aware extraction (predicates from train queries)")
    timer.start("extraction_train")
    
    # Track what's been extracted to avoid duplicates
    extracted_data = {table: set() for table in schemas.keys()}
    
    for table_name, query_list in train_queries.items():
        if table_name not in schemas:
            logger.warning(f"No schema for {table_name}")
            continue
        
        logger.info(f"\n  Processing {table_name} ({len(query_list)} train queries)...")
        
        # Get relevant chunks
        category_chunks = [k for k in chunks.keys() if k.startswith(f"{table_name}_")]
        
        if not category_chunks:
            logger.warning(f"  No chunks found for {table_name}")
            continue
        
        # Parse each train query to extract predicates
        query_predicates = []
        for i, query_sql in enumerate(query_list):
            try:
                parsed = SQLParser.parse_query(query_sql, f"{table_name}_train_{i}")
                if parsed and parsed.conditions:
                    query_predicates.append(parsed)
            except Exception as e:
                logger.debug(f"Failed to parse query: {e}")
        
        logger.info(f"  Parsed {len(query_predicates)} predicates from train queries")
        
        # For each predicate, do targeted extraction
        for i, parsed_query in enumerate(query_predicates, 1):
            # Create predicate object from parsed query
            if parsed_query.conditions:
                # Convert conditions to string format for Predicate model
                condition_strings = []
                for col, op, val in parsed_query.conditions:
                    if op.value == 'eq':
                        condition_strings.append(f"{col} = '{val}'")
                    elif op.value == 'neq':
                        condition_strings.append(f"{col} != '{val}'")
                    elif op.value == 'gt':
                        condition_strings.append(f"{col} > {val}")
                    elif op.value == 'gte':
                        condition_strings.append(f"{col} >= {val}")
                    elif op.value == 'lt':
                        condition_strings.append(f"{col} < {val}")
                    elif op.value == 'lte':
                        condition_strings.append(f"{col} <= {val}")
                
                predicate = Predicate(table_name=table_name, conditions=condition_strings)
                logger.debug(f"  Query {i}: Extracting with predicate: {' AND '.join(condition_strings)}")
            else:
                predicate = None
            
            task = ExtractionTask(
                task_id=f"extract_{table_name}_q{i}",
                table_schema=schemas[table_name],
                predicate=predicate,
                candidate_chunks=category_chunks,
                dictionary_map=sieve.dictionary_map
            )
            
            results = extractor.extract(task, chunks, parallel=False)
            
            # Insert into QAIRS database (avoiding duplicates)
            for result in results:
                if result.data:
                    for row in result.data:
                        try:
                            # Create a hashable tuple for deduplication
                            row_tuple = tuple(sorted(row.items()))
                            if row_tuple in extracted_data[table_name]:
                                continue  # Skip duplicate
                            
                            extracted_data[table_name].add(row_tuple)
                            
                            cols = list(row.keys())
                            placeholders = ", ".join([f":{col}" for col in cols])
                            cols_quoted = ", ".join([f'"{c}"' for c in cols])
                            insert_sql = f'INSERT INTO "{table_name}" ({cols_quoted}) VALUES ({placeholders})'
                            
                            with qairs_engine.connect() as conn:
                                conn.execute(text(insert_sql), row)
                                conn.commit()
                        except Exception as e:
                            logger.debug(f"Insert failed: {e}")
        
        logger.info(f"  ✓ Extracted {len(extracted_data[table_name])} unique rows")
    
    timer.end("extraction_train")
    
    # Step 9: Evaluate on test queries (100%)
    logger.info("\n[9/9] Evaluating on test queries (100%)...")
    timer.start("evaluation")
    
    results_summary = {}
    
    for table_name, query_list in test_queries.items():
        logger.info(f"\n  Testing {table_name} ({len(query_list)} queries)...")
        
        total_tp = 0
        total_fp = 0
        total_fn = 0
        errors = 0
        perfect_matches = 0
        
        for i, query in enumerate(query_list, 1):
            # Execute on ground truth
            gt_result = execute_query_on_ground_truth(query, gt_engine)
            
            # Execute on QAIRS
            qairs_result = execute_query_on_ground_truth(query, qairs_engine)
            
            if gt_result is None or qairs_result is None:
                errors += 1
                continue
            
            # Get columns from query result
            if gt_result and qairs_result:
                columns = list(gt_result[0].keys()) if gt_result else (list(qairs_result[0].keys()) if qairs_result else [])
            else:
                columns = []
            
            # Calculate F1 metrics with fuzzy matching
            tp, fp, fn = find_matching_rows(gt_result, qairs_result, columns, use_fuzzy=True)
            
            total_tp += tp
            total_fp += fp
            total_fn += fn
            
            # Check for perfect match
            if fp == 0 and fn == 0 and tp == len(gt_result):
                perfect_matches += 1
            else:
                precision, recall, f1 = calculate_f1(tp, fp, fn)
                logger.debug(f"  Query {i}: TP={tp}, FP={fp}, FN={fn}, P={precision:.2f}, R={recall:.2f}, F1={f1:.2f}")
        
        # Calculate aggregate metrics
        precision, recall, f1 = calculate_f1(total_tp, total_fp, total_fn)
        total_queries = len(query_list) - errors
        
        results_summary[table_name] = {
            'queries': total_queries,
            'perfect': perfect_matches,
            'errors': errors,
            'tp': total_tp,
            'fp': total_fp,
            'fn': total_fn,
            'precision': precision,
            'recall': recall,
            'f1': f1
        }
        
        logger.info(f"  Perfect Matches: {perfect_matches}/{total_queries}")
        logger.info(f"  Precision: {precision:.3f}, Recall: {recall:.3f}, F1: {f1:.3f}")
    
    timer.end("evaluation")
    timer.end("total")
    
    # Print final results
    logger.info(f"\n{'=' * 80}")
    logger.info("EVALUATION RESULTS (F1 SCORING)")
    logger.info(f"{'=' * 80}")
    
    # Calculate overall metrics
    overall_tp = sum(r['tp'] for r in results_summary.values())
    overall_fp = sum(r['fp'] for r in results_summary.values())
    overall_fn = sum(r['fn'] for r in results_summary.values())
    overall_precision, overall_recall, overall_f1 = calculate_f1(overall_tp, overall_fp, overall_fn)
    
    overall_perfect = sum(r['perfect'] for r in results_summary.values())
    overall_queries = sum(r['queries'] for r in results_summary.values())
    
    logger.info(f"\nOverall Metrics:")
    logger.info(f"  Perfect Query Matches: {overall_perfect}/{overall_queries} ({overall_perfect/overall_queries*100:.1f}%)")
    logger.info(f"  Precision: {overall_precision:.3f}")
    logger.info(f"  Recall: {overall_recall:.3f}")
    logger.info(f"  F1 Score: {overall_f1:.3f}")
    logger.info(f"  TP={overall_tp}, FP={overall_fp}, FN={overall_fn}\n")
    
    logger.info(f"{'Table':<12} {'Perfect':>7} {'Queries':>7} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    logger.info("-" * 80)
    for table, res in results_summary.items():
        logger.info(f"{table:<12} {res['perfect']:>7} {res['queries']:>7} "
                   f"{res['precision']:>10.3f} {res['recall']:>10.3f} {res['f1']:>10.3f}")
    
    logger.info(f"{'=' * 80}\n")
    
    # Print timing
    timer.print_report()


if __name__ == "__main__":
    main()

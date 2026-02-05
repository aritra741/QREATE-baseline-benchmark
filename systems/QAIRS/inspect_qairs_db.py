#!/usr/bin/env python3
"""
Inspect the QAIRS database to see what was extracted.
"""
import sqlite3
from pathlib import Path
from loguru import logger

def inspect_database(db_path):
    """Inspect a SQLite database."""
    if not Path(db_path).exists():
        logger.error(f"Database not found: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    logger.info(f"Database: {db_path}")
    logger.info(f"Tables: {tables}")
    logger.info("=" * 80)
    
    for table in tables:
        # Get table schema
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        
        logger.info(f"\nTable: {table}")
        logger.info(f"Columns: {[col[1] for col in columns]}")
        logger.info(f"Row count: {count}")
        
        # Show first 5 rows
        if count > 0:
            cursor.execute(f"SELECT * FROM {table} LIMIT 5")
            rows = cursor.fetchall()
            col_names = [col[1] for col in columns]
            
            logger.info(f"\nFirst {min(5, count)} rows:")
            for i, row in enumerate(rows, 1):
                logger.info(f"  Row {i}:")
                for col_name, value in zip(col_names, row):
                    logger.info(f"    {col_name}: {value}")
        
        logger.info("-" * 80)
    
    conn.close()

def main():
    # Inspect both databases
    qairs_db = Path(__file__).parent / "qairs_player.db"
    gt_db = Path(__file__).parent / "ground_truth.db"
    
    if qairs_db.exists():
        logger.info("\n" + "=" * 80)
        logger.info("QAIRS DATABASE")
        logger.info("=" * 80)
        inspect_database(qairs_db)
    else:
        logger.warning(f"QAIRS database not found: {qairs_db}")
    
    if gt_db.exists():
        logger.info("\n" + "=" * 80)
        logger.info("GROUND TRUTH DATABASE")
        logger.info("=" * 80)
        inspect_database(gt_db)
    else:
        logger.warning(f"Ground truth database not found: {gt_db}")

if __name__ == "__main__":
    main()

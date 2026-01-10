#!/usr/bin/env python3
"""
Analyze GEM query results and compare with expectations.
"""

import json
import sys
from pathlib import Path

# Paths
CACHE_DIR = Path(__file__).parent / "systems" / "GEM" / ".cache"
RESULTS_FILE = CACHE_DIR / "query_results.json"
DB_FILE = CACHE_DIR / "gem.sqlite"


def load_results():
    """Load query results from cache."""
    if not RESULTS_FILE.exists():
        print(f"❌ Results file not found: {RESULTS_FILE}")
        print("Run: python test_gem_complete_system.py first")
        sys.exit(1)
    
    with open(RESULTS_FILE, 'r') as f:
        return json.load(f)


def print_results(results):
    """Pretty print query results."""
    print("=" * 100)
    print("QUERY RESULTS SUMMARY")
    print("=" * 100)
    print()
    
    total_rows = 0
    for query_id in sorted(results.keys(), key=lambda x: int(x.split('_')[1])):
        result = results[query_id]
        rows = result.get('rows', 0)
        total_rows += rows
        success = result.get('success', False)
        query_type = "binary" if int(query_id.split('_')[1]) <= 10 else "multi_table"
        
        status = "✓" if success else "✗"
        print(f"{status} Query {query_id}: {rows:4d} rows  ({query_type} join)")
    
    print()
    print(f"Total rows across all queries: {total_rows}")
    print(f"Average rows per query: {total_rows / len(results):.1f}")
    print()


def show_sample_query(results, query_num=1):
    """Show details of a specific query."""
    query_id = f"query_{query_num}"
    
    if query_id not in results:
        print(f"❌ Query {query_num} not found")
        return
    
    result = results[query_id]
    
    print("=" * 100)
    print(f"QUERY {query_num} DETAILS")
    print("=" * 100)
    print()
    print(f"SQL Query:")
    print(f"  {result.get('sql', 'N/A')}")
    print()
    print(f"Success: {result.get('success', False)}")
    print(f"Rows returned: {result.get('rows', 0)}")
    
    if result.get('error'):
        print(f"Error: {result.get('error')}")
    
    print()


def export_to_csv(results, output_file="gem_query_results.csv"):
    """Export results to CSV."""
    import csv
    
    output_path = Path(__file__).parent / output_file
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Query ID', 'Success', 'Rows', 'Query Type', 'SQL'])
        
        for query_id in sorted(results.keys(), key=lambda x: int(x.split('_')[1])):
            result = results[query_id]
            query_num = int(query_id.split('_')[1])
            query_type = "binary" if query_num <= 10 else "multi_table"
            
            writer.writerow([
                query_id,
                result.get('success', False),
                result.get('rows', 0),
                query_type,
                result.get('sql', '')
            ])
    
    print(f"✓ Results exported to {output_path}")


def main():
    """Main analysis."""
    results = load_results()
    
    print()
    print_results(results)
    
    # Show sample queries
    show_sample_query(results, 1)
    show_sample_query(results, 11)
    
    # Export to CSV
    export_to_csv(results)
    
    # Database info
    print()
    print("=" * 100)
    print("DATABASE INFO")
    print("=" * 100)
    print()
    print(f"Database file: {DB_FILE}")
    print(f"Cache directory: {CACHE_DIR}")
    print()
    print("To explore the database:")
    print(f"  sqlite3 {DB_FILE}")
    print()
    print("Common queries:")
    print("  SELECT COUNT(*) as drug_count FROM drug;")
    print("  SELECT COUNT(*) as disease_count FROM disease;")
    print("  SELECT COUNT(*) as institution_count FROM institution;")
    print("  SELECT DISTINCT disease_name FROM drug LIMIT 10;")
    print("  SELECT DISTINCT disease_name FROM disease LIMIT 10;")
    print()


if __name__ == "__main__":
    main()

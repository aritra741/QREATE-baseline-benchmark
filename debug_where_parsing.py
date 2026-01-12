#!/usr/bin/env python3
"""Debug: Check how WHERE clauses are being parsed"""

from docetl_query_executor import DocETLHealthcareQueryExecutor

executor = DocETLHealthcareQueryExecutor()

# Test a few queries
queries = [
    "SELECT generic_name FROM drug WHERE generic_name = 'Pravastatin';",
    "SELECT generic_name, brand_name FROM drug WHERE brand_name != 'Aspirin';",
    "SELECT generic_name FROM drug WHERE generic_name != 'Aspirin' AND indication != 'fever';",
]

for query in queries:
    parsed = executor._parse_sql_query(query)
    print(f"\nQuery: {query}")
    print(f"WHERE conditions: {parsed.get('where_conditions', [])}")

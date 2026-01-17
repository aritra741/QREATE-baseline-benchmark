import os
import sys
import pandas as pd

# Add the systems directory to path so we can import qreate
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'systems')))

from qreate.qreate_runner import QREATE

def run_test():
    # Initialize QREATE
    print("Initializing QREATE system...")
    q = QREATE(cache_dir=".cache/test_qreate_state.pkl")
    
    # Ingest the test document
    input_dir = "systems/qreate/input_test"
    print(f"Ingesting documents from {input_dir}...")
    q.ingest_documents(input_dir)
    
    # Materialize
    print("Materializing Knowledge Graph...")
    q.materialize()
    
    # Show tables
    if q.db:
        tables = q.db.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' AND table_type = 'BASE TABLE'").fetchall()
        print(f"\nDiscovered {len(tables)} tables:")
        for (table_name,) in tables:
            print(f"\n--- TABLE: {table_name} ---")
            df = q.db.execute(f"SELECT * FROM {table_name}").df()
            print(df.to_string(index=False))
    else:
        print("No database materialized.")

if __name__ == "__main__":
    run_test()

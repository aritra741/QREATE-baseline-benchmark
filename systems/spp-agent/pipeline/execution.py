from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import pandas as pd


def execute_sql_on_db(db: dict[str, pd.DataFrame], sql: str) -> pd.DataFrame:
    conn = duckdb.connect(database=":memory:")
    for table, df in db.items():
        clean = df.copy()
        conn.register(table, clean)
    try:
        return conn.execute(sql).fetchdf()
    except Exception as exc:
        raise RuntimeError(f"SQL execution failed: {exc}") from exc
    finally:
        conn.close()


def db_to_temp_csv_dir(db: dict[str, pd.DataFrame]) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="spp_db_"))
    for table, df in db.items():
        df.to_csv(tmp / f"{table}.csv", index=False)
    return tmp

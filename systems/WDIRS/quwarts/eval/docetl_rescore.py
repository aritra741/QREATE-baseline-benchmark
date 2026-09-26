"""Score DocETL-style extraction tables through the QuWARTS scoring path.

Each query's extraction is a list of records (``doc_id`` plus the query's fields), as DocETL's
map writes them. One SQLite database per query holds that table with the full physical schema
(referenced columns plus unresolved signature fallback columns), then the official SQL path
and the shared scorer run on it. ``--recorded`` rescores the frozen DocETL Legal run, which must
reproduce its reported product (0.12350932750098194) for the path to be comparable.

    python -m quwarts.eval.docetl_rescore --corpus legal --recorded
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from quwarts.core.pipeline import official_sql
from quwarts.core.router.registry import RESULTS, get_corpus
from quwarts.core.schema_columns import complete_physical_schema
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.router_execute_v3 import DATASET, score


def build_query_db(table: str, records: list[dict[str, Any]], numeric: set[str], sql: str, qid: str,
                   dest: Path, predicates, null_sentinels: bool) -> Path:
    frame = pd.DataFrame([{k: v for k, v in r.items() if k != "text"} for r in records])
    for col in frame.columns:
        if col in numeric:
            frame[col] = pd.to_numeric(frame[col].astype(str).str.replace(",", "", regex=False)
                                       .str.replace(" ", "", regex=False), errors="coerce")
            if null_sentinels:
                frame.loc[frame[col] == -1, col] = None
        elif null_sentinels:
            frame[col] = frame[col].where(~frame[col].astype(str).str.strip().isin(["", "None", "nan"]), None)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    conn = sqlite3.connect(dest)
    frame.to_sql(table, conn, if_exists="replace", index=False)
    complete_physical_schema(conn, {qid: sql}, predicates)
    conn.commit()
    conn.execute(official_sql(sql, dest, predicates, query_id=qid)).fetchall()
    conn.close()
    return dest


def rescore(corpus: str, tables_by_query: dict[str, dict[str, list[dict]]], numeric_by_table: dict[str, set[str]],
            queries: dict[str, str], out: Path, null_sentinels: bool) -> dict[str, Any]:
    audit = audit_workload([{"query_id": q, "sql": s} for q, s in queries.items()])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    dbs = {}
    for qid, tables in tables_by_query.items():
        if len(tables) != 1:
            raise NotImplementedError("multi-table queries: one database with several tables")
        (table, records), = tables.items()
        dbs[qid] = str(build_query_db(table, records, numeric_by_table.get(table, set()), queries[qid], qid,
                                      out / f"{qid.replace(':', '_')}.db", predicates, null_sentinels))
    base = Path(next(iter(dbs.values())))
    return score(DATASET[corpus], queries, dbs, base)


def recorded_tables(corpus: str) -> tuple[dict, dict]:
    run = RESULTS / f"docetl_{corpus}_case80"
    manifest = {q["query_id"]: q["sql"] for q in json.loads((run / "query_manifest.json").read_text())}
    tables: dict[str, dict[str, list]] = {}
    for qid in manifest:
        for path in sorted((run / "docetl_pipelines" / qid).glob("table_*/pipeline_output.json")):
            tables.setdefault(qid, {})[path.parent.name[len("table_"):]] = json.loads(path.read_text())
    return manifest, tables


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--recorded", action="store_true")
    parser.add_argument("--null-sentinels", action="store_true", help="map -1 and empty strings to NULL")
    args = parser.parse_args(argv)
    spec = get_corpus(args.corpus)
    manifest, tables = recorded_tables(spec.name)
    # The recorded runner coerced a column to numeric when the benchmark schema typed it numeric.
    types = spec.benchmark_attribute_descriptions(purpose="scoring")
    numeric = {t.sql_name: {a for a, r in types.get(t.attributes_key, {}).items()
                            if str(r.get("value_type")) in ("int", "float")} for t in spec.tables}
    tag = "recorded_nullfix" if args.null_sentinels else "recorded"
    report = rescore(spec.name, tables, numeric, manifest, RESULTS / "docetl_diagnostics" / spec.name / tag, args.null_sentinels)
    (RESULTS / "docetl_diagnostics" / spec.name / f"{tag}_score.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "per_query"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

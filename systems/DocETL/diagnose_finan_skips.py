"""Why did the recorded DocETL Finan run keep only 7 of 100 filings?

Re-runs the exact DocETL map configuration of the grid run (runner, prompt, model,
timeout, retries) for one query on a handful of filings, one filing per pipeline and
with ``skip_on_error`` forced off, so every failure surfaces with its exception.
Writes nothing into the frozen DocETL results.

    python diagnose_finan_skips.py 10 9 68 23 1
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "systems" / "WDIRS"))
sys.path.insert(0, str(ROOT))

for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import test_player_query_awareness_trend_docetl as runner  # noqa: E402

QUERY = "finan_multiagg20:q4"


def main() -> None:
    docs = sys.argv[1:] or ["10", "9", "68", "23", "1"]
    runner.DOCETL_MODEL = "openrouter/qwen/qwen-2.5-7b-instruct"
    runner.OLLAMA_BASE_URL = None
    runner.DOCETL_THREADS = 1
    runner.configure_dataset("Finan")
    manifest = json.loads((ROOT / "results" / "docetl_finan_case80" / "query_manifest.json").read_text())
    sql = next(q["sql"] for q in manifest if q["query_id"] == QUERY)
    cols = runner.columns_per_table_from_sql(sql)["finance"]

    original_map = runner.MapOp
    runner.MapOp = lambda **kw: original_map(**{**kw, "skip_on_error": False})
    all_records = runner._raw_doc_records_for_table("finance")
    results = {}
    for doc in docs:
        record = next(r for r in all_records if r["doc_id"] == doc)
        runner._raw_doc_records_for_table = lambda table, r=record: [r]
        work = Path(tempfile.mkdtemp(prefix=f"diag_{doc}_"))
        try:
            frame = runner._run_docetl_map_pipeline_for_table(QUERY, "finance", cols, sql, work)
            results[doc] = {"status": "ok", "rows": len(frame), "chars": len(record["text"])}
        except BaseException as exc:  # noqa: BLE001
            results[doc] = {"status": "error", "chars": len(record["text"]), "type": type(exc).__name__,
                            "message": str(exc)[:600], "trace_tail": traceback.format_exc()[-1500:]}
        print(json.dumps({doc: results[doc]}, indent=2), flush=True)


if __name__ == "__main__":
    main()

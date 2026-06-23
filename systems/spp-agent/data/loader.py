from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from utils.config import load_config


def _benchu_root() -> Path:
    return Path(load_config()["paths"]["benchu_root"])


def _corpus_dir(dataset_name: str) -> Path:
    from data.dataset_registry import normalize_dataset_name

    root = _benchu_root()
    ds_key = normalize_dataset_name(dataset_name)

    # Check dataset-specific corpus_path from config first
    from utils.config import load_config
    cfg = load_config()
    ds_block = cfg.get("datasets", {}).get(ds_key, {})
    if isinstance(ds_block, dict) and ds_block.get("corpus_path"):
        configured = root / ds_block["corpus_path"]
        if configured.is_dir():
            return configured

    synthetic = root / "source_data" / f"Synthetic{dataset_name}"
    if synthetic.is_dir():
        return synthetic
    if ds_key == "Med":
        healthcare = root / "source_data" / "Healthcare"
        if healthcare.is_dir():
            return healthcare
    if ds_key == "Finan":
        finance = root / "source_data" / "Finance" / "finance"
        if finance.is_dir():
            return finance
    data_dir = root / "Data" / dataset_name
    if data_dir.is_dir():
        return data_dir
    raise FileNotFoundError(
        f"Corpus directory not found for dataset {dataset_name}. "
        f"Expected {synthetic}, source_data/Healthcare/ (Med), "
        f"source_data/Finance/finance/ (Finan), or text files under {data_dir}."
    )


def load_corpus(dataset_name: str) -> list[dict]:
    """
    Return list of documents:
    {
      "doc_id": str,
      "text": str,
      "metadata": dict
    }
    """
    corpus_root = _corpus_dir(dataset_name)
    docs: list[dict] = []

    txt_files = sorted(corpus_root.rglob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(
            f"No .txt corpus files found under {corpus_root}. "
            "Bench-U Player corpus is expected in source_data/SyntheticPlayer/."
        )

    from data.dataset_registry import corpus_folder_to_table, normalize_dataset_name

    from data.dataset_registry import FINAN_DATASET, FINAN_SQL_TABLE

    dataset_key = normalize_dataset_name(dataset_name)
    for path in txt_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(corpus_root)
        folder = rel.parts[0] if len(rel.parts) > 1 else path.stem
        mapped = corpus_folder_to_table(dataset_key, folder)
        # For flat single-table corpora (e.g. Finan), all docs belong to one table
        if mapped in ("unknown", folder) and dataset_key == FINAN_DATASET:
            table_hint = FINAN_SQL_TABLE
        else:
            table_hint = mapped
        docs.append(
            {
                "doc_id": str(rel.with_suffix("")),
                "text": text,
                "metadata": {
                    "file_name": path.name,
                    "table_hint": table_hint,
                    "corpus_folder": folder if folder != path.stem else table_hint,
                    "source_path": str(path),
                },
            }
        )

    if not docs:
        raise RuntimeError(f"Corpus for {dataset_name} is empty.")
    return docs


_QUERY_HEADER_RE = re.compile(
    r"^--\s*Query\s+(\d+)\s*:\s*(.*?)(?:\(([^)]*)\))?\s*$",
    re.IGNORECASE,
)


def _parse_sql_file(path: Path, category: str | None) -> list[dict]:
    content = path.read_text(encoding="utf-8")
    queries: list[dict] = []
    current_meta: dict | None = None
    current_sql_lines: list[str] = []

    def flush() -> None:
        nonlocal current_meta, current_sql_lines
        if current_meta is None:
            return
        sql = "\n".join(current_sql_lines).strip().rstrip(";")
        if not sql:
            current_meta = None
            current_sql_lines = []
            return
        qid = f"{path.stem}_{current_meta['index']}"
        queries.append(
            {
                "query_id": qid,
                "sql_query": sql + ";",
                "nl_query": None,
                "category": category or current_meta.get("subcategory"),
                "metadata": {
                    "source_file": str(path),
                    "query_index": current_meta["index"],
                    "subcategory": current_meta.get("subcategory"),
                    "tables": current_meta.get("tables"),
                },
            }
        )
        current_meta = None
        current_sql_lines = []

    for line in content.splitlines():
        header_match = _QUERY_HEADER_RE.match(line.strip())
        if header_match:
            flush()
            tables_raw = header_match.group(3) or ""
            tables = [t.strip() for t in tables_raw.split(",") if t.strip()] if tables_raw else []
            current_meta = {
                "index": int(header_match.group(1)),
                "subcategory": header_match.group(2).strip(),
                "tables": tables,
            }
            continue
        if current_meta is not None:
            if line.strip().startswith("--") and not current_sql_lines:
                continue
            current_sql_lines.append(line)

    flush()

    if not queries and content.strip():
        sql = content.strip().rstrip(";") + ";"
        queries.append(
            {
                "query_id": f"{path.stem}_1",
                "sql_query": sql,
                "nl_query": None,
                "category": category,
                "metadata": {"source_file": str(path), "query_index": 1},
            }
        )
    return queries


def load_queries(dataset_name: str) -> list[dict]:
    """
    Return list of queries:
    {
      "query_id": str,
      "sql_query": str,
      "nl_query": str | None,
      "category": str | None,
      "metadata": dict
    }

    sql_query is required.
    If SQL is unavailable, raise RuntimeError.
    """
    query_root = _benchu_root() / "Query" / dataset_name
    if not query_root.is_dir():
        raise FileNotFoundError(f"Query directory not found: {query_root}")

    sql_files = sorted(query_root.rglob("*.sql"))
    if not sql_files:
        raise RuntimeError(f"SQL queries not found for dataset {dataset_name}. NL2SQL is out of scope for this pilot.")

    all_queries: list[dict] = []
    for sql_file in sql_files:
        if "systems" in sql_file.parts:
            continue
        # Held-out train/dev/test manifests live here; never load into the general pool.
        if "Splits" in sql_file.parts:
            continue
        category = sql_file.parent.name if sql_file.parent != query_root else None
        parsed = _parse_sql_file(sql_file, category)
        if not parsed:
            continue
        for q in parsed:
            if not q.get("sql_query"):
                raise RuntimeError(f"Empty SQL in {sql_file}")
        all_queries.extend(parsed)

    if not all_queries:
        raise RuntimeError(f"SQL queries not found for dataset {dataset_name}. NL2SQL is out of scope for this pilot.")
    return all_queries


def load_ground_truth(dataset_name: str) -> dict[str, pd.DataFrame]:
    """
    Return table_name -> DataFrame.
    """
    root = _benchu_root()
    for candidate in (
        root / "GroundTruth" / dataset_name,
        root / "Data" / dataset_name,
        root / "Query" / dataset_name,
    ):
        if candidate.is_dir():
            gt_dir = candidate
            break
    else:
        raise FileNotFoundError(
            f"Ground-truth tables not found for {dataset_name}. "
            f"Checked GroundTruth/, Data/, and Query/{dataset_name}/."
        )

    csv_files = sorted(gt_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No ground-truth CSV tables found in {gt_dir}")

    from data.dataset_registry import normalize_dataset_name, corpus_folder_to_table

    ds_key = normalize_dataset_name(dataset_name)
    tables: dict[str, pd.DataFrame] = {}
    for csv_path in csv_files:
        stem = csv_path.stem
        # Normalise GT table name to match what SQL queries use.
        # e.g. Finan.csv -> "Finan" but queries say "finance"
        canonical = corpus_folder_to_table(ds_key, stem.lower()) or stem
        tables[canonical] = pd.read_csv(csv_path)
    return tables

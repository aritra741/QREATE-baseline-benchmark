"""CSPaper case-study 80/20 eval on source_data/CSPaper with OpenRouter Qwen."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.experiments.extract_util import cached_pdf_text, longer_text, schema_context
from quwarts.experiments.player_case80 import (
    _as_scalar,
    parse_json_object,
    score_split,
    split_80_20,
)

load_env_file(ROOT / ".env")

CASE = ROOT / "case study"
TXT_DIR = ROOT / "source_data" / "CSPaper" / "txt"
PDF_DIR = ROOT / "source_data" / "CSPaper"
CORPUS = TXT_DIR
CACHE_VERSION = "pdf-schema-v2"

PACKS = [
    CASE / "workloads" / "cspaper_agg20" / "query_manifest.json",
    CASE / "workloads" / "cspaper_filter20" / "query_manifest.json",
    CASE / "workloads" / "cspaper_groupby20" / "query_manifest.json",
    CASE / "workloads" / "cspaper_multiagg20" / "query_manifest.json",
]

FIELDS = [
    "topic",
    "uses_knowledge_graph",
    "reasoning_depth",
    "retrieval_method",
    "uses_reranker",
    "data_modality",
    "application_domain",
    "use_agent",
    "agent_framework",
    "multi_turn_retrieval",
    "baseline_amount",
]

YES_NO = {
    "uses_knowledge_graph",
    "uses_reranker",
    "use_agent",
    "multi_turn_retrieval",
}

PROMPT = (
    "This is one CS/NLP paper. Extract one record. "
    "topic is one of: Information Retrieval, Retrieval-Augmented Generation, Data Selection, SFT. "
    "uses_knowledge_graph, uses_reranker, use_agent, multi_turn_retrieval must be Yes or No: "
    "Yes if the document indicates the property, No if it does not. Do not leave them null. "
    "reasoning_depth is single-hop or multi-hop. "
    "retrieval_method is one of: Dense Retrieval, Graph-based Retrieval, Hybrid Retrieval, Sparse Retrieval, Web Search, other. "
    "data_modality is one or more of Audio, Image, Table, Text, Code joined by ||. "
    "application_domain is one or more of General, Education, Finance, Sports, Government, Legal, Medical, Academic, Art, Other. "
    "agent_framework is CoT, ToT, Multi-Agent Collaboration, Other, or null if use_agent is No. "
    "baseline_amount is the integer count of baselines compared in the paper. "
    f"Return a single JSON object with keys: {FIELDS}. "
    "Use null only for non-boolean fields the document does not state.\n\nDOCUMENT:\n"
)


def load_queries() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in PACKS:
        payload = json.loads(path.read_text())
        pack = path.parent.name
        for index, row in enumerate(payload):
            sql = str(row.get("sql") or "").strip()
            if not sql or sql in seen:
                continue
            seen.add(sql)
            rows.append({
                "query_id": f"{pack}:{row.get('query_id', f'q{index}')}",
                "sql": sql,
                "pack": pack,
            })
    return rows


def load_documents(pdf_cache: Path, workers: int = 8) -> list[dict[str, str]]:
    paths = sorted(TXT_DIR.glob("*.txt"))

    def one(path: Path) -> dict[str, str]:
        stub = path.read_text(encoding="utf-8", errors="replace")
        pdf = PDF_DIR / f"{path.stem}.pdf"
        full = cached_pdf_text(pdf, pdf_cache) if pdf.exists() else ""
        return {"doc_id": path.name, "text": longer_text(full, stub)}

    docs: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, path) for path in paths]
        for future in as_completed(futures):
            docs.append(future.result())
    docs.sort(key=lambda row: row["doc_id"])
    return docs


def coerce(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in FIELDS:
        value = _as_scalar(row.get(field))
        if value in ("", "null", "None", "unknown", "n/a", "N/A", -1, "-1"):
            value = None
        if field in YES_NO and value is not None:
            token = str(value).strip().lower()
            if token in {"yes", "y", "true", "1"}:
                value = "Yes"
            elif token in {"no", "n", "false", "0"}:
                value = "No"
            else:
                value = None
        if field == "baseline_amount" and value is not None:
            try:
                value = int(float(str(value).replace(",", "").strip()))
            except ValueError:
                value = None
        if isinstance(value, str):
            value = value.strip() or None
        out[field] = value
    return out


def cache_key(doc_id: str, model: str, text: str) -> str:
    payload = f"cspaper|{CACHE_VERSION}|{doc_id}|{model}|{hashlib.sha256(text.encode()).hexdigest()}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _closed_nulls(row: dict[str, Any]) -> list[str]:
    return [field for field in YES_NO if row.get(field) not in {"Yes", "No"}]


def _fill_closed(caller, row: dict[str, Any], text: str, model: str) -> dict[str, Any]:
    missing = _closed_nulls(row)
    if not missing:
        return row
    snippet = schema_context(text, missing, limit=8000)
    raw = caller.complete(
        "Decide each field from the document only. "
        "Each field is Yes or No. Yes if the document indicates the property, "
        f"No if it does not. Return a single JSON object with keys: {missing}.\n\n"
        f"DOCUMENT:\n{snippet}",
        purpose="extract",
        attribute="cspaper_closed",
        model=model,
        system="Return grounded JSON. No commentary.",
    )
    extra = coerce(parse_json_object(raw))
    for field in missing:
        if extra.get(field) in {"Yes", "No"}:
            row[field] = extra[field]
    return row


def extract_one(caller, doc: dict[str, str], cache_dir: Path, model: str) -> dict[str, Any]:
    text = schema_context(doc["text"], FIELDS, limit=12000)
    key = cache_key(doc["doc_id"], model, text)
    path = cache_dir / f"{key}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        row = coerce(cached)
        row["_doc_id"] = cached.get("_doc_id", doc["doc_id"])
        if _closed_nulls(row):
            row = _fill_closed(caller, row, doc["text"], model)
            path.write_text(json.dumps(row, ensure_ascii=False, indent=2))
        return row
    raw = caller.complete(
        PROMPT + text,
        purpose="extract",
        attribute="cspaper",
        model=model,
        system="Extract grounded JSON facts. No commentary.",
    )
    row = coerce(parse_json_object(raw))
    row = _fill_closed(caller, row, doc["text"], model)
    row["_doc_id"] = doc["doc_id"]
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2))
    return row


def materialize(rows: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        cols = ", ".join(f'"{field}" TEXT' for field in FIELDS)
        conn.execute(f'CREATE TABLE cspaper ({cols})')
        marks = ", ".join("?" for _ in FIELDS)
        for row in rows:
            conn.execute(
                f"INSERT INTO cspaper VALUES ({marks})",
                [None if row.get(field) in (None, "") else str(row.get(field)) for field in FIELDS],
            )
        conn.commit()
    finally:
        conn.close()
    return path


def load_gold() -> dict[str, list[dict[str, Any]]]:
    sys.path.insert(0, str(WDIRS))
    from diagnostics.run_config_grid import load_ground_truth
    return load_ground_truth("CSPaper")


def run(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.output)
    cache_dir = out / "extract_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    queries = load_queries()
    train, test = split_80_20(queries, args.seed)
    documents = load_documents(out / "pdf_text", workers=args.workers)
    mean_chars = sum(len(d["text"]) for d in documents) / max(len(documents), 1)
    print(f"loaded docs mean_chars={mean_chars:.0f}", flush=True)
    if mean_chars < 8000:
        print("warning: PDF text looks truncated; closed fields will stay sparse", flush=True)
    ledger = TokenLedger(theta=args.budget, seed=args.seed)
    caller = make_caller(ledger, model=args.model, max_tokens=700)

    print(
        f"corpus={CORPUS} docs={len(documents)} queries={len(queries)} "
        f"train={len(train)} test={len(test)}",
        flush=True,
    )
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(extract_one, caller, doc, cache_dir, args.model)
            for doc in documents
        ]
        for index, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if index == 1 or index % 20 == 0 or index == len(futures):
                filled = sum(1 for field in YES_NO if rows[-1].get(field) in {"Yes", "No"})
                print(f"extract {index}/{len(futures)} closed_filled={filled}/4", flush=True)

    db_path = materialize(rows, out / "cspaper.sqlite")
    report = score_split(test, db_path, load_gold(), dataset="CSPaper")
    train_report = score_split(train, db_path, load_gold(), dataset="CSPaper")
    summary = {
        "corpus": str(CORPUS),
        "model": args.model,
        "seed": args.seed,
        "train_ids": [row["query_id"] for row in train],
        "test_ids": [row["query_id"] for row in test],
        "row_counts": {"cspaper": len(rows)},
        "tokens_spent": ledger.spent,
        "theta": ledger.theta,
        **report,
        "train": {
            "n_train": train_report["n_test"],
            "mean_official_accuracy": train_report["mean_official_accuracy"],
            "mean_structure_f2": train_report["mean_structure_f2"],
            "mean_cell_f1_05": train_report["mean_cell_f1_05"],
            "mean_query_score_05": train_report["mean_query_score_05"],
        },
    }
    (out / "report.json").write_text(json.dumps(summary, indent=2, default=str))
    (out / "train_report.json").write_text(json.dumps(train_report, indent=2, default=str))
    print(json.dumps({
        "mean_official_accuracy": summary["mean_official_accuracy"],
        "mean_structure_f2": summary["mean_structure_f2"],
        "mean_cell_f1_05": summary["mean_cell_f1_05"],
        "mean_query_score_05": summary["mean_query_score_05"],
        "train": summary["train"],
        "tokens_spent": summary["tokens_spent"],
        "row_counts": summary["row_counts"],
    }, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "quwarts_cspaper_case80")
    parser.add_argument("--budget", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""QuWARTS 80/20 extract+score for single-table case-study datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
from quwarts.experiments.extract_util import schema_context
from quwarts.experiments.player_case80 import (
    _as_scalar,
    parse_json_object,
    score_split,
    split_80_20,
)

load_env_file(ROOT / ".env")

CASE = ROOT / "case study"

DATASETS = {
    "Art": {
        "eval": "Art",
        "table": "art",
        "txt": ROOT / "source_data" / "Art" / "wikiart",
        "packs": ["art_agg20", "art_filter20", "art_groupby20", "art_multiagg20"],
        "lead": "This is one artist biography. Extract that artist only.",
        "context_limit": 7000,
        "max_tokens": 700,
    },
    "Finan": {
        "eval": "Finan",
        "table": "finance",
        "txt": ROOT / "source_data" / "Finance" / "finance",
        "packs": ["finan_agg20", "finan_filter20", "finan_groupby20", "finan_multiagg20"],
        "lead": "This is one company annual report. Extract that company only. "
        "Numeric money fields are integers. Convert to USD if needed.",
        "context_limit": 12000,
        "max_tokens": 900,
    },
    "Legal": {
        "eval": "Legal",
        "table": "legal",
        "txt": ROOT / "source_data" / "Legal" / "legal_case",
        "packs": ["legal_agg20", "legal_filter20", "legal_groupby20", "legal_multiagg20"],
        "lead": "This is one court judgment. Extract that case only.",
        "context_limit": 12000,
        "max_tokens": 700,
    },
}

ZERO_ONE = {"teaching", "evidence", "first_judge"}
YES_NO = {"major_equity_changes"}


def _attributes(eval_name: str) -> dict[str, Any]:
    path = ROOT / "Query" / eval_name / f"{eval_name}_attributes.json"
    payload = json.loads(path.read_text())
    table = next(iter(payload.values()))
    return {str(name).lower(): spec for name, spec in table.items()}


def fields_for(eval_name: str) -> list[str]:
    return list(_attributes(eval_name).keys())


def numeric_fields(eval_name: str) -> set[str]:
    attrs = _attributes(eval_name)
    return {
        name
        for name, spec in attrs.items()
        if spec.get("value_type") in {"int", "float"} or spec.get("usage") == "numerical"
    }


def closed_note(eval_name: str) -> str:
    lines = []
    for name, spec in _attributes(eval_name).items():
        desc = spec.get("description") or ""
        if spec.get("is_fixed") or "choose" in desc.lower() or "select one" in desc.lower():
            lines.append(f"{name}: {desc}")
    return "\n".join(lines)


def load_queries(dataset: str) -> list[dict[str, str]]:
    spec = DATASETS[dataset]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for pack in spec["packs"]:
        payload = json.loads((CASE / "workloads" / pack / "query_manifest.json").read_text())
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


def load_documents(dataset: str) -> list[dict[str, str]]:
    folder = DATASETS[dataset]["txt"]
    docs = []
    for path in sorted(folder.glob("*.txt")):
        docs.append({
            "doc_id": path.name,
            "text": path.read_text(encoding="utf-8", errors="replace"),
        })
    return docs


def prompt_for(dataset: str, text: str) -> str:
    spec = DATASETS[dataset]
    fields = fields_for(spec["eval"])
    note = closed_note(spec["eval"])
    extra = f"Closed fields:\n{note}\n" if note else ""
    return (
        f"{spec['lead']}\n{extra}"
        f"Return a single JSON object with keys: {fields}. "
        "Use null when the document does not state a value.\n\n"
        f"DOCUMENT:\n{text}"
    )


def coerce(dataset: str, row: dict[str, Any]) -> dict[str, Any]:
    eval_name = DATASETS[dataset]["eval"]
    numeric = numeric_fields(eval_name)
    out: dict[str, Any] = {}
    for field in fields_for(eval_name):
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
        elif field in ZERO_ONE and value is not None:
            token = str(value).strip().lower()
            if token in {"1", "yes", "true", "y"}:
                value = 1
            elif token in {"0", "no", "false", "n"}:
                value = 0
            else:
                value = None
        if field in numeric and field not in ZERO_ONE and value is not None:
            text = str(value).replace(",", "").replace("$", "").strip()
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            if match:
                number = match.group()
                value = float(number) if "." in number else int(number)
            else:
                value = None
        if isinstance(value, str):
            value = value.strip() or None
        out[field] = value
    return out


def cache_key(dataset: str, doc_id: str, model: str, text: str) -> str:
    payload = f"{dataset}|v1|{doc_id}|{model}|{hashlib.sha256(text.encode()).hexdigest()}"
    return hashlib.sha256(payload.encode()).hexdigest()


def extract_one(caller, dataset: str, doc: dict[str, str], cache_dir: Path, model: str) -> dict[str, Any]:
    spec = DATASETS[dataset]
    fields = fields_for(spec["eval"])
    context = schema_context(doc["text"], fields, limit=spec["context_limit"])
    key = cache_key(dataset, doc["doc_id"], model, context)
    path = cache_dir / f"{key}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        row = coerce(dataset, cached)
        row["_doc_id"] = cached.get("_doc_id", doc["doc_id"])
        return row
    raw = caller.complete(
        prompt_for(dataset, context),
        purpose="extract",
        attribute=spec["table"],
        model=model,
        system="Extract grounded JSON facts. No commentary.",
    )
    row = coerce(dataset, parse_json_object(raw))
    row["_doc_id"] = doc["doc_id"]
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2))
    return row


def materialize(dataset: str, rows: list[dict[str, Any]], path: Path) -> Path:
    spec = DATASETS[dataset]
    fields = fields_for(spec["eval"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        cols = ", ".join(f'"{field}" TEXT' for field in fields)
        conn.execute(f'CREATE TABLE "{spec["table"]}" ({cols})')
        marks = ", ".join("?" for _ in fields)
        for row in rows:
            conn.execute(
                f'INSERT INTO "{spec["table"]}" VALUES ({marks})',
                [None if row.get(field) in (None, "") else str(row.get(field)) for field in fields],
            )
        conn.commit()
    finally:
        conn.close()
    return path


def load_gold(dataset: str) -> dict[str, list[dict[str, Any]]]:
    from diagnostics.run_config_grid import load_ground_truth
    return load_ground_truth(DATASETS[dataset]["eval"])


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = args.dataset
    spec = DATASETS[dataset]
    out = Path(args.output)
    cache_dir = out / "extract_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    queries = load_queries(dataset)
    train, test = split_80_20(queries, args.seed)
    documents = load_documents(dataset)
    ledger = TokenLedger(theta=args.budget, seed=args.seed)
    caller = make_caller(ledger, model=args.model, max_tokens=spec["max_tokens"])

    print(
        f"dataset={dataset} docs={len(documents)} queries={len(queries)} "
        f"train={len(train)} test={len(test)}",
        flush=True,
    )
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(extract_one, caller, dataset, doc, cache_dir, args.model)
            for doc in documents
        ]
        for index, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if index == 1 or index % 25 == 0 or index == len(futures):
                print(f"extract {index}/{len(futures)}", flush=True)

    db_path = materialize(dataset, rows, out / f"{spec['table']}.sqlite")
    gold = load_gold(dataset)
    report = score_split(test, db_path, gold, dataset=spec["eval"])
    train_report = score_split(train, db_path, gold, dataset=spec["eval"])
    summary = {
        "dataset": dataset,
        "model": args.model,
        "seed": args.seed,
        "train_ids": [row["query_id"] for row in train],
        "test_ids": [row["query_id"] for row in test],
        "row_counts": {spec["table"]: len(rows)},
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
        "dataset": dataset,
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
    parser.add_argument("--dataset", choices=tuple(DATASETS), required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--budget", type=int, default=8_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if args.output is None:
        args.output = ROOT / "results" / f"quwarts_{args.dataset.lower()}_case80"
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

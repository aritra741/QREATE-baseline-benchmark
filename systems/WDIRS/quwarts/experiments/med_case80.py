"""Med case-study 80/20 eval on source_data/Healthcare with OpenRouter Qwen.

Corpus and queries match ``case study/``: Healthcare
``disease_small`` / ``drug_small`` / ``institutes_small`` and the five 20-query
packs. Gold is ``Data/Med``.
"""

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
from quwarts.experiments.extract_util import schema_context
from quwarts.experiments.player_case80 import (
    _as_scalar,
    align_names,
    parse_json_object,
    score_split,
    split_80_20,
)

load_env_file(ROOT / ".env")

CASE = ROOT / "case study"
CORPUS = ROOT / "source_data" / "Healthcare"
GOLD_DIR = ROOT / "Data" / "Med"

PACKS = [
    CASE / "workloads" / "med_agg20" / "query_manifest.json",
    CASE / "workloads" / "med_groupby20" / "query_manifest.json",
    CASE / "workloads" / "med_join20" / "query_manifest.json",
    CASE / "workloads" / "med_filterjoin20" / "query_manifest.json",
    CASE / "workloads" / "med_multiagg20" / "query_manifest.json",
]

SOURCE_SUBDIRS = {
    "disease": "disease_small",
    "drug": "drug_small",
    "institution": "institutes_small",
}

ENTITY_FIELDS = {
    "disease": [
        "disease_name", "disease_type", "pathogenesis", "diagnostic_methods",
        "treatments", "prognosis",
    ],
    "drug": [
        "generic_name", "disease_name", "pharmaceutical_form", "manufacturer",
        "administration_route", "prescription_status", "storage_conditions",
    ],
    "institution": [
        "institution_name", "institution_type", "institution_country",
        "research_diseases", "research_fields", "key_technologies",
        "international_collaboration", "funding_sources",
    ],
}

NUMERIC = set()

PROMPTS = {
    "disease": (
        "This is one disease article. Extract that disease only. "
        "disease_type / pathogenesis / diagnostic_methods / treatments / prognosis "
        "use the document's terms, lowercase snake_case when it is a category "
        "(infectious, neoplastic, oral_medication, clinical_evaluation). "
        "Join multiple values with ||."
    ),
    "drug": (
        "This is one drug article. Extract that drug only. "
        "disease_name is the main treated disease. "
        "pharmaceutical_form and administration_route are categories "
        "(tablet, injection, capsule, oral). "
        "prescription_status is prescription_only, over_the_counter, restricted, or unclassified. "
        "Join multiple values with ||."
    ),
    "institution": (
        "This is one medical research institution. Extract that institution only. "
        "institution_type is public, private, university-affiliated, or corporate research lab. "
        "research_diseases are specific disease names. "
        "Join multiple values with ||."
    ),
}


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


def useful_context(text: str, fields: list[str] | None = None, limit: int = 7000) -> str:
    return schema_context(text, fields or [], limit=limit)


def load_documents() -> list[dict[str, str]]:
    docs = []
    for entity, subdir in SOURCE_SUBDIRS.items():
        folder = CORPUS / subdir
        for path in sorted(folder.glob("*.txt")):
            docs.append({
                "doc_id": f"{entity}/{path.name}",
                "entity": entity,
                "text": path.read_text(encoding="utf-8", errors="replace"),
                "id": path.stem,
            })
    return docs


def coerce(entity: str, row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in ENTITY_FIELDS[entity]:
        value = _as_scalar(row.get(field))
        if value in ("", "null", "None", "unknown", "n/a", "N/A", -1, "-1"):
            value = None
        if isinstance(value, str):
            value = value.strip() or None
        out[field] = value
    return out


def prompt_for(entity: str, text: str, hints: dict[str, list[str]]) -> str:
    extra = ""
    if entity in {"drug", "institution"} and hints.get("diseases"):
        extra = "Known disease names (copy one exactly if present): " + ", ".join(
            hints["diseases"][:50]
        )
    return (
        f"{PROMPTS[entity]}\n{extra}\n"
        f"Return a single JSON object with keys: {ENTITY_FIELDS[entity]}.\n"
        f"Use null when the document does not state a value.\n\nDOCUMENT:\n{text}"
    )


def cache_key(entity: str, doc_id: str, model: str, text: str) -> str:
    payload = f"{entity}|{doc_id}|{model}|{hashlib.sha256(text.encode()).hexdigest()}"
    return hashlib.sha256(payload.encode()).hexdigest()


def extract_one(caller, entity: str, doc: dict[str, str], hints: dict[str, list[str]], cache_dir: Path, model: str) -> dict[str, Any]:
    context = useful_context(doc["text"], ENTITY_FIELDS[entity], limit=7000)
    key = cache_key(entity, doc["doc_id"], model, context)
    path = cache_dir / f"{key}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        row = coerce(entity, cached)
        row["id"] = cached.get("id") or doc["id"]
        row["_doc_id"] = cached.get("_doc_id", doc["doc_id"])
        return row
    text = caller.complete(
        prompt_for(entity, context, hints),
        purpose="extract",
        attribute=entity,
        model=model,
        system="Extract grounded JSON facts. No commentary.",
    )
    row = coerce(entity, parse_json_object(text))
    row["id"] = doc["id"]
    row["_doc_id"] = doc["doc_id"]
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2))
    return row


def align_multi(value: Any, candidates: list[str]) -> str | None:
    value = _as_scalar(value)
    if not value:
        return None
    parts = [part.strip() for part in str(value).replace("|", "||").split("||") if part.strip()]
    aligned = []
    for part in parts:
        hit = align_names(part, candidates)
        aligned.append(hit or part)
    return "||".join(aligned) if aligned else None


def materialize(tables: dict[str, list[dict[str, Any]]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        for table, rows in tables.items():
            fields = ["id", *ENTITY_FIELDS[table]]
            cols = ", ".join(f'"{field}" TEXT' for field in fields)
            conn.execute(f'CREATE TABLE "{table}" ({cols})')
            marks = ", ".join("?" for _ in fields)
            for row in rows:
                conn.execute(
                    f'INSERT INTO "{table}" VALUES ({marks})',
                    [None if row.get(field) in (None, "") else str(row.get(field)) for field in fields],
                )
        conn.commit()
    finally:
        conn.close()
    return path


def load_gold() -> dict[str, list[dict[str, Any]]]:
    sys.path.insert(0, str(WDIRS))
    from diagnostics.run_config_grid import load_ground_truth
    return load_ground_truth("Med")


def run(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.output)
    cache_dir = out / "extract_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    queries = load_queries()
    train, test = split_80_20(queries, args.seed)
    documents = load_documents()
    ledger = TokenLedger(theta=args.budget, seed=args.seed)
    caller = make_caller(ledger, model=args.model, max_tokens=900)

    grouped: dict[str, list[dict[str, str]]] = {name: [] for name in ENTITY_FIELDS}
    for doc in documents:
        grouped[doc["entity"]].append(doc)

    tables: dict[str, list[dict[str, Any]]] = {name: [] for name in ENTITY_FIELDS}
    hints: dict[str, list[str]] = {"diseases": []}

    def extract_group(entity: str) -> list[dict[str, Any]]:
        rows = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(extract_one, caller, entity, doc, hints, cache_dir, args.model)
                for doc in grouped[entity]
            ]
            for future in as_completed(futures):
                rows.append(future.result())
        return rows

    print(
        f"corpus={CORPUS} docs={len(documents)} queries={len(queries)} "
        f"train={len(train)} test={len(test)}",
        flush=True,
    )
    tables["disease"] = extract_group("disease")
    hints["diseases"] = [
        row.get("disease_name") for row in tables["disease"] if row.get("disease_name")
    ]
    tables["drug"] = extract_group("drug")
    for row in tables["drug"]:
        row["disease_name"] = align_multi(row.get("disease_name"), hints["diseases"])
    tables["institution"] = extract_group("institution")
    for row in tables["institution"]:
        row["research_diseases"] = align_multi(row.get("research_diseases"), hints["diseases"])

    db_path = materialize(tables, out / "med.sqlite")
    counts = {name: len(rows) for name, rows in tables.items()}
    report = score_split(test, db_path, load_gold(), dataset="Med")
    train_report = score_split(train, db_path, load_gold(), dataset="Med")
    summary = {
        "corpus": str(CORPUS),
        "model": args.model,
        "seed": args.seed,
        "train_ids": [row["query_id"] for row in train],
        "test_ids": [row["query_id"] for row in test],
        "row_counts": counts,
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
        "row_counts": counts,
    }, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "quwarts_med_case80")
    parser.add_argument("--budget", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

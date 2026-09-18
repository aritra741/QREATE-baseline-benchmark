"""Classifier v2 on the two largest standalone-oracle attributes only."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.ledger import BudgetExhausted, TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.signature import audit_workload, enumerate_predicates, rewrite_sql
from quwarts.core.signature_classify import (
    labels_to_cells,
    needs_document,
    parse_v2,
    v2_prompt,
)
from quwarts.core.truth import PredicateLabel
from quwarts.experiments.extract_util import schema_context
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import (
    documents_for,
    gold_name,
    queries_for,
    score_with_rewrites,
)

load_env_file(ROOT / ".env")

MODEL_SIG = ROOT / "results" / "quwarts_med_signatures" / "artifacts" / "aprime_model_sig.db"
APRIME = next((ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "databases").glob("*.db"))
GOLD_SIG = ROOT / "results" / "quwarts_med_signatures" / "artifacts" / "aprime_gold_sig.db"
STEP5 = ROOT / "results" / "quwarts_med_signatures" / "step5_model.json"
DIAG = ROOT / "results" / "quwarts_med_signatures" / "step5_diagnostics.json"
OUT = ROOT / "results" / "quwarts_med_signatures"
TARGET = ("drug.manufacturer", "drug.pharmaceutical_form")
BUDGET = 400_000
WORKERS = 8


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _fold(value) -> str:
    return " ".join(str(value or "").replace("_", " ").casefold().split())


def entity_key(row: dict, table: str) -> str:
    for col in (f"{table}_name", "generic_name", "name"):
        if row.get(col) not in (None, ""):
            return _fold(row[col])
    return Path(str(row.get("doc_id") or "")).stem


def surfaces(row: dict, column: str) -> list[str]:
    found = []
    if row.get(column) not in (None, ""):
        found.append(str(row[column]))
    for col, value in row.items():
        if str(col).endswith("_name") and value not in (None, ""):
            found.append(str(value))
    return list(dict.fromkeys(found))


def load_table(path: Path, table: str) -> list[dict]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in con.execute(f"SELECT * FROM {_q(table)}")]
    finally:
        con.close()


def classify(caller, prompt: str, preds, purpose: str) -> tuple[dict[str, PredicateLabel], str]:
    try:
        text = caller.complete(
            prompt,
            purpose=purpose,
            attribute=preds[0].attribute,
            system="Classify concepts for one entity attribute. JSON only. Multiple may apply.",
            max_tokens=280,
        )
    except BudgetExhausted:
        return {pred.pred_id: PredicateLabel("NULL", "failed") for pred in preds}, ""
    except Exception:
        return {pred.pred_id: PredicateLabel("NULL", "failed") for pred in preds}, ""
    return parse_v2(text, preds), text


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    report = audit_workload(queries)
    predicates = enumerate_predicates(report.occurrences, report.signature_eligible)
    by_attr = defaultdict(list)
    for pred in predicates:
        by_attr[pred.attribute].append(pred)
    docs = {doc.doc_id: doc.text for doc in documents_for("Med")}
    dest = OUT / "artifacts" / "aprime_model_sig_v2_subset.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(MODEL_SIG, dest)

    ledger = TokenLedger(theta=BUDGET, seed=42)
    caller = make_caller(ledger, model=DEFAULT_MODEL, max_tokens=280)
    raw_dir = OUT / "step5_v2_raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir()
    cache: dict[tuple[str, str], dict[str, PredicateLabel]] = {}
    cache_lock = threading.Lock()
    status = Counter()
    n_value = 0
    n_doc = 0
    n_cache = 0
    updates: dict[tuple[str, str], dict[str, PredicateLabel]] = {}

    jobs = []
    for attr in TARGET:
        preds = by_attr[attr]
        table, col = attr.split(".", 1)
        for row in load_table(APRIME, table):
            jobs.append((attr, preds, table, col, row))

    def run(job):
        attr, preds, table, col, row = job
        key = (attr, entity_key(row, table))
        with cache_lock:
            if key in cache:
                return attr, row.get("doc_id"), cache[key], "cache", ""
        prompt = v2_prompt(
            attr, preds,
            entity_name=entity_key(row, table),
            surfaces=surfaces(row, col),
        )
        labels, raw = classify(caller, prompt, preds, "sig_v2_entity")
        if needs_document(labels):
            text = schema_context(docs.get(row.get("doc_id"), "") or "", [col], 4000)
            labels, raw = classify(
                caller,
                v2_prompt(
                    attr, preds,
                    entity_name=entity_key(row, table),
                    surfaces=surfaces(row, col),
                    document=text,
                ),
                preds,
                "sig_v2_document",
            )
            kind = "document"
        else:
            kind = "entity"
        with cache_lock:
            cache[key] = labels
        return attr, row.get("doc_id"), labels, kind, raw

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), 1):
            attr, doc_id, labels, kind, raw = future.result()
            if kind == "cache":
                n_cache += 1
            elif kind == "document":
                n_doc += 1
            else:
                n_value += 1
            updates[(attr, doc_id)] = labels
            for lab in labels.values():
                status[lab.classifier_status] += 1
            (raw_dir / f"{kind}_{index}.json").write_text(
                json.dumps({
                    "attribute": attr,
                    "doc_id": doc_id,
                    "kind": kind,
                    "raw": raw,
                    "labels": {
                        key: {"sql_truth": lab.sql_truth, "classifier_status": lab.classifier_status}
                        for key, lab in labels.items()
                    },
                }, indent=2)
            )
            if index == 1 or index % 25 == 0:
                print(f"v2 {index}/{len(futures)} spent={ledger.spent} kind={kind}", flush=True)

    con = sqlite3.connect(dest)
    try:
        for (attr, doc_id), labels in updates.items():
            preds = by_attr[attr]
            cells = labels_to_cells(labels)
            assignments = ", ".join(f"{_q(pred.sig_name)} = ?" for pred in preds)
            con.execute(
                f"UPDATE {_q(preds[0].table)} SET {assignments} WHERE doc_id = ?",
                [cells.get(pred.pred_id) for pred in preds] + [doc_id],
            )
        con.commit()
    finally:
        con.close()

    gold = load_ground_truth(gold_name("Med"))
    scored = score_with_rewrites(
        test,
        {row["query_id"]: rewrite_sql(row["sql"], predicates) for row in test},
        dest,
        gold,
        "Med",
    )
    step5 = json.loads(STEP5.read_text()) if STEP5.is_file() else {}
    diag = json.loads(DIAG.read_text()) if DIAG.is_file() else {}
    oracles = (diag.get("attribute_oracles") or {})
    product = mean_per_query_product(scored)
    payload = {
        "arm": "classifier_v2_subset",
        "attributes": list(TARGET),
        "tokens_spent": ledger.spent,
        "budget": BUDGET,
        "n_entity_calls": n_value,
        "n_document_calls": n_doc,
        "n_cache_hits": n_cache,
        "n_cache_keys": len(cache),
        "classifier_status": dict(status),
        "mean_structure_f2": float(scored.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(scored),
        "mean_per_query_product": product,
        "vs_step5": {
            "product": product - float(step5.get("mean_per_query_product") or 0.0),
            "structure_f2": float(scored.get("mean_structure_f2") or 0.0)
            - float(step5.get("mean_structure_f2") or 0.0),
            "cell_f1_20": mean_cell_f1_20(scored) - float(step5.get("mean_cell_f1_at_0.20") or 0.0),
        },
        "standalone_gold_ceiling_those_attrs": {
            name: (oracles.get("one_at_a_time_replace_model_with_gold") or {}).get(name)
            for name in TARGET
        },
        "test_empty": sum(1 for row in scored.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0),
        "sqlite_path": str(dest),
    }
    path = OUT / "step5_v2_subset.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

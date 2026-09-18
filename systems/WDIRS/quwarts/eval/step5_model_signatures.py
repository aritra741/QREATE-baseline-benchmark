"""Step 5. Model-generated signatures on the A' row set. Budget-matched."""

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
from quwarts.core.signature import (
    audit_workload,
    enumerate_predicates,
    rewrite_sql,
)
from quwarts.core.signature_classify import (
    ClassifyResult,
    document_prompt,
    emptiness_labels,
    labels_to_cells,
    needs_model,
    parse_labels,
    value_is_missing,
    value_prompt,
)
from quwarts.core.truth import PredicateLabel, merge_atoms
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import (
    documents_for,
    gold_name,
    queries_for,
    score_with_rewrites,
)
from quwarts.experiments.extract_util import schema_context

load_env_file(ROOT / ".env")

APRIME = next((ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "databases").glob("*.db"))
APRIME_REPORT = ROOT / "results" / "quwarts_med_aprime" / "aprime_report.json"
STEP4 = ROOT / "results" / "quwarts_med_signatures" / "step4_oracle_aprime.json"
GOLD_SIG_DB = ROOT / "results" / "quwarts_med_signatures" / "artifacts" / "aprime_gold_sig.db"
OUT = ROOT / "results" / "quwarts_med_signatures"
BUDGET = 1_543_790
WORKERS = 12


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def load_rows(path: Path) -> dict[str, list[dict]]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        tables = {}
        for (table,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
        ):
            tables[table] = [dict(row) for row in con.execute(f"SELECT * FROM {_q(table)}")]
        return tables
    finally:
        con.close()


def clip_doc(text: str, attribute: str) -> str:
    return schema_context(text or "", [attribute.split(".")[-1]], limit=4000)


def classify_one(caller, prompt: str, purpose: str, predicates) -> ClassifyResult:
    try:
        text = caller.complete(
            prompt,
            purpose=purpose,
            attribute=predicates[0].attribute if predicates else "",
            system="Classify one attribute's workload predicates. JSON only.",
            max_tokens=220,
        )
    except BudgetExhausted:
        labels = {
            pred.pred_id: PredicateLabel("NULL", "failed")
            for pred in predicates
        }
        return ClassifyResult(labels, "budget", "", purpose)
    except Exception:
        labels = {
            pred.pred_id: PredicateLabel("NULL", "failed")
            for pred in predicates
        }
        return ClassifyResult(labels, "error", "", purpose)
    present, labels = parse_labels(text, predicates)
    source = "value" if purpose == "sig_value" else "document"
    if present is False:
        source = source + "+absent"
    return ClassifyResult(labels, source, text, purpose)


def main() -> int:
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    report = audit_workload(queries)
    predicates = enumerate_predicates(report.occurrences, report.signature_eligible)
    by_attr: dict[str, list] = defaultdict(list)
    for pred in predicates:
        by_attr[pred.attribute].append(pred)

    rows = load_rows(APRIME)
    docs = {doc.doc_id: doc.text for doc in documents_for("Med")}
    dest = OUT / "artifacts" / "aprime_model_sig.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(APRIME, dest)

    ledger = TokenLedger(theta=BUDGET, seed=42)
    caller = make_caller(ledger, model=DEFAULT_MODEL, max_tokens=220)
    cache: dict[tuple[str, str], ClassifyResult] = {}
    cache_lock = threading.Lock()
    raw_dir = OUT / "step5_raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    status_counts = Counter()
    purpose_tokens = Counter()
    value_resolved = []
    doc_resolved = []
    value_jobs = []
    seen_values: set[tuple[str, str]] = set()
    for attr, preds in by_attr.items():
        table, col = attr.split(".", 1)
        model_preds = [p for p in preds if needs_model(p)]
        if table not in rows or not model_preds:
            continue
        for row in rows[table]:
            value = row.get(col)
            if value_is_missing(value):
                continue
            key = (attr, str(value))
            if key in seen_values:
                continue
            seen_values.add(key)
            value_jobs.append((attr, row.get("doc_id"), str(value), model_preds))

    def write_raw(kind: str, attr: str, doc_id: str, value, result: ClassifyResult, index: int) -> None:
        (raw_dir / f"{kind}_{index}.json").write_text(
            json.dumps({
                "kind": kind,
                "attribute": attr,
                "doc_id": doc_id,
                "value": value,
                "raw": result.raw,
                "source": result.source,
                "labels": {
                    key: {"sql_truth": lab.sql_truth, "classifier_status": lab.classifier_status}
                    for key, lab in result.labels.items()
                },
            }, indent=2)
        )

    n_cache_hits = 0
    n_value_calls = 0
    n_doc_calls = 0

    def run_value(job):
        attr, doc_id, value, preds = job
        result = classify_one(caller, value_prompt(attr, value, preds), "sig_value", preds)
        with cache_lock:
            cache[(attr, value)] = result
        return attr, doc_id, value, result

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(run_value, job) for job in value_jobs]
        for index, future in enumerate(as_completed(futures), 1):
            attr, doc_id, value, result = future.result()
            n_value_calls += 1
            value_resolved.append(attr)
            write_raw("value", attr, doc_id, value, result, index)
            if index == 1 or index % 50 == 0:
                print(f"step5 value {index}/{len(futures)} spent={ledger.spent}", flush=True)

    results_by_row: dict[tuple[str, str, str], dict[str, PredicateLabel]] = {}
    doc_jobs = []
    for attr, preds in by_attr.items():
        table, col = attr.split(".", 1)
        model_preds = [p for p in preds if needs_model(p)]
        if table not in rows:
            continue
        for row in rows[table]:
            doc_id = row.get("doc_id")
            value = row.get(col)
            labels = emptiness_labels(preds, value_is_missing(value))
            cached = None if value_is_missing(value) else cache.get((attr, str(value)))
            if cached is not None:
                n_cache_hits += 1
                labels.update(cached.labels)
                uncertain = any(lab.classifier_status != "known" for lab in cached.labels.values())
            else:
                uncertain = True
            if model_preds and (value_is_missing(value) or uncertain):
                doc_jobs.append((attr, doc_id, None if value_is_missing(value) else str(value), model_preds))
            results_by_row[(table, doc_id, attr)] = labels

    def run_doc(job):
        attr, doc_id, value, preds = job
        text = clip_doc(docs.get(doc_id, ""), attr)
        result = classify_one(caller, document_prompt(attr, value, preds, text), "sig_document", preds)
        return attr, doc_id, value, result

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(run_doc, job) for job in doc_jobs]
        for index, future in enumerate(as_completed(futures), 1):
            attr, doc_id, value, result = future.result()
            n_doc_calls += 1
            doc_resolved.append(attr)
            write_raw("document", attr, doc_id, value, result, index)
            table = attr.split(".", 1)[0]
            labels = dict(results_by_row.get((table, doc_id, attr)) or {})
            labels = merge_atoms(labels, result.labels, set(result.labels))
            results_by_row[(table, doc_id, attr)] = labels
            if index == 1 or index % 50 == 0:
                print(f"step5 document {index}/{len(futures)} spent={ledger.spent}", flush=True)

    for labels in results_by_row.values():
        for lab in labels.values():
            status_counts[lab.classifier_status] += 1

    con = sqlite3.connect(dest)
    try:
        existing = {
            table: {info[1] for info in con.execute(f"PRAGMA table_info({_q(table)})")}
            for (table,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
            )
        }
        for pred in predicates:
            if pred.table in existing and pred.sig_name not in existing[pred.table]:
                con.execute(f"ALTER TABLE {_q(pred.table)} ADD COLUMN {_q(pred.sig_name)} INTEGER")
                existing[pred.table].add(pred.sig_name)
        for (table, doc_id, attr), labels in results_by_row.items():
            cells = labels_to_cells(labels)
            preds = [p for p in by_attr[attr] if p.sig_name in existing.get(table, ())]
            if not preds:
                continue
            assignments = ", ".join(f"{_q(p.sig_name)} = ?" for p in preds)
            con.execute(
                f"UPDATE {_q(table)} SET {assignments} WHERE doc_id = ?",
                [cells.get(p.pred_id) for p in preds] + [doc_id],
            )
        con.commit()
    finally:
        con.close()

    for rec in ledger.records:
        purpose_tokens[rec.purpose] += rec.tokens

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    rewrites = {row["query_id"]: rewrite_sql(row["sql"], predicates) for row in test}
    test_report = score_with_rewrites(test, rewrites, dest, gold, "Med")
    aprime = json.loads(APRIME_REPORT.read_text()) if APRIME_REPORT.is_file() else {}
    step4 = json.loads(STEP4.read_text()) if STEP4.is_file() else {}

    agreement = {}
    if GOLD_SIG_DB.is_file():
        gold_con = sqlite3.connect(GOLD_SIG_DB)
        pred_con = sqlite3.connect(dest)
        try:
            for pred in predicates:
                try:
                    gold_rows = {
                        row[0]: row[1]
                        for row in gold_con.execute(
                            f"SELECT doc_id, {_q(pred.sig_name)} FROM {_q(pred.table)}"
                        )
                    }
                    pred_rows = {
                        row[0]: row[1]
                        for row in pred_con.execute(
                            f"SELECT doc_id, {_q(pred.sig_name)} FROM {_q(pred.table)}"
                        )
                    }
                except sqlite3.Error:
                    continue
                n = 0
                match = 0
                for doc_id, gval in gold_rows.items():
                    if doc_id not in pred_rows:
                        continue
                    n += 1
                    if gval == pred_rows[doc_id]:
                        match += 1
                agreement[pred.pred_id] = {
                    "attribute": pred.attribute,
                    "operator": pred.operator,
                    "literal": pred.literal,
                    "n": n,
                    "agree": match,
                    "rate": (match / n) if n else None,
                }
        finally:
            gold_con.close()
            pred_con.close()

    payload = {
        "step": 5,
        "budget": BUDGET,
        "tokens_spent": ledger.spent,
        "token_split": dict(purpose_tokens),
        "n_value_calls": n_value_calls,
        "n_document_calls": n_doc_calls,
        "n_cache_hits": n_cache_hits,
        "value_resolved_attributes": sorted(set(value_resolved)),
        "document_resolved_attributes": sorted(set(doc_resolved)),
        "classification_scale": "vocabulary_sized" if n_doc_calls == 0 else (
            "mixed" if n_value_calls else "corpus_sized"
        ),
        "classifier_status": dict(status_counts),
        "mean_structure_f2": float(test_report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(test_report),
        "mean_per_query_product": mean_per_query_product(test_report),
        "vs_aprime": {
            "structure_f2": float(test_report.get("mean_structure_f2") or 0.0)
            - float(aprime.get("mean_structure_f2") or 0.0),
            "cell_f1_20": mean_cell_f1_20(test_report)
            - float(aprime.get("mean_cell_f1_at_0.20") or 0.0),
            "product": mean_per_query_product(test_report)
            - float(aprime.get("mean_per_query_product") or 0.0),
        },
        "vs_step4_oracle": {
            "structure_f2": float(test_report.get("mean_structure_f2") or 0.0)
            - float(step4.get("mean_structure_f2") or 0.0),
            "cell_f1_20": mean_cell_f1_20(test_report)
            - float(step4.get("mean_cell_f1_at_0.20") or 0.0),
            "product": mean_per_query_product(test_report)
            - float(step4.get("mean_per_query_product") or 0.0),
        },
        "gold_signature_agreement_eval_only": {
            "mean_rate": (
                sum(item["rate"] for item in agreement.values() if item["rate"] is not None)
                / max(1, sum(1 for item in agreement.values() if item["rate"] is not None))
            ),
            "per_predicate": agreement,
        },
        "test_empty_query_count": sum(
            1 for row in test_report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0
        ),
        "sqlite_path": str(dest),
        "scope_limit_full_value_required": report.full_value_required,
        "row_counts": {table: len(items) for table, items in rows.items()},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "step5_model.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({k: payload[k] for k in payload if k != "gold_signature_agreement_eval_only"}, indent=2, default=str)[:5000])
    print("agreement_mean", payload["gold_signature_agreement_eval_only"]["mean_rate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Eval-only: confusion matrix, attribute oracles, cacheability. Zero tokens."""

from __future__ import annotations

import json
import random
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.signature import audit_workload, enumerate_predicates, rewrite_sql
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

APRIME = next((ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "databases").glob("*.db"))
GOLD_SIG = ROOT / "results" / "quwarts_med_signatures" / "artifacts" / "aprime_gold_sig.db"
MODEL_SIG = ROOT / "results" / "quwarts_med_signatures" / "artifacts" / "aprime_model_sig.db"
RAW = ROOT / "results" / "quwarts_med_signatures" / "step5_raw"
OUT = ROOT / "results" / "quwarts_med_signatures"
NAME_COLS = {
    "disease": "disease_name",
    "drug": "generic_name",
    "institution": "institution_name",
}
SURFACE_FALLBACK = {
    "drug": "disease_name",
    "institution": "research_diseases",
}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _cell(value) -> str:
    if value is None:
        return "NULL"
    if value == 1:
        return "TRUE"
    if value == 0:
        return "FALSE"
    return "NULL"


def _fold(value) -> str:
    return " ".join(str(value or "").replace("_", " ").casefold().split())


def load_table(path: Path, table: str) -> list[dict]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in con.execute(f"SELECT * FROM {_q(table)}")]
    finally:
        con.close()


def columns(path: Path, table: str) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {row[1] for row in con.execute(f"PRAGMA table_info({_q(table)})")}
    finally:
        con.close()


def score_db(path: Path, test, predicates, gold) -> dict:
    rewrites = {row["query_id"]: rewrite_sql(row["sql"], predicates) for row in test}
    report = score_with_rewrites(test, rewrites, path, gold, "Med")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "test_empty": sum(1 for row in report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0),
        "per_query_product": {
            row["query_id"]: float(row.get("structure_f2") or 0.0)
            * float(row.get("cell_f1_20") or row.get("cell_f1_05") or 0.0)
            for row in report.get("per_query") or []
        },
    }


def copy_swap(dest: Path, base: Path, donor: Path, preds) -> None:
    if dest.exists():
        dest.unlink()
    shutil.copy2(base, dest)
    src = sqlite3.connect(donor)
    dst = sqlite3.connect(dest)
    try:
        for pred in preds:
            src_cols = {row[1] for row in src.execute(f"PRAGMA table_info({_q(pred.table)})")}
            dst_cols = {row[1] for row in dst.execute(f"PRAGMA table_info({_q(pred.table)})")}
            if pred.sig_name not in src_cols or pred.sig_name not in dst_cols:
                continue
            if "doc_id" not in src_cols or "doc_id" not in dst_cols:
                continue
            for doc_id, value in src.execute(
                f"SELECT doc_id, {_q(pred.sig_name)} FROM {_q(pred.table)}"
            ):
                dst.execute(
                    f"UPDATE {_q(pred.table)} SET {_q(pred.sig_name)} = ? WHERE doc_id = ?",
                    (value, doc_id),
                )
        dst.commit()
    finally:
        src.close()
        dst.close()


def load_raw_status() -> dict[tuple[str, str, str], dict]:
    """(attribute, doc_id, pred_id) -> {status, source_present, kind}."""

    by_row: dict[tuple[str, str], dict] = {}
    if not RAW.is_dir():
        return {}
    files = sorted(RAW.glob("*.json"), key=lambda p: (0 if p.name.startswith("value_") else 1, p.name))
    for path in files:
        payload = json.loads(path.read_text())
        attr = payload.get("attribute")
        doc_id = payload.get("doc_id")
        if not attr or not doc_id:
            continue
        key = (attr, doc_id)
        entry = by_row.get(key, {"source_present": None, "kind": None, "labels": {}})
        raw = payload.get("raw") or ""
        present = None
        if "source_present" in raw:
            low = raw.lower()
            if "source_present" in low:
                if '"source_present": false' in low or '"source_present":false' in low:
                    present = False
                elif '"source_present": true' in low or '"source_present":true' in low:
                    present = True
        if payload.get("source", "").endswith("absent"):
            present = False
        entry["source_present"] = present if present is not None else entry.get("source_present")
        entry["kind"] = payload.get("kind") or entry.get("kind")
        entry["labels"].update(payload.get("labels") or {})
        by_row[key] = entry
    out = {}
    for (attr, doc_id), entry in by_row.items():
        for pred_id, lab in (entry.get("labels") or {}).items():
            out[(attr, doc_id, pred_id)] = {
                "status": (lab or {}).get("classifier_status") or "unknown",
                "model_label": (lab or {}).get("sql_truth"),
                "source_present": entry.get("source_present"),
                "kind": entry.get("kind"),
            }
    return out


def bucket(gold: str, model: str, status: str) -> str:
    status = status or "unknown"
    if gold == model and gold in {"TRUE", "FALSE", "NULL"}:
        return "exact_agreement"
    if gold == "TRUE" and model == "NULL" and status in {"failed", "uncertain", "grounding-abstained"}:
        return "TRUE/NULL/abstained"
    if gold == "TRUE" and model == "NULL":
        return "TRUE/NULL/other"
    if gold == "TRUE" and model == "FALSE" and status == "known":
        return "TRUE/FALSE/known"
    if gold == "FALSE" and model == "TRUE" and status == "known":
        return "FALSE/TRUE/known"
    if gold == "FALSE" and model == "NULL" and status == "uncertain":
        return "FALSE/NULL/uncertain"
    if gold == "FALSE" and model == "NULL":
        return "FALSE/NULL/other"
    if gold == "NULL" and model in {"TRUE", "FALSE"} and status == "known":
        return "NULL/valued/known"
    if gold == "NULL" and model in {"TRUE", "FALSE"}:
        return "NULL/valued/other"
    return f"{gold}/{model}/{status}"


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    report = audit_workload(queries)
    predicates = enumerate_predicates(report.occurrences, report.signature_eligible)
    gold_tables = load_ground_truth(gold_name("Med"))
    raw = load_raw_status()
    test_ids = {row["query_id"] for row in test}
    q_weight = {
        pred.pred_id: sum(1 for qid in pred.query_ids if qid in test_ids)
        for pred in predicates
    }
    q_weight_all = {pred.pred_id: len(pred.query_ids) for pred in predicates}

    aprime_rows = {
        table: {row["doc_id"]: row for row in load_table(APRIME, table) if row.get("doc_id")}
        for table in ("disease", "drug", "institution")
    }
    gold_rows = {pred.table: load_table(GOLD_SIG, pred.table) for pred in predicates}
    model_rows = {pred.table: load_table(MODEL_SIG, pred.table) for pred in predicates}
    gold_by_doc = {
        table: {row["doc_id"]: row for row in rows if row.get("doc_id")}
        for table, rows in gold_rows.items()
    }
    model_by_doc = {
        table: {row["doc_id"]: row for row in rows if row.get("doc_id")}
        for table, rows in model_rows.items()
    }

    cells = []
    per_pred = {}
    for pred in predicates:
        counts = Counter()
        gold_true = 0
        recovered = 0
        samples = defaultdict(list)
        for doc_id, grow in gold_by_doc.get(pred.table, {}).items():
            mrow = model_by_doc.get(pred.table, {}).get(doc_id) or {}
            g = _cell(grow.get(pred.sig_name))
            m = _cell(mrow.get(pred.sig_name))
            meta = raw.get((pred.attribute, doc_id, pred.pred_id), {})
            status = meta.get("status") or ("known" if m in {"TRUE", "FALSE"} else "unknown")
            if meta.get("source_present") is False and m == "NULL":
                status = "grounding-abstained"
            key = bucket(g, m, status)
            counts[key] += 1
            if g == "TRUE":
                gold_true += 1
                if m == "TRUE":
                    recovered += 1
            arow = aprime_rows.get(pred.table, {}).get(doc_id) or {}
            if len(samples[key]) < 20:
                samples[key].append({
                    "doc_id": doc_id,
                    "attribute": pred.attribute,
                    "operator": pred.operator,
                    "literal": pred.literal,
                    "gold": g,
                    "model": m,
                    "status": status,
                    "source_present": meta.get("source_present"),
                    "raw_kind": meta.get("kind"),
                    "aprime_value": arow.get(pred.column),
                    "aprime_name": arow.get(NAME_COLS.get(pred.table, ""), arow.get(SURFACE_FALLBACK.get(pred.table, ""))),
                })
            cells.append((pred, doc_id, g, m, status, key))
        per_pred[pred.pred_id] = {
            "attribute": pred.attribute,
            "operator": pred.operator,
            "literal": pred.literal,
            "n_test_queries": q_weight[pred.pred_id],
            "n_queries": q_weight_all[pred.pred_id],
            "counts": dict(counts),
            "gold_true": gold_true,
            "true_recall": (recovered / gold_true) if gold_true else None,
            "weighted_true_miss": (gold_true - recovered) * q_weight[pred.pred_id],
            "samples": {name: items for name, items in samples.items() if name != "exact_agreement"},
        }

    overall = Counter()
    weighted = Counter()
    for pred in predicates:
        for name, n in per_pred[pred.pred_id]["counts"].items():
            overall[name] += n
            weighted[name] += n * q_weight[pred.pred_id]
    gold_true_all = sum(item["gold_true"] for item in per_pred.values())
    recovered_all = sum(
        int(round((item["true_recall"] or 0) * item["gold_true"]))
        for item in per_pred.values()
    )
    by_attr_recall = {}
    for pred in predicates:
        item = per_pred[pred.pred_id]
        agg = by_attr_recall.setdefault(
            pred.attribute,
            {"gold_true": 0, "recovered": 0, "weighted_true_miss": 0, "n_test_queries": 0},
        )
        agg["gold_true"] += item["gold_true"]
        agg["recovered"] += int(round((item["true_recall"] or 0) * item["gold_true"]))
        agg["weighted_true_miss"] += item["weighted_true_miss"]
        agg["n_test_queries"] = max(agg["n_test_queries"], item["n_test_queries"])
    for name, agg in by_attr_recall.items():
        agg["true_recall"] = (agg["recovered"] / agg["gold_true"]) if agg["gold_true"] else None

    major = ["TRUE/NULL/abstained", "TRUE/FALSE/known", "FALSE/TRUE/known", "FALSE/NULL/uncertain", "NULL/valued/known", "exact_agreement"]
    sample_out = {}
    rng = random.Random(42)
    for name in major:
        pool = []
        for pred in predicates:
            pool.extend(per_pred[pred.pred_id]["samples"].get(name, []))
        rng.shuffle(pool)
        sample_out[name] = pool[:20]

    confusion = {
        "label": "eval_diagnostic",
        "overall_counts": dict(overall),
        "query_weighted_counts": dict(weighted),
        "gold_true_recall_excluding_gold_null": {
            "recovered": recovered_all,
            "gold_true": gold_true_all,
            "recall": (recovered_all / gold_true_all) if gold_true_all else None,
        },
        "per_attribute_true_recall": by_attr_recall,
        "per_predicate": {
            pred.pred_id: {
                k: v for k, v in per_pred[pred.pred_id].items() if k != "samples"
            }
            for pred in predicates
        },
        "samples": sample_out,
        "note": (
            "failed/source_present=false mapped to grounding-abstained when model sql_truth is NULL. "
            "true_recall excludes gold-null rows."
        ),
    }

    # Attribute oracles.
    tmp = OUT / "artifacts" / "oracle_attr"
    tmp.mkdir(parents=True, exist_ok=True)
    attrs = sorted({pred.attribute for pred in predicates})
    base5 = score_db(MODEL_SIG, test, predicates, gold_tables)
    base4 = score_db(GOLD_SIG, test, predicates, gold_tables)
    one_at_a_time = {}
    leave_one_out = {}
    for attr in attrs:
        subset = [pred for pred in predicates if pred.attribute == attr]
        up = tmp / f"up_{attr.replace('.', '_')}.db"
        down = tmp / f"down_{attr.replace('.', '_')}.db"
        copy_swap(up, MODEL_SIG, GOLD_SIG, subset)
        copy_swap(down, GOLD_SIG, MODEL_SIG, subset)
        up_score = score_db(up, test, predicates, gold_tables)
        down_score = score_db(down, test, predicates, gold_tables)
        one_at_a_time[attr] = {
            **{k: up_score[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product", "test_empty")},
            "delta_product_vs_step5": up_score["mean_per_query_product"] - base5["mean_per_query_product"],
            "delta_structure_vs_step5": up_score["mean_structure_f2"] - base5["mean_structure_f2"],
            "delta_cell_vs_step5": up_score["mean_cell_f1_at_0.20"] - base5["mean_cell_f1_at_0.20"],
        }
        leave_one_out[attr] = {
            **{k: down_score[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product", "test_empty")},
            "delta_product_vs_step4": down_score["mean_per_query_product"] - base4["mean_per_query_product"],
            "drop_from_oracle": base4["mean_per_query_product"] - down_score["mean_per_query_product"],
        }
        print(
            f"attr {attr} +gold {one_at_a_time[attr]['delta_product_vs_step5']:+.4f} "
            f"loo_drop {leave_one_out[attr]['drop_from_oracle']:+.4f}",
            flush=True,
        )

    # Cacheability on gold names (benchmark characterization only).
    cacheability = {}
    gold_csv = gold_tables
    gold_id_name: dict[str, dict[str, str]] = {}
    for table, rows in gold_csv.items():
        mapping = {}
        name_col = NAME_COLS.get(table)
        if not name_col:
            continue
        for row in rows:
            stem = str(row.get("id") or "").strip()
            if not stem:
                continue
            mapping[stem] = _fold(row.get(name_col))
        gold_id_name[table] = mapping
    for pred in predicates:
        by_key: dict[str, set[str]] = defaultdict(set)
        n = 0
        for doc_id, grow in gold_by_doc.get(pred.table, {}).items():
            stem = Path(str(doc_id)).stem
            key = gold_id_name.get(pred.table, {}).get(stem)
            if not key:
                continue
            by_key[key].add(_cell(grow.get(pred.sig_name)))
            n += 1
        conflicts = {name: sorted(values) for name, values in by_key.items() if len(values) > 1}
        cacheability[pred.pred_id] = {
            "attribute": pred.attribute,
            "operator": pred.operator,
            "literal": pred.literal,
            "cache_key": NAME_COLS.get(pred.table),
            "n_keys": len(by_key),
            "n_conflict_keys": len(conflicts),
            "constant_per_name": len(conflicts) == 0,
            "conflict_examples": list(conflicts.items())[:5],
        }

    n_const = sum(1 for item in cacheability.values() if item["constant_per_name"])
    payload = {
        "confusion": confusion,
        "attribute_oracles": {
            "label": "oracle_diagnostic",
            "step5": {k: base5[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product", "test_empty")},
            "step4": {k: base4[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product", "test_empty")},
            "one_at_a_time_replace_model_with_gold": one_at_a_time,
            "leave_one_out_restore_model_on_oracle": leave_one_out,
            "ranked_standalone_gain": sorted(
                ((name, row["delta_product_vs_step5"]) for name, row in one_at_a_time.items()),
                key=lambda item: -item[1],
            ),
            "ranked_oracle_necessity": sorted(
                ((name, row["drop_from_oracle"]) for name, row in leave_one_out.items()),
                key=lambda item: -item[1],
            ),
        },
        "cacheability_gold_eval_only": {
            "key": "normalized gold entity name",
            "n_predicates_constant_per_name": n_const,
            "n_predicates": len(cacheability),
            "per_predicate": cacheability,
            "note": "Benchmark characterization. Not a method input.",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "step5_diagnostics.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    summary = {
        "wrote": str(path),
        "gold_true_recall": confusion["gold_true_recall_excluding_gold_null"],
        "overall": confusion["overall_counts"],
        "weighted": confusion["query_weighted_counts"],
        "attr_true_recall": {
            name: row["true_recall"] for name, row in sorted(by_attr_recall.items())
        },
        "standalone_top": payload["attribute_oracles"]["ranked_standalone_gain"][:8],
        "loo_top": payload["attribute_oracles"]["ranked_oracle_necessity"][:8],
        "cache_constant": n_const,
        "n_preds": len(cacheability),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

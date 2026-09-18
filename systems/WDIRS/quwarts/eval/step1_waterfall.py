"""Step 1 diagnostics. Gold is read only here. Zero tokens."""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.extract import EvidenceStore
from quwarts.core.models import FrozenPortfolio
from quwarts.core.pipeline import serve_plans
from quwarts.core.population import apply_population, _commit
from quwarts.experiments.player_case80 import execute, split_80_20
from quwarts.experiments.synthesize_case80 import (
    documents_for,
    gold_name,
    queries_for,
)

SCORE_DB = next((ROOT / "results" / "quwarts_med_repair_round" / "artifacts" / "databases").glob("*.db"))
EVIDENCE = ROOT / "results" / "quwarts_med_repair80_diag" / "artifacts" / "evidence"
MANIFEST = ROOT / "results" / "quwarts_med_repair80_diag" / "artifacts" / "runs" / "manifest.json"
OUT = ROOT / "results" / "quwarts_med_step1" / "step1_report.json"
CORPUS = ROOT / "source_data" / "Healthcare"
SOURCE_SUBDIRS = {
    "disease": "disease_small",
    "drug": "drug_small",
    "institution": "institutes_small",
}
JOIN_KEYS = {
    "disease": ("disease_name",),
    "drug": ("disease_name",),
    "institution": ("research_diseases",),
}
STAGES = (
    "gold_entity",
    "source_file_found",
    "file_processed",
    "entity_emitted",
    "candidate_row",
    "validation_accepted",
    "dedup_survived",
    "populated_row",
    "query_visible_row",
    "aligned_output_row",
)


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _stem(value: Any) -> str:
    return Path(str(value or "")).stem


def _as_int_stem(value: Any) -> str:
    text = _stem(value)
    try:
        return str(int(text))
    except (TypeError, ValueError):
        return text


def load_portfolio(statements: dict[str, str]) -> FrozenPortfolio:
    from quwarts.core.logical import extend_logical_schema
    from quwarts.core.materialize import refresh_coverage_from_sqlite, refresh_schema_from_sqlite

    manifest = json.loads(MANIFEST.read_text())
    fields = {name: manifest[name] for name in FrozenPortfolio.model_fields if name in manifest}
    portfolio = FrozenPortfolio.model_validate(fields)
    for item in portfolio.databases:
        item.sqlite_path = str(SCORE_DB)
    portfolio.logical_schema = extend_logical_schema(portfolio.logical_schema, statements.values())
    for config, item in zip(portfolio.configurations, portfolio.databases):
        refresh_schema_from_sqlite(config.schema_, item.sqlite_path)
        item.coverage = refresh_coverage_from_sqlite(item.coverage, item.sqlite_path)
    return portfolio


def table_rows(db: Path, table: str) -> list[dict[str, Any]]:
    con = sqlite3.connect(db)
    try:
        cols = [info[1] for info in con.execute(f"PRAGMA table_info({_q(table)})")]
        return [
            {col: value for col, value in zip(cols, row)}
            for row in con.execute(f"SELECT * FROM {_q(table)}")
        ]
    finally:
        con.close()


def index_pred(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        for raw in (row.get("id"), row.get("doc_id")):
            if raw in (None, ""):
                continue
            found[_stem(raw)] = row
            found[_as_int_stem(raw)] = row
    return found


def nonempty(value: Any) -> bool:
    return value not in (None, "")


def first_loss(flags: dict[str, bool]) -> str | None:
    prev = True
    for name in STAGES:
        ok = flags[name]
        if prev and not ok:
            return f"{name}_lost"
        prev = ok
    return None


def waterfall(gold, documents, store, portfolio, workload, test, plans) -> dict[str, Any]:
    by_entity: dict[str, list] = defaultdict(list)
    for doc in documents:
        entity = (doc.metadata or {}).get("entity") or str(doc.doc_id).split("/", 1)[0]
        by_entity[entity].append(doc)

    records = list(store.records.values())
    recs_by_doc: dict[str, list] = defaultdict(list)
    for rec in records:
        recs_by_doc[rec.doc_id].append(rec)
        recs_by_doc[_stem(rec.doc_id)].append(rec)

    config = portfolio.configurations[0]
    pop_rows = apply_population(records, config, workload)
    before_merge = []
    grouped: dict[str, list] = defaultdict(list)
    for rec in records:
        grouped[rec.doc_id].append(rec)
    for doc_id, items in grouped.items():
        row = {"doc_id": doc_id}
        accepted = False
        emitted = False
        for rec in items:
            if nonempty(rec.surface_value):
                emitted = True
            committed = _commit(rec, config.pop)
            if committed not in (None, ""):
                accepted = True
                row[rec.attribute] = committed
        row["_emitted"] = emitted
        row["_accepted"] = accepted
        before_merge.append(row)

    pop_by_doc = {_stem(row.get("doc_id")): row for row in pop_rows}
    pop_by_doc.update({_as_int_stem(row.get("doc_id")): row for row in pop_rows})
    cand_by_doc = {_stem(row.get("doc_id")): row for row in before_merge}
    cand_by_doc.update({_as_int_stem(row.get("doc_id")): row for row in before_merge})

    merge_on = any(cfg.strategy == "merge" for cfg in config.pop.er.values())
    pred_tables = {name: table_rows(SCORE_DB, name) for name in gold}
    pred_index = {name: index_pred(rows) for name, rows in pred_tables.items()}

    visible_stems: dict[str, set[str]] = defaultdict(set)
    for row in test:
        plan = plans.get(row["query_id"]) or {}
        sql = plan.get("sql") if isinstance(plan, dict) else plan
        if not sql:
            continue
        lowered = sql.lower()
        for table in gold:
            if table.lower() not in lowered:
                continue
            for prow in pred_tables[table]:
                stem = _stem(prow.get("doc_id"))
                if any(nonempty(prow.get(key)) for key in JOIN_KEYS[table]) or nonempty(prow.get("id")):
                    visible_stems[table].add(stem)
                    visible_stems[table].add(_as_int_stem(stem))

    report = {}
    for table, grows in gold.items():
        files = {path.stem: path for path in (CORPUS / SOURCE_SUBDIRS[table]).glob("*.txt")}
        docs = {_stem(doc.doc_id): doc for doc in by_entity.get(table, [])}
        pred = pred_index[table]
        lost = Counter()
        per = []
        flags_count = Counter()
        for grow in grows:
            gid = str(grow.get("id") or "").strip()
            keys = {gid, _stem(gid), _as_int_stem(gid)}
            file_hit = any(key in files for key in keys)
            doc_hit = any(key in docs for key in keys)
            recs = []
            for key in keys:
                recs.extend(recs_by_doc.get(key, []))
                recs.extend(recs_by_doc.get(f"{table}/{key}.txt", []))
                recs.extend(recs_by_doc.get(f"{table}/{key}", []))
            processed = bool(recs)
            emitted = any(nonempty(rec.surface_value) for rec in recs)
            cand = None
            for key in keys:
                cand = cand or cand_by_doc.get(key)
            candidate = cand is not None
            validated = bool(cand and cand.get("_accepted"))
            survived = any(pop_by_doc.get(key) is not None for key in keys)
            prow = None
            for key in keys:
                prow = prow or pred.get(key)
            populated = prow is not None
            visible = any(key in visible_stems[table] for key in keys) if populated else False
            aligned = populated
            flags = {
                "gold_entity": True,
                "source_file_found": file_hit,
                "file_processed": processed,
                "entity_emitted": emitted,
                "candidate_row": candidate,
                "validation_accepted": validated,
                "dedup_survived": survived,
                "populated_row": populated,
                "query_visible_row": visible,
                "aligned_output_row": aligned,
            }
            reason = first_loss(flags)
            if reason:
                lost[reason] += 1
            for name, ok in flags.items():
                flags_count[name] += int(ok)
            if reason:
                per.append({"id": gid, "lost_at": reason, "merge_on": merge_on})
        n = len(grows)
        cause = dominant_cause(lost, flags_count, n)
        report[table] = {
            "n_gold": n,
            "counts": {name: int(flags_count[name]) for name in STAGES},
            "first_loss": dict(lost),
            "dominant_cause": cause,
            "merge_enabled": merge_on,
            "db_rows": len(pred_tables[table]),
            "lost_sample": per[:12],
        }
    return report


def dominant_cause(lost: Counter, flags: Counter, n: int) -> dict[str, Any]:
    if not lost:
        return {"class": "none", "detail": "every gold entity reaches the database"}
    top, count = lost.most_common(1)[0]
    if top in {"validation_accepted_lost", "dedup_survived_lost", "populated_row_lost", "candidate_row_lost"}:
        klass = "correctness bug"
    elif top in {"entity_emitted_lost", "file_processed_lost"}:
        klass = "genuine recall miss"
    elif top == "aligned_output_row_lost":
        klass = "identity bug"
    elif top == "query_visible_row_lost":
        klass = "representation issue"
    elif top == "source_file_found_lost":
        klass = "corpus miss"
    else:
        klass = "unclassified"
    return {"class": klass, "first_transition": top, "n": count, "of": n}


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def factorization(test, plans, gold_tables) -> dict[str, Any]:
    from spp.aggregation_metrics import (
        MetricConfig,
        _gold_numeric_range,
        _numeric_range_err,
        align_columns,
        align_rows,
        detect_grouping_errors,
        gold_table_from_sql,
        predicted_table_from_rows,
        schema_from_sql,
        string_sim,
    )
    from spp.config_grid import _build_in_memory_db

    gold_conn = _build_in_memory_db(gold_tables)
    config = MetricConfig()
    per_col: dict[str, dict[str, Any]] = {}
    range_errs: list[float] = []
    rel_errs: list[float] = []
    string_scores: list[float] = []
    try:
        for row in test:
            plan = plans.get(row["query_id"]) or {}
            pred_sql = plan.get("sql") if isinstance(plan, dict) else plan
            path = (plan.get("sqlite_path") if isinstance(plan, dict) else None) or str(SCORE_DB)
            schema = schema_from_sql(row["sql"])
            if not schema.get("is_aggregation"):
                continue
            gold_rows = execute(gold_conn, row["sql"])
            local = sqlite3.connect(path)
            try:
                pred_rows = execute(local, pred_sql) if pred_sql else []
            finally:
                local.close()
            gold = gold_table_from_sql(gold_rows, row["sql"])
            pred = predicted_table_from_rows(pred_rows, gold=gold)
            cols = align_columns(pred, gold, config=config)
            rows_s = align_rows(pred, gold, cols, config=config, tier="semantic")
            if not rows_s["matched_pairs"]:
                rows_s = align_rows(pred, gold, cols, config=config, tier="normalized")
            if not rows_s["matched_pairs"]:
                rows_s = align_rows(pred, gold, cols, config=config, tier="exact")
            grouping = detect_grouping_errors(pred, gold, cols, config=config)
            excluded = set(grouping.get("merge_pred_indices") or ()) | set(
                grouping.get("split_pred_indices") or ()
            )
            pairs = [(pi, gi) for pi, gi, _ in rows_s["matched_pairs"] if pi not in excluded]
            n_hat = len(pred.rows)
            n_gold = len(gold.rows)
            m = len(pairs)
            ranked = list(gold.by_role("measure")) or list(gold.by_role("key"))
            gold_to_pred = cols["gold_to_pred"]
            for column in ranked:
                if str(column.name).split(".")[-1].lower() == "id":
                    continue
                pred_name = gold_to_pred.get(column.name)
                scores = []
                for pi, gi in pairs:
                    if pred_name is None:
                        scores.append(0.0)
                        continue
                    pv = pred.rows[pi].get(pred_name)
                    gv = gold.rows[gi].get(column.name)
                    if column.type == "numeric":
                        lo, hi = _gold_numeric_range(gold, column.name)
                        range_err, _ = _numeric_range_err(
                            pv, gv, col_min=lo, col_max=hi, epsilon=config.epsilon,
                        )
                        if range_err is None:
                            scores.append(0.0)
                            continue
                        range_errs.append(range_err)
                        scores.append(max(0.0, 1.0 - min(range_err / 0.20, 1.0)))
                        gf = _to_float(gv)
                        pf = _to_float(pv)
                        if gf is not None and pf is not None and abs(gf) > 1e-12:
                            rel_errs.append(abs(pf - gf) / abs(gf))
                        elif gf is not None and pf is not None:
                            rel_errs.append(0.0 if abs(pf - gf) <= 1e-12 else math.inf)
                    else:
                        sim = string_sim(pv, gv, abbreviation_map=config.abbreviation_map)
                        string_scores.append(sim)
                        scores.append(sim)
                mean_aligned = sum(scores) / len(scores) if scores else 0.0
                key = f"{row['query_id']}::{column.name}"
                prec = (m / n_hat) if n_hat else 0.0
                rec = (m / n_gold) if n_gold else 0.0
                per_col[key] = {
                    "query_id": row["query_id"],
                    "column": column.name,
                    "type": column.type,
                    "role": column.role,
                    "operator": column.operator,
                    "n_pred": n_hat,
                    "n_gold": n_gold,
                    "n_aligned": m,
                    "alignment_precision": prec,
                    "alignment_recall": rec,
                    "mean_comparator_aligned": mean_aligned,
                    "P_c": prec * mean_aligned,
                    "R_c": rec * mean_aligned,
                }
    finally:
        gold_conn.close()

    def _hist(values: list[float], edges: list[tuple[str, float, float]]) -> dict[str, float]:
        finite = [v for v in values if math.isfinite(v)]
        if not finite:
            return {name: 0.0 for name, _, _ in edges}
        out = {}
        for name, lo, hi in edges:
            out[name] = sum(1 for v in finite if lo <= v < hi) / len(finite)
        return out

    numeric_pass = {
        "le_0.05": sum(1 for v in range_errs if v <= 0.05) / len(range_errs) if range_errs else None,
        "le_0.20": sum(1 for v in range_errs if v <= 0.20) / len(range_errs) if range_errs else None,
        "in_5_to_20": sum(1 for v in range_errs if 0.05 < v <= 0.20) / len(range_errs) if range_errs else None,
    }
    rel_pass = {
        "le_0.05": sum(1 for v in rel_errs if math.isfinite(v) and v <= 0.05) / len(rel_errs) if rel_errs else None,
        "le_0.20": sum(1 for v in rel_errs if math.isfinite(v) and v <= 0.20) / len(rel_errs) if rel_errs else None,
        "in_5_to_20": sum(1 for v in rel_errs if math.isfinite(v) and 0.05 < v <= 0.20) / len(rel_errs) if rel_errs else None,
    }
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in per_col.values():
        by_name[row["column"]].append(row)

    def _mean(items: list[dict[str, Any]], field: str) -> float:
        values = [float(item[field]) for item in items]
        return sum(values) / len(values) if values else 0.0

    return {
        "per_query_column": per_col,
        "per_column_mean": {
            name: {
                "n_queries": len(items),
                "mean_n_pred": _mean(items, "n_pred"),
                "mean_n_gold": _mean(items, "n_gold"),
                "mean_n_aligned": _mean(items, "n_aligned"),
                "mean_alignment_precision": _mean(items, "alignment_precision"),
                "mean_alignment_recall": _mean(items, "alignment_recall"),
                "mean_comparator_aligned": _mean(items, "mean_comparator_aligned"),
                "mean_P_c": _mean(items, "P_c"),
                "mean_R_c": _mean(items, "R_c"),
            }
            for name, items in sorted(by_name.items())
        },
        "aligned_numeric_range_error": {
            "n": len(range_errs),
            "mean": sum(range_errs) / len(range_errs) if range_errs else None,
            "median": sorted(range_errs)[len(range_errs) // 2] if range_errs else None,
            "pass_at": numeric_pass,
            "histogram": _hist(
                range_errs,
                [
                    ("exact_or_le_1pct", 0.0, 0.01),
                    ("1_to_5pct", 0.01, 0.05),
                    ("5_to_20pct", 0.05, 0.20),
                    ("20_to_100pct", 0.20, 1.0),
                    ("gt_100pct", 1.0, math.inf),
                ],
            ),
        },
        "aligned_numeric_relative_error": {
            "n": len(rel_errs),
            "finite": sum(1 for v in rel_errs if math.isfinite(v)),
            "mean_finite": (
                sum(v for v in rel_errs if math.isfinite(v))
                / max(1, sum(1 for v in rel_errs if math.isfinite(v)))
            )
            if rel_errs
            else None,
            "pass_at": rel_pass,
            "histogram": _hist(
                [v for v in rel_errs if math.isfinite(v)],
                [
                    ("exact_or_le_1pct", 0.0, 0.01),
                    ("1_to_5pct", 0.01, 0.05),
                    ("5_to_20pct", 0.05, 0.20),
                    ("20_to_100pct", 0.20, 1.0),
                    ("gt_100pct", 1.0, math.inf),
                ],
            ),
        },
        "aligned_string_sim": {
            "n": len(string_scores),
            "mean": sum(string_scores) / len(string_scores) if string_scores else None,
            "ge_0.90": (
                sum(1 for v in string_scores if v >= 0.90) / len(string_scores)
                if string_scores
                else None
            ),
            "histogram": _hist(
                string_scores,
                [
                    ("lt_0.50", 0.0, 0.50),
                    ("0.50_to_0.90", 0.50, 0.90),
                    ("ge_0.90", 0.90, 1.0000001),
                ],
            ),
        },
    }


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.core.workload import analyze_workload

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    train_sql = {row["query_id"]: row["sql"] for row in train}
    test_sql = {row["query_id"]: row["sql"] for row in test}
    documents = documents_for("Med")
    gold = load_ground_truth(gold_name("Med"))
    _, workload = analyze_workload(train_sql)
    portfolio = load_portfolio({**train_sql, **test_sql})
    store = EvidenceStore(EVIDENCE)
    plans = serve_plans(portfolio, {**train_sql, **test_sql})
    section_11 = waterfall(gold, documents, store, portfolio, workload, test, plans)
    section_12 = factorization(test, plans, gold)
    payload = {
        "score_db": str(SCORE_DB),
        "1_1_waterfall": section_11,
        "1_2_factorization": {
            k: v for k, v in section_12.items() if k != "per_query_column"
        },
        "1_2_per_query_column": section_12["per_query_column"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({
        "wrote": str(OUT),
        "1_1": {
            table: {
                "counts": row["counts"],
                "first_loss": row["first_loss"],
                "dominant_cause": row["dominant_cause"],
                "db_rows": row["db_rows"],
            }
            for table, row in section_11.items()
        },
        "1_2_columns": section_12["per_column_mean"],
        "1_2_numeric_range": section_12["aligned_numeric_range_error"],
        "1_2_numeric_relative": section_12["aligned_numeric_relative_error"],
        "1_2_string": section_12["aligned_string_sim"],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

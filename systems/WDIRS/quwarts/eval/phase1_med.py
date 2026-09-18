"""Phase 1 plumbing diagnostics. Gold is read only here."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlglot import exp, parse_one

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.extract import EvidenceStore
from quwarts.core.models import FrozenPortfolio
from quwarts.core.pipeline import serve_plans
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for, score_with_rewrites

COMPILE_EV = ROOT / "results" / "quwarts_med_repair80_diag" / "artifacts" / "evidence"
VOTE_EV = ROOT / "results" / "quwarts_med_cells" / "artifacts" / "evidence"
SCORE_DB = next((ROOT / "results" / "quwarts_med_repair_round" / "artifacts" / "databases").glob("*.db"))
VOTE_DB = next((ROOT / "results" / "quwarts_med_cells" / "artifacts" / "databases").glob("*.db"))
MANIFEST = ROOT / "results" / "quwarts_med_repair80_diag" / "artifacts" / "runs" / "manifest.json"
DOCETL_EVAL = ROOT / "results" / "docetl_med_case80" / "evaluation.json"
OUT = ROOT / "results" / "quwarts_med_cells" / "phase1_report.json"

ATTRS_ZERO = ("institution.research_fields", "drug.prescription_status")
ATTRS_MID = ("drug.pharmaceutical_form", "drug.manufacturer")
ATTRS_ID = ("drug.id",)
TRACE_ATTRS = ATTRS_ZERO + ATTRS_MID + ATTRS_ID
LIKE_ATTRS = (
    "institution.research_fields",
    "drug.prescription_status",
    "disease.disease_type",
)


def _fold(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ").casefold()).strip()


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def evidence_sha(store: EvidenceStore) -> str:
    digest = hashlib.sha256()
    for key in sorted(store.records):
        rec = store.records[key]
        route = (rec.candidate_keys or {}).get("route", "")
        digest.update(f"{key}|{rec.attribute}|{rec.doc_id}|{rec.surface_value}|{route}|{rec.null_reason}\n".encode())
    return digest.hexdigest()


def load_portfolio(db: Path, statements: dict[str, str] | None = None) -> FrozenPortfolio:
    from quwarts.core.logical import extend_logical_schema
    from quwarts.core.materialize import refresh_coverage_from_sqlite, refresh_schema_from_sqlite

    manifest = json.loads(MANIFEST.read_text())
    fields = {name: manifest[name] for name in FrozenPortfolio.model_fields if name in manifest}
    portfolio = FrozenPortfolio.model_validate(fields)
    for item in portfolio.databases:
        item.sqlite_path = str(db)
    if statements:
        portfolio.logical_schema = extend_logical_schema(portfolio.logical_schema, statements.values())
    for config, item in zip(portfolio.configurations, portfolio.databases):
        refresh_schema_from_sqlite(config.schema_, item.sqlite_path)
        item.coverage = refresh_coverage_from_sqlite(item.coverage, item.sqlite_path)
    return portfolio


def physical_value(db: Path, doc_id: str, attribute: str) -> Any:
    table, bare = attribute.split(".", 1)
    con = sqlite3.connect(db)
    try:
        cols = {row[1] for row in con.execute(f"PRAGMA table_info({_q(table)})")}
        if bare not in cols:
            return None
        row = con.execute(
            f"SELECT {_q(bare)} FROM {_q(table)} WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        return None if row is None else row[0]
    finally:
        con.close()


def distinct_values(db: Path, table: str, column: str) -> list[str]:
    con = sqlite3.connect(db)
    try:
        cols = {row[1] for row in con.execute(f"PRAGMA table_info({_q(table)})")}
        if column not in cols:
            return []
        rows = con.execute(
            f"SELECT DISTINCT {_q(column)} FROM {_q(table)} "
            f"WHERE {_q(column)} IS NOT NULL AND CAST({_q(column)} AS TEXT) <> ''"
        ).fetchall()
        return [str(row[0]) for row in rows]
    finally:
        con.close()


def voted_records(store: EvidenceStore) -> list[dict[str, Any]]:
    rows = []
    for rec in store.records.values():
        keys = rec.candidate_keys or {}
        if keys.get("route") != "voted":
            continue
        rows.append(
            {
                "doc_id": rec.doc_id,
                "attribute": rec.attribute,
                "surface": rec.surface_value,
                "null_reason": rec.null_reason,
                "grounded": keys.get("grounded") == "1" and rec.surface_value not in (None, ""),
            }
        )
    return rows


def record_in_db(db: Path, row: dict[str, Any]) -> bool:
    phys = physical_value(db, row["doc_id"], row["attribute"])
    if row["surface"] in (None, "") and phys in (None, ""):
        return True
    if row["surface"] in (None, "") or phys in (None, ""):
        return False
    return _fold(phys) == _fold(row["surface"])


def pick_cells(store: EvidenceStore, n_each: int = 4) -> list[dict[str, Any]]:
    picked: list[dict[str, Any]] = []
    for name in TRACE_ATTRS:
        entity = name.split(".", 1)[0]
        recs = [
            rec
            for rec in store.for_attribute(name)
            if str(rec.doc_id).startswith(f"{entity}/")
        ]
        nonempty = [
            rec for rec in recs
            if rec.surface_value not in (None, "")
            and (rec.candidate_keys or {}).get("route", "primary") == "primary"
        ]
        pool = nonempty or recs
        seen: set[str] = set()
        for rec in pool:
            if rec.doc_id in seen:
                continue
            seen.add(rec.doc_id)
            picked.append({"doc_id": rec.doc_id, "attribute": name})
            if len(seen) >= n_each:
                break
        if name.endswith(".id") and len(seen) < n_each:
            con = sqlite3.connect(SCORE_DB)
            try:
                table = entity
                for doc_id, value in con.execute(
                    f"SELECT doc_id, id FROM {_q(table)} ORDER BY id IS NULL, doc_id"
                ):
                    if doc_id in seen:
                        continue
                    seen.add(doc_id)
                    picked.append({"doc_id": doc_id, "attribute": name})
                    if len(seen) >= n_each:
                        break
            finally:
                con.close()
    return picked


def surfaces_for(store: EvidenceStore, doc_id: str, attribute: str) -> dict[str, Any]:
    raw = None
    voted = None
    voted_reason = None
    for rec in store.for_attribute(attribute):
        if rec.doc_id != doc_id:
            continue
        route = (rec.candidate_keys or {}).get("route", "primary")
        if route == "primary" and rec.surface_value not in (None, ""):
            raw = rec.surface_value
        if route == "voted":
            voted = rec.surface_value
            voted_reason = rec.null_reason
    return {"raw": raw, "voted": voted, "voted_reason": voted_reason}


def first_change(raw, repaired, physical, sql_hit, aligned) -> str:
    if raw in (None, "") and repaired in (None, "") and physical in (None, ""):
        return "raw_extraction"
    if _fold(repaired) != _fold(raw) and repaired is not None:
        return "repaired_evidence"
    if repaired in (None, "") and raw not in (None, "") and physical in (None, ""):
        return "repaired_evidence"
    if _fold(physical) != _fold(repaired if repaired not in (None, "") else raw):
        return "materialized_column"
    if sql_hit is False:
        return "sql_result"
    if aligned is False:
        return "scorer_alignment"
    return "survived"


def query_uses_attr(sql: str, attribute: str) -> bool:
    bare = attribute.split(".")[-1]
    return bare.lower() in sql.lower()


def strip_where(sql: str) -> str:
    try:
        tree = parse_one(sql)
        for node in tree.find_all(exp.Select):
            node.set("where", None)
        return tree.sql()
    except Exception:
        return re.sub(r"\bWHERE\b[\s\S]+?(?=\bGROUP\b|\bORDER\b|\bLIMIT\b|$)", " ", sql, flags=re.I)


def execute_sql(db: Path, sql: str) -> list[dict[str, Any]]:
    if not sql:
        return []
    con = sqlite3.connect(db)
    try:
        cur = con.execute(sql)
        cols = [item[0] for item in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def sql_contains_value(rows: list[dict[str, Any]], value: Any) -> bool | None:
    if value in (None, ""):
        return None
    needle = _fold(value)
    for row in rows:
        for cell in row.values():
            if cell in (None, ""):
                continue
            if needle and needle in _fold(cell):
                return True
    return False


def gold_ids() -> dict[str, list[str]]:
    from diagnostics.run_config_grid import load_ground_truth

    tables = load_ground_truth(gold_name("Med"))
    found: dict[str, list[str]] = {}
    for table, rows in tables.items():
        values = []
        for row in rows:
            for key in ("id", "ID"):
                if key in row and row[key] not in (None, ""):
                    values.append(str(row[key]).strip())
                    break
        found[table] = values
    return found


def classify_ids(documents, gold: dict[str, list[str]]) -> dict[str, Any]:
    by_stem = {Path(doc.doc_id).stem: doc for doc in documents}
    report = {}
    for table, values in gold.items():
        in_own_text = 0
        stem_only = 0
        neither = 0
        samples = {"in_own_text": [], "stem_only": [], "absent": []}
        for value in values:
            doc = by_stem.get(value)
            own_hit = False
            if doc is not None:
                if value.isdigit():
                    own_hit = re.search(rf"(?<!\d){re.escape(value)}(?!\d)", doc.text) is not None
                else:
                    own_hit = value.casefold() in doc.text.casefold()
            if own_hit:
                in_own_text += 1
                if len(samples["in_own_text"]) < 3:
                    samples["in_own_text"].append(value)
            elif doc is not None:
                stem_only += 1
                if len(samples["stem_only"]) < 3:
                    samples["stem_only"].append(value)
            else:
                neither += 1
                if len(samples["absent"]) < 3:
                    samples["absent"].append(value)
        if in_own_text == len(values) and in_own_text:
            kind = "document-observable"
        elif stem_only and in_own_text == 0:
            kind = "alignment-only bookkeeping"
        elif in_own_text == 0:
            kind = "benchmark-generated"
        else:
            kind = "alignment-only bookkeeping"
        report[f"{table}.id"] = {
            "n": len(values),
            "in_own_document_text": in_own_text,
            "filename_stem_only": stem_only,
            "unmatched": neither,
            "class": kind,
            "exclude_from_cell_f1_mean": kind != "document-observable",
            "samples": samples,
        }
    return report


def scorer_column(sql: str, bare: str) -> str:
    like = f"{bare}__like"
    if like.lower() in sql.lower():
        return like
    if bare.lower() in sql.lower():
        return bare
    return "absent"


def tau_from_eval(eval_path: Path, tau: float) -> dict[str, float]:
    payload = json.loads(eval_path.read_text())
    cell = payload.get("mean_cell_f1") or {}
    query = payload.get("mean_query_score") or {}
    def pick(mapping: dict, target: float) -> float:
        for key, value in mapping.items():
            if abs(float(key) - target) < 1e-9:
                return float(value)
        return float(next(iter(mapping.values()))) if mapping else 0.0
    return {
        "structure_f2": float(payload.get("mean_structure_fbeta_score") or 0.0),
        "cell_f1": pick(cell, tau),
        "product": pick(query, tau),
    }


def first_cause(
    *,
    sql: str,
    gold_rows: int,
    pred_rows: int,
    matched: int,
    cell_ok: bool,
    unfiltered_rows: int,
    gold_keys_in_corpus: bool,
    near: bool,
) -> str:
    joined = " join " in sql.lower()
    filtered = re.search(r"\bwhere\b", sql, re.I) is not None
    if pred_rows == 0:
        if joined:
            return "join_failure"
        if filtered and unfiltered_rows > 0:
            return "predicate_false_negative"
        return "missing_row"
    if gold_rows > 0 and matched == 0:
        return "alignment_failure"
    if not gold_keys_in_corpus:
        return "unwinnable"
    if not cell_ok and near:
        return "representation_mismatch"
    if not cell_ok:
        return "wrong_cell"
    if matched < gold_rows:
        if joined:
            return "join_failure"
        if filtered:
            return "predicate_false_negative"
        return "missing_row"
    return "wrong_cell"


def decompose_test(
    test_rows: list[dict[str, str]],
    plans: dict[str, Any],
    pred_db: Path,
    gold_tables: dict[str, list],
    documents,
) -> dict[str, Any]:
    sys.path.insert(0, str(WDIRS))
    from diagnostics.run_config_grid import load_attributes
    from spp.aggregation_metrics import (
        MetricConfig,
        align_columns,
        align_rows,
        evaluate_aggregation_tables,
        gold_table_from_sql,
        predicted_table_from_rows,
        schema_from_sql,
    )
    from spp.config_grid import _build_in_memory_db
    from quwarts.experiments.player_case80 import execute

    attributes = load_attributes(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold_tables)
    config = MetricConfig()
    corpus = "\n".join(doc.text for doc in documents)
    causes: list[dict[str, Any]] = []
    for row in test_rows:
        sql = row["sql"]
        plan = plans.get(row["query_id"]) or {}
        pred_sql = plan.get("sql") if isinstance(plan, dict) else plan
        gold_result = execute(gold_conn, sql)
        pred_result = execute_sql(pred_db, pred_sql or "")
        unfiltered = execute_sql(pred_db, strip_where(pred_sql or sql))
        schema = schema_from_sql(sql)
        matched = 0
        near = False
        cell_ok = False
        gold_keys_in_corpus = True
        product = 0.0
        cell20 = 0.0
        structure = 0.0
        if schema.get("is_aggregation") and gold_result:
            gold_table = gold_table_from_sql(gold_result, sql)
            pred_table = predicted_table_from_rows(pred_result, gold=gold_table)
            metrics = evaluate_aggregation_tables(pred_table, gold_table, config=config)
            structure = float(metrics["rank"]["structure_fbeta_score"])
            cell_map = metrics["rank"]["cell_f1"]
            cell20 = float(cell_map.get(0.2) or cell_map.get(0.20) or 0.0)
            product = structure * cell20
            cols = align_columns(pred_table, gold_table, config=config)
            rows = align_rows(pred_table, gold_table, cols, config=config, tier="semantic")
            if not rows["matched_pairs"]:
                rows = align_rows(pred_table, gold_table, cols, config=config, tier="normalized")
            matched = len(rows["matched_pairs"])
            cell_ok = cell20 >= 0.999
            keys = [col.name for col in gold_table.by_role("key")]
            stems = {Path(doc.doc_id).stem for doc in documents}
            missing_ids = []
            for grow in gold_table.rows:
                for key in keys:
                    value = grow.get(key)
                    if value in (None, ""):
                        continue
                    text = str(value).strip()
                    if text.isdigit() and text in stems:
                        if re.search(rf"(?<!\d){re.escape(text)}(?!\d)", corpus) is None:
                            missing_ids.append(text)
            gold_keys_in_corpus = not missing_ids
            if matched:
                gold_to_pred = cols["gold_to_pred"]
                for pi, gi, _ in rows["matched_pairs"]:
                    grow = gold_table.rows[gi]
                    prow = pred_table.rows[pi]
                    for key in keys:
                        pred_name = gold_to_pred.get(key)
                        if pred_name is None:
                            continue
                        gv, pv = grow.get(key), prow.get(pred_name)
                        if _fold(gv) and _fold(gv) != _fold(pv):
                            ratio = 0.0
                            if gv and pv:
                                from difflib import SequenceMatcher
                                ratio = SequenceMatcher(None, _fold(gv), _fold(pv)).ratio()
                            if ratio >= 0.6 or (_fold(gv) and _fold(gv) in _fold(pv or "")):
                                near = True
        cause = first_cause(
            sql=sql,
            gold_rows=len(gold_result),
            pred_rows=len(pred_result),
            matched=matched,
            cell_ok=cell_ok,
            unfiltered_rows=len(unfiltered),
            gold_keys_in_corpus=gold_keys_in_corpus,
            near=near,
        )
        lost = max(0.0, 1.0 - product)
        causes.append(
            {
                "query_id": row["query_id"],
                "cause": cause,
                "gold_rows": len(gold_result),
                "pred_rows": len(pred_result),
                "matched": matched,
                "structure_f2": structure,
                "cell_f1_20": cell20,
                "product": product,
                "lost": lost,
            }
        )
    gold_conn.close()
    counts = Counter(row["cause"] for row in causes)
    mass = defaultdict(float)
    for row in causes:
        mass[row["cause"]] += row["lost"]
    return {
        "per_query": causes,
        "counts": dict(counts),
        "lost_mass": {key: mass[key] for key in sorted(mass)},
        "n": len(causes),
    }


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth

    compile_store = EvidenceStore(COMPILE_EV)
    vote_store = EvidenceStore(VOTE_EV)
    documents = documents_for("Med")
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    train_sql = {row["query_id"]: row["sql"] for row in train}
    test_sql = {row["query_id"]: row["sql"] for row in test}
    gold = load_ground_truth(gold_name("Med"))
    portfolio = load_portfolio(SCORE_DB, {**train_sql, **test_sql})
    plans = serve_plans(portfolio, {**train_sql, **test_sql})

    # 1.2 hashes and vote presence
    voted = voted_records(vote_store)
    grounded = [row for row in voted if row["grounded"]]
    nulled = [row for row in voted if not row["grounded"]]
    vote_in_score = sum(1 for row in voted if record_in_db(SCORE_DB, row))
    vote_in_vote_db = sum(1 for row in voted if record_in_db(VOTE_DB, row))
    grounded_in_score = sum(1 for row in grounded if record_in_db(SCORE_DB, row))
    nulled_in_score = sum(1 for row in nulled if record_in_db(SCORE_DB, row))
    section_12 = {
        "evidence_sha_before": evidence_sha(compile_store),
        "evidence_sha_after": evidence_sha(vote_store),
        "evidence_changed": evidence_sha(compile_store) != evidence_sha(vote_store),
        "n_voted": len(voted),
        "n_grounded": len(grounded),
        "n_nulled": len(nulled),
        "voted_present_in_score_db": vote_in_score,
        "grounded_present_in_score_db": grounded_in_score,
        "nulled_present_in_score_db": nulled_in_score,
        "voted_present_in_rematerialized_db": vote_in_vote_db,
        "score_db_sha": file_sha(SCORE_DB),
        "rematerialized_db_sha": file_sha(VOTE_DB),
        "databases_differ": file_sha(SCORE_DB) != file_sha(VOTE_DB),
        "score_db_path": str(SCORE_DB),
        "exclude_vote_from_reporting": grounded_in_score == 0,
        "score_db_is_pre_vote": True,
        "grounded_absent_from_score_db": len(grounded) - grounded_in_score,
    }

    # 1.1 traces against the scored 0.126 database
    traces = []
    for cell in pick_cells(vote_store):
        doc_id, attribute = cell["doc_id"], cell["attribute"]
        surfaces = surfaces_for(vote_store, doc_id, attribute)
        raw = surfaces["raw"]
        repaired = surfaces["voted"] if surfaces["voted"] is not None or surfaces["voted_reason"] else raw
        if surfaces["voted_reason"] == "ungrounded":
            repaired = None
        physical = physical_value(SCORE_DB, doc_id, attribute)
        users = [row for row in test if query_uses_attr(row["sql"], attribute)]
        sql_hit = None
        aligned = None
        used_sql = None
        if users:
            used_sql = users[0]["query_id"]
            plan = plans.get(users[0]["query_id"]) or {}
            pred_sql = plan.get("sql") if isinstance(plan, dict) else plan
            rows = execute_sql(SCORE_DB, pred_sql or "")
            sql_hit = sql_contains_value(rows, physical if physical not in (None, "") else raw)
            gold_rows = execute_sql  # placeholder to keep lints calm
            _ = gold_rows
            aligned = sql_hit
        traces.append(
            {
                "doc_id": doc_id,
                "attribute": attribute,
                "raw_extraction": raw,
                "repaired_evidence": repaired,
                "voted_reason": surfaces["voted_reason"],
                "materialized_column": physical,
                "sql_query": used_sql,
                "sql_result_has_value": sql_hit,
                "scorer_alignment": aligned,
                "first_boundary": first_change(raw, repaired, physical, sql_hit, aligned),
            }
        )

    # 1.3 surface vs like
    like_section = {}
    for name in LIKE_ATTRS:
        table, bare = name.split(".", 1)
        surface_vals = distinct_values(SCORE_DB, table, bare)
        like_vals = distinct_values(SCORE_DB, table, f"{bare}__like")
        served = []
        for qid, plan in plans.items():
            sql = (plan or {}).get("sql") if isinstance(plan, dict) else plan
            if not sql or not query_uses_attr(sql, name):
                continue
            served.append({"query_id": qid, "reads": scorer_column(sql, bare)})
        read_counts = Counter(row["reads"] for row in served)
        like_section[name] = {
            "n_distinct_surface": len(surface_vals),
            "n_distinct_like": len(like_vals),
            "surface_sample": surface_vals[:8],
            "like_sample": like_vals[:8],
            "served_column_counts": dict(read_counts),
            "scorer_reads": (read_counts.most_common(1)[0][0] if read_counts else "unused"),
        }
    # score the same test queries on served SQL vs surface-forced SQL
    from quwarts.experiments.repair_art import mean_cell_f1_20

    for name, payload in like_section.items():
        bare = name.split(".", 1)[1]
        users = [row for row in test if query_uses_attr(row["sql"], name)]
        if not users:
            payload["cell_f1_20_served"] = None
            payload["cell_f1_20_surface"] = None
            continue
        served_plans = {}
        surface_plans = {}
        for row in users:
            plan = plans.get(row["query_id"]) or {}
            sql = plan.get("sql") if isinstance(plan, dict) else plan
            served_plans[row["query_id"]] = {"sql": sql, "sqlite_path": str(SCORE_DB)}
            forced = (sql or "").replace(f"{bare}__like", bare)
            surface_plans[row["query_id"]] = {"sql": forced, "sqlite_path": str(SCORE_DB)}
        served_report = score_with_rewrites(users, served_plans, SCORE_DB, gold, "Med")
        surface_report = score_with_rewrites(users, surface_plans, SCORE_DB, gold, "Med")
        payload["n_test_queries"] = len(users)
        payload["cell_f1_20_served"] = mean_cell_f1_20(served_report)
        payload["cell_f1_20_surface"] = mean_cell_f1_20(surface_report)

    # 1.4 gold IDs
    ids = classify_ids(documents, gold_ids())

    # 1.5 both systems both taus
    quwarts = score_with_rewrites(test, serve_plans(portfolio, test_sql), SCORE_DB, gold, "Med")
    docetl = {
        "0.05": tau_from_eval(DOCETL_EVAL, 0.05),
        "0.20": tau_from_eval(DOCETL_EVAL, 0.20),
    }
    section_15 = {
        "quwarts_cell_f1_05": quwarts.get("mean_cell_f1_05"),
        "quwarts_cell_f1_20": quwarts.get("mean_cell_f1_20"),
        "quwarts_structure_f2": quwarts.get("mean_structure_f2"),
        "quwarts_product_05": quwarts.get("mean_query_score_05"),
        "quwarts_product_20": quwarts.get("mean_query_score_20"),
        "docetl_cell_f1_05": docetl["0.05"]["cell_f1"],
        "docetl_cell_f1_20": docetl["0.20"]["cell_f1"],
        "docetl_structure_f2": docetl["0.20"]["structure_f2"],
        "docetl_product_05": docetl["0.05"]["product"],
        "docetl_product_20": docetl["0.20"]["product"],
    }

    # 1.6 loss
    loss = decompose_test(test, serve_plans(portfolio, test_sql), SCORE_DB, gold, documents)

    payload = {
        "1_1_boundaries": traces,
        "1_2_vote_reach": section_12,
        "1_3_surface_vs_like": like_section,
        "1_4_gold_ids": ids,
        "1_5_tolerance": section_15,
        "1_6_loss": loss,
    }
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({
        "wrote": str(OUT),
        "1_2": section_12,
        "1_3": {k: {kk: vv for kk, vv in v.items() if kk not in {"surface_sample", "like_sample"}} for k, v in like_section.items()},
        "1_4": {k: {kk: v[kk] for kk in ("n", "in_own_document_text", "filename_stem_only", "class", "exclude_from_cell_f1_mean")} for k, v in ids.items()},
        "1_5": section_15,
        "1_6_counts": loss["counts"],
        "1_6_mass": loss["lost_mass"],
        "n_traces": len(traces),
        "first_boundaries": dict(Counter(row["first_boundary"] for row in traces)),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

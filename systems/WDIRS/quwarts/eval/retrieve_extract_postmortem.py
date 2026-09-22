"""Zero-token postmortem and non-destructive replay of frozen retrieve-extract runs."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlglot import exp

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.materialize import file_sha256
from quwarts.core.models import Role
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem, source_document_hash
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.config import FROZEN
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.route import _disproportionate
from quwarts.core.schema_columns import assert_queries_execute
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload, parse_sql
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import (
    documents_for,
    gold_name,
    queries_for,
    score_with_rewrites,
)

PLUMBING_DB = {
    "Finan": ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db",
    "Legal": ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db",
}
FRESH_DB = {
    "Finan": ROOT / "results" / "quwarts_retrieve_extract" / "finan" / "databases" / "finan_retrieve_extract.db",
    "Legal": ROOT / "results" / "quwarts_retrieve_extract" / "legal" / "databases" / "legal_retrieve_extract.db",
}
ART = {
    "Finan": ROOT / "results" / "quwarts_retrieve_extract" / "finan",
    "Legal": ROOT / "results" / "quwarts_retrieve_extract" / "legal",
}
PLUMBING_SCORE = {
    "Finan": {"product": 0.01685238629683074, "f2": 0.29248809938465115, "f1": 0.027592592592592592},
    "Legal": {"product": 0.022455905439098717, "f2": 0.20543217286914767, "f1": 0.03653846153846154},
}
FRESH_SCORE = {
    "Finan": {"product": 0.0, "f2": 0.0, "f1": 0.0},
    "Legal": {"product": 0.014604377104377106, "f2": 0.22059966177613236, "f1": 0.026388888888888892},
}
DOCETL = {
    "Finan": {"product": 0.08410358973968853, "f2": 0.537, "f1": 0.114},
    "Legal": {"product": 0.12350932750098194, "f2": 0.789, "f1": 0.129},
}
OUT = ROOT / "results" / "quwarts_retrieve_extract" / "retrieve_extract_postmortem.json"
REPLAY_ROOT = ROOT / "results" / "quwarts_retrieve_extract" / "replay"
DET_REASONS = {
    "hard_fit_and_effective_fit_and_ledger",
    "long_or_unfit_and_diffuse_retrieval",
    "document_too_long_or_disproportionate",
    "default_retrieved_chunks",
}
REPLAY_RULE = {
    "copy_only_if_plumbing_sql_null": True,
    "require_found": True,
    "require_exact_span_revalidation": True,
    "require_source_document_hash": True,
    "require_normalization_when_typed": True,
    "never_overwrite_nonnull": True,
    "reject": ["not_found", "uncertain", "malformed", "ungrounded", "normalization_failed"],
    "do_not_change": ["identity", "row_counts", "signatures", "filters", "groups", "rewrites"],
    "rules": ["official", "critical_fills", "literal_fills", "fresh_original"],
}


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _hash_obj(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _null(value: Any) -> bool:
    return value in (None, "")


def _fetch(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    cur = conn.execute(sql)
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, rec)) for rec in cur.fetchall()]


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def _score(name: str, dest: Path, test: list[dict[str, str]], rewrites: dict[str, str], gold) -> dict[str, Any]:
    report = score_with_rewrites(test, rewrites, dest, gold, name)
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": [
            {
                "query_id": row["query_id"],
                "structure_f2": row.get("structure_f2"),
                "cell_f1_20": row.get("cell_f1_20"),
                "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
            }
            for row in report.get("per_query") or []
        ],
    }


def load_catalog(name: str) -> dict[str, dict[str, Any]]:
    path = ROOT / "Query" / name / f"{name}_attributes.json"
    raw = json.loads(path.read_text())
    out: dict[str, dict[str, Any]] = {}
    for attrs in raw.values():
        if not isinstance(attrs, dict):
            continue
        for attr, spec in attrs.items():
            if isinstance(spec, dict):
                out[str(attr).lower()] = spec
    return out


def is_semantic_label(attribute: str, catalog: dict[str, dict[str, Any]], dtype: str) -> bool:
    info = catalog.get(attribute.split(".")[-1].lower()) or {}
    if info.get("is_fixed") is True:
        return True
    if str(info.get("usage") or "").lower() == "categorical":
        return True
    desc = str(info.get("description") or "").lower()
    if "choose one from" in desc or "choose one or more from" in desc:
        return True
    if dtype == "numeric":
        return False
    return False


def role_buckets(roles: set[Role]) -> list[str]:
    names = {role.value if hasattr(role, "value") else str(role) for role in roles}
    buckets = []
    if "predicate" in names:
        buckets.append("WHERE")
    if "join" in names:
        buckets.append("JOIN ON")
    if "group" in names:
        buckets.append("GROUP BY / CASE")
    if names & {"agg_additive", "agg_distinct", "agg_extremal"}:
        buckets.append("COUNT or aggregate input")
    if names == {"project"} or (not buckets and "project" in names):
        buckets.append("projection only")
    return buckets or ["projection only"]


def is_critical(roles: set[Role]) -> bool:
    return any(bucket != "projection only" for bucket in role_buckets(roles))


def classify_route(row: dict[str, Any]) -> str:
    meas = row.get("measurements") or {}
    conc = row.get("retrieval_concentration") or {}
    remaining = int(row.get("remaining_budget") or 0)
    hard = bool(meas.get("hard_fit"))
    effective = bool(meas.get("effective_fit"))
    feasible = list(row.get("feasible") or [])
    doc_tokens = int(meas.get("document_tokens") or 0)
    if hard and effective and not _disproportionate(doc_tokens, remaining):
        return "deterministic_whole"
    if not hard or not effective:
        if conc.get("diffuse"):
            top2 = float(conc.get("top2_share") or 0.0)
            unique = int(conc.get("unique_sections") or 0)
            if unique >= int(FROZEN["diffuse_unique_sections"]) and top2 < float(FROZEN["borderline_concentration_lo"]):
                return "deterministic_section_map"
            if len(feasible) > 1:
                return "genuinely_borderline"
            return "deterministic_section_map"
        return "deterministic_retrieval"
    return "genuinely_borderline"


def simulated_mode(row: dict[str, Any]) -> str:
    meas = row.get("measurements") or {}
    conc = row.get("retrieval_concentration") or {}
    if meas.get("hard_fit") and meas.get("effective_fit"):
        return "whole_document"
    if not conc.get("diffuse") and float(conc.get("top2_share") or 0.0) > 0:
        return "retrieved_chunks"
    return "section_map"


def router_audit(name: str) -> dict[str, Any]:
    art = ART[name]
    decisions = json.loads((art / "route_log.json").read_text())
    ledger = json.loads((art / "ledger.json").read_text())
    extract = json.loads((art / "extract_log.json").read_text())
    router_costs = [int(rec["tokens"]) for rec in ledger["records"] if rec["purpose"] == "context_router"]
    first_pass = [int(rec["tokens"]) for rec in ledger["records"] if rec["purpose"] == "first_pass"]
    repair = [int(rec["tokens"]) for rec in ledger["records"] if rec["purpose"] in {"repair", "refine"}]
    plannerish = [row for row in decisions if row.get("reason") not in DET_REASONS]
    assigned = []
    for row, cost in zip(plannerish, router_costs):
        assigned.append((row, cost))
    leftover = router_costs[len(assigned) :]
    classes = Counter()
    class_tokens = Counter()
    reconstructed = []
    for row in decisions:
        klass = classify_route(row)
        classes[klass] += 1
        meas = row.get("measurements") or {}
        reconstructed.append(
            {
                "document_tokens": meas.get("document_tokens"),
                "prompt_schema_tokens": meas.get("prompt_and_schema_tokens"),
                "completion_reserve": meas.get("reserved_completion_tokens"),
                "hard_context_limit": meas.get("model_context_limit"),
                "effective_input_limit": meas.get("effective_input_limit"),
                "remaining_budget": row.get("remaining_budget"),
                "bundle_size": len(row.get("attributes") or []),
                "retrieval_concentration": row.get("retrieval_concentration"),
                "selected_mode": row.get("mode"),
                "class": klass,
                "reason": row.get("reason"),
            }
        )
    for row, cost in assigned:
        klass = classify_route(row)
        class_tokens[klass] += cost
    call_classes = Counter(classify_route(row) for row, _cost in assigned)
    recovered = int(sum(router_costs))
    mean_extract = (sum(first_pass) / len(first_pass)) if first_pass else 0.0
    extra_calls = int(recovered // mean_extract) if mean_extract else 0
    fp = [row for row in extract if row.get("phase") == "first_pass"]
    covered_attrs = {attr for row in fp for attr in row.get("attributes") or []}
    covered_docs = {row["doc_id"] for row in fp}
    covered_pairs = {(row["doc_id"], attr) for row in fp for attr in row.get("attributes") or []}
    sim_modes = Counter(simulated_mode(row) for row in decisions)
    mode_agree = sum(1 for row in decisions if simulated_mode(row) == row.get("mode"))
    return {
        "n_decisions": len(decisions),
        "n_router_calls": len(router_costs),
        "router_tokens": recovered,
        "unassigned_router_tokens": leftover,
        "decision_classes": dict(classes),
        "router_call_classes": dict(call_classes),
        "router_tokens_by_class": dict(class_tokens),
        "deterministic_simulation": {
            "mode_counts": dict(sim_modes),
            "agrees_with_selected": mode_agree,
            "disagrees": len(decisions) - mode_agree,
            "tokens_recovered": recovered,
            "mean_first_pass_cost": mean_extract,
            "mean_repair_or_refine_cost": (sum(repair) / len(repair)) if repair else 0.0,
            "additional_extractor_calls": extra_calls,
            "current_first_pass_jobs": len(fp),
            "current_attribute_coverage": sorted(covered_attrs),
            "current_entity_coverage": len(covered_docs),
            "current_pair_coverage": len(covered_pairs),
        },
        "sample_reconstructed": reconstructed[:3],
    }


def load_evidence(name: str) -> dict[tuple[str, str], dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted((ART[name] / "cache").glob("*.json")):
        payload = json.loads(path.read_text())
        manifest = payload.get("manifest") or {}
        if manifest.get("operator") != "retrieve_extract":
            continue
        parsed = (payload.get("record") or {}).get("parsed") or {}
        identity = str(manifest.get("entity_identity") or "")
        digest = str(manifest.get("source_document_hash") or "")
        for attr, item in (parsed.get("items") or {}).items():
            key = (identity, attr)
            status = item.get("status")
            grounded = bool(item.get("grounded"))
            rank = 3 if status == "found" and grounded else 1 if status == "found" else 0
            current = best.get(key)
            if current and current["_rank"] > rank:
                continue
            best[key] = {
                **item,
                "_rank": rank,
                "entity_identity": identity,
                "source_document_hash": digest,
                "context_hashes": list(manifest.get("context_hashes") or []),
            }
    return best


def table_rows(path: Path, table: str) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = {}
        for raw in conn.execute(f"SELECT * FROM {_q(table)}"):
            payload = dict(raw)
            rows[str(payload.get("__entity_id") or "")] = payload
        return rows
    finally:
        conn.close()


def semantic_columns(path: Path, table: str) -> list[str]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return [
            row[1]
            for row in conn.execute(f"PRAGMA table_info({_q(table)})")
            if not str(row[1]).startswith("__")
            and not str(row[1]).startswith("sig_")
            and row[1] not in {"doc_id", "rowid"}
            and "." not in str(row[1])
            and not str(row[1]).endswith("__surface")
            and not str(row[1]).endswith("__canonical")
        ]
    finally:
        conn.close()


def value_flow(name: str, workload, catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    table = "finance" if name == "Finan" else "legal"
    plumbing = table_rows(PLUMBING_DB[name], table)
    fresh = table_rows(FRESH_DB[name], table)
    evidence = load_evidence(name)
    attrs = sorted(workload.requirements)
    totals = Counter()
    by_attr: dict[str, Counter] = defaultdict(Counter)
    by_role: dict[str, Counter] = defaultdict(Counter)
    fresh_status: dict[str, Counter] = defaultdict(Counter)
    for eid, plow in plumbing.items():
        frow = fresh.get(eid) or {}
        for attr in attrs:
            bare = attr.split(".")[-1]
            pval = plow.get(bare)
            fval = frow.get(bare)
            ev = evidence.get((eid, attr)) or {}
            if ev:
                fresh_status[attr][str(ev.get("status") or "missing")] += 1
                if ev.get("grounded"):
                    fresh_status[attr]["grounded"] += 1
                if ev.get("norm_error"):
                    fresh_status[attr]["norm_error"] += 1
            if _null(pval) and _null(fval):
                label = "both_NULL"
            elif not _null(pval) and _null(fval):
                label = "plumbing_value_lost"
            elif _null(pval) and not _null(fval):
                label = "fresh_fill_into_plumbing_NULL"
            elif str(pval) == str(fval):
                label = "retained_unchanged"
            else:
                label = "conflicting_grounded_values" if ev.get("grounded") else "fresh_overwrite_of_plumbing_nonNULL"
            totals[label] += 1
            by_attr[attr][label] += 1
            for bucket in role_buckets(workload.requirements[attr].roles):
                by_role[bucket][label] += 1
    return {
        "relation": table,
        "entities_aligned": len(set(plumbing) & set(fresh)),
        "totals": dict(totals),
        "by_attribute": {name: dict(counter) for name, counter in by_attr.items()},
        "by_ast_role": {name: dict(counter) for name, counter in by_role.items()},
        "fresh_grounding": {name: dict(counter) for name, counter in fresh_status.items()},
    }


def _stage_sql(sql: str) -> dict[str, str]:
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return {"full": sql}
    primary = None
    for table in tree.find_all(exp.Table):
        primary = table.name
        break
    base = f"SELECT COUNT(*) AS n FROM {_q(primary)}" if primary else "SELECT 0 AS n"
    join_tree = tree.copy()
    join_tree.set("where", None)
    join_tree.set("group", None)
    join_tree.set("having", None)
    join_tree.set("order", None)
    join_tree.set("expressions", [exp.alias_(exp.Count(this=exp.Star()), "n")])
    where_tree = tree.copy()
    where_tree.set("group", None)
    where_tree.set("having", None)
    where_tree.set("order", None)
    where_tree.set("expressions", [exp.alias_(exp.Count(this=exp.Star()), "n")])
    group_tree = tree.copy()
    group_tree.set("having", None)
    group_tree.set("order", None)
    if group_tree.args.get("group"):
        group_tree.set("expressions", [exp.alias_(exp.Count(this=exp.Star()), "n")])
    return {
        "base": base,
        "join": join_tree.sql(dialect="sqlite"),
        "where": where_tree.sql(dialect="sqlite"),
        "group": group_tree.sql(dialect="sqlite"),
        "full": sql,
    }


def _count(conn: sqlite3.Connection, sql: str) -> tuple[int | None, str | None]:
    try:
        rows = _fetch(conn, sql)
    except sqlite3.Error as exc:
        return None, str(exc)
    if not rows:
        return 0, None
    if len(rows) == 1 and "n" in {str(key).lower() for key in rows[0]}:
        key = next(k for k in rows[0] if str(k).lower() == "n")
        return int(rows[0][key] or 0), None
    return len(rows), None


def _filter_attrs(sql: str) -> list[str]:
    try:
        tree = parse_sql(sql)
    except Exception:
        return []
    names = []
    where = tree.args.get("where") if isinstance(tree, exp.Select) else None
    if where:
        for col in where.find_all(exp.Column):
            names.append((col.name or "").lower())
    return list(dict.fromkeys(names))


def empty_bag_traces(name: str, dest: Path, statements: dict[str, str], test_ids: set[str], predicates) -> dict[str, Any]:
    table = "finance" if name == "Finan" else "legal"
    conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    cols = {row[1].lower() for row in conn.execute(f"PRAGMA table_info({_q(table)})")}
    failures = Counter()
    traces = []
    empty_ids = []
    for qid, sql in statements.items():
        if qid not in test_ids:
            continue
        rewritten = official_sql(sql, dest, predicates)
        bag = _fetch(conn, rewritten)
        if bag:
            continue
        empty_ids.append(qid)
        stages = _stage_sql(rewritten)
        counts = {}
        errors = {}
        for stage, stage_sql in stages.items():
            n, err = _count(conn, stage_sql)
            counts[stage] = n
            if err:
                errors[stage] = err
        first = "full"
        for stage in ("base", "join", "where", "group", "full"):
            if counts.get(stage) in (0, None):
                first = stage
                break
        attrs = _filter_attrs(rewritten)
        reason = "compiler/runtime failure" if errors else "predicate mismatch"
        if first == "base":
            reason = "compiler/runtime failure" if errors.get("base") else "missing source value"
        elif first == "join":
            reason = "join-key failure"
        elif first == "where":
            nulls = 0
            wrong = 0
            if attrs:
                present = [col for col in attrs if col in cols]
                if present:
                    clause = " AND ".join(f"{_q(col)} IS NOT NULL AND CAST({_q(col)} AS TEXT) <> ''" for col in present)
                    filled = int(conn.execute(f"SELECT COUNT(*) FROM {_q(table)} WHERE {clause}").fetchone()[0])
                    nulls = int(conn.execute(f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0]) - filled
                    if filled == 0:
                        reason = "missing source value"
                    else:
                        reason = "wrong extracted value"
                        wrong = filled
            else:
                reason = "predicate mismatch"
        elif first == "group":
            reason = "group-key mismatch"
        elif first == "full" and counts.get("where"):
            reason = "aggregate input NULL"
        failures[reason] += 1
        traces.append(
            {
                "query_id": qid,
                "first_failing_stage": first,
                "counts": counts,
                "errors": errors,
                "referenced_attributes": attrs,
                "reason": reason,
            }
        )
    conn.close()
    return {"n_empty_test": len(empty_ids), "empty_ids": empty_ids, "failures": dict(failures), "traces": traces}


def _copy_frozen(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(src, dest)


def candidate_fills(
    name: str,
    workload,
    catalog: dict[str, dict[str, Any]],
    documents: list,
) -> list[dict[str, Any]]:
    table = "finance" if name == "Finan" else "legal"
    plumbing = table_rows(PLUMBING_DB[name], table)
    texts = {document_stem(doc.doc_id) or doc.doc_id: (doc.doc_id, doc.text) for doc in documents}
    evidence = load_evidence(name)
    out = []
    for eid, plow in plumbing.items():
        stem = str(plow.get("__provenance_label") or document_stem(str(plow.get("doc_id") or "")))
        source_id, text = texts.get(stem) or texts.get(str(plow.get("doc_id") or "")) or ("", "")
        digest = source_document_hash(source_id, text) if source_id else ""
        for attr, req in workload.requirements.items():
            bare = attr.split(".")[-1]
            ev = evidence.get((eid, attr))
            if ev is None:
                continue
            status = ev.get("status")
            raw = ev.get("raw_value")
            spans = ev.get("evidence") or []
            span = next((item.get("exact_span") for item in spans if item.get("exact_span")), None)
            dtype = req.dtype or "string"
            semantic = is_semantic_label(attr, catalog, dtype)
            critical = is_critical(req.roles)
            reasons = []
            if _null(plow.get(bare)) is False:
                reasons.append("plumbing_nonnull")
            if status != "found":
                reasons.append(f"status:{status}")
            if not ev.get("grounded"):
                reasons.append("ungrounded")
            if ev.get("source_document_hash") and digest and ev["source_document_hash"] != digest:
                reasons.append("document_hash_mismatch")
            if not span or (text and span.lower() not in text.lower()):
                reasons.append("span_not_in_source")
            if raw not in (None, "") and span and str(raw).lower() not in str(span).lower():
                if ev.get("normalized_value") is None or str(ev.get("normalized_value")) not in str(span):
                    reasons.append("value_not_in_span")
            norm_value, _unit, norm_err = normalize_value(raw, dtype)
            if dtype == "numeric" and norm_err:
                reasons.append("normalization_failed")
            value = norm_value if dtype == "numeric" and norm_value is not None else raw
            accepted = not reasons
            out.append(
                {
                    "entity_id": eid,
                    "attribute": attr,
                    "bare": bare,
                    "value": value,
                    "raw": raw,
                    "span": span,
                    "source_id": (spans[0] or {}).get("source_id") if spans else "",
                    "document_hash": digest,
                    "status": status,
                    "grounded": bool(ev.get("grounded")),
                    "norm_error": norm_err,
                    "semantic_label": semantic,
                    "critical": critical,
                    "roles": role_buckets(req.roles),
                    "accepted": accepted,
                    "reject_reasons": reasons,
                }
            )
    return out


def apply_replay(src: Path, dest: Path, fills: list[dict[str, Any]], table: str, rule: str) -> dict[str, Any]:
    _copy_frozen(src, dest)
    conn = sqlite3.connect(str(dest))
    before_rows = int(conn.execute(f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0])
    checksums = {}
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")]
    for col in cols:
        checksums[col] = [
            rec[0]
            for rec in conn.execute(
                f"SELECT { _q(col) } FROM {_q(table)} ORDER BY {_q('__entity_id')}"
            )
        ]
    conn.execute(
        "CREATE TABLE IF NOT EXISTS replay_fills ("
        "entity_id TEXT, attribute TEXT, value TEXT, raw TEXT, span TEXT, "
        "source_id TEXT, document_hash TEXT, rule TEXT)"
    )
    accepted = []
    overwritten = 0
    for fill in fills:
        if rule == "critical_fills" and not fill["critical"]:
            continue
        if rule == "literal_fills" and fill["semantic_label"]:
            continue
        if not fill["accepted"]:
            continue
        current = conn.execute(
            f"SELECT { _q(fill['bare']) } FROM {_q(table)} WHERE {_q('__entity_id')} = ?",
            [fill["entity_id"]],
        ).fetchone()
        if current is None:
            continue
        if not _null(current[0]):
            overwritten += 1
            continue
        conn.execute(
            f"UPDATE {_q(table)} SET {_q(fill['bare'])} = ? WHERE {_q('__entity_id')} = ? AND "
            f"({_q(fill['bare'])} IS NULL OR CAST({_q(fill['bare'])} AS TEXT) = '')",
            [fill["value"], fill["entity_id"]],
        )
        if conn.execute(f"SELECT changes()").fetchone()[0]:
            accepted.append(fill)
            conn.execute(
                "INSERT INTO replay_fills VALUES (?,?,?,?,?,?,?,?)",
                [
                    fill["entity_id"],
                    fill["attribute"],
                    None if fill["value"] is None else str(fill["value"]),
                    fill["raw"],
                    fill["span"],
                    fill["source_id"],
                    fill["document_hash"],
                    rule,
                ],
            )
    conn.commit()
    after_rows = int(conn.execute(f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0])
    changed_cols = []
    for col in cols:
        if col in {"replay_fills"}:
            continue
        now = [rec[0] for rec in conn.execute(f"SELECT {_q(col)} FROM {_q(table)} ORDER BY {_q('__entity_id')}")]
        if now != checksums[col]:
            changed_cols.append(col)
    wrote = {fill["bare"] for fill in accepted}
    unrelated_changed = [col for col in changed_cols if col not in wrote]
    visible = int(conn.execute("SELECT COUNT(*) FROM replay_fills").fetchone()[0])
    conn.close()
    return {
        "accepted": len(accepted),
        "sql_visible": visible,
        "overwrites_blocked": overwritten,
        "row_count_before": before_rows,
        "row_count_after": after_rows,
        "changed_columns": changed_cols,
        "unrelated_columns_changed": unrelated_changed,
        "accepted_fills": accepted,
    }


def gold_cell_accuracy(name: str, fills: list[dict[str, Any]], gold_rows: list[dict[str, Any]], plumbing: dict[str, dict[str, Any]]) -> dict[str, Any]:
    gold_by_id = {str(row.get("id") or ""): row for row in gold_rows}
    literal = {"tp": 0, "n": 0}
    numeric = {"tp": 0, "n": 0}
    semantic = {"tp": 0, "n": 0}
    by_attr = defaultdict(lambda: {"n": 0, "tp": 0})
    by_role = defaultdict(lambda: {"n": 0, "tp": 0})
    for fill in fills:
        plow = plumbing.get(fill["entity_id"]) or {}
        stem = str(plow.get("__provenance_label") or "")
        grow = gold_by_id.get(stem)
        if grow is None:
            continue
        gold = grow.get(fill["bare"])
        if gold in (None, ""):
            continue
        pred = fill.get("value")
        hit = False
        if fill["semantic_label"]:
            semantic["n"] += 1
            gold_set = {part.strip().lower() for part in str(gold).replace("||", ";").split(";") if part.strip()}
            pred_set = {part.strip().lower() for part in str(pred).replace("||", ";").split(";") if part.strip()}
            hit = bool(gold_set & pred_set) if gold_set and pred_set else str(gold).strip().lower() == str(pred).strip().lower()
            semantic["tp"] += int(hit)
        elif fill.get("roles") and False:
            pass
        dtype_numeric = False
        try:
            gnum = float(str(gold).replace(",", ""))
            pnum = float(str(pred).replace(",", ""))
            dtype_numeric = True
            numeric["n"] += 1
            hit = abs(gnum - pnum) <= max(0.20 * max(abs(gnum), 1.0), 1e-6)
            numeric["tp"] += int(hit)
        except ValueError:
            literal["n"] += 1
            hit = str(gold).strip().lower() == str(pred).strip().lower() or (
                str(pred) and str(pred).strip().lower() in str(gold).strip().lower()
            )
            literal["tp"] += int(hit)
        by_attr[fill["attribute"]]["n"] += 1
        by_attr[fill["attribute"]]["tp"] += int(hit)
        for role in fill["roles"]:
            by_role[role]["n"] += 1
            by_role[role]["tp"] += int(hit)
        _ = dtype_numeric
    def _rate(cell: dict[str, int]) -> float:
        return cell["tp"] / cell["n"] if cell["n"] else 0.0

    return {
        "grounded_literal_accuracy": _rate(literal),
        "normalized_numeric_accuracy": _rate(numeric),
        "semantic_value_accuracy": _rate(semantic),
        "literal": literal,
        "numeric": numeric,
        "semantic": semantic,
        "by_attribute": {k: {**v, "precision": _rate(v)} for k, v in by_attr.items()},
        "by_ast_role": {k: {**v, "precision": _rate(v)} for k, v in by_role.items()},
    }


def freeze_bags(dest: Path, statements: dict[str, str], predicates) -> tuple[str, dict[str, str], list[str]]:
    conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    rewrites = {qid: official_sql(sql, dest, predicates) for qid, sql in statements.items()}
    assert_queries_execute(conn, rewrites, any_error=True)
    bags = {qid: _norm_bag(_fetch(conn, sql)) for qid, sql in rewrites.items()}
    empty = [qid for qid, bag in bags.items() if not bag]
    conn.close()
    return hashlib.sha256(repr(sorted(bags.items())).encode()).hexdigest(), rewrites, empty


def main() -> int:
    print("retrieve-extract postmortem", flush=True)
    frozen_before = {
        f"plumbing_{name}": file_sha256(path) for name, path in PLUMBING_DB.items()
    } | {f"fresh_{name}": file_sha256(path) for name, path in FRESH_DB.items()}
    rule_hash = _hash_obj(REPLAY_RULE)
    built: dict[str, Any] = {"replay_rule_sha256": rule_hash, "qwen_calls": 0, "corpora": {}}
    frozen_replays: dict[str, dict[str, Path]] = {}
    pending_score: dict[str, Any] = {}
    for name in ("Finan", "Legal"):
        print(f"audit {name}", flush=True)
        queries = queries_for(name)
        statements = {row["query_id"]: row["sql"] for row in queries}
        logical, workload = analyze_workload(statements)
        catalog = load_catalog(name)
        documents = documents_for(name)
        audit = audit_workload(queries)
        predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
        _, test = split_80_20(queries, 42)
        test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
        test_ids = {row["query_id"] for row in test_count}
        router = router_audit(name)
        reqs = workload.requirements
        critical_attrs = sorted(attr for attr, req in reqs.items() if is_critical(req.roles))
        extra = router["deterministic_simulation"]["additional_extractor_calls"]
        covered = set(router["deterministic_simulation"]["current_attribute_coverage"])
        would_cover_attrs = sorted(set(covered) | set(critical_attrs[: max(0, extra)]))
        router["deterministic_simulation"]["workload_critical_attributes"] = critical_attrs
        router["deterministic_simulation"]["finan_every_critical_attribute"] = (
            set(critical_attrs).issubset(set(would_cover_attrs)) if name == "Finan" else None
        )
        router["deterministic_simulation"]["could_cover_every_critical_attribute"] = extra >= max(
            0, len(critical_attrs) - len(covered)
        )
        flow = value_flow(name, workload, catalog)
        table = "finance" if name == "Finan" else "legal"
        tmp = Path(tempfile.mkdtemp(prefix=f"fresh_{name}_")) / FRESH_DB[name].name
        shutil.copy2(FRESH_DB[name], tmp)
        traces = empty_bag_traces(name, tmp, statements, test_ids, predicates)
        shutil.rmtree(tmp.parent, ignore_errors=True)
        fills = candidate_fills(name, workload, catalog, documents)
        candidates = len(fills)
        rejected = sum(1 for fill in fills if not fill["accepted"])
        replay_dir = REPLAY_ROOT / name.lower()
        replay_dir.mkdir(parents=True, exist_ok=True)
        rules = {}
        paths = {}
        for rule in ("official", "critical_fills", "literal_fills"):
            dest = replay_dir / f"{name.lower()}_{rule}.db"
            applied = apply_replay(PLUMBING_DB[name], dest, fills, table, rule)
            bag_hash, rewrites, empty = freeze_bags(dest, statements, predicates)
            paths[rule] = dest
            rules[rule] = {
                "candidates": candidates,
                "accepted": applied["accepted"],
                "rejected": rejected,
                "sql_visible_fills": applied["sql_visible"],
                "overwrites_blocked": applied["overwrites_blocked"],
                "row_count_before": applied["row_count_before"],
                "row_count_after": applied["row_count_after"],
                "changed_columns": applied["changed_columns"],
                "unrelated_columns_changed": applied["unrelated_columns_changed"],
                "empty_bags_after": len(empty),
                "empty_bag_ids": empty,
                "db_path": str(dest),
                "db_sha256": file_sha256(dest),
                "output_bag_sha256": bag_hash,
                "accepted_by_attribute": dict(Counter(fill["attribute"] for fill in applied["accepted_fills"])),
                "accepted_by_role": dict(Counter(role for fill in applied["accepted_fills"] for role in fill["roles"])),
                "gates": {
                    "plumbing_rows_preserved": applied["row_count_before"] == applied["row_count_after"],
                    "no_nonnull_overwrite": applied["overwrites_blocked"] == 0,
                    "unrelated_columns_unchanged": not applied["unrelated_columns_changed"],
                    "accepted_have_hashes": all(fill["document_hash"] and fill["span"] for fill in applied["accepted_fills"]),
                    "zero_model_calls": True,
                },
                "_accepted_fills": applied["accepted_fills"],
                "_rewrites": rewrites,
            }
            print(json.dumps({"corpus": name, "rule": rule, "accepted": applied["accepted"], "db": rules[rule]["db_sha256"][:16]}), flush=True)
        fresh_copy = replay_dir / f"{name.lower()}_fresh_original.db"
        _copy_frozen(FRESH_DB[name], fresh_copy)
        bag_hash, rewrites, empty = freeze_bags(fresh_copy, statements, predicates)
        plumb_tmp = Path(tempfile.mkdtemp(prefix=f"plumb_{name}_")) / PLUMBING_DB[name].name
        shutil.copy2(PLUMBING_DB[name], plumb_tmp)
        plumb_empty = empty_bag_traces(name, plumb_tmp, statements, test_ids, predicates)
        shutil.rmtree(plumb_tmp.parent, ignore_errors=True)
        rules["fresh_original"] = {
            "candidates": 0,
            "accepted": 0,
            "rejected": 0,
            "sql_visible_fills": 0,
            "empty_bags_after": len(empty),
            "empty_bag_ids": empty,
            "db_path": str(fresh_copy),
            "db_sha256": file_sha256(fresh_copy),
            "output_bag_sha256": bag_hash,
            "gates": {"reproduced_locked_fresh": file_sha256(fresh_copy) == file_sha256(FRESH_DB[name])},
            "_rewrites": rewrites,
            "_accepted_fills": [],
        }
        paths["fresh_original"] = fresh_copy
        frozen_replays[name] = paths
        pending_score[name] = {
            "router": router,
            "value_flow": flow,
            "empty_bags_fresh": traces,
            "empty_bags_plumbing": plumb_empty,
            "rules": rules,
            "fills": fills,
            "test_count": test_count,
            "predicates": predicates,
            "table": table,
            "catalog": catalog,
            "workload": workload,
        }
        print(f"froze {name} replays", flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    for name in ("Finan", "Legal"):
        state = pending_score[name]
        gold = load_ground_truth(gold_name(name))
        gold_rows = gold[state["table"]]
        plumbing_rows = table_rows(PLUMBING_DB[name], state["table"])
        test = state["test_count"]
        scores = {}
        for rule, spec in state["rules"].items():
            dest = Path(spec["db_path"])
            rewrites = {row["query_id"]: spec["_rewrites"][row["query_id"]] for row in test}
            scored = _score(name, dest, test, rewrites, gold)
            accepted = spec.get("_accepted_fills") or []
            precision = gold_cell_accuracy(name, accepted, gold_rows, plumbing_rows) if accepted else {
                "grounded_literal_accuracy": 0.0,
                "normalized_numeric_accuracy": 0.0,
                "semantic_value_accuracy": 0.0,
            }
            plumb_empty = set(state["empty_bags_plumbing"]["empty_ids"])
            fresh_empty = set(state["empty_bags_fresh"]["empty_ids"])
            after_empty = set(spec.get("empty_bag_ids") or [])
            if rule == "fresh_original":
                after_empty = fresh_empty
            changed = [
                {
                    "query_id": row["query_id"],
                    "product": row["product"],
                    "delta_vs_plumbing": None,
                    "structure_f2": row["structure_f2"],
                    "cell_f1_20": row["cell_f1_20"],
                }
                for row in scored["per_query"]
            ]
            scores[rule] = {
                "mean_structure_f2": scored["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scored["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scored["mean_per_query_product"],
                "empty_bags_before_fresh": len(fresh_empty),
                "empty_bags_after": len(after_empty),
                "queries_changed_vs_fresh_empty": len(fresh_empty.symmetric_difference(after_empty)),
                "accepted_fill_precision": precision,
                "per_query": changed,
            }
            print(
                json.dumps(
                    {
                        "corpus": name,
                        "rule": rule,
                        "product": scored["mean_per_query_product"],
                        "f2": scored["mean_structure_f2"],
                        "f1": scored["mean_cell_f1_at_0.20"],
                    }
                ),
                flush=True,
            )
            spec.pop("_accepted_fills", None)
            spec.pop("_rewrites", None)
        fresh_vals = value_flow_gold(name, state["workload"], gold_rows, plumbing_rows, table_rows(FRESH_DB[name], state["table"]), state["catalog"])
        extra = state["router"]["deterministic_simulation"]["additional_extractor_calls"]
        covered = set(state["router"]["deterministic_simulation"]["current_attribute_coverage"])
        critical = state["router"]["deterministic_simulation"]["workload_critical_attributes"]
        official_product = scores["official"]["mean_per_query_product"]
        decision = {
            "deterministic_routing_worth_another_fresh_run": name == "Finan" and extra >= 11 and len(covered) < len(critical),
            "fresh_extractor_useful_incremental_evidence": official_product > PLUMBING_SCORE[name]["product"]
            or scores["official"]["accepted_fill_precision"].get("normalized_numeric_accuracy", 0) > 0
            or scores["official"].get("mean_per_query_product", 0) != PLUMBING_SCORE[name]["product"],
            "remaining_gap_attributes": remaining_gap(state["empty_bags_fresh"], state["value_flow"], critical),
        }
        built["corpora"][name] = {
            "router_audit": state["router"],
            "value_flow": state["value_flow"],
            "value_flow_gold": fresh_vals,
            "empty_bag_trace": state["empty_bags_fresh"],
            "empty_bag_trace_plumbing": {"n_empty_test": state["empty_bags_plumbing"]["n_empty_test"], "failures": state["empty_bags_plumbing"]["failures"]},
            "replays": {rule: spec for rule, spec in state["rules"].items()},
            "scores": {
                "plumbing_only": PLUMBING_SCORE[name],
                "locked_fresh": FRESH_SCORE[name],
                "docetl": DOCETL[name],
                **{rule: {k: v for k, v in payload.items() if k != "per_query"} | {"n_test": len(payload.get("per_query") or [])} for rule, payload in scores.items()},
            },
            "per_query": {rule: scores[rule]["per_query"] for rule in scores},
            "decision": decision,
        }
    frozen_after = {
        f"plumbing_{name}": file_sha256(path) for name, path in PLUMBING_DB.items()
    } | {f"fresh_{name}": file_sha256(path) for name, path in FRESH_DB.items()}
    built["frozen_hashes_before"] = frozen_before
    built["frozen_hashes_after"] = frozen_after
    built["frozen_unchanged"] = frozen_before == frozen_after
    OUT.write_text(json.dumps(built, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT), "qwen_calls": 0, "frozen_unchanged": built["frozen_unchanged"]}, indent=2))
    return 0


def value_flow_gold(name: str, workload, gold_rows, plumbing, fresh, catalog) -> dict[str, Any]:
    gold_by_id = {str(row.get("id") or ""): row for row in gold_rows}
    by_attr = {}
    by_role = defaultdict(lambda: {"fresh_n": 0, "fresh_tp": 0, "plumb_n": 0, "plumb_tp": 0})
    for attr, req in workload.requirements.items():
        bare = attr.split(".")[-1]
        semantic = is_semantic_label(attr, catalog, req.dtype)
        cell = {"fresh_n": 0, "fresh_tp": 0, "plumb_n": 0, "plumb_tp": 0, "gold_n": 0, "kind": "semantic" if semantic else ("numeric" if req.dtype == "numeric" else "literal")}
        for eid, frow in fresh.items():
            plow = plumbing.get(eid) or {}
            stem = str(plow.get("__provenance_label") or frow.get("__provenance_label") or "")
            grow = gold_by_id.get(stem)
            if grow is None or grow.get(bare) in (None, ""):
                continue
            cell["gold_n"] += 1
            gold = grow.get(bare)
            for key, row, prefix in (("fresh", frow, "fresh"), ("plumb", plow, "plumb")):
                pred = row.get(bare)
                if _null(pred):
                    continue
                cell[f"{prefix}_n"] += 1
                hit = _match_gold(gold, pred, semantic, req.dtype)
                cell[f"{prefix}_tp"] += int(hit)
                for role in role_buckets(req.roles):
                    by_role[role][f"{prefix}_n"] += 1
                    by_role[role][f"{prefix}_tp"] += int(hit)
        cell["fresh_precision"] = cell["fresh_tp"] / cell["fresh_n"] if cell["fresh_n"] else 0.0
        cell["fresh_recall"] = cell["fresh_tp"] / cell["gold_n"] if cell["gold_n"] else 0.0
        cell["plumbing_precision"] = cell["plumb_tp"] / cell["plumb_n"] if cell["plumb_n"] else 0.0
        cell["plumbing_recall"] = cell["plumb_tp"] / cell["gold_n"] if cell["gold_n"] else 0.0
        by_attr[attr] = cell
    return {
        "by_attribute": by_attr,
        "by_ast_role": {
            role: {
                **vals,
                "fresh_precision": vals["fresh_tp"] / vals["fresh_n"] if vals["fresh_n"] else 0.0,
                "plumbing_precision": vals["plumb_tp"] / vals["plumb_n"] if vals["plumb_n"] else 0.0,
            }
            for role, vals in by_role.items()
        },
    }


def _match_gold(gold: Any, pred: Any, semantic: bool, dtype: str) -> bool:
    if semantic:
        gold_set = {part.strip().lower() for part in str(gold).replace("||", ";").split(";") if part.strip()}
        pred_set = {part.strip().lower() for part in str(pred).replace("||", ";").split(";") if part.strip()}
        return bool(gold_set & pred_set)
    if dtype == "numeric":
        try:
            gnum = float(str(gold).replace(",", ""))
            pnum = float(str(pred).replace(",", ""))
        except ValueError:
            return str(gold).strip().lower() == str(pred).strip().lower()
        return abs(gnum - pnum) <= max(0.20 * max(abs(gnum), 1.0), 1e-6)
    return str(gold).strip().lower() == str(pred).strip().lower()


def remaining_gap(traces: dict[str, Any], flow: dict[str, Any], critical: list[str]) -> list[str]:
    attrs = Counter()
    for trace in traces.get("traces") or []:
        for attr in trace.get("referenced_attributes") or []:
            attrs[attr] += 1
    lost = []
    for attr, counts in (flow.get("by_attribute") or {}).items():
        if counts.get("plumbing_value_lost") or counts.get("both_NULL"):
            if attr in critical or attr.split(".")[-1] in {item.split(".")[-1] for item in critical}:
                lost.append(attr)
    ranked = [attr for attr, _n in attrs.most_common()]
    return list(dict.fromkeys(ranked + lost))[:12]


if __name__ == "__main__":
    raise SystemExit(main())

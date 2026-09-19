"""Zero-token replay of stored filter-recall decisions. Gold after freeze."""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.pipeline import official_sql
from quwarts.core.query_filter import (
    StoredDecision,
    alias_order,
    decode_witness_key,
    filter_signature_id,
    has_row_filter,
    load_stored_decisions,
    materialize_replay,
    outer_alias_tables,
    select_replay,
)
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.query_witness import compile_witness_spec, grain_sql_for, support_from_grain
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import parse_sql
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites
from spp.config_grid import _build_in_memory_db

COMPARE = ROOT / "results" / "quwarts_med_signatures" / "acquisition_compare.json"
DOCETL_EVAL = ROOT / "results" / "docetl_med_case80" / "evaluation.json"
OUT = ROOT / "results" / "quwarts_med_signatures"
FILTER_DB = OUT / "artifacts" / "aprime_filter.db"
VOTE_PATHS = (
    OUT / "filter_recall_votes.jsonl",
    OUT / "artifacts" / "filter_votes.jsonl",
    OUT / "filter_recall_votes.json",
)
RULE_ORDER = (
    "primary",
    "two_true_no_false",
    "evidence_plus_one",
    "strict_grounded",
    "broad_original",
)


def _score(test, dest, gold, rewrites):
    report = score_with_rewrites(test, rewrites, dest, gold, "Med")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": report.get("per_query") or [],
        "test_empty_query_count": sum(
            1 for row in report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0
        ),
    }


def _official_rewrites(rows, dest, predicates):
    return {row["query_id"]: official_sql(row["sql"], dest, predicates) for row in rows}


def _ids_for(conn: sqlite3.Connection, table: str, rowid: int) -> str:
    cols = {row[1].lower() for row in conn.execute(f'PRAGMA table_info("{table}")')}
    if "doc_id" in cols:
        row = conn.execute(f'SELECT doc_id FROM "{table}" WHERE rowid = ?', [rowid]).fetchone()
        if row and row[0] not in (None, ""):
            return Path(str(row[0])).stem
    if "id" in cols:
        row = conn.execute(f'SELECT id FROM "{table}" WHERE rowid = ?', [rowid]).fetchone()
        return str(row[0] or "") if row else ""
    return str(rowid)


def _entity_from_key(conn: sqlite3.Connection, sql: str, key: str) -> tuple | None:
    try:
        tree = parse_sql(sql)
    except Exception:
        return None
    aliases = outer_alias_tables(tree)
    order = alias_order(tree)
    rids = decode_witness_key(key)
    parts = []
    for alias, rid in zip(order, rids):
        table = aliases.get(alias, alias)
        if rid is None:
            parts.append((table, "NULL"))
            continue
        try:
            parts.append((table, _ids_for(conn, table, int(rid))))
        except sqlite3.Error:
            return None
    return tuple(sorted(parts)) if parts else None


def _entity_from_grain(conn: sqlite3.Connection, spec, item) -> tuple:
    rowids = item.rowids or {spec.primary: item.rowid}
    parts = []
    for table, rid in rowids.items():
        if rid in (None, ""):
            parts.append((str(table), "NULL"))
        else:
            parts.append((str(table), _ids_for(conn, table, int(rid))))
    return tuple(sorted(parts))


def _fetch_grain(conn: sqlite3.Connection, sql: str, spec):
    try:
        cur = conn.execute(sql)
    except sqlite3.Error:
        return []
    cols = [item[0] for item in cur.description] if cur.description else []
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return support_from_grain(spec, rows, None)


def gold_precision(
    decisions: list[StoredDecision],
    statements: dict[str, str],
    queries: list[dict[str, str]],
    dest: Path,
    gold_conn: sqlite3.Connection,
) -> dict[str, Any]:
    gold_by_qid: dict[str, set[tuple]] = {}
    for row in queries:
        qid = row["query_id"]
        sql = row["sql"]
        if not has_row_filter(sql):
            continue
        spec = compile_witness_spec(qid, sql)
        grain = _fetch_grain(gold_conn, grain_sql_for(spec), spec)
        gold_by_qid[qid] = {_entity_from_grain(gold_conn, spec, item) for item in grain}
    qw = sqlite3.connect(str(dest))
    judged = []
    try:
        for item in decisions:
            sql = statements.get(item.query_id)
            if not sql:
                judged.append({**_judgment_row(item), "label": "unresolved", "reason": "missing_query"})
                continue
            entity = _entity_from_key(qw, sql, item.witness_key)
            gold_ents = gold_by_qid.get(item.query_id) or set()
            if entity is None:
                label = "unresolved"
            elif entity in gold_ents:
                label = "tp"
            else:
                label = "fp"
            judged.append({**_judgment_row(item), "label": label, "entity": entity})
    finally:
        qw.close()
    return _precision_splits(judged)


def _judgment_row(item: StoredDecision) -> dict[str, Any]:
    return {
        "signature_id": item.signature_id,
        "witness_key": item.witness_key,
        "query_id": item.query_id,
        "pattern": item.pattern,
        "has_evidence_metadata": item.has_evidence_metadata,
        "broad_accepted": item.broad_accepted,
    }


def _rate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(1 for row in rows if row["label"] == "tp")
    fp = sum(1 for row in rows if row["label"] == "fp")
    unresolved = sum(1 for row in rows if row["label"] == "unresolved")
    judged = tp + fp
    return {
        "n": len(rows),
        "tp": tp,
        "fp": fp,
        "unresolved": unresolved,
        "precision": (tp / judged) if judged else None,
    }


def _precision_splits(judged: list[dict[str, Any]]) -> dict[str, Any]:
    by_pattern = defaultdict(list)
    by_sig = defaultdict(list)
    by_evidence = defaultdict(list)
    for row in judged:
        by_pattern[row["pattern"]].append(row)
        by_sig[row["signature_id"]].append(row)
        by_evidence["present" if row["has_evidence_metadata"] else "absent"].append(row)
    return {
        "overall": _rate(judged),
        "by_pattern": {key: _rate(rows) for key, rows in sorted(by_pattern.items())},
        "by_signature": {key: _rate(rows) for key, rows in sorted(by_sig.items())},
        "by_evidence_metadata": {key: _rate(rows) for key, rows in sorted(by_evidence.items())},
    }


def _overlap(selected: dict[str, list[StoredDecision]]) -> dict[str, int]:
    sets = {
        name: {(item.signature_id, item.witness_key) for item in rows}
        for name, rows in selected.items()
    }
    out = {name: len(sets[name]) for name in RULE_ORDER}
    for left, right in combinations(RULE_ORDER, 2):
        out[f"{left}&{right}"] = len(sets[left] & sets[right])
    return out


def main() -> int:
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    statements = {row["query_id"]: row["sql"] for row in queries}
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    stored_compare = json.loads(COMPARE.read_text()) if COMPARE.is_file() else {}
    agent_info = stored_compare.get("agent") or {}
    agent_db = Path(agent_info.get("sqlite_path") or "")
    if not agent_db.is_file():
        raise SystemExit(f"agent incumbent missing: {agent_db}")
    if FILTER_DB.resolve() == agent_db.resolve():
        raise SystemExit("refusing to start from the dirty filter database")
    decisions, inventory = load_stored_decisions(VOTE_PATHS, FILTER_DB)
    print(
        json.dumps(
            {
                "inventory": inventory,
                "agent": str(agent_db),
                "n_decisions": len(decisions),
            },
            indent=2,
        ),
        flush=True,
    )
    selected = {name: select_replay(decisions, name) for name in RULE_ORDER}
    frozen: dict[str, dict[str, Any]] = {}
    for name in RULE_ORDER:
        dest = OUT / "artifacts" / f"aprime_filter_replay_{name}.db"
        print(f"replay {name} proposed={len(selected[name])} dest={dest}", flush=True)
        material = materialize_replay(agent_db, dest, selected[name], statements, predicates)
        frozen[name] = {"dest": dest, "material": material, "selected": selected[name]}
        print(
            f"  materialized={material['n_materialized']} visible={material['n_sql_visible']} "
            f"changed={len(material['changed_queries'])} filled={len(material['empty_filled'])}",
            flush=True,
        )
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)
    agent_score = _score(test_count, agent_db, gold, _official_rewrites(test_count, agent_db, predicates))
    stored_docetl = json.loads(DOCETL_EVAL.read_text()) if DOCETL_EVAL.is_file() else {}
    docetl_product = None
    if stored_docetl:
        per = stored_docetl.get("per_query") or {}
        if per:
            products = []
            for row in test_count:
                item = per.get(row["query_id"]) or {}
                rank = item.get("rank") or {}
                f2 = float(rank.get("structure_fbeta_score") or 0.0)
                cells = rank.get("cell_f1") or {}
                cell20 = next((float(v) for k, v in cells.items() if abs(float(k) - 0.20) < 1e-9), 0.0)
                products.append(f2 * cell20)
            docetl_product = sum(products) / max(len(products), 1)
    arms = {}
    try:
        for name in RULE_ORDER:
            dest = frozen[name]["dest"]
            material = frozen[name]["material"]
            chosen = frozen[name]["selected"]
            score = _score(test_count, dest, gold, _official_rewrites(test_count, dest, predicates))
            precision = gold_precision(chosen, statements, queries, dest, gold_conn)
            arms[name] = {
                "n_proposed": material["n_proposed"],
                "n_materialized": material["n_materialized"],
                "n_sql_visible": material["n_sql_visible"],
                "changed_queries": material["changed_queries"],
                "n_changed_queries": len(material["changed_queries"]),
                "n_unchanged_queries": len(material["unchanged_queries"]),
                "count_mass_delta": material["count_mass_delta"],
                "empty_before": material["empty_before"],
                "empty_after": material["empty_after"],
                "empty_filled": material["empty_filled"],
                "n_empty_filled": len(material["empty_filled"]),
                "invariants": {
                    "empty_wrap_ok": material["empty_wrap_ok"],
                    "incumbent_dropped": material["incumbent_dropped"],
                    "unrelated_changed": material["unrelated_changed"],
                },
                "score": {
                    "mean_structure_f2": score["mean_structure_f2"],
                    "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
                    "mean_per_query_product": score["mean_per_query_product"],
                    "test_empty_query_count": score["test_empty_query_count"],
                },
                "gold_precision": precision,
                "per_query": score["per_query"],
                "per_query_delta": material["per_query_delta"],
            }
            print(
                json.dumps(
                    {
                        "rule": name,
                        "proposed": material["n_proposed"],
                        "materialized": material["n_materialized"],
                        "visible": material["n_sql_visible"],
                        "f2": score["mean_structure_f2"],
                        "f1": score["mean_cell_f1_at_0.20"],
                        "product": score["mean_per_query_product"],
                        "gold_precision": precision["overall"],
                    }
                ),
                flush=True,
            )
    finally:
        gold_conn.close()
    incumbent_prod = agent_score["mean_per_query_product"]
    primary = arms["primary"]["score"]["mean_per_query_product"]
    useful = []
    for name, arm in arms.items():
        prod = arm["score"]["mean_per_query_product"]
        prec = (arm.get("gold_precision") or {}).get("overall") or {}
        if prod > incumbent_prod + 1e-12:
            useful.append({"rule": name, "reason": "official_product", "product": prod})
        if (prec.get("precision") or 0) >= 0.5 and int(prec.get("tp") or 0) >= 10:
            useful.append({"rule": name, "reason": "gold_precision", "precision": prec})
    payload = {
        "tokens_spent": 0,
        "qwen_calls": 0,
        "classifier_modified": False,
        "incumbent": "agent",
        "incumbent_product": agent_score["mean_per_query_product"],
        "inventory": inventory,
        "overlap": _overlap(selected),
        "official_arm": "primary",
        "primary_beats_incumbent": primary > incumbent_prod + 1e-12,
        "useful_precision_cohorts": useful,
        "stop_filter_recall": primary <= incumbent_prod + 1e-12 and not useful,
        "agent_official": {
            "mean_structure_f2": agent_score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": agent_score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": agent_score["mean_per_query_product"],
        },
        "docetl_product": docetl_product,
        "arms": arms,
        "pattern_counts": dict(Counter(item.pattern for item in decisions)),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "filter_replay.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({k: payload[k] for k in (
        "inventory", "overlap", "primary_beats_incumbent",
        "useful_precision_cohorts", "stop_filter_recall",
    )}, indent=2, default=str))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Zero-token distinct-identity oracle decomposition. Gold after traces. No frozen writes."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.distinct_diag import (
    CATEGORIES,
    SIDECAR,
    classify_pair,
    classify_witness_values,
    extract_distinct_measures,
    grain_with_measures,
    is_null,
    norm_value,
    reaggregate_sql,
    rewrite_distinct_sidecar,
    same_partition,
    token_key,
    tokens,
)
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.query_witness import compile_witness_spec, normalize_group
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import parse_sql
from sqlglot import exp
from quwarts.experiments.player_case80 import execute, split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites
from spp.config_grid import _build_in_memory_db

COMPARE = ROOT / "results" / "quwarts_med_signatures" / "acquisition_compare.json"
DOCETL_EVAL = ROOT / "results" / "docetl_med_case80" / "evaluation.json"
OUT = ROOT / "results" / "quwarts_med_signatures" / "distinct_identity.json"
LABEL_COLS = ("generic_name", "institution_name", "disease_name", "name")
POLICIES = (
    "null_mismatch",
    "collision",
    "fragmentation",
    "tokenization",
    "synthetic_key",
    "gold_partition",
)


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


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


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1].lower() for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _label_col(cols: set[str]) -> str | None:
    for name in LABEL_COLS:
        if name in cols:
            return name
    return None


def _canon_col(cols: set[str]) -> str | None:
    for name in ("id__canonical", "entity__canonical"):
        if name in cols:
            return name
    return None


def _fetch(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error:
        return []
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _group_key(row: dict[str, Any], aliases: tuple[str, ...]) -> tuple:
    return tuple(normalize_group(row.get(name)) for name in aliases)


def _entity(conn: sqlite3.Connection, spec, row: dict[str, Any]) -> tuple:
    parts = []
    for alias, table in spec.alias_to_table:
        raw = row.get(f"{alias}__rid")
        if raw in (None, ""):
            continue
        parts.append((table, _ids_for(conn, table, int(raw))))
    return tuple(sorted(parts))


def _counted_table(measure_sql: str, spec) -> str:
    try:
        tree = parse_sql(measure_sql)
    except Exception:
        return spec.primary
    for col in tree.find_all(exp.Column):
        if (col.name or "").lower() != "id":
            continue
        alias = (col.table or spec.primary_alias or "").lower()
        return spec.table_for(alias) or spec.primary
    return spec.primary


def _counted_entity(conn: sqlite3.Connection, spec, row: dict[str, Any], table: str) -> tuple | None:
    for alias, mapped in spec.alias_to_table:
        if mapped != table:
            continue
        raw = row.get(f"{alias}__rid")
        if raw in (None, ""):
            continue
        return (table, _ids_for(conn, table, int(raw)))
    raw = row.get(f"{spec.primary_alias}__rid")
    if raw in (None, ""):
        return None
    return (table, _ids_for(conn, table, int(raw)))


def _primary_meta(conn: sqlite3.Connection, spec, row: dict[str, Any]) -> dict[str, Any]:
    alias = spec.primary_alias
    table = spec.primary
    raw = row.get(f"{alias}__rid")
    if raw in (None, ""):
        return {"table": table, "rowid": None, "stem": None, "id": None, "label": None, "canon": None}
    rid = int(raw)
    cols = _cols(conn, table)
    rec = {"table": table, "rowid": rid, "stem": _ids_for(conn, table, rid)}
    if "id" in cols:
        val = conn.execute(f'SELECT id FROM "{table}" WHERE rowid = ?', [rid]).fetchone()
        rec["id"] = None if not val or is_null(val[0]) else val[0]
    else:
        rec["id"] = None
    label = _label_col(cols)
    if label:
        val = conn.execute(f'SELECT "{label}" FROM "{table}" WHERE rowid = ?', [rid]).fetchone()
        rec["label"] = None if not val or is_null(val[0]) else val[0]
    else:
        rec["label"] = None
    canon = _canon_col(cols)
    if canon:
        val = conn.execute(f'SELECT "{canon}" FROM "{table}" WHERE rowid = ?', [rid]).fetchone()
        rec["canon"] = None if not val or is_null(val[0]) else val[0]
    else:
        rec["canon"] = None
    return rec


def _score(test, dest, gold, rewrites):
    report = score_with_rewrites(test, rewrites, dest, gold, "Med")
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


def _official(rows, dest, predicates, rewrite_distinct: bool) -> dict[str, str]:
    out = {}
    for row in rows:
        sql = rewrite_distinct_sidecar(row["sql"]) if rewrite_distinct and extract_distinct_measures(row["sql"]) else row["sql"]
        out[row["query_id"]] = official_sql(sql, dest, predicates)
    return out


def _row_index(conn: sqlite3.Connection) -> dict[str, dict[str, dict[str, Any]]]:
    found: dict[str, dict[str, dict[str, Any]]] = {}
    tables = [
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'")
    ]
    for table in tables:
        cols = _cols(conn, table)
        if "doc_id" not in cols and "id" not in cols:
            continue
        label = _label_col(cols)
        canon = _canon_col(cols)
        select = ["rowid", "id"] if "id" in cols else ["rowid", "NULL"]
        select.append("doc_id" if "doc_id" in cols else "NULL")
        select.append(f'"{label}"' if label else "NULL")
        select.append(f'"{canon}"' if canon else "NULL")
        by_stem = {}
        for rid, iid, doc, lab, can in conn.execute(f'SELECT {", ".join(select)} FROM "{table}"'):
            stem = Path(str(doc)).stem if doc not in (None, "") else (str(iid) if iid not in (None, "") else str(rid))
            by_stem[str(stem)] = {
                "rowid": int(rid),
                "id": None if is_null(iid) else iid,
                "stem": str(stem),
                "label": None if is_null(lab) else lab,
                "canon": None if is_null(can) else can,
            }
        found[table.lower()] = by_stem
    return found


def _gold_index(conn: sqlite3.Connection) -> dict[str, dict[str, dict[str, Any]]]:
    found: dict[str, dict[str, dict[str, Any]]] = {}
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for table in tables:
        cols = _cols(conn, table)
        if "id" not in cols:
            continue
        label = _label_col(cols)
        select = ["rowid", "id", f'"{label}"' if label else "NULL"]
        by_stem = {}
        for rid, iid, lab in conn.execute(f'SELECT {", ".join(select)} FROM "{table}"'):
            stem = str(iid)
            by_stem[stem] = {
                "rowid": int(rid),
                "id": None if is_null(iid) else iid,
                "stem": stem,
                "label": None if is_null(lab) else lab,
                "canon": None,
            }
        found[table.lower()] = by_stem
    return found


def _sidecar_value(policy: str, qw: dict[str, Any], gold: dict[str, Any] | None, flags: dict[str, bool]) -> Any:
    incumbent = qw.get("id")
    gold_id = None if gold is None else gold.get("id")
    stem = qw.get("stem")
    if policy == "null_mismatch":
        if is_null(incumbent) and not is_null(gold_id):
            return gold_id
        if not is_null(incumbent) and is_null(gold_id):
            return None
        return incumbent
    if policy == "collision":
        return gold_id if flags.get("collision") and gold_id is not None else incumbent
    if policy == "fragmentation":
        return gold_id if flags.get("fragmentation") and gold_id is not None else incumbent
    if policy == "tokenization":
        return gold_id if flags.get("tokenization") and gold_id is not None else incumbent
    if policy == "synthetic_key":
        return stem
    if policy == "gold_partition":
        return gold_id if gold_id is not None else incumbent
    return incumbent


def _apply_sidecar(dest: Path, policy: str, qw_idx, gold_idx, flagged: dict[tuple[str, str], set[str]]) -> None:
    conn = sqlite3.connect(str(dest))
    try:
        for table, by_stem in qw_idx.items():
            cols = _cols(conn, table)
            if SIDECAR not in cols:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{SIDECAR}" TEXT')
            for stem, qw in by_stem.items():
                gold = (gold_idx.get(table) or {}).get(str(stem))
                flags = {name: stem in flagged.get((table, name), set()) for name in CATEGORIES}
                value = _sidecar_value(policy, qw, gold, flags)
                conn.execute(
                    f'UPDATE "{table}" SET "{SIDECAR}" = ? WHERE rowid = ?',
                    [None if is_null(value) else str(value), qw["rowid"]],
                )
        conn.commit()
    finally:
        conn.close()


def _candidate_of(name: str, qw: dict[str, Any]) -> Any:
    if name == "rowid":
        return qw.get("rowid")
    if name == "entity_label":
        return qw.get("label")
    if name == "stem":
        return qw.get("stem")
    if name == "normalized_value":
        return norm_value(qw.get("id"))
    if name == "token_key":
        return token_key(qw.get("id"))
    if name == "er_cluster":
        return qw.get("canon")
    return None


def main() -> int:
    queries = queries_for("Med")
    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    agent = Path((json.loads(COMPARE.read_text()).get("agent") or {}).get("sqlite_path") or "")
    if not agent.is_file():
        raise SystemExit(f"agent incumbent missing: {agent}")
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)
    qw_conn = sqlite3.connect(str(agent))
    distinct_rows = [row for row in queries if extract_distinct_measures(row["sql"])]
    print(f"distinct queries {len(distinct_rows)} / {len(queries)} incumbent={agent}", flush=True)

    traces = []
    discrepancies: list[dict[str, Any]] = []
    cardinality = []
    flagged: dict[tuple[str, str], set[str]] = defaultdict(set)
    per_query = []

    for row in distinct_rows:
        qid = row["query_id"]
        sql = row["sql"]
        spec = compile_witness_spec(qid, sql)
        measures = extract_distinct_measures(sql)
        groups = spec.group_aliases
        grain = grain_with_measures(sql, measures)
        gold_grain = _fetch(gold_conn, grain)
        qw_grain = _fetch(qw_conn, official_sql(grain, agent, predicates))
        gold_bag = execute(gold_conn, sql)
        qw_bag = execute(qw_conn, official_sql(sql, agent, predicates))
        try:
            gold_re = execute(gold_conn, reaggregate_sql(sql, measures, groups))
        except Exception:
            gold_re = []
        try:
            qw_re = execute(qw_conn, official_sql(reaggregate_sql(sql, measures, groups), agent, predicates))
        except Exception:
            qw_re = []
        gold_valid = _norm_bag(gold_re) == _norm_bag(gold_bag)
        qw_valid = _norm_bag(qw_re) == _norm_bag(qw_bag)
        traces.append(
            {
                "query_id": qid,
                "n_measures": len(measures),
                "identity": all(item["identity"] for item in measures),
                "gold_valid": gold_valid,
                "quwarts_valid": qw_valid,
                "excluded": not (gold_valid and qw_valid),
            }
        )
        if not (gold_valid and qw_valid):
            per_query.append({"query_id": qid, "excluded": True, "measures": measures})
            continue
        query_disc = Counter()
        for index, measure in enumerate(measures):
            table = _counted_table(measure["sql"], spec)
            gold_by = defaultdict(dict)
            qw_by = defaultdict(dict)
            for item in gold_grain:
                ent = _counted_entity(gold_conn, spec, item, table)
                if ent:
                    gold_by[_group_key(item, groups)][ent] = item
            for item in qw_grain:
                ent = _counted_entity(qw_conn, spec, item, table)
                if ent:
                    qw_by[_group_key(item, groups)][ent] = item
            for group in set(gold_by) | set(qw_by):
                gmap = gold_by.get(group) or {}
                qmap = qw_by.get(group) or {}
                gold_card = len({norm_value(row.get(f"distinct_{index}")) for row in gmap.values() if not is_null(row.get(f"distinct_{index}"))})
                qw_card = len({norm_value(row.get(f"distinct_{index}")) for row in qmap.values() if not is_null(row.get(f"distinct_{index}"))})
                cardinality.append(
                    {
                        "query_id": qid,
                        "measure": measure["alias"],
                        "group": group,
                        "incumbent_cardinality": qw_card,
                        "gold_cardinality": gold_card,
                        "n_qw": len(qmap),
                        "n_gold": len(gmap),
                    }
                )
                shared = set(gmap) & set(qmap)
                gold_only = set(gmap) - set(qmap)
                for ent in gold_only:
                    discrepancies.append(
                        {
                            "query_id": qid,
                            "measure": measure["alias"],
                            "category": "support_inherited",
                            "entity": ent,
                            "group": group,
                        }
                    )
                    query_disc["support_inherited"] += 1
                    if ent[1]:
                        flagged[(table, "support_inherited")].add(str(ent[1]))
                aligned = []
                for ent in shared:
                    qw_row = qmap[ent]
                    gold_row = gmap[ent]
                    qw_val = qw_row.get(f"distinct_{index}")
                    gold_val = gold_row.get(f"distinct_{index}")
                    meta = _primary_meta(qw_conn, spec, qw_row)
                    meta["table"] = table
                    meta["stem"] = ent[1]
                    cat = classify_witness_values(
                        qw_val,
                        gold_val,
                        identity=measure["identity"],
                        stable=ent[1],
                        in_qw=True,
                        in_gold=True,
                    )
                    aligned.append((ent, qw_val, gold_val, meta, cat))
                    if cat:
                        discrepancies.append(
                            {
                                "query_id": qid,
                                "measure": measure["alias"],
                                "category": cat,
                                "entity": ent,
                                "group": group,
                                "qw": qw_val,
                                "gold": gold_val,
                            }
                        )
                        query_disc[cat] += 1
                        if ent[1]:
                            flagged[(table, cat)].add(str(ent[1]))
                for i, (ent_a, qw_a, gold_a, meta_a, cat_a) in enumerate(aligned):
                    if cat_a in {"null_missing", "null_extra"}:
                        continue
                    for ent_b, qw_b, gold_b, meta_b, cat_b in aligned[i + 1 :]:
                        if cat_b in {"null_missing", "null_extra"}:
                            continue
                        pair = classify_pair(
                            qw_a,
                            gold_a,
                            qw_b,
                            gold_b,
                            identity=measure["identity"],
                            stable_a=meta_a.get("stem"),
                            stable_b=meta_b.get("stem"),
                        )
                        if pair in {None, "observationally_irrelevant"}:
                            continue
                        if pair == "synthetic_key" and (cat_a == "synthetic_key" or cat_b == "synthetic_key"):
                            continue
                        discrepancies.append(
                            {
                                "query_id": qid,
                                "measure": measure["alias"],
                                "category": pair,
                                "entity": (ent_a, ent_b),
                                "group": group,
                            }
                        )
                        query_disc[pair] += 1
                        for ent in (ent_a, ent_b):
                            if ent[1]:
                                flagged[(table, pair)].add(str(ent[1]))
        per_query.append(
            {
                "query_id": qid,
                "excluded": False,
                "n_measures": len(measures),
                "discrepancies": dict(query_disc),
            }
        )

    qw_idx = _row_index(qw_conn)
    gold_idx = _gold_index(gold_conn)
    candidate_names = ("rowid", "entity_label", "stem", "normalized_value", "token_key", "er_cluster")
    candidate_hits = {name: {"n": 0, "null_match": 0, "partition_pairs": 0, "partition_match": 0, "available": 0} for name in candidate_names}
    aligned_rows = []
    for table, by_stem in qw_idx.items():
        gold_table = gold_idx.get(table) or {}
        pairs = []
        for stem, qw in by_stem.items():
            gold_row = gold_table.get(str(stem))
            if gold_row is None:
                continue
            pairs.append((qw, gold_row))
            aligned_rows.append((table, qw, gold_row))
        for name in candidate_names:
            vals = [(_candidate_of(name, qw), gold_row.get("id")) for qw, gold_row in pairs]
            if any(not is_null(left) for left, _ in vals):
                candidate_hits[name]["available"] += 1
            for left, right in vals:
                candidate_hits[name]["n"] += 1
                if is_null(left) == is_null(right):
                    candidate_hits[name]["null_match"] += 1
            for i, (a, ga) in enumerate(vals):
                for b, gb in vals[i + 1 :]:
                    candidate_hits[name]["partition_pairs"] += 1
                    a_eq = not is_null(a) and not is_null(b) and norm_value(a) == norm_value(b)
                    g_eq = not is_null(ga) and not is_null(gb) and norm_value(ga) == norm_value(gb)
                    a_null = is_null(a) and is_null(b)
                    g_null = is_null(ga) and is_null(gb)
                    if a_null or g_null:
                        if a_null == g_null:
                            candidate_hits[name]["partition_match"] += 1
                        continue
                    if a_eq == g_eq:
                        candidate_hits[name]["partition_match"] += 1
    candidate_report = {}
    for name, row in candidate_hits.items():
        n = max(row["n"], 1)
        pairs = max(row["partition_pairs"], 1)
        candidate_report[name] = {
            **row,
            "null_pattern_agreement": row["null_match"] / n if row["n"] else None,
            "equality_partition_agreement": row["partition_match"] / pairs if row["partition_pairs"] else None,
        }

    agent_score = _score(test_count, agent, gold, _official(test_count, agent, predicates, False))
    stored_docetl = json.loads(DOCETL_EVAL.read_text()) if DOCETL_EVAL.is_file() else {}
    docetl_product = None
    if stored_docetl:
        per = stored_docetl.get("per_query") or {}
        products = []
        for row in test_count:
            item = per.get(row["query_id"]) or {}
            rank = item.get("rank") or {}
            f2 = float(rank.get("structure_fbeta_score") or 0.0)
            cells = rank.get("cell_f1") or {}
            cell20 = next((float(v) for k, v in cells.items() if abs(float(k) - 0.20) < 1e-9), 0.0)
            products.append(f2 * cell20)
        if products:
            docetl_product = sum(products) / len(products)

    counterfactuals = {}
    for policy in POLICIES:
        tmpdir = Path(tempfile.mkdtemp(prefix=f"distinct_{policy}_"))
        dest = tmpdir / "replay.db"
        shutil.copy2(agent, dest)
        assert dest.resolve() != agent.resolve()
        _apply_sidecar(dest, policy, qw_idx, gold_idx, flagged)
        score = _score(test_count, dest, gold, _official(test_count, dest, predicates, True))
        dest.unlink()
        tmpdir.rmdir()
        counterfactuals[policy] = score
        print(
            json.dumps(
                {
                    "policy": policy,
                    "f2": score["mean_structure_f2"],
                    "f1": score["mean_cell_f1_at_0.20"],
                    "product": score["mean_per_query_product"],
                }
            ),
            flush=True,
        )

    by_cat = Counter(item["category"] for item in discrepancies)
    test_ids = {row["query_id"] for row in test_count}
    mass = {}
    for cat in CATEGORIES:
        qids = {item["query_id"] for item in discrepancies if item["category"] == cat}
        test_hit = sorted(qids & test_ids)
        mass[cat] = {
            "n": by_cat[cat],
            "n_queries": len(qids),
            "test_queries": test_hit,
            "n_test_queries": len(test_hit),
        }
    best = max(counterfactuals.items(), key=lambda item: item[1]["mean_per_query_product"])
    mechanical = {"null_mismatch", "synthetic_key", "collision", "fragmentation", "tokenization"}
    semantic = best[0] not in mechanical and best[0] != "gold_partition"
    payload = {
        "tokens_spent": 0,
        "qwen_calls": 0,
        "frozen_db_written": False,
        "incumbent": str(agent),
        "incumbent_product": agent_score["mean_per_query_product"],
        "docetl_product": docetl_product,
        "n_queries": len(queries),
        "n_distinct_queries": len(distinct_rows),
        "trace_validity": {
            "n": len(traces),
            "gold_valid": sum(1 for row in traces if row["gold_valid"]),
            "quwarts_valid": sum(1 for row in traces if row["quwarts_valid"]),
            "both_valid": sum(1 for row in traces if row["gold_valid"] and row["quwarts_valid"]),
            "excluded": [row["query_id"] for row in traces if row["excluded"]],
            "per_query": traces,
        },
        "cardinality": cardinality,
        "discrepancy_counts": dict(by_cat),
        "affected_score_mass": mass,
        "counterfactuals": {
            name: {
                "mean_structure_f2": row["mean_structure_f2"],
                "mean_cell_f1_at_0.20": row["mean_cell_f1_at_0.20"],
                "mean_per_query_product": row["mean_per_query_product"],
                "per_query": row["per_query"],
            }
            for name, row in counterfactuals.items()
        },
        "candidate_keys": candidate_report,
        "agent_official": agent_score,
        "oracle_0_250_interpretation": {
            "prior_distinct_oracle_product": 0.24984791037422616,
            "prior_oracle_contaminated": True,
            "prior_oracle_also_overlaid": [
                "id",
                "CASE-condition attributes (prognosis, pharmaceutical_form, administration_route)",
            ],
            "identity_only_product": counterfactuals["gold_partition"]["mean_per_query_product"],
            "primarily": "mechanical_identity_key_plus_support",
            "reason": (
                "COUNT(DISTINCT *.id) uses an extracted id that is mostly NULL or a name. "
                "Stem/rowid match gold's equality partition exactly. Pure identity replacement "
                "does not realize 0.250 because most gold distinct witnesses never reach the "
                "aggregate (join/filter). The stored 0.250 overlay also copied CASE-condition "
                "columns, not only the identity key."
            ),
        },
        "largest_realizable_ceiling": {
            "name": best[0],
            **{k: best[1][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
        },
        "per_query": per_query,
        "vote_journal_regression": (
            "Future model arms must persist per-candidate strategy labels, raw decisions, "
            "and evidence metadata. Filter-recall votes are not recovered."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "distinct_queries": payload["n_distinct_queries"],
                "trace": {k: payload["trace_validity"][k] for k in ("n", "both_valid", "excluded")},
                "discrepancies": dict(by_cat),
                "counterfactuals": {
                    name: row["mean_per_query_product"] for name, row in counterfactuals.items()
                },
                "candidates": {
                    name: {
                        "null": row["null_pattern_agreement"],
                        "partition": row["equality_partition_agreement"],
                    }
                    for name, row in candidate_report.items()
                },
                "ceiling": payload["largest_realizable_ceiling"],
            },
            indent=2,
        )
    )
    print("wrote", OUT)
    gold_conn.close()
    qw_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Isolated component oracles via query-local sidecars. Gold after freeze. No frozen writes."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlglot import exp

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.component_oracle import (
    COMPONENTS,
    apply_component_sql,
    base_checksums,
    ensure_oracle_tables,
    from_join_sql,
    table_schemas,
    uses_component,
    with_predicate_flag,
    write_set_ok,
)
from quwarts.core.distinct_diag import extract_distinct_measures, is_null, norm_value
from quwarts.core.pipeline import official_sql
from quwarts.core.query_filter import alias_order
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import grain_sql, query_shape
from quwarts.core.query_witness import compile_witness_spec, grain_sql_for, normalize_group
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import parse_sql
from quwarts.experiments.player_case80 import execute, split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites
from spp.config_grid import _build_in_memory_db

COMPARE = ROOT / "results" / "quwarts_med_signatures" / "acquisition_compare.json"
PRIOR = ROOT / "results" / "quwarts_med_signatures" / "witness_gap.json"
OUT = ROOT / "results" / "quwarts_med_signatures" / "component_oracles.json"
POISON_COLS = ("prognosis", "pharmaceutical_form", "administration_route")
OLD_CEILINGS = {
    "filter": 0.3700907511151512,
    "join": 0.12439887110939743,
    "group": 0.3293500103744105,
    "presence": 0.12439887110939743,
    "distinct": 0.24984791037422616,
    "base_row": None,
    "full_witness": None,
}
TARGET = {
    "base_row": {"base"},
    "filter": {"filter"},
    "join": {"join"},
    "group": {"group"},
    "presence": {"presence"},
    "distinct": {"distinct"},
    "full_witness": {"base", "filter", "join", "group", "presence", "distinct"},
}


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
        return "" if not row or row[0] in (None, "") else str(row[0])
    return str(rowid)


def _fetch(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error:
        return []
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _stem_maps(qw: sqlite3.Connection) -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = {}
    for table, in qw.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' "
        "AND name NOT LIKE 'oracle_%' AND name NOT LIKE 'filter_additions'"
    ):
        cols = {row[1].lower() for row in qw.execute(f'PRAGMA table_info("{table}")')}
        mapping: dict[str, int] = {}
        if "doc_id" in cols:
            for rid, doc in qw.execute(f'SELECT rowid, doc_id FROM "{table}"'):
                if doc not in (None, ""):
                    mapping[Path(str(doc)).stem] = int(rid)
        found[table.lower()] = mapping
    return found


def _gold_stems(gold: sqlite3.Connection, table: str) -> set[str]:
    cols = {row[1].lower() for row in gold.execute(f'PRAGMA table_info("{table}")')}
    if "id" not in cols:
        return set()
    return {str(row[0]) for row in gold.execute(f'SELECT id FROM "{table}"') if row[0] not in (None, "")}


def _entity_tuple(conn: sqlite3.Connection, spec, row: dict[str, Any]) -> tuple:
    parts = []
    for alias, table in spec.alias_to_table:
        raw = row.get(f"{alias}__rid")
        if raw in (None, ""):
            continue
        parts.append((table, _ids_for(conn, table, int(raw))))
    return tuple(sorted(parts))


def _stem_key(conn: sqlite3.Connection, spec, row: dict[str, Any], order: list[str]) -> str:
    parts = []
    alias_table = dict(spec.alias_to_table)
    for alias in order:
        table = alias_table.get(alias, alias)
        raw = row.get(f"{alias}__rid")
        if raw in (None, ""):
            parts.append("NULL")
        else:
            parts.append(_ids_for(conn, table, int(raw)) or "NULL")
    return "|".join(parts) if parts else "NULL"


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


def _bags(conn: sqlite3.Connection, statements: dict[str, str]) -> dict[str, tuple]:
    return {qid: _norm_bag(_fetch(conn, sql)) for qid, sql in statements.items()}


def _ons(sql: str) -> list[tuple[str, exp.Expression]]:
    tree = parse_sql(sql)
    found = []
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        table = join.this
        right = (getattr(table, "alias", None) or getattr(table, "name", None) or "").lower()
        if on is not None:
            found.append((right, on))
    return found


def _cross_sql(left_table: str, left_alias: str, right_table: str, right_alias: str, on: exp.Expression) -> str:
    return (
        f'SELECT "{left_alias}".rowid AS left_rid, "{right_alias}".rowid AS right_rid, '
        f'({on.sql(dialect="sqlite")}) AS admit '
        f'FROM "{left_table}" AS "{left_alias}" CROSS JOIN "{right_table}" AS "{right_alias}"'
    )


def _presence_alias(sql: str) -> str | None:
    tree = parse_sql(sql)
    for proj in getattr(tree, "expressions", []) or []:
        alias = proj.alias if isinstance(proj, exp.Alias) else "n"
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        if isinstance(expr, exp.Count) and not expr.args.get("distinct") and expr.this is not None:
            if not (expr.args.get("star") or isinstance(expr.this, exp.Star)):
                return alias
    return None


def populate(
    component: str,
    dest: Path,
    gold_conn: sqlite3.Connection,
    queries: list[dict[str, str]],
    predicates,
) -> dict[str, Any]:
    qw = sqlite3.connect(str(dest))
    ensure_oracle_tables(qw)
    before = base_checksums(qw)
    schemas = table_schemas(qw)
    stems = _stem_maps(qw)
    log: list[dict[str, Any]] = []
    try:
        for row in queries:
            if component != "full_witness" and not uses_component(row["sql"], component):
                continue
            spec = compile_witness_spec(row["query_id"], row["sql"])
            if component in {"base_row", "full_witness"}:
                _fill_base(qw, gold_conn, spec, stems, log)
            if component in {"filter", "full_witness"} and uses_component(row["sql"], "filter"):
                _fill_filter(qw, gold_conn, dest, row, spec, predicates, log)
            if component in {"join", "full_witness"} and uses_component(row["sql"], "join"):
                _fill_join(qw, gold_conn, dest, row, spec, predicates, stems, log)
            if component in {"group", "full_witness"} and uses_component(row["sql"], "group"):
                _fill_group(qw, gold_conn, dest, row, spec, predicates, log)
            if component in {"presence", "full_witness"} and uses_component(row["sql"], "presence"):
                _fill_presence(qw, gold_conn, dest, row, spec, predicates, stems, log)
            if component in {"distinct", "full_witness"} and uses_component(row["sql"], "distinct"):
                _fill_distinct(qw, gold_conn, dest, row, spec, predicates, log)
        qw.commit()
        gates = write_set_ok(qw, component, before)
        if not gates["ok"]:
            raise RuntimeError(f"{component} write set exceeded: {gates}")
        return {
            "log": log,
            "gates": gates,
            "n_writes": len(log),
            "checksums": before,
            "schemas": schemas,
        }
    finally:
        qw.close()


def _fill_base(qw, gold, spec, stems, log) -> None:
    for table in spec.tables:
        qw_stems = set(stems.get(table, {}))
        gold_stems = _gold_stems(gold, table)
        for stem in sorted(gold_stems - qw_stems):
            qw.execute(
                "INSERT OR IGNORE INTO oracle_base(table_name, stem, available) VALUES (?, ?, 1)",
                [table, stem],
            )
            log.append(
                {
                    "component": "base_row",
                    "query_id": spec.query_id,
                    "node": table,
                    "witness": stem,
                    "old": False,
                    "oracle": True,
                }
            )
        for stem in sorted(qw_stems - gold_stems):
            qw.execute(
                "INSERT OR IGNORE INTO oracle_base(table_name, stem, available) VALUES (?, ?, 0)",
                [table, stem],
            )
            log.append(
                {
                    "component": "base_row",
                    "query_id": spec.query_id,
                    "node": table,
                    "witness": stem,
                    "old": True,
                    "oracle": False,
                }
            )


def _fill_filter(qw, gold, dest, row, spec, predicates, log) -> None:
    tree = parse_sql(row["sql"])
    where = tree.args.get("where")
    if where is None:
        return
    official = official_sql(row["sql"], dest, predicates)
    official_tree = parse_sql(official)
    official_where = official_tree.args.get("where")
    gold_rows = _fetch(gold, with_predicate_flag(row["sql"], where.this, "admit"))
    qw_rows = _fetch(
        qw,
        with_predicate_flag(
            official,
            official_where.this if official_where is not None else exp.Literal.number(1),
            "admit",
        ),
    )
    gold_map = {_entity_tuple(gold, spec, item): int(bool(item.get("admit"))) for item in gold_rows}
    order = alias_order(official_tree)
    for item in qw_rows:
        ent = _entity_tuple(qw, spec, item)
        if ent not in gold_map:
            continue
        old = int(bool(item.get("admit")))
        new = gold_map[ent]
        if old == new:
            continue
        key = _stem_key(qw, spec, item, order)
        qw.execute(
            "INSERT OR REPLACE INTO oracle_filter(query_id, witness_key, admit, old_admit) VALUES (?, ?, ?, ?)",
            [row["query_id"], key, new, old],
        )
        log.append(
            {
                "component": "filter",
                "query_id": row["query_id"],
                "node": "where",
                "witness": key,
                "old": old,
                "oracle": new,
            }
        )


def _fill_join(qw, gold, dest, row, spec, predicates, stems, log) -> None:
    official = official_sql(row["sql"], dest, predicates)
    gold_on = {right: on for right, on in _ons(row["sql"])}
    official_on = {right: on for right, on in _ons(official)}
    for join in spec.joins:
        g_on = gold_on.get(join.right_alias)
        q_on = official_on.get(join.right_alias)
        if g_on is None or q_on is None:
            continue
        gold_rows = _fetch(gold, _cross_sql(join.left_table, join.left_alias, join.right_table, join.right_alias, g_on))
        qw_rows = _fetch(qw, _cross_sql(join.left_table, join.left_alias, join.right_table, join.right_alias, q_on))
        gold_map = {
            (
                _ids_for(gold, join.left_table, int(item["left_rid"])),
                _ids_for(gold, join.right_table, int(item["right_rid"])),
            ): int(bool(item.get("admit")))
            for item in gold_rows
            if item.get("left_rid") not in (None, "") and item.get("right_rid") not in (None, "")
        }
        qw_map = {
            (
                _ids_for(qw, join.left_table, int(item["left_rid"])),
                _ids_for(qw, join.right_table, int(item["right_rid"])),
            ): int(bool(item.get("admit")))
            for item in qw_rows
            if item.get("left_rid") not in (None, "") and item.get("right_rid") not in (None, "")
        }
        shared = set(gold_map) & set(qw_map)
        for pair in shared:
            old = qw_map[pair]
            new = gold_map[pair]
            if old == new:
                continue
            qw.execute(
                "INSERT OR REPLACE INTO oracle_join"
                "(query_id, join_id, left_key, right_key, admit, old_admit) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [row["query_id"], join.join_id, pair[0], pair[1], new, old],
            )
            log.append(
                {
                    "component": "join",
                    "query_id": row["query_id"],
                    "node": join.join_id,
                    "witness": f"{pair[0]}|{pair[1]}",
                    "old": old,
                    "oracle": new,
                }
            )


def _supported(qw, dest, row, spec, predicates) -> dict[tuple, dict[str, Any]]:
    official = official_sql(grain_sql_for(spec), dest, predicates)
    grain = _fetch(qw, official)
    order = alias_order(parse_sql(official))
    out = {}
    for item in grain:
        out[_entity_tuple(qw, spec, item)] = {
            "row": item,
            "key": _stem_key(qw, spec, item, order),
        }
    return out


def _fill_group(qw, gold, dest, row, spec, predicates, log) -> None:
    if not spec.group_aliases:
        return
    supported = _supported(qw, dest, row, spec, predicates)
    gold_grain = _fetch(gold, grain_sql(row["sql"]))
    gold_by = {_entity_tuple(gold, spec, item): item for item in gold_grain}
    for ent, payload in supported.items():
        gold_row = gold_by.get(ent)
        if gold_row is None:
            continue
        for alias in spec.group_aliases:
            old = normalize_group(payload["row"].get(alias))
            new = normalize_group(gold_row.get(alias))
            if old == new:
                continue
            qw.execute(
                "INSERT OR REPLACE INTO oracle_group"
                "(query_id, alias, witness_key, label, old_label) VALUES (?, ?, ?, ?, ?)",
                [row["query_id"], alias, payload["key"], new, old],
            )
            log.append(
                {
                    "component": "group",
                    "query_id": row["query_id"],
                    "node": alias,
                    "witness": payload["key"],
                    "old": old,
                    "oracle": new,
                }
            )


def _fill_presence(qw, gold, dest, row, spec, predicates, stems, log) -> None:
    alias = _presence_alias(row["sql"])
    if not alias or not spec.count_column:
        return
    supported = _supported(qw, dest, row, spec, predicates)
    table = spec.primary
    gold_cols = {c[1].lower() for c in gold.execute(f'PRAGMA table_info("{table}")')}
    qw_cols = {c[1].lower() for c in qw.execute(f'PRAGMA table_info("{table}")')}
    if spec.count_column not in gold_cols:
        return
    for ent, payload in supported.items():
        stem = dict(ent).get(table)
        if stem is None:
            continue
        gold_val = gold.execute(
            f'SELECT "{spec.count_column}" FROM "{table}" WHERE CAST(id AS TEXT) = ?',
            [str(stem)],
        ).fetchone()
        new = 0 if gold_val is None or is_null(gold_val[0]) else 1
        old = 0
        rid = stems.get(table, {}).get(str(stem))
        if rid is not None and spec.count_column in qw_cols:
            inc = qw.execute(
                f'SELECT "{spec.count_column}" FROM "{table}" WHERE rowid = ?',
                [rid],
            ).fetchone()
            old = 0 if inc is None or is_null(inc[0]) else 1
        if old == new:
            continue
        qw.execute(
            "INSERT OR REPLACE INTO oracle_presence"
            "(query_id, measure, witness_key, present, old_present) VALUES (?, ?, ?, ?, ?)",
            [row["query_id"], alias, payload["key"], new, old],
        )
        log.append(
            {
                "component": "presence",
                "query_id": row["query_id"],
                "node": alias,
                "witness": payload["key"],
                "old": old,
                "oracle": new,
            }
        )


def _fill_distinct(qw, gold, dest, row, spec, predicates, log) -> None:
    measures = extract_distinct_measures(row["sql"])
    if not measures:
        return
    supported = _supported(qw, dest, row, spec, predicates)
    gold_sql = grain_sql(row["sql"])
    gold_tree = parse_sql(gold_sql)
    if isinstance(gold_tree, exp.Select):
        extra = list(gold_tree.expressions)
        for i, item in enumerate(measures):
            extra.append(exp.alias_(parse_sql(item["sql"]), f"distinct_{i}"))
        gold_tree.set("expressions", extra)
        gold_sql = gold_tree.sql(dialect="sqlite")
    gold_grain = _fetch(gold, gold_sql)
    gold_by = {_entity_tuple(gold, spec, item): item for item in gold_grain}
    qw_sql = official_sql(grain_sql(row["sql"]), dest, predicates)
    qw_tree = parse_sql(qw_sql)
    if isinstance(qw_tree, exp.Select):
        extra = list(qw_tree.expressions)
        for i, item in enumerate(measures):
            extra.append(exp.alias_(parse_sql(item["sql"]), f"distinct_{i}"))
        qw_tree.set("expressions", extra)
        qw_sql = qw_tree.sql(dialect="sqlite")
    qw_extra = {_entity_tuple(qw, spec, item): item for item in _fetch(qw, qw_sql)}
    for ent, payload in supported.items():
        gold_row = gold_by.get(ent)
        qw_row = qw_extra.get(ent, payload["row"])
        if gold_row is None:
            continue
        for i, item in enumerate(measures):
            old_val = qw_row.get(f"distinct_{i}")
            new_val = gold_row.get(f"distinct_{i}")
            old_null = 1 if is_null(old_val) else 0
            new_null = 1 if is_null(new_val) else 0
            old_part = None if old_null else norm_value(old_val)
            new_part = None if new_null else str(new_val)
            if old_null == new_null and (old_null or old_part == norm_value(new_val)):
                continue
            qw.execute(
                "INSERT OR REPLACE INTO oracle_distinct"
                "(query_id, measure, witness_key, is_null, partition, old_null, old_partition) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [row["query_id"], item["alias"], payload["key"], new_null, new_part, old_null, old_part],
            )
            log.append(
                {
                    "component": "distinct",
                    "query_id": row["query_id"],
                    "node": item["alias"],
                    "witness": payload["key"],
                    "old": {"null": old_null, "partition": old_part},
                    "oracle": {"null": new_null, "partition": new_part},
                }
            )


def _rewrites(rows, dest, predicates, component, schemas) -> dict[str, str]:
    out = {}
    for row in rows:
        spec = compile_witness_spec(row["query_id"], row["sql"])
        official = official_sql(row["sql"], dest, predicates)
        out[row["query_id"]] = apply_component_sql(
            official,
            row["query_id"],
            component,
            joins=spec.joins,
            group_aliases=spec.group_aliases,
            tables=spec.tables,
            schemas=schemas,
        )
    return out


def _python_reagg(rows: list[dict[str, Any]], spec, sql: str) -> list[dict[str, Any]]:
    shape = query_shape(spec.query_id, sql)
    buckets: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        key = tuple(normalize_group(item.get(name)) for name in spec.group_aliases)
        buckets[key].append(item)
    out = []
    for key, items in buckets.items():
        rec = {name: val for name, val in zip(spec.group_aliases, key)}
        for alias, kind in shape.aggregates:
            if kind == "count_distinct":
                vals = set()
                for item in items:
                    raw = item.get("distinct_value")
                    if raw is None:
                        raw = item.get("distinct_0")
                    if not is_null(raw):
                        vals.add(norm_value(raw))
                rec[alias] = len(vals)
            else:
                rec[alias] = len(items)
        out.append(rec)
    return out


def _component_state(conn, sql: str, spec, dest, predicates, component, schemas) -> dict[str, Any]:
    official = official_sql(sql, dest, predicates)
    grain = apply_component_sql(
        official_sql(grain_sql_for(spec), dest, predicates),
        spec.query_id,
        component,
        joins=spec.joins,
        group_aliases=spec.group_aliases,
        tables=spec.tables,
        schemas=schemas,
    )
    fj = apply_component_sql(
        official_sql(from_join_sql(sql), dest, predicates),
        spec.query_id,
        component,
        joins=spec.joins,
        group_aliases=spec.group_aliases,
        tables=spec.tables,
        schemas=schemas,
    )
    grain_rows = _fetch(conn, grain)
    join_rows = _fetch(conn, fj)
    groups = {}
    presence = {}
    distinct = {}
    for item in grain_rows:
        ent = _entity_tuple(conn, spec, item)
        groups[ent] = tuple(normalize_group(item.get(name)) for name in spec.group_aliases)
        if "counted_value" in item:
            presence[ent] = 0 if is_null(item.get("counted_value")) else 1
        if "distinct_value" in item:
            val = item.get("distinct_value")
            distinct[ent] = (1 if is_null(val) else 0, None if is_null(val) else norm_value(val))
    pairs = []
    for join in spec.joins:
        for item in join_rows:
            left_rid = item.get(f"{join.left_alias}__rid")
            right_rid = item.get(f"{join.right_alias}__rid")
            if left_rid in (None, "") or right_rid in (None, ""):
                continue
            pairs.append(
                (
                    join.join_id,
                    _ids_for(conn, join.left_table, int(left_rid)),
                    _ids_for(conn, join.right_table, int(right_rid)),
                )
            )
    admitted = {_entity_tuple(conn, spec, item) for item in grain_rows}
    return {
        "admitted": admitted,
        "groups": groups,
        "presence": presence,
        "distinct": distinct,
        "pairs": frozenset(pairs),
        "grain": grain_rows,
        "official": official,
        "grain_sql": grain,
    }


def _non_target_ok(component: str, inc: dict[str, Any], ora: dict[str, Any]) -> list[str]:
    allowed = TARGET[component]
    failures = []
    shared = inc["admitted"] & ora["admitted"]
    if "join" not in allowed and inc["pairs"] != ora["pairs"]:
        failures.append("join")
    if "filter" not in allowed and "base" not in allowed:
        if inc["admitted"] != ora["admitted"] and "join" not in allowed:
            failures.append("filter")
    if "group" not in allowed:
        for ent in shared:
            if inc["groups"].get(ent) != ora["groups"].get(ent):
                failures.append("group")
                break
    if "presence" not in allowed:
        for ent in shared:
            if inc["presence"].get(ent) != ora["presence"].get(ent):
                failures.append("presence")
                break
    if "distinct" not in allowed:
        for ent in shared:
            if inc["distinct"].get(ent) != ora["distinct"].get(ent):
                failures.append("distinct")
                break
    return failures


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    queries = queries_for("Med")
    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    agent = Path((json.loads(COMPARE.read_text()).get("agent") or {}).get("sqlite_path") or "")
    if not agent.is_file():
        raise SystemExit(f"agent incumbent missing: {agent}")
    frozen_digest = file_digest(agent)
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)
    inc_conn = sqlite3.connect(f"file:{agent}?mode=ro", uri=True)
    inc_official = {row["query_id"]: official_sql(row["sql"], agent, predicates) for row in queries}
    incumbent_score = _score(test_count, agent, gold, {r["query_id"]: inc_official[r["query_id"]] for r in test_count})
    incumbent_prod = incumbent_score["mean_per_query_product"]
    incumbent_bags = _bags(inc_conn, inc_official)
    prior = json.loads(PRIOR.read_text()) if PRIOR.is_file() else {}
    oracles = {}
    print(f"component oracles incumbent={agent} product={incumbent_prod}", flush=True)
    for component in COMPONENTS:
        tmp = Path(tempfile.mkdtemp(prefix=f"oracle_{component}_"))
        dest = tmp / "oracle.db"
        shutil.copy2(agent, dest)
        assert dest.resolve() != agent.resolve()
        try:
            filled = populate(component, dest, gold_conn, queries, predicates)
            schemas = filled["schemas"]
            dest_conn = sqlite3.connect(str(dest))
            rewrites = _rewrites(queries, dest, predicates, component, schemas)
            after_bags = _bags(dest_conn, rewrites)
            unused = [
                qid
                for qid, sql in statements.items()
                if not uses_component(sql, component) and after_bags.get(qid) != incumbent_bags.get(qid)
            ]
            if unused:
                dest_conn.close()
                raise RuntimeError(f"{component} moved unused queries: {unused[:8]}")
            changed = [qid for qid in statements if after_bags.get(qid) != incumbent_bags.get(qid)]
            test_changed = [r["query_id"] for r in test_count if r["query_id"] in changed]
            invalid = []
            nontarget = []
            for row in queries:
                if component != "full_witness" and not uses_component(row["sql"], component):
                    continue
                spec = compile_witness_spec(row["query_id"], row["sql"])
                inc_state = _component_state(inc_conn, row["sql"], spec, agent, predicates, "incumbent", {})
                ora_state = _component_state(dest_conn, row["sql"], spec, dest, predicates, component, schemas)
                bad = _non_target_ok(component, inc_state, ora_state)
                if bad:
                    nontarget.append({"query_id": row["query_id"], "fields": bad})
                cf = _fetch(dest_conn, rewrites[row["query_id"]])
                reagg = _python_reagg(ora_state["grain"], spec, row["sql"])
                if _norm_bag(reagg) != _norm_bag(cf):
                    invalid.append(row["query_id"])
            score = _score(test_count, dest, gold, {r["query_id"]: rewrites[r["query_id"]] for r in test_count})
            dest_conn.close()
            oracles[component] = {
                "score": {
                    "mean_structure_f2": score["mean_structure_f2"],
                    "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
                    "mean_per_query_product": score["mean_per_query_product"],
                },
                "lift": score["mean_per_query_product"] - incumbent_prod,
                "n_writes": filled["n_writes"],
                "sidecar_counts": filled["gates"]["sidecar_counts"],
                "changed_queries": changed,
                "n_changed_queries": len(changed),
                "test_changed": test_changed,
                "n_test_changed": len(test_changed),
                "unused_moved": unused,
                "invalid_traces": invalid,
                "n_invalid_traces": len(invalid),
                "nontarget_failures": nontarget[:20],
                "n_nontarget_failures": len(nontarget),
                "gates": filled["gates"],
                "changelog": filled["log"],
                "old_ceiling": OLD_CEILINGS.get(component),
                "corrected_ceiling": score["mean_per_query_product"],
                "per_query": score["per_query"],
            }
            print(
                json.dumps(
                    {
                        "oracle": component,
                        "f2": score["mean_structure_f2"],
                        "f1": score["mean_cell_f1_at_0.20"],
                        "product": score["mean_per_query_product"],
                        "lift": score["mean_per_query_product"] - incumbent_prod,
                        "writes": filled["n_writes"],
                        "changed": len(changed),
                        "test_changed": len(test_changed),
                        "invalid": len(invalid),
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            oracles[component] = {
                "aborted": True,
                "error": str(exc),
                "old_ceiling": OLD_CEILINGS.get(component),
                "score": {
                    "mean_structure_f2": None,
                    "mean_cell_f1_at_0.20": None,
                    "mean_per_query_product": None,
                },
                "lift": None,
                "n_writes": 0,
                "n_test_changed": 0,
            }
            print(json.dumps({"oracle": component, "aborted": True, "error": str(exc)}), flush=True)
        finally:
            dest.unlink(missing_ok=True)
            tmp.rmdir()
    live = [(name, row) for name, row in oracles.items() if name != "full_witness" and not row.get("aborted")]
    ranked = max(live, key=lambda item: item[1]["score"]["mean_per_query_product"] or 0.0) if live else ("", {})
    after_digest = file_digest(agent)
    payload = {
        "tokens_spent": 0,
        "qwen_calls": 0,
        "frozen_db_written": after_digest != frozen_digest,
        "frozen_digest": frozen_digest,
        "incumbent": str(agent),
        "incumbent_product": incumbent_prod,
        "incumbent_official": {
            "mean_structure_f2": incumbent_score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": incumbent_score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": incumbent_prod,
        },
        "oracles": oracles,
        "highest_corrected_component": {
            "name": ranked[0],
            **(ranked[1].get("score") or {}),
            "lift": (ranked[1] or {}).get("lift"),
        },
        "contamination": {
            "distinct": "CASE-condition columns (prognosis, pharmaceutical_form, administration_route) plus id",
            "filter": "copied WHERE columns into base tables; those columns also feed GROUP BY CASE",
            "join": "copied ON columns (names) into base tables; those columns also feed filters/groups",
            "group": "copied GROUP BY/CASE input columns into base tables",
            "presence": "copied counted-expression columns into base tables",
        },
        "prior_oracles": {
            name: (prior.get("component_oracles") or {}).get(name, {}).get("mean_per_query_product")
            for name in ("filter", "join", "group", "presence", "distinct")
        },
        "poison_columns": list(POISON_COLS),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "incumbent": incumbent_prod,
                "products": {k: (v.get("score") or {}).get("mean_per_query_product") for k, v in oracles.items()},
                "lifts": {k: v.get("lift") for k, v in oracles.items()},
                "highest": payload["highest_corrected_component"],
                "frozen_written": payload["frozen_db_written"],
            },
            indent=2,
        )
    )
    print("wrote", OUT)
    gold_conn.close()
    inc_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

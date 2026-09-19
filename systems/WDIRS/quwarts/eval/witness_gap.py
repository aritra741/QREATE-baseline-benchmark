"""Zero-token witness-gap diagnostic. Gold is read only here. No LLM, no frozen-DB writes."""

from __future__ import annotations

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

from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import QueryShape, SupportRow, query_shape
from quwarts.core.query_witness import (
    compile_witness_spec,
    grain_sql_for,
    normalize_group,
    support_from_grain,
)
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import parse_sql
from quwarts.experiments.player_case80 import execute, score_split, split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites
from spp.aggregation_metrics import (
    MetricConfig,
    evaluate_aggregation_tables,
    gold_table_from_sql,
    json_ready_metrics,
    predicted_table_from_rows,
    schema_from_sql,
)
from spp.config_grid import _build_in_memory_db

COMPARE = ROOT / "results" / "quwarts_med_signatures" / "acquisition_compare.json"
DOCETL_DIR = ROOT / "results" / "docetl_med_case80"
DOCETL_EVAL = DOCETL_DIR / "evaluation.json"
OUT = ROOT / "results" / "quwarts_med_signatures" / "witness_gap.json"

COMPONENTS = (
    "base_row",
    "filter",
    "join_edge",
    "group",
    "presence",
    "distinct",
)
ORACLES = ("filter", "join", "group", "presence", "distinct")


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(k), json.dumps(row.get(k), default=str)) for k in row)))
    return tuple(sorted(frozen))


def _count_mass(rows: list[dict[str, Any]]) -> int:
    total = 0
    for row in rows:
        for key, value in row.items():
            if str(key).lower().endswith("count") and value not in (None, ""):
                try:
                    total += int(value)
                except (TypeError, ValueError):
                    continue
    return total


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


def _identity(spec, row: SupportRow, conn: sqlite3.Connection) -> tuple:
    parts = []
    for table, rid in sorted((row.rowids or {spec.primary: row.rowid}).items()):
        parts.append((table, _ids_for(conn, table, int(rid))))
    groups = tuple(normalize_group(row.group_key.get(name)) for name in spec.group_aliases)
    distinct = normalize_group(row.distinct_value) if spec.distinct_sql else ""
    return (tuple(parts), groups, distinct)


def _cols(expr: exp.Expression | None) -> list[tuple[str, str]]:
    if expr is None:
        return []
    found = []
    for col in expr.find_all(exp.Column):
        table = (col.table or "").lower()
        name = (col.name or "").lower()
        if name and not name.startswith("sig_"):
            found.append((table, name))
    return list(dict.fromkeys(found))


def component_columns(sql: str, spec, kind: str) -> list[tuple[str, str]]:
    tree = parse_sql(sql)
    aliases = {(table.alias or table.name or "").lower(): (table.name or "").lower() for table in tree.find_all(exp.Table)}
    raw: list[tuple[str, str]] = []
    if kind == "filter":
        raw = _cols(tree.args.get("where"))
    elif kind == "join":
        for join in tree.find_all(exp.Join):
            raw.extend(_cols(join.args.get("on")))
    elif kind == "group":
        group = tree.args.get("group")
        if group is not None:
            for item in group.expressions:
                raw.extend(_cols(item))
        for expr in spec.group_sql:
            try:
                raw.extend(_cols(parse_sql(expr)))
            except Exception:
                continue
    elif kind == "presence" and spec.count_column:
        raw = [("", spec.count_column)]
    elif kind == "distinct" and spec.distinct_sql:
        try:
            raw = _cols(parse_sql(spec.distinct_sql))
        except Exception:
            raw = []
    out = []
    for table, name in raw:
        if name in {"rowid"}:
            continue
        resolved = aliases.get(table, table)
        out.append((resolved, name))
    return list(dict.fromkeys(out))


def fetch_grain(conn: sqlite3.Connection, sql: str, spec) -> list[SupportRow]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error:
        return []
    cols = [item[0] for item in cur.description] if cur.description else []
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return support_from_grain(spec, rows, None)


def reaggregate_sql(sql: str, spec) -> str:
    grain = parse_sql(grain_sql_for(spec))
    orig = parse_sql(sql)
    if not isinstance(grain, exp.Select) or not isinstance(orig, exp.Select):
        return grain_sql_for(spec)
    measures: list[str] = []
    for proj in orig.expressions:
        alias = proj.alias if isinstance(proj, exp.Alias) else None
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        agg = expr if isinstance(expr, (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)) else expr.find(
            (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)
        )
        if agg is None:
            continue
        inner = agg.this
        if isinstance(agg, exp.Count) and (
            inner is None or isinstance(inner, exp.Star) or agg.args.get("star")
        ):
            measures.append(f'COUNT(*) AS "{alias or "n"}"')
        elif isinstance(agg, exp.Count) and (agg.args.get("distinct") or isinstance(inner, exp.Distinct)):
            measures.append(f'COUNT(DISTINCT distinct_value) AS "{alias or "n"}"')
        else:
            name = f"m_{alias or 'x'}"
            payload = inner.copy() if inner is not None else expr.copy()
            grain.set("expressions", list(grain.expressions) + [exp.alias_(payload, name)])
            op = "SUM" if isinstance(agg, exp.Sum) else "COUNT"
            measures.append(f'{op}("{name}") AS "{alias or name}"')
    groups = [f'"{name}"' for name in spec.group_aliases]
    select = ", ".join(groups + measures) if groups or measures else "COUNT(*) AS n"
    body = f"SELECT {select} FROM ({grain.sql(dialect='sqlite')})"
    if groups:
        body += " GROUP BY " + ", ".join(groups)
    return body


def official_bag(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        return execute(conn, sql)
    except Exception:
        return []


def score_bags(test, gold, pred_by_qid: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    gold_conn = _build_in_memory_db(gold)
    config = MetricConfig()
    per_query = []
    for row in test:
        sql = row["sql"]
        gold_rows = execute(gold_conn, sql)
        pred_rows = pred_by_qid.get(row["query_id"]) or []
        item = {
            "query_id": row["query_id"],
            "gold_rows": len(gold_rows),
            "pred_rows": len(pred_rows),
            "gold_n": _count_mass(gold_rows),
            "pred_n": _count_mass(pred_rows),
        }
        schema = schema_from_sql(sql)
        if schema.get("is_aggregation"):
            try:
                gold_table = gold_table_from_sql(gold_rows, sql)
                pred = predicted_table_from_rows(pred_rows, gold=gold_table)
                metrics = json_ready_metrics(evaluate_aggregation_tables(pred, gold_table, config=config))
                s = float(metrics["rank"]["structure_fbeta_score"])
                cell_map = metrics["rank"]["cell_f1"]
                cell20 = next((float(v) for k, v in cell_map.items() if abs(float(k) - 0.20) < 1e-9), 0.0)
                item["structure_f2"] = s
                item["cell_f1_20"] = cell20
                item["product"] = s * cell20
            except Exception as exc:
                item["metric_error"] = str(exc)
                item["structure_f2"] = 0.0
                item["cell_f1_20"] = 0.0
                item["product"] = 0.0
        else:
            item["structure_f2"] = 0.0
            item["cell_f1_20"] = 0.0
            item["product"] = 0.0
        item["count_error"] = item["pred_n"] - item["gold_n"]
        per_query.append(item)
    gold_conn.close()
    n = len(per_query) or 1
    return {
        "mean_structure_f2": sum(r["structure_f2"] for r in per_query) / n,
        "mean_cell_f1_at_0.20": sum(r["cell_f1_20"] for r in per_query) / n,
        "mean_per_query_product": sum(r["product"] for r in per_query) / n,
        "per_query": per_query,
    }


def overlay(dest: Path, gold_conn: sqlite3.Connection, columns: list[tuple[str, str]]) -> int:
    conn = sqlite3.connect(str(dest))
    changed = 0
    by_table: dict[str, list[str]] = defaultdict(list)
    for table, column in columns:
        if table:
            by_table[table].append(column)
    try:
        have = {row[0].lower(): row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, cols in by_table.items():
            real = have.get(table)
            if real is None:
                continue
            qw_cols = {row[1].lower() for row in conn.execute(f'PRAGMA table_info("{real}")')}
            gold_cols = {row[1].lower() for row in gold_conn.execute(f'PRAGMA table_info("{table}")')}
            use = [col for col in dict.fromkeys(cols) if col in qw_cols and col in gold_cols]
            if not use or "id" not in qw_cols or "id" not in gold_cols:
                continue
            gold_rows = gold_conn.execute(
                f'SELECT id, {", ".join(f"{c}" for c in use)} FROM "{table}"'
            ).fetchall()
            stems = {}
            if "doc_id" in qw_cols:
                for rid, doc in conn.execute(f'SELECT rowid, doc_id FROM "{real}"'):
                    if doc not in (None, ""):
                        stems[Path(str(doc)).stem] = int(rid)
            assignments = ", ".join(f'"{c}" = ?' for c in use)
            for row in gold_rows:
                rid = stems.get(str(row[0]))
                if rid is None:
                    continue
                conn.execute(
                    f'UPDATE "{real}" SET {assignments} WHERE rowid = ?',
                    list(row[1:]) + [rid],
                )
                changed += 1
        conn.commit()
    finally:
        conn.close()
    return changed


def _rid_clause(tree: exp.Expression, qw_rids: dict[str, int]) -> str:
    parts = []
    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        alias = (table.alias or table.name or "").lower()
        if name in qw_rids:
            parts.append(f'"{alias}".rowid = {qw_rids[name]}')
    return " AND ".join(parts)


def _probe(conn: sqlite3.Connection, sql: str, extra_where: str) -> bool:
    try:
        tree = parse_sql(sql)
        tree.set("expressions", [exp.Literal.number(1)])
        tree.set("group", None)
        tree.set("order", None)
        tree.set("having", None)
        if extra_where:
            extra = parse_sql(extra_where)
            if tree.args.get("where") is not None:
                tree.set("where", exp.Where(this=exp.and_(tree.args["where"].this, extra)))
            else:
                tree.set("where", exp.Where(this=extra))
        return conn.execute(tree.sql(dialect="sqlite")).fetchone() is not None
    except sqlite3.Error:
        return False


def earliest_failure(spec, gold_row: SupportRow, qw_conn, qw_path, predicates, gold_conn, sql: str) -> str:
    gold_ids = {}
    for table, rid in (gold_row.rowids or {spec.primary: gold_row.rowid}).items():
        gold_ids[table] = _ids_for(gold_conn, table, int(rid))
    qw_rids = {}
    for table, ident in gold_ids.items():
        if not ident:
            return "base_row"
        hit = qw_conn.execute(f'SELECT rowid, doc_id FROM "{table}"').fetchall()
        rid = None
        for raw_rid, doc in hit:
            if doc and Path(str(doc)).stem == str(ident):
                rid = int(raw_rid)
                break
        if rid is None:
            return "base_row"
        qw_rids[table] = rid
    official = official_sql(sql, qw_path, predicates)
    try:
        tree = parse_sql(official)
    except Exception:
        return "filter"
    rid_sql = _rid_clause(tree, qw_rids)
    if spec.joins:
        if not _probe(qw_conn, official, rid_sql):
            return _filter_or_join(qw_conn, official, spec, qw_rids)
    elif not _probe(qw_conn, official, rid_sql):
        return "filter"
    if spec.group_aliases:
        gold_g = tuple(normalize_group(gold_row.group_key.get(name)) for name in spec.group_aliases)
        qw_rows = fetch_grain(qw_conn, official_sql(grain_sql_for(spec), qw_path, predicates), spec)
        match = [
            row
            for row in qw_rows
            if {t: _ids_for(qw_conn, t, int(r)) for t, r in (row.rowids or {}).items()} == gold_ids
        ]
        if not match:
            return "group"
        qw_g = tuple(normalize_group(match[0].group_key.get(name)) for name in spec.group_aliases)
        if qw_g != gold_g:
            return "group"
    if "counted_value" in spec.kinds and spec.count_column:
        val = qw_conn.execute(
            f'SELECT "{spec.count_column}" FROM "{spec.primary}" WHERE rowid = ?',
            [qw_rids.get(spec.primary, 0)],
        ).fetchone()
        if val is None or val[0] in (None, ""):
            return "presence"
    if spec.distinct_sql:
        gold_d = normalize_group(gold_row.distinct_value)
        qw_rows = fetch_grain(qw_conn, official_sql(grain_sql_for(spec), qw_path, predicates), spec)
        match = [
            row
            for row in qw_rows
            if {t: _ids_for(qw_conn, t, int(r)) for t, r in (row.rowids or {}).items()} == gold_ids
        ]
        if not match or normalize_group(match[0].distinct_value) != gold_d:
            return "distinct"
    return "filter"


def _filter_or_join(qw_conn, official: str, spec, qw_rids: dict[str, int], rid_sql: str = "") -> str:
    try:
        tree = parse_sql(official)
        # drop joins; keep primary
        primary_alias = spec.primary_alias
        where = tree.args.get("where")
        sql = f'SELECT 1 FROM "{spec.primary}" AS "{primary_alias}"'
        if where is not None:
            sql += " WHERE " + where.this.sql(dialect="sqlite")
        sql += (" AND " if where is not None else " WHERE ") + f'"{primary_alias}".rowid = {qw_rids[spec.primary]}'
        if qw_conn.execute(sql).fetchone() is None:
            return "filter"
    except sqlite3.Error:
        return "filter"
    return "join_edge"


def mean_report(report: dict[str, Any]) -> dict[str, float]:
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report) if "per_query" in report else float(report.get("mean_cell_f1_at_0.20") or 0.0),
        "mean_per_query_product": (
            mean_per_query_product(report)
            if report.get("per_query") and "cell_f1_20" in (report["per_query"][0] or {})
            else float(report.get("mean_per_query_product") or 0.0)
        ),
    }


def main() -> int:
    queries = queries_for("Med")
    _, test = split_80_20(queries, 42)
    test = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    statements = {row["query_id"]: row["sql"] for row in test}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    agent = Path((json.loads(COMPARE.read_text()).get("agent") or {}).get("sqlite_path") or "")
    if not agent.is_file():
        raise SystemExit(f"incumbent missing: {agent}")
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)
    qw_conn = sqlite3.connect(str(agent))
    qw_official = {row["query_id"]: official_sql(row["sql"], agent, predicates) for row in test}
    qw_score = score_with_rewrites(test, qw_official, agent, gold, "Med")
    docetl_bags = {}
    for row in test:
        path = DOCETL_DIR / "query_tables" / f"{row['query_id']}.json"
        docetl_bags[row["query_id"]] = json.loads(path.read_text()) if path.is_file() else []
    docetl_score = score_bags(test, gold, docetl_bags)
    stored_docetl = json.loads(DOCETL_EVAL.read_text()) if DOCETL_EVAL.is_file() else {}

    per_query = []
    gap_components: Counter[str] = Counter()
    traces = []
    for row in test:
        qid = row["query_id"]
        sql = row["sql"]
        shape = query_shape(qid, sql)
        spec = compile_witness_spec(qid, sql, shape)
        gold_grain = fetch_grain(gold_conn, grain_sql_for(spec), spec)
        qw_grain = fetch_grain(qw_conn, official_sql(grain_sql_for(spec), agent, predicates), spec)
        gold_bag = official_bag(gold_conn, sql)
        qw_bag = official_bag(qw_conn, qw_official[qid])
        try:
            gold_re = official_bag(gold_conn, reaggregate_sql(sql, spec))
        except Exception:
            gold_re = []
        try:
            qw_re = official_bag(qw_conn, official_sql(reaggregate_sql(sql, spec), agent, predicates))
        except Exception:
            qw_re = []
        gold_valid = _norm_bag(gold_re) == _norm_bag(gold_bag)
        qw_valid = _norm_bag(qw_re) == _norm_bag(qw_bag)
        traces.append({"query_id": qid, "gold_valid": gold_valid, "quwarts_valid": qw_valid, "kind": spec.kind})
        gold_ids = {_identity(spec, item, gold_conn) for item in gold_grain}
        qw_ids = {_identity(spec, item, qw_conn) for item in qw_grain}
        tp = gold_ids & qw_ids
        fp = qw_ids - gold_ids
        fn = gold_ids - qw_ids
        reasons = Counter()
        if gold_valid and qw_valid:
            gold_by_id = {_identity(spec, item, gold_conn): item for item in gold_grain}
            for key in fn:
                reason = earliest_failure(spec, gold_by_id[key], qw_conn, agent, predicates, gold_conn, sql)
                reasons[reason] += 1
                gap_components[reason] += 1
        else:
            reasons["invalid_trace"] += len(fn)
        qw_item = next(r for r in qw_score["per_query"] if r["query_id"] == qid)
        de_item = next(r for r in docetl_score["per_query"] if r["query_id"] == qid)
        stored = (stored_docetl.get("per_query") or {}).get(qid) or {}
        qw_prod = float(qw_item.get("structure_f2") or 0.0) * float(qw_item.get("cell_f1_20") or 0.0)
        de_prod = float(de_item.get("product") or 0.0)
        per_query.append(
            {
                "query_id": qid,
                "kind": spec.kind,
                "gold_valid": gold_valid,
                "quwarts_valid": qw_valid,
                "docetl_witness_provenance": "unavailable",
                "gold_n": _count_mass(gold_bag),
                "quwarts_n": _count_mass(qw_bag),
                "docetl_n": de_item["pred_n"],
                "quwarts_count_error": _count_mass(qw_bag) - _count_mass(gold_bag),
                "docetl_count_error": de_item["count_error"],
                "quwarts_tp": len(tp) if gold_valid and qw_valid else None,
                "quwarts_fp": len(fp) if gold_valid and qw_valid else None,
                "quwarts_fn": len(fn) if gold_valid and qw_valid else None,
                "fn_by_component": dict(reasons),
                "quwarts_f2": qw_item.get("structure_f2"),
                "quwarts_f1_20": qw_item.get("cell_f1_20"),
                "quwarts_product": qw_prod,
                "docetl_f2": de_item.get("structure_f2"),
                "docetl_f1_20": de_item.get("cell_f1_20"),
                "docetl_product": de_prod,
                "docetl_stored_f2": (stored.get("rank") or {}).get("structure_fbeta_score"),
                "better_of_product": max(qw_prod, de_prod),
                "product_gap_vs_docetl": de_prod - qw_prod,
            }
        )

    oracle_scores = {}
    for kind in ORACLES:
        tmp = Path(tempfile.mkdtemp()) / f"oracle_{kind}.db"
        shutil.copy2(agent, tmp)
        cols = []
        for row in test:
            spec = compile_witness_spec(row["query_id"], row["sql"])
            cols.extend(component_columns(row["sql"], spec, kind))
        overlay(tmp, gold_conn, cols)
        rewrites = {row["query_id"]: official_sql(row["sql"], tmp, predicates) for row in test}
        report = score_with_rewrites(test, rewrites, tmp, gold, "Med")
        oracle_scores[kind] = {
            "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
            "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
            "mean_per_query_product": mean_per_query_product(report),
            "per_query": [
                {
                    "query_id": item["query_id"],
                    "product": float(item.get("structure_f2") or 0.0) * float(item.get("cell_f1_20") or 0.0),
                    "structure_f2": item.get("structure_f2"),
                    "cell_f1_20": item.get("cell_f1_20"),
                }
                for item in report.get("per_query") or []
            ],
        }
        tmp.unlink()
        tmp.parent.rmdir()

    qw_prod = mean_per_query_product(qw_score)
    de_prod = docetl_score["mean_per_query_product"]
    better = sum(item["better_of_product"] for item in per_query) / len(per_query)
    ranked_gap = sorted(per_query, key=lambda item: (-(item["product_gap_vs_docetl"] or 0), -abs(item["quwarts_count_error"])))
    ceiling = max(oracle_scores.items(), key=lambda item: item[1]["mean_per_query_product"])
    payload = {
        "incumbent": "agent",
        "incumbent_product": qw_prod,
        "docetl_product": de_prod,
        "better_of_product": better,
        "docetl_witness_provenance": "unavailable",
        "trace_validity": {
            "gold_valid": sum(1 for t in traces if t["gold_valid"]),
            "quwarts_valid": sum(1 for t in traces if t["quwarts_valid"]),
            "both_valid": sum(1 for t in traces if t["gold_valid"] and t["quwarts_valid"]),
            "n": len(traces),
            "per_query": traces,
        },
        "quwarts": {
            "mean_structure_f2": float(qw_score.get("mean_structure_f2") or 0.0),
            "mean_cell_f1_at_0.20": mean_cell_f1_20(qw_score),
            "mean_per_query_product": qw_prod,
        },
        "docetl": docetl_score,
        "gap_mass_by_component": dict(gap_components),
        "component_oracles": oracle_scores,
        "highest_ceiling_component": {"name": ceiling[0], **ceiling[1]},
        "top_gap_queries": [
            {
                "query_id": item["query_id"],
                "product_gap_vs_docetl": item["product_gap_vs_docetl"],
                "quwarts_product": item["quwarts_product"],
                "docetl_product": item["docetl_product"],
                "quwarts_count_error": item["quwarts_count_error"],
                "fn_by_component": item["fn_by_component"],
            }
            for item in ranked_gap[:10]
        ],
        "per_query": per_query,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "trace": payload["trace_validity"],
                "quwarts": payload["quwarts"],
                "docetl_product": de_prod,
                "better_of": better,
                "gap_mass": dict(gap_components),
                "oracles": {k: v["mean_per_query_product"] for k, v in oracle_scores.items()},
                "highest_ceiling": ceiling[0],
                "top_gap": [item["query_id"] for item in ranked_gap[:10]],
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

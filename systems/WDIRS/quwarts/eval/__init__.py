"""Firewalled evaluation. The only module allowed to read ``data/gold/``."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from quwarts.core.models import FrozenPortfolio


def load_gold(root: Path) -> dict[str, list[dict[str, Any]]]:
    root = Path(root)
    tables: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(root.glob("*")):
        if path.suffix == ".json":
            tables[path.stem] = json.loads(path.read_text())
        elif path.suffix == ".csv":
            with path.open(newline="") as handle:
                tables[path.stem] = list(csv.DictReader(handle))
    return tables


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def align_rows(
    gold: list[dict[str, Any]],
    pred: list[dict[str, Any]],
    key_fields: list[str],
) -> list[tuple[dict[str, Any] | None, dict[str, Any] | None]]:
    gold_groups: dict[str, list[dict[str, Any]]] = {}
    pred_groups: dict[str, list[dict[str, Any]]] = {}
    for row in gold:
        gold_groups.setdefault(_key(row, key_fields), []).append(row)
    for row in pred:
        pred_groups.setdefault(_key(row, key_fields), []).append(row)
    pairs: list[tuple[dict[str, Any] | None, dict[str, Any] | None]] = []
    for key in sorted(set(gold_groups) | set(pred_groups)):
        left = gold_groups.get(key, [])
        right = pred_groups.get(key, [])
        n = min(len(left), len(right))
        for index in range(n):
            pairs.append((left[index], right[index]))
        for index in range(n, len(left)):
            pairs.append((left[index], None))
        for index in range(n, len(right)):
            pairs.append((None, right[index]))
    return pairs


def _key(row: dict[str, Any], fields: list[str]) -> str:
    if not fields:
        return _norm(next(iter(row.values()), ""))
    return "|".join(_norm(row.get(field) or row.get(field.split(".")[-1])) for field in fields)


def cell_score(gold: Any, pred: Any, kind: str = "string") -> tuple[float, float]:
    if gold is None and pred is None:
        return 1.0, 1.0
    if gold is None or pred is None:
        return 0.0, 0.0
    if kind == "numeric":
        try:
            g = float(str(gold).replace(",", "").replace("$", ""))
            p = float(str(pred).replace(",", "").replace("$", ""))
        except ValueError:
            return 0.0, 0.0
        if g == 0:
            ok = 1.0 if p == 0 else 0.0
            return ok, ok
        rel = abs(p - g) / abs(g)
        score = max(0.0, 1.0 - rel)
        return score, score
    if kind == "multivalued":
        gset = {part.strip().lower() for part in str(gold).split(",") if part.strip()}
        pset = {part.strip().lower() for part in str(pred).split(",") if part.strip()}
        if not gset and not pset:
            return 1.0, 1.0
        inter = len(gset & pset)
        p = inter / max(len(pset), 1)
        r = inter / max(len(gset), 1)
        return p, r
    ok = 1.0 if _norm(gold) == _norm(pred) else 0.0
    return ok, ok


def column_scores(
    pairs: list[tuple[dict[str, Any] | None, dict[str, Any] | None]],
    columns: list[str],
    kinds: dict[str, str] | None = None,
) -> dict[str, tuple[float, float]]:
    kinds = kinds or {}
    n_gold = sum(1 for gold, _ in pairs if gold is not None)
    n_pred = sum(1 for _, pred in pairs if pred is not None)
    out: dict[str, tuple[float, float]] = {}
    for column in columns:
        p_sum = 0.0
        r_sum = 0.0
        kind = kinds.get(column, "string")
        for gold, pred in pairs:
            g = None if gold is None else gold.get(column) or gold.get(column.split(".")[-1])
            p = None if pred is None else pred.get(column) or pred.get(column.split(".")[-1])
            if gold is None and pred is None:
                continue
            cp, cr = cell_score(g, p, kind)
            p_sum += cp
            r_sum += cr
        precision = p_sum / max(n_pred, 1)
        recall = r_sum / max(n_gold, 1)
        out[column] = (precision, recall)
    return out


def f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def error(
    gold: list[dict[str, Any]],
    pred: list[dict[str, Any]],
    key_fields: list[str],
    columns: list[str],
    kinds: dict[str, str] | None = None,
) -> float:
    pairs = align_rows(gold, pred, key_fields)
    scores = column_scores(pairs, columns, kinds)
    if not scores:
        return 1.0
    values = [f1(p, r) for p, r in scores.values()]
    return 1.0 - (sum(values) / len(values))


def execute_sql(sqlite_path: str, sql: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(sqlite_path)
    try:
        cur = conn.execute(sql)
        cols = [item[0] for item in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def evaluate_portfolio(
    portfolio: FrozenPortfolio,
    gold_by_query: dict[str, list[dict[str, Any]]],
    key_fields: list[str],
    columns: list[str],
    kinds: dict[str, str] | None = None,
) -> dict[str, Any]:
    db_by_config = {db.config_id: db for db in portfolio.databases}
    per_query = {}
    errors = []
    for query_id, gold in gold_by_query.items():
        config_id = portfolio.route.get(query_id)
        sql = portfolio.rewrites.get(query_id)
        if config_id is None or sql is None or config_id not in db_by_config:
            per_query[query_id] = {"error": 1.0, "reason": "unrouted"}
            errors.append(1.0)
            continue
        pred = execute_sql(db_by_config[config_id].sqlite_path, sql)
        value = error(gold, pred, key_fields, columns, kinds)
        per_query[query_id] = {"error": value, "rows": len(pred)}
        errors.append(value)
    return {
        "sum_error": sum(errors),
        "mean_error": sum(errors) / max(len(errors), 1),
        "per_query": per_query,
        "tokens_spent": portfolio.tokens_spent,
        "cache_hit_rate": portfolio.cache_hit_rate,
    }


def routing_gap(
    oracle_errors: dict[str, float],
    realized_errors: dict[str, float],
) -> float:
    if not realized_errors:
        return 0.0
    return sum(realized_errors[key] - oracle_errors.get(key, realized_errors[key]) for key in realized_errors) / len(
        realized_errors
    )

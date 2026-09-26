"""Need-aware cell comparison consistent with ``evaluation/comparators.py``.

With the evaluation LLM disabled (its default), the benchmark scores:
multi-valued cells by lexical set F1 over ``||``-separated parts, numbers by
exact equality, strings by case- and whitespace-insensitive equality, and two
empty cells as a match. A ``predicate`` need only cares whether its SQL
conditions evaluate the same way on both values, so it is scored on condition
truth (SQL three-valued), evaluated in SQLite.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from functools import lru_cache
from typing import Any

from quwarts.core.router.needs import Need

_NULL = {"", "null", "none", "n/a", "na", "unknown", "not found", "not_present"}
_WS = re.compile(r"\s+")
_local = threading.local()


def is_null(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return not any(not is_null(item) for item in value)
    return str(value).strip().lower() in _NULL


def as_text(value: Any) -> str:
    if isinstance(value, list):
        return " || ".join(str(item) for item in value if not is_null(item))
    return _WS.sub(" ", str(value)).strip()


def parts(value: Any) -> list[str]:
    return [part.strip().lower() for part in as_text(value).split("||") if part.strip()]


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = as_text(value).replace(",", "").replace("$", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def value_score(a: Any, b: Any, value_type: str) -> float:
    if is_null(a) and is_null(b):
        return 1.0
    if is_null(a) or is_null(b):
        return 0.0
    if value_type in ("int", "float", "number"):
        x, y = as_number(a), as_number(b)
        if x is None or y is None:
            return 1.0 if as_text(a).lower() == as_text(b).lower() else 0.0
        return 1.0 if x == y else 0.0
    if value_type.startswith("multi"):
        pa, pb = parts(a), parts(b)
        if not pa or not pb:
            return 0.0
        matched = len(set(pa) & set(pb))
        precision, recall = matched / len(pa), matched / len(pb)
        return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return 1.0 if as_text(a).lower() == as_text(b).lower() else 0.0


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(":memory:")
        _local.conn = conn
    return conn


@lru_cache(maxsize=65536)
def _truth(condition: str, attribute: str, value: Any) -> int | None:
    sql = (
        f'SELECT CASE WHEN ({condition}) THEN 1 WHEN NOT ({condition}) THEN 0 ELSE NULL END '
        f'FROM (SELECT ? AS "{attribute}")'
    )
    try:
        (result,) = _conn().execute(sql, (value,)).fetchone()
    except sqlite3.Error:
        return None
    return result


def sql_value(value: Any, value_type: str) -> Any:
    if is_null(value):
        return None
    if value_type in ("int", "float", "number"):
        number = as_number(value)
        if number is not None:
            return number
    return as_text(value)


def predicate_truths(need: Need, value: Any, value_type: str) -> tuple[int | None, ...]:
    bound = sql_value(value, value_type)
    return tuple(_truth(condition, need.attribute, bound) for condition in need.conditions)


def need_score(need: Need, a: Any, b: Any, value_type: str) -> float:
    """Expected agreement, in benchmark units, between two values for one need."""

    if need.kind == "predicate" and need.conditions:
        ta, tb = predicate_truths(need, a, value_type), predicate_truths(need, b, value_type)
        return sum(1.0 for x, y in zip(ta, tb) if x == y) / len(ta)
    return value_score(a, b, value_type)

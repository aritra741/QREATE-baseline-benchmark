"""Distinct-identity diagnostics. Equality partitions, not string equality."""

from __future__ import annotations

import re
from typing import Any

from sqlglot import exp

from quwarts.core.workload import parse_sql

SIDECAR = "__diag_distinct"
IDENTITY_NAMES = frozenset({"id"})
CATEGORIES = (
    "null_missing",
    "null_extra",
    "collision",
    "fragmentation",
    "tokenization",
    "synthetic_key",
    "support_inherited",
    "observationally_irrelevant",
)
_TOKEN_SPLIT = re.compile(r"(?:\s*\|\|\s*|\s*\|\s*|[;,/]+|\s+)")


def is_null(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def norm_value(value: Any) -> str | None:
    if is_null(value):
        return None
    return " ".join(str(value).casefold().split())


def tokens(value: Any) -> frozenset[str] | None:
    text = norm_value(value)
    if text is None:
        return None
    parts = [item for item in _TOKEN_SPLIT.split(text) if item]
    return frozenset(parts) if parts else frozenset({text})


def token_key(value: Any) -> str | None:
    parts = tokens(value)
    if parts is None:
        return None
    return "|".join(sorted(parts))


def extract_distinct_measures(sql: str) -> list[dict[str, Any]]:
    tree = parse_sql(sql)
    found: list[dict[str, Any]] = []
    if not isinstance(tree, exp.Select):
        return found
    for index, proj in enumerate(tree.expressions):
        alias = proj.alias if isinstance(proj, exp.Alias) else f"c{index}"
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        count = expr if isinstance(expr, exp.Count) else expr.find(exp.Count)
        if count is None:
            continue
        inner = count.this
        if not (count.args.get("distinct") or isinstance(inner, exp.Distinct)):
            continue
        if isinstance(inner, exp.Distinct) and inner.expressions:
            inner = inner.expressions[0]
        if isinstance(inner, exp.Tuple) and inner.expressions:
            inner = inner.expressions[0]
        found.append(
            {
                "alias": alias,
                "sql": inner.sql(dialect="sqlite") if inner is not None else "",
                "identity": _is_identity(inner),
            }
        )
    return found


def _is_identity(expr: exp.Expression | None) -> bool:
    if expr is None:
        return False
    if isinstance(expr, exp.Column):
        return (expr.name or "").lower() in IDENTITY_NAMES
    if isinstance(expr, exp.Case):
        for pair in expr.args.get("ifs") or []:
            if _is_identity(getattr(pair, "true", None) or pair.args.get("true")):
                return True
        return _is_identity(expr.args.get("default"))
    return any(
        isinstance(col, exp.Column) and (col.name or "").lower() in IDENTITY_NAMES
        for col in expr.find_all(exp.Column)
    )


def rewrite_distinct_sidecar(sql: str, sidecar: str = SIDECAR) -> str:
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql

    def replace(node: exp.Expression | None) -> exp.Expression | None:
        if node is None:
            return None
        if isinstance(node, exp.Column) and (node.name or "").lower() in IDENTITY_NAMES:
            copy = node.copy()
            copy.set("this", exp.to_identifier(sidecar))
            return copy
        return node.transform(
            lambda item: (
                exp.Column(
                    this=exp.to_identifier(sidecar),
                    table=item.args.get("table"),
                )
                if isinstance(item, exp.Column) and (item.name or "").lower() in IDENTITY_NAMES
                else item
            )
        )

    for proj in tree.expressions:
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        count = expr if isinstance(expr, exp.Count) else (expr.find(exp.Count) if expr else None)
        if count is None:
            continue
        inner = count.this
        if not (count.args.get("distinct") or isinstance(inner, exp.Distinct)):
            continue
        if isinstance(inner, exp.Distinct):
            inner.set("expressions", [replace(item) or item for item in inner.expressions])
        else:
            count.set("this", replace(inner) or inner)
    return tree.sql(dialect="sqlite")


def grain_with_measures(sql: str, measures: list[dict[str, Any]]) -> str:
    from quwarts.core.query_support import grain_sql

    tree = parse_sql(grain_sql(sql))
    if not isinstance(tree, exp.Select):
        return sql
    kept = list(tree.expressions)
    for index, item in enumerate(measures):
        kept.append(exp.alias_(parse_sql(item["sql"]), f"distinct_{index}"))
    tree.set("expressions", kept)
    return tree.sql(dialect="sqlite")


def reaggregate_sql(sql: str, measures: list[dict[str, Any]], group_aliases: tuple[str, ...]) -> str:
    grain = grain_with_measures(sql, measures)
    groups = [f'"{name}"' for name in group_aliases]
    aggs = [f'COUNT(DISTINCT distinct_{i}) AS "{item["alias"]}"' for i, item in enumerate(measures)]
    select = ", ".join(groups + aggs) if groups or aggs else "COUNT(*) AS n"
    body = f"SELECT {select} FROM ({grain})"
    if groups:
        body += " GROUP BY " + ", ".join(groups)
    return body


def same_partition(left: list[Any], right: list[Any]) -> bool:
    if len(left) != len(right):
        return False
    mapping: dict[Any, Any] = {}
    reverse: dict[Any, Any] = {}
    for a, b in zip(left, right):
        a_null, b_null = is_null(a), is_null(b)
        if a_null != b_null:
            return False
        if a_null:
            continue
        if a in mapping and mapping[a] != b:
            return False
        if b in reverse and reverse[b] != a:
            return False
        mapping[a] = b
        reverse[b] = a
    return True


def classify_pair(
    qw_a: Any,
    gold_a: Any,
    qw_b: Any,
    gold_b: Any,
    *,
    identity: bool,
    stable_a: Any | None = None,
    stable_b: Any | None = None,
) -> str | None:
    if is_null(qw_a) != is_null(gold_a) or is_null(qw_b) != is_null(gold_b):
        return None
    qw_eq = (not is_null(qw_a) and not is_null(qw_b) and norm_value(qw_a) == norm_value(qw_b))
    gold_eq = (not is_null(gold_a) and not is_null(gold_b) and norm_value(gold_a) == norm_value(gold_b))
    qw_null_both = is_null(qw_a) and is_null(qw_b)
    gold_null_both = is_null(gold_a) and is_null(gold_b)
    if qw_null_both or gold_null_both:
        return None
    if qw_eq and not gold_eq:
        return "collision"
    if (not qw_eq) and gold_eq and not is_null(qw_a) and not is_null(qw_b):
        return "fragmentation"
    tok_a, tok_b = tokens(qw_a), tokens(qw_b)
    gold_tok_a, gold_tok_b = tokens(gold_a), tokens(gold_b)
    if tok_a is not None and gold_tok_a is not None and tok_a != gold_tok_a and not identity:
        if ("|" in str(qw_a) or "||" in str(qw_a)) or tok_a != tokens(qw_a if not is_null(qw_a) else gold_a):
            return "tokenization"
    if identity and stable_a is not None and not is_null(qw_a) and norm_value(qw_a) != norm_value(stable_a):
        return "synthetic_key"
    if identity and stable_b is not None and not is_null(qw_b) and norm_value(qw_b) != norm_value(stable_b):
        return "synthetic_key"
    if qw_eq == gold_eq and norm_value(qw_a) != norm_value(gold_a):
        return "observationally_irrelevant"
    return None


def classify_witness_values(
    qw_val: Any,
    gold_val: Any,
    *,
    identity: bool,
    stable: Any | None = None,
    in_qw: bool,
    in_gold: bool,
) -> str | None:
    if in_gold and not in_qw:
        return "support_inherited"
    if not in_gold:
        return None
    if is_null(qw_val) and not is_null(gold_val):
        return "null_missing"
    if not is_null(qw_val) and is_null(gold_val):
        return "null_extra"
    if identity and not is_null(qw_val) and stable is not None and norm_value(qw_val) != norm_value(stable):
        return "synthetic_key"
    if not is_null(qw_val) and not is_null(gold_val) and norm_value(qw_val) != norm_value(gold_val):
        qw_tok, gold_tok = tokens(qw_val), tokens(gold_val)
        if qw_tok != gold_tok and ("|" in str(qw_val) or "||" in str(qw_val)):
            return "tokenization"
        return "observationally_irrelevant"
    return None

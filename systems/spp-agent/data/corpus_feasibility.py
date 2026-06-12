"""Detect aggregation queries whose WHERE literals are absent from the probe corpus."""

from __future__ import annotations

import re

_WHERE_LITERAL_RE = re.compile(r"'((?:''|[^'])*)'")
_WHERE_CLAUSE_RE = re.compile(r"\bwhere\b(.+?)(?:\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", re.IGNORECASE | re.DOTALL)


def extract_where_string_literals(sql: str) -> list[str]:
    """Return single-quoted string literals appearing in the WHERE clause."""
    match = _WHERE_CLAUSE_RE.search(sql)
    if not match:
        return []
    where_text = match.group(1)
    return [lit.replace("''", "'") for lit in _WHERE_LITERAL_RE.findall(where_text)]


def literal_in_corpus(value: str, corpus: list[dict]) -> bool:
    """Case-insensitive substring match against raw document text."""
    needle = value.strip().lower()
    if not needle:
        return True
    for doc in corpus:
        if needle in doc.get("text", "").lower():
            return True
    return False


def missing_corpus_literals(sql: str, corpus: list[dict]) -> list[str]:
    """String literals from WHERE that do not appear in any corpus document."""
    missing: list[str] = []
    for literal in extract_where_string_literals(sql):
        if not literal_in_corpus(literal, corpus):
            missing.append(literal)
    return missing


def is_corpus_infeasible(
    *,
    sql: str,
    corpus: list[dict],
    pred_rows: int,
    gold_rows: int,
) -> bool:
    """
    True when gold and pred are both empty because a WHERE literal is absent
    from the probe corpus.
    """
    if pred_rows != 0 or gold_rows != 0:
        return False
    if not re.search(r"\bwhere\b", sql, re.IGNORECASE):
        return False
    return bool(missing_corpus_literals(sql, corpus))

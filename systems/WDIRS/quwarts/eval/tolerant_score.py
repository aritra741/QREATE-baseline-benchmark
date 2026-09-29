"""Format-tolerant scoring, reported next to the benchmark metric (AUDIT: reads gold).

The benchmark metric (``spp.aggregation_metrics`` through ``player_case80.score_split``) compares result
cells after light canonicalization (case, spacing, one date pattern, a fixed USA/UK map). A value that
names the same thing in another form scores as wrong: ``19th–20th`` against ``19th-20th``, ``May 3, 1920``
against ``1920-05-03``, ``a || b`` against ``b||a``, the string ``'null'`` against a missing value.

The tolerant tier applies one symmetric, generic normalization to every stored cell of both databases
(gold and predicted, for every system) and to the query's string literals, then runs the unchanged metric.
Normalizing the data rather than the result rows keeps GROUP BY right: two spellings of one value form
one group before aggregation. It changes only which forms count as equal. Rules, all corpus-independent:

* text: Unicode NFKC, dashes and quotes unified, surrounding quotes and a trailing period dropped,
  whitespace collapsed, case folded
* missing: empty, ``null``, ``none``, ``n/a``, ``nan`` and ``-`` are NULL
* lists: a cell with ``||`` is a set: parts normalized, de-duplicated and sorted
* numbers: a text cell that is only a number (thousands separators, a currency sign, a trailing percent
  sign) becomes that number
* dates: a full date in a common written form becomes ISO ``YYYY-MM-DD``
* centuries: ordinal centuries and ranges (``19th century``, ``nineteenth``, ``19th and 20th centuries``)
  become ``19th`` / ``19th-20th``
* booleans: ``true`` / ``yes`` become ``yes``, ``false`` / ``no`` become ``no``

    report = score_tolerant(dataset, queries, dbs, base, scratch)   # next to router_execute_v3.score
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

_DASHES = re.compile(r"[‐‑‒–—―−]")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_MISSING = {"", "null", "none", "n/a", "na", "nan", "-", "--"}
_NUMBER = re.compile(r"^[$€£]?\s*-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?$|^[$€£]?\s*-?\d+(?:\.\d+)?%?$")
_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
    "twentieth": 20, "twenty-first": 21, "twenty first": 21,
}
_ORD = r"(\d{1,2})(?:st|nd|rd|th)"
_CENTURY = re.compile(rf"^{_ORD}(?:\s*(?:-|to|and|/|&)\s*{_ORD})?(?:\s+centur(?:y|ies))?(?:\s+(?:ad|ce))?$")
_BARE_CENTURY = re.compile(r"^(\d{1,2})(?:\s*(?:-|to|and|/|&)\s*(\d{1,2}))?\s+centur(?:y|ies)$")
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
                 "%d %B %Y", "%d %b %Y", "%d %B, %Y", "%Y-%m-%dT%H:%M:%S")


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _century(text: str) -> str | None:
    t = text
    for word, n in sorted(_ORDINAL_WORDS.items(), key=lambda x: -len(x[0])):
        t = re.sub(rf"\b{word}\b", _ordinal(n), t)
    m = _CENTURY.match(t) or _BARE_CENTURY.match(t)
    if not m:
        return None
    a, b = m.group(1), m.group(2)
    if not (1 <= int(a) <= 21) or (b and not 1 <= int(b) <= 21):
        return None
    return _ordinal(int(a)) + (f"-{_ordinal(int(b))}" if b and b != a else "")


def _date(text: str) -> str | None:
    t = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", text)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def scalar(value: Any) -> Any:
    if value is None or isinstance(value, (int, float)):
        return value
    text = unicodedata.normalize("NFKC", str(value)).translate(_QUOTES)
    text = _DASHES.sub("-", text)
    text = re.sub(r"\s+", " ", text).strip().strip("\"'").strip()
    if text.endswith(".") and text.count(".") == 1 and not re.search(r"\d\.$", text):
        text = text[:-1].rstrip()
    low = text.casefold()
    if low in _MISSING:
        return None
    if _NUMBER.match(low):
        raw = low.replace(",", "").lstrip("$€£").strip().rstrip("%")
        number = float(raw)
        return int(number) if number.is_integer() else number
    if low in ("true", "yes"):
        return "yes"
    if low in ("false", "no"):
        return "no"
    century = _century(low)
    if century:
        return century
    date = _date(text)
    if date:
        return date
    return low


def cell(value: Any) -> Any:
    if isinstance(value, str) and "||" in value:
        parts = {p for p in (scalar(x) for x in value.split("||")) if p is not None}
        if not parts:
            return None
        return "||".join(sorted(str(p) for p in parts))
    return scalar(value)


def normalize_sql(sql: str) -> str:
    """The same normalization applied to the query's string literals (``LIKE`` patterns keep their
    wildcards; the empty string stays the empty string), so a literal and the cells it names stay equal."""

    import sqlglot
    from sqlglot import exp

    tree = sqlglot.parse_one(sql, read="sqlite")

    def fix(node):
        if isinstance(node, exp.Literal) and node.is_string and node.this != "":
            new = cell(node.this)
            if isinstance(new, str) and new != node.this:
                return exp.Literal.string(new)
        return node

    return tree.transform(fix).sql(dialect="sqlite")


def _unresolved_signatures(conn) -> bool:
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        for col in [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]:
            if col.startswith("sig_") and col.endswith("_r"):
                if conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" = 1').fetchone()[0]:
                    return False
    return True


def normalized_copy(src: str | Path, dest: Path, columns: set[str] | None = None) -> Path:
    """A copy of a predicted database with every attribute cell normalized (signature and internal
    columns untouched). The signature rewrite of the benchmark scorer is a no-op when every signature is
    unresolved; that is checked, since the tolerant path runs the query directly.

    ``columns`` (lower-case names): normalize only these; a query's score depends only on the columns it
    references, so scoring a few queries needs only theirs."""

    import shutil
    import sqlite3

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    conn = sqlite3.connect(dest)
    if not _unresolved_signatures(conn):
        conn.close()
        raise NotImplementedError(f"{src}: resolved signature columns; the tolerant path would differ")
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')
                if r[1] != "doc_id" and not r[1].startswith(("sig_", "__")) and not r[1].endswith("__canonical")
                and (columns is None or r[1].lower() in columns)]
        for col in cols:
            rows_ = conn.execute(f'SELECT rowid, "{col}" FROM "{table}" WHERE typeof("{col}") = \'text\'').fetchall()
            updates = [(cell(v), rowid) for rowid, v in rows_ if cell(v) != v]
            conn.executemany(f'UPDATE "{table}" SET "{col}" = ? WHERE rowid = ?', updates)
    conn.commit()
    conn.close()
    return dest


def score_tolerant(dataset: str, queries: dict[str, str], dbs: dict[str, str], base: Path, scratch: Path) -> dict[str, Any]:
    """The benchmark metric over normalized databases (gold and predicted) and normalized queries."""

    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
    from quwarts.experiments.synthesize_case80 import gold_name, score_with_rewrites

    gold = {t: [{k: cell(v) for k, v in r.items()} for r in rs] for t, rs in load_ground_truth(gold_name(dataset)).items()}
    copies: dict[str, str] = {}
    for path in sorted({*dbs.values(), str(base)}):
        copies[path] = str(normalized_copy(path, scratch / f"{len(copies):04d}_{Path(path).name}"))
    sql = {q: normalize_sql(s) for q, s in queries.items()}
    rows_ = [{"query_id": q, "sql": sql[q], "pack": q.split(":", 1)[0]} for q in queries]
    rewrites = {q: {"sql": sql[q], "sqlite_path": copies[dbs.get(q, str(base))]} for q in queries}
    report = score_with_rewrites(rows_, rewrites, Path(copies[str(base)]), gold, dataset)
    per_query = [{"query_id": r["query_id"], "structure_f2": r.get("structure_f2"), "cell_f1_20": r.get("cell_f1_20"),
                  "product": float(r.get("structure_f2") or 0.0) * float(r.get("cell_f1_20") or 0.0), "pred_rows": r.get("pred_rows")}
                 for r in report.get("per_query") or []]
    return {"mean_per_query_product": mean_per_query_product(report), "mean_cell_f1_20": mean_cell_f1_20(report),
            "per_query": per_query}

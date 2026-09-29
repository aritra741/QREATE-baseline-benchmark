"""The model tier (T2): rewrite residual values with the model, one call per batch of distinct values.

Its cost is linear in the number of distinct residual values, not in rows or documents: a column with
1,000 cells and 40 distinct off-form values costs one call. No document is read. Calls are memoized in a
journal keyed by the prompt's hash (the same memo discipline as the read journal), so a replay is free.

Answers are validated against the column's target: a value in the vocabulary, or one that fits the
literals' shape family. Anything else (including ``null``) leaves the value as T0/T1 left it.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any, Callable

from quwarts.core.represent.normalize import Target, status

SYSTEM = "You standardize database values so that SQL queries can match them. Return JSON only."
BATCH = 40
_lock = threading.Lock()


def prompt(target: Target, values: list[str]) -> str:
    lines = [f"Column: {target.table}.{target.column}"]
    if target.description:
        lines.append(f"Meaning: {target.description}")
    if target.vocabulary:
        shown = target.vocabulary[:40]
        lines.append("Values queries use, with their exact spelling: " + "; ".join(shown))
    style = []
    if target.case:
        style.append({"title": "Title Case", "lower": "lower case", "upper": "UPPER CASE"}[target.case])
    if target.separator == "_":
        style.append("words joined by underscores")
    if target.vocabulary:
        style.append("as short as the listed values")
    if style:
        lines.append("Form of a value: " + ", ".join(style) + ".")
    lines += [
        "",
        "For each numbered value below, give the standardized value:",
        "- if it means one of the listed values, give that listed value exactly;",
        "- if it is a value of this column that is not listed, write it in the same form;",
        "- if it is not a value of this column, give null.",
        'Answer with JSON only, mapping each number to a string or null: {"1": "...", "2": null}',
        "",
    ]
    lines += [f"{i}. {v}" for i, v in enumerate(values, 1)]
    return "\n".join(lines)


def _parse(text: str, n: int) -> dict[int, Any]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        raw = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    out = {}
    for k, v in raw.items():
        try:
            i = int(str(k).strip().rstrip("."))
        except ValueError:
            continue
        if 1 <= i <= n:
            out[i] = v
    return out


class Journal:
    def __init__(self, path: Path):
        self.path = path
        self.rows: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["sha"]] = row

    def get(self, sha: str) -> dict | None:
        return self.rows.get(sha)

    def put(self, row: dict) -> None:
        with _lock:
            self.rows[row["sha"]] = row
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def estimate_tokens(target: Target, values: list[str]) -> int:
    """Prompt and answer tokens of normalizing these values (for the router, before any call)."""

    from quwarts.core.retrieve_extract.tokens import count_tokens

    total = 0
    for start in range(0, len(values), BATCH):
        batch = values[start:start + BATCH]
        total += count_tokens(prompt(target, batch)) + 30 + sum(len(v) // 3 + 8 for v in batch)
    return total


def normalize(target: Target, values: list[str], caller: Callable | None, journal: Journal,
              workers: int = 8) -> tuple[dict[str, str], dict[str, int]]:
    """Residual value -> validated model rewrite; stats (calls made, replayed, tokens spent)."""

    from concurrent.futures import ThreadPoolExecutor

    stats = {"calls": 0, "replayed": 0, "tokens": 0, "accepted": 0, "rejected": 0}
    batches = [values[i:i + BATCH] for i in range(0, len(values), BATCH)]
    out: dict[str, str] = {}

    def run(batch: list[str]) -> None:
        text = prompt(target, batch)
        sha = hashlib.sha256((SYSTEM + "\n" + text).encode()).hexdigest()
        row = journal.get(sha)
        if row is None:
            if caller is None:
                return
            before = caller.ledger.spent
            answer = caller.complete(text, "represent_t2", system=SYSTEM, table=target.table, column=target.column)
            row = {"sha": sha, "table": target.table, "column": target.column, "values": batch,
                   "response": answer, "tokens": caller.ledger.spent - before}
            journal.put(row)
            with _lock:
                stats["calls"] += 1
                stats["tokens"] += row["tokens"]
        else:
            with _lock:
                stats["replayed"] += 1
        parsed = _parse(row["response"], len(batch))
        for i, v in enumerate(batch, 1):
            new = parsed.get(i)
            if isinstance(new, str) and new.strip() and status(new.strip(), target) != "off":
                with _lock:
                    out[v] = new.strip()
                    stats["accepted"] += 1
            else:
                with _lock:
                    stats["rejected"] += 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run, batches))
    return out, stats


def verify_matches(pairs: list[tuple[str, list[str]]], context: str, caller: Callable | None, journal: Journal
                   ) -> tuple[dict[str, str], dict[str, int]]:
    """Entity resolution questions: for each surface, which candidate (if any) names the same entity."""

    stats = {"calls": 0, "replayed": 0, "tokens": 0}
    out: dict[str, str] = {}
    for start in range(0, len(pairs), 25):
        batch = pairs[start:start + 25]
        lines = [f"Values of {context} must match the entity names of the other table exactly.",
                 "For each numbered value, give the candidate that names the same entity, or null if none does.",
                 'Answer with JSON only: {"1": "candidate text", "2": null}', ""]
        for i, (surface, cands) in enumerate(batch, 1):
            lines.append(f"{i}. {surface}  | candidates: " + " ; ".join(cands))
        text = "\n".join(lines)
        sha = hashlib.sha256((SYSTEM + "\n" + text).encode()).hexdigest()
        row = journal.get(sha)
        if row is None:
            if caller is None:
                continue
            before = caller.ledger.spent
            answer = caller.complete(text, "represent_er", system=SYSTEM, context=context)
            row = {"sha": sha, "context": context, "pairs": batch, "response": answer, "tokens": caller.ledger.spent - before}
            journal.put(row)
            stats["calls"] += 1
            stats["tokens"] += row["tokens"]
        else:
            stats["replayed"] += 1
        parsed = _parse(row["response"], len(batch))
        for i, (surface, cands) in enumerate(batch, 1):
            got = parsed.get(i)
            if isinstance(got, str) and got.strip() in cands:
                out[surface] = got.strip()
    return out, stats

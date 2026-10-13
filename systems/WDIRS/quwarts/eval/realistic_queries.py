"""The realistic query workload (Query/Realistic/<corpus>.sql): every query an aggregate a real user would ask, joins
only inside aggregates. Ids ``real:<corpus>#<Qn>``; loaded into a corpus's catalogue by ``register``."""

from __future__ import annotations

import re
from pathlib import Path

import os

QDIR = Path(__file__).resolve().parents[4] / "Query" / "Realistic"
# QUWARTS_REALISTIC=v2: the relational version (grouped tables, HAVING, top-k, subqueries; Query/Realistic/v2), ids real2:
VERSION = os.environ.get("QUWARTS_REALISTIC", "v1")


def load(corpus: str) -> list[tuple[str, str, str]]:
    """(id, question, sql) in file order."""
    out = []
    path, prefix = (QDIR / f"{corpus}.sql", "real") if VERSION == "v1" else (QDIR / VERSION / f"{corpus}.sql", "real" + VERSION[1:])
    for block in re.split(r";\s*\n", path.read_text()):
        m = re.search(r"--\s*(QJ?\d+):\s*(.*)", block)
        sql = "\n".join(x for x in block.splitlines() if not x.strip().startswith("--")).strip()
        if m and sql:
            out.append((f"{prefix}:{corpus}#{m.group(1)}", m.group(2).strip(), sql))
    return out


def register(ctx, corpus: str) -> list[str]:
    ids = []
    for qid, _q, sql in load(corpus):
        ctx.catalog[qid] = sql
        ids.append(qid)
    return ids

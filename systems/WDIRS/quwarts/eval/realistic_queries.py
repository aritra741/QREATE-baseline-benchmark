"""The realistic query workload (Query/Realistic/<corpus>.sql): every query an aggregate a real user would ask, joins
only inside aggregates. Ids ``real:<corpus>#<Qn>``; loaded into a corpus's catalogue by ``register``."""

from __future__ import annotations

import re
from pathlib import Path

QDIR = Path(__file__).resolve().parents[4] / "Query" / "Realistic"


def load(corpus: str) -> list[tuple[str, str, str]]:
    """(id, question, sql) in file order."""
    out = []
    for block in re.split(r";\s*\n", (QDIR / f"{corpus}.sql").read_text()):
        m = re.search(r"--\s*(QJ?\d+):\s*(.*)", block)
        sql = "\n".join(x for x in block.splitlines() if not x.strip().startswith("--")).strip()
        if m and sql:
            out.append((f"real:{corpus}#{m.group(1)}", m.group(2).strip(), sql))
    return out


def register(ctx, corpus: str) -> list[str]:
    ids = []
    for qid, _q, sql in load(corpus):
        ctx.catalog[qid] = sql
        ids.append(qid)
    return ids

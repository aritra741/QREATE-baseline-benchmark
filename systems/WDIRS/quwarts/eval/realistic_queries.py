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
    if VERSION == "v1":
        path, prefix = QDIR / f"{corpus}.sql", "real"
    elif VERSION == "v2":
        path, prefix = QDIR / "v2" / f"{corpus}.sql", "real2"
    else:  # v3 on: the multi-agent-reviewed test set (the build set is load_build)
        path, prefix = QDIR / VERSION / f"{corpus}_test.sql", "real" + VERSION[1:]
    for block in re.split(r";\s*\n", path.read_text()):
        m = re.search(r"--\s*(Q[A-Z]*\d+):\s*(.*)", block)
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


def load_build(corpus: str) -> dict[str, str]:
    """The realistic build workload (v3 on): what users asked before the table was built, on its initial columns.
    Used as W0 when QUWARTS_W0_REALISTIC=1 (drift_run.context)."""
    out = {}
    for block in re.split(r";\s*\n", (QDIR / VERSION / f"{corpus}_build.sql").read_text()):
        m = re.search(r"--\s*(Q[A-Z]*\d+):\s*(.*)", block)
        sql = "\n".join(x for x in block.splitlines() if not x.strip().startswith("--")).strip()
        if m and sql:
            out[f"build{VERSION[1:]}:{corpus}#{m.group(1)}"] = sql
    return out

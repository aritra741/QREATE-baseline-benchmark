"""Query-critical extraction priorities from the workload AST and a live DB."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from quwarts.core.amplify import attach_amplification, amp
from quwarts.core.models import Role, Workload
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.config import FROZEN
from quwarts.core.retrieve_extract.route import prompt_and_schema_tokens
from quwarts.core.workload import analyze_workload


def _critical(roles: set[Role]) -> bool:
    names = {role.value if hasattr(role, "value") else str(role) for role in roles}
    return bool(names & {"predicate", "join", "group", "agg_additive", "agg_distinct", "agg_extremal"})


def _empty_or_zero(rows: list[dict[str, Any]], query_id: str, sql: str) -> bool:
    if not rows:
        return True
    if len(rows) == 1 and is_count_query(query_shape(query_id, sql)):
        values = [value for value in rows[0].values() if value not in (None, "")]
        if values and all(str(value) in {"0", "0.0"} for value in values):
            return True
        if not values:
            return True
    return False


def gated_query_counts(
    sqlite_path: Path,
    statements: dict[str, str],
    predicates,
    workload: Workload,
) -> dict[str, int]:
    attach_amplification(workload)
    gated: dict[str, int] = {name: 0 for name in workload.requirements}
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        for query_id, sql in statements.items():
            rewritten = official_sql(sql, sqlite_path, predicates)
            try:
                cur = conn.execute(rewritten)
                cols = [item[0] for item in cur.description] if cur.description else []
                rows = [dict(zip(cols, rec)) for rec in cur.fetchall()]
            except sqlite3.Error:
                rows = []
            if not _empty_or_zero(rows, query_id, sql):
                continue
            _, single = analyze_workload({query_id: sql})
            for name, req in single.requirements.items():
                if name in gated and _critical(req.roles):
                    gated[name] += 1
    finally:
        conn.close()
    return gated


def missing_mass(sqlite_path: Path, table: str, attributes: Iterable[str]) -> dict[str, int]:
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        cols = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
        out: dict[str, int] = {}
        for name in attributes:
            bare = name.split(".")[-1]
            if bare not in cols:
                out[name] = 0
                continue
            out[name] = int(
                conn.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE "{bare}" IS NULL OR CAST("{bare}" AS TEXT) = \'\''
                ).fetchone()[0]
            )
        return out
    finally:
        conn.close()


def rank_attributes(
    workload: Workload,
    gated: dict[str, int],
    missing: dict[str, int],
    descriptions: dict[str, str],
) -> list[dict[str, Any]]:
    attach_amplification(workload)
    reserve = int(FROZEN["reserved_completion_tokens"])
    cap = int(FROZEN["retrieve_context_cap"])
    ranked = []
    for name, req in workload.requirements.items():
        cost = max(1.0, prompt_and_schema_tokens([name], descriptions) + cap + reserve)
        freq = float(req.freq_weight or 0.0)
        amplification = float(req.amp if req.amp is not None else amp(req))
        miss = float(missing.get(name, 0))
        gate = float(gated.get(name, 0))
        priority = (gate * freq * amplification * miss) / cost
        tie = (freq * amplification * miss) / cost
        ranked.append(
            {
                "attribute": name,
                "priority": priority,
                "tiebreak": tie,
                "empty_or_zero_support_queries_gated": int(gate),
                "query_frequency": freq,
                "downstream_amplification": amplification,
                "missing_entity_mass": int(miss),
                "estimated_extraction_cost": cost,
                "critical": _critical(req.roles),
                "roles": sorted(role.value if hasattr(role, "value") else str(role) for role in (req.roles or set())),
            }
        )
    ranked.sort(key=lambda row: (-row["priority"], -row["tiebreak"], row["attribute"]))
    return ranked

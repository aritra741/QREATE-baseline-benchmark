"""Router-v3 plan: context-split schema discovery for a reference workload.

1. Needs: one per (query, attribute) use, with its SQL-derived kind (zero tokens).
2. Contexts: the canonical read plus each reference-workload query.
3. Paired sampling (``context_probe``) within ``probe_fraction * theta``.
4. Distances D(i <- p) with upper confidence bounds (``facility``).
5. Budgeted facility location: which contexts to materialize per table and which
   provider serves each need. Needs sharing a provider share one physical column;
   an attribute whose needs land on different providers becomes a set of
   context-split columns.

The plan reports its expected loss (mean per query, benchmark cell-score units)
relative to serving every need from its own query context, as an upper bound and
as a point estimate.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from quwarts.core.ledger import BudgetedCaller
from quwarts.core.router.context_probe import V3, Observations, contexts_by_table, field_specs, run_context_probe
from quwarts.core.router.corpus_features import table_corpus
from quwarts.core.router.facility import INCUMBENT, combine, need_distances, table_frontier
from quwarts.core.router.needs import CANONICAL, workload_needs
from quwarts.core.router.plan import canonical_json, file_sha
from quwarts.core.router.registry import CorpusSpec
from quwarts.core.router.workload_features import workload_features

VERSION = "router-v3"
PROBE_FRACTION = 0.20


def load_incumbent(spec: CorpusSpec, db_path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    """``{(table, doc file name): {attribute: value}}``; empty when there is no incumbent."""

    if db_path is None or not Path(db_path).is_file():
        return {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for table in spec.tables:
        try:
            cursor = conn.execute(f'SELECT * FROM "{table.sql_name}"')
        except sqlite3.Error:
            continue
        names = [d[0] for d in cursor.description]
        if "doc_id" not in names:
            continue
        for row in cursor.fetchall():
            record = dict(zip(names, row))
            doc = Path(str(record.get("doc_id"))).name
            if not doc.endswith(".txt"):
                doc = f"{doc}.txt"
            out[(table.sql_name, doc)] = record
    conn.close()
    return out


def build_plan_v3(
    spec: CorpusSpec,
    theta: int,
    caller: BudgetedCaller | None = None,
    journal: Path | None = None,
    incumbent_db: Path | None = None,
    observations: Observations | None = None,
    probe_spent: int = 0,
) -> dict[str, Any]:
    queries = spec.queries()
    needs = workload_needs(spec, queries)
    wf = workload_features(spec, queries)
    numeric = {q for q, use in wf["attributes"].items() if use.numeric}
    fields = field_specs(spec, needs, numeric)
    corpora = {t.sql_name: table_corpus(t) for t in spec.tables if any(n.table == t.sql_name for n in needs)}
    doc_tokens = {name: tc.tokens for name, tc in corpora.items()}
    read_cost = {name: tc.full_read_cost() for name, tc in corpora.items()}
    db = incumbent_db or spec.incumbent_db
    incumbent = load_incumbent(spec, db)

    probe_budget = int(theta * PROBE_FRACTION)
    probe: dict[str, Any] = {"budget": probe_budget, "spent": probe_spent, "dry_run": caller is None and observations is None}
    if observations is None and caller is not None:
        probe = run_context_probe(spec, needs, queries, doc_tokens, fields, caller, probe_budget, journal)
        observations = Observations.from_json(probe["observations"])
    observations = observations or Observations()
    spent = int(probe.get("spent", 0))

    distances = need_distances(needs, observations, fields, incumbent)
    available = max(0, theta - spent)
    frontiers = {
        table: table_frontier(table, [n for n in needs if n.table == table], distances, read_cost[table])
        for table in corpora
    }
    cost, loss_point, picks = combine(frontiers, available)
    n_queries = len(queries)

    decisions = []
    upper_total = 0.0
    for need in needs:
        provider, point = picks[need.table].assignment[need.key]
        d = distances.get((need.key, provider))
        upper = 0.0 if provider == need.query_id else (d.ucb if d and not math.isinf(d.ucb) else 1.0)
        upper_total += need.weight * upper
        decisions.append({
            **need.to_json(),
            "provider": provider,
            "loss_point": point,
            "loss_upper": upper,
            "pairs": d.n if d else 0,
        })

    columns: dict[str, dict[str, list[str]]] = {}
    for row in decisions:
        columns.setdefault(row["qualified"], {}).setdefault(row["provider"], []).append(row["query_id"])

    plan = {
        "router": {"version": VERSION, "probe_fraction": PROBE_FRACTION, "v3": V3},
        "corpus": spec.name,
        "inputs": {
            "manifest_sha": file_sha(spec.manifest),
            "attributes_sha": [file_sha(p) for p in spec.attributes_json],
            "incumbent_sha": file_sha(db) if incumbent else None,
            "corpus_fingerprint": hashlib.sha256(canonical_json(doc_tokens).encode()).hexdigest(),
        },
        "budget": {"theta": theta, "probe_budget": probe_budget, "probe_spent": spent,
                   "available": available, "planned": cost,
                   "own_context_cost": sum(read_cost[t] * len({n.query_id for n in needs if n.table == t}) for t in corpora)},
        "expected_loss_per_query": {"upper": upper_total / n_queries, "point": loss_point / n_queries},
        "contexts_opened": {t: list(o.contexts) for t, o in picks.items()},
        "columns": columns,
        "decisions": decisions,
        "distances": [d.to_json() for d in distances.values() if d.n],
        "probe": {k: v for k, v in probe.items() if k != "observations"},
        "frontier_sizes": {t: len(f) for t, f in frontiers.items()},
    }
    plan["plan_hash"] = hashlib.sha256(canonical_json({k: v for k, v in plan.items() if k != "probe"}).encode()).hexdigest()
    return plan, observations


def summarize_v3(plan: dict[str, Any]) -> str:
    b = plan["budget"]
    loss = plan["expected_loss_per_query"]
    lines = [
        f"corpus={plan['corpus']} {VERSION} expected loss/query: point={loss['point']:.3f} upper={loss['upper']:.3f} "
        f"planned={b['planned']:,}/{b['available']:,} probe={b['probe_spent']:,} theta={b['theta']:,} "
        f"own-context cost={b['own_context_cost']:,} plan={plan['plan_hash'][:12]}",
    ]
    for table, contexts in plan["contexts_opened"].items():
        lines.append(f"  table {table}: open {contexts or ['(none: incumbent only)']}")
    for qualified, groups in sorted(plan["columns"].items()):
        parts = [f"{provider.replace('__', '')}<-{len(qs)}q" for provider, qs in sorted(groups.items())]
        lines.append(f"  {qualified:<40} {' | '.join(parts)}")
    return "\n".join(lines)

"""Workload-witness residual scheduler. Gold-free."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlglot import exp

from quwarts.core.shared_bundle.inventory import _roles_for
from quwarts.core.signature import resolve_attribute, select_aliases, table_aliases
from quwarts.core.workload import _default_entity, parse_sql

DEPEND_ROLES = {"WHERE", "JOIN", "CASE", "GROUP BY", "HAVING", "aggregate input"}


def query_attr_roles(statements: dict[str, str]) -> dict[str, dict[str, set[str]]]:
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for query_id, sql in statements.items():
        tree = parse_sql(sql)
        aliases = table_aliases(tree)
        default = _default_entity(tree)
        skip = select_aliases(tree)
        for column in tree.find_all(exp.Column):
            resolved = resolve_attribute(column, aliases, default)
            if resolved is None:
                continue
            name = resolved[2]
            if name in skip or name == "rowid":
                continue
            for role, _expr in _roles_for(column):
                out[query_id][name].add(role)
    return out


class WorkloadGraph:
    def __init__(
        self,
        tasks: list[dict[str, Any]],
        empty_cells: list[tuple[str, str]],
        resolved_free: set[tuple[str, str]],
        roles: dict[str, dict[str, set[str]]],
        query_ids: list[str],
        entities: list[str],
    ) -> None:
        self.tasks = {task["key"]: task for task in tasks}
        self.empty = set(empty_cells)
        self.resolved_free = set(resolved_free)
        self.query_ids = query_ids
        self.entities = entities
        self.required = {
            qid: sorted(name for name, role_set in roles.get(qid, {}).items() if role_set & DEPEND_ROLES)
            for qid in query_ids
        }
        self.witnesses: list[dict[str, Any]] = []
        self.by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.n_candidate: dict[str, int] = {}
        for qid in query_ids:
            count = 0
            for entity in entities:
                needed = []
                unavailable = False
                for attr in self.required[qid]:
                    key = (entity, attr)
                    if key in self.resolved_free:
                        continue
                    if key in self.empty:
                        unavailable = True
                        continue
                    task_key = f"{entity}::{attr}"
                    if task_key not in self.tasks:
                        unavailable = True
                        continue
                    needed.append(attr)
                feasible = not unavailable
                if feasible:
                    count += 1
                rec = {
                    "query_id": qid,
                    "entity_id": entity,
                    "needed": needed,
                    "feasible": feasible,
                    "already_complete": feasible and not needed,
                }
                self.witnesses.append(rec)
                self.by_entity[entity].append(rec)
            self.n_candidate[qid] = count


def greedy_schedule(graph: WorkloadGraph, cost_of, budget: int) -> dict[str, Any]:
    scheduled: set[str] = set()
    packages: list[dict[str, Any]] = []
    spent = 0
    while True:
        best = None
        for entity, rows in graph.by_entity.items():
            open_rows = []
            for row in rows:
                if not row["feasible"] or row["already_complete"]:
                    continue
                need = [attr for attr in row["needed"] if f"{entity}::{attr}" not in scheduled]
                if need:
                    open_rows.append((row, need))
            for row, need in open_rows:
                keys = [f"{entity}::{attr}" for attr in need]
                extra = cost_of(keys)
                if extra <= 0 or spent + extra > budget:
                    continue
                added = set(keys)
                newly = []
                for other, remain in open_rows:
                    if remain and all(f"{entity}::{attr}" in added or f"{entity}::{attr}" in scheduled for attr in remain):
                        if any(f"{entity}::{attr}" in added for attr in remain):
                            n = graph.n_candidate[other["query_id"]]
                            newly.append((other["query_id"], 1.0 / n if n else 0.0))
                gain = sum(item[1] for item in newly)
                if gain <= 0:
                    continue
                cand = (-gain / extra, row["query_id"], entity, tuple(need), extra, keys)
                if best is None or cand < best:
                    best = cand
        if best is None:
            break
        _eff, qid, entity, need, extra, keys = best
        scheduled.update(keys)
        spent += extra
        packages.append({"query_id": qid, "entity_id": entity, "attributes": list(need), "task_keys": keys, "reserved_delta": extra})
    leftover = []
    for key, task in sorted(graph.tasks.items()):
        if key in scheduled:
            continue
        extra = cost_of([key])
        if extra > 0 and spent + extra <= budget:
            scheduled.add(key)
            spent += extra
            leftover.append(key)
    return {"scheduled_keys": [key for key in scheduled], "packages": packages, "leftover_fillers": leftover, "reserved": spent, "solver": "deterministic_witness_package_greedy"}

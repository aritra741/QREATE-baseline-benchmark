"""Canonical query-witness programs. Dedup conditions and group expressions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from sqlglot import exp

from quwarts.core.amplify import amp, attach_amplification
from quwarts.core.contracts import case_literals_from_sql
from quwarts.core.query_filter import atomic_conditions, canonicalize_filter
from quwarts.core.query_witness import compile_witness_spec, group_digest
from quwarts.core.workload import Workload, parse_sql

_AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)


def _norm(sql: str) -> str:
    return " ".join((sql or "").lower().split())


def _digest(text: str) -> str:
    return hashlib.sha256(_norm(text).encode()).hexdigest()[:16]


def case_then_values(sql: str) -> list[str]:
    values: list[str] = []
    try:
        tree = parse_sql(sql)
    except Exception:
        return values
    for case in tree.find_all(exp.Case):
        for branch in case.args.get("ifs") or []:
            then = branch.args.get("true")
            if then is None:
                continue
            if isinstance(then, exp.Literal) and then.is_string:
                values.append(str(then.this))
        default = case.args.get("default")
        if isinstance(default, exp.Literal) and default.is_string:
            values.append(str(default.this))
    return list(dict.fromkeys(values))


def apply_case(expr_sql: str, surface: str) -> str | None:
    legal = case_then_values(expr_sql)
    if not legal or not surface:
        return None
    blob = surface.casefold()
    try:
        tree = parse_sql(f"SELECT {expr_sql}")
    except Exception:
        for label in legal:
            if label and label.casefold() in blob:
                return label
        return None
    for case in tree.find_all(exp.Case):
        for branch in case.args.get("ifs") or []:
            cond = branch.this
            then = branch.args.get("true")
            label = str(then.this) if isinstance(then, exp.Literal) and then.is_string else None
            literals = [str(item.this) for item in (cond.find_all(exp.Literal) if cond else []) if item.is_string]
            if any(lit and lit.casefold() in blob for lit in literals):
                return label
        default = case.args.get("default")
        if isinstance(default, exp.Literal) and default.is_string:
            return str(default.this)
    for label in legal:
        if label and label.casefold() in blob:
            return label
    return None


def _agg_sql(sql: str) -> str:
    try:
        tree = parse_sql(sql)
    except Exception:
        return ""
    parts = []
    for proj in getattr(tree, "expressions", []) or []:
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        if expr.find(_AGGS):
            parts.append(_norm(expr.sql(dialect="sqlite")))
    return " | ".join(parts)


def _columns(sql: str) -> list[str]:
    try:
        tree = parse_sql(sql)
    except Exception:
        return []
    names = []
    for col in tree.find_all(exp.Column):
        name = (col.name or "").lower()
        if name and name not in {"rowid"}:
            names.append(name)
    return list(dict.fromkeys(names))


@dataclass
class WitnessProgram:
    program_id: str
    condition_id: str
    group_id: str
    condition_sql: str
    group_sql: str | None
    agg_sql: str
    query_ids: list[str] = field(default_factory=list)
    kinds: tuple[str, ...] = ()
    legal_group_values: list[str] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    frequency: float = 0.0
    amplification: float = 0.0
    requested_fields: list[str] = field(default_factory=list)


def compile_programs(queries: list[dict[str, str]], workload: Workload) -> list[WitnessProgram]:
    attach_amplification(workload)
    by_id: dict[str, WitnessProgram] = {}
    for row in queries:
        qid = row["query_id"]
        sql = row["sql"]
        spec = compile_witness_spec(qid, sql)
        cond = canonicalize_filter(sql)
        group = spec.group_sql[0] if spec.group_sql else None
        agg = _agg_sql(sql)
        program_id = _digest(f"{cond}||{group or ''}||{agg}")
        condition_id = _digest(cond or "")
        group_id = group_digest(group) if group else "none"
        req = workload.requirements
        freq = 0.0
        amps = 0.0
        for name, item in req.items():
            bare = name.split(".")[-1]
            if bare in _columns(sql):
                freq += float(item.freq_weight or 0.0)
                amps += float(item.amp if item.amp is not None else amp(item))
        literals = []
        for atom in atomic_conditions(sql):
            literals.extend(re.findall(r"'([^']+)'", atom.get("sql") or ""))
        for values in case_literals_from_sql(sql).values():
            literals.extend(values)
        literals.extend(case_then_values(group or ""))
        fields = ["witness_id", "condition", "evidence"]
        if group:
            fields.append("group_value")
        if "counted_value" in spec.kinds:
            fields.append("counted_value_present")
        if any(token in agg for token in ("sum(", "avg(", "max(", "min(")):
            fields.append("aggregate_value")
        current = by_id.get(program_id)
        if current is None:
            by_id[program_id] = WitnessProgram(
                program_id=program_id,
                condition_id=condition_id,
                group_id=group_id,
                condition_sql=cond,
                group_sql=group,
                agg_sql=agg,
                query_ids=[qid],
                kinds=spec.kinds,
                legal_group_values=case_then_values(group or sql),
                literals=list(dict.fromkeys(lit for lit in literals if lit)),
                columns=_columns(sql),
                frequency=freq,
                amplification=max(amps, 1.0),
                requested_fields=fields,
            )
        else:
            current.query_ids.append(qid)
            current.frequency += freq
            current.literals = list(dict.fromkeys(current.literals + literals))
    return sorted(by_id.values(), key=lambda item: item.program_id)

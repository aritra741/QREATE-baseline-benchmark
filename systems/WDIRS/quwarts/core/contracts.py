"""Workload contracts compiled from SQL. Open vocabulary; never a closed domain."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlglot import exp, parse_one

from quwarts.core.domain import like_tokens_from_workload
from quwarts.core.models import Workload


def _fold(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").casefold().split())


def _column_name(node) -> str | None:
    if isinstance(node, exp.Column):
        table = node.table or ""
        name = node.name
        if table:
            return f"{table}.{name}"
        return name
    return None


def _string_literals(node) -> list[str]:
    found = []
    if node is None:
        return found
    for item in node.find_all(exp.Literal):
        if item.is_number:
            continue
        text = item.name if hasattr(item, "name") else str(item.this)
        text = str(text).strip()
        if len(text) >= 3 and text.startswith("%") and text.endswith("%") and "%" not in text[1:-1]:
            text = text[1:-1].strip()
        if text:
            found.append(text)
    return found


def case_literals_from_sql(sql: str) -> dict[str, list[str]]:
    """Comparison literals inside CASE WHEN, keyed by column."""

    found: dict[str, set[str]] = defaultdict(set)
    try:
        tree = parse_one(sql)
    except Exception:
        return {}
    for case in tree.find_all(exp.Case):
        for branch in case.args.get("ifs") or []:
            cond = branch.this
            if cond is None:
                continue
            cols = [_column_name(col) for col in cond.find_all(exp.Column)]
            cols = [name for name in cols if name]
            literals = _string_literals(cond)
            if not cols or not literals:
                continue
            for name in cols:
                found[name].update(literals)
                found[name.split(".")[-1]].update(literals)
    return {name: sorted(values) for name, values in found.items()}


def compile_contracts(workload: Workload) -> dict[str, dict[str, Any]]:
    """Sound constraints implied by the SQL. Each row records its AST source."""

    case_lits: dict[str, set[str]] = defaultdict(set)
    eq_lits: dict[str, set[str]] = defaultdict(set)
    for template in workload.templates:
        sql = template.raw_sql or template.canonical_sql
        for name, values in case_literals_from_sql(sql).items():
            case_lits[name].update(values)
        for slot in template.param_slots:
            op = (slot.op or "").upper()
            if op in {"=", "==", "<>", "!="} or (op and op not in {"LIKE", "IN", "BETWEEN"}):
                for value in slot.observed_constants or []:
                    if value in (None, "") or (isinstance(value, (int, float)) and not isinstance(value, bool)):
                        if isinstance(value, str) and value != "":
                            eq_lits[slot.attribute].add(str(value))
                    elif isinstance(value, str):
                        eq_lits[slot.attribute].add(value)

    like = like_tokens_from_workload(workload)
    contracts: dict[str, dict[str, Any]] = {}
    names = set(workload.requirements) | set(case_lits) | set(like) | set(workload.in_lists)
    for name in names:
        if "." not in name and name not in workload.requirements:
            continue
        sources: list[str] = []
        vocab: list[str] = []
        kind = "workload_undetermined"
        case_vals = list(case_lits.get(name) or case_lits.get(name.split(".")[-1]) or [])
        like_vals = list(like.get(name) or like.get(name.split(".")[-1]) or [])
        in_vals: list[str] = []
        for item in workload.in_lists.get(name) or workload.in_lists.get(name.split(".")[-1], []):
            in_vals.extend(item)
        eq_vals = list(eq_lits.get(name) or eq_lits.get(name.split(".")[-1]) or [])
        if case_vals:
            sources.append("case_when")
            vocab.extend(case_vals)
        if like_vals:
            sources.append("like")
            vocab.extend(like_vals)
        if in_vals:
            sources.append("in_list")
            vocab.extend(in_vals)
        if eq_vals:
            sources.append("comparison_literal")
            vocab.extend(eq_vals)
        uniq = []
        folded = set()
        for item in vocab:
            key = _fold(item)
            if not key or key in folded:
                continue
            folded.add(key)
            uniq.append(item)
        if uniq:
            kind = "open_vocabulary"
        elif sources:
            kind = "structural"
        contracts[name] = {
            "kind": kind,
            "sources": sorted(set(sources)),
            "vocab": uniq,
            "closed": False,
        }
    for template in workload.templates:
        for left, right in template.join_pairs:
            for name in (left, right):
                row = contracts.setdefault(
                    name,
                    {"kind": "structural", "sources": [], "vocab": [], "closed": False},
                )
                if "equijoin" not in row["sources"]:
                    row["sources"].append("equijoin")
                if row["kind"] == "workload_undetermined":
                    row["kind"] = "structural"
    return contracts


def token_hits(surface: str, vocab: list[str]) -> list[str]:
    folded = _fold(surface)
    hits = []
    for token in vocab:
        key = _fold(token)
        if key and (key == folded or key in folded or folded in key):
            hits.append(token)
    return hits


def assign_vocab(surface: str | None, vocab: list[str]) -> str | None:
    """Query-relevant tokens only. No default to the first token."""

    if surface in (None, "") or not vocab:
        return None
    hits = token_hits(str(surface), vocab)
    if not hits:
        return None
    return "|".join(hits)


def abstention(contracts: dict[str, dict[str, Any]], names: list[str]) -> dict[str, float]:
    if not names:
        return {"attributes": 0.0, "n_undetermined": 0, "n": 0}
    undetermined = [
        name for name in names
        if (contracts.get(name) or {}).get("kind", "workload_undetermined") == "workload_undetermined"
    ]
    return {
        "attributes": len(undetermined) / len(names),
        "n_undetermined": len(undetermined),
        "n": len(names),
        "names": undetermined,
    }

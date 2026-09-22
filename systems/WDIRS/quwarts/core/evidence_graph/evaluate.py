"""Deterministic graph-to-observable evaluation. No further model calls."""

from __future__ import annotations

import re
from typing import Any

from quwarts.core.evidence_graph.graph import competing_by_attribute

STATUS_CANON = {
    "company": "Company",
    "organization": "Organization",
    "organisation": "Organization",
    "government": "Government",
}
CASE_TYPE_CANON = {
    "administrative case": "Administrative Case",
    "civil case": "Civil Case",
    "commercial case": "Commercial Case",
    "criminal case": "Criminal Case",
}
VERDICT_CANON = {
    "dismissed": "Dismissed",
    "approved": "Approved",
    "others": "Others",
    "guilty": "Guilty",
    "not guilty": "Not Guilty",
}


def _num(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    if "." in match.group():
        return float(match.group())
    return int(match.group())


def _label(value: Any, table: dict[str, str]) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return table.get(text.lower(), text)


def _facts_for(facts: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [fact for fact in facts if name in fact.get("attribute_candidates", [])]


def _reject_numeric_identity(name: str, fact: dict[str, Any]) -> bool:
    if fact.get("component_role") in {"citation_id", "list_index"}:
        return True
    if name == "case_number" and fact.get("entity_role") == "statute":
        return True
    if name == "legal_basis_num" and fact.get("entity_role") == "precedent":
        return True
    if name == "hearing_year" and fact.get("temporal_role") not in {"", "hearing"}:
        return True
    if name == "first_judge" and fact.get("component_role") == "list_index":
        return True
    if name == "first_judge" and fact.get("value_type") in {"integer", "year"} and fact.get("entity_role") != "judge":
        if fact.get("component_role") != "indicator":
            return True
    return False


def select_value(facts: list[dict[str, Any]], name: str, want: str) -> tuple[Any, list[str], str]:
    rows = [fact for fact in _facts_for(facts, name) if not _reject_numeric_identity(name, fact)]
    if not rows:
        return None, [], "unresolved"
    usable = []
    for fact in rows:
        if want == "numeric":
            if fact.get("value_type") not in {"integer", "decimal", "year"} and _num(fact.get("normalized_value")) is None:
                continue
            if name in {"case_number", "legal_basis_num"} and fact.get("component_role") not in {"", "count", "total"}:
                continue
            number = _num(fact.get("normalized_value"))
            if number is None:
                continue
            usable.append((number, fact))
        elif want == "year":
            if fact.get("temporal_role") not in {"", "hearing"}:
                continue
            number = _num(fact.get("normalized_value"))
            if number is None or number < 1800 or number > 2100:
                continue
            usable.append((int(number), fact))
        elif want == "label":
            value = fact.get("normalized_value") or fact.get("raw_value")
            if value in (None, ""):
                continue
            usable.append((str(value).strip(), fact))
        elif want == "presence":
            usable.append((True, fact))
        elif want == "entity":
            if fact.get("component_role") == "list_index":
                continue
            value = fact.get("normalized_value") or fact.get("raw_value")
            if value in (None, ""):
                continue
            if re.fullmatch(r"\d+", str(value).strip()) and fact.get("entity_role") != "judge" and fact.get("component_role") != "indicator":
                continue
            usable.append((str(value).strip(), fact))
        else:
            value = fact.get("normalized_value") or fact.get("raw_value")
            if value in (None, ""):
                continue
            usable.append((value, fact))
    if not usable:
        return None, [], "unresolved"
    distinct = {str(value) for value, _fact in usable}
    if len(distinct) > 1:
        return None, [fact["fact_id"] for _value, fact in usable], "unresolved_conflict"
    value, fact = usable[0]
    return value, [item["fact_id"] for _value, item in usable], "resolved"


def _presence(facts: list[dict[str, Any]], name: str, coverage: str) -> dict[str, Any]:
    value, ids, state = select_value(facts, name, "presence")
    if state == "resolved":
        return _decision("RESOLVED", True, ids, "presence_true")
    if coverage != "whole_document":
        return _decision("UNRESOLVED", None, [], "absence_from_pack_unresolved")
    return _decision("UNRESOLVED", None, [], "no_not_found_facts")


def _nonempty(facts: list[dict[str, Any]], name: str) -> dict[str, Any]:
    value, ids, state = select_value(facts, name, "label")
    if state != "resolved":
        return _decision("UNRESOLVED", None, ids, state)
    text = str(value).strip()
    if not text:
        return _decision("RESOLVED", False, ids, "empty_status")
    return _decision("RESOLVED", True, ids, "nonempty_status")


def _decision(state: str, value: Any, fact_ids: list[str], reason: str) -> dict[str, Any]:
    return {
        "state": state,
        "value": value,
        "sql_null": state == "RESOLVED" and value is None,
        "fact_ids": list(dict.fromkeys(fact_ids)),
        "reason": reason,
    }


def evaluate_observables(facts: list[dict[str, Any]], observables: list[dict[str, Any]], coverage: str) -> list[dict[str, Any]]:
    grouped = competing_by_attribute(facts)
    out = []
    for item in observables:
        decision = evaluate_one(facts, item, coverage)
        decision.update(
            {
                "observable_id": item["observable_id"],
                "attribute": item["attribute"],
                "kind": item["kind"],
                "role": item["role"],
                "expression": item["expression"],
                "query_ids": item.get("query_ids") or [],
                "raw_occurrences": item.get("raw_occurrences") or 0,
                "available_facts": [fact["fact_id"] for fact in grouped.get(item["attribute"], [])],
            }
        )
        out.append(decision)
    return out


def evaluate_one(facts: list[dict[str, Any]], item: dict[str, Any], coverage: str) -> dict[str, Any]:
    name = item["attribute"]
    kind = item["kind"]
    role = item["role"]
    if kind == "presence" and role == "is_not_null":
        return _presence(facts, name, coverage)
    if kind == "presence" and role == "nonempty":
        return _nonempty(facts, name)
    if kind == "numeric":
        value, ids, state = select_value(facts, name, "numeric" if name != "hearing_year" else "year")
        if state != "resolved":
            return _decision("UNRESOLVED", None, ids, state)
        return _decision("RESOLVED", value, ids, "numeric_contribution")
    if name == "hearing_year":
        value, ids, state = select_value(facts, name, "year")
        if state != "resolved":
            return _decision("UNRESOLVED", None, ids, state)
        year = int(value)
        if kind == "group":
            return _decision("RESOLVED", year, ids, "hearing_year_group")
        if "2006" in item["expression"] and "2008" in item["expression"]:
            return _decision("RESOLVED", 2006 <= year <= 2008, ids, "hearing_year_filter")
        if "2005" in item["expression"] and "2009" in item["expression"]:
            return _decision("RESOLVED", 2005 <= year <= 2009, ids, "hearing_year_filter")
        return _decision("UNRESOLVED", None, ids, "unknown_hearing_predicate")
    if name == "case_number" and kind == "group":
        value, ids, state = select_value(facts, name, "numeric")
        if state != "resolved":
            return _decision("UNRESOLVED", None, ids, state)
        number = int(value)
        if ">= 8" in item["expression"] or ">=8" in item["match_sql"]:
            label = "precedent_heavy" if number >= 8 else "precedent_light"
        else:
            label = "many_precedents" if number >= 10 else "fewer_precedents"
        return _decision("RESOLVED", label, ids, "case_number_branch")
    if name == "legal_basis_num" and kind == "group":
        value, ids, state = select_value(facts, name, "numeric")
        if state != "resolved":
            return _decision("UNRESOLVED", None, ids, state)
        number = int(value)
        label = "0_or_1" if number <= 1 else ("2_or_3" if number <= 3 else "4_or_more")
        return _decision("RESOLVED", label, ids, "legal_basis_branch")
    if name == "case_type":
        value, ids, state = select_value(facts, name, "label")
        if state != "resolved":
            return _decision("UNRESOLVED", None, ids, state)
        label = _label(value, CASE_TYPE_CANON) or str(value)
        if kind == "predicate":
            return _decision("RESOLVED", label == "Civil Case", ids, "case_type_filter")
        known = {"Administrative Case", "Civil Case", "Commercial Case"}
        return _decision("RESOLVED", label if label in known else "Other", ids, "case_type_branch")
    if name in {"plaintiff_current_status", "defendant_current_status"}:
        value, ids, state = select_value(facts, name, "label")
        if state != "resolved":
            return _decision("UNRESOLVED", None, ids, state)
        canon = _label(value, STATUS_CANON) or str(value).strip()
        nonempty = bool(canon)
        if kind == "presence":
            return _decision("RESOLVED", nonempty, ids, "status_nonempty")
        if "IN ('Company', 'Organization', 'Government')" in item["expression"] or "in ('company', 'organization', 'government')" in item["match_sql"]:
            return _decision("RESOLVED", canon in {"Company", "Organization", "Government"}, ids, "status_in_filter")
        if "= 'Government'" in item["expression"] or "= 'government'" in item["match_sql"]:
            return _decision("RESOLVED", canon == "Government", ids, "status_eq_filter")
        if "= 'Company'" in item["expression"] or "= 'company'" in item["match_sql"]:
            return _decision("RESOLVED", canon == "Company", ids, "status_eq_filter")
        if name == "plaintiff_current_status":
            known = {"Company", "Organization", "Government"}
            label = canon if canon in known else ("Individual_or_other" if nonempty else None)
        else:
            known = {"Government", "Company", "Organization"}
            label = canon if canon in known else ("Other" if nonempty else None)
        if label is None:
            return _decision("RESOLVED", None, ids, "sql_null_empty_status")
        return _decision("RESOLVED", label, ids, "status_branch")
    if name == "verdict":
        value, ids, state = select_value(facts, name, "label")
        if state != "resolved":
            return _decision("UNRESOLVED", None, ids, state)
        label = _label(value, VERDICT_CANON) or str(value)
        if "= 'Dismissed'" in item["expression"] or "= 'dismissed'" in item["match_sql"]:
            return _decision("RESOLVED", label == "Dismissed", ids, "verdict_dismissed")
        if "= 'Approved'" in item["expression"] or "= 'approved'" in item["match_sql"]:
            return _decision("RESOLVED", label == "Approved", ids, "verdict_approved")
        known = {"Dismissed", "Approved", "Others"}
        return _decision("RESOLVED", label if label in known else "Other", ids, "verdict_branch")
    if name == "first_judge":
        if kind == "presence":
            return _presence(facts, name, coverage)
        value, ids, state = select_value(facts, name, "entity")
        if state != "resolved":
            return _decision("UNRESOLVED", None, ids, state)
        return _decision("RESOLVED", str(value), ids, "first_judge_group")
    return _decision("UNRESOLVED", None, [], "unsupported_observable")


def reuse_stats(traces: list[dict[str, Any]]) -> dict[str, Any]:
    support: dict[str, set[str]] = {}
    for row in traces:
        if row.get("state") != "RESOLVED":
            continue
        for fact_id in row.get("fact_ids") or []:
            support.setdefault(fact_id, set()).add(row["observable_id"])
    if not support:
        return {"resolved_facts": 0, "reused_facts": 0, "reuse_fraction": 0.0, "fact_to_observables": {}}
    reused = sum(1 for ids in support.values() if len(ids) >= 2)
    return {
        "resolved_facts": len(support),
        "reused_facts": reused,
        "reuse_fraction": reused / len(support),
        "fact_to_observables": {key: sorted(value) for key, value in support.items()},
    }

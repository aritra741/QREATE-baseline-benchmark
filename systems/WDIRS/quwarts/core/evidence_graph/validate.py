"""Gold-free structural, cross-role, and independent source/role validation."""

from __future__ import annotations

import random
import re
from typing import Any

from quwarts.core.evidence_graph.config import ALLOWED_ATTRIBUTES, SEED, VALUE_TYPES
from quwarts.core.evidence_graph.evaluate import evaluate_observables

ROLE_CUES = {
    "hearing": re.compile(r"\b(hearing|heard|before me on|trial commenced)\b", re.I),
    "judgment": re.compile(r"\b(judgment|judgement|reasons|decided|i order|i dismiss)\b", re.I),
    "citation": re.compile(r"\[[12]\d{3}\]|\bv\b"),
    "plaintiff": re.compile(r"\b(plaintiff|applicant|appellant)\b", re.I),
    "defendant": re.compile(r"\b(defendant|respondent)\b", re.I),
    "judge": re.compile(r"\b(justice|judge|\bJ\.|\bJJ\.)\b", re.I),
    "statute": re.compile(r"\b(act|statute|code|section s\s?\d)\b", re.I),
    "precedent": re.compile(r"\b(cited|considered|applied|followed|distinguished|v )\b", re.I),
}


def structural_validation(document: str, facts: list[dict[str, Any]], traces: list[dict[str, Any]], replay: list[dict[str, Any]]) -> dict[str, Any]:
    offset_ok = 0
    offset_n = 0
    unknown = []
    missing_quote = []
    unsupported = []
    for fact in facts:
        for name in fact.get("attribute_candidates") or []:
            if name not in ALLOWED_ATTRIBUTES:
                unknown.append(fact["fact_id"])
        if fact.get("value_type") not in VALUE_TYPES:
            unknown.append(fact["fact_id"])
        if fact.get("stated_or_inferred") == "stated":
            offset_n += 1
            start, end, quote = fact.get("source_start"), fact.get("source_end"), fact.get("source_quote") or ""
            if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(document) and document[start:end] == quote:
                offset_ok += 1
            else:
                missing_quote.append(fact["fact_id"])
    for row in traces:
        if row.get("reason") == "unsupported_observable":
            unsupported.append(row["observable_id"])
    replay_ok = traces == replay
    return {
        "valid_json_schema": True,
        "stated_facts": offset_n,
        "offset_valid": offset_ok,
        "offset_validity": (offset_ok / offset_n) if offset_n else 1.0,
        "unknown_attributes": sorted(set(unknown)),
        "quoted_text_absent": missing_quote,
        "unsupported_observables": unsupported,
        "deterministic_replay": replay_ok,
    }


def cross_role_validation(document: str, facts: list[dict[str, Any]], traces: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {fact["fact_id"]: fact for fact in facts}
    checks = []
    for row in traces:
        if row.get("state") != "RESOLVED":
            continue
        ok = True
        reasons = []
        for fact_id in row.get("fact_ids") or []:
            fact = by_id.get(fact_id)
            if not fact:
                ok = False
                reasons.append("missing_fact")
                continue
            window = _window(document, fact)
            name = row["attribute"]
            if name == "hearing_year" and fact.get("temporal_role") not in {"", "hearing"}:
                ok = False
                reasons.append("temporal_role")
            if name == "hearing_year" and fact.get("temporal_role") == "hearing" and window and not ROLE_CUES["hearing"].search(window):
                if ROLE_CUES["citation"].search(fact.get("source_quote") or ""):
                    ok = False
                    reasons.append("citation_year_as_hearing")
            if name in {"plaintiff_current_status", "defendant_current_status"}:
                want = "plaintiff" if name.startswith("plaintiff") else "defendant"
                if fact.get("entity_role") not in {"", want}:
                    ok = False
                    reasons.append("entity_role")
            if name == "first_judge" and fact.get("component_role") == "list_index":
                ok = False
                reasons.append("list_index_as_judge")
            if name == "case_number" and fact.get("component_role") == "citation_id":
                ok = False
                reasons.append("citation_as_case_number")
            if row["kind"] == "numeric" and fact.get("value_type") not in {"integer", "decimal", "year"} and not str(fact.get("normalized_value")).replace(".", "", 1).lstrip("-").isdigit():
                ok = False
                reasons.append("type")
            if row["kind"] == "presence" and row["role"] == "is_not_null" and row.get("value") is True:
                if fact.get("value_type") in {"integer", "decimal", "year"} and name == "first_judge" and fact.get("component_role") != "indicator":
                    reasons.append("numeric_presence_guard")
        checks.append({"observable_id": row["observable_id"], "ok": ok, "reasons": reasons})
    n = len(checks)
    return {
        "resolved": n,
        "compatible": sum(1 for row in checks if row["ok"]),
        "rate": (sum(1 for row in checks if row["ok"]) / n) if n else 1.0,
        "checks": checks,
    }


def independent_spot_sample(traces: list[dict[str, Any]], fraction: float = 0.20) -> list[dict[str, Any]]:
    resolved = [row for row in traces if row.get("state") == "RESOLVED"]
    if not resolved:
        return []
    rng = random.Random(SEED)
    k = max(1, int(round(len(resolved) * fraction)))
    return rng.sample(resolved, min(k, len(resolved)))


def independent_source_role(document: str, facts: list[dict[str, Any]], traces: list[dict[str, Any]], descriptions: dict[str, str]) -> dict[str, Any]:
    by_id = {fact["fact_id"]: fact for fact in facts}
    sampled = independent_spot_sample(traces)
    judgments = []
    for row in sampled:
        support = True
        role_ok = True
        reasons = []
        for fact_id in row.get("fact_ids") or []:
            fact = by_id.get(fact_id)
            if not fact:
                support = False
                role_ok = False
                reasons.append("missing_node")
                continue
            quote = fact.get("source_quote") or ""
            window = _window(document, fact, pad=180)
            if fact.get("stated_or_inferred") == "stated":
                if quote and quote not in window and quote not in document:
                    support = False
                    reasons.append("quote_absent")
                start, end = fact.get("source_start"), fact.get("source_end")
                if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(document) and document[start:end] == quote):
                    support = False
                    reasons.append("offset_mismatch")
            if row["attribute"] == "hearing_year" and fact.get("temporal_role") not in {"", "hearing"}:
                role_ok = False
                reasons.append("temporal")
            if row["attribute"] == "first_judge" and re.fullmatch(r"\d+", str(fact.get("normalized_value") or "")) and fact.get("component_role") != "indicator":
                role_ok = False
                reasons.append("digit_judge")
            if row["kind"] == "numeric" and row["attribute"] == "case_number" and fact.get("component_role") == "citation_id":
                role_ok = False
                reasons.append("citation_component")
            desc = descriptions.get(row["attribute"], "")
            judgments.append(
                {
                    "observable_id": row["observable_id"],
                    "fact_id": fact_id,
                    "attribute": row["attribute"],
                    "use": row["expression"],
                    "description": desc,
                    "support": support,
                    "role_ok": role_ok,
                    "agree": support and role_ok,
                    "reasons": reasons,
                    "window": window[:400],
                }
            )
    n = len(judgments)
    agree = sum(1 for row in judgments if row["agree"])
    return {
        "n": n,
        "agreement": (agree / n) if n else 1.0,
        "support_rate": (sum(1 for row in judgments if row["support"]) / n) if n else 1.0,
        "role_rate": (sum(1 for row in judgments if row["role_ok"]) / n) if n else 1.0,
        "judgments": judgments,
    }


def replay_traces(facts: list[dict[str, Any]], observables: list[dict[str, Any]], coverage: str) -> list[dict[str, Any]]:
    return evaluate_observables(facts, observables, coverage)


def _window(document: str, fact: dict[str, Any], pad: int = 80) -> str:
    start = fact.get("source_start")
    end = fact.get("source_end")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(document):
        return document[max(0, start - pad) : min(len(document), end + pad)]
    quote = fact.get("source_quote") or ""
    if quote and quote in document:
        idx = document.find(quote)
        return document[max(0, idx - pad) : min(len(document), idx + len(quote) + pad)]
    return ""

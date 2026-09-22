"""One deterministic specification executor. No attribute-name branches."""

from __future__ import annotations

from typing import Any

from quwarts.core.amortized_select.dsl import TERM_FIELDS


def _hay(feat: dict[str, Any], field: str) -> str:
    key = {"section_title": "section_title", "row_label": "row_label", "column_header": "column_header", "table_title": "table_title"}[field]
    return str(feat.get(key) or "").lower()


def _has_term(text: str, term: str) -> bool:
    blob = f" {text} "
    token = str(term or "").strip().lower()
    return bool(token) and token in blob


def _period_key(feat: dict[str, Any]) -> int:
    raw = str(feat.get("period") or "")
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits[:4]) if len(digits) >= 4 else -1


def hard_reject(feat: dict[str, Any], spec: dict[str, Any]) -> str | None:
    for field in TERM_FIELDS:
        text = _hay(feat, field)
        for term in spec["rejected_metadata_terms"][field]:
            if _has_term(text, term):
                return f"rejected_{field}"
    form = spec["value_form"]
    shape = feat.get("value_shape")
    if form == "number" and shape not in {"number", "percent"}:
        return "non_numeric"
    if form == "percent" or spec["unit_policy"] == "percent":
        if shape != "percent" and "%" not in str(feat.get("raw_span") or "") and "percent" not in str(feat.get("unit") or "").lower():
            if form == "number" and spec["unit_policy"] == "percent":
                return "not_percent"
    if form == "short_code" and shape not in {"short_code"}:
        return "not_short_code"
    if form == "full_legal_name" and shape == "short_code":
        return "abbreviation"
    scope = spec["scope_policy"]
    role = feat.get("scope_role")
    if scope == "total" and role in {"segment", "component"}:
        return "not_total"
    if scope == "consolidated" and role not in {"consolidated", "total"}:
        return "not_consolidated"
    if scope == "component" and role in {"total", "consolidated"}:
        return "not_component"
    return None


def _preferred_score(feat: dict[str, Any], spec: dict[str, Any]) -> int:
    score = 0
    for field in TERM_FIELDS:
        text = _hay(feat, field)
        for term in spec["preferred_metadata_terms"][field]:
            if _has_term(text, term):
                score += 1
    return score


def _scope_score(feat: dict[str, Any], spec: dict[str, Any]) -> int:
    scope = spec["scope_policy"]
    role = feat.get("scope_role")
    if scope == "any":
        return 0
    return int(role == scope or (scope == "total" and role in {"total", "consolidated"}))


def _period_score(feat: dict[str, Any], spec: dict[str, Any], latest: int) -> int:
    policy = spec["period_policy"]
    year = _period_key(feat)
    if policy == "any":
        return 0
    if policy in {"latest", "period_end", "reporting_period"}:
        if year < 0:
            return 0
        return int(year == latest) if latest > 0 else 1
    return 0


def _unit_score(feat: dict[str, Any], spec: dict[str, Any]) -> int:
    policy = spec["unit_policy"]
    if policy == "any":
        return 0
    unit = str(feat.get("unit") or "").lower()
    if policy == "percent":
        return int("percent" in unit or feat.get("value_shape") == "percent")
    if policy == "resolve_from_header":
        return int(bool(unit))
    return 0


def _form_score(feat: dict[str, Any], spec: dict[str, Any]) -> int:
    return int(feat.get("value_shape") == spec["value_form"] or spec["value_form"] in {"text", "categorical"})


def _pos_score(feat: dict[str, Any]) -> int:
    return {"early": 2, "middle": 1, "late": 0}.get(str(feat.get("document_position")), 0)


def _source_score(feat: dict[str, Any]) -> int:
    return int(feat.get("source_type") == "table")


def compare_key(feat: dict[str, Any], spec: dict[str, Any], latest: int) -> tuple:
    order = spec.get("tie_break_order") or ["preferred_metadata", "scope", "period", "lexical_similarity"]
    mapping = {
        "preferred_metadata": _preferred_score(feat, spec),
        "scope": _scope_score(feat, spec),
        "period": _period_score(feat, spec, latest),
        "unit": _unit_score(feat, spec),
        "value_form": _form_score(feat, spec),
        "lexical_similarity": float(feat.get("lexical", {}).get("max") or 0.0),
        "occurrence_count": int(feat.get("occurrence_count") or 0),
        "document_position": _pos_score(feat),
        "source_type": _source_score(feat),
    }
    return tuple(mapping[name] for name in order if name in mapping)


def execute_cell(spec: dict[str, Any], feats: list[dict[str, Any]]) -> dict[str, Any]:
    rejected = []
    survivors = []
    for feat in feats:
        reason = hard_reject(feat, spec)
        if reason:
            rejected.append({"id": feat.get("id"), "reason": reason})
        else:
            survivors.append(feat)
    if not survivors:
        return {
            "status": "abstain",
            "candidate_ids": [],
            "reason": "all_rejected" if rejected else "empty",
            "rejected": rejected,
            "survivors": [],
            "tie": False,
        }
    latest = max((_period_key(item) for item in survivors), default=-1)
    ranked = sorted(survivors, key=lambda item: (compare_key(item, spec, latest), -int(item.get("start") or 0)), reverse=True)
    best = compare_key(ranked[0], spec, latest)
    winners = [item for item in ranked if compare_key(item, spec, latest) == best]
    if len(winners) != 1:
        if spec.get("abstain_on_conflict", True):
            return {
                "status": "abstain",
                "candidate_ids": [item.get("id") for item in winners],
                "reason": "tie_or_conflict",
                "rejected": rejected,
                "survivors": [item.get("id") for item in survivors],
                "tie": True,
                "winning_criteria": list(spec.get("tie_break_order") or []),
            }
    chosen = winners[0]
    return {
        "status": "selected",
        "candidate_ids": [chosen.get("id")],
        "reason": None,
        "rejected": rejected,
        "survivors": [item.get("id") for item in survivors],
        "tie": False,
        "winning_criteria": {
            "preferred": _preferred_score(chosen, spec),
            "scope": chosen.get("scope_role"),
            "period": chosen.get("period"),
            "lexical": chosen.get("lexical", {}).get("max"),
        },
    }

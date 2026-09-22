"""Safe selection-program DSL. Rejects leakage, code, and document-specific terms."""

from __future__ import annotations

import json
import re
from typing import Any

from quwarts.core.amortized_select.config import (
    ALLOWED_OPS,
    ALLOWED_PERIOD,
    ALLOWED_SCOPE,
    ALLOWED_TASK_CLASS,
    ALLOWED_TIE_BREAK,
    ALLOWED_UNIT,
    ALLOWED_VALUE_FORM,
    GENERIC_VOCAB,
)
from quwarts.core.shared_bundle.context_blocks import tokens_of
from quwarts.experiments.extract_util import field_terms

TERM_FIELDS = ("row_label", "column_header", "table_title", "section_title")
_CODE_OR_VALUE = re.compile(r"^(?:C\d+|-?\d[\d,]*\.?\d*%?)$")
_FORBIDDEN = re.compile(r"\b(import|def |lambda |re\.|select |where |case |python|regex)\b", re.I)


def _tokens(text: str) -> list[str]:
    return [tok for tok in field_terms(text or "") + tokens_of(text or "") if tok and len(tok) > 1]


def empty_spec(name: str, task_class: str) -> dict[str, Any]:
    return {
        "attribute": name,
        "task_class": "categorical" if task_class == "classification" else "extractive",
        "preferred_metadata_terms": {field: [] for field in TERM_FIELDS},
        "rejected_metadata_terms": {field: [] for field in TERM_FIELDS},
        "period_policy": "reporting_period",
        "scope_policy": "any",
        "unit_policy": "any",
        "value_form": "categorical" if task_class == "classification" else "number",
        "allowed_operations": ["identity"],
        "tie_break_order": ["preferred_metadata", "scope", "period", "lexical_similarity"],
        "abstain_on_conflict": True,
    }


def allowed_term_bank(
    description: str,
    name: str,
    sample_feats: list[list[dict[str, Any]]],
) -> set[str]:
    bank = set(GENERIC_VOCAB)
    bank.update(_tokens(description))
    bank.update(_tokens(name.replace("_", " ")))
    field_df: dict[str, set[int]] = {}
    for doc_i, feats in enumerate(sample_feats):
        seen: set[str] = set()
        for item in feats:
            for field in TERM_FIELDS:
                key = "section_title" if field == "section_title" else field
                src = item.get(key) or item.get("heading") or ""
                for tok in _tokens(str(src)):
                    seen.add(tok)
        for tok in seen:
            field_df.setdefault(tok, set()).add(doc_i)
    for tok, docs in field_df.items():
        if len(docs) >= 2:
            bank.add(tok)
    return bank


def _clean_terms(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    out = []
    for item in values:
        text = str(item or "").strip().lower()
        if text:
            out.append(text)
    return list(dict.fromkeys(out))


def normalize_spec(raw: dict[str, Any], name: str, task_class: str) -> dict[str, Any]:
    base = empty_spec(name, task_class)
    if not isinstance(raw, dict):
        return base
    spec = dict(base)
    spec["attribute"] = name
    task = str(raw.get("task_class") or spec["task_class"]).strip().lower()
    spec["task_class"] = task if task in ALLOWED_TASK_CLASS else spec["task_class"]
    for group in ("preferred_metadata_terms", "rejected_metadata_terms"):
        blob = raw.get(group) if isinstance(raw.get(group), dict) else {}
        spec[group] = {field: _clean_terms(blob.get(field)) for field in TERM_FIELDS}
    period = str(raw.get("period_policy") or spec["period_policy"]).strip()
    spec["period_policy"] = period if period in ALLOWED_PERIOD else "any"
    scope = str(raw.get("scope_policy") or spec["scope_policy"]).strip()
    spec["scope_policy"] = scope if scope in ALLOWED_SCOPE else "any"
    unit = str(raw.get("unit_policy") or spec["unit_policy"]).strip()
    spec["unit_policy"] = unit if unit in ALLOWED_UNIT else "any"
    form = str(raw.get("value_form") or spec["value_form"]).strip()
    spec["value_form"] = form if form in ALLOWED_VALUE_FORM else spec["value_form"]
    ops = raw.get("allowed_operations") if isinstance(raw.get("allowed_operations"), list) else ["identity"]
    spec["allowed_operations"] = [str(op) for op in ops if str(op) in ALLOWED_OPS] or ["identity"]
    ties = raw.get("tie_break_order") if isinstance(raw.get("tie_break_order"), list) else spec["tie_break_order"]
    spec["tie_break_order"] = [str(item) for item in ties if str(item) in ALLOWED_TIE_BREAK]
    spec["abstain_on_conflict"] = bool(raw.get("abstain_on_conflict", True))
    return spec


def term_tokens(spec: dict[str, Any]) -> list[str]:
    out = []
    for group in ("preferred_metadata_terms", "rejected_metadata_terms"):
        for field in TERM_FIELDS:
            for term in spec[group][field]:
                out.extend(_tokens(term) or [term])
    return out


def validate_spec(
    spec: dict[str, Any],
    *,
    name: str,
    description: str,
    bank: set[str],
    literals: list[str],
    entity_names: list[str],
) -> list[str]:
    errors = []
    dumped = json.dumps(spec)
    if _FORBIDDEN.search(dumped):
        errors.append("forbidden_code_or_sql")
    if spec.get("attribute") not in {name, ""}:
        errors.append("attribute_mismatch")
    if spec.get("task_class") not in ALLOWED_TASK_CLASS:
        errors.append("bad_task_class")
    for term in term_tokens(spec):
        if _CODE_OR_VALUE.match(term):
            errors.append(f"numeric_or_candidate_id:{term}")
            continue
        if term not in bank and term.replace("_", "") not in bank:
            errors.append(f"untraceable_term:{term}")
    for lit in literals:
        bare = str(lit).strip()
        if len(bare) < 3:
            continue
        if bare.lower() in dumped.lower() and bare.lower() not in description.lower():
            errors.append(f"predicate_literal:{bare}")
    for entity in entity_names:
        token = str(entity or "").strip()
        if len(token) >= 4 and token.lower() in dumped.lower():
            errors.append("entity_name_leak")
            break
    return list(dict.fromkeys(errors))


def restore_schema_policy(spec: dict[str, Any], *, description: str, allows_sum: bool, unit_percent: bool, domain: list[str]) -> dict[str, Any]:
    text = (description or "").lower()
    out = json.loads(json.dumps(spec))
    if "total" in text and out["scope_policy"] in {"component", "entity_level"}:
        out["scope_policy"] = "total"
    if "consolidated" in text:
        out["scope_policy"] = "consolidated"
    if "period" in text or "reporting" in text:
        if out["period_policy"] == "any":
            out["period_policy"] = "reporting_period"
    if "end of the reporting period" in text or "period-end" in text or "period end" in text:
        out["period_policy"] = "period_end"
    if unit_percent:
        out["unit_policy"] = "percent"
        out["value_form"] = "number"
    if "full legal name" in text:
        out["value_form"] = "full_legal_name"
    if "code" in text and "exchange" in text:
        out["value_form"] = "short_code"
    if domain:
        out["task_class"] = "categorical"
        out["value_form"] = "categorical"
    if not allows_sum:
        out["allowed_operations"] = ["identity"]
    return out


def apply_critic_fixes(
    spec: dict[str, Any],
    critic: dict[str, Any],
    *,
    bank: set[str],
    description: str,
    allows_sum: bool,
    unit_percent: bool,
    domain: list[str],
) -> dict[str, Any]:
    out = restore_schema_policy(spec, description=description, allows_sum=allows_sum, unit_percent=unit_percent, domain=domain)
    invalid = critic.get("invalid_terms") if isinstance(critic.get("invalid_terms"), list) else []
    drop = {str(item).strip().lower() for item in invalid if item}
    for group in ("preferred_metadata_terms", "rejected_metadata_terms"):
        for field in TERM_FIELDS:
            kept = []
            for term in out[group][field]:
                toks = _tokens(term) or [term]
                if any(tok in drop or tok not in bank for tok in toks):
                    continue
                kept.append(term)
            out[group][field] = kept
    if str(critic.get("unresolved_contradiction") or "").strip().lower() in {"true", "yes", "unresolved"}:
        out["abstain_on_conflict"] = True
    if str(critic.get("component_vs_total") or "").lower().find("total") >= 0:
        out["scope_policy"] = "total"
    if str(critic.get("name_vs_code") or "").lower().find("full") >= 0:
        out["value_form"] = "full_legal_name"
    if str(critic.get("period_ambiguity") or "").strip():
        out["abstain_on_conflict"] = True
    if str(critic.get("unit_ambiguity") or "").strip() and unit_percent:
        out["unit_policy"] = "percent"
    return out

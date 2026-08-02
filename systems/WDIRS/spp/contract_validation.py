"""Validation and adaptive repair admission for contract extraction.

Validation is evidence-local: a value is accepted only when its own exact span
supports its semantic form and entity identity.  Cross-record checks then
enforce relationship endpoints, units, and conflict visibility.  Repair
admission has no attempt-count cutoff; novelty and the remaining completion
reserve are the stopping conditions.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from spp.workload_contract import (
    AttributeContract,
    RelationshipContract,
    WorkloadContract,
)
from spp.calculation_tools import calculate, operands_are_grounded


@dataclass(frozen=True)
class ValidationIssue:
    """One actionable contract or extraction violation."""

    code: str
    message: str
    severity: str = "error"
    entity: str = ""
    attribute: Optional[str] = None
    document_id: Optional[str] = None
    record_index: Optional[int] = None
    evidence: Optional[str] = None
    relationship: Optional[str] = None

    def __post_init__(self) -> None:
        if self.severity not in {"error", "warning"}:
            raise ValueError("validation severity must be 'error' or 'warning'")
        if not self.code:
            raise ValueError("validation issue requires a code")

    @property
    def fingerprint(self) -> str:
        """Hash the violation shape without retaining source literals."""

        payload = {
            "code": self.code,
            "severity": self.severity,
            "entity": self.entity,
            "attribute": self.attribute,
            "document_id": self.document_id,
            "relationship": self.relationship,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()


def _value(record: object, name: str, default: object = None) -> object:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _symbol_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _text_key(value: object) -> str:
    return " ".join(
        re.findall(r"[a-z0-9]+", str(value or "").lower(), re.UNICODE)
    )


def _issue(
    record: object,
    code: str,
    message: str,
    *,
    severity: str = "error",
    evidence: Optional[str] = None,
) -> ValidationIssue:
    index = _value(record, "record_index")
    return ValidationIssue(
        code=code,
        message=message,
        severity=severity,
        entity=str(_value(record, "entity", "") or ""),
        attribute=(
            str(_value(record, "attribute"))
            if _value(record, "attribute") is not None
            else None
        ),
        document_id=(
            str(_value(record, "document_id"))
            if _value(record, "document_id") is not None
            else None
        ),
        record_index=int(index) if isinstance(index, int) else None,
        evidence=evidence,
        relationship=(
            str(_value(record, "relationship"))
            if _value(record, "relationship") is not None
            else None
        ),
    )


@dataclass(frozen=True)
class RepairTarget:
    """One document-local symbol that can be repaired without re-extraction."""

    phase: str
    document_id: str
    entity: str = ""
    attribute: Optional[str] = None
    relationship: Optional[str] = None
    issue_codes: Tuple[str, ...] = ()
    record_indexes: Tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.phase not in {"entity", "attribute", "relationship"}:
            raise ValueError(f"unsupported repair phase: {self.phase}")
        if not self.document_id:
            raise ValueError("repair target requires a document_id")


def _decimal(value: object) -> Optional[Decimal]:
    if isinstance(value, bool) or value is None:
        return None
    rendered = str(value).strip().replace(",", "")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", rendered):
        return None
    try:
        candidate = Decimal(rendered)
    except InvalidOperation:
        return None
    return candidate if candidate.is_finite() else None


def _date_key(value: object) -> Optional[Tuple[int, Optional[int], Optional[int]]]:
    rendered = str(value or "").strip()
    if re.fullmatch(r"\d{4}", rendered):
        return int(rendered), None, None
    normalized = rendered.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.year, parsed.month, parsed.day
    except ValueError:
        pass
    for pattern in (
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
    ):
        try:
            parsed = datetime.strptime(rendered, pattern)
            return parsed.year, parsed.month, parsed.day
        except ValueError:
            continue
    return None


def _date_candidates(span: str) -> Set[Tuple[int, Optional[int], Optional[int]]]:
    candidates: Set[Tuple[int, Optional[int], Optional[int]]] = set()
    patterns = (
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
        r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
        r"\d{1,2},?\s+\d{4}\b",
        r"\b\d{4}\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, span, re.IGNORECASE):
            key = _date_key(match.group(0).replace(",", ","))
            if key is not None:
                candidates.add(key)
    return candidates


def _type_matches(value: object, semantic_type: str) -> bool:
    if semantic_type == "text":
        return isinstance(value, str) and bool(value.strip())
    if semantic_type == "integer":
        number = _decimal(value)
        return number is not None and number == number.to_integral_value()
    if semantic_type == "real":
        return _decimal(value) is not None
    if semantic_type == "date":
        return _date_key(value) is not None
    if semantic_type == "boolean":
        if isinstance(value, bool):
            return True
        return str(value).strip().lower() in {
            "true",
            "false",
            "yes",
            "no",
        }
    return False


def _grounded_in_span(
    value: object, span: str, semantic_types: Sequence[str]
) -> bool:
    for semantic_type in semantic_types or ("text",):
        if not _type_matches(value, semantic_type):
            continue
        if semantic_type == "text":
            value_key = _text_key(value)
            if value_key and value_key in _text_key(span):
                return True
        elif semantic_type in {"integer", "real"}:
            expected = _decimal(value)
            for match in re.finditer(
                r"(?<![\w.])[+-]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?![\w.])",
                span,
            ):
                if _decimal(match.group(0)) == expected:
                    return True
            number_words = {
                "zero": 0,
                "one": 1,
                "two": 2,
                "three": 3,
                "four": 4,
                "five": 5,
                "six": 6,
                "seven": 7,
                "eight": 8,
                "nine": 9,
                "ten": 10,
                "first": 1,
                "second": 2,
                "third": 3,
                "fourth": 4,
                "fifth": 5,
                "sixth": 6,
                "seventh": 7,
                "eighth": 8,
                "ninth": 9,
                "tenth": 10,
                "single": 1,
            }
            if expected is not None and any(
                _decimal(number) == expected
                for token, number in number_words.items()
                if re.search(rf"\b{token}\b", span, re.IGNORECASE)
            ):
                return True
        elif semantic_type == "date":
            expected_date = _date_key(value)
            if expected_date in _date_candidates(span):
                return True
        elif semantic_type == "boolean":
            expected = str(value).strip().lower()
            equivalents = {
                "true": {"true", "yes"},
                "yes": {"true", "yes"},
                "false": {"false", "no"},
                "no": {"false", "no"},
            }.get(expected, {expected})
            if any(
                re.search(rf"\b{re.escape(token)}\b", span, re.IGNORECASE)
                for token in equivalents
            ):
                return True
    return False


def _stem_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    return token


def _semantic_attribute_grounded(
    record: object,
    span: str,
    semantic_types: Sequence[str],
) -> bool:
    """Recognize explicit boolean predicates and singular counted events."""

    if _value(record, "derivation_kind") == "tool_calculation":
        inputs = _value(record, "derivation_inputs", {}) or {}
        if isinstance(inputs, Mapping):
            operands = inputs.get("operands")
            source_operands = inputs.get("source_operands")
            if isinstance(operands, list) and isinstance(source_operands, list):
                try:
                    expected = calculate(
                        str(inputs.get("operation")), operands
                    )
                except ValueError:
                    expected = None
                if (
                    expected == _value(record, "value")
                    and operands_are_grounded(
                        operands,
                        source_operands,
                        span,
                        corpus_reference_year=inputs.get(
                            "corpus_reference_year"
                        ),
                    )
                ):
                    return True
    attribute_tokens = [
        _stem_token(token)
        for token in _symbol_key(_value(record, "attribute", "")).split("_")
        if token and token not in {"is", "has"}
    ]
    if not attribute_tokens:
        return False
    span_tokens = {
        _stem_token(token) for token in _text_key(span).split() if token
    }
    overlap = set(attribute_tokens) & span_tokens
    value = _value(record, "value")
    if "boolean" in semantic_types and value is True:
        return bool(overlap)
    numeric = _decimal(value)
    if (
        numeric == Decimal(1)
        and set(semantic_types) & {"integer", "real"}
    ):
        return len(overlap) >= max(1, math.ceil(len(set(attribute_tokens)) / 2))
    return False


def validate_field_local_span(
    record: object,
    source_text: Optional[str],
    *,
    semantic_types: Sequence[str] = (),
) -> Tuple[ValidationIssue, ...]:
    """Validate exact offsets and ensure this field's value occurs in its span."""

    if source_text is None:
        return (
            _issue(
                record,
                "source_document_missing",
                "the record's source document is unavailable",
            ),
        )
    span = _value(record, "exact_span")
    if not isinstance(span, str) or not span:
        return (
            _issue(record, "exact_span_missing", "exact_span must be non-empty"),
        )
    issues: List[ValidationIssue] = []
    start = _value(record, "span_start")
    end = _value(record, "span_end")
    if isinstance(start, int) and isinstance(end, int):
        if (
            start < 0
            or end < start
            or end > len(source_text)
            or source_text[start:end] != span
        ):
            issues.append(
                _issue(
                    record,
                    "exact_span_offsets",
                    "span offsets do not select exact_span in the source",
                    evidence=span,
                )
            )
    elif span not in source_text:
        issues.append(
            _issue(
                record,
                "exact_span_not_in_source",
                "exact_span is not a verbatim source substring",
                evidence=span,
            )
        )
    value = _value(record, "value")
    expected_types = semantic_types or (
        "text",
        "integer",
        "real",
        "date",
        "boolean",
    )
    if (
        value not in (None, "")
        and not _grounded_in_span(value, span, expected_types)
        and not _semantic_attribute_grounded(record, span, expected_types)
    ):
        issues.append(
            _issue(
                record,
                "field_value_not_in_span",
                "the field's value is not locally supported by exact_span",
                evidence=span,
            )
        )
    return tuple(issues)


def validate_semantic_type(
    record: object,
    expected: AttributeContract | Sequence[str] | str,
) -> Tuple[ValidationIssue, ...]:
    """Validate a scalar against every retained semantic-type alternative."""

    if isinstance(expected, AttributeContract):
        semantic_types = expected.semantic_types
    elif isinstance(expected, str):
        semantic_types = (expected,)
    else:
        semantic_types = tuple(expected)
    value = _value(record, "value")
    if any(_type_matches(value, candidate) for candidate in semantic_types):
        return ()
    return (
        _issue(
            record,
            "semantic_type_mismatch",
            f"value does not satisfy semantic type alternatives {semantic_types}",
        ),
    )


def validate_count_date(
    record: object,
    expected: AttributeContract | Sequence[str] | str,
    *,
    count: Optional[bool] = None,
) -> Tuple[ValidationIssue, ...]:
    """Apply strict count and date rules beyond generic scalar typing.

    Count fields must be finite, integral, and non-negative.  Date values must
    parse and have a parse-equivalent form in the field-local span.  A query's
    ``COUNT`` aggregate does not by itself turn its input field into a count;
    automatic count detection is limited to the field symbol.
    """

    if isinstance(expected, AttributeContract):
        semantic_types = expected.semantic_types
        if count is None:
            tokens = set(_symbol_key(expected.name).split("_"))
            count = bool(
                tokens
                & {
                    "count",
                    "number",
                    "quantity",
                    "award",
                    "awards",
                    "championship",
                    "championships",
                    "medal",
                    "medals",
                    "title",
                    "titles",
                    "mvp",
                }
                and set(semantic_types) <= {"integer", "real"}
            )
    elif isinstance(expected, str):
        semantic_types = (expected,)
    else:
        semantic_types = tuple(expected)
    count = bool(count)
    issues: List[ValidationIssue] = []
    value = _value(record, "value")
    span = str(_value(record, "exact_span", "") or "")
    if count:
        numeric = _decimal(value)
        if (
            numeric is None
            or numeric != numeric.to_integral_value()
            or numeric < 0
        ):
            issues.append(
                _issue(
                    record,
                    "invalid_count",
                    "count values must be non-negative integers",
                )
            )
        elif not _grounded_in_span(value, span, ("integer",)):
            issues.append(
                _issue(
                    record,
                    "count_not_in_span",
                    "count is not explicitly supported by exact_span",
                    evidence=span,
                )
            )
        issues.extend(validate_calendar_year_as_count(record))
    if set(semantic_types) == {"date"}:
        date = _date_key(value)
        if date is None:
            issues.append(
                _issue(record, "invalid_date", "date value is not parseable")
            )
        elif date not in _date_candidates(span):
            issues.append(
                _issue(
                    record,
                    "date_not_in_span",
                    "date is not parse-equivalent to a date in exact_span",
                    evidence=span,
                )
            )
    return tuple(issues)


def validate_calendar_year_as_count(
    record: object,
) -> Tuple[ValidationIssue, ...]:
    """Reject a four-digit calendar year misread as an entity count.

    Count-like attributes (awards, championships, medals, titles) reject any
    value in the modern year range. Other count fields still require temporal
    syntax in the local span, or a bare year-only span.
    """

    numeric = _decimal(_value(record, "value"))
    if (
        numeric is None
        or numeric != numeric.to_integral_value()
        or numeric < 1000
        or numeric > 2999
    ):
        return ()
    year = str(int(numeric))
    span = str(_value(record, "exact_span", "") or "")
    attribute_tokens = set(
        _symbol_key(_value(record, "attribute", "")).split("_")
    )
    count_like = bool(
        attribute_tokens
        & {
            "award",
            "awards",
            "championship",
            "championships",
            "medal",
            "medals",
            "title",
            "titles",
            "mvp",
            "won",
        }
    )
    temporal_prefix = re.search(
        rf"\b(?:in|during|since|until|through|from|year|dated|date|"
        rf"calendar|as\s+of)\b(?:\W+\w+){{0,3}}\W+{re.escape(year)}\b",
        span,
        re.IGNORECASE,
    )
    temporal_suffix = re.search(
        rf"\b{re.escape(year)}\b\W*(?:calendar\s+year|year|season|dated)\b",
        span,
        re.IGNORECASE,
    )
    full_date = any(
        candidate[0] == int(numeric)
        and candidate[1] is not None
        and candidate[2] is not None
        for candidate in _date_candidates(span)
    )
    bare_year = bool(
        re.fullmatch(rf"\W*{re.escape(year)}\W*", span.strip())
    )
    if count_like or temporal_prefix or temporal_suffix or full_date or bare_year:
        return (
            _issue(
                record,
                "calendar_year_as_count",
                "a calendar year cannot serve as an entity count",
                evidence=span,
            ),
        )
    return ()


def validate_identity(
    record: object,
    known_identities: Iterable[str] = (),
    *,
    require_span_support: bool = True,
    require_discovered: bool = False,
) -> Tuple[ValidationIssue, ...]:
    """Validate identity presence, entity-first linkage, and local support."""

    identity = str(_value(record, "identity", "") or "").strip()
    if not identity:
        return (
            _issue(record, "identity_missing", "record identity is empty"),
        )
    issues: List[ValidationIssue] = []
    known = {_text_key(value) for value in known_identities if _text_key(value)}
    identity_key = _text_key(identity)
    identity_tokens = {
        token for token in identity_key.split() if len(token) >= 3
    }
    compatible_known = {
        candidate
        for candidate in known
        if identity_tokens
        and (
            set(identity_key.split()) <= set(candidate.split())
            or set(candidate.split()) <= set(identity_key.split())
        )
    }
    if require_discovered and not known:
        issues.append(
            _issue(
                record,
                "identity_not_discovered",
                "attribute identity has no entity-discovery evidence",
                evidence=identity,
            )
        )
    elif (
        known
        and identity_key not in known
        and len(compatible_known) != 1
    ):
        issues.append(
            _issue(
                record,
                "identity_not_discovered",
                "attribute identity was not produced by entity discovery",
                evidence=identity,
            )
        )
    span = str(_value(record, "exact_span", "") or "")
    span_key = _text_key(span)
    span_tokens = set(span_key.split())
    other_tokens = {
        token
        for candidate in known
        if candidate != identity_key
        for token in candidate.split()
        if len(token) >= 3
    }
    locally_identifying_tokens = identity_tokens - other_tokens
    identity_supported = (
        bool(identity_key)
        and (
            identity_key in span_key
            or bool(locally_identifying_tokens & span_tokens)
        )
    )
    if require_span_support and identity_key and not identity_supported:
        issues.append(
            _issue(
                record,
                "identity_not_in_span",
                "identity is not locally supported by exact_span",
                evidence=span,
            )
        )
    return tuple(issues)


def validate_relationship_endpoints(
    relationship: RelationshipContract | WorkloadContract,
    entity_names: Optional[Iterable[str]] = None,
    *,
    records: Sequence[object] = (),
    known_identities: Optional[Mapping[str, Iterable[str]]] = None,
) -> Tuple[ValidationIssue, ...]:
    """Validate declared entities and any extracted relationship identities."""

    if isinstance(relationship, WorkloadContract):
        names = {entity.name for entity in relationship.entities}
        issues: List[ValidationIssue] = []
        for item in relationship.relationships:
            issues.extend(
                validate_relationship_endpoints(
                    item,
                    names,
                    records=records,
                    known_identities=known_identities,
                )
            )
        return tuple(issues)

    available = {_symbol_key(value) for value in (entity_names or ())}
    issues = []
    for side, entity in (
        ("left", relationship.left_entity),
        ("right", relationship.right_entity),
    ):
        if available and _symbol_key(entity) not in available:
            issues.append(
                ValidationIssue(
                    code="relationship_endpoint_unknown",
                    message=f"{side} relationship endpoint is not a contract entity",
                    entity=entity,
                )
            )

    identity_map = {
        _symbol_key(entity): {
            _text_key(identity) for identity in identities if _text_key(identity)
        }
        for entity, identities in (known_identities or {}).items()
    }
    relationship_names = {
        _symbol_key(relationship.name),
        *(_symbol_key(value) for value in relationship.alternatives),
    }
    for index, record in enumerate(records):
        record_name = _symbol_key(
            _value(record, "relationship", _value(record, "name", ""))
        )
        if record_name and record_name not in relationship_names:
            continue
        span = str(_value(record, "exact_span", "") or "")
        for side, entity in (
            ("left", relationship.left_entity),
            ("right", relationship.right_entity),
        ):
            identity = str(_value(record, f"{side}_identity", "") or "").strip()
            identity_key = _text_key(identity)
            known_for_entity = identity_map.get(_symbol_key(entity), set())
            identity_tokens = {
                token for token in identity_key.split() if len(token) >= 3
            }
            compatible_known = {
                candidate
                for candidate in known_for_entity
                if identity_tokens
                and (
                    set(identity_key.split()) <= set(candidate.split())
                    or set(candidate.split()) <= set(identity_key.split())
                )
            }
            if not identity:
                issues.append(
                    ValidationIssue(
                        code="relationship_identity_missing",
                        message=f"{side} relationship identity is missing",
                        entity=entity,
                        document_id=(
                            str(_value(record, "document_id"))
                            if _value(record, "document_id") is not None
                            else None
                        ),
                        record_index=index,
                        relationship=relationship.name,
                    )
                )
            elif (
                known_identities is not None
                and (
                    not known_for_entity
                    or (
                        identity_key not in known_for_entity
                        and len(compatible_known) != 1
                    )
                )
            ):
                issues.append(
                    ValidationIssue(
                        code="relationship_identity_unknown",
                        message=(
                            f"{side} identity was not discovered for endpoint "
                            f"{entity}"
                        ),
                        entity=entity,
                        document_id=(
                            str(_value(record, "document_id"))
                            if _value(record, "document_id") is not None
                            else None
                        ),
                        record_index=index,
                        evidence=identity,
                        relationship=relationship.name,
                    )
                )
            span_key = _text_key(span)
            span_tokens = set(span_key.split())
            other_tokens = {
                token
                for candidate in known_for_entity
                if candidate != identity_key
                for token in candidate.split()
                if len(token) >= 3
            }
            local_tokens = identity_tokens - other_tokens
            endpoint_supported = (
                bool(identity_key)
                and (
                    identity_key in span_key
                    or bool(local_tokens & span_tokens)
                )
            )
            if identity and identity_key and not endpoint_supported:
                issues.append(
                    ValidationIssue(
                        code="relationship_endpoint_not_in_span",
                        message=(
                            f"{side} relationship identity is not supported "
                            "by exact_span"
                        ),
                        entity=entity,
                        document_id=(
                            str(_value(record, "document_id"))
                            if _value(record, "document_id") is not None
                            else None
                        ),
                        record_index=index,
                        evidence=span,
                        relationship=relationship.name,
                    )
                )
    return tuple(issues)


def _unit_key(value: object) -> str:
    rendered = str(value or "").strip().lower()
    aliases = {"%": "percent", "percentage": "percent"}
    rendered = aliases.get(rendered, rendered)
    return re.sub(r"[^a-z0-9]+", "_", rendered).strip("_")


def _attribute_candidates(
    record: object, contracts: Sequence[AttributeContract]
) -> Tuple[AttributeContract, ...]:
    entity = _symbol_key(_value(record, "entity", ""))
    attribute = _symbol_key(_value(record, "attribute", ""))
    return tuple(
        contract
        for contract in contracts
        if attribute
        in {_symbol_key(value) for value in contract.symbols}
        and (
            not contract.owners
            or entity in {_symbol_key(owner) for owner in contract.owners}
        )
    )


def validate_units_and_conflicts(
    records: Sequence[object],
    attributes: Sequence[AttributeContract],
) -> Tuple[ValidationIssue, ...]:
    """Validate expected units and expose contradictory values per field."""

    issues: List[ValidationIssue] = []
    grouped: Dict[Tuple[str, str, str], List[object]] = defaultdict(list)
    for record in records:
        if _value(record, "attribute") is None:
            continue
        candidates = _attribute_candidates(record, attributes)
        if not candidates:
            continue
        allowed_units = {
            _unit_key(unit)
            for contract in candidates
            for unit in contract.units
            if _unit_key(unit)
        }
        actual_unit = _unit_key(_value(record, "unit"))
        if allowed_units and not actual_unit:
            issues.append(
                _issue(
                    record,
                    "unit_missing",
                    f"expected one of the units {sorted(allowed_units)}",
                )
            )
        elif allowed_units and actual_unit not in allowed_units:
            issues.append(
                _issue(
                    record,
                    "unit_mismatch",
                    f"unit is not one of {sorted(allowed_units)}",
                    evidence=str(_value(record, "unit")),
                )
            )
        key = (
            _symbol_key(_value(record, "entity", "")),
            _symbol_key(_value(record, "attribute", "")),
            _text_key(_value(record, "identity", "")),
        )
        grouped[key].append(record)

    for (_entity, _attribute, _identity), group in grouped.items():
        values = {
            json.dumps(_value(record, "value"), sort_keys=True, default=str)
            for record in group
        }
        units = {
            _unit_key(_value(record, "unit"))
            for record in group
            if _unit_key(_value(record, "unit"))
        }
        if len(values) > 1:
            issues.append(
                _issue(
                    group[0],
                    "conflicting_values",
                    "the same identity/field has multiple extracted values",
                    severity="warning",
                )
            )
        if len(units) > 1:
            issues.append(
                _issue(
                    group[0],
                    "conflicting_units",
                    "the same identity/field has multiple extracted units",
                    severity="warning",
                )
            )
    return tuple(issues)


def validate_contract(contract: WorkloadContract) -> Tuple[ValidationIssue, ...]:
    """Validate static endpoint and alternative consistency."""

    issues = list(validate_relationship_endpoints(contract))
    for attribute in contract.attributes:
        types = set(attribute.semantic_types)
        if "date" in types and types & {"integer", "real", "boolean"}:
            issues.append(
                ValidationIssue(
                    code="semantic_type_conflict",
                    message="attribute retains incompatible semantic alternatives",
                    severity="warning",
                    entity=attribute.entity,
                    attribute=attribute.name,
                )
            )
    return tuple(issues)


def _document_texts(documents: Mapping[str, str] | Sequence[object]) -> Dict[str, str]:
    if isinstance(documents, Mapping):
        return {str(key): str(value) for key, value in documents.items()}
    result: Dict[str, str] = {}
    for document in documents:
        document_id = str(_value(document, "document_id", ""))
        text = _value(document, "text")
        if document_id and isinstance(text, str):
            result[document_id] = text
    return result


def validate_extraction(
    extraction: object,
    contract: WorkloadContract,
    documents: Mapping[str, str] | Sequence[object],
) -> Tuple[ValidationIssue, ...]:
    """Run all contract and evidence checks over an extraction result."""

    records_value = _value(extraction, "records")
    if records_value is None:
        if isinstance(extraction, Sequence) and not isinstance(
            extraction, (str, bytes)
        ):
            records = tuple(extraction)
        else:
            entity_records = _value(extraction, "entity_records", ()) or ()
            attribute_records = _value(extraction, "attribute_records", ()) or ()
            records = (*entity_records, *attribute_records)
    else:
        records = tuple(records_value)
    relationship_records = tuple(
        _value(extraction, "relationship_records", ()) or ()
    )
    sources = _document_texts(documents)
    issues: List[ValidationIssue] = list(validate_contract(contract))

    known: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    known_by_entity: Dict[str, Set[str]] = defaultdict(set)
    for record in records:
        if _value(record, "attribute") is None:
            entity = _symbol_key(_value(record, "entity", ""))
            document_id = str(_value(record, "document_id", ""))
            identity = str(_value(record, "identity", "") or "")
            known[(entity, document_id)].add(identity)
            known_by_entity[str(_value(record, "entity", ""))].add(identity)

    partition_documents: Dict[str, List[str]] = defaultdict(list)
    for document_id in sources:
        normalized = document_id.replace("\\", "/").strip("/")
        if "/" in normalized:
            partition_documents[
                _symbol_key(normalized.split("/", 1)[0])
            ].append(document_id)
    for entity in contract.entities:
        entity_key = _symbol_key(entity.name)
        if any(
            _symbol_key(name) == entity_key and identities
            for name, identities in known_by_entity.items()
        ):
            continue
        candidates = sorted(partition_documents.get(entity_key, ()))
        if candidates:
            issues.append(
                ValidationIssue(
                    code="entity_contract_uncovered",
                    message=(
                        "no primary entity identity was extracted for this "
                        "source partition"
                    ),
                    entity=entity.name,
                    document_id=candidates[0],
                )
            )

    observed_fields = {
        (
            _symbol_key(_value(record, "entity", "")),
            _symbol_key(_value(record, "attribute", "")),
        )
        for record in records
        if _value(record, "attribute") is not None
    }
    for attribute in contract.attributes:
        for owner in attribute.owners:
            key = (_symbol_key(owner), _symbol_key(attribute.name))
            if key in observed_fields:
                continue
            discovered_documents = sorted(
                document_id
                for (entity_key, document_id), identities in known.items()
                if entity_key == _symbol_key(owner) and identities
            )
            if discovered_documents:
                issues.append(
                    ValidationIssue(
                        code="attribute_contract_uncovered",
                        message=(
                            "the required field has no accepted evidence in "
                            "the discovered entity registry"
                        ),
                        entity=owner,
                        attribute=attribute.name,
                        document_id=discovered_documents[0],
                    )
                )

    for index, record in enumerate(records):
        if isinstance(record, Mapping) and "record_index" not in record:
            record = {**record, "record_index": index}
        document_id = str(_value(record, "document_id", ""))
        attribute_name = _value(record, "attribute")
        if attribute_name is None:
            issues.extend(
                validate_field_local_span(
                    record, sources.get(document_id), semantic_types=("text",)
                )
            )
            issues.extend(validate_identity(record))
            continue
        candidates = _attribute_candidates(record, contract.attributes)
        if not candidates:
            issues.append(
                _issue(
                    record,
                    "attribute_not_in_contract",
                    "record field is not present for this contract entity",
                )
            )
            continue
        semantic_types = tuple(
            sorted(
                {
                    semantic_type
                    for candidate in candidates
                    for semantic_type in candidate.semantic_types
                }
            )
        )
        issues.extend(
            validate_field_local_span(
                record,
                sources.get(document_id),
                semantic_types=semantic_types,
            )
        )
        issues.extend(validate_semantic_type(record, semantic_types))
        for candidate in candidates:
            issues.extend(validate_count_date(record, candidate))
        issues.extend(
            validate_identity(
                record,
                known.get(
                    (
                        _symbol_key(_value(record, "entity", "")),
                        document_id,
                    ),
                    (),
                ),
                require_span_support=True,
            )
        )

    relationship_names = {
        _symbol_key(value)
        for relationship in contract.relationships
        for value in (relationship.name, *relationship.alternatives)
    }
    for index, record in enumerate(relationship_records):
        if isinstance(record, Mapping) and "record_index" not in record:
            record = {**record, "record_index": index}
        document_id = str(_value(record, "document_id", ""))
        issues.extend(
            validate_field_local_span(
                record,
                sources.get(document_id),
            )
        )
        name = _symbol_key(_value(record, "relationship", ""))
        if not name or name not in relationship_names:
            issues.append(
                _issue(
                    record,
                    "relationship_not_in_contract",
                    "relationship record does not match a contract edge",
                )
            )

    issues.extend(
        validate_relationship_endpoints(
            contract,
            records=relationship_records,
            known_identities=known_by_entity,
        )
    )
    issues.extend(validate_units_and_conflicts(records, contract.attributes))
    unique: Dict[Tuple[object, ...], ValidationIssue] = {}
    for issue in issues:
        key = (
            issue.code,
            issue.severity,
            issue.entity,
            issue.attribute,
            issue.document_id,
            issue.record_index,
            issue.evidence,
            issue.relationship,
        )
        unique.setdefault(key, issue)
    return tuple(unique.values())


def targeted_repair_targets(
    issues: Sequence[ValidationIssue],
    *,
    include_warnings: bool = False,
) -> Tuple[RepairTarget, ...]:
    """Group validation outcomes into deterministic document-local repairs."""

    grouped: Dict[
        Tuple[str, str, str, Optional[str], Optional[str]],
        Dict[str, Set[object]],
    ] = {}
    for issue in issues:
        if issue.severity != "error" and not include_warnings:
            continue
        if not issue.document_id:
            # Static contract issues have no source-local repair target.
            continue
        if issue.relationship:
            phase = "relationship"
        elif issue.attribute is not None:
            phase = "attribute"
        else:
            phase = "entity"
        key = (
            phase,
            issue.document_id,
            issue.entity,
            issue.attribute,
            issue.relationship,
        )
        state = grouped.setdefault(
            key,
            {"issue_codes": set(), "record_indexes": set()},
        )
        state["issue_codes"].add(issue.code)
        if issue.record_index is not None:
            state["record_indexes"].add(issue.record_index)
    return tuple(
        RepairTarget(
            phase=phase,
            document_id=document_id,
            entity=entity,
            attribute=attribute,
            relationship=relationship,
            issue_codes=tuple(
                sorted(str(value) for value in state["issue_codes"])
            ),
            record_indexes=tuple(
                sorted(int(value) for value in state["record_indexes"])
            ),
        )
        for (
            phase,
            document_id,
            entity,
            attribute,
            relationship,
        ), state in sorted(grouped.items(), key=lambda item: str(item[0]))
    )


def build_targeted_repair_targets(
    issues: Sequence[ValidationIssue],
    *,
    include_warnings: bool = False,
) -> Tuple[RepairTarget, ...]:
    """Compatibility-friendly named wrapper for targeted repair planning."""

    return targeted_repair_targets(
        issues, include_warnings=include_warnings
    )


def _evidence_hashes(evidence: object) -> Set[str]:
    if evidence is None:
        return set()
    if isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes)):
        values: Iterable[object] = evidence
    else:
        values = (evidence,)
    result = set()
    for value in values:
        encoded = json.dumps(
            value,
            sort_keys=True,
            default=lambda item: asdict(item)
            if hasattr(item, "__dataclass_fields__")
            else str(item),
        ).encode("utf-8")
        result.add(hashlib.sha256(encoded).hexdigest())
    return result


@dataclass
class AdaptiveRepairAdmission:
    """Track novelty and admit repairs while completion remains affordable.

    There is intentionally no maximum candidate or retry count. A proposed
    repair is admitted only if it contributes a previously unseen violation
    shape or evidence digest and its worst-case token cost leaves the declared
    completion reserve untouched.
    """

    seen_violations: Set[str] = field(default_factory=set)
    seen_evidence: Set[str] = field(default_factory=set)
    admitted_attempts: int = 0

    def admit(
        self,
        issues: Sequence[ValidationIssue],
        *,
        evidence: object = None,
        estimated_repair_tokens: int,
        completion_reserve: int,
        remaining_tokens: Optional[int] = None,
        ledger: Optional[object] = None,
    ) -> bool:
        """Record and admit a novel, affordable repair candidate."""

        if estimated_repair_tokens < 0 or completion_reserve < 0:
            raise ValueError("repair cost and completion reserve cannot be negative")
        if remaining_tokens is None:
            available = getattr(ledger, "available", None)
            if available is None:
                raise ValueError("remaining_tokens or a ledger is required")
            remaining_tokens = int(available)
        violation_hashes = {issue.fingerprint for issue in issues}
        evidence_hashes = _evidence_hashes(evidence)
        novel_violations = violation_hashes - self.seen_violations
        novel_evidence = evidence_hashes - self.seen_evidence
        if not issues or (not novel_violations and not novel_evidence):
            return False
        if (
            int(remaining_tokens) - int(estimated_repair_tokens)
            < int(completion_reserve)
        ):
            return False
        self.seen_violations.update(violation_hashes)
        self.seen_evidence.update(evidence_hashes)
        self.admitted_attempts += 1
        return True


def admit_adaptive_repair(
    admission: AdaptiveRepairAdmission,
    issues: Sequence[ValidationIssue],
    *,
    evidence: object = None,
    estimated_repair_tokens: int,
    completion_reserve: int,
    remaining_tokens: Optional[int] = None,
    ledger: Optional[object] = None,
) -> bool:
    """Functional wrapper for backend code that owns an admission tracker."""

    return admission.admit(
        issues,
        evidence=evidence,
        estimated_repair_tokens=estimated_repair_tokens,
        completion_reserve=completion_reserve,
        remaining_tokens=remaining_tokens,
        ledger=ledger,
    )

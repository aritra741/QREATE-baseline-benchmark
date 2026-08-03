"""Evidence-backed, idempotent memory for derived cardinalities."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from spp.calculation_tools import calculate
from spp.evidence_store import EvidenceAnchor, EvidenceStore


COUNT_MEMORY_VERSION = 1
_SMALL_NUMBERS = {
    "zero": 0,
    "no": 0,
    "a": 1,
    "an": 1,
    "one": 1,
    "single": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _surface_occurs(surface: str, span: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(surface)}(?![A-Za-z0-9])",
            span,
        )
    )


def parse_quantity_surface(surface: object) -> Optional[int]:
    """Parse an explicitly cited integer surface without model arithmetic."""

    rendered = str(surface or "").strip().casefold()
    if not rendered:
        return None
    numeric = re.fullmatch(r"[+]?\d[\d,]*", rendered)
    if numeric is not None:
        return int(rendered.replace(",", ""))
    tokens = [
        token
        for token in re.split(r"[\s-]+", rendered)
        if token and token != "and"
    ]
    if not tokens:
        return None
    total = 0
    current = 0
    for token in tokens:
        if token in _SMALL_NUMBERS:
            current += _SMALL_NUMBERS[token]
        elif token in _TENS:
            current += _TENS[token]
        elif token == "hundred":
            current = max(1, current) * 100
        elif token in {"thousand", "million"}:
            total += max(1, current) * _SCALES[token]
            current = 0
        else:
            return None
    return total + current


@dataclass(frozen=True)
class CountMemoryResult:
    """One deterministic reduction over stored count facts."""

    value: int
    mode: str
    facts: Tuple[Mapping[str, object], ...]
    anchor_ids: Tuple[str, ...]


def count_derivation_is_grounded(
    value: object,
    inputs: object,
    documents: Optional[Mapping[str, str]] = None,
) -> bool:
    """Recompute a count-memory result and optionally restore every span."""

    if not isinstance(inputs, Mapping) or inputs.get("tool") != "count_memory":
        return False
    facts = inputs.get("facts")
    if not isinstance(facts, list) or not facts:
        return False
    totals = []
    increments = []
    keys = set()
    for fact in facts:
        if not isinstance(fact, Mapping):
            return False
        operation = fact.get("operation")
        if operation not in {"set_total", "add_distinct"}:
            return False
        quantity = fact.get("quantity")
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity < 0
            or (operation == "add_distinct" and quantity < 1)
        ):
            return False
        normalized_key = _key(fact.get("fact_key"))
        if not normalized_key or normalized_key in keys:
            return False
        keys.add(normalized_key)
        evidence = fact.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return False
        surface = fact.get("quantity_surface")
        grounded_surface = False
        for item in evidence:
            if not isinstance(item, Mapping):
                return False
            span = item.get("exact_span")
            if not isinstance(span, str) or not span:
                return False
            if surface is not None and _surface_occurs(
                str(surface), span
            ):
                grounded_surface = (
                    parse_quantity_surface(surface) == quantity
                )
            if documents is not None:
                document_id = str(item.get("document_id", ""))
                source = documents.get(document_id)
                start = item.get("start")
                end = item.get("end")
                if (
                    source is None
                    or not isinstance(start, int)
                    or not isinstance(end, int)
                    or start < 0
                    or end != start + len(span)
                    or source[start:end] != span
                ):
                    return False
        if surface is None:
            grounded_surface = operation == "add_distinct" and quantity == 1
        if not grounded_surface:
            return False
        (totals if operation == "set_total" else increments).append(quantity)
    if totals:
        expected = totals[0] if len(set(totals)) == 1 else None
    elif increments:
        expected = calculate("add", increments)
    else:
        expected = None
    return expected == value


class EvidenceCountMemory:
    """A scoped memory tool whose writes require verbatim source evidence."""

    def __init__(
        self,
        evidence_store: EvidenceStore,
        *,
        contract_fingerprint: str,
        entity: str,
        identity: str,
        attribute: str,
        producer: str = "",
    ):
        self.evidence_store = evidence_store
        scope = {
            "version": COUNT_MEMORY_VERSION,
            "contract": contract_fingerprint,
            "entity": entity,
            "identity": identity,
            "attribute": attribute,
            "producer": producer,
        }
        self.memory_key = hashlib.sha256(
            json.dumps(scope, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self.entity = entity
        self.identity = identity
        self.attribute = attribute

    def facts(self) -> Tuple[Mapping[str, object], ...]:
        return tuple(
            self.evidence_store.count_facts(memory_key=self.memory_key)
        )

    def prompt_state(self) -> Tuple[dict, ...]:
        """Expose only compact source-derived state to the next model call."""

        return tuple(
            {
                "operation": fact["operation"],
                "fact_key": fact["fact_key"],
                "quantity": fact["quantity"],
                "unit": fact["unit"],
                "conflicted": fact["conflicted"],
            }
            for fact in self.facts()
        )

    def remember(
        self,
        *,
        operation: str,
        fact_key: str,
        quantity: object,
        quantity_surface: object,
        exact_span: str,
        document_id: str,
        start: int,
        end: int,
        unit: Optional[str],
    ) -> bool:
        """Apply one checked ``set_total`` or weighted ``add_distinct`` call."""

        if operation not in {"set_total", "add_distinct"}:
            return False
        if isinstance(quantity, bool):
            return False
        try:
            integer_quantity = int(quantity)
        except (TypeError, ValueError):
            return False
        if integer_quantity != quantity or integer_quantity < 0:
            return False
        if operation == "add_distinct" and integer_quantity < 1:
            return False
        surface = (
            str(quantity_surface).strip()
            if quantity_surface is not None
            else ""
        )
        if surface:
            if not _surface_occurs(surface, exact_span):
                return False
            if parse_quantity_surface(surface) != integer_quantity:
                return False
        elif operation == "set_total" or integer_quantity != 1:
            return False

        rendered_key = str(fact_key or "").strip()
        normalized_key = _key(rendered_key)
        if not normalized_key or not exact_span:
            return False
        if start < 0 or end != start + len(exact_span):
            return False

        anchor = EvidenceAnchor.create(
            document_id=document_id,
            text=exact_span,
            start=start,
            end=end,
            anchor_type="count_memory_fact",
            metadata={
                "entity": self.entity,
                "identity": self.identity,
                "attribute": self.attribute,
                "operation": operation,
                "fact_key": rendered_key,
                "quantity": integer_quantity,
            },
        )
        current_facts = self.facts()
        for fact in current_facts:
            if any(
                item.get("anchor_id") == anchor.anchor_id
                for item in fact.get("evidence", ())
            ):
                return (
                    fact["operation"] == operation
                    and int(fact["quantity"]) == integer_quantity
                )
        existing = {
            _key(fact["fact_key"]): fact for fact in current_facts
        }
        if (
            normalized_key not in existing
            and rendered_key not in exact_span
        ):
            return False
        self.evidence_store.add_anchors((anchor,))
        fact_id = hashlib.sha256(
            (
                f"count-memory-v{COUNT_MEMORY_VERSION}\0{self.memory_key}\0"
                f"{operation}\0{normalized_key}"
            ).encode("utf-8")
        ).hexdigest()
        self.evidence_store.remember_count_fact(
            fact_id=fact_id,
            memory_key=self.memory_key,
            operation=operation,
            fact_key=rendered_key,
            quantity=integer_quantity,
            quantity_surface=surface or None,
            unit=unit,
            anchor_id=anchor.anchor_id,
        )
        return True

    def reduce(self) -> Optional[CountMemoryResult]:
        """Prefer a consistent explicit total, otherwise sum unique increments."""

        facts = self.facts()
        if not facts or any(bool(fact["conflicted"]) for fact in facts):
            return None
        totals = tuple(
            fact for fact in facts if fact["operation"] == "set_total"
        )
        increments = tuple(
            fact for fact in facts if fact["operation"] == "add_distinct"
        )
        if totals:
            values = {int(fact["quantity"]) for fact in totals}
            if len(values) != 1:
                return None
            selected = totals
            value = values.pop()
            mode = "explicit_total"
        elif increments:
            selected = increments
            value = calculate(
                "add",
                [int(fact["quantity"]) for fact in increments],
            )
            mode = "distinct_sum"
        else:
            return None
        anchors = tuple(
            sorted(
                {
                    str(anchor_id)
                    for fact in selected
                    for anchor_id in fact["anchor_ids"]
                }
            )
        )
        return CountMemoryResult(
            value=int(value),
            mode=mode,
            facts=selected,
            anchor_ids=anchors,
        )


"""Entity-first extraction driven by a workload contract.

Every model call is budgeted, content-addressed in the shared evidence store,
and constrained to verbatim source evidence.  Attribute calls request exactly
one field for one source document; this avoids positional row coercion and
makes field-local validation possible.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from json_repair import repair_json

from spp.budget_ledger import BudgetExhausted
from spp.budgeted_llm import BudgetedLLMClient
from spp.calculation_tools import calculate, operands_are_grounded
from spp.evidence_store import EvidenceAnchor, EvidenceStore
from spp.workload_contract import (
    AttributeContract,
    EntityContract,
    RelationshipContract,
    WorkloadContract,
)
from token_counter import count_tokens


_PROMPT_VERSION = 8
_ENTITY_ARTIFACT_VERSION = 3
_CONTEXT_ROUTING_VERSION = 3
CORPUS_REFERENCE_YEAR = 2026
_CONTEXT_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "before",
        "between",
        "count",
        "each",
        "every",
        "from",
        "have",
        "many",
        "most",
        "only",
        "over",
        "show",
        "that",
        "their",
        "these",
        "those",
        "what",
        "when",
        "where",
        "which",
        "with",
    }
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceDocument:
    """Minimal source-document shape accepted by :class:`ContractExtractor`.

    Existing ``spp.native_backend.SourceDocument`` instances are accepted
    structurally; callers do not need to convert them to this local equivalent.
    """

    document_id: str
    text: str
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentUnit:
    """One full source document used as an independently cached prompt unit."""

    unit_id: str
    document_id: str
    text: str
    start: int
    end: int
    source_ranges: Tuple[Tuple[int, int], ...] = ()


@dataclass(frozen=True)
class ExtractionRecord:
    """One extracted value with an exact, field-local source span."""

    entity: str
    attribute: Optional[str]
    identity: str
    value: object
    exact_span: str
    unit: Optional[str]
    document_id: str
    unit_id: str
    span_start: int
    span_end: int
    derivation_kind: Optional[str] = None
    derivation_inputs: Mapping[str, object] = field(default_factory=dict)

    @property
    def is_entity(self) -> bool:
        """Whether this row came from the entity-discovery phase."""

        return self.attribute is None

    def to_payload(self) -> dict:
        """Return a JSON-compatible record for backend handoff."""

        return asdict(self)


@dataclass(frozen=True)
class RelationshipRecord:
    """One explicitly stated edge between two discovered entity identities."""

    relationship: str
    left_entity: str
    right_entity: str
    left_identity: str
    right_identity: str
    exact_span: str
    document_id: str
    unit_id: str
    span_start: int
    span_end: int

    def to_payload(self) -> dict:
        """Return a JSON-compatible relationship edge."""

        return asdict(self)


@dataclass(frozen=True)
class DerivationMapping:
    """A reversible unit or categorical mapping over accepted raw values."""

    entity: str
    attribute: str
    source_value: object
    target_value: object
    mapping_kind: str
    source_unit: Optional[str] = None
    target_unit: Optional[str] = None
    supporting_document_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.mapping_kind not in {"taxonomy", "unit"}:
            raise ValueError("unsupported derivation mapping kind")

    def to_payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ContractExtraction:
    """Partial or complete evidence produced for one workload contract."""

    contract_fingerprint: str
    entity_records: Tuple[ExtractionRecord, ...]
    attribute_records: Tuple[ExtractionRecord, ...]
    relationship_records: Tuple[RelationshipRecord, ...] = ()
    derivation_mappings: Tuple[DerivationMapping, ...] = ()
    complete: bool = True
    budget_exhausted: bool = False
    pending_target: Optional[str] = None

    @property
    def records(self) -> Tuple[ExtractionRecord, ...]:
        """Return entity and field records, preserving the original API."""

        return (*self.entity_records, *self.attribute_records)

    @property
    def all_records(
        self,
    ) -> Tuple[ExtractionRecord | RelationshipRecord, ...]:
        """Return field records followed by explicit relationship edges."""

        return (*self.records, *self.relationship_records)

    def by_entity(self) -> Mapping[str, Tuple[ExtractionRecord, ...]]:
        """Group all records by logical entity for relational materialization."""

        grouped: Dict[str, List[ExtractionRecord]] = {}
        for record in self.records:
            grouped.setdefault(record.entity, []).append(record)
        return {key: tuple(value) for key, value in grouped.items()}

    def to_payload(self) -> dict:
        """Return a stable payload suitable for a ContractBackend."""

        return {
            "contract_fingerprint": self.contract_fingerprint,
            "entity_records": [
                record.to_payload() for record in self.entity_records
            ],
            "attribute_records": [
                record.to_payload() for record in self.attribute_records
            ],
            "relationship_records": [
                record.to_payload() for record in self.relationship_records
            ],
            "derivation_mappings": [
                mapping.to_payload() for mapping in self.derivation_mappings
            ],
            "complete": self.complete,
            "budget_exhausted": self.budget_exhausted,
            "pending_target": self.pending_target,
        }


def _symbol_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _canonical_identity(
    surface: object,
    known_identities: Sequence[str],
) -> str:
    rendered = str(surface or "").strip()
    surface_key = _symbol_key(rendered)
    if not surface_key:
        return rendered
    exact = [
        identity
        for identity in known_identities
        if _symbol_key(identity) == surface_key
    ]
    if len(exact) == 1:
        return exact[0]
    surface_tokens = set(surface_key.split("_"))
    candidates = []
    for identity in known_identities:
        identity_key = _symbol_key(identity)
        identity_tokens = set(identity_key.split("_"))
        overlap = {
            token
            for token in surface_tokens & identity_tokens
            if len(token) >= 3
        }
        if overlap and (
            surface_tokens <= identity_tokens
            or identity_tokens <= surface_tokens
        ):
            candidates.append(identity)
    return candidates[0] if len(candidates) == 1 else rendered


def _document_unit(document: SourceDocument) -> DocumentUnit:
    digest = hashlib.sha256(
        f"contract-document\0{document.document_id}\0{document.text}".encode(
            "utf-8"
        )
    ).hexdigest()
    return DocumentUnit(
        unit_id=digest,
        document_id=document.document_id,
        text=document.text,
        start=0,
        end=len(document.text),
        source_ranges=((0, len(document.text)),),
    )


class ContractExtractor:
    """Run literal-grounded extraction through a budget-enforcing client.

    Parameters are deliberately backend-neutral. ``documents`` may contain
    native SPP source documents or any objects exposing ``document_id``,
    ``text``, and optional ``metadata`` fields.  The extractor registers those
    documents and all accepted exact spans in ``evidence_store``.
    """

    version = (
        f"{_PROMPT_VERSION}.entity-{_ENTITY_ARTIFACT_VERSION}."
        f"context-{_CONTEXT_ROUTING_VERSION}"
    )

    def __init__(
        self,
        documents: Sequence[object],
        llm_client: BudgetedLLMClient,
        evidence_store: EvidenceStore,
        *,
        max_entity_tokens: int = 768,
        max_attribute_tokens: int = 512,
        max_workers: Optional[int] = None,
        max_context_characters: Optional[int] = None,
    ):
        if not documents:
            raise ValueError("contract extraction requires source documents")
        if max_entity_tokens <= 0 or max_attribute_tokens <= 0:
            raise ValueError("extraction token limits must be positive")
        normalized: List[SourceDocument] = []
        for document in documents:
            document_id = str(getattr(document, "document_id", "")).strip()
            text = getattr(document, "text", None)
            if not document_id or not isinstance(text, str):
                raise TypeError(
                    "source documents require string document_id and text fields"
                )
            metadata = getattr(document, "metadata", {}) or {}
            if not isinstance(metadata, Mapping):
                raise TypeError("source document metadata must be a mapping")
            normalized.append(
                SourceDocument(
                    document_id=document_id,
                    text=text,
                    metadata=dict(metadata),
                )
            )
        self.documents = tuple(normalized)
        self.units = tuple(_document_unit(document) for document in normalized)
        self.llm_client = llm_client
        self.evidence_store = evidence_store
        self.max_entity_tokens = int(max_entity_tokens)
        self.max_attribute_tokens = int(max_attribute_tokens)
        self.max_workers = max(
            1,
            int(
                max_workers
                if max_workers is not None
                else os.getenv("SPP_CONTRACT_MAX_WORKERS", "4")
            ),
        )
        self.max_context_characters = max(
            1200,
            int(
                max_context_characters
                if max_context_characters is not None
                else os.getenv("SPP_CONTRACT_CONTEXT_CHARS", "3600")
            ),
        )
        self._budget_exhausted = False
        self._pending_target: Optional[str] = None
        self._document_text = {
            document.document_id: document.text for document in self.documents
        }
        # Fixed corpus clock for time-relative tool calculations. This is not
        # attribute-specific; the model still decides whether any derivation
        # is warranted and must request the calculator explicitly.
        self.reference_year = CORPUS_REFERENCE_YEAR
        for document in self.documents:
            self.evidence_store.add_document(
                document.document_id,
                document.text,
                metadata=dict(document.metadata),
            )

    @staticmethod
    def _prefix(document_id: str) -> str:
        normalized = str(document_id).replace("\\", "/").strip("/")
        return _symbol_key(normalized.split("/", 1)[0])

    def documents_for_entity(
        self, entity: EntityContract | str
    ) -> Tuple[DocumentUnit, ...]:
        """Route a partitioned corpus by observed document-id prefixes.

        Prefix routing is enabled only when at least one prefix matches the
        requested entity or one of its aliases.  Otherwise all documents are
        retained, which is the safe behavior for flat or partially named
        corpora.  No corpus name or benchmark table is hard-coded.
        """

        if isinstance(entity, EntityContract):
            names = entity.symbols
        else:
            names = (str(entity),)
        target_keys = {_symbol_key(name) for name in names if _symbol_key(name)}
        matched = tuple(
            unit
            for unit in self.units
            if self._prefix(unit.document_id) in target_keys
        )
        return matched or self.units

    @staticmethod
    def _search_phrases(values: Iterable[object]) -> Tuple[str, ...]:
        phrases: List[str] = []
        for value in values:
            rendered = re.sub(
                r"[_\W]+",
                " ",
                str(value or "").lower(),
            ).strip()
            if not rendered:
                continue
            candidates = [rendered]
            candidates.extend(
                token
                for token in rendered.split()
                if len(token) >= 3 and token not in _CONTEXT_STOPWORDS
            )
            for candidate in candidates:
                if candidate not in phrases:
                    phrases.append(candidate)
        return tuple(phrases)

    def _focused_unit(
        self,
        unit: DocumentUnit,
        *,
        terms: Iterable[object] = (),
        lead_only: bool = False,
    ) -> DocumentUnit:
        """Select bounded, verbatim source windows for one contract call."""

        source = self._document_text[unit.document_id]
        limit = self.max_context_characters
        if len(source) <= limit:
            return _document_unit(
                SourceDocument(unit.document_id, source)
            )

        lead_size = min(limit if lead_only else max(800, limit // 3), len(source))
        ranges: List[Tuple[int, int]] = [(0, lead_size)]
        phrases = self._search_phrases(terms)
        if not lead_only and phrases:
            remaining = max(0, limit - lead_size)
            window_size = max(600, remaining // 2)
            candidates: Dict[Tuple[int, int], float] = {}
            for rank, phrase in enumerate(phrases):
                weight = 1.0 + 1.0 / (rank + 1)
                for match in re.finditer(
                    re.escape(phrase),
                    source,
                    flags=re.IGNORECASE,
                ):
                    start = max(0, match.start() - window_size // 2)
                    end = min(len(source), start + window_size)
                    start = max(0, end - window_size)
                    key = (start, end)
                    candidates[key] = candidates.get(key, 0.0) + weight
            for candidate, _score in sorted(
                candidates.items(),
                key=lambda item: (
                    -item[1],
                    item[0][0],
                    item[0][1],
                ),
            ):
                if sum(end - start for start, end in ranges) >= limit:
                    break
                if any(
                    max(start, candidate[0]) < min(end, candidate[1])
                    for start, end in ranges
                ):
                    continue
                available = limit - sum(
                    end - start for start, end in ranges
                )
                if available <= 0:
                    break
                start, end = candidate
                if end - start > available:
                    if end == len(source):
                        start = end - available
                    else:
                        end = start + available
                ranges.append((start, end))

        ranges = sorted(ranges)
        text = "\n\n".join(source[start:end] for start, end in ranges)
        digest = hashlib.sha256(
            (
                f"contract-context-v{_CONTEXT_ROUTING_VERSION}\0"
                f"{unit.unit_id}\0{ranges}\0{text}"
            ).encode("utf-8")
        ).hexdigest()
        return DocumentUnit(
            unit_id=digest,
            document_id=unit.document_id,
            text=text,
            start=ranges[0][0],
            end=ranges[-1][1],
            source_ranges=tuple(ranges),
        )

    def _locate_exact_span(
        self,
        unit: DocumentUnit,
        exact_span: str,
    ) -> Optional[int]:
        source = self._document_text.get(unit.document_id, "")
        ranges = unit.source_ranges or ((unit.start, unit.end),)
        for start, end in ranges:
            offset = source.find(exact_span, start, end)
            if offset >= 0 and offset + len(exact_span) <= end:
                return offset
        return None

    @staticmethod
    def _partition_heading_identity(
        entity: EntityContract,
        unit: DocumentUnit,
    ) -> Optional[str]:
        entity_keys = {
            _symbol_key(value) for value in entity.symbols if _symbol_key(value)
        }
        if ContractExtractor._prefix(unit.document_id) not in entity_keys:
            return None
        match = re.search(r"(?m)^[ \t]*(\S[^\r\n]*)[ \t]*$", unit.text)
        if match is None:
            return None
        heading = match.group(1).strip()
        if (
            not heading
            or len(heading) > 200
            or len(heading.split()) > 20
            or heading[-1:] in {".", "!", "?", ";", ":"}
            or _symbol_key(heading)
            in {"contents", "introduction", "overview", "references"}
        ):
            return None
        return heading

    @staticmethod
    def _entity_prompt(entity: EntityContract, unit: DocumentUnit) -> str:
        contract = {
            "entity": entity.name,
            "primary_subject_only": True,
            "name_alternatives": list(entity.alternatives),
            "identity_attribute_alternatives": list(
                entity.identity_attributes
            ),
            "query_roles": {
                query_id: list(roles) for query_id, roles in entity.contexts
            },
            "natural_language_query_hints": dict(entity.query_hints),
        }
        return (
            "Identify every distinct instance of the requested entity that is "
            "a primary subject of this source document. A primary subject is an "
            "instance the document states facts about, not an instance merely "
            "mentioned as a related object, comparison, owner, location, or "
            "example. Do not infer from outside knowledge, promote related "
            "mentions into entity rows, or merge distinct instances. Return only "
            "a JSON array. Every object must have exactly these keys: "
            '"identity", "value", "exact_span", "unit". identity is the stable '
            "source-stated label for the instance; value must repeat that "
            "identity for this discovery phase; exact_span is the shortest "
            "verbatim, case-sensitive source substring that supports the "
            "identity; unit must be null. Return [] when no instance is stated."
            "\n\nEntity contract:\n"
            f"{json.dumps(contract, sort_keys=True)}"
            "\n\nVerbatim source evidence excerpt(s):\n"
            f"{unit.text}"
        )

    @staticmethod
    def _relationship_prompt(
        relationship: RelationshipContract,
        unit: DocumentUnit,
        left_identities: Sequence[str],
        right_identities: Sequence[str],
    ) -> str:
        contract = {
            "relationship": relationship.name,
            "relationship_alternatives": list(relationship.alternatives),
            "left_entity": relationship.left_entity,
            "right_entity": relationship.right_entity,
            "left_attribute_alternatives": list(
                relationship.left_attributes
            ),
            "right_attribute_alternatives": list(
                relationship.right_attributes
            ),
            "known_left_identities": list(left_identities),
            "known_right_identities": list(right_identities),
            "query_roles": {
                query_id: list(roles)
                for query_id, roles in relationship.contexts
            },
            "natural_language_query_hints": dict(
                relationship.query_hints
            ),
        }
        return (
            "Extract only explicitly stated edges for the requested relationship "
            "from this source document. Do not infer an edge from co-occurrence "
            "or outside knowledge. Return only a JSON array. Every object must "
            'have exactly these keys: "left_identity", "right_identity", '
            '"exact_span". Each identity names the stated endpoint; exact_span '
            "is the shortest verbatim, case-sensitive source substring that "
            "locally supports both endpoints and the edge. Return [] when no "
            "edge is stated."
            "\n\nRelationship contract:\n"
            f"{json.dumps(contract, sort_keys=True)}"
            "\n\nVerbatim source evidence excerpt(s):\n"
            f"{unit.text}"
        )

    @staticmethod
    def _attribute_prompt(
        attribute: AttributeContract,
        owner: str,
        unit: DocumentUnit,
        identities: Sequence[str],
    ) -> str:
        contract = {
            "entity": owner or None,
            "possible_entities": list(attribute.entity_alternatives),
            "attribute": attribute.name,
            "name_alternatives": list(attribute.alternatives),
            "semantic_type_alternatives": list(attribute.semantic_types),
            "unit_alternatives": list(attribute.units),
            "query_roles": {
                query_id: list(roles)
                for query_id, roles in attribute.contexts
            },
            "natural_language_query_hints": dict(
                attribute.query_hints
            ),
            "known_document_identities": list(identities),
        }
        return (
            "Extract only the single requested attribute for every explicitly "
            "supported entity instance in this source document. Return one "
            "object per supported identity and no object for a missing value. "
            "Do not infer, calculate, normalize, or copy a value from another "
            "field. Preserve the source's numeric magnitude: for example, if "
            "the source states 1.2 million, value must be 1.2 and unit must be "
            '"million", never 1200000. Return only a JSON array. Every object '
            "must have exactly "
            'these keys: "identity", "value", "exact_span", "unit". identity '
            "links the value to its source-stated entity instance; value is one "
            "JSON scalar; exact_span is the shortest verbatim, case-sensitive "
            "source substring that locally supports both the identity/value "
            "association and this field; unit is the explicitly stated unit or "
            "null. Return [] when this field is absent."
            "\n\nAttribute contract:\n"
            f"{json.dumps(contract, sort_keys=True)}"
            "\n\nVerbatim source evidence excerpt(s):\n"
            f"{unit.text}"
        )

    @staticmethod
    def _parse_response(response: str) -> List[Mapping[str, object]]:
        """Parse object rows without inventing positional field assignments."""

        rendered = str(response or "").strip()
        if not rendered:
            raise ValueError("contract extraction response is empty")

        candidates: List[str] = []
        candidates.extend(
            match.strip()
            for match in re.findall(
                r"```(?:json)?\s*(.*?)```",
                rendered,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match.strip()
        )
        start, end = rendered.find("["), rendered.rfind("]")
        if start >= 0 and end >= start:
            candidates.append(rendered[start : end + 1])
        candidates.append(rendered)

        payload: object = None
        parse_error: Optional[Exception] = None
        for candidate in dict.fromkeys(candidates):
            try:
                payload = json.loads(candidate)
                parse_error = None
                break
            except json.JSONDecodeError as exc:
                parse_error = exc
                try:
                    payload = repair_json(candidate, return_objects=True)
                except Exception as repair_exc:
                    parse_error = repair_exc
                    continue
                if isinstance(payload, (list, Mapping)):
                    parse_error = None
                    break
        if parse_error is not None or not isinstance(
            payload, (list, Mapping)
        ):
            raise ValueError(
                "contract extraction response is not valid JSON"
            ) from parse_error

        if isinstance(payload, Mapping):
            for key in (
                "records",
                "results",
                "rows",
                "data",
                "entities",
                "attributes",
                "relationships",
                "extractions",
            ):
                nested = payload.get(key)
                if isinstance(nested, list):
                    payload = nested
                    break
            else:
                if any(
                    key in payload
                    for key in ("identity", "left_identity", "exact_span")
                ):
                    payload = [payload]
                else:
                    raise ValueError(
                        "contract extraction object contains no row array"
                    )

        rows: List[Mapping[str, object]] = []
        for item in payload:
            if isinstance(item, Mapping):
                rows.append(dict(item))
            elif isinstance(item, list):
                rows.extend(
                    dict(nested)
                    for nested in item
                    if isinstance(nested, Mapping)
                )
        if payload and not rows:
            raise ValueError(
                "contract extraction response must contain object rows"
            )
        return rows

    @staticmethod
    def _recover_scalar_entity_response(
        response: str,
        source_text: str,
    ) -> List[Mapping[str, object]]:
        """Recover one source-exact identity from a scalar-only entity array."""

        rendered = str(response or "").strip()
        start, end = rendered.find("["), rendered.rfind("]")
        if start < 0 or end < start:
            return []
        candidate = rendered[start : end + 1]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                payload = repair_json(candidate, return_objects=True)
            except Exception:
                return []
        if (
            not isinstance(payload, list)
            or len(payload) != 1
            or not isinstance(payload[0], str)
        ):
            return []
        identity = payload[0].strip()
        if not identity or identity not in source_text:
            return []
        return [
            {
                "identity": identity,
                "value": identity,
                "exact_span": identity,
                "unit": None,
            }
        ]

    def _artifact_key(
        self,
        *,
        phase: str,
        prompt: str,
        unit: DocumentUnit,
    ) -> str:
        model = getattr(
            getattr(self.llm_client, "client", self.llm_client),
            "model",
            type(getattr(self.llm_client, "client", self.llm_client)).__name__,
        )
        artifact_version = (
            f"{_PROMPT_VERSION}.entity-{_ENTITY_ARTIFACT_VERSION}"
            if phase == "entity"
            else str(_PROMPT_VERSION)
        )
        payload = (
            f"workload-contract-extraction-v{artifact_version}\0{phase}\0"
            f"{model}\0{unit.unit_id}\0{prompt}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _rows(
        self,
        *,
        phase: str,
        prompt: str,
        unit: DocumentUnit,
        max_tokens: int,
    ) -> List[Mapping[str, object]]:
        key = self._artifact_key(phase=phase, prompt=prompt, unit=unit)
        cached = self.evidence_store.get_shared_artifact(key)
        if cached is not None:
            if not isinstance(cached, list) or any(
                not isinstance(item, Mapping) for item in cached
            ):
                raise ValueError(f"invalid cached contract artifact: {key}")
            return [dict(item) for item in cached]

        ledger = getattr(self.llm_client, "ledger", None)
        before = int(getattr(ledger, "actual_spent", 0))
        response = self.llm_client.generate(
            prompt,
            max_tokens=max_tokens,
            temperature=0.0,
            system_prompt=(
                "You are a source-grounded extraction engine. Output JSON only; "
                "all exact_span values must be copied verbatim from the supplied "
                "source document."
            ),
            operation=f"contract_{phase}_extraction",
            shared_key=key,
        )
        cacheable = True
        try:
            rows = self._parse_response(response)
        except ValueError as first_error:
            repair_prompt = (
                f"{prompt}\n\n"
                "FORMAT CORRECTION: The previous answer below did not contain "
                "a valid JSON array of objects. Re-read the source and return "
                "only the requested JSON object array. Do not add commentary "
                "or infer any unsupported value. Return [] when no row is "
                "supported.\n\nPrevious invalid answer:\n"
                f"{response}"
            )
            repaired = self.llm_client.generate(
                repair_prompt,
                max_tokens=max_tokens,
                temperature=0.0,
                system_prompt=(
                    "You are a source-grounded extraction engine. Output JSON "
                    "only; all exact_span values must be copied verbatim from "
                    "the supplied source document."
                ),
                operation=f"contract_{phase}_format_retry",
                shared_key=f"{key}:format-retry",
            )
            try:
                rows = self._parse_response(repaired)
            except ValueError:
                rows = (
                    self._recover_scalar_entity_response(
                        repaired, unit.text
                    )
                    or self._recover_scalar_entity_response(
                        response, unit.text
                    )
                    if phase == "entity"
                    else []
                )
                if rows:
                    logger.info(
                        "Recovered source-exact scalar entity response: "
                        "document=%s",
                        unit.document_id,
                    )
                else:
                    cacheable = False
                    logger.warning(
                        "Rejecting malformed contract extraction after one "
                        "format retry: phase=%s document=%s error=%s",
                        phase,
                        unit.document_id,
                        first_error,
                    )
        produced = max(0, int(getattr(ledger, "actual_spent", before)) - before)
        if cacheable:
            self.evidence_store.put_shared_artifact(
                key,
                stage="contract_extraction",
                payload=rows,
                producer_tokens=produced,
            )
        return rows

    def _budgeted_rows(
        self,
        *,
        target: str,
        phase: str,
        prompt: str,
        unit: DocumentUnit,
        max_tokens: int,
    ) -> Optional[List[Mapping[str, object]]]:
        """Return cached/generated rows or mark a resumable budget boundary."""

        try:
            return self._rows(
                phase=phase,
                prompt=prompt,
                unit=unit,
                max_tokens=max_tokens,
            )
        except BudgetExhausted:
            self._budget_exhausted = True
            self._pending_target = target
            return None

    def _run_row_jobs(
        self,
        jobs: Sequence[Mapping[str, object]],
    ) -> Tuple[Optional[List[Mapping[str, object]]], ...]:
        """Dispatch independent document calls concurrently, preserving order."""
        if not jobs:
            return ()

        def run(job: Mapping[str, object]):
            return self._budgeted_rows(
                target=str(job["target"]),
                phase=str(job["phase"]),
                prompt=str(job["prompt"]),
                unit=job["unit"],
                max_tokens=int(job["max_tokens"]),
            )

        if self.max_workers == 1:
            return tuple(run(job) for job in jobs)
        system_prompt = (
            "You are a source-grounded extraction engine. Output JSON only; "
            "all exact_span values must be copied verbatim from the supplied "
            "source document."
        )

        def estimate(job: Mapping[str, object]) -> int:
            text = f"{system_prompt} {job['prompt']}"
            conservative = (len(text.encode("utf-8")) + 1) // 2
            try:
                prompt_tokens = max(count_tokens(text), conservative)
            except RuntimeError:
                prompt_tokens = conservative
            return prompt_tokens + int(job["max_tokens"])

        ledger = getattr(self.llm_client, "ledger", None)
        results: List[Optional[List[Mapping[str, object]]]] = []
        with ThreadPoolExecutor(
            max_workers=min(self.max_workers, len(jobs)),
            thread_name_prefix="contract-extract",
        ) as executor:
            for start in range(0, len(jobs), self.max_workers):
                wave = jobs[start : start + self.max_workers]
                affordable = (
                    ledger is None
                    or int(getattr(ledger, "available", 0))
                    >= sum(estimate(job) for job in wave)
                )
                if affordable:
                    results.extend(executor.map(run, wave))
                else:
                    # Near the boundary, dispatch in deterministic contract
                    # order so partial progress is reproducible.
                    results.extend(run(job) for job in wave)
        return tuple(results)

    @staticmethod
    def _scalar(value: object) -> bool:
        return (
            value is None
            or isinstance(value, (str, int, bool))
            or (isinstance(value, float) and math.isfinite(value))
        )

    def _records(
        self,
        *,
        phase: str,
        entity: str,
        attribute: Optional[str],
        unit: DocumentUnit,
        rows: Iterable[Mapping[str, object]],
        known_identities: Sequence[str] = (),
    ) -> Tuple[ExtractionRecord, ...]:
        """Accept only complete rows whose exact span occurs in this unit."""

        accepted: List[ExtractionRecord] = []
        anchors: List[EvidenceAnchor] = []
        for row in rows:
            if not {"identity", "value", "exact_span", "unit"} <= set(row):
                continue
            identity_value = row.get("identity")
            span_value = row.get("exact_span")
            value = row.get("value")
            unit_value = row.get("unit")
            if (
                not self._scalar(value)
                or identity_value is None
                or not isinstance(span_value, str)
                or (
                    unit_value is not None
                    and not isinstance(unit_value, (str, int, float))
                )
            ):
                continue
            identity = _canonical_identity(
                identity_value,
                known_identities,
            )
            exact_span = span_value
            if not identity or not exact_span:
                continue
            if phase == "attribute" and value in (None, ""):
                continue
            start = self._locate_exact_span(unit, exact_span)
            if start is None:
                # A case-insensitive or normalized match is not an exact span.
                continue
            record = ExtractionRecord(
                entity=entity,
                attribute=attribute,
                identity=identity,
                value=value,
                exact_span=exact_span,
                unit=(
                    str(unit_value).strip()
                    if unit_value is not None and str(unit_value).strip()
                    else None
                ),
                document_id=unit.document_id,
                unit_id=unit.unit_id,
                span_start=start,
                span_end=start + len(exact_span),
            )
            accepted.append(record)
            anchors.append(
                EvidenceAnchor.create(
                    document_id=unit.document_id,
                    text=exact_span,
                    start=record.span_start,
                    end=record.span_end,
                    anchor_type=f"contract_{phase}_span",
                    metadata={
                        "unit_id": unit.unit_id,
                        "entity": entity,
                        "attribute": attribute,
                        "identity": identity,
                        "unit": record.unit,
                    },
                )
            )
        if anchors:
            self.evidence_store.add_anchors(anchors)
        return tuple(accepted)

    def _relationship_records(
        self,
        *,
        relationship: RelationshipContract,
        unit: DocumentUnit,
        rows: Iterable[Mapping[str, object]],
        left_identities: Sequence[str] = (),
        right_identities: Sequence[str] = (),
    ) -> Tuple[RelationshipRecord, ...]:
        """Accept explicit edges only when their complete span is verbatim."""

        accepted: List[RelationshipRecord] = []
        anchors: List[EvidenceAnchor] = []
        for row in rows:
            if not {
                "left_identity",
                "right_identity",
                "exact_span",
            } <= set(row):
                continue
            left_identity = _canonical_identity(
                row.get("left_identity"),
                left_identities,
            )
            right_identity = _canonical_identity(
                row.get("right_identity"),
                right_identities,
            )
            exact_span = row.get("exact_span")
            if (
                not left_identity
                or not right_identity
                or not isinstance(exact_span, str)
                or not exact_span
            ):
                continue
            start = self._locate_exact_span(unit, exact_span)
            if start is None:
                continue
            record = RelationshipRecord(
                relationship=relationship.name,
                left_entity=relationship.left_entity,
                right_entity=relationship.right_entity,
                left_identity=left_identity,
                right_identity=right_identity,
                exact_span=exact_span,
                document_id=unit.document_id,
                unit_id=unit.unit_id,
                span_start=start,
                span_end=start + len(exact_span),
            )
            accepted.append(record)
            anchors.append(
                EvidenceAnchor.create(
                    document_id=unit.document_id,
                    text=exact_span,
                    start=record.span_start,
                    end=record.span_end,
                    anchor_type="contract_relationship_span",
                    metadata={
                        "unit_id": unit.unit_id,
                        "relationship": relationship.name,
                        "left_entity": relationship.left_entity,
                        "right_entity": relationship.right_entity,
                        "left_identity": left_identity,
                        "right_identity": right_identity,
                    },
                )
            )
        if anchors:
            self.evidence_store.add_anchors(anchors)
        return tuple(accepted)

    def extract_entities(
        self, contract: WorkloadContract
    ) -> Tuple[ExtractionRecord, ...]:
        """Complete the entity-discovery phase for the whole contract."""

        result: List[ExtractionRecord] = []
        jobs: List[dict] = []
        contexts: List[Tuple[EntityContract, DocumentUnit]] = []
        for entity in contract.entities:
            for source_unit in self.documents_for_entity(entity):
                heading = self._partition_heading_identity(
                    entity, source_unit
                )
                if heading is not None:
                    result.extend(
                        self._records(
                            phase="entity",
                            entity=entity.name,
                            attribute=None,
                            unit=source_unit,
                            rows=(
                                {
                                    "identity": heading,
                                    "value": heading,
                                    "exact_span": heading,
                                    "unit": None,
                                },
                            ),
                        )
                    )
                    continue
                unit = self._focused_unit(source_unit, lead_only=True)
                prompt = self._entity_prompt(entity, unit)
                contexts.append((entity, unit))
                jobs.append(
                    {
                        "target": (
                            f"entity:{entity.name}:{unit.document_id}"
                        ),
                        "phase": "entity",
                        "prompt": prompt,
                        "unit": unit,
                        "max_tokens": self.max_entity_tokens,
                    }
                )
        for (entity, unit), rows in zip(
            contexts, self._run_row_jobs(jobs)
        ):
            if rows is not None:
                result.extend(
                    self._records(
                        phase="entity",
                        entity=entity.name,
                        attribute=None,
                        unit=unit,
                        rows=rows,
                    )
                )
        return tuple(result)

    def extract_attributes(
        self,
        contract: WorkloadContract,
        entity_records: Sequence[ExtractionRecord],
    ) -> Tuple[ExtractionRecord, ...]:
        """Extract one contract field per prompt after entity discovery."""

        identities: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        for record in entity_records:
            key = (_symbol_key(record.entity), record.document_id)
            if record.identity not in identities[key]:
                identities[key].append(record.identity)

        result: List[ExtractionRecord] = []
        if self._budget_exhausted:
            return ()
        heading_keys = {
            (
                _symbol_key(record.entity),
                _symbol_key(record.attribute),
                record.document_id,
            )
            for record in self._derive_heading_attributes(
                contract, entity_records
            )
        }

        def priority(attribute: AttributeContract) -> tuple:
            roles = {
                role.split(":", 1)[0]
                for _query_id, query_roles in attribute.contexts
                for role in query_roles
            }
            weights = {
                "join": 0,
                "filter": 1,
                "aggregate": 2,
                "having": 2,
                "group_by": 3,
                "projection": 4,
                "binding": 5,
                "mentioned": 6,
            }
            return (
                min((weights.get(role, 7) for role in roles), default=7),
                -len(attribute.query_ids),
                attribute.entity,
                attribute.name,
            )

        jobs: List[dict] = []
        contexts: List[
            Tuple[
                AttributeContract,
                str,
                DocumentUnit,
                Tuple[str, ...],
            ]
        ] = []
        for attribute in sorted(contract.attributes, key=priority):
            owners = attribute.owners or ("",)
            for owner in owners:
                owner_contract = contract.entity(owner) if owner else None
                units = (
                    self.documents_for_entity(owner_contract or owner)
                    if owner
                    else self.units
                )
                terms = (
                    attribute.name,
                    *attribute.alternatives,
                    *attribute.units,
                    *dict(attribute.query_hints).values(),
                )
                for source_unit in units:
                    if (
                        _symbol_key(owner),
                        _symbol_key(attribute.name),
                        source_unit.document_id,
                    ) in heading_keys:
                        continue
                    unit = self._focused_unit(source_unit, terms=terms)
                    known = tuple(
                        identities.get(
                            (_symbol_key(owner), unit.document_id),
                            [],
                        )
                    )
                    prompt = self._attribute_prompt(
                        attribute, owner, unit, known
                    )
                    contexts.append((attribute, owner, unit, known))
                    jobs.append(
                        {
                            "target": (
                                f"attribute:{owner}:{attribute.name}:"
                                f"{unit.document_id}"
                            ),
                            "phase": "attribute",
                            "prompt": prompt,
                            "unit": unit,
                            "max_tokens": self.max_attribute_tokens,
                        }
                    )
        for (attribute, owner, unit, known), rows in zip(
            contexts, self._run_row_jobs(jobs)
        ):
            if rows is not None:
                result.extend(
                    self._records(
                        phase="attribute",
                        entity=owner,
                        attribute=attribute.name,
                        unit=unit,
                        rows=rows,
                        known_identities=known,
                    )
                )
        return tuple(result)

    def _derive_calculated_attributes(
        self,
        contract: WorkloadContract,
        entity_records: Sequence[ExtractionRecord],
        attribute_records: Sequence[ExtractionRecord],
    ) -> Tuple[ExtractionRecord, ...]:
        """Let the model request deterministic tools for missing numeric fields."""

        if self._budget_exhausted:
            return ()
        existing = {
            (
                _symbol_key(record.entity),
                _symbol_key(record.attribute),
                record.document_id,
            )
            for record in attribute_records
            if record.attribute is not None
            and record.value not in (None, "")
        }
        numeric = tuple(
            attribute
            for attribute in contract.attributes
            if set(attribute.semantic_types) & {"integer", "real"}
        )
        result: List[ExtractionRecord] = []
        for entity_record in entity_records:
            owner = _symbol_key(entity_record.entity)
            missing = [
                attribute
                for attribute in numeric
                if owner
                in {_symbol_key(value) for value in attribute.owners}
                and (
                    owner,
                    _symbol_key(attribute.name),
                    entity_record.document_id,
                )
                not in existing
            ]
            if not missing:
                continue
            source_unit = next(
                (
                    unit
                    for unit in self.units
                    if unit.document_id == entity_record.document_id
                ),
                None,
            )
            if source_unit is None:
                continue
            terms = tuple(
                value
                for attribute in missing
                for value in (
                    attribute.name,
                    *attribute.alternatives,
                    *dict(attribute.query_hints).values(),
                )
            )
            unit = self._focused_unit(source_unit, terms=terms)
            contracts = [
                {
                    "attribute": attribute.name,
                    "semantic_types": list(attribute.semantic_types),
                    "units": list(attribute.units),
                    "query_hints": dict(attribute.query_hints),
                }
                for attribute in missing
            ]
            prompt = (
                "Decide whether any missing numeric attribute below can be "
                "calculated exactly from explicit facts in the source. Do not "
                "guess and do not perform arithmetic yourself. Request a tool "
                "only when all required source operands and their association "
                "with the known identity are explicit.\n\n"
                "Available tools:\n"
                "1. calculator(operation, operands), where operation is one of "
                "add, subtract, multiply, divide, minimum, maximum, count.\n"
                "2. corpus_reference_year(), whose current result is "
                f"{self.reference_year}. This is the fixed corpus clock "
                "for time-relative attributes; use it only when the "
                "requested attribute is explicitly time-relative and the "
                "source provides the other temporal operand.\n\n"
                "Return only a JSON array. Each tool request must have exactly "
                "identity, attribute, tool, operation, operands, "
                "source_operands, exact_span, and unit. tool must be "
                "\"calculator\". operands are passed to the calculator in "
                "order. source_operands lists only operands copied from "
                "exact_span; a corpus_reference_year operand is not a source "
                "operand. exact_span must be one verbatim case-sensitive source "
                "substring supporting the identity and every source operand. "
                "Return [] when no exact derivation is warranted.\n\n"
                f"Known identity: {entity_record.identity}\n"
                f"Missing attribute contracts: {json.dumps(contracts, sort_keys=True)}"
                "\n\nVerbatim source evidence excerpt(s):\n"
                f"{unit.text}"
            )
            rows = self._budgeted_rows(
                target=f"calculation:{entity_record.entity}:{unit.document_id}",
                phase="calculation",
                prompt=prompt,
                unit=unit,
                max_tokens=max(self.max_attribute_tokens, 768),
            )
            if rows is None:
                break
            allowed = {
                _symbol_key(attribute.name): attribute
                for attribute in missing
            }
            for row in rows:
                if set(row) != {
                    "identity",
                    "attribute",
                    "tool",
                    "operation",
                    "operands",
                    "source_operands",
                    "exact_span",
                    "unit",
                }:
                    continue
                attribute = allowed.get(
                    _symbol_key(row.get("attribute", ""))
                )
                operands = row.get("operands")
                source_operands = row.get("source_operands")
                exact_span = row.get("exact_span")
                if (
                    attribute is None
                    or row.get("tool") != "calculator"
                    or not isinstance(operands, list)
                    or not isinstance(source_operands, list)
                    or not isinstance(exact_span, str)
                    or not operands_are_grounded(
                        operands,
                        source_operands,
                        exact_span,
                        corpus_reference_year=self.reference_year,
                    )
                ):
                    continue
                offset = self._locate_exact_span(unit, exact_span)
                if offset is None:
                    continue
                try:
                    value = calculate(str(row.get("operation")), operands)
                except ValueError:
                    continue
                if (
                    set(attribute.semantic_types) == {"integer"}
                    and not isinstance(value, int)
                ):
                    continue
                identity = _canonical_identity(
                    str(row.get("identity", "")),
                    (entity_record.identity,),
                )
                result.append(
                    ExtractionRecord(
                        entity=entity_record.entity,
                        attribute=attribute.name,
                        identity=identity,
                        value=value,
                        exact_span=exact_span,
                        unit=(
                            str(row["unit"])
                            if row.get("unit") is not None
                            else None
                        ),
                        document_id=unit.document_id,
                        unit_id=unit.unit_id,
                        span_start=offset,
                        span_end=offset + len(exact_span),
                        derivation_kind="tool_calculation",
                        derivation_inputs={
                            "tool": "calculator",
                            "operation": str(row.get("operation")),
                            "operands": list(operands),
                            "source_operands": list(source_operands),
                            "corpus_reference_year": self.reference_year,
                        },
                    )
                )
        return tuple(result)

    def _derive_heading_attributes(
        self,
        contract: WorkloadContract,
        entity_records: Sequence[ExtractionRecord],
    ) -> Tuple[ExtractionRecord, ...]:
        """Project explicit document-heading labels into requested text fields."""

        result: List[ExtractionRecord] = []
        for attribute in contract.attributes:
            if "text" not in attribute.semantic_types:
                continue
            symbols = {_symbol_key(value) for value in attribute.symbols}
            mode = next(
                (
                    candidate
                    for candidate in (
                        "name",
                        "label",
                        "title",
                        "state",
                        "province",
                        "region",
                    )
                    if candidate in symbols
                ),
                None,
            )
            if mode is None:
                continue
            owner_keys = {_symbol_key(owner) for owner in attribute.owners}
            for entity_record in entity_records:
                if _symbol_key(entity_record.entity) not in owner_keys:
                    continue
                heading = entity_record.exact_span.strip()
                if not heading:
                    continue
                if mode in {"state", "province", "region"}:
                    if "," not in heading:
                        continue
                    value = heading.rsplit(",", 1)[1].strip()
                else:
                    value = heading.split(",", 1)[0].strip()
                if not value:
                    continue
                result.append(
                    ExtractionRecord(
                        entity=entity_record.entity,
                        attribute=attribute.name,
                        identity=entity_record.identity,
                        value=value,
                        exact_span=heading,
                        unit=None,
                        document_id=entity_record.document_id,
                        unit_id=entity_record.unit_id,
                        span_start=entity_record.span_start,
                        span_end=entity_record.span_end,
                        derivation_kind="heading_component",
                        derivation_inputs={"component": mode},
                    )
                )
        return tuple(result)

    def documents_for_relationship(
        self,
        relationship: RelationshipContract,
        contract: Optional[WorkloadContract] = None,
    ) -> Tuple[DocumentUnit, ...]:
        """Route edge extraction to either endpoint's available partition."""

        endpoint_keys: set[str] = set()
        for endpoint in (
            relationship.left_entity,
            relationship.right_entity,
        ):
            entity = contract.entity(endpoint) if contract is not None else None
            endpoint_keys.update(
                _symbol_key(value)
                for value in (entity.symbols if entity is not None else (endpoint,))
            )
        matched = tuple(
            unit
            for unit in self.units
            if self._prefix(unit.document_id) in endpoint_keys
        )
        return matched or self.units

    def extract_relationships(
        self,
        contract: WorkloadContract,
        entity_records: Sequence[ExtractionRecord],
    ) -> Tuple[RelationshipRecord, ...]:
        """Extract explicit contract edges after entity discovery."""

        if self._budget_exhausted:
            return ()
        identities: Dict[str, List[str]] = defaultdict(list)
        local_identities: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        for record in entity_records:
            key = _symbol_key(record.entity)
            if record.identity not in identities[key]:
                identities[key].append(record.identity)
            local_key = (key, record.document_id)
            if record.identity not in local_identities[local_key]:
                local_identities[local_key].append(record.identity)

        def identities_for_unit(
            entity: str,
            unit: DocumentUnit,
        ) -> Tuple[str, ...]:
            key = _symbol_key(entity)
            selected = list(
                local_identities.get((key, unit.document_id), ())
            )
            text_key = _symbol_key(unit.text)
            for identity in identities.get(key, ()):
                identity_key = _symbol_key(identity)
                identity_tokens = identity_key.split("_")
                if (
                    identity not in selected
                    and (
                        identity_key in text_key
                        or any(
                            len(token) >= 4 and token in text_key
                            for token in identity_tokens
                        )
                    )
                ):
                    selected.append(identity)
                if len(selected) >= 24:
                    break
            return tuple(selected)

        result: List[RelationshipRecord] = []
        jobs: List[dict] = []
        contexts: List[
            Tuple[
                RelationshipContract,
                DocumentUnit,
                Tuple[str, ...],
                Tuple[str, ...],
            ]
        ] = []
        for relationship in contract.relationships:
            terms = (
                relationship.name,
                *relationship.alternatives,
                relationship.left_entity,
                relationship.right_entity,
                *relationship.left_attributes,
                *relationship.right_attributes,
                *dict(relationship.query_hints).values(),
            )
            for source_unit in self.documents_for_relationship(
                relationship, contract
            ):
                unit = self._focused_unit(source_unit, terms=terms)
                left_identities = identities_for_unit(
                    relationship.left_entity, unit
                )
                right_identities = identities_for_unit(
                    relationship.right_entity, unit
                )
                prompt = self._relationship_prompt(
                    relationship,
                    unit,
                    left_identities,
                    right_identities,
                )
                contexts.append(
                    (
                        relationship,
                        unit,
                        left_identities,
                        right_identities,
                    )
                )
                jobs.append(
                    {
                        "target": (
                            f"relationship:{relationship.name}:"
                            f"{unit.document_id}"
                        ),
                        "phase": "relationship",
                        "prompt": prompt,
                        "unit": unit,
                        "max_tokens": self.max_attribute_tokens,
                    }
                )
        for (
            relationship,
            unit,
            left_identities,
            right_identities,
        ), rows in zip(
            contexts, self._run_row_jobs(jobs)
        ):
            if rows is not None:
                result.extend(
                    self._relationship_records(
                        relationship=relationship,
                        unit=unit,
                        rows=rows,
                        left_identities=left_identities,
                        right_identities=right_identities,
                    )
                )
        return tuple(result)

    @staticmethod
    def _unit_scale(unit: Optional[str]) -> Optional[float]:
        rendered = str(unit or "").strip().casefold()
        if not rendered:
            return None
        for pattern, scale in (
            (r"\btrillions?\b", 1_000_000_000_000.0),
            (r"\bbillions?\b", 1_000_000_000.0),
            (r"\bmillions?\b", 1_000_000.0),
            (r"\bthousands?\b", 1_000.0),
        ):
            if re.search(pattern, rendered):
                return scale
        return 1.0

    def _unit_mappings(
        self,
        contract: WorkloadContract,
        records: Sequence[ExtractionRecord],
    ) -> Tuple[DerivationMapping, ...]:
        result: List[DerivationMapping] = []
        for attribute in contract.attributes:
            candidates = [
                record
                for record in records
                if _symbol_key(record.entity)
                in {_symbol_key(owner) for owner in attribute.owners}
                and _symbol_key(record.attribute)
                == _symbol_key(attribute.name)
                and isinstance(record.value, (int, float))
                and not isinstance(record.value, bool)
                and record.unit
            ]
            target_unit, target_scale = next(
                (
                    (unit, scale)
                    for unit in attribute.units
                    if (scale := self._unit_scale(unit)) is not None
                ),
                (None, 1.0),
            )
            scales_by_value: Dict[str, set[float]] = defaultdict(set)
            for record in candidates:
                source_scale = self._unit_scale(record.unit)
                if source_scale is not None:
                    scales_by_value[
                        json.dumps(record.value, sort_keys=True)
                    ].add(source_scale)
            for record in candidates:
                source_scale = self._unit_scale(record.unit)
                key = json.dumps(record.value, sort_keys=True)
                if (
                    source_scale is None
                    or len(scales_by_value[key]) != 1
                ):
                    continue
                converted = (
                    float(record.value) * source_scale / target_scale
                )
                target_value: object = (
                    int(converted) if converted.is_integer() else converted
                )
                if target_value == record.value and (
                    not target_unit
                    or _symbol_key(target_unit)
                    == _symbol_key(record.unit)
                ):
                    continue
                result.append(
                    DerivationMapping(
                        entity=record.entity,
                        attribute=attribute.name,
                        source_value=record.value,
                        target_value=target_value,
                        mapping_kind="unit",
                        source_unit=record.unit,
                        target_unit=target_unit,
                        supporting_document_ids=(record.document_id,),
                    )
                )
        return tuple(result)

    @staticmethod
    def _casefold_taxonomy_mappings(
        attribute: AttributeContract,
        candidates: Sequence[ExtractionRecord],
    ) -> Tuple[DerivationMapping, ...]:
        """Collapse pure case/whitespace variants without an LLM call."""

        surfaces: Dict[str, List[str]] = {}
        documents: Dict[str, set[str]] = {}
        for record in candidates:
            value = str(record.value).strip()
            key = " ".join(value.casefold().split())
            if not key:
                continue
            surfaces.setdefault(key, []).append(value)
            documents.setdefault(key, set()).add(record.document_id)
        mappings: List[DerivationMapping] = []
        for key, variants in surfaces.items():
            if len(set(variants)) < 2:
                continue
            # Prefer the most frequent surface, then lexicographically stable.
            counts: Dict[str, int] = {}
            for value in variants:
                counts[value] = counts.get(value, 0) + 1
            canonical = sorted(
                counts,
                key=lambda value: (-counts[value], value),
            )[0]
            for source in sorted(set(variants)):
                if source == canonical:
                    continue
                mappings.append(
                    DerivationMapping(
                        entity=attribute.entity,
                        attribute=attribute.name,
                        source_value=source,
                        target_value=canonical,
                        mapping_kind="taxonomy",
                        supporting_document_ids=tuple(
                            sorted(documents.get(key, ()))
                        ),
                    )
                )
        return tuple(mappings)

    def _taxonomy_mappings(
        self,
        contract: WorkloadContract,
        records: Sequence[ExtractionRecord],
    ) -> Tuple[DerivationMapping, ...]:
        if self._budget_exhausted:
            return ()
        result: List[DerivationMapping] = []
        for attribute in contract.attributes:
            roles = {
                role
                for _query_id, query_roles in attribute.contexts
                for role in query_roles
            }
            if (
                "group_by" not in roles
                or any(role.startswith("filter:") for role in roles)
                or set(attribute.semantic_types) != {"text"}
            ):
                continue
            candidates = [
                record
                for record in records
                if _symbol_key(record.entity)
                in {_symbol_key(owner) for owner in attribute.owners}
                and _symbol_key(record.attribute)
                == _symbol_key(attribute.name)
                and isinstance(record.value, str)
                and record.value.strip()
            ]
            values = tuple(
                sorted({str(record.value).strip() for record in candidates})
            )
            if len(values) < 2:
                continue
            result.extend(
                self._casefold_taxonomy_mappings(attribute, candidates)
            )
            case_variants = len(
                {" ".join(value.casefold().split()) for value in values}
            )
            if case_variants < 2:
                continue
            prompt = (
                "Choose the categorical representation that most directly "
                "answers the natural-language workload. When observed values "
                "are aliases, labels for instances, spelling/case variants, "
                "compound labels, or finer subcategories of the concept "
                "requested by the query, map them to consistent canonical "
                "values at the requested semantic level. If the workload "
                "groups by a concept that is naturally coarser than the "
                "observed instance labels, map every observed value onto that "
                "coarser mutually exclusive taxonomy. Preserve distinct values "
                "only when the query asks for that detailed level; do not "
                "reduce cardinality merely for convenience. Raw grouping is "
                "not coherent when observed labels mix atomic categories, "
                "compound categories, free-form descriptions, and spelling or "
                "case variants; in that situation choose the smallest "
                "conventional mutually exclusive taxonomy justified by ordinary "
                "language, and map non-values to null. If no semantic "
                "mapping is justified, return []. Otherwise return only a "
                "JSON array whose objects have exactly source_value and "
                "target_value. source_value must be copied exactly from "
                "observed_values. Every observed_value should appear at most "
                "once as source_value. Include every observed value when a "
                "coarser taxonomy is proposed; a partial taxonomy is invalid. "
                "target_value must be a canonical string, or null when the "
                "source label is not actually a value of the requested "
                "attribute. target_value must be justified solely "
                "by the NL workload, observed labels, and ordinary language "
                "meaning; it must not encode an expected benchmark answer.\n\n"
                f"Entity: {attribute.entity}\n"
                f"Attribute: {attribute.name}\n"
                "Natural-language workload hints: "
                f"{json.dumps(dict(attribute.query_hints), sort_keys=True)}\n"
                f"Observed value count: {len(values)}\n"
                f"Case-insensitive unique count: {case_variants}\n"
                f"Observed values: {json.dumps(values)}"
            )
            supporting_documents = {
                record.document_id for record in candidates
            }
            representative = next(
                (
                    unit
                    for unit in self.units
                    if unit.document_id in supporting_documents
                ),
                self.units[0],
            )
            rows = self._budgeted_rows(
                target=(
                    f"taxonomy:{attribute.entity}:"
                    f"{attribute.name}"
                ),
                phase="taxonomy",
                prompt=prompt,
                unit=representative,
                max_tokens=max(
                    self.max_attribute_tokens,
                    min(2_048, 96 * len(values)),
                ),
            )
            if rows is None:
                break
            mapping: Dict[str, object] = {}
            for row in rows:
                if set(row) != {"source_value", "target_value"}:
                    continue
                source = row.get("source_value")
                target = row.get("target_value")
                if (
                    not isinstance(source, str)
                    or source not in values
                    or (
                        target is not None
                        and (
                            not isinstance(target, str)
                            or not target.strip()
                        )
                    )
                ):
                    continue
                mapping[source] = (
                    target.strip() if isinstance(target, str) else None
                )
            # Propagate case-insensitive targets to every observed surface form.
            by_case = {
                source.casefold(): target
                for source, target in mapping.items()
            }
            for value in values:
                if value.casefold() in by_case:
                    mapping[value] = by_case[value.casefold()]
            missing = sorted(set(values) - set(mapping))
            if mapping and missing:
                repair_prompt = (
                    "Complete an otherwise valid categorical mapping. Return "
                    "only a JSON array whose objects have exactly source_value "
                    "and target_value. Include every missing source exactly "
                    "once. source_value must be copied exactly from "
                    "missing_observed_values. Use the same taxonomy already "
                    "chosen in accepted_mapping. target_value must be a "
                    "canonical string, or null when the source label is not "
                    "actually a value of the requested attribute. Do not alter "
                    "or repeat accepted mappings.\n\n"
                    f"Entity: {attribute.entity}\n"
                    f"Attribute: {attribute.name}\n"
                    "Natural-language workload hints: "
                    f"{json.dumps(dict(attribute.query_hints), sort_keys=True)}\n"
                    f"Accepted mapping: {json.dumps(mapping, sort_keys=True)}\n"
                    f"Missing observed values: {json.dumps(missing)}"
                )
                repair_rows = self._budgeted_rows(
                    target=(
                        f"taxonomy-repair:{attribute.entity}:"
                        f"{attribute.name}"
                    ),
                    phase="taxonomy",
                    prompt=repair_prompt,
                    unit=representative,
                    max_tokens=max(
                        self.max_attribute_tokens,
                        min(2_048, 96 * len(missing)),
                    ),
                )
                if repair_rows is None:
                    break
                for row in repair_rows:
                    if set(row) != {"source_value", "target_value"}:
                        continue
                    source = row.get("source_value")
                    target = row.get("target_value")
                    if (
                        not isinstance(source, str)
                        or source not in missing
                        or (
                            target is not None
                            and (
                                not isinstance(target, str)
                                or not target.strip()
                            )
                        )
                    ):
                        continue
                    mapping[source] = (
                        target.strip()
                        if isinstance(target, str)
                        else None
                    )
            # Mixed raw/canonical values are worse than no taxonomy because
            # they create incompatible grouping levels.
            if set(mapping) != set(values):
                continue
            if all(
                isinstance(target, str)
                and source.casefold() == target.casefold()
                for source, target in mapping.items()
            ):
                continue
            for source, target in sorted(mapping.items()):
                result.append(
                    DerivationMapping(
                        entity=attribute.entity,
                        attribute=attribute.name,
                        source_value=source,
                        target_value=target,
                        mapping_kind="taxonomy",
                        supporting_document_ids=tuple(
                            sorted(
                                {
                                    record.document_id
                                    for record in candidates
                                    if str(record.value).strip() == source
                                }
                            )
                        ),
                    )
                )
        return tuple(result)

    def derive_mappings(
        self,
        contract: WorkloadContract,
        records: Sequence[ExtractionRecord],
    ) -> Tuple[DerivationMapping, ...]:
        """Build explicit reversible mappings after raw extraction."""
        return (
            *self._unit_mappings(contract, records),
            *self._taxonomy_mappings(contract, records),
        )

    @staticmethod
    def _target_value(target: object, name: str, default: object = None) -> object:
        if isinstance(target, Mapping):
            return target.get(name, default)
        return getattr(target, name, default)

    def repair_target(
        self,
        contract: WorkloadContract,
        target: object,
        *,
        entity_records: Sequence[ExtractionRecord] = (),
        rejected_record: Optional[object] = None,
    ) -> Tuple[ExtractionRecord | RelationshipRecord, ...]:
        """Budget one repair prompt for one validation-addressed target.

        ``target`` may be a validation ``RepairTarget`` or a mapping with
        ``phase``, ``document_id``, entity/field/relationship names, and
        ``issue_codes``. The method never broadens a repair to other documents
        or symbols and returns an empty tuple at a budget boundary.
        """

        document_id = str(
            self._target_value(target, "document_id", "") or ""
        )
        unit = next(
            (item for item in self.units if item.document_id == document_id),
            None,
        )
        if unit is None:
            raise ValueError(f"unknown repair document: {document_id}")
        phase = str(self._target_value(target, "phase", "") or "")
        entity = str(self._target_value(target, "entity", "") or "")
        attribute_name = self._target_value(target, "attribute")
        relationship_name = self._target_value(target, "relationship")
        issue_codes = tuple(
            str(value)
            for value in (
                self._target_value(target, "issue_codes", ()) or ()
            )
        )
        correction = (
            "\n\nTargeted repair: correct only these validation failures: "
            f"{json.dumps(issue_codes)}. Do not change or emit any other target."
        )
        if rejected_record is not None:
            payload = (
                rejected_record.to_payload()
                if hasattr(rejected_record, "to_payload")
                else rejected_record
            )
            correction += (
                "\nRejected record (use only to correct the listed failures):\n"
                + json.dumps(payload, sort_keys=True, default=str)
            )

        if phase == "entity":
            entity_contract = contract.entity(entity)
            if entity_contract is None:
                raise ValueError(f"unknown repair entity: {entity}")
            unit = self._focused_unit(unit, lead_only=True)
            prompt = self._entity_prompt(entity_contract, unit) + correction
            rows = self._budgeted_rows(
                target=f"repair:entity:{entity}:{document_id}",
                phase="repair_entity",
                prompt=prompt,
                unit=unit,
                max_tokens=self.max_entity_tokens,
            )
            return (
                self._records(
                    phase="entity",
                    entity=entity_contract.name,
                    attribute=None,
                    unit=unit,
                    rows=rows,
                )
                if rows is not None
                else ()
            )

        if phase == "attribute":
            attribute = next(
                (
                    item
                    for item in contract.attributes
                    if _symbol_key(item.name)
                    == _symbol_key(attribute_name)
                    and (
                        not item.owners
                        or _symbol_key(entity)
                        in {_symbol_key(owner) for owner in item.owners}
                    )
                ),
                None,
            )
            if attribute is None:
                raise ValueError(
                    f"unknown repair attribute: {entity}.{attribute_name}"
                )
            unit = self._focused_unit(
                unit,
                terms=(
                    attribute.name,
                    *attribute.alternatives,
                    *attribute.units,
                    *dict(attribute.query_hints).values(),
                ),
            )
            identities = tuple(
                record.identity
                for record in entity_records
                if _symbol_key(record.entity) == _symbol_key(entity)
                and record.document_id == document_id
            )
            prompt = (
                self._attribute_prompt(attribute, entity, unit, identities)
                + correction
            )
            rows = self._budgeted_rows(
                target=(
                    f"repair:attribute:{entity}:{attribute.name}:{document_id}"
                ),
                phase="repair_attribute",
                prompt=prompt,
                unit=unit,
                max_tokens=self.max_attribute_tokens,
            )
            return (
                self._records(
                    phase="attribute",
                    entity=entity,
                    attribute=attribute.name,
                    unit=unit,
                    rows=rows,
                    known_identities=identities,
                )
                if rows is not None
                else ()
            )

        if phase == "relationship":
            relationship = next(
                (
                    item
                    for item in contract.relationships
                    if _symbol_key(item.name)
                    == _symbol_key(relationship_name)
                    or _symbol_key(relationship_name)
                    in {
                        _symbol_key(value)
                        for value in item.alternatives
                    }
                ),
                None,
            )
            if relationship is None:
                raise ValueError(
                    f"unknown repair relationship: {relationship_name}"
                )
            unit = self._focused_unit(
                unit,
                terms=(
                    relationship.name,
                    *relationship.alternatives,
                    relationship.left_entity,
                    relationship.right_entity,
                    *relationship.left_attributes,
                    *relationship.right_attributes,
                    *dict(relationship.query_hints).values(),
                ),
            )
            by_entity: Dict[str, List[str]] = defaultdict(list)
            for record in entity_records:
                by_entity[_symbol_key(record.entity)].append(record.identity)
            prompt = (
                self._relationship_prompt(
                    relationship,
                    unit,
                    by_entity[_symbol_key(relationship.left_entity)],
                    by_entity[_symbol_key(relationship.right_entity)],
                )
                + correction
            )
            rows = self._budgeted_rows(
                target=(
                    f"repair:relationship:{relationship.name}:{document_id}"
                ),
                phase="repair_relationship",
                prompt=prompt,
                unit=unit,
                max_tokens=self.max_attribute_tokens,
            )
            return (
                self._relationship_records(
                    relationship=relationship,
                    unit=unit,
                    rows=rows,
                    left_identities=by_entity[
                        _symbol_key(relationship.left_entity)
                    ],
                    right_identities=by_entity[
                        _symbol_key(relationship.right_entity)
                    ],
                )
                if rows is not None
                else ()
            )
        raise ValueError(f"unsupported repair phase: {phase}")

    def extract(self, contract: WorkloadContract) -> ContractExtraction:
        """Return all affordable progress instead of raising on budget exhaustion."""

        self._budget_exhausted = False
        self._pending_target = None
        entity_records = self.extract_entities(contract)
        relationship_records = self.extract_relationships(
            contract, entity_records
        )
        heading_records = self._derive_heading_attributes(
            contract, entity_records
        )
        heading_keys = {
            (
                _symbol_key(record.entity),
                _symbol_key(record.attribute),
                record.document_id,
            )
            for record in heading_records
        }
        extracted_attributes = tuple(
            record
            for record in self.extract_attributes(
                contract, entity_records
            )
            if (
                _symbol_key(record.entity),
                _symbol_key(record.attribute),
                record.document_id,
            )
            not in heading_keys
        )
        direct_attribute_records = (
            *heading_records,
            *extracted_attributes,
        )
        attribute_records = (
            *direct_attribute_records,
            *self._derive_calculated_attributes(
                contract,
                entity_records,
                direct_attribute_records,
            ),
        )
        derivation_mappings = self.derive_mappings(
            contract, attribute_records
        )
        return ContractExtraction(
            contract_fingerprint=contract.fingerprint,
            entity_records=entity_records,
            attribute_records=attribute_records,
            relationship_records=relationship_records,
            derivation_mappings=derivation_mappings,
            complete=not self._budget_exhausted,
            budget_exhausted=self._budget_exhausted,
            pending_target=self._pending_target,
        )

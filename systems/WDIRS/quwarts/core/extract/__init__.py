"""Least-commitment evidence store and staged extractor."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Callable, Iterable

from collections import defaultdict

from quwarts.core.ledger import BudgetExhausted, BudgetedCaller, TokenLedger
from quwarts.core.models import (
    AttributeRequirement,
    EvidenceRecord,
    Role,
    SliceSpec,
    SourceDocument,
    Template,
    Workload,
)
from quwarts.core.preprocess import Segment, segment_documents, policy_hash
from quwarts.core.models import PreprocessPolicy

_OTHER = "other"


ExtractorFn = Callable[[Segment, str, str], tuple[str | None, Any, int]]


def evidence_key(segment_id: str, attribute: str, extractor_cfg_hash: str, quality_tier: str) -> str:
    payload = f"{segment_id}|{attribute}|{extractor_cfg_hash}|{quality_tier}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EvidenceStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else None
        self.records: dict[str, EvidenceRecord] = {}
        self.lookups = 0
        self.hits = 0
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self) -> None:
        for path in self.root.glob("*.json"):
            payload = json.loads(path.read_text())
            record = EvidenceRecord.model_validate(payload)
            self.records[record.key] = record

    def get(
        self,
        segment_id: str,
        attribute: str,
        extractor_cfg_hash: str,
        quality_tier: str,
    ) -> EvidenceRecord | None:
        self.lookups += 1
        key = evidence_key(segment_id, attribute, extractor_cfg_hash, quality_tier)
        record = self.records.get(key)
        if record is not None:
            self.hits += 1
        return record

    def put(self, record: EvidenceRecord) -> EvidenceRecord:
        existing = self.records.get(record.key)
        if existing is not None:
            self.hits += 1
            return existing
        self.records[record.key] = record
        if self.root:
            (self.root / f"{record.key}.json").write_text(record.model_dump_json(indent=2))
        return record

    def cache_hit_rate(self) -> float:
        if self.lookups == 0:
            return 1.0 if self.records else 0.0
        return self.hits / self.lookups

    def for_attribute(self, attribute: str) -> list[EvidenceRecord]:
        return [row for row in self.records.values() if row.attribute == attribute]


def default_extractor(segment: Segment, attribute: str, tier: str) -> tuple[str | None, Any, int]:
    """Deterministic extractor used when no model is configured.

    Looks for ``attribute: value`` or ``Attribute value`` patterns. Token cost
    is a function of segment length so the ledger still moves.
    """

    bare = attribute.split(".")[-1]
    pattern = re.compile(
        rf"(?:{re.escape(bare)}|{re.escape(bare.replace('_', ' '))})\s*[:=-]?\s*([A-Za-z0-9$.,-]+)",
        re.IGNORECASE,
    )
    match = pattern.search(segment.text)
    tokens = max(1, math.ceil(len(segment.text) / (8 if tier == "cheap" else 4)))
    if match:
        surface = match.group(1).strip().rstrip(".")
        return surface, _parse(surface), tokens
    # last-resort: numbered value near the attribute word
    word = re.search(rf"{re.escape(bare)}\b", segment.text, re.IGNORECASE)
    if word:
        nearby = segment.text[word.start() : word.start() + 80]
        number = re.search(r"[-+]?\d[\d,]*\.?\d*", nearby)
        if number:
            return number.group(0), _parse(number.group(0)), tokens
    return None, None, tokens


_REFUSAL = re.compile(
    r"(sure, i can|as an ai|i cannot|i can't|json object|provided text does not)",
    re.IGNORECASE,
)


def validate_cell(value: Any, dtype: str = "string") -> tuple[str | None, Any, str | None]:
    """Reject non-scalars, dtype failures, and leftover model prose."""

    if isinstance(value, dict):
        if "value" in value:
            return validate_cell(value.get("value"), dtype)
        return None, None, "non_scalar"
    if isinstance(value, list):
        return validate_cell(
            next((item for item in value if item not in (None, "")), None),
            dtype,
        )
    if value in (None, "", "null", "none", "n/a", "None"):
        return None, None, "not_found"
    text = str(value).strip()
    if not text:
        return None, None, "not_found"
    if text[:1] in "{[" or _REFUSAL.search(text):
        return None, None, "non_scalar"
    if dtype in {"numeric", "date"}:
        parsed = _parse(text)
        if not isinstance(parsed, (int, float)):
            return None, None, "dtype_coercion"
        return text, parsed, None
    if len(text) > 400:
        return None, None, "rejected_prose"
    return text, _parse(text), None


def constrained_cell(
    raw: Any,
    vocab: list[str],
    dtype: str = "string",
) -> tuple[str | None, Any, str | None, bool]:
    """Parse a closed-choice extract. residue=True means not in vocab."""

    allowed = {item.lower(): item for item in vocab if item}
    value = raw
    extra = None
    if isinstance(raw, dict):
        value = raw.get("value")
        if value is None:
            value = raw.get("choice") or raw.get("right")
        extra = raw.get("surface") or raw.get("other")
        if extra in (None, "", "null", "none"):
            extra = None
        else:
            extra = str(extra).strip()
    if value in (None, "", "null", "none"):
        return None, None, "not_found", False
    text = str(value).strip()
    if not text:
        return None, None, "not_found", False
    if text.lower() == _OTHER:
        if extra and extra.lower() != _OTHER:
            surface, parsed, reason = validate_cell(extra, dtype)
            return surface, parsed, reason, True
        return None, None, "other", True
    hit = allowed.get(text.lower())
    if hit is not None:
        surface, parsed, reason = validate_cell(hit, dtype)
        return surface, parsed, reason, False
    if extra and extra.lower() != _OTHER:
        surface, parsed, reason = validate_cell(extra, dtype)
        if surface is not None:
            return surface, parsed, reason, True
    surface, parsed, reason = validate_cell(text, dtype)
    return surface, parsed, reason, True


def prefer_constrained_records(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    """One record per cell. A constrained extract replaces free-form cache."""

    best: dict[tuple[str, str], EvidenceRecord] = {}
    for record in records:
        key = (record.segment_id, record.attribute)
        prev = best.get(key)
        if prev is None:
            best[key] = record
            continue
        prev_c = bool((prev.candidate_keys or {}).get("constrained"))
        new_c = bool((record.candidate_keys or {}).get("constrained"))
        if new_c and not prev_c:
            best[key] = record
            continue
        if prev_c and not new_c:
            continue
        if record.stage >= prev.stage:
            best[key] = record
    return list(best.values())


def complete_authority(
    records: list[EvidenceRecord],
    workload: Workload,
    logical=None,
) -> list[EvidenceRecord]:
    """Populate the identity side of each equijoin from unmatched references.

    A missing authority row cannot be bridged. Atomic referencing values
    with no identity-side match become authority evidence so the join
    has a right-hand row.
    """

    refs = join_authority(workload, logical)
    if not refs:
        return records
    extra: list[EvidenceRecord] = []
    for ref, auth in refs.items():
        seen = {
            (record.surface_value or "").strip().lower()
            for record in records
            if _on_authority_relation(record, auth) and record.surface_value
        }
        entity = auth.split(".", 1)[0]
        for record in records:
            if record.attribute != ref:
                continue
            value = (record.surface_value or "").strip()
            if not value or "," in value or value.lower() in seen:
                continue
            slug = _slug(value)
            extra.append(
                EvidenceRecord(
                    key=evidence_key(
                        f"join_complete:{auth}:{slug}", auth, "join_complete", "cheap",
                    ),
                    segment_id=f"join_complete:{auth}:{slug}",
                    doc_id=f"{entity}/join_complete/{slug}",
                    attribute=auth,
                    surface_value=value,
                    parsed_value=value,
                    candidate_keys={"surface": value, "completed": "join"},
                    extractor_cfg_hash="join_complete",
                    quality_tier="cheap",
                    stage=2,
                )
            )
            seen.add(value.lower())
    return list(records) + extra


def _on_authority_relation(record: EvidenceRecord, auth: str) -> bool:
    if record.attribute != auth:
        return False
    entity = auth.split(".", 1)[0]
    doc = record.doc_id or ""
    if "/" in doc:
        return doc.split("/", 1)[0].lower() == entity.lower()
    return True


def _slug(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    return "-".join(part for part in text.split("-") if part)[:80] or "value"


def join_authority(workload: Workload, logical=None) -> dict[str, str]:
    """Referencing join column -> identity (authority) column.

    The authority side is the entity's own identity attribute (``id``,
    ``name``, ``*_id``, ``*_name``). ``logical`` is accepted so the AST key
    can be consulted; a one-attribute entity must not promote a foreign
    key to identity, so the test is structural, not ``identity_name``'s
    fallback.
    """

    _ = logical
    mapping: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for template in workload.templates:
        for left, right in template.join_pairs:
            key = tuple(sorted((left, right)))
            if key in seen or left == right:
                continue
            seen.add(key)
            left_id = _structural_identity(left)
            right_id = _structural_identity(right)
            if left_id and not right_id:
                mapping[right] = left
            elif right_id and not left_id:
                mapping[left] = right
    return mapping


def _structural_identity(qualified: str) -> bool:
    bare = qualified.split(".")[-1].lower()
    return bare in {"id", "name"} or bare.endswith("_name") or bare.endswith("_id")


def _parse_llm_value(text: str, dtype: str = "string") -> tuple[str | None, Any, str | None]:
    cleaned = (text or "").strip()
    if not cleaned or cleaned.lower() in {"null", "none", "n/a"}:
        return None, None, "not_found"
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if match:
            try:
                payload = json.loads(match.group())
            except json.JSONDecodeError:
                payload = None
        else:
            payload = None
    if isinstance(payload, dict) and "value" in payload:
        return validate_cell(payload.get("value"), dtype)
    if isinstance(payload, dict):
        return None, None, "non_scalar"
    return validate_cell(cleaned if payload is None else payload, dtype)


def _parse_llm_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            return {}
        try:
            payload = json.loads(match.group())
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _parse(surface: str) -> Any:
    cleaned = surface.replace(",", "").replace("$", "")
    try:
        if "." in cleaned:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return surface


def cluster_document_formats(documents: list[SourceDocument]) -> dict[str, str]:
    """Structural format clusters for rho estimation."""

    clusters: dict[str, str] = {}
    for doc in documents:
        headers = len(re.findall(r"(?m)^[A-Z][A-Za-z ]{2,}:", doc.text))
        tables = doc.text.count("|")
        length_bin = min(len(doc.text) // 200, 8)
        label = f"h{headers}-t{min(tables, 5)}-l{length_bin}"
        clusters[doc.doc_id] = label
    return clusters


class StagedExtractor:
    def __init__(
        self,
        store: EvidenceStore,
        ledger: TokenLedger,
        extractor: ExtractorFn = default_extractor,
        caller: BudgetedCaller | None = None,
        stage1_recall_threshold: float = 0.15,
        seed: int = 0,
    ):
        self.store = store
        self.ledger = ledger
        self.extractor = extractor
        self.caller = caller
        self.stage1_recall_threshold = stage1_recall_threshold
        self.seed = seed
        self.stage1_admitted: set[str] = set()
        self.stage1_rate: float = 1.0
        self.constraints: dict[str, str] = {}

    def extract(
        self,
        documents: list[SourceDocument],
        workload: Workload,
        policy: PreprocessPolicy,
        tiers: dict[str, str],
        format_clusters: dict[str, str] | None = None,
        logical=None,
    ) -> dict[str, int]:
        segments = segment_documents(documents, policy)
        format_clusters = format_clusters or cluster_document_formats(documents)
        self.constraints = join_authority(workload, logical)
        counts = {"stage1": 0, "stage2": 0, "stage3": 0}
        admitted_docs: set[str] = set()
        try:
            self._extract_stages(
                segments, workload, policy, tiers, format_clusters, counts, admitted_docs,
            )
        except BudgetExhausted:
            pass
        total_docs = {segment.doc_id for segment in segments}
        self.stage1_rate = len(admitted_docs | self.stage1_admitted) / max(1, len(total_docs))
        return counts

    def _extract_stages(
        self,
        segments,
        workload: Workload,
        policy: PreprocessPolicy,
        tiers: dict[str, str],
        format_clusters: dict[str, str],
        counts: dict[str, int],
        admitted_docs: set[str],
    ) -> None:
        filter_attrs = _filter_attributes(workload)
        remaining = [
            name for name in workload.requirements if name not in filter_attrs
        ]
        unsafe = {
            name
            for name, req in workload.requirements.items()
            if any(
                not _template(workload, tid).slice_safe
                for tid in req.templates
            )
        }
        dtypes = {name: req.dtype for name, req in workload.requirements.items()}
        authority = [
            name
            for name in workload.requirements
            if name in set(self.constraints.values())
        ]
        for segment in segments:
            self._extract_many(
                segment, authority, tiers, stage=1,
                format_clusters=format_clusters, policy=policy, dtypes=dtypes,
            )
            counts["stage1"] += len(authority)
        for segment in segments:
            keep = False
            records = self._extract_many(
                segment, filter_attrs, tiers, stage=1,
                format_clusters=format_clusters, policy=policy, dtypes=dtypes,
            )
            counts["stage1"] += len(filter_attrs)
            for record in records:
                req = workload.requirements.get(record.attribute)
                if req is None:
                    continue
                slice_spec = SliceSpec(kind="full") if record.attribute in unsafe else req.slice
                if _admits(record, slice_spec, self.stage1_recall_threshold):
                    keep = True
            if keep or not filter_attrs:
                admitted_docs.add(segment.doc_id)
                self.stage1_admitted.add(segment.doc_id)

        total_docs = {segment.doc_id for segment in segments}
        self.stage1_rate = len(admitted_docs) / max(1, len(total_docs))

        for segment in segments:
            if filter_attrs and segment.doc_id not in admitted_docs:
                continue
            self._extract_many(
                segment, remaining, tiers, stage=2,
                format_clusters=format_clusters, policy=policy, dtypes=dtypes,
            )
            counts["stage2"] += len(remaining)
            promote = [
                name
                for name in filter_attrs
                if workload.requirements[name].roles & {
                    Role.PROJECT, Role.GROUP, Role.KEY, Role.JOIN,
                    Role.AGG_ADDITIVE, Role.AGG_EXTREMAL, Role.AGG_DISTINCT,
                }
            ]
            self._extract_many(
                segment, promote, {name: "expensive" for name in promote}, stage=3,
                format_clusters=format_clusters, policy=policy, dtypes=dtypes,
            )
            counts["stage3"] += len(promote)

    def _extract_one(
        self,
        segment: Segment,
        attribute: str,
        tier: str,
        stage: int,
        format_clusters: dict[str, str],
        policy: PreprocessPolicy,
        slice_spec: SliceSpec,
        dtype: str = "string",
    ) -> EvidenceRecord:
        records = self._extract_many(
            segment, [attribute], {attribute: tier}, stage,
            format_clusters, policy, {attribute: dtype},
        )
        return records[0]

    def _extract_many(
        self,
        segment: Segment,
        attributes: list[str],
        tiers: dict[str, str],
        stage: int,
        format_clusters: dict[str, str],
        policy: PreprocessPolicy,
        dtypes: dict[str, str],
    ) -> list[EvidenceRecord]:
        if not attributes:
            return []
        extractor_name = "llm" if self.caller is not None else self.extractor.__name__
        records: list[EvidenceRecord] = []
        missing: list[str] = []
        cfg_for: dict[str, tuple[str, str]] = {}
        vocab_for: dict[str, list[str]] = {}
        for attribute in attributes:
            tier = tiers.get(attribute, "cheap")
            auth = self.constraints.get(attribute)
            vocab = self._authority_vocab(auth) if auth else []
            if auth and vocab:
                vocab_for[attribute] = vocab
                tag = f"|constrained|{auth}"
            else:
                tag = ""
            cfg_hash = hashlib.sha256(
                f"{policy_hash(policy)}|{tier}|{extractor_name}{tag}".encode()
            ).hexdigest()[:12]
            cfg_for[attribute] = (cfg_hash, tier)
            cached = self.store.get(segment.segment_id, attribute, cfg_hash, tier)
            if cached is not None:
                records.append(cached)
            else:
                missing.append(attribute)

        if not missing:
            return records

        extracted: dict[str, tuple[str | None, Any, str | None, int, str | None]] = {}
        if self.caller is not None:
            free = [name for name in missing if name not in vocab_for]
            grouped: dict[str, list[str]] = defaultdict(list)
            for name in missing:
                if name in vocab_for:
                    grouped[self.constraints[name]].append(name)
            if free:
                extracted.update(
                    self._llm_extract_free(segment, free, cfg_for, dtypes)
                )
            for auth, names in grouped.items():
                extracted.update(
                    self._llm_extract_constrained(
                        segment, names, vocab_for[names[0]], cfg_for, dtypes,
                    )
                )
        else:
            for attribute in missing:
                surface, parsed, tokens = self.extractor(
                    segment, attribute, cfg_for[attribute][1],
                )
                if attribute in vocab_for:
                    surface, parsed, reason, residue = constrained_cell(
                        surface if surface is not None else parsed,
                        vocab_for[attribute],
                        dtypes.get(attribute, "string"),
                    )
                else:
                    surface, parsed, reason = validate_cell(
                        parsed if surface is None else surface,
                        dtypes.get(attribute, "string"),
                    )
                    residue = False
                self.ledger.spend(
                    tokens, purpose="extract", attribute=attribute,
                    tier=cfg_for[attribute][1], stage=stage,
                )
                extracted[attribute] = (
                    surface, parsed, reason, tokens,
                    "other" if residue else ("vocab" if attribute in vocab_for else None),
                )

        for attribute in missing:
            surface, parsed, reason, tokens, constrained = extracted[attribute]
            cfg_hash, tier = cfg_for[attribute]
            keys = {
                "surface": str(surface) if surface is not None else "",
                "doc_id": segment.doc_id,
            }
            if constrained:
                keys["constrained"] = constrained
            record = EvidenceRecord(
                key=evidence_key(segment.segment_id, attribute, cfg_hash, tier),
                segment_id=segment.segment_id,
                doc_id=segment.doc_id,
                template_cluster_id=format_clusters.get(segment.doc_id),
                attribute=attribute,
                surface_value=None if surface is None else str(surface),
                parsed_value=parsed,
                original_unit=_guess_unit(surface),
                null_reason=None if surface is not None else (reason or "not_found"),
                candidate_keys=keys,
                span=None,
                confidence=0.9 if surface is not None else 0.2,
                extractor_cfg_hash=cfg_hash,
                quality_tier=tier,  # type: ignore[arg-type]
                stage=stage,  # type: ignore[arg-type]
                tokens_spent=tokens,
            )
            records.append(self.store.put(record))
        return records

    def _authority_vocab(self, auth: str | None) -> list[str]:
        if not auth:
            return []
        values: list[str] = []
        seen: set[str] = set()
        for record in self.store.for_attribute(auth):
            text = (record.surface_value or "").strip()
            if not text or "," in text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            values.append(text)
        return sorted(values, key=str.lower)

    def _llm_extract_free(
        self,
        segment: Segment,
        missing: list[str],
        cfg_for: dict[str, tuple[str, str]],
        dtypes: dict[str, str],
    ) -> dict[str, tuple[str | None, Any, str | None, int, str | None]]:
        extracted: dict[str, tuple[str | None, Any, str | None, int, str | None]] = {}
        tier = "expensive" if any(cfg_for[name][1] == "expensive" for name in missing) else "cheap"
        limit = 12000 if tier == "expensive" else 4000
        clip = segment.text[:limit]
        listed = ", ".join(missing)
        prompt = (
            "Extract the following attributes from the document. "
            "Return one JSON object mapping each attribute name to a scalar or null. "
            "No commentary, no nested objects.\n"
            f"ATTRIBUTES: {listed}\n\nDOCUMENT:\n{clip}"
        )
        try:
            text = self.caller.complete(
                prompt, purpose="extract", attributes=missing, tier=tier,
            )
        except Exception:
            for attribute in missing:
                extracted[attribute] = (None, None, "provider_error", 0, None)
            return extracted
        payload = _parse_llm_object(text)
        tokens = max(1, (len(prompt) + len(text)) // 4)
        share = max(1, tokens // max(len(missing), 1))
        for attribute in missing:
            raw = payload.get(attribute)
            if raw is None:
                raw = payload.get(attribute.split(".")[-1])
            surface, parsed, reason = validate_cell(raw, dtypes.get(attribute, "string"))
            extracted[attribute] = (surface, parsed, reason, share, None)
        return extracted

    def _llm_extract_constrained(
        self,
        segment: Segment,
        missing: list[str],
        vocab: list[str],
        cfg_for: dict[str, tuple[str, str]],
        dtypes: dict[str, str],
    ) -> dict[str, tuple[str | None, Any, str | None, int, str | None]]:
        extracted: dict[str, tuple[str | None, Any, str | None, int, str | None]] = {}
        tier = "expensive" if any(cfg_for[name][1] == "expensive" for name in missing) else "cheap"
        limit = 12000 if tier == "expensive" else 4000
        clip = segment.text[:limit]
        listed = ", ".join(missing)
        prompt = (
            "Extract the following attributes from the document. "
            "Each value must be exactly one of the allowed values, or the token "
            f"{_OTHER} if the document uses a name that is not listed. "
            "Return one JSON object mapping each attribute name to an allowed "
            f"value, null, or {_OTHER}. If {_OTHER}, return "
            '{"value": "other", "surface": "<name as written>"}. '
            "No commentary.\n"
            f"ATTRIBUTES: {listed}\n"
            f"ALLOWED: {json.dumps(vocab)}\n\nDOCUMENT:\n{clip}"
        )
        try:
            text = self.caller.complete(
                prompt, purpose="extract", attributes=missing, tier=tier,
            )
        except Exception:
            for attribute in missing:
                extracted[attribute] = (None, None, "provider_error", 0, None)
            return extracted
        payload = _parse_llm_object(text)
        tokens = max(1, (len(prompt) + len(text)) // 4)
        share = max(1, tokens // max(len(missing), 1))
        for attribute in missing:
            raw = payload.get(attribute)
            if raw is None:
                raw = payload.get(attribute.split(".")[-1])
            surface, parsed, reason, residue = constrained_cell(
                raw, vocab, dtypes.get(attribute, "string"),
            )
            mark = None if surface is None else ("other" if residue else "vocab")
            extracted[attribute] = (surface, parsed, reason, share, mark)
        return extracted


def _template(workload: Workload, template_id: str) -> Template:
    for template in workload.templates:
        if template.id == template_id:
            return template
    raise KeyError(template_id)


def _filter_attributes(workload: Workload) -> list[str]:
    names = [
        name
        for name, req in workload.requirements.items()
        if Role.PREDICATE in req.roles
    ]
    return sorted(names, key=lambda name: (-workload.requirements[name].freq_weight, name))


def _admits(record: EvidenceRecord, slice_spec: SliceSpec, threshold: float) -> bool:
    if record.surface_value is None:
        return False
    if slice_spec.kind == "full":
        return True
    if slice_spec.contains_constants([record.surface_value, record.parsed_value]):
        return True
    # recall-biased over-admission: keep low-confidence misses near the slice
    return (record.confidence or 0.0) >= threshold and bool(slice_spec.ranges)


def _guess_unit(surface: str | None) -> str | None:
    if surface is None:
        return None
    if "$" in surface or "usd" in surface.lower():
        return "usd"
    return None


def allocate_tiers(workload: Workload) -> dict[str, str]:
    """Section 13.4. Uses amp when present, else role heuristics."""

    tiers: dict[str, str] = {}
    for name, req in workload.requirements.items():
        roles = req.roles
        rho = req.stats.rho if req.stats else 0.5
        multiplicity = req.stats.multiplicity if req.stats else 1.0
        group_size = req.stats.group_size if req.stats else 1.0
        if roles & {Role.KEY, Role.JOIN}:
            tiers[name] = "expensive"
        elif roles & {Role.GROUP, Role.AGG_EXTREMAL} and group_size >= 4:
            tiers[name] = "expensive"
        elif Role.AGG_DISTINCT in roles and multiplicity >= 2:
            tiers[name] = "expensive"
        elif Role.AGG_ADDITIVE in roles and rho <= 0.35:
            tiers[name] = "cheap"
        elif Role.PREDICATE in roles and roles & {Role.PROJECT, Role.GROUP, Role.KEY}:
            tiers[name] = "expensive"
        elif roles == {Role.PROJECT} or roles <= {Role.PROJECT, Role.PREDICATE}:
            tiers[name] = "cheap"
        else:
            tiers[name] = "cheap"
    return tiers

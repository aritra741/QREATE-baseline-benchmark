"""Frozen Gate 1 policy: model, schema, prompts, routing, and thresholds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
WDIRS = ROOT / "systems" / "WDIRS"
SOURCE = ROOT / "source_data" / "Legal" / "legal_case"
SCHEMA_PATH = ROOT / "Query" / "Legal" / "Legal_attributes.json"
OBSERVABLES_PATH = ROOT / "results" / "quwarts_legal_observable_sidecar" / "observables.json"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
OUT = ROOT / "results" / "quwarts_legal_evidence_graph_preflight"
TOKENIZER_PATH = WDIRS / "quwarts" / "assets" / "qwen25_tokenizer.json"

MODEL = "qwen/qwen-2.5-7b-instruct"
SEED = 20260921
SAMPLE_N = 32
THETA_25 = 12_610_011
MEAN_TOKENS_CAP = 22_123
MAX_CALLS = 4
TEMPERATURE = 0.0
WORKERS = 4

EFFECTIVE_INPUT_LIMIT = 11_000
COMPLETION_SPACE = 512
SAFETY_MARGIN = 500
WRAPPER_RESERVE = 850
PACK_BUDGET = 5_200
EXTRACT_MAX_TOKENS = 720
RESOLVE_MAX_TOKENS = 720
VERIFY_MAX_TOKENS = 420
SPOT_MAX_TOKENS = 360

ALLOWED_ATTRIBUTES = (
    "case_number",
    "case_type",
    "plaintiff_current_status",
    "defendant_current_status",
    "first_judge",
    "hearing_year",
    "legal_basis_num",
    "verdict",
)
VALUE_TYPES = ("string", "integer", "decimal", "year", "label", "entity")
ENTITY_ROLES = ("", "plaintiff", "defendant", "judge", "court", "statute", "precedent", "other")
TEMPORAL_ROLES = ("", "hearing", "judgment", "publication", "citation", "other")
COMPONENT_ROLES = ("", "count", "total", "component", "citation_id", "list_index", "indicator", "other")
STATED = ("stated", "inferred")

NODE_SCHEMA = {
    "fact_id": "",
    "attribute_candidates": [],
    "raw_value": "",
    "normalized_value": None,
    "value_type": "string | integer | decimal | year | label | entity",
    "entity_role": "",
    "temporal_role": "",
    "component_role": "",
    "heading": "",
    "source_start": 0,
    "source_end": 0,
    "source_quote": "",
    "stated_or_inferred": "stated | inferred",
    "confidence": 0.0,
}

THRESHOLDS = {
    "projected_total_tokens": THETA_25,
    "documents_with_route": 570,
    "max_calls_per_document": MAX_CALLS,
    "mean_calls_per_document": 4.0,
    "mean_tokens_per_document": MEAN_TOKENS_CAP,
    "reuse_fraction": 0.50,
    "source_offset_validity": 0.98,
    "independent_validation": 0.80,
}

CALL1_ATTRIBUTES = ("case_number", "hearing_year", "legal_basis_num", "first_judge")
CALL2_ATTRIBUTES = ("case_type", "plaintiff_current_status", "defendant_current_status", "verdict")

SYSTEM = (
    "Extract reusable Legal document facts as JSON. "
    "Do not emit SQL answers, query results, or NOT_FOUND facts. "
    "Offsets are 0-based into the original source document and must reproduce the quote exactly."
)

CALL1_PROMPT = """Call 1: identity and numeric evidence.
Build reusable facts, not SQL answers. Preserve competing facts. Do not emit NOT_FOUND.

Extract only evidence for:
- case_number: count of distinct precedent cases cited, considered, discussed, or applied. Not a docket/file number. Not a statute number. Not a citation token such as [2006] HCA 46.
- hearing_year: year the hearing began (YYYY). Do not treat judgment, publication, or citation years as hearing years. If unsure, emit competing year facts with different temporal_role values.
- legal_basis_num: count of distinct statutes or codes cited (e.g. Trade Practices Act 1974 counts as 1). Not a section number used as the count.
- first_judge: the first named presiding judge if present, and/or a 0/1 first-judgment indicator if the document states that. Numbered-list digits are not judge identities.

Each fact must use this schema:
{"fact_id":"c1_01","attribute_candidates":["hearing_year"],"raw_value":"2008","normalized_value":2008,"value_type":"year","entity_role":"","temporal_role":"hearing","component_role":"","heading":"","source_start":0,"source_end":0,"source_quote":"2008","stated_or_inferred":"stated","confidence":0.7}

Rules:
- stated facts need offsets where document[start:end] == source_quote.
- inferred facts may have empty quote and start=end=-1.
- value_type is one of string, integer, decimal, year, label, entity.
- Keep ambiguity. Multiple facts per attribute are allowed.
- At most 10 facts. Return {"facts":[...]} only.
"""

CALL2_PROMPT = """Call 2: classification and outcome evidence.
Build reusable facts, not SQL answers. Preserve competing facts. Do not emit NOT_FOUND.

Extract only evidence for:
- case_type: one of Criminal Case, Civil Case, Commercial Case, Administrative Case, or a short source phrase that classifies the proceeding.
- plaintiff_current_status: occupation or type of the plaintiff. If a company/organization/government body, use Company, Organization, or Government. If an individual, keep the occupation or Individual.
- defendant_current_status: same rules for the defendant.
- verdict: court decision language. Prefer Dismissed, Approved, Others, Guilty, Not Guilty when the source supports that label.

Each fact must use this schema:
{"fact_id":"c2_01","attribute_candidates":["verdict"],"raw_value":"dismissed","normalized_value":"Dismissed","value_type":"label","entity_role":"","temporal_role":"judgment","component_role":"","heading":"","source_start":0,"source_end":0,"source_quote":"dismissed","stated_or_inferred":"stated","confidence":0.7}

Rules:
- Distinguish plaintiff language from defendant language with entity_role.
- Outcome words in party submissions are not automatically the verdict.
- stated facts need offsets where document[start:end] == source_quote.
- Keep ambiguity. At most 10 facts. Return {"facts":[...]} only.
"""

CALL3_PROMPT = """Call 3: graph resolver.
You receive only compact facts from Calls 1 and 2, not the document.
Deduplicate obvious duplicates. Resolve entity roles. Distinguish:
- hearing year vs judgment/publication/citation years;
- case_number (precedent count) vs citations vs legal_basis_num;
- judge names vs numbered-list digits.
Retain unresolved competing facts. Derive workload-visible labels only when evidence supports them.
Do not invent new source quotes. You may keep inferred normalized_value when the cited fact already exists.
Return {"facts":[...],"workload_conflicts":[{"attribute":"","observable_ids":[],"fact_ids":[],"reason":""}]}.
Put a conflict in workload_conflicts when competing facts would change a workload observable. If none, use [].
"""

CALL4_PROMPT = """Call 4: conditional verifier.
You receive conflicting graph nodes, their local source windows, and the affected observable definitions.
Resolve the conflict or preserve uncertainty. Do not reread anything beyond the supplied windows.
Do not invent quotes absent from a window. Do not emit NOT_FOUND.
Return {"facts":[...],"preserved_uncertainty":"YES|NO"}.
The facts list replaces only the conflicting nodes; keep competing facts if still uncertain.
"""

SPOT_PROMPT = """Judge whether the graph node is source-supported and role-compatible for the stated observable.
You see only the raw source window, the node, the attribute definition, and the observable use.
Reply {"support":"YES|NO","role_ok":"YES|NO"} . YES requires the quote to appear in the window and the role/type to match the observable.
"""

CALL1_TERMS = [
    "case number", "precedent", "cited", "considered", "applied", "discussed",
    "hearing", "heard", "year", "judge", "justice", "first judgment",
    "legal basis", "statute", "act", "code", "section", "citation", "v ",
]
CALL2_TERMS = [
    "case type", "civil", "commercial", "administrative", "criminal",
    "plaintiff", "applicant", "defendant", "respondent",
    "company", "organization", "organisation", "government",
    "verdict", "dismissed", "approved", "guilty", "orders",
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(payload: Any) -> str:
    return sha256_text(json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True))


def load_attribute_descriptions() -> dict[str, str]:
    payload = json.loads(SCHEMA_PATH.read_text())
    table = next(iter(payload.values()))
    return {
        name: str(spec.get("description") or "")
        for name, spec in table.items()
        if isinstance(spec, dict) and name in ALLOWED_ATTRIBUTES
    }


def load_observables() -> list[dict[str, Any]]:
    payload = json.loads(OBSERVABLES_PATH.read_text())
    rows = list(payload.get("observables") or [])
    if len(rows) != 24:
        raise SystemExit(f"expected 24 frozen observables, found {len(rows)}")
    return rows


def frozen_prompts() -> dict[str, str]:
    return {
        "system": SYSTEM,
        "call1": CALL1_PROMPT,
        "call2": CALL2_PROMPT,
        "call3": CALL3_PROMPT,
        "call4": CALL4_PROMPT,
        "spot": SPOT_PROMPT,
    }

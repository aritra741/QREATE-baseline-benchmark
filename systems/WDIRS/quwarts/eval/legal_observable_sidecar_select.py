"""Legal workload-observable acquisition with role-separated sidecars.

Gold, scorer output, DocETL answers, and prior per-cell diagnostics stay
unread until a separate post-freeze scorer runs.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import random
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
_OPEN = builtins.open


def _blocked(path: str) -> bool:
    text = str(path).replace("\\", "/")
    if text.endswith("query_manifest.json"):
        return False
    needles = (
        "ground_" + "truth",
        "quwarts_legal_" + "shared_reachability",
        "quwarts_legal_" + "cost_aware_reachability",
        "quwarts_legal_" + "evidence_card_aggregation_audit",
        "quwarts_legal_" + "pairwise_ab",
        "quwarts_legal_" + "forced_binary",
        "quwarts_legal_" + "corpus_probe",
        "quwarts_legal_" + "checked_rank",
        "docetl_legal",
    )
    return any(needle in text for needle in needles)


def _guard(path, *args, **kwargs):
    if _blocked(str(path)):
        raise PermissionError(path)
    return _OPEN(path, *args, **kwargs)


builtins.open = _guard

for entry in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from quwarts.core.corpus_probe.context import exhaustive_chunks, route_context, whole_document_budget
from quwarts.core.docetl_exact_message.adapter import DOCETL_MODEL, canonical_request, tools_for_schema
from quwarts.core.ledger import BudgetExhausted, SpendRecord, TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.observable_sidecar import (
    TABLE,
    bag_hash,
    base_checksum,
    compile_observables,
    ensure_schema,
    execute_bags,
    identity_checksum,
    install_database,
    run_role_fixtures,
    write_specs,
)
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import issue_call, parse_tool, reserved_of, usage_of

OUT = ROOT / "results" / "quwarts_legal_observable_sidecar"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
MANIFEST = ROOT / "results" / "docetl_legal_case80" / "query_manifest.json"
SCHEMA_PATH = ROOT / "Query" / "Legal" / "Legal_attributes.json"
SOURCE = ROOT / "source_data" / "Legal" / "legal_case"
DB_PATH = OUT / "legal_observable.db"
THETA = 12_610_011
SEED = 20260921
SAMPLE_N = 8
RESERVE = 20_000

DECISION_SCHEMA = {
    "state_1": "str",
    "value_1": "str",
    "start_1": "int",
    "end_1": "int",
    "state_2": "str",
    "value_2": "str",
    "start_2": "int",
    "end_2": "int",
    "state_3": "str",
    "value_3": "str",
    "start_3": "int",
    "end_3": "int",
}
FACT_SCHEMA = {
    "value_1": "str",
    "start_1": "int",
    "end_1": "int",
    "value_2": "str",
    "start_2": "int",
    "end_2": "int",
    "value_3": "str",
    "start_3": "int",
    "end_3": "int",
}
VERIFY_SCHEMA = {"keep_1": "str", "keep_2": "str", "keep_3": "str"}
JUDGE_SCHEMA = {"choice": "str", "reason": "str"}

DIRECT_PROMPT = """You decide workload observables for one attribute. Use only the evidence. For each observable fill state_N with RESOLVED or UNRESOLVED, value_N with the decision, and start_N/end_N with character offsets into the source document. Unused slots are UNRESOLVED with start -1 and end -1. Value is TRUE, FALSE, NULL, one legal label, or an integer. Do not put the role name in state_N. Return UNRESOLVED when the evidence does not support a decision. Do not invent identifiers. Resolved SQL NULL is the string NULL, which is different from UNRESOLVED. Presence TRUE needs a cited span or a typed value in the evidence. Presence FALSE needs the whole document and no supporting span. A predicate is not FALSE merely because a literal is absent; return the boolean, not the raw attribute. A group answer must be one legal label. A numeric answer needs the integer in a short span, with the right period and scale. If the period, unit, or component-versus-total is ambiguous, return UNRESOLVED."""

DECOMPOSE_PROMPT = """Extract up to three source facts for this attribute. Each fact is a short typed value and the character offsets of its span. Do not decide the SQL observable yet."""

REDUCE_PROMPT = """Reduce the extracted facts to role-specific observable decisions. Use only those facts and the listed spans. Cite the fact offsets. Return UNRESOLVED when the facts do not support the decision."""

GLEAN_PROMPT = DIRECT_PROMPT

VERIFY_PROMPT = """Check each proposed decision against the evidence. Reply keep only when the cited span supports that exact decision. Otherwise reply drop."""

JUDGE_PROMPT = """Two anonymous answers decide the same observables from the same evidence. Prefer the answer that supports more observables with cited evidence. An answer that decides nothing loses to an answer with source-supported decisions. Penalize unsupported commitments. Reply A or B."""


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
        handle.flush()


def _journal_keys(path: Path) -> set[str]:
    found: set[str] = set()
    if not path.exists():
        return found
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        found.add(str(row.get("key")))
    return found


def _class_of(kind: str) -> str:
    if kind == "presence":
        return "presence"
    if kind == "predicate":
        return "predicate"
    if kind == "group":
        return "group"
    return "numeric"


def _descriptions() -> dict[str, str]:
    payload = _read_json(SCHEMA_PATH)
    table = next(iter(payload.values()))
    return {
        name: str(spec.get("description") or "")
        for name, spec in table.items()
        if isinstance(spec, dict)
    }


def _domain_from_description(text: str) -> list[str]:
    found: list[str] = []
    for block in re.findall(r"\[([^\]]+)\]", text or ""):
        found.extend(part.strip() for part in block.split(",") if part.strip())
    return found


def _literals(expression: str) -> list[str]:
    return re.findall(r"'([^']*)'", expression or "")


def _load_ledger() -> TokenLedger:
    ledger = TokenLedger(theta=THETA, seed=SEED)
    path = OUT / "live_ledger.json"
    if path.exists():
        snap = _read_json(path)
        ledger.spent = int(snap.get("spent") or 0)
        ledger.records = [
            SpendRecord(purpose=row["purpose"], tokens=int(row["tokens"]), metadata=dict(row.get("metadata") or {}))
            for row in snap.get("records") or []
        ]
    return ledger


def _save_ledger(ledger: TokenLedger) -> None:
    _write_json(OUT / "live_ledger.json", ledger.snapshot())


def _call(ledger: TokenLedger, purpose: str, user: str, schema: dict[str, str], metadata: dict[str, Any]) -> dict[str, Any]:
    tools, choice = tools_for_schema(schema, DOCETL_MODEL)
    request = canonical_request(
        model=DOCETL_MODEL,
        messages=[{"role": "user", "content": user}],
        tools=tools,
        tool_choice=choice,
    )
    prompt_tokens, reserved = reserved_of(user, tools)
    if ledger.remaining() < reserved + RESERVE:
        raise BudgetExhausted(purpose)
    response = issue_call(request)
    prompt, completion, actual = usage_of(response, reserved)
    if ledger.spent + actual > ledger.theta:
        ledger.records.append(SpendRecord(purpose=purpose, tokens=actual, metadata={"prompt": prompt, "completion": completion, **metadata}))
        ledger.spent += actual
        _save_ledger(ledger)
        raise BudgetExhausted(purpose)
    ledger.spend(actual, purpose, prompt=prompt, completion=completion, **metadata)
    _save_ledger(ledger)
    parsed = parse_tool(response)
    parsed["tokens"] = actual
    parsed["prompt_tokens"] = prompt_tokens
    return parsed


def _slots(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    row = parsed.get("parsed") or {}
    items = []
    for index in (1, 2, 3):
        items.append(
            {
                "state": str(row.get(f"state_{index}") or "UNRESOLVED").strip().upper(),
                "value": str(row.get(f"value_{index}") or "").strip(),
                "start": row.get(f"start_{index}"),
                "end": row.get(f"end_{index}"),
            }
        )
    return items


def _facts(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    row = parsed.get("parsed") or {}
    items = []
    for index in (1, 2, 3):
        items.append(
            {
                "value": str(row.get(f"value_{index}") or "").strip(),
                "start": row.get(f"start_{index}"),
                "end": row.get(f"end_{index}"),
            }
        )
    return items


def _span_ok(document: str, start: Any, end: Any) -> tuple[int, int] | None:
    try:
        left = int(start)
        right = int(end)
    except (TypeError, ValueError):
        return None
    if left < 0 or right > len(document) or right <= left or right - left > 240:
        return None
    return left, right


def _integers(text: str) -> list[int]:
    return [int(item) for item in re.findall(r"\b\d{1,6}\b", text)]


def _yearish(value: int, description: str) -> bool:
    if not 1900 <= value <= 2100:
        return False
    lowered = description.lower()
    return "year" not in lowered and "yyyy" not in lowered


def _canonicalize(decision: dict[str, Any], observable: dict[str, Any]) -> tuple[str, str]:
    state = str(decision.get("state") or "").strip().upper()
    value = str(decision.get("value") or "").strip()
    upper = value.upper()
    if upper in {"YES", "NO"}:
        upper = "TRUE" if upper == "YES" else "FALSE"
        value = upper
    if upper in {"1", "0"} and observable["kind"] == "presence":
        value = "TRUE" if upper == "1" else "FALSE"
        upper = value
    if state in {"TRUE", "FALSE", "NULL"} and upper in {"", state}:
        value = state
        upper = state
    if upper in {"TRUE", "FALSE", "NULL", "UNRESOLVED"}:
        return ("UNRESOLVED" if upper == "UNRESOLVED" else "RESOLVED"), value
    if state in {"UNRESOLVED", "ABSTAIN", ""}:
        return "UNRESOLVED", value
    literals = [item.lower() for item in _literals(observable.get("expression") or "")]
    if observable["kind"] == "predicate" and value.lower() in literals:
        return "RESOLVED", "TRUE"
    return "RESOLVED", value


def _locate(document: str, decision: dict[str, Any], value: str) -> tuple[int, int] | None:
    cited = _span_ok(document, decision.get("start"), decision.get("end"))
    if cited is not None:
        return cited
    token = value.strip()
    if len(token) < 2 or token.upper() in {"TRUE", "FALSE", "NULL", "UNRESOLVED"}:
        return None
    lowered = document.lower()
    needle = token.lower()
    positions = []
    cursor = 0
    while len(positions) < 4:
        found = lowered.find(needle, cursor)
        if found < 0:
            break
        positions.append(found)
        cursor = found + 1
    if len(positions) == 1:
        return positions[0], positions[0] + len(token)
    return None


def validate_decision(
    observable: dict[str, Any],
    decision: dict[str, Any],
    document: str,
    coverage: str,
    spans: list[dict[str, Any]],
    description: str,
    domains: list[str],
) -> dict[str, Any]:
    state, value = _canonicalize(decision, observable)
    if state == "UNRESOLVED" or value.upper() == "UNRESOLVED" or not value:
        return {"accepted": False, "reason": "unresolved"}
    cited = _locate(document, decision, value)
    if cited is None and value.upper() == "FALSE" and coverage == "whole_document" and not spans:
        cited = (0, min(len(document), 1) or 0)
    if cited is None and value.upper() == "TRUE" and spans:
        cited = (int(spans[0]["start"]), int(spans[0]["end"]))
    if cited is None or cited[1] <= cited[0]:
        return {"accepted": False, "reason": "unsupported_offset", "committed": True}
    left, right = cited
    snippet = document[left:right]
    kind = observable["kind"]
    role = observable["role"]
    labels = list(observable.get("legal_labels") or [])
    lowered = snippet.lower()

    if kind == "presence":
        if value.upper() == "TRUE":
            span_hit = any(str(item.get("value") or "") and str(item.get("value")).lower() in lowered for item in spans)
            if len(snippet.strip()) < 8 and not span_hit:
                return {"accepted": False, "reason": "presence_without_evidence", "committed": True}
            return {"accepted": True, "sql_truth": "TRUE", "value_text": None, "start": left, "end": right}
        if value.upper() == "FALSE":
            if coverage != "whole_document" or spans:
                return {"accepted": False, "reason": "absence_not_exhaustive", "committed": True}
            return {"accepted": True, "sql_truth": "FALSE", "value_text": None, "start": left, "end": right}
        if value.upper() == "NULL":
            return {"accepted": True, "sql_truth": "NULL", "value_text": None, "start": left, "end": right}
        return {"accepted": False, "reason": "illegal_presence", "committed": True}

    if kind == "predicate":
        literals = [item.lower() for item in _literals(observable["expression"])]
        years = [int(item) for item in re.findall(r"\b\d{4}\b", observable["expression"])]
        if value.upper() == "TRUE":
            literal_hit = any(item and item in lowered for item in literals)
            year_hit = False
            if years and len(years) >= 2:
                year_hit = any(years[0] <= item <= years[1] for item in _integers(snippet))
            elif years:
                year_hit = years[0] in _integers(snippet)
            if not literal_hit and not year_hit:
                return {"accepted": False, "reason": "predicate_true_unsupported", "committed": True}
            return {"accepted": True, "sql_truth": "TRUE", "value_text": None, "start": left, "end": right}
        if value.upper() == "FALSE":
            competitors = [item.lower() for item in domains + labels if item.lower() not in literals]
            competitor_hit = any(item and item in lowered for item in competitors)
            literal_hit = any(item and item in lowered for item in literals)
            if not competitor_hit or literal_hit:
                return {"accepted": False, "reason": "predicate_false_needs_competitor", "committed": True}
            return {"accepted": True, "sql_truth": "FALSE", "value_text": None, "start": left, "end": right}
        return {"accepted": False, "reason": "illegal_predicate", "committed": True}

    if kind == "group" and role == "case_branch":
        if value not in labels:
            return {"accepted": False, "reason": "illegal_label", "committed": True}
        if value.lower() in lowered:
            return {"accepted": True, "sql_truth": None, "value_text": value, "start": left, "end": right}
        numbers = _integers(snippet)
        derived = False
        if value == "precedent_heavy":
            derived = any(item >= 8 for item in numbers)
        elif value == "precedent_light":
            derived = any(item < 8 for item in numbers)
        elif value == "many_precedents":
            derived = any(item >= 10 for item in numbers)
        elif value == "fewer_precedents":
            derived = any(item < 10 for item in numbers)
        elif value == "0_or_1":
            derived = any(item <= 1 for item in numbers)
        elif value == "2_or_3":
            derived = any(item in {2, 3} for item in numbers)
        elif value == "4_or_more":
            derived = any(item >= 4 for item in numbers)
        elif value in {"Individual_or_other", "Other"}:
            blocked = any(token.lower() in lowered for token in labels if token not in {value, "Other", "Individual_or_other"})
            derived = bool(snippet.strip()) and not blocked
        if not derived:
            return {"accepted": False, "reason": "label_unsupported", "committed": True}
        return {"accepted": True, "sql_truth": None, "value_text": value, "start": left, "end": right}

    if kind == "group" and role == "group_key":
        if not value or value not in snippet:
            return {"accepted": False, "reason": "group_key_unsupported", "committed": True}
        if "year" in description.lower() or "yyyy" in description.lower():
            if not re.fullmatch(r"(19|20)\d{2}", value):
                return {"accepted": False, "reason": "bad_year", "committed": True}
        return {"accepted": True, "sql_truth": None, "value_text": value, "start": left, "end": right}

    if kind == "numeric":
        try:
            number = int(float(value))
        except ValueError:
            return {"accepted": False, "reason": "non_numeric", "committed": True}
        numbers = _integers(snippet)
        if number not in numbers or len(set(numbers)) != 1:
            return {"accepted": False, "reason": "numeric_ambiguous", "committed": True}
        if _yearish(number, description):
            return {"accepted": False, "reason": "period_or_scale", "committed": True}
        return {"accepted": True, "sql_truth": None, "value_text": str(number), "start": left, "end": right}
    return {"accepted": False, "reason": "unknown_kind", "committed": True}


def _windows(document: str, spans: list[dict[str, Any]]) -> str:
    parts = []
    for span in spans[:6]:
        left = max(0, int(span["start"]) - 180)
        right = min(len(document), int(span["end"]) + 180)
        parts.append(f"[{left}:{right}]\n{document[left:right]}")
    return "\n\n".join(parts)


def build_packet(document: str, attribute: str, observables: list[dict[str, Any]], description: str) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    literals = []
    for item in observables:
        literals.extend(_literals(item["expression"]))
    literals.extend(_domain_from_description(description))
    lowered = document.lower()
    for literal in dict.fromkeys(literals):
        needle = literal.lower()
        if not needle:
            continue
        start = 0
        while len(hits) < 8:
            found = lowered.find(needle, start)
            if found < 0:
                break
            key = (found, found + len(literal))
            if key not in seen:
                seen.add(key)
                hits.append({"start": found, "end": found + len(literal), "value": document[found:found + len(literal)]})
            start = found + len(needle)
    if attribute and any(item["kind"] in {"numeric", "group", "predicate"} for item in observables):
        for match in re.finditer(r"\b\d{1,4}\b", document):
            if len(hits) >= 10:
                break
            key = (match.start(), match.end())
            if key in seen:
                continue
            seen.add(key)
            hits.append({"start": match.start(), "end": match.end(), "value": match.group()})
    wrapper = 1600
    doc_tokens = count_tokens(document)
    mode = route_context(wrapper, doc_tokens)
    if mode == "whole_document":
        context = document
        coverage = "whole_document"
    else:
        context = _windows(document, hits)
        if not context:
            chunks = exhaustive_chunks(document)
            first = chunks[0]["text"] if chunks else document[:1200]
            context = first
        coverage = "retrieval_priority"
    values = sorted({str(item["value"]) for item in hits})
    return {
        "attribute": attribute,
        "mode": mode,
        "coverage": coverage,
        "document_tokens": doc_tokens,
        "spans": hits,
        "context": context,
        "candidate_values": values,
        "ambiguity": len(values) > 3,
        "description": description,
    }


def _observable_block(observables: list[dict[str, Any]]) -> str:
    lines = []
    for index, item in enumerate(observables[:3], start=1):
        labels = ", ".join(item.get("legal_labels") or []) or "the value supported by the expression"
        lines.append(
            f"{index}. id={item['observable_id']} role={item['role']} class={_class_of(item['kind'])}\n"
            f"expression: {item['expression']}\nlegal output domain: {labels}"
        )
    return "\n".join(lines)


def _decision_user(packet: dict[str, Any], observables: list[dict[str, Any]], instruction: str, extra: str = "") -> str:
    span_lines = "\n".join(
        f"- {item['start']}:{item['end']} {item['value']}" for item in packet["spans"][:10]
    ) or "- none"
    return (
        f"{instruction}\n\n"
        f"Attribute: {packet['attribute']}\n"
        f"Official description: {packet['description']}\n"
        f"Coverage: {packet['coverage']}\n"
        f"Ambiguous candidates: {packet['ambiguity']}\n"
        f"Deterministic spans:\n{span_lines}\n\n"
        f"Observables:\n{_observable_block(observables)}\n\n"
        f"{extra}"
        f"Source evidence:\n{packet['context']}"
    )


def _score_plan(rows: list[dict[str, Any]]) -> dict[str, float]:
    committed = [row for row in rows if row.get("committed") or row.get("accepted")]
    accepted = [row for row in rows if row.get("accepted")]
    unsupported = [row for row in committed if not row.get("accepted")]
    return {
        "accepted": len(accepted),
        "committed": len(committed),
        "unsupported": len(unsupported),
        "score": len(accepted) * 10 - len(unsupported),
    }


def _bundle_observables(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in inventory:
        grouped[(item["attribute"], _class_of(item["kind"]))].append(item)
    bundles = []
    for (attribute, obs_class), items in sorted(grouped.items()):
        items = sorted(items, key=lambda row: (-len(row["query_ids"]), -row["raw_occurrences"], row["observable_id"]))
        for offset in range(0, len(items), 3):
            chunk = items[offset:offset + 3]
            frequency = sum(len(row["query_ids"]) for row in chunk)
            amplification = sum(row["raw_occurrences"] for row in chunk)
            reuse = sum(row["raw_occurrences"] for row in chunk)
            bundles.append(
                {
                    "bundle_id": _hash([row["observable_id"] for row in chunk])[:12],
                    "attribute": attribute,
                    "obs_class": obs_class,
                    "observables": chunk,
                    "frequency": frequency,
                    "amplification": amplification,
                    "reuse": reuse,
                }
            )
    return bundles


def _representative(bundles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    for bundle in bundles:
        current = chosen.get(bundle["obs_class"])
        rank = bundle["frequency"] * bundle["amplification"] * bundle["reuse"]
        if current is None or rank > current["_rank"]:
            chosen[bundle["obs_class"]] = {**bundle, "_rank": rank}
    return chosen


def run_plans_for_bundle(
    ledger: TokenLedger,
    bundle: dict[str, Any],
    packet: dict[str, Any],
    document: str,
    domains: list[str],
    entity_id: str,
    phase: str,
    only: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    observables = bundle["observables"]
    results: dict[str, list[dict[str, Any]]] = {}
    wanted = {only} if only else {"direct", "decompose", "glean"}

    def judge(parsed: dict[str, Any], plan: str) -> list[dict[str, Any]]:
        rows = []
        for observable, decision in zip(observables, _slots(parsed)):
            verdict = validate_decision(
                observable,
                decision,
                document,
                packet["coverage"],
                packet["spans"],
                packet["description"],
                domains,
            )
            rows.append({"plan": plan, "observable_id": observable["observable_id"], "entity_id": entity_id, **verdict, "raw_state": decision.get("state"), "raw_value": decision.get("value")})
        return rows

    if "direct" in wanted:
        direct = _call(
            ledger,
            f"{phase}_direct",
            _decision_user(packet, observables, DIRECT_PROMPT),
            DECISION_SCHEMA,
            {"entity_id": entity_id, "bundle": bundle["bundle_id"], "plan": "direct"},
        )
        results["direct"] = judge(direct, "direct")

    if "decompose" not in wanted and "glean" not in wanted:
        return results
    if "decompose" in wanted:
        facts = _call(
            ledger,
            f"{phase}_decompose",
            _decision_user(packet, observables, DECOMPOSE_PROMPT),
            FACT_SCHEMA,
            {"entity_id": entity_id, "bundle": bundle["bundle_id"], "plan": "decompose"},
        )
        fact_text = json.dumps(_facts(facts), default=str)
        reduced = _call(
            ledger,
            f"{phase}_reduce",
            _decision_user(packet, observables, REDUCE_PROMPT, f"Facts:\n{fact_text}\n\n"),
            DECISION_SCHEMA,
            {"entity_id": entity_id, "bundle": bundle["bundle_id"], "plan": "decompose"},
        )
        results["decompose"] = judge(reduced, "decompose")

    if "glean" not in wanted:
        return results
    gleaned = _call(
        ledger,
        f"{phase}_glean",
        _decision_user(packet, observables, GLEAN_PROMPT),
        DECISION_SCHEMA,
        {"entity_id": entity_id, "bundle": bundle["bundle_id"], "plan": "glean"},
    )
    proposed = _slots(gleaned)
    verify_user = _decision_user(
        packet,
        observables,
        VERIFY_PROMPT,
        "Proposed decisions:\n" + json.dumps(proposed, default=str) + "\n\n",
    )
    verified = _call(
        ledger,
        f"{phase}_verify",
        verify_user,
        VERIFY_SCHEMA,
        {"entity_id": entity_id, "bundle": bundle["bundle_id"], "plan": "glean"},
    )
    keeps = verified.get("parsed") or {}
    filtered = dict(gleaned)
    filtered_parsed = dict(gleaned.get("parsed") or {})
    for index in (1, 2, 3):
        if str(keeps.get(f"keep_{index}") or "").strip().lower() != "keep":
            filtered_parsed[f"state_{index}"] = "UNRESOLVED"
            filtered_parsed[f"value_{index}"] = ""
    filtered["parsed"] = filtered_parsed
    results["glean"] = judge(filtered, "glean")
    return results


def _blind_pick(ledger: TokenLedger, obs_class: str, left_name: str, right_name: str, left_rows: list[dict], right_rows: list[dict]) -> str:
    def brief(rows: list[dict]) -> str:
        kept = [row for row in rows if row.get("accepted")]
        dropped = [row for row in rows if row.get("committed") and not row.get("accepted")]
        return json.dumps({"supported": [{k: row.get(k) for k in ("observable_id", "value_text", "sql_truth")} for row in kept], "unsupported": len(dropped)})

    def once(first: str, second: str, tag: str) -> str:
        user = f"{JUDGE_PROMPT}\n\nClass: {obs_class}\nAnswer A:\n{first}\n\nAnswer B:\n{second}"
        parsed = _call(ledger, "sample_judge", user, JUDGE_SCHEMA, {"class": obs_class, "order": tag})
        choice = str((parsed.get("parsed") or {}).get("choice") or "").strip().upper()
        return choice if choice in {"A", "B"} else ""

    forward = once(brief(left_rows), brief(right_rows), "forward")
    backward = once(brief(right_rows), brief(left_rows), "reverse")
    votes = []
    if forward == "A":
        votes.append(left_name)
    elif forward == "B":
        votes.append(right_name)
    if backward == "A":
        votes.append(right_name)
    elif backward == "B":
        votes.append(left_name)
    if len(votes) == 2 and votes[0] == votes[1]:
        return votes[0]
    return ""


def _sample_entities(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    path = OUT / "sample.json"
    if path.exists():
        return _read_json(path)["entities"]
    measured = []
    for row in rows:
        stem = str(row["doc_id"]).replace(".txt", "")
        source = SOURCE / f"{stem}.txt"
        if not source.exists():
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        measured.append({"entity_id": row["__entity_id"], "doc_id": row["doc_id"], "tokens": count_tokens(text)})
    limit = whole_document_budget() - 2000
    eligible = [item for item in measured if item["tokens"] <= limit]
    eligible.sort(key=lambda item: (item["tokens"], item["doc_id"]))
    if len(eligible) < SAMPLE_N:
        raise SystemExit("sample pool smaller than requested")
    quartiles: list[list[dict[str, Any]]] = [[], [], [], []]
    for index, item in enumerate(eligible):
        quartiles[min(3, index * 4 // len(eligible))].append(item)
    rng = random.Random(SEED)
    picked: list[dict[str, Any]] = []
    per = SAMPLE_N // 4
    for bucket in quartiles:
        rng.shuffle(bucket)
        picked.extend(bucket[:per])
    picked = sorted(picked, key=lambda item: item["doc_id"])
    _write_json(path, {"seed": SEED, "n": len(picked), "entities": picked, "hash": _hash(picked)})
    return picked


def _entities() -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    try:
        rows = list(conn.execute('SELECT doc_id, "__entity_id" FROM legal ORDER BY doc_id'))
    finally:
        conn.close()
    items = []
    for row in rows:
        stem = str(row[0]).replace(".txt", "")
        source = SOURCE / f"{stem}.txt"
        tokens = count_tokens(source.read_text(encoding="utf-8", errors="replace")) if source.exists() else 10**9
        items.append({"entity_id": row[1], "doc_id": row[0], "stem": stem, "tokens": tokens})
    items.sort(key=lambda item: (item["tokens"], item["doc_id"]))
    return items


def _document(stem: str) -> str:
    return (SOURCE / f"{stem}.txt").read_text(encoding="utf-8", errors="replace")


def _apply(conn: sqlite3.Connection, observable_id: str, entity_id: str, sql_truth: str | None, value_text: str | None, provenance: str) -> tuple[Any, Any]:
    before = conn.execute(
        'SELECT COUNT(*) FROM legal WHERE "__entity_id" = ?',
        [entity_id],
    ).fetchone()
    conn.execute(
        f"""INSERT INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(observable_id, entity_id) DO UPDATE SET
              resolved=excluded.resolved, sql_truth=excluded.sql_truth,
              value_text=excluded.value_text, provenance=excluded.provenance""",
        [observable_id, entity_id, sql_truth, value_text, provenance],
    )
    conn.commit()
    return before[0], before[0]


def _probe(db: Path, expression: str, entity_id: str, predicates) -> Any:
    sql = f'SELECT ({expression}) AS value FROM legal WHERE "__entity_id" = ?'
    from quwarts.core.pipeline import official_sql

    rewritten = official_sql(f'SELECT {expression} AS value FROM legal WHERE "__entity_id" = \'{entity_id}\'', db, predicates, query_id="probe")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = conn.execute(rewritten).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def main() -> None:
    load_env_file(ROOT / ".env")
    OUT.mkdir(parents=True, exist_ok=True)
    fixtures = run_role_fixtures()
    if not all(fixtures.values()):
        _write_json(OUT / "fixtures.json", fixtures)
        raise SystemExit("role separation fixtures failed")
    queries = _read_json(MANIFEST)
    inventory = compile_observables(queries)
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    if not DB_PATH.exists():
        install_database(PLUMBING, DB_PATH, inventory)
    else:
        conn = sqlite3.connect(DB_PATH)
        try:
            ensure_schema(conn)
            write_specs(conn, inventory)
        finally:
            conn.close()
    plumbing_bags = execute_bags(PLUMBING, statements, predicates)
    empty_bags = execute_bags(DB_PATH, statements, predicates) if not (OUT / "decision_journal.jsonl").exists() else None
    if empty_bags is not None and empty_bags != plumbing_bags:
        raise SystemExit("empty sidecars diverged from plumbing")
    conn = sqlite3.connect(DB_PATH)
    try:
        base_hash = base_checksum(conn)
        identity_hash = identity_checksum(conn)
        edge_count = conn.execute("SELECT COUNT(*) FROM observable_edges").fetchone()[0]
    finally:
        conn.close()
    plumbing_conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    try:
        if base_checksum(plumbing_conn) != base_hash or identity_checksum(plumbing_conn) != identity_hash:
            raise SystemExit("base checksum changed")
    finally:
        plumbing_conn.close()
    descriptions = _descriptions()
    observable_rows = [item.to_json() for item in inventory.observables]
    domains: dict[str, list[str]] = defaultdict(list)
    for item in observable_rows:
        domains[item["attribute"]].extend(item.get("legal_labels") or [])
        domains[item["attribute"]].extend(_literals(item["expression"]))
        domains[item["attribute"]].extend(_domain_from_description(descriptions.get(item["attribute"], "")))
    for key, values in list(domains.items()):
        domains[key] = list(dict.fromkeys(values))
    bundles = _bundle_observables(observable_rows)
    for bundle in bundles:
        bundle["score"] = (
            bundle["frequency"] * bundle["amplification"] * 570 * bundle["reuse"] / 3000
        )
    reps = _representative(bundles)
    prompts = {
        "direct": DIRECT_PROMPT,
        "decompose": DECOMPOSE_PROMPT,
        "reduce": REDUCE_PROMPT,
        "glean": GLEAN_PROMPT,
        "verify": VERIFY_PROMPT,
        "judge": JUDGE_PROMPT,
        "model": DOCETL_MODEL,
    }
    _write_json(
        OUT / "observables.json",
        {
            "raw_occurrences": inventory.raw_occurrences,
            "canonical": inventory.canonical,
            "reuse_ratio": inventory.reuse_ratio,
            "joins": inventory.joins,
            "derived": inventory.derived,
            "observables": observable_rows,
            "bundles": bundles,
            "fixtures": fixtures,
            "empty_bag_match": True,
            "edge_count": edge_count,
            "base_hash": base_hash,
            "identity_hash": identity_hash,
        },
    )
    _write_json(OUT / "prompts.json", prompts)
    ledger = _load_ledger()
    entities = _entities()
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        sample_rows = list(conn.execute('SELECT doc_id, "__entity_id" FROM legal'))
    finally:
        conn.close()
    sample = _sample_entities(sample_rows)
    by_id = {item["entity_id"]: item for item in entities}
    plan_path = OUT / "plan_journal.jsonl"
    done = _journal_keys(plan_path)
    chosen_path = OUT / "chosen_plans.json"
    if not chosen_path.exists():
        try:
            for entity in sample:
                meta = by_id[entity["entity_id"]]
                document = _document(meta["stem"])
                for obs_class, bundle in sorted(reps.items()):
                    key = f"sample|{entity['entity_id']}|{bundle['bundle_id']}"
                    if key in done:
                        continue
                    packet = build_packet(document, bundle["attribute"], bundle["observables"], descriptions.get(bundle["attribute"], ""))
                    _append(OUT / "evidence_journal.jsonl", {"key": key, "entity_id": entity["entity_id"], "attribute": bundle["attribute"], "mode": packet["mode"], "coverage": packet["coverage"], "spans": packet["spans"], "ambiguity": packet["ambiguity"]})
                    results = run_plans_for_bundle(ledger, bundle, packet, document, domains[bundle["attribute"]], entity["entity_id"], "sample")
                    _append(plan_path, {"key": key, "class": obs_class, "results": results})
                    done.add(key)
                    print(json.dumps({"sample": entity["doc_id"], "class": obs_class, "spent": ledger.spent}), flush=True)
        except BudgetExhausted:
            print(json.dumps({"stopped": "budget_during_sample", "spent": ledger.spent}), flush=True)
        collected: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        if plan_path.exists():
            for line in plan_path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                for plan, items in (row.get("results") or {}).items():
                    collected[row["class"]][plan].extend(items)
        selection = {}
        comparisons = {}
        for obs_class, plans in collected.items():
            scored = {plan: _score_plan(rows) for plan, rows in plans.items()}
            ranking = sorted(scored, key=lambda plan: (-scored[plan]["score"], plan))
            winner = ranking[0] if ranking else "direct"
            blinded = ""
            if len(ranking) >= 2:
                try:
                    blinded = _blind_pick(ledger, obs_class, ranking[0], ranking[1], plans[ranking[0]], plans[ranking[1]])
                except BudgetExhausted:
                    blinded = ""
            if blinded in ranking[:2]:
                winner = blinded
            selection[obs_class] = winner
            comparisons[obs_class] = {"scores": scored, "ranking": ranking, "blinded": blinded, "selected": winner}
        if not selection:
            raise SystemExit("plan selection produced no class")
        for obs_class in reps:
            selection.setdefault(obs_class, "direct")
        _write_json(chosen_path, {"selected": selection, "comparisons": comparisons, "hash": _hash(selection)})
    selected = _read_json(chosen_path)["selected"]
    decision_path = OUT / "decision_journal.jsonl"
    decided = _journal_keys(decision_path)
    by_attr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bundle in sorted(bundles, key=lambda item: -item["score"]):
        by_attr[bundle["attribute"]].append(bundle)
    attr_order = sorted(by_attr, key=lambda name: -max(item["score"] for item in by_attr[name]))
    cursors = {name: 0 for name in attr_order}
    progress = True
    while progress and ledger.remaining() > RESERVE:
        progress = False
        for attribute in attr_order:
            items = by_attr[attribute]
            if not items:
                continue
            bundle = items[cursors[attribute] % len(items)]
            cursors[attribute] += 1
            plan = selected.get(bundle["obs_class"], "direct")
            served = False
            for entity in entities:
                key_prefix = f"full|{entity['entity_id']}|{bundle['bundle_id']}"
                if key_prefix in decided:
                    continue
                served = True
                document = _document(entity["stem"])
                packet = build_packet(document, attribute, bundle["observables"], descriptions.get(attribute, ""))
                if packet["coverage"] != "whole_document" and not packet["spans"]:
                    _append(decision_path, {"key": key_prefix, "accepted": [], "skipped": "no_retrieval_evidence"})
                    decided.add(key_prefix)
                    progress = True
                    break
                try:
                    results = run_plans_for_bundle(
                        ledger, bundle, packet, document, domains[attribute], entity["entity_id"], "acquire", only=plan
                    )
                except BudgetExhausted:
                    progress = False
                    served = False
                    break
                chosen_rows = results.get(plan) or []
                accepted = []
                conn = sqlite3.connect(DB_PATH)
                try:
                    for row in chosen_rows:
                        if not row.get("accepted"):
                            continue
                        observable = next(item for item in bundle["observables"] if item["observable_id"] == row["observable_id"])
                        before = _probe(DB_PATH, observable["expression"], entity["entity_id"], predicates)
                        conn.execute(
                            f"""INSERT INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance)
                                VALUES (?, ?, 1, ?, ?, ?)
                                ON CONFLICT(observable_id, entity_id) DO UPDATE SET
                                  resolved=excluded.resolved, sql_truth=excluded.sql_truth,
                                  value_text=excluded.value_text, provenance=excluded.provenance""",
                            [row["observable_id"], entity["entity_id"], row.get("sql_truth"), row.get("value_text"), json.dumps({"start": row.get("start"), "end": row.get("end"), "plan": plan})],
                        )
                        conn.commit()
                        after = _probe(DB_PATH, observable["expression"], entity["entity_id"], predicates)
                        accepted.append({**row, "before": before, "after": after})
                finally:
                    conn.close()
                record = {"key": key_prefix, "entity_id": entity["entity_id"], "bundle": bundle["bundle_id"], "plan": plan, "rows": chosen_rows, "accepted": accepted}
                _append(decision_path, record)
                decided.add(key_prefix)
                progress = True
                print(json.dumps({"acquire": entity["doc_id"], "attribute": attribute, "class": bundle["obs_class"], "accepted": len(accepted), "spent": ledger.spent}), flush=True)
                break
            if not served:
                continue
            if ledger.remaining() <= RESERVE:
                break
    final_bags = execute_bags(DB_PATH, statements, predicates)
    rebuild = OUT / "rebuild.db"
    if rebuild.exists():
        rebuild.unlink()
    install_database(PLUMBING, rebuild, inventory)
    replay = sqlite3.connect(rebuild)
    try:
        if decision_path.exists():
            for line in decision_path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                for item in row.get("accepted") or []:
                    replay.execute(
                        f"""INSERT INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance)
                            VALUES (?, ?, 1, ?, ?, ?)
                            ON CONFLICT(observable_id, entity_id) DO UPDATE SET
                              resolved=1, sql_truth=excluded.sql_truth, value_text=excluded.value_text, provenance=excluded.provenance""",
                        [item["observable_id"], item["entity_id"], item.get("sql_truth"), item.get("value_text"), "rebuild"],
                    )
        replay.commit()
        rebuild_base = base_checksum(replay)
        rebuild_identity = identity_checksum(replay)
    finally:
        replay.close()
    rebuild_bags = execute_bags(rebuild, statements, predicates)
    changed = [query_id for query_id in statements if final_bags[query_id] != plumbing_bags[query_id]]
    freeze = {
        "ready": True,
        "gold_loaded": False,
        "theta": THETA,
        "spent": ledger.spent,
        "model": DOCETL_MODEL,
        "selected_plans": selected,
        "observables_hash": _hash(observable_rows),
        "prompts_hash": _hash(prompts),
        "sample_hash": _hash(sample),
        "plans_hash": _hash(_read_json(chosen_path)),
        "schedule_hash": _hash(bundles),
        "base_hash": base_hash,
        "identity_hash": identity_hash,
        "rebuild_base_match": rebuild_base == base_hash,
        "rebuild_identity_match": rebuild_identity == identity_hash,
        "rebuild_bag_match": rebuild_bags == final_bags,
        "bag_hash": bag_hash(final_bags),
        "plumbing_bag_hash": bag_hash(plumbing_bags),
        "changed_queries": changed,
        "ledger_fingerprint": ledger.fingerprint(),
        "db_hash": file_sha256(DB_PATH),
        "fixtures": fixtures,
        "edge_count": edge_count,
        "raw_occurrences": inventory.raw_occurrences,
        "canonical": inventory.canonical,
        "reuse_ratio": inventory.reuse_ratio,
    }
    _write_json(OUT / "generation_frozen.json", freeze)
    _write_json(OUT / "official_bags.json", final_bags)
    print(json.dumps({"frozen": True, "spent": ledger.spent, "changed": changed, "rebuild": freeze["rebuild_bag_match"]}), flush=True)


if __name__ == "__main__":
    main()

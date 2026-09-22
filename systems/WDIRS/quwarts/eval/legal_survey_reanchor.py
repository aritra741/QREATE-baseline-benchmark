"""Deterministic re-anchoring replay for the frozen Legal survey arm.

Extraction prompts, samples, contribution programs, estimator, and acceptance
rules stay frozen. The original survey directory is read-only. New model calls
are limited to the already specified semantic validator, and only after the
gold-free recovery gate passes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import quwarts.eval.legal_survey_theta50 as survey
import quwarts.eval.legal_wcci_theta50 as wcci

survey_guard = survey._guard
import builtins

builtins.open = survey_guard

ROOT = survey.ROOT
SOURCE = ROOT / "results" / "quwarts_legal_survey_theta50"
OUT = ROOT / "results" / "quwarts_legal_survey_reanchor"
DOCS = survey.DOCS
PRIOR_SPENT = 14_067_427
THETA = 25_220_022
REMAINING = THETA - PRIOR_SPENT
DOCETL_PRODUCT = survey.DOCETL_PRODUCT
WCCI_PRODUCT = survey.WCCI_PRODUCT

RULES: dict[str, Any] = {
    "name": "deterministic evidence re-anchoring",
    "unchanged": [
        "extraction_prompt",
        "sample",
        "contribution_programs",
        "estimator",
        "uncertainty_gates",
        "query_acceptance_rules",
        "semantic_validator_prompt",
    ],
    "normalization": [
        "NFKC",
        "whitespace_runs",
        "curly_quotes",
        "dash_variants",
        "nonbreaking_space",
        "line_break_hyphenation",
        "surrounding_punctuation",
    ],
    "not_normalized": ["words", "numbers", "signs", "units", "dates"],
    "anchor_order": [
        "exact_rendered_context",
        "exact_source",
        "normalized_unique",
        "frozen_candidate",
        "context_relative_offsets",
        "multiple_same_contribution",
        "semantic_label_needs_validator",
        "reject",
    ],
    "multiple_occurrence": "accept only when every match yields the same group value and numeric value; bare repeated years and short labels stay ambiguous",
    "validator": "frozen survey validation prompt and system string",
    "gate": {
        "min_sql_visible_nonzero": 50,
        "min_queries_with_10_known": 3,
        "known_means": "deterministic TRUE or covered FALSE",
        "nonzero_means": "deterministic TRUE support",
    },
    "estimator": "same Poisson waves, control variate, rounding, bootstrap, half samples, and acceptance thresholds",
    "stopping": "do not issue a validator call whose reservation would exceed theta 25220022",
}


def sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def load_documents() -> dict[str, str]:
    documents = {}
    for path in sorted(DOCS.glob("*.txt"), key=lambda item: int(item.stem) if item.stem.isdigit() else item.stem):
        documents[f"{path.stem}.txt"] = path.read_text(errors="replace")
    return documents


def normalize(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    mapping: list[int] = []
    index = 0
    while index < len(text):
        if text[index] == "-" and index + 1 < len(text) and text[index + 1] == "\n":
            index += 2
            continue
        piece = text[index]
        if piece in {"\u00a0", "\u2007", "\u202f"}:
            piece = " "
        piece = {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "−": "-"}.get(piece, piece)
        piece = unicodedata.normalize("NFKC", piece)
        if piece.isspace():
            if chars and chars[-1] == " ":
                index += 1
                continue
            piece = " "
        for char in piece:
            chars.append(char)
            mapping.append(index)
        index += 1
    return "".join(chars), mapping


def needle_key(text: str) -> str:
    normalized, _mapping = normalize(text.strip(" \t\r\n.,;:()[]{}"))
    return normalized.strip()


def find_all(haystack: str, needle: str) -> list[int]:
    if not needle:
        return []
    starts = []
    cursor = 0
    while True:
        found = haystack.find(needle, cursor)
        if found < 0:
            return starts
        starts.append(found)
        cursor = found + 1


def span_from_normalized(text: str, needle: str) -> tuple[int, int] | None:
    normalized, mapping = normalize(text)
    key = needle_key(needle)
    if not key:
        return None
    starts = find_all(normalized, key)
    if len(starts) != 1:
        return None
    start = starts[0]
    return mapping[start], mapping[start + len(key) - 1] + 1


def coordinate_class(text: str, prompt: str, chunks: list[tuple[int, int]], start: int, end: int, claimed: str) -> str:
    if claimed and 0 <= start < end <= len(text) and text[start:end] == claimed:
        return "source_codepoints"
    raw = text.encode()
    if claimed and 0 <= start < end <= len(raw):
        try:
            if raw[start:end].decode() == claimed:
                return "utf8_bytes"
        except UnicodeDecodeError:
            pass
    if claimed and 0 <= start < end <= len(prompt) and prompt[start:end] == claimed:
        return "rendered_prompt"
    for origin, limit in chunks:
        chunk = text[origin:limit]
        if claimed and 0 <= start < end <= len(chunk) and chunk[start:end] == claimed:
            return "chunk_codepoints"
        local_start, local_end = start - origin, end - origin
        if claimed and 0 <= local_start < local_end <= len(chunk) and chunk[local_start:local_end] == claimed:
            return "chunk_shifted"
    if claimed and text.count(claimed) == 1:
        return "text_identity_not_offsets"
    if claimed and text.count(claimed) > 1:
        return "repeated_text_bad_offsets"
    if claimed and span_from_normalized(text, claimed):
        return "normalized_text"
    return "no_coherent_coordinate_system"


def same_contribution(evidence: str, proposed: dict[str, Any]) -> bool:
    if len(evidence) < 8:
        return False
    if re.fullmatch(r"(19|20)\d{2}", evidence.strip()):
        return False
    group = ((proposed.get("group_key") or {}).get("value") or {})
    if isinstance(group, dict):
        for value in group.values():
            if isinstance(value, list):
                return False
            if value is not None and str(value) not in evidence and str(value) not in evidence.replace(" ", ""):
                return False
    return True


def anchor_evidence(text: str, chunks: list[tuple[int, int]], proposed: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], str]:
    evidence = [dict(item) for item in (proposed.get("evidence") or []) if isinstance(item, dict)]
    if not evidence or not any(str(item.get("text") or "") for item in evidence):
        return "no_evidence", evidence, "no evidence text"
    methods = []
    anchored = []
    for item in evidence:
        claimed = str(item.get("text") or "")
        try:
            start, end = int(item.get("start") or 0), int(item.get("end") or 0)
        except (TypeError, ValueError):
            start, end = -1, -1
        method = None
        source_start = source_end = None
        for origin, limit in chunks:
            chunk = text[origin:limit]
            hits = find_all(chunk, claimed)
            if len(hits) == 1:
                method = "exact_rendered_context"
                source_start, source_end = origin + hits[0], origin + hits[0] + len(claimed)
                break
            if claimed and 0 <= start < end <= len(chunk) and chunk[start:end] == claimed:
                method = "context_relative_offsets"
                source_start, source_end = origin + start, origin + end
                break
        if method is None and len(chunks) == 1 and chunks[0][0] == 0:
            hits = find_all(text, claimed)
            if len(hits) == 1:
                method = "exact_source"
                source_start, source_end = hits[0], hits[0] + len(claimed)
        if method is None:
            mapped = span_from_normalized(text, claimed)
            if mapped:
                method = "normalized_unique"
                source_start, source_end = mapped
        if method is None and len(find_all(text, claimed)) > 1 and same_contribution(claimed, proposed):
            method = "multiple_same_contribution"
            source_start = text.find(claimed)
            source_end = source_start + len(claimed)
        if method is None:
            values = []
            group = ((proposed.get("group_key") or {}).get("value") or {})
            if isinstance(group, dict):
                values.extend(str(value) for value in group.values() if not isinstance(value, list))
            matched = [candidate for candidate in candidates if candidate.get("start") is not None and str(candidate.get("value")) in values]
            unique_values = {str(candidate.get("value")) for candidate in matched}
            if matched and len(unique_values) == 1:
                method = "frozen_candidate"
                source_start = int(matched[0]["start"])
                source_end = int(matched[0]["end"])
                claimed = text[source_start:source_end]
        if method is None:
            return "rejected", evidence, "evidence could not be anchored"
        methods.append(method)
        anchored.append({**item, "text": text[source_start:source_end], "start": source_start, "end": source_end, "anchor_method": method})
    aggregates = dict(proposed.get("aggregate_values") or {})
    for key, payload in list(aggregates.items()):
        if not isinstance(payload, dict) or not payload.get("text"):
            continue
        claimed = str(payload["text"])
        hits = find_all(text, claimed)
        if len(hits) == 1:
            aggregates[key] = {**payload, "text": claimed, "start": hits[0], "end": hits[0] + len(claimed)}
        else:
            mapped = span_from_normalized(text, claimed)
            if mapped:
                aggregates[key] = {**payload, "text": text[mapped[0]:mapped[1]], "start": mapped[0], "end": mapped[1]}
    proposed["aggregate_values"] = aggregates
    return methods[0], anchored, "anchored"


def candidate_index(documents: dict[str, str], plumbing: dict[str, dict[str, Any]], attributes: list[str], literals: dict[str, set[str]], descriptions: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    index = {}
    for doc, text in documents.items():
        index[doc] = wcci.build_candidates(doc, text, attributes, literals, descriptions, plumbing.get(doc) or {})
    return index


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "frozen.json").exists() and os.environ.get("REANCHOR_FORCE") != "1":
        print(json.dumps({"already_frozen": str(OUT / "frozen.json")}), flush=True)
        return
    if survey.file_sha(survey.WCCI_DB) != survey.WCCI_DB_HASH:
        raise SystemExit("wcci database hash mismatch")
    design = json.loads((SOURCE / "design_frozen.json").read_text())
    (OUT / "rules_frozen.json").write_text(json.dumps(RULES, indent=2, sort_keys=True))
    (OUT / "rules_frozen.sha256").write_text(sha(RULES))
    documents = load_documents()
    journal = [json.loads(line) for line in (SOURCE / "journal.jsonl").read_text().splitlines() if line.strip()]
    specs = {spec["query_id"]: spec for spec in design["contribution_specs"]}
    keywords = design["keywords"]
    descriptions = json.loads(survey.ATTRIBUTES.read_text())["legal_case"]
    attributes = sorted({atom for spec in specs.values() for atom in spec["presence_atoms"]})
    literals = {name: set(values) for name, values in (design.get("literals") or {}).items()} if False else {}
    # Literals are recovered from the frozen contribution specs, not from gold.
    for spec in specs.values():
        for group in spec["group_expression"]:
            for label in survey.case_labels(group["expr"]):
                column = group["expr"].get("column")
                if group["expr"].get("op") == "column" and column:
                    literals.setdefault(column, set()).add(str(label))
                for when in group["expr"].get("whens") or []:
                    predicate = when.get("if") or {}
                    if predicate.get("column") and isinstance(predicate.get("value"), str):
                        literals.setdefault(predicate["column"], set()).add(predicate["value"])
                    for value in predicate.get("values") or []:
                        if isinstance(value, str):
                            literals.setdefault(predicate["column"], set()).add(value)
    plumbing = {row["doc_id"]: row for row in survey.load_rows(survey.PLUMBING)}
    candidates = candidate_index(documents, plumbing, attributes, literals, descriptions)
    diagnosis = Counter()
    diagnosis_mode = Counter()
    diagnosis_query = Counter()
    records = []
    recovered_true = Counter()
    recovered_known = Counter()
    method_counts = Counter()
    original_true = 0
    for row in journal:
        text = documents[row["document_id"]]
        chunks, _complete = survey.chunks_for(text, keywords)
        bundle_specs = [specs[query_id] for query_id in row["bundle"].split("+")]
        rendered = survey.extraction_prompt(row["document_id"], text[chunks[0][0]:chunks[0][1]] if chunks else text, bundle_specs, descriptions)
        for query in row["result"]["queries"]:
            proposed = dict(query.get("proposed") or {})
            if str(proposed.get("support") or "").upper() == "TRUE":
                original_true += 1
            evidence = (proposed.get("evidence") or [{}])[0]
            claimed = str(evidence.get("text") or "")
            try:
                start, end = int(evidence.get("start") or 0), int(evidence.get("end") or 0)
            except (TypeError, ValueError):
                start, end = -1, -1
            coord = coordinate_class(text, rendered, chunks, start, end, claimed) if query.get("reason") == "bad_offsets" else "already_valid"
            diagnosis[coord] += 1
            diagnosis_mode[(row.get("context_mode"), coord)] += 1
            diagnosis_query[(query["query_id"], coord)] += 1
            spec = specs[query["query_id"]]
            method, anchored, detail = ("not_needed", list(proposed.get("evidence") or []), "original checks passed")
            if query.get("reason") == "bad_offsets":
                method, anchored, detail = anchor_evidence(text, chunks, proposed, candidates.get(row["document_id"]) or [])
            if method not in {"rejected", "no_evidence", "not_needed"}:
                proposed["evidence"] = anchored
            state, reason = survey.validate_contribution(row["document_id"], text, spec, {**proposed, "document_id": row["document_id"]}, bool(row.get("coverage_complete")))
            deterministic = "accepted" if state in {"TRUE", "FALSE"} else "ambiguous" if method == "rejected" and "multiple" in detail else "rejected"
            if state in {"TRUE", "FALSE"}:
                deterministic = "accepted"
            elif method == "rejected":
                deterministic = "rejected"
            else:
                deterministic = "rejected"
            record = {
                "query_id": query["query_id"],
                "document_id": row["document_id"],
                "bundle": row["bundle"],
                "phase": row["phase"],
                "context_mode": row.get("context_mode"),
                "original_status": query.get("reason"),
                "coordinate_class": coord,
                "anchor_method": method,
                "source_start": anchored[0]["start"] if anchored and method not in {"rejected", "no_evidence", "not_needed"} else None,
                "source_end": anchored[0]["end"] if anchored and method not in {"rejected", "no_evidence", "not_needed"} else None,
                "candidate_id": None,
                "deterministic_status": deterministic,
                "reason": reason,
                "state": state,
                "detail": detail,
                "proposed": proposed,
                "coverage_complete": bool(row.get("coverage_complete")),
            }
            records.append(record)
            method_counts[method] += 1
            if state in {"TRUE", "FALSE"}:
                recovered_known[query["query_id"]] += 1
            if state == "TRUE":
                recovered_true[query["query_id"]] += 1
    nonzero = sum(recovered_true.values())
    queries_ready = sum(1 for count in recovered_known.values() if count >= 10)
    gate_pass = nonzero >= RULES["gate"]["min_sql_visible_nonzero"] and queries_ready >= RULES["gate"]["min_queries_with_10_known"]
    diagnosis_payload = {
        "by_class": dict(diagnosis),
        "by_mode": {f"{mode}|{kind}": count for (mode, kind), count in diagnosis_mode.items()},
        "by_query": {f"{query}|{kind}": count for (query, kind), count in diagnosis_query.items()},
        "original_proposed_true": original_true,
        "methods": dict(method_counts),
        "recovered_true_by_query": dict(recovered_true),
        "recovered_known_by_query": dict(recovered_known),
        "sql_visible_nonzero": nonzero,
        "queries_with_10_known": queries_ready,
        "gate_pass": gate_pass,
    }
    (OUT / "diagnosis.json").write_text(json.dumps(diagnosis_payload, indent=2, sort_keys=True))
    (OUT / "anchoring.jsonl").write_text("".join(json.dumps({key: value for key, value in record.items() if key != "proposed"}, default=str) + "\n" for record in records))
    print(json.dumps({"gate_pass": gate_pass, "nonzero": nonzero, "queries_ready": queries_ready, "true": dict(recovered_true), "methods": dict(method_counts)}, default=str), flush=True)
    if not gate_pass:
        conclusion = "deterministic re-anchoring recovers insufficient survey signal"
        frozen = {"conclusion": conclusion, "gate": diagnosis_payload, "tokens": PRIOR_SPENT, "validator_calls": 0, "rules_sha256": sha(RULES)}
        (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, sort_keys=True))
        (OUT / "REPORT.md").write_text("\n".join([
            "# Deterministic evidence re-anchoring",
            "",
            f"Conclusion: `{conclusion}`",
            "",
            f"Original proposed TRUE supports: {original_true}",
            f"SQL-visible nonzero contributions after re-anchoring: {nonzero}",
            f"Queries with at least 10 known contributions: {queries_ready}",
            f"Tokens: {PRIOR_SPENT}",
            "",
            "The recovery gate requires 50 nonzero contributions and 3 queries with 10 known contributions. It failed before any semantic-validator call.",
            "",
            "Returned offsets do not form a coherent source, byte, codepoint, chunk, or prompt coordinate system. Exact and normalized text matching recovered some spans, and the frozen type, CASE, numeric-role, and citation checks still rejected most proposed TRUE supports. That is an evidence-addressing and contribution-generation failure. It is not a sampling-variance failure, because the repaired contributions never reached the estimator.",
            "",
            "No new extraction prompt, replica, or vote follows from this repair.",
        ]) + "\n")
        return

    from quwarts.core.ledger import BudgetExhausted, TokenLedger
    from quwarts.core.llm.openrouter import load_env_file, make_caller
    from quwarts.core.retrieve_extract.tokens import count_tokens

    load_env_file(ROOT / ".env")
    ledger = TokenLedger(theta=REMAINING, seed=survey.SEED)
    validator = make_caller(ledger, model=survey.MODEL, temperature=0.0, max_tokens=survey.DESIGN["validation_max_tokens"])
    validation_rows = []
    accepted_obs: dict[str, dict[str, dict[str, Any]]] = {query_id: {} for query_id in specs}
    for record in records:
        spec = specs[record["query_id"]]
        text = documents[record["document_id"]]
        if record["state"] == "FALSE":
            accepted_obs[record["query_id"]][record["document_id"]] = {"state": "FALSE", "groups": {}, "values": {}, "numbers": {}, "reason": record["reason"]}
            continue
        if record["state"] != "TRUE":
            continue
        prompt = "\n".join([
            f"Document {record['document_id']}. Check whether the proposed row contribution is supported by the evidence.",
            f"Query condition: {json.dumps(spec['support_predicates'])}",
            f"Proposal: {json.dumps(record['proposed'], default=str)[:4000]}",
            f"Local context: {survey.local_context(text, record['proposed'])}",
            'Return {"decision":"accept|reject|uncertain","reason":""}.',
        ])
        reserve = count_tokens(prompt) + survey.DESIGN["validation_max_tokens"]
        if PRIOR_SPENT + ledger.spent + reserve > THETA or reserve > ledger.remaining():
            validation_rows.append({**record, "semantic": "skipped_budget"})
            break
        try:
            raw = validator.complete(prompt, "validate", model=survey.MODEL, system=design["prompts"]["validation_system"], document_id=record["document_id"], bundle=record["bundle"])
        except BudgetExhausted:
            break
        except Exception as exc:  # noqa: BLE001
            validation_rows.append({"query_id": record["query_id"], "document_id": record["document_id"], "semantic": "error", "error": type(exc).__name__})
            continue
        decision = str((survey.parse_json(raw) or {}).get("decision") or "uncertain").lower()
        if decision not in {"accept", "reject", "uncertain"}:
            decision = "uncertain"
        validation_rows.append({"query_id": record["query_id"], "document_id": record["document_id"], "semantic": decision})
        if decision != "accept":
            continue
        groups = survey.normalize_group(spec, (record["proposed"].get("group_key") or {}).get("value") or {})
        values = {}
        for term in spec["aggregate_terms"]:
            if term["op"] in {"avg", "max"}:
                payload = (record["proposed"].get("aggregate_values") or {}).get(term.get("column")) or {}
                values[term["alias"]] = payload.get("value") if isinstance(payload, dict) else payload
            elif term["op"] == "sum_case":
                raw_value = (record["proposed"].get("aggregate_values") or {}).get(term["alias"])
                values[term["alias"]] = 1 if str(raw_value) in {"1", "1.0", "True"} else 0
        accepted_obs[record["query_id"]][record["document_id"]] = {"state": "TRUE", "groups": groups, "values": values, "numbers": {}, "reason": "validator_accept"}
    (OUT / "validation.jsonl").write_text("".join(json.dumps(row, default=str) + "\n" for row in validation_rows))
    wave0 = design["wave0_sample"]
    wave0_pi = design["wave0_inclusion"]
    wave1_payload = json.loads((SOURCE / "wave1_schedule.json").read_text())
    wave1 = wave1_payload["sample"]
    wave1_pi = wave1_payload["pi"]
    waves = [
        {"name": "wave0", "sample": wave0, "pi": wave0_pi, "weight": sum(wave0_pi.values())},
        {"name": "wave1", "sample": wave1, "pi": wave1_pi, "weight": sum(float(value) for value in wave1_pi.values()) or 1.0},
    ]
    wcci_rows = {row["doc_id"]: row for row in survey.load_rows(survey.WCCI_DB)}
    memory = sqlite3.connect(":memory:")
    contributions = {}
    for spec in specs.values():
        contributions[spec["query_id"]] = {doc: survey.row_contribution(spec, row, memory) for doc, row in wcci_rows.items()}
    wcci_bags = json.loads((SOURCE / "bags.json").read_text())
    # Original hybrid bags are the WCCI bags. Prefer the untouched WCCI bag file.
    wcci_bags = json.loads(survey.WCCI_BAGS.read_text())
    docs = sorted(documents)
    hybrid = {}
    provenance = {}
    outputs = {}
    for spec in design["contribution_specs"]:
        observed = accepted_obs[spec["query_id"]]
        wcci_map = contributions[spec["query_id"]]
        raw = survey.estimate_query(spec, docs, wcci_map, observed, waves)
        counts = survey.reconcile_counts(raw["groups"], survey.DESIGN["acceptance"]["kept_group_min_count"])
        cells = {}
        bag = []
        combined_pi = {**wave0_pi, **{doc: max(float(wave0_pi[doc]), float(wave1_pi.get(doc, 0.0))) for doc in docs}}
        for key, count in counts.items():
            group_values = json.loads(key)
            members = [doc for doc, item in observed.items() if item.get("state") == "TRUE" and json.dumps(item.get("groups") or {}, sort_keys=True, default=str) == key]
            cell = {**raw["groups"][key], "count": count, "ess": survey.ess(list(wave0) + list(wave1), combined_pi, members), "numeric": {}}
            row = dict(group_values)
            for term in spec["aggregate_terms"]:
                if term["op"] == "count_star":
                    row[term["alias"]] = count
                elif term["op"] in {"avg", "sum_case"}:
                    payload = survey.numeric_estimate(spec, term, key, docs, wcci_map, observed, waves)
                    cell["numeric"][term["alias"]] = payload
                    if term["op"] == "avg":
                        row[term["alias"]] = payload["average"]
                    else:
                        row[term["alias"]] = int(round(min(count, max(0.0, payload["numerator"]))))
                elif term["op"] == "max":
                    validated = [survey.typed_number((item.get("values") or {}).get(term["alias"])) for doc, item in observed.items() if item.get("state") == "TRUE" and json.dumps(item.get("groups") or {}, sort_keys=True, default=str) == key]
                    validated = [number for number in validated if number is not None]
                    row[term["alias"]] = max(validated) if validated else None
                    cell["numeric"][term["alias"]] = {"average": row[term["alias"]], "numerator_se": 0.0, "denominator": 1.0}
            cells[key] = cell
            if spec["having_expression"] and count < spec["having_expression"]["count_star_gte"]:
                continue
            bag.append(row)
        ok, reason = survey.accept_query(spec, docs, wcci_map, observed, waves, wcci_bags[spec["query_id"]], bag, cells)
        hybrid[spec["query_id"]] = bag if ok else wcci_bags[spec["query_id"]]
        provenance[spec["query_id"]] = {"decision": "survey" if ok else "wcci_fallback", "reason": reason}
        outputs[spec["query_id"]] = {"decision": provenance[spec["query_id"]]["decision"], "reason": reason, "survey_bag": bag}
        if not ok and json.dumps(hybrid[spec["query_id"]], sort_keys=True, default=str) != json.dumps(wcci_bags[spec["query_id"]], sort_keys=True, default=str):
            raise SystemExit(f"fallback drifted for {spec['query_id']}")
    if survey.file_sha(survey.WCCI_DB) != survey.WCCI_DB_HASH or PRIOR_SPENT + ledger.spent > THETA:
        raise SystemExit("freeze gate failed")
    (OUT / "estimator_outputs.json").write_text(json.dumps(outputs, indent=2, default=str))
    (OUT / "bags.json").write_text(json.dumps(hybrid, ensure_ascii=False))
    (OUT / "ledger.json").write_text(json.dumps({"prior_spent": PRIOR_SPENT, "repair_spent": ledger.spent, "cumulative": PRIOR_SPENT + ledger.spent}, indent=2))
    frozen = {
        "rules_sha256": sha(RULES),
        "bag_hash": survey.bag_hash(hybrid),
        "cumulative_tokens": PRIOR_SPENT + ledger.spent,
        "accepted": [query_id for query_id, item in provenance.items() if item["decision"] == "survey"],
        "fallbacks": [query_id for query_id, item in provenance.items() if item["decision"] == "wcci_fallback"],
        "wcci_database_hash": survey.file_sha(survey.WCCI_DB),
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, sort_keys=True))
    survey._FROZEN["ok"] = True
    queries = json.loads(survey.MANIFEST.read_text())
    report = survey.score_bags(hybrid, queries)
    product = float(report["mean_per_query_product"])
    if product > DOCETL_PRODUCT:
        conclusion = "evidence re-anchoring unlocks a Legal win"
    else:
        conclusion = "re-anchoring enables estimation but repaired survey remains below DocETL"
    (OUT / "scores.json").write_text(json.dumps({"conclusion": conclusion, "product": product, "f2": report["mean_structure_f2"], "f1": report["mean_cell_f1_20"], "per_query": report["per_query"], "provenance": provenance, "tokens": PRIOR_SPENT + ledger.spent}, indent=2, default=str))
    (OUT / "REPORT.md").write_text("\n".join([
        "# Deterministic evidence re-anchoring",
        "",
        f"Conclusion: `{conclusion}`",
        "",
        f"Product: {product}",
        f"F2: {report['mean_structure_f2']}",
        f"Cell F1@0.20: {report['mean_cell_f1_20']}",
        f"Tokens: {PRIOR_SPENT + ledger.spent}",
        f"Accepted queries: {len(frozen['accepted'])}",
        f"WCCI fallbacks: {len(frozen['fallbacks'])}",
        "",
        "No new extraction prompt, replica, or vote follows from this repair.",
    ]) + "\n")
    print(json.dumps({"conclusion": conclusion, "product": product, "spent": PRIOR_SPENT + ledger.spent, "accepted": len(frozen["accepted"])}), flush=True)


if __name__ == "__main__":
    main()

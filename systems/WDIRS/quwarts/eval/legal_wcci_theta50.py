"""Workload-calibrated collective inference for Legal at θ50.

The design file is hashed before the first model call. Benchmark gold and
DocETL map outputs stay unread until the shared database and bags are frozen.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import sys
import threading
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path("/Users/aritramazumder/Documents/UDA-Bench-main")
sys.path[:0] = [str(ROOT / "systems" / "WDIRS"), str(ROOT / "systems" / "docetl-main"), str(ROOT)]

from quwarts.core.wcci.design import DESIGN

_OPEN = builtins.open
_FROZEN = {"ok": False}
_BLOCK = (
    "ground_truth",
    "/gold/",
    "gold.json",
    "extract_fields.json",
    "pipeline_output.json",
    "query_results.json",
    "evaluation.json",
    "shared_reachability",
    "cost_aware_reachability",
    "diagnostic_scores",
    "evidence_card_aggregation",
    "quwarts_legal_expert_budget",
    "docetl_legal_case80/docetl_pipelines",
)
_ALLOW = ("query_manifest.json", "legal_attributes.json", "observables.json")


def _blocked(path: object) -> bool:
    if _FROZEN["ok"]:
        return False
    text = str(path).replace("\\", "/")
    lower = text.lower()
    if any(text.endswith(suffix) for suffix in _ALLOW):
        return False
    return any(fragment.lower() in lower for fragment in _BLOCK)


def _guard(path, *args, **kwargs):
    if _blocked(path):
        raise PermissionError(f"forbidden_before_freeze:{path}")
    return _OPEN(path, *args, **kwargs)


builtins.open = _guard

import sqlglot
from sqlglot import exp

from quwarts.core.ledger import BudgetExhausted, TokenLedger
from quwarts.core.llm.openrouter import load_env_file, make_caller
from quwarts.core.retrieve_extract.tokens import count_tokens

MANIFEST = ROOT / "results" / "docetl_legal_case80" / "query_manifest.json"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
ATTRIBUTES = ROOT / "Query" / "Legal" / "Legal_attributes.json"
DOCS = ROOT / "source_data" / "Legal" / "legal_case"
OUT = ROOT / "results" / "quwarts_legal_wcci_theta50"
DOCETL_PRODUCT = 0.12350932750098194


def sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quartile(values: dict[str, float]) -> dict[str, int]:
    ordered = sorted(values, key=lambda key: (values[key], key))
    width = max(1, len(ordered)) / 4
    return {key: min(4, int(index / width) + 1) for index, key in enumerate(ordered)}


def workload_columns(queries: list[dict[str, str]]) -> tuple[list[str], dict[str, set[str]], list[tuple[str, str]]]:
    attributes: set[str] = set()
    literals: dict[str, set[str]] = defaultdict(set)
    pairs: set[tuple[str, str]] = set()
    for query in queries:
        tree = sqlglot.parse_one(query["sql"])
        cols = []
        for column in tree.find_all(exp.Column):
            name = (column.name or "").strip()
            if name and name not in {"*", "doc_id"}:
                attributes.add(name)
                cols.append(name)
        for node in tree.find_all(exp.EQ):
            column = node.this if isinstance(node.this, exp.Column) else node.expression if isinstance(node.expression, exp.Column) else None
            literal = node.expression if isinstance(node.expression, exp.Literal) else node.this if isinstance(node.this, exp.Literal) else None
            if column is not None and literal is not None and not literal.is_number:
                literals[column.name].add(str(literal.this))
        for node in tree.find_all(exp.In):
            if isinstance(node.this, exp.Column):
                for item in node.expressions:
                    if isinstance(item, exp.Literal) and not item.is_number:
                        literals[node.this.name].add(str(item.this))
        unique = sorted(set(cols))
        for left in unique:
            for right in unique:
                if left < right:
                    pairs.add((left, right))
    return sorted(attributes), {key: set(value) for key, value in literals.items()}, sorted(pairs)


def load_descriptions() -> dict[str, dict[str, Any]]:
    payload = json.loads(ATTRIBUTES.read_text())
    return payload["legal_case"]


def read_documents() -> list[tuple[str, str]]:
    paths = sorted(DOCS.glob("*.txt"), key=lambda path: int(path.stem) if path.stem.isdigit() else path.stem)
    return [(f"{path.stem}.txt", path.read_text(errors="replace")) for path in paths]


def plumbing_rows() -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = {row["doc_id"]: dict(row) for row in conn.execute("SELECT * FROM legal")}
    conn.close()
    return rows


def _candidate(doc: str, attribute: str, value: Any, channel: str, start: int | None, end: int | None, text: str, lineage: str) -> dict[str, Any]:
    identity = f"{doc}|{attribute}|{channel}|{start}|{end}|{value}|{lineage}"
    return {
        "document_id": doc,
        "attribute": attribute,
        "candidate_id": hashlib.sha256(identity.encode()).hexdigest()[:16],
        "value": value,
        "channel": channel,
        "start": start,
        "end": end,
        "lineage": lineage,
        "surface": None if start is None or end is None else text[start:end],
        "context": None if start is None else text[max(0, start - 80): min(len(text), (end or start) + 80)],
    }


def build_candidates(doc: str, text: str, attributes: list[str], literals: dict[str, set[str]], descriptions: dict[str, dict[str, Any]], plumbing: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    lowered = text.lower()
    for attribute in attributes:
        if plumbing.get(attribute) not in (None, ""):
            continue
        found.append(_candidate(doc, attribute, None, "KEEP_PLUMBING", None, None, text, "existing plumbing value"))
        found.append(_candidate(doc, attribute, None, "LEAVE_NULL", None, None, text, "explicit leave-null option"))
        for label in sorted(literals.get(attribute, set())):
            start = lowered.find(label.lower())
            if start >= 0:
                found.append(_candidate(doc, attribute, label, "workload_label", start, start + len(label), text, "casefolded workload literal"))
        description = (descriptions.get(attribute) or {}).get("description") or ""
        for label in re.findall(r"'([^']+)'", description):
            start = lowered.find(label.lower())
            if start >= 0:
                found.append(_candidate(doc, attribute, label, "description_label", start, start + len(label), text, "label quoted in the attribute description"))
        if attribute in {"hearing_year", "judgment_year"}:
            for match in re.finditer(r"\b(?:19|20)\d{2}\b", text):
                found.append(_candidate(doc, attribute, match.group(0), "year", match.start(), match.end(), text, "deterministic year parse"))
                break
        if attribute == "legal_basis_num":
            spans = list(re.finditer(r"\b[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,4} Act \d{4}\b", text))
            if spans:
                found.append(_candidate(doc, attribute, len({span.group(0) for span in spans}), "citation_count", spans[0].start(), spans[-1].end(), text, "count of distinct Act citations"))
        if attribute == "case_number":
            spans = list(re.finditer(r"\b[A-Z][A-Za-z&. ]{2,80}\bv\b[A-Za-z&. ]{2,80}", text))
            if spans:
                found.append(_candidate(doc, attribute, min(len(spans), 12), "precedent_count", spans[0].start(), spans[0].end(), text, "count of v-style case captions"))
        if attribute in {"first_judge", "evidence"}:
            for phrase, value in (("first instance", "1"), ("first judgment", "1"), ("no evidence", "0"), ("evidence was", "1")):
                start = lowered.find(phrase)
                if start >= 0:
                    found.append(_candidate(doc, attribute, value, "binary_phrase", start, start + len(phrase), text, f"phrase {phrase}"))
        if attribute in {"plaintiff_current_status", "defendant_current_status"}:
            for phrase, label in (("pty ltd", "Company"), ("limited", "Company"), ("department", "Government"), ("minister", "Government"), ("organisation", "Organization"), ("organization", "Organization")):
                start = lowered.find(phrase)
                if start >= 0:
                    canonical = label if label in literals.get(attribute, {label}) or label.lower() in {item.lower() for item in literals.get(attribute, set())} else label
                    for item in literals.get(attribute, set()):
                        if item.lower() == label.lower():
                            canonical = item
                    found.append(_candidate(doc, attribute, canonical, "party_type", start, start + len(phrase), text, f"party suffix {phrase}"))
    return found


def featurize(candidate: dict[str, Any], text: str, descriptions: dict[str, dict[str, Any]], literals: dict[str, set[str]]) -> dict[str, float]:
    attribute = candidate["attribute"]
    description = (descriptions.get(attribute) or {}).get("description") or ""
    surface = candidate.get("surface") or ""
    start = candidate.get("start")
    terms = [word.lower() for word in re.findall(r"[A-Za-z]{4,}", description)[:8]]
    proximity = 0.0
    if start is not None:
        window = text[max(0, start - 200): start + 200].lower()
        proximity = sum(1.0 for term in terms if term in window) / max(1, len(terms))
    header = ""
    if start is not None:
        prior = text.rfind("\n", 0, start)
        header = text[text.rfind("\n\n", 0, start): prior].strip().splitlines()[-1:] or [""]
        header = header[0][:80]
    return {
        "channel_label": 1.0 if candidate["channel"] in {"workload_label", "description_label", "party_type"} else 0.0,
        "channel_numeric": 1.0 if candidate["channel"] in {"year", "citation_count", "precedent_count", "binary_phrase"} else 0.0,
        "channel_keep": 1.0 if candidate["channel"] == "KEEP_PLUMBING" else 0.0,
        "channel_leave": 1.0 if candidate["channel"] == "LEAVE_NULL" else 0.0,
        "attribute_proximity": proximity,
        "description_term_proximity": proximity,
        "has_header": 1.0 if header else 0.0,
        "span_length": float(len(surface)) / 80.0,
        "document_position": 0.0 if start is None else start / max(1, len(text)),
        "workload_label": 1.0 if str(candidate["value"]) in literals.get(attribute, set()) else 0.0,
        "parse_altered": 1.0 if candidate["channel"] in {"citation_count", "precedent_count", "party_type"} else 0.0,
        "has_offset": 1.0 if start is not None else 0.0,
    }


def strata_for(docs: list[tuple[str, str]], candidates: dict[str, list[dict[str, Any]]], plumbing: dict[str, dict[str, Any]], attributes: list[str], rare: set[str]) -> dict[str, dict[str, Any]]:
    lengths = {doc: len(text) for doc, text in docs}
    density = {doc: float(len(candidates.get(doc, []))) for doc, _ in docs}
    length_q = quartile({doc: float(value) for doc, value in lengths.items()})
    density_q = quartile(density)
    rows = {}
    for doc, text in docs:
        lowered = text.lower()
        section = 1 if re.search(r"(?m)^(between|introduction|orders|reasons|background)\b", lowered) or "\t" in text else 0
        present = sum(1 for attribute in attributes if plumbing[doc].get(attribute) not in (None, ""))
        coverage = sum(1 for label in rare if label.lower() in lowered)
        completeness = present / max(1, len(attributes))
        rows[doc] = {
            "length_quartile": length_q[doc],
            "density_quartile": density_q[doc],
            "section_or_table": section,
            "plumbing_completeness": completeness,
            "observable_coverage": coverage,
            "rare_label": 1 if coverage else 0,
            "bytes": lengths[doc],
        }
    complete_q = quartile({doc: row["plumbing_completeness"] for doc, row in rows.items()})
    cover_q = quartile({doc: float(row["observable_coverage"]) for doc, row in rows.items()})
    for doc, row in rows.items():
        row["plumbing_quartile"] = complete_q[doc]
        row["coverage_quartile"] = cover_q[doc]
        row["stratum"] = f"{row['length_quartile']}|{row['density_quartile']}|{row['section_or_table']}|{row['plumbing_quartile']}|{row['coverage_quartile']}|{row['rare_label']}"
    return rows


def draw_sample(meta: dict[str, dict[str, Any]], size: int, seed: int) -> dict[str, float]:
    groups: dict[str, list[str]] = defaultdict(list)
    for doc, row in meta.items():
        groups[row["stratum"]].append(doc)
    rng = random.Random(seed)
    keys = sorted(groups)
    total = sum(len(groups[key]) for key in keys)
    raw = {key: size * len(groups[key]) / total for key in keys}
    alloc = {key: int(raw[key]) for key in keys}
    leftover = size - sum(alloc.values())
    for key in sorted(keys, key=lambda item: (raw[item] - alloc[item], item), reverse=True):
        if leftover <= 0:
            break
        if alloc[key] < len(groups[key]):
            alloc[key] += 1
            leftover -= 1
    # Guarantee a seat for every non-empty stratum while the sample still fits.
    missing = [key for key in keys if alloc[key] == 0]
    donors = sorted(keys, key=lambda item: alloc[item], reverse=True)
    for key in missing:
        donor = next((item for item in donors if alloc[item] > 1), None)
        if donor is None:
            break
        alloc[donor] -= 1
        alloc[key] += 1
    chosen = []
    for key in keys:
        pool = sorted(groups[key])
        rng.shuffle(pool)
        chosen.extend(pool[: min(alloc[key], len(pool))])
    probabilities = {}
    for key in keys:
        probability = alloc[key] / len(groups[key]) if groups[key] else 0.0
        for doc in groups[key]:
            if doc in chosen:
                probabilities[doc] = probability
    return probabilities


def split_sample(probabilities: dict[str, float], seed: int) -> dict[str, str]:
    docs = sorted(probabilities)
    rng = random.Random(seed + 1)
    rng.shuffle(docs)
    n = len(docs)
    n_train = int(round(n * DESIGN["split"]["train"]))
    n_val = int(round(n * DESIGN["split"]["validation"]))
    roles = {}
    for index, doc in enumerate(docs):
        if index < n_train:
            roles[doc] = "train"
        elif index < n_train + n_val:
            roles[doc] = "validation"
        else:
            roles[doc] = "test"
    return roles


def parse_json(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def normalize(value: Any, attribute: str, literals: dict[str, set[str]]) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text.upper() in {"LEAVE_NULL", "UNCERTAIN", "NONE", "NULL"}:
            return None
        for label in literals.get(attribute, set()):
            if text.lower() == label.lower():
                return label
        if attribute in {"case_number", "legal_basis_num", "evidence"}:
            try:
                return int(float(text))
            except ValueError:
                return None
        return text
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and attribute in {"case_number", "legal_basis_num", "evidence"}:
        return int(value)
    return str(value)


def call_json(caller, prompt: str, purpose: str, phase_cap: int, phase_spent: list[int], lock: threading.Lock) -> dict[str, Any] | None:
    estimate = count_tokens(prompt) + 800
    with lock:
        if phase_spent[0] + estimate > phase_cap or caller.ledger.remaining() < estimate:
            return None
        phase_spent[0] += estimate
    try:
        text = caller.complete(prompt, purpose, model=DESIGN["model"])
    except BudgetExhausted:
        return None
    except Exception as exc:
        return {"_error": type(exc).__name__}
    parsed = parse_json(text)
    if parsed is None:
        return {"_raw": text[:500], "_unparsed": True}
    return parsed


def probe_document(caller, doc: str, text: str, cands: list[dict[str, Any]], attributes: list[str], descriptions: dict[str, dict[str, Any]], phase_cap: int, phase_spent: list[int], lock: threading.Lock, plans: set[str]) -> dict[str, Any]:
    by_attr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in cands:
        if candidate["channel"] not in {"KEEP_PLUMBING", "LEAVE_NULL"}:
            by_attr[candidate["attribute"]].append(candidate)
    outputs = {}
    if "P1_joint_map" in plans:
        if count_tokens(text) <= DESIGN["p1_abstain_when_document_tokens_exceed"]:
            schema = {attribute: (descriptions.get(attribute) or {}).get("description", attribute) for attribute in attributes}
            prompt = (
                "Extract a JSON object of legal attributes from the full document. "
                "Each value must be copied or deterministically counted from the document. "
                "Use null when the document does not state it. Keys:\n"
                + json.dumps(schema)
                + "\n\nDOCUMENT\n"
                + text
            )
            outputs["P1_joint_map"] = call_json(caller, prompt, "wcci_p1", phase_cap, phase_spent, lock)
        else:
            outputs["P1_joint_map"] = {"_abstain": True}
    if "P2_split_gather" in plans:
        parts = [text[index * len(text) // 3: (index + 1) * len(text) // 3] for index in range(3)]
        selected = []
        complete = True
        for index, part in enumerate(parts):
            cards = []
            offset = index * len(text) // 3
            for attribute, rows in by_attr.items():
                for candidate in rows:
                    if candidate.get("start") is None:
                        continue
                    if offset <= candidate["start"] < offset + len(part):
                        cards.append({"id": candidate["candidate_id"], "attribute": attribute, "excerpt": (candidate.get("surface") or "")[:120]})
            excerpt = part if count_tokens(part) <= 6000 else part[:8000]
            if excerpt != part:
                complete = False
            prompt = (
                "Return JSON {\"selected\": [candidate ids present in this chunk]}. "
                "Select only ids whose excerpt is supported by the chunk.\n"
                + json.dumps(cards[:40])
                + "\n\nCHUNK\n"
                + excerpt
            )
            parsed = call_json(caller, prompt, "wcci_p2", phase_cap, phase_spent, lock)
            if parsed is None:
                complete = False
                break
            selected.extend(parsed.get("selected") or [])
        outputs["P2_split_gather"] = {"selected": selected, "complete": complete}
    if "P3_compressed_map" in plans:
        lines = []
        for candidate in cands:
            if candidate.get("start") is None:
                continue
            lines.append(f"{candidate['start']}-{candidate['end']}:{candidate.get('surface')}")
        compressed = "\n".join(lines[:80])
        prompt = (
            "The lines are source spans with original offsets. Return JSON mapping each attribute to "
            "{\"value\": ..., \"start\": offset, \"end\": offset}. Use null if unsupported.\nAttributes: "
            + ", ".join(attributes)
            + "\n\nEVIDENCE\n"
            + compressed
        )
        outputs["P3_compressed_map"] = call_json(caller, prompt, "wcci_p3", phase_cap, phase_spent, lock)
    if "P4_evidence_ledger" in plans:
        headings = re.findall(r"(?m)^[A-Z][A-Za-z ]{3,40}$", text)[:12]
        spans = []
        for candidate in cands:
            if candidate.get("start") is None:
                continue
            spans.append({"start": candidate["start"], "end": candidate["end"], "text": (candidate.get("surface") or "")[:100], "attribute": candidate["attribute"]})
        prompt = (
            "Build one JSON evidence ledger {\"entries\": [{\"start\": n, \"end\": n, \"role\": attribute}]} "
            "from these spans and headings. Do not add spans that are not listed.\nHeadings: "
            + json.dumps(headings)
            + "\nSpans:\n"
            + json.dumps(spans[:60])
        )
        ledger = call_json(caller, prompt, "wcci_p4", phase_cap, phase_spent, lock)
        projected = []
        if ledger and isinstance(ledger.get("entries"), list):
            for entry in ledger["entries"]:
                try:
                    start, end = int(entry.get("start")), int(entry.get("end"))
                except (TypeError, ValueError):
                    continue
                role = str(entry.get("role") or "")
                for candidate in by_attr.get(role, []):
                    if candidate.get("start") == start:
                        projected.append(candidate["candidate_id"])
        outputs["P4_evidence_ledger"] = {"selected": projected, "ledger": bool(ledger)}
    if "P5_candidate_card" in plans:
        cards = []
        for attribute, rows in by_attr.items():
            for candidate in rows[:4]:
                cards.append({
                    "id": candidate["candidate_id"],
                    "attribute": attribute,
                    "excerpt": (candidate.get("context") or "")[:180],
                    "description": ((descriptions.get(attribute) or {}).get("description") or "")[:180],
                })
        cards.append({"id": "KEEP_PLUMBING", "attribute": "*", "excerpt": "", "description": "keep the plumbing cell"})
        cards.append({"id": "LEAVE_NULL", "attribute": "*", "excerpt": "", "description": "leave the cell null"})
        prompt = (
            "Return JSON {\"choices\": {attribute: candidate_id}}. "
            "Choose one id per attribute from the cards, or LEAVE_NULL, KEEP_PLUMBING, or UNCERTAIN.\n"
            + json.dumps(cards[:48])
        )
        outputs["P5_candidate_card"] = call_json(caller, prompt, "wcci_p5", phase_cap, phase_spent, lock)
    return outputs


def plan_values(outputs: dict[str, Any], cands: list[dict[str, Any]], attributes: list[str], literals: dict[str, set[str]]) -> dict[str, dict[str, Any]]:
    by_id = {row["candidate_id"]: row for row in cands}
    values: dict[str, dict[str, Any]] = {plan: {} for plan in outputs}
    for attribute in attributes:
        p1 = outputs.get("P1_joint_map") or {}
        if isinstance(p1, dict) and attribute in p1 and not p1.get("_abstain"):
            values["P1_joint_map"][attribute] = normalize(p1.get(attribute), attribute, literals)
        p3 = outputs.get("P3_compressed_map") or {}
        if isinstance(p3, dict) and isinstance(p3.get(attribute), dict):
            values["P3_compressed_map"][attribute] = normalize(p3[attribute].get("value"), attribute, literals)
        elif isinstance(p3, dict) and attribute in p3 and not isinstance(p3.get(attribute), dict):
            values["P3_compressed_map"][attribute] = normalize(p3.get(attribute), attribute, literals)
        for plan, key in (("P2_split_gather", "selected"), ("P4_evidence_ledger", "selected"), ("P5_candidate_card", "choices")):
            blob = outputs.get(plan) or {}
            if plan == "P5_candidate_card" and isinstance(blob.get("choices"), dict):
                cid = blob["choices"].get(attribute)
                row = by_id.get(cid)
                if row is not None:
                    values[plan][attribute] = row["value"]
                elif cid in {"LEAVE_NULL", "KEEP_PLUMBING"}:
                    values[plan][attribute] = None
            else:
                for cid in blob.get(key) or []:
                    row = by_id.get(cid)
                    if row and row["attribute"] == attribute:
                        values[plan][attribute] = row["value"]
                        break
    return values


def commit_cells(plan_map: dict[str, dict[str, Any]], cands: list[dict[str, Any]], attributes: list[str], p1_full: bool, p2_complete: bool) -> dict[str, dict[str, Any]]:
    committed = {}
    by_value: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in cands:
        if candidate["value"] is not None:
            by_value[(candidate["attribute"], str(candidate["value"]))] = candidate
    for attribute in attributes:
        votes: dict[Any, list[str]] = defaultdict(list)
        for plan, payload in plan_map.items():
            if attribute in payload:
                votes[payload[attribute]].append(plan)
        agreed = [value for value, plans in votes.items() if value is not None and len(plans) >= 2]
        if len(agreed) == 1:
            candidate = by_value.get((attribute, str(agreed[0])))
            committed[attribute] = {"state": "committed", "value": agreed[0], "candidate_id": None if candidate is None else candidate["candidate_id"], "plans": votes[agreed[0]]}
        elif len(agreed) > 1:
            committed[attribute] = {"state": "UNCERTAIN", "value": None, "reason": "disagreement"}
        elif p1_full and "P1_joint_map" in plan_map and plan_map["P1_joint_map"].get(attribute) is not None:
            value = plan_map["P1_joint_map"][attribute]
            candidate = by_value.get((attribute, str(value)))
            if candidate and candidate.get("start") is not None:
                committed[attribute] = {"state": "committed", "value": value, "candidate_id": candidate["candidate_id"], "plans": ["P1_joint_map", "verifier"]}
            else:
                committed[attribute] = {"state": "UNCERTAIN", "value": None, "reason": "unverifiable"}
        elif (p1_full or p2_complete) and all(plan_map.get(plan, {}).get(attribute) is None for plan in plan_map if attribute in plan_map.get(plan, {})) and plan_map:
            if any(attribute in payload for payload in plan_map.values()):
                committed[attribute] = {"state": "committed", "value": None, "candidate_id": "LEAVE_NULL", "plans": ["absence"]}
            else:
                committed[attribute] = {"state": "UNCERTAIN", "value": None, "reason": "no_plan"}
        else:
            committed[attribute] = {"state": "UNCERTAIN", "value": None, "reason": "insufficient_agreement"}
    return committed


def fit_logistic(rows: list[list[float]], labels: list[float]) -> list[float]:
    if not rows:
        return [0.0]
    width = len(rows[0])
    weights = [0.0] * (width + 1)
    for _ in range(160):
        gradient = [0.0] * (width + 1)
        for features, label in zip(rows, labels):
            score = weights[0] + sum(weight * value for weight, value in zip(weights[1:], features))
            score = max(-20.0, min(20.0, score))
            probability = 1.0 / (1.0 + pow(2.718281828, -score))
            error = probability - label
            gradient[0] += error
            for index, value in enumerate(features):
                gradient[index + 1] += error * value
        scale = max(1, len(rows))
        for index in range(len(weights)):
            weights[index] -= 0.35 * gradient[index] / scale
    return weights


def logistic_probability(weights: list[float], features: list[float]) -> float:
    score = weights[0] + sum(weight * value for weight, value in zip(weights[1:], features))
    score = max(-20.0, min(20.0, score))
    return 1.0 / (1.0 + pow(2.718281828, -score))


def feature_vector(features: dict[str, float]) -> list[float]:
    return [features[key] for key in sorted(features)]


def ht_rate(records: list[tuple[float, float]]) -> tuple[float, float]:
    if not records:
        return 0.0, 1.0
    weight = sum(1.0 / pi for _, pi in records if pi > 0)
    total = sum(value / pi for value, pi in records if pi > 0)
    rate = total / weight if weight else 0.0
    variance = sum(((value - rate) / pi) ** 2 for value, pi in records if pi > 0)
    se = (variance ** 0.5) / weight if weight else 1.0
    return rate, max(se, 1e-6)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "frozen.json").exists() and os.environ.get("WCCI_FORCE") != "1":
        print(json.dumps({"already_frozen": str(OUT / "frozen.json")}), flush=True)
        return
    (OUT / "design_frozen.json").write_text(json.dumps(DESIGN, indent=2, sort_keys=True))
    design_hash = sha(DESIGN)
    (OUT / "design_frozen.sha256").write_text(design_hash + "\n")
    print(json.dumps({"design_sha256": design_hash}), flush=True)

    queries = json.loads(MANIFEST.read_text())
    attributes, literals, pairs = workload_columns(queries)
    descriptions = load_descriptions()
    documents = read_documents()
    if len(documents) != 570:
        raise SystemExit(f"expected 570 documents, found {len(documents)}")
    plumbing = plumbing_rows()
    texts = dict(documents)
    candidates: dict[str, list[dict[str, Any]]] = {}
    features: dict[str, dict[str, dict[str, float]]] = {}
    for doc, text in documents:
        rows = build_candidates(doc, text, attributes, literals, descriptions, plumbing[doc])
        candidates[doc] = rows
        features[doc] = {row["candidate_id"]: featurize(row, text, descriptions, literals) for row in rows}
    rare = {label for labels in literals.values() for label in labels}
    meta = strata_for(documents, candidates, plumbing, attributes, rare)
    probabilities = draw_sample(meta, DESIGN["sample_size"], DESIGN["seed"])
    roles = split_sample(probabilities, DESIGN["seed"])
    sample_manifest = {
        "design_sha256": design_hash,
        "attributes": attributes,
        "literals": {key: sorted(value) for key, value in literals.items()},
        "pairs": pairs,
        "sample_size": len(probabilities),
        "inclusion_probabilities": probabilities,
        "roles": roles,
        "strata": {doc: meta[doc] for doc in probabilities},
    }
    (OUT / "sample_frozen.json").write_text(json.dumps(sample_manifest, indent=2))
    (OUT / "sample_frozen.sha256").write_text(sha(sample_manifest) + "\n")
    inventory_hash = sha({doc: [row["candidate_id"] for row in rows] for doc, rows in candidates.items()})
    (OUT / "inventory_frozen.sha256").write_text(inventory_hash + "\n")
    print(json.dumps({"sample": len(probabilities), "inventory_sha256": inventory_hash, "roles": dict(Counter(roles.values()))}), flush=True)

    load_env_file(ROOT / ".env")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY is not set")
    ledger = TokenLedger(theta=DESIGN["theta"], seed=DESIGN["seed"])
    caller = make_caller(ledger, model=DESIGN["model"], temperature=0.0, max_tokens=700)
    journal_path = OUT / "journal.jsonl"
    journal_lock = threading.Lock()
    done = set()
    if journal_path.exists():
        for line in journal_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done.add((row["plan_group"], row["document_id"]))
    phase_spent = [0]
    probe_cap = DESIGN["budget_allocation"]["probe_and_checked_references"]

    def journal(row: dict[str, Any]) -> None:
        with journal_lock:
            with journal_path.open("a") as handle:
                handle.write(json.dumps(row, default=str) + "\n")

    probe_docs = [doc for doc, role in roles.items() if role in {"train", "validation"}]
    all_plans = set(DESIGN["plans"])
    for index, doc in enumerate(probe_docs):
        if ("probe", doc) in done:
            continue
        outputs = probe_document(caller, doc, texts[doc], candidates[doc], attributes, descriptions, probe_cap, phase_spent, journal_lock, all_plans)
        p1_full = not (outputs.get("P1_joint_map") or {}).get("_abstain")
        p2_complete = bool((outputs.get("P2_split_gather") or {}).get("complete"))
        values = plan_values(outputs, candidates[doc], attributes, literals)
        committed = commit_cells(values, candidates[doc], attributes, p1_full, p2_complete)
        journal({"plan_group": "probe", "document_id": doc, "role": roles[doc], "outputs": outputs, "values": values, "committed": committed, "spent": ledger.spent})
        if index % 8 == 0:
            print(json.dumps({"probed": index + 1, "of": len(probe_docs), "spent": ledger.spent}), flush=True)
        if ledger.spent >= probe_cap:
            print(json.dumps({"probe_stopped_at_allocation": ledger.spent}), flush=True)
            break

    probed = {}
    for line in journal_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["plan_group"] == "probe":
            probed[row["document_id"]] = row

    def committed_records(role: str) -> dict[str, dict[str, dict[str, Any]]]:
        return {doc: row["committed"] for doc, row in probed.items() if roles.get(doc) == role and "committed" in row}

    train = committed_records("train")
    validation = committed_records("validation")

    def training_matrix(split: dict[str, dict[str, dict[str, Any]]]):
        rows, labels = [], []
        for doc, cells in split.items():
            by_id = {candidate["candidate_id"]: candidate for candidate in candidates[doc]}
            for attribute, cell in cells.items():
                if cell.get("state") != "committed":
                    continue
                target_id = cell.get("candidate_id")
                target_value = cell.get("value")
                for candidate in candidates[doc]:
                    if candidate["attribute"] != attribute:
                        continue
                    matched = candidate["candidate_id"] == target_id or (target_value is not None and candidate["value"] == target_value)
                    if cell.get("value") is None and candidate["channel"] == "LEAVE_NULL":
                        matched = True
                    rows.append(feature_vector(features[doc][candidate["candidate_id"]]))
                    labels.append(1.0 if matched else 0.0)
                    by_id.setdefault(candidate["candidate_id"], candidate)
        return rows, labels

    train_x, train_y = training_matrix(train)
    weights = fit_logistic(train_x, train_y)
    (OUT / "scorer_frozen.json").write_text(json.dumps({"weights": weights, "feature_order": sorted(next(iter(next(iter(features.values())).values()))) if features else []}, indent=2))
    (OUT / "scorer_frozen.sha256").write_text(sha({"weights": weights}) + "\n")

    def cell_choice(doc: str, attribute: str) -> tuple[str, Any, float]:
        best_id, best_value, best_p = "LEAVE_NULL", None, 0.0
        for candidate in candidates[doc]:
            if candidate["attribute"] != attribute:
                continue
            if plumbing[doc].get(attribute) not in (None, ""):
                return "KEEP_PLUMBING", plumbing[doc].get(attribute), 1.0
            probability = logistic_probability(weights, feature_vector(features[doc][candidate["candidate_id"]]))
            if candidate["channel"] == "LEAVE_NULL":
                probability = max(probability, 0.34)
            if probability > best_p:
                best_id, best_value, best_p = candidate["candidate_id"], candidate["value"], probability
        return best_id, best_value, best_p

    def assignment_for(mode: str) -> dict[tuple[str, str], Any]:
        chosen = {}
        for doc, _text in documents:
            for attribute in attributes:
                if plumbing[doc].get(attribute) not in (None, ""):
                    chosen[(doc, attribute)] = plumbing[doc].get(attribute)
                    continue
                cid, value, probability = cell_choice(doc, attribute)
                if mode == "plumbing":
                    chosen[(doc, attribute)] = None
                elif mode == "conservative" and probability < 0.8:
                    chosen[(doc, attribute)] = None
                elif mode == "bootstrap_robust" and probability < 0.65:
                    chosen[(doc, attribute)] = None
                else:
                    chosen[(doc, attribute)] = value
        if mode in {"pairwise", "query_observable", "full_wcci"}:
            for left, right in pairs:
                both = []
                for doc, cells in {**train, **validation}.items():
                    left_cell = cells.get(left) or {}
                    right_cell = cells.get(right) or {}
                    if left_cell.get("state") == "committed" and right_cell.get("state") == "committed":
                        flag = 1.0 if left_cell.get("value") is not None and right_cell.get("value") is not None else 0.0
                        both.append((flag, probabilities[doc]))
                rate, se = ht_rate(both)
                observed = sum(1.0 if chosen[(doc, left)] is not None and chosen[(doc, right)] is not None else 0.0 for doc, _ in documents) / len(documents)
                if se and abs(observed - rate) / se > 1.96 and observed > rate:
                    ranked = sorted(documents, key=lambda item: cell_choice(item[0], left)[2] + cell_choice(item[0], right)[2])
                    for doc, _text in ranked:
                        if chosen[(doc, left)] is None or chosen[(doc, right)] is None:
                            continue
                        if plumbing[doc].get(left) in (None, "") and cell_choice(doc, left)[2] <= cell_choice(doc, right)[2]:
                            chosen[(doc, left)] = None
                        elif plumbing[doc].get(right) in (None, ""):
                            chosen[(doc, right)] = None
                        observed = sum(1.0 if chosen[(item, left)] is not None and chosen[(item, right)] is not None else 0.0 for item, _ in documents) / len(documents)
                        if abs(observed - rate) / se <= 1.96:
                            break
        if mode in {"univariate", "pairwise", "query_observable", "full_wcci"}:
            for attribute in attributes:
                committed_flags = []
                for doc, cells in {**train, **validation}.items():
                    cell = cells.get(attribute) or {}
                    if cell.get("state") == "committed":
                        committed_flags.append((1.0 if cell.get("value") is not None else 0.0, probabilities[doc]))
                rate, se = ht_rate(committed_flags)
                current = [1.0 if chosen[(doc, attribute)] is not None else 0.0 for doc, _ in documents]
                observed = sum(current) / len(current)
                z = abs(observed - rate) / se
                if z > 1.96 and observed > rate:
                    ranked = sorted(documents, key=lambda item: cell_choice(item[0], attribute)[2])
                    for doc, _text in ranked:
                        if plumbing[doc].get(attribute) not in (None, "") or chosen[(doc, attribute)] is None:
                            continue
                        chosen[(doc, attribute)] = None
                        observed = sum(1.0 if chosen[(item, attribute)] is not None else 0.0 for item, _ in documents) / len(documents)
                        if abs(observed - rate) / se <= 1.96:
                            break
        return chosen

    def utility(assignment: dict[tuple[str, str], Any], split: dict[str, dict[str, dict[str, Any]]]) -> float:
        total = 0
        matched = 0
        for doc, cells in split.items():
            for attribute, cell in cells.items():
                if cell.get("state") != "committed":
                    continue
                total += 1
                if assignment.get((doc, attribute)) == cell.get("value"):
                    matched += 1
        return matched / total if total else 0.0

    def lower_bound(assignment: dict[tuple[str, str], Any]) -> float:
        docs = sorted(validation)
        if not docs:
            return 0.0
        rng = random.Random(DESIGN["seed"] + 7)
        scores = []
        for _ in range(30):
            draw = [docs[rng.randrange(len(docs))] for _ in docs]
            subset = {doc: validation[doc] for doc in draw if doc in validation}
            scores.append(utility(assignment, subset))
        scores.sort()
        return scores[max(0, int(0.05 * (len(scores) - 1)))]

    variants = {}
    for name in DESIGN["plan_variants"]:
        assignment = assignment_for(name)
        writes = sum(1 for (doc, attribute), value in assignment.items() if plumbing[doc].get(attribute) in (None, "") and value is not None)
        violation = 0.0
        for attribute in attributes:
            flags = []
            for doc, cells in {**train, **validation}.items():
                cell = cells.get(attribute) or {}
                if cell.get("state") == "committed":
                    flags.append((1.0 if cell.get("value") is not None else 0.0, probabilities[doc]))
            rate, se = ht_rate(flags)
            observed = sum(1.0 if assignment[(doc, attribute)] is not None else 0.0 for doc, _text in documents) / len(documents)
            violation += max(0.0, abs(observed - rate) / se - 1.96) ** 2
        variants[name] = {
            "utility": utility(assignment, validation),
            "lower_bound": lower_bound(assignment),
            "moment_violation": violation,
            "writes": writes,
            "tokens": ledger.spent,
            "assignment": assignment,
        }
        print(json.dumps({"variant": name, "utility": variants[name]["utility"], "lcb": variants[name]["lower_bound"], "writes": writes}), flush=True)
    selected = sorted(
        variants,
        key=lambda name: (
            -variants[name]["lower_bound"],
            variants[name]["moment_violation"],
            variants[name]["tokens"],
            variants[name]["writes"],
            name,
        ),
    )[0]
    official = variants[selected]["assignment"]

    # Generalization calls on the untouched test split happen after the scorer is frozen.
    phase_spent[0] = 0
    validation_cap = DESIGN["budget_allocation"]["validation_calls"]
    for doc, role in roles.items():
        if role != "test" or ("test", doc) in done:
            continue
        outputs = probe_document(caller, doc, texts[doc], candidates[doc], attributes, descriptions, validation_cap, phase_spent, journal_lock, {"P1_joint_map", "P5_candidate_card"})
        values = plan_values(outputs, candidates[doc], attributes, literals)
        p1_full = not (outputs.get("P1_joint_map") or {}).get("_abstain")
        committed = commit_cells(values, candidates[doc], attributes, p1_full, False)
        journal({"plan_group": "test", "document_id": doc, "outputs": outputs, "committed": committed, "spent": ledger.spent})
        if ledger.spent >= DESIGN["budget_allocation"]["probe_and_checked_references"] + validation_cap:
            break
    test_rows = {}
    for line in journal_path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            if row["plan_group"] == "test":
                test_rows[row["document_id"]] = row.get("committed") or {}
    test_utility = utility(official, test_rows)

    database = OUT / "legal_wcci.db"
    if database.exists():
        database.unlink()
    shutil.copy(PLUMBING, database)
    conn = sqlite3.connect(database)
    entity_before = list(conn.execute('SELECT doc_id, "__entity_id" FROM legal ORDER BY doc_id'))
    writes = 0
    for (doc, attribute), value in official.items():
        current = conn.execute(f'SELECT "{attribute}" FROM legal WHERE doc_id = ?', (doc,)).fetchone()
        if current is None:
            continue
        if current[0] not in (None, ""):
            continue
        if value is None:
            continue
        conn.execute(f'UPDATE legal SET "{attribute}" = ? WHERE doc_id = ? AND ("{attribute}" IS NULL OR "{attribute}" = "")', (value, doc))
        writes += 1
    conn.commit()
    entity_after = list(conn.execute('SELECT doc_id, "__entity_id" FROM legal ORDER BY doc_id'))
    row_count = conn.execute("SELECT COUNT(*) FROM legal").fetchone()[0]
    conn.close()
    if entity_before != entity_after or row_count != 570:
        raise SystemExit("entity ids or row count changed")

    from quwarts.core.pipeline import official_sql
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates
    from quwarts.core.observable_sidecar import bag_hash

    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    statements = {row["query_id"]: row["sql"] for row in queries}
    bags = {}
    failures = []
    read = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    for qid, sql in statements.items():
        rewritten = official_sql(sql, database, predicates, query_id=qid)
        try:
            cursor = read.execute(rewritten)
            columns = [item[0] for item in cursor.description] if cursor.description else []
            bags[qid] = [dict(zip(columns, record)) for record in cursor.fetchall()]
        except sqlite3.Error as exc:
            failures.append({"query_id": qid, "error": str(exc)})
            bags[qid] = []
    read.close()
    plumbing_bags = {}
    base = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    for qid, sql in statements.items():
        cursor = base.execute(sql)
        columns = [item[0] for item in cursor.description] if cursor.description else []
        plumbing_bags[qid] = [dict(zip(columns, record)) for record in cursor.fetchall()]
    base.close()
    manifest = {
        "selected_plan": selected,
        "test_utility": test_utility,
        "variants": {name: {key: value for key, value in row.items() if key != "assignment"} for name, row in variants.items()},
        "writes": writes,
        "ledger_spent": ledger.spent,
        "database_sha256": file_sha(database),
        "bag_sha256": bag_hash(bags),
        "failures": failures,
        "row_count": row_count,
        "design_sha256": design_hash,
        "gold_loaded": False,
    }
    (OUT / "assignment_manifest.json").write_text(json.dumps({
        "selected_plan": selected,
        "writes": writes,
        "cells": {f"{doc}|{attribute}": value for (doc, attribute), value in official.items()},
    }))
    (OUT / "frozen.json").write_text(json.dumps(manifest, indent=2, default=str))
    (OUT / "bags.json").write_text(json.dumps(bags, default=str))
    (OUT / "ledger.json").write_text(json.dumps(ledger.snapshot(), default=str))
    if failures or ledger.spent > DESIGN["theta"]:
        (OUT / "REPORT.md").write_text("# WCCI\n\nConclusion: `run invalid`\n")
        print(json.dumps({"conclusion": "run invalid", "failures": failures, "spent": ledger.spent}), flush=True)
        return

    _FROZEN["ok"] = True
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
    from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

    gold = load_ground_truth(gold_name("Legal"))
    full = {row["query_id"]: row for row in queries_for("Legal")}
    rewrites = {qid: {"sql": official_sql(sql, database, predicates, query_id=qid), "sqlite_path": str(database)} for qid, sql in statements.items()}
    rows = [{"query_id": qid, "sql": sql, "pack": (full.get(qid) or {}).get("pack")} for qid, sql in statements.items()]
    report = score_with_rewrites(rows, rewrites, PLUMBING, gold, "Legal")
    product = mean_per_query_product(report)
    per_query = [
        {
            "query_id": row["query_id"],
            "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
            "structure_f2": row.get("structure_f2"),
            "cell_f1_20": row.get("cell_f1_20"),
        }
        for row in report.get("per_query") or []
    ]
    if product > DOCETL_PRODUCT:
        conclusion = "workload-calibrated collective inference beats Legal DocETL"
    elif product > 0.022455905439098717 and test_utility + 1e-9 < variants[selected]["utility"]:
        conclusion = "probe estimates do not generalize"
    elif product > 0.022455905439098717:
        conclusion = "collective inference improves Legal but remains below DocETL"
    else:
        conclusion = "probe estimates do not generalize"
    # The preselected plan stays official. Ablations reuse the frozen scorer and are diagnostic.
    ablation_products = {"official": product}
    lines = [
        "# Workload-calibrated collective inference",
        "",
        f"Conclusion: `{conclusion}`",
        "",
        f"Selected plan: `{selected}`",
        f"Product: {product}",
        f"F2: {report.get('mean_structure_f2')}",
        f"Cell F1@0.20: {mean_cell_f1_20(report)}",
        f"DocETL product: {DOCETL_PRODUCT}",
        f"Tokens: {ledger.spent}",
        f"Writes: {writes}",
        f"Probe-validation utility: {variants[selected]['utility']}",
        f"Probe-test utility: {test_utility}",
        f"Design hash: `{design_hash}`",
        f"Database hash: `{manifest['database_sha256']}`",
        f"Bag hash: `{manifest['bag_sha256']}`",
        "",
        "| query | product |",
        "| --- | ---: |",
    ]
    for row in per_query:
        lines.append(f"| {row['query_id']} | {row['product']} |")
    lines.extend(["", "No further Legal prompt, vote, replica, or budget increase follows from this arm.", ""])
    (OUT / "REPORT.md").write_text("\n".join(lines))
    (OUT / "scores.json").write_text(json.dumps({"conclusion": conclusion, "product": product, "per_query": per_query, "ablations": ablation_products, "selected_plan": selected, "test_utility": test_utility, "spent": ledger.spent}, indent=2))
    print(json.dumps({"conclusion": conclusion, "product": product, "selected": selected, "spent": ledger.spent, "test_utility": test_utility}), flush=True)


if __name__ == "__main__":
    main()

"""Fused query-conditioned map execution for the 16 Legal queries.

Compatible queries share one document transmission. Each query keeps its own
output namespace, relation, and official SQL. The grouping plan is frozen
before any corpus call.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


_FROZEN: dict[str, bool] = {"ok": False}
_ORIGINAL_OPEN = open


def _blocked(path: Path) -> bool:
    if _FROZEN["ok"]:
        return False
    text = str(path)
    name = path.name
    if name in {"query_manifest.json", "Legal_attributes.json"}:
        return False
    if "quwarts_legal_plumbing" in text or "source_data" in text or "qwen25_tokenizer.json" in text:
        return False
    if "quwarts_legal_fused_query_maps" in text:
        return False
    if "docetl-main" in text and "results" not in text:
        return False
    forbidden = (
        "ground_truth",
        "/gold/",
        "gold.json",
        "extract_fields.json",
        "pipeline_output.json",
        "query_results.json",
        "query_tables",
        "evaluation.json",
        "summary.json",
        "shared_reachability",
        "cost_aware_reachability",
        "diagnostic_scores",
        "evidence_card",
        "quwarts_legal_",
        "Data/Legal",
        "docetl_cache",
        ".cache",
    )
    return any(part in text for part in forbidden)


def _guard_open(file, mode="r", *args, **kwargs):
    path = Path(file)
    if any(flag in mode for flag in ("r", "+")) and "b" not in mode and _blocked(path):
        raise PermissionError(f"blocked before the fused-map freeze: {path}")
    return _ORIGINAL_OPEN(file, mode, *args, **kwargs)


import builtins

builtins.open = _guard_open

PROJECT = Path(__file__).resolve().parents[4]
WDIRS = PROJECT / "systems" / "WDIRS"
DOCETL = PROJECT / "systems" / "docetl-main"
for entry in (WDIRS, DOCETL, PROJECT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from docetl.operations.utils.validation import strict_render, validate_output_types  # noqa: E402
from quwarts.core.docetl_unit_parity.schema import compile_query_schema  # noqa: E402
from quwarts.core.ledger import BudgetExhausted, TokenLedger  # noqa: E402
from quwarts.core.llm.openrouter import load_env_file, make_caller  # noqa: E402
from quwarts.core.observable_sidecar import bag_hash, identity_checksum  # noqa: E402
from quwarts.core.pipeline import official_sql  # noqa: E402
from quwarts.core.retrieve_extract.tokens import count_tokens  # noqa: E402
from quwarts.core.signature import audit_workload, enumerate_predicates  # noqa: E402
from quwarts.core.signature_realize import live_predicates  # noqa: E402


OUT = PROJECT / "results" / "quwarts_legal_fused_query_maps"
PLUMBING = PROJECT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
MANIFEST = PROJECT / "results" / "docetl_legal_case80" / "query_manifest.json"
ATTRIBUTES = PROJECT / "Query" / "Legal" / "Legal_attributes.json"
DOCS = PROJECT / "source_data" / "Legal" / "legal_case"
MODEL = "qwen/qwen-2.5-7b-instruct"
TEMPERATURE = 0.1
MAX_TOKENS = 280
INPUT_CAP = 6000
WORKERS = 4
SEED = 20260922
THETA = {"theta25": 12_610_011, "theta50": 25_220_022, "theta75": 37_830_032}
DOCETL_PRODUCT = 0.12350932750098194
DOCETL_TOKENS = 50_440_043
WCCI_PRODUCT = 0.09594618648894966
PLUMBING_PRODUCT = 0.022455905439098717
OFFICIAL_POLICY = "fusion_same_attribute"
SENTINEL = None
MAP_TEMPLATE = """Treat each query as an independent extraction task.
Return a separate result object for each query.
Do not copy SQL constants unless supported by the document.
Do not compute the final SQL result.

DOCUMENT:
{{ input.document }}

{% for query in input.queries %}
QUERY {{ query.query_id }}
SQL context, not a request to answer the query:
{{ query.sql }}
Missing value: null
Fields:
{% for field in query.fields %}
- {{ field.name }} ({{ field.type }}): {{ field.description }}
  workload domain: {{ field.domain }}
{% endfor %}
{% endfor %}

Return JSON with this shape and no other keys:
{"query_results":[{"query_id":"<id>","fields":{"<field>": <typed value or null>}}]}
"""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical(row) + "\n")


def load_queries() -> list[dict[str, Any]]:
    payload = json.loads(MANIFEST.read_text())
    return [
        {"query_id": item["query_id"], "sql": item["sql"], "pack": str(item["query_id"]).split(":", 1)[0]}
        for item in payload
    ]


def load_descriptions() -> dict[str, dict[str, Any]]:
    payload = json.loads(ATTRIBUTES.read_text())
    return payload["legal_case"]


def read_documents() -> list[tuple[str, str]]:
    paths = sorted(DOCS.glob("*.txt"), key=lambda path: int(path.stem) if path.stem.isdigit() else path.stem)
    return [(f"{path.stem}.txt", path.read_text(errors="replace")) for path in paths]


def workload_domains(sql: str) -> dict[str, list[str]]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    found: dict[str, list[str]] = defaultdict(list)
    for node in tree.find_all((exp.EQ, exp.NEQ, exp.In)):
        column = next(node.find_all(exp.Column), None)
        if column is None:
            continue
        values = []
        for literal in node.find_all(exp.Literal):
            if literal.is_string:
                text = str(literal.this)
                if text and text not in values:
                    values.append(text)
        if values:
            found[column.name].extend(value for value in values if value not in found[column.name])
    return dict(found)


def contracts_for(queries: list[dict[str, Any]], descriptions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    compiled: dict[str, dict[str, Any]] = {}
    for query in queries:
        schema = compile_query_schema(query["query_id"], query["sql"])
        domains = workload_domains(query["sql"])
        fields = []
        for item in schema.fields:
            spec = descriptions.get(item.name) or {}
            physical = "int" if spec.get("value_type") == "int" else "str"
            fields.append(
                {
                    "name": item.name,
                    "type": physical,
                    "description": spec.get("description") or item.description,
                    "domain": domains.get(item.name) or [],
                    "usages": item.usages,
                }
            )
        compiled[query["query_id"]] = {
            "query_id": query["query_id"],
            "sql": query["sql"],
            "pack": query["pack"],
            "fields": fields,
            "names": [field["name"] for field in fields],
        }
    return compiled


def contract_view(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_id": contract["query_id"],
        "sql": contract["sql"],
        "fields": [
            {
                "name": field["name"],
                "type": field["type"],
                "description": field["description"],
                "domain": ", ".join(field["domain"]) if field["domain"] else "unrestricted",
            }
            for field in contract["fields"]
        ],
    }


def render_prompt(document: str, group: list[dict[str, Any]]) -> str:
    return strict_render(MAP_TEMPLATE, {"input": {"document": document, "queries": [contract_view(item) for item in group]}})


def schema_tokens(contract: dict[str, Any]) -> int:
    return count_tokens(render_prompt("", [contract]))


def completion_estimate(n_fields: int, n_queries: int) -> int:
    return 36 + n_queries * 22 + n_fields * 14


def prompt_cost(doc_tokens: int, overhead: int) -> int:
    if doc_tokens + overhead <= INPUT_CAP:
        return doc_tokens + overhead + MAX_TOKENS
    return INPUT_CAP + MAX_TOKENS


def pair_stats(left: dict[str, Any], right: dict[str, Any], doc_tokens: list[int]) -> dict[str, Any] | None:
    left_names = {field["name"]: field for field in left["fields"]}
    right_names = {field["name"]: field for field in right["fields"]}
    shared = sorted(set(left_names) & set(right_names))
    union = sorted(set(left_names) | set(right_names))
    if len(union) > 6:
        return None
    for name in shared:
        if left_names[name]["type"] != right_names[name]["type"]:
            return None
    if completion_estimate(len(union), 2) > MAX_TOKENS:
        return None
    left_overhead = schema_tokens(left)
    right_overhead = schema_tokens(right)
    fused_overhead = count_tokens(render_prompt("", [left, right]))
    single = sum(prompt_cost(tokens, left_overhead) + prompt_cost(tokens, right_overhead) for tokens in doc_tokens)
    fused = sum(prompt_cost(tokens, fused_overhead) for tokens in doc_tokens)
    if fused >= single:
        return None
    risk = 0.0
    for name in shared:
        left_domain = set(left_names[name]["domain"])
        right_domain = set(right_names[name]["domain"])
        if left_domain and right_domain and left_domain != right_domain:
            risk += 1.0 if left_domain.isdisjoint(right_domain) else 0.5
    return {
        "queries": [left["query_id"], right["query_id"]],
        "union": len(union),
        "overlap": len(shared),
        "risk": risk,
        "savings": single - fused,
        "fused_cost": fused,
        "single_cost": single,
        "shared": shared,
    }


def partition(contracts: dict[str, dict[str, Any]], doc_tokens: list[int], blocked: set[tuple[str, str]]) -> list[list[str]]:
    ids = sorted(contracts)
    index = {query_id: bit for bit, query_id in enumerate(ids)}
    eligible: dict[tuple[int, int], dict[str, Any]] = {}
    single_cost = {query_id: sum(prompt_cost(tokens, schema_tokens(contracts[query_id])) for tokens in doc_tokens) for query_id in ids}
    for left_at, left_id in enumerate(ids):
        for right_id in ids[left_at + 1 :]:
            key = tuple(sorted((left_id, right_id)))
            if key in blocked:
                continue
            stats = pair_stats(contracts[left_id], contracts[right_id], doc_tokens)
            if stats is not None:
                eligible[(index[left_id], index[right_id])] = stats
    best: dict[int, tuple] = {0: (0, 0, 0, 0.0, ())}
    width = len(ids)
    for mask in range(1 << width):
        if mask not in best:
            continue
        key = best[mask]
        free = [bit for bit in range(width) if mask & (1 << bit) == 0]
        for bit in free:
            nxt = mask | (1 << bit)
            groups = tuple(sorted(key[4] + ((ids[bit],),)))
            candidate = (
                key[0] + single_cost[ids[bit]],
                max(key[1], len(contracts[ids[bit]]["names"])),
                key[2],
                key[3],
                groups,
            )
            if nxt not in best or candidate < best[nxt]:
                best[nxt] = candidate
        for left_at, left in enumerate(free):
            for right in free[left_at + 1 :]:
                stats = eligible.get((min(left, right), max(left, right)))
                if stats is None:
                    continue
                nxt = mask | (1 << left) | (1 << right)
                groups = tuple(sorted(key[4] + (tuple(stats["queries"]),)))
                candidate = (
                    key[0] + stats["fused_cost"],
                    max(key[1], stats["union"]),
                    key[2] - stats["overlap"],
                    key[3] + stats["risk"],
                    groups,
                )
                if nxt not in best or candidate < best[nxt]:
                    best[nxt] = candidate
    full = (1 << width) - 1
    if full not in best:
        raise SystemExit("run invalid: queries were not covered")
    return [list(group) for group in best[full][4]]


def locate_sections(document: str, contract: dict[str, Any]) -> list[tuple[int, int]]:
    needles = []
    for field in contract["fields"]:
        needles.append(field["name"].replace("_", " "))
        needles.extend(field["domain"])
        for token in re.findall(r"[A-Za-z]{5,}", field["description"])[:6]:
            needles.append(token)
    spans = []
    lowered = document.lower()
    for needle in needles:
        probe = needle.lower()
        if len(probe) < 3:
            continue
        start = 0
        while True:
            found = lowered.find(probe, start)
            if found < 0:
                break
            spans.append((max(0, found - 220), min(len(document), found + len(needle) + 220)))
            start = found + len(probe)
    if not spans:
        spans = [(0, min(len(document), 1800))]
    spans.sort()
    merged: list[list[int]] = []
    for left, right in spans:
        if not merged or left > merged[-1][1] + 40:
            merged.append([left, right])
        else:
            merged[-1][1] = max(merged[-1][1], right)
    return [(left, right) for left, right in merged]


def pack_sections(document: str, spans: list[tuple[int, int]]) -> str:
    return "\n\n".join(document[left:right] for left, right in spans)


def route_group(document: str, group: list[dict[str, Any]]) -> dict[str, Any]:
    whole = render_prompt(document, group)
    if count_tokens(whole) <= INPUT_CAP:
        return {"mode": "whole_document", "spans": [[0, len(document)]], "split": False}
    per_query = [locate_sections(document, contract) for contract in group]
    union: list[tuple[int, int]] = []
    for spans in per_query:
        union.extend(spans)
    union = locate_sections(document, {"fields": [field for contract in group for field in contract["fields"]]})
    # Keep every singleton span even if the union finder drops one.
    required = []
    for spans in per_query:
        required.extend(spans)
    required.sort()
    merged: list[list[int]] = []
    for left, right in required:
        if not merged or left > merged[-1][1]:
            merged.append([left, right])
        else:
            merged[-1][1] = max(merged[-1][1], right)
    packed = pack_sections(document, [(left, right) for left, right in merged])
    prompt = render_prompt(packed, group)
    if count_tokens(prompt) <= INPUT_CAP:
        return {"mode": "sections", "spans": merged, "split": False}
    return {"mode": "split", "spans": per_query, "split": True}


def normalize_value(field: dict[str, Any], value: Any) -> tuple[Any, str | None]:
    if value is None or value == "null":
        return None, None
    if field["type"] == "int":
        text = str(value).replace(",", "").strip()
        if re.fullmatch(r"-?\d+", text):
            return int(text), None
        return value, "wrong type"
    text = str(value).strip()
    if not text:
        return None, None
    for option in field["domain"]:
        if text.lower() == option.lower():
            return option, None
    if field["domain"]:
        return text, "wrong type"
    return text, None


def validate_subresult(contract: dict[str, Any], payload: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "malformed output"
    if payload.get("query_id") != contract["query_id"]:
        return None, "malformed output"
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return None, "malformed output"
    expected = {field["name"] for field in contract["fields"]}
    if set(fields) - expected:
        return None, "malformed output"
    missing = [name for name in expected if name not in fields]
    if missing:
        return None, "missing field"
    normalized: dict[str, Any] = {}
    schema: dict[str, str] = {}
    present: dict[str, Any] = {}
    for field in contract["fields"]:
        value, error = normalize_value(field, fields[field["name"]])
        if error:
            return None, error
        normalized[field["name"]] = value
        if value is not None:
            schema[field["name"]] = field["type"]
            present[field["name"]] = value
    if present:
        valid, errors = validate_output_types(present, schema, model=MODEL)
        if not valid:
            return None, "wrong type" if any("type" in error.lower() for error in errors) else "malformed output"
    return {"query_id": contract["query_id"], "fields": normalized}, None


def parse_fused(text: str) -> list[dict[str, Any]]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return []
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    rows = payload.get("query_results") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and "query_id" in payload and "fields" in payload:
        rows = [payload]
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def apply_same_attribute(group: list[dict[str, Any]], results: dict[str, dict[str, Any]], policy: str) -> dict[str, dict[str, Any]]:
    if policy != "fusion_same_attribute":
        return results
    by_name: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for contract in group:
        for field in contract["fields"]:
            by_name[field["name"]].append((contract["query_id"], field))
    updated = {query_id: {"query_id": query_id, "fields": dict(row["fields"])} for query_id, row in results.items()}
    for name, owners in by_name.items():
        if len(owners) < 2:
            continue
        donors = [(query_id, field) for query_id, field in owners if updated[query_id]["fields"].get(name) is not None]
        if len(donors) != 1:
            continue
        donor_id, donor_field = donors[0]
        for query_id, field in owners:
            if query_id == donor_id or field["type"] != donor_field["type"]:
                continue
            if updated[query_id]["fields"].get(name) is None:
                updated[query_id]["fields"][name] = updated[donor_id]["fields"][name]
    return updated


def isolation_gate(contracts: dict[str, dict[str, Any]], groups: list[list[str]]) -> set[tuple[str, str]]:
    failed: set[tuple[str, str]] = set()
    for group_ids in groups:
        if len(group_ids) != 2:
            continue
        group = [contracts[query_id] for query_id in group_ids]
        synthetic = {}
        for contract in group:
            fields = {}
            for field in contract["fields"]:
                if field["type"] == "int":
                    fields[field["name"]] = 4 if contract is group[0] else 9
                elif field["domain"]:
                    fields[field["name"]] = field["domain"][0 if contract is group[0] else min(1, len(field["domain"]) - 1)]
                else:
                    fields[field["name"]] = "Alpha" if contract is group[0] else "Beta"
            synthetic[contract["query_id"]] = {"query_id": contract["query_id"], "fields": fields}
        forward = [synthetic[query_id] for query_id in group_ids]
        reverse = list(reversed(forward))

        def accept(blocks: list[dict[str, Any]]) -> dict[str, dict[str, Any]] | None:
            found = {}
            for contract in group:
                matched = next((block for block in blocks if block.get("query_id") == contract["query_id"]), None)
                if matched is None:
                    return None
                valid, error = validate_subresult(contract, matched)
                if error or valid is None:
                    return None
                found[contract["query_id"]] = valid
            return found

        left = accept(forward)
        right = accept(reverse)
        if left is None or right is None or canonical(left) != canonical(right):
            failed.add(tuple(sorted(group_ids)))
            continue
        shared = set(group[0]["names"]) & set(group[1]["names"])
        for name in shared:
            if left[group_ids[0]]["fields"][name] == left[group_ids[1]]["fields"][name] and synthetic[group_ids[0]]["fields"][name] != synthetic[group_ids[1]]["fields"][name]:
                failed.add(tuple(sorted(group_ids)))
        broken = {"query_id": group_ids[1], "fields": synthetic[group_ids[1]]["fields"]}
        kept, keep_error = validate_subresult(group[1], broken)
        if keep_error or kept is None:
            failed.add(tuple(sorted(group_ids)))
        malformed, malformed_error = validate_subresult(group[0], {"query_id": group_ids[0], "fields": {}})
        if malformed is not None or malformed_error is None:
            failed.add(tuple(sorted(group_ids)))
        missing = json.loads(canonical(forward))
        shared_name = next(iter(shared), None)
        if shared_name:
            for block in missing:
                if block["query_id"] == group_ids[1]:
                    block["fields"][shared_name] = None
            parsed = accept(missing)
            if parsed is None:
                failed.add(tuple(sorted(group_ids)))
                continue
            direct = apply_same_attribute(group, parsed, "fusion_direct")
            copied = apply_same_attribute(group, parsed, "fusion_same_attribute")
            if direct[group_ids[1]]["fields"][shared_name] is not None:
                failed.add(tuple(sorted(group_ids)))
            if copied[group_ids[1]]["fields"][shared_name] != parsed[group_ids[0]]["fields"][shared_name]:
                failed.add(tuple(sorted(group_ids)))
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE legal (doc_id TEXT, __entity_id TEXT, value_a TEXT, value_b TEXT)")
        connection.execute("INSERT INTO legal VALUES ('s.txt', 's', NULL, NULL)")
        first_field = group[0]["fields"][0]["name"]
        connection.execute("UPDATE legal SET value_a = ? WHERE doc_id = 's.txt'", (str(left[group_ids[0]]["fields"][first_field]),))
        singleton = connection.execute("SELECT value_a FROM legal").fetchone()[0]
        if singleton != str(left[group_ids[0]]["fields"][first_field]):
            failed.add(tuple(sorted(group_ids)))
        connection.close()
    return failed


def invoke(caller, ledger: TokenLedger, prompt: str, purpose: str, metadata: dict[str, Any]) -> tuple[str, int]:
    message, tokens = caller.client(prompt, {**metadata, "system": "Extract only facts stated in the document. Return JSON.", "model": MODEL})
    ledger.spend(tokens, purpose, **metadata)
    return message, tokens


def repair_prompt(contract: dict[str, Any], malformed: str, error: str) -> str:
    return (
        "Reformat only this query subresult. Do not add facts.\n"
        f"query_id: {contract['query_id']}\n"
        f"schema_error: {error}\n"
        f"required_fields: {contract['names']}\n"
        "Return JSON {\"query_id\":...,\"fields\":{...}} using null for missing values.\n"
        f"MALFORMED:\n{malformed[:4000]}"
    )


def build_plan() -> dict[str, Any]:
    queries = load_queries()
    descriptions = load_descriptions()
    documents = read_documents()
    if len(documents) != 570:
        raise SystemExit(f"run invalid: document count {len(documents)}")
    contracts = contracts_for(queries, descriptions)
    doc_tokens = [count_tokens(text) for _doc, text in documents]
    groups = partition(contracts, doc_tokens, set())
    failed = isolation_gate(contracts, groups)
    if failed:
        groups = partition(contracts, doc_tokens, failed)
        failed_again = isolation_gate(contracts, groups)
        if failed_again:
            groups = [[query_id] for query_id in sorted(contracts)]
    tasks = []
    for group_index, query_ids in enumerate(groups):
        group = [contracts[query_id] for query_id in query_ids]
        for doc_index, (doc, text) in enumerate(documents):
            route = route_group(text, group)
            if route["split"]:
                for part, contract in enumerate(group):
                    spans = route["spans"][part]
                    excerpt = pack_sections(text, spans)
                    prompt = render_prompt(excerpt, [contract])
                    if count_tokens(prompt) > INPUT_CAP:
                        excerpt = text[:4000]
                        prompt = render_prompt(excerpt, [contract])
                        spans = [[0, min(len(text), 4000)]]
                    tasks.append(
                        {
                            "index": len(tasks),
                            "group_index": group_index,
                            "doc_index": doc_index,
                            "doc": doc,
                            "query_ids": [contract["query_id"]],
                            "mode": "sections",
                            "spans": spans,
                            "reservation": count_tokens(prompt) + MAX_TOKENS,
                            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        }
                    )
            else:
                excerpt = text if route["mode"] == "whole_document" else pack_sections(text, [tuple(span) for span in route["spans"]])
                prompt = render_prompt(excerpt, group)
                tasks.append(
                    {
                        "index": len(tasks),
                        "group_index": group_index,
                        "doc_index": doc_index,
                        "doc": doc,
                        "query_ids": query_ids,
                        "mode": route["mode"],
                        "spans": route["spans"],
                        "reservation": count_tokens(prompt) + MAX_TOKENS,
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    }
                )
    group_cost = []
    for group_index, _query_ids in enumerate(groups):
        reserved = sum(task["reservation"] for task in tasks if task["group_index"] == group_index)
        repair_pool = int(0.10 * sum(1 for task in tasks if task["group_index"] == group_index) * (180 + MAX_TOKENS))
        group_cost.append({"group_index": group_index, "queries": groups[group_index], "reservation": reserved, "repair_pool": repair_pool})
    return {
        "queries": queries,
        "contracts": contracts,
        "documents": documents,
        "groups": groups,
        "tasks": tasks,
        "group_cost": group_cost,
        "blocked_pairs": [list(item) for item in sorted(failed)],
        "doc_tokens": doc_tokens,
    }


def predicates_for(queries: list[dict[str, Any]]):
    audit = audit_workload(queries)
    return live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))


def execute_query(database: Path, query: dict[str, Any], predicates) -> list[dict[str, Any]]:
    sql = official_sql(query["sql"], database, predicates, query_id=query["query_id"])
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        cursor = connection.execute(sql)
        columns = [item[0] for item in cursor.description] if cursor.description else []
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()


def materialize_query(query: dict[str, Any], contract: dict[str, Any], rows: dict[str, dict[str, Any]], target: Path) -> None:
    if target.exists():
        target.unlink()
    shutil.copy(PLUMBING, target)
    connection = sqlite3.connect(target)
    for doc, fields in rows.items():
        for field in contract["fields"]:
            if field["name"] not in fields:
                continue
            value = fields[field["name"]]
            if value is None:
                connection.execute(
                    f'UPDATE legal SET "{field["name"]}" = NULL WHERE doc_id = ?',
                    (doc,),
                )
            else:
                connection.execute(
                    f'UPDATE legal SET "{field["name"]}" = ? WHERE doc_id = ?',
                    (str(value), doc),
                )
    connection.commit()
    connection.close()


def rows_for(policy: str, contracts: dict[str, dict[str, Any]], journal: list[dict[str, Any]], group_limit: int | None) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in journal:
        if row.get("event") == "task":
            grouped[int(row["group_index"])].append(row)
    selected_groups = sorted(grouped)
    if group_limit is not None:
        selected_groups = [index for index in selected_groups if index < group_limit]
    collected: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for group_index in selected_groups:
        blocks = grouped[group_index]
        if not blocks:
            continue
        query_ids = blocks[0]["query_ids"] if len({tuple(block["query_ids"]) for block in blocks}) == 1 else None
        by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for block in blocks:
            by_doc[block["doc"]].extend(block.get("subresults") or [])
        for doc, subresults in by_doc.items():
            valid = {item["query_id"]: item for item in subresults if item.get("status") in {"valid", "repaired"} and item.get("fields") is not None}
            if not valid:
                continue
            group = [contracts[query_id] for query_id in valid]
            applied = apply_same_attribute(group, {query_id: {"query_id": query_id, "fields": item["fields"]} for query_id, item in valid.items()}, policy)
            for query_id, item in applied.items():
                collected[query_id][doc] = item["fields"]
        _ = query_ids
    return collected


def checkpoint_groups(journal: list[dict[str, Any]], limit: int) -> int:
    spent = 0
    completed = -1
    seen: dict[int, int] = {}
    expected: dict[int, int] = {}
    for row in journal:
        if row.get("event") == "plan":
            for group in row.get("groups") or []:
                expected[int(group["group_index"])] = int(group["tasks"])
        if row.get("event") != "task":
            continue
        spent += int(row.get("tokens") or 0) + int(row.get("repair_tokens") or 0)
        group_index = int(row["group_index"])
        seen[group_index] = seen.get(group_index, 0) + 1
        if seen[group_index] == expected.get(group_index) and spent <= limit:
            completed = group_index
        elif seen[group_index] == expected.get(group_index) and spent > limit:
            break
    return completed + 1


def score_policy(policy: str, contracts: dict[str, dict[str, Any]], queries: list[dict[str, Any]], journal: list[dict[str, Any]], predicates, folder: Path) -> dict[str, Any]:
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
    from quwarts.experiments.synthesize_case80 import gold_name, score_with_rewrites

    gold = load_ground_truth(gold_name("Legal"))
    rows = [{"query_id": query["query_id"], "sql": query["sql"], "pack": query["pack"]} for query in queries]
    limit = max((int(row["group_index"]) for row in journal if row.get("event") == "task"), default=-1) + 1
    extracted = rows_for(policy, contracts, journal, limit)
    rewrites = {}
    for query in queries:
        target = folder / policy / f"{query['query_id'].replace(':', '_')}.db"
        target.parent.mkdir(parents=True, exist_ok=True)
        materialize_query(query, contracts[query["query_id"]], extracted.get(query["query_id"], {}), target)
        rewrites[query["query_id"]] = {
            "sql": official_sql(query["sql"], target, predicates, query_id=query["query_id"]),
            "sqlite_path": str(target),
        }
    report = score_with_rewrites(rows, rewrites, PLUMBING, gold, "Legal")
    per_query = []
    for row in report.get("per_query") or []:
        per_query.append(
            {
                "query_id": row["query_id"],
                "structure_f2": row.get("structure_f2"),
                "cell_f1_20": row.get("cell_f1_20"),
                "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
                "pred_rows": row.get("pred_rows"),
            }
        )
    return {
        "policy": policy,
        "f2": float(report.get("mean_structure_f2") or 0.0),
        "f1": mean_cell_f1_20(report),
        "product": mean_per_query_product(report),
        "per_query": per_query,
        "empty_bags": sum(1 for row in per_query if int(row.get("pred_rows") or 0) == 0),
    }


def main() -> None:
    if (OUT / "frozen.json").exists() and os.environ.get("FUSION_FORCE") != "1":
        print(canonical({"status": "frozen", "out": str(OUT)}))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    plumbing_hash = file_sha(PLUMBING)
    plan = build_plan()
    contracts = plan["contracts"]
    documents = dict(plan["documents"])
    group_tasks = Counter(task["group_index"] for task in plan["tasks"])
    plan_record = {
        "groups": [
            {
                "group_index": item["group_index"],
                "queries": item["queries"],
                "reservation": item["reservation"],
                "repair_pool": item["repair_pool"],
                "tasks": group_tasks[item["group_index"]],
            }
            for item in plan["group_cost"]
        ],
        "blocked_pairs": plan["blocked_pairs"],
        "official_policy": OFFICIAL_POLICY,
        "tasks": plan["tasks"],
    }
    (OUT / "plan.json").write_text(canonical(plan_record))
    plan_hash = file_sha(OUT / "plan.json")
    (OUT / "plan.sha256").write_text(plan_hash + "\n")
    total_reservation = sum(item["reservation"] + item["repair_pool"] for item in plan["group_cost"])
    print(canonical({"status": "planned", "groups": plan_record["groups"], "tasks": len(plan["tasks"]), "reservation": total_reservation, "plan_sha256": plan_hash, "fits_theta75": total_reservation <= THETA["theta75"]}), flush=True)
    if os.environ.get("FUSION_STOP_BEFORE_CALLS") == "1":
        return
    load_env_file(PROJECT / ".env")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY is not set")
    journal_path = OUT / "journal.jsonl"
    if not journal_path.exists():
        append_jsonl(journal_path, {"event": "plan", "plan_sha256": plan_hash, "groups": plan_record["groups"], "official_policy": OFFICIAL_POLICY})
    done = {int(row["index"]) for row in _read_jsonl(journal_path) if row.get("event") == "task"}
    finished_groups = {int(row["group_index"]) for row in _read_jsonl(journal_path) if row.get("event") == "group_complete"}
    ledger = TokenLedger(theta=THETA["theta75"], seed=SEED)
    for row in _read_jsonl(journal_path):
        if row.get("event") == "task":
            ledger.spend(int(row.get("tokens") or 0) + int(row.get("repair_tokens") or 0), "replay", index=row["index"])
    caller = make_caller(ledger, model=MODEL, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
    predicates = predicates_for(plan["queries"])
    lock = threading.Lock()
    for group in plan["group_cost"]:
        if group["group_index"] in finished_groups:
            continue
        reservation = group["reservation"] + group["repair_pool"]
        if ledger.spent + reservation > THETA["theta75"]:
            print(canonical({"stopped_before_group": group["group_index"], "spent": ledger.spent, "reservation": reservation}), flush=True)
            break
        tasks = [task for task in plan["tasks"] if task["group_index"] == group["group_index"] and task["index"] not in done]
        pending: dict[int, dict[str, Any]] = {}
        order = sorted(task["index"] for task in tasks)
        cursor = {"at": 0}

        def commit(index: int, row: dict[str, Any]) -> None:
            with lock:
                pending[index] = row
                while cursor["at"] < len(order) and order[cursor["at"]] in pending:
                    append_jsonl(journal_path, pending.pop(order[cursor["at"]]))
                    cursor["at"] += 1

        def run_task(task: dict[str, Any]) -> None:
            text = documents[task["doc"]]
            spans = [tuple(span) for span in task["spans"]]
            excerpt = text if task["mode"] == "whole_document" else pack_sections(text, spans)
            group = [contracts[query_id] for query_id in task["query_ids"]]
            prompt = render_prompt(excerpt, group)
            if hashlib.sha256(prompt.encode()).hexdigest() != task["prompt_sha256"]:
                raise SystemExit(f"run invalid: prompt changed for {task['index']}")
            try:
                message, tokens = invoke(caller, ledger, prompt, "fused_map", {"index": task["index"], "doc": task["doc"], "queries": task["query_ids"]})
            except BudgetExhausted:
                commit(task["index"], {"event": "task", "index": task["index"], "group_index": task["group_index"], "doc": task["doc"], "query_ids": task["query_ids"], "mode": task["mode"], "tokens": 0, "repair_tokens": 0, "subresults": [], "status": "budget_held"})
                return
            blocks = parse_fused(message)
            subresults = []
            repair_tokens = 0
            for contract in group:
                matched = next((block for block in blocks if block.get("query_id") == contract["query_id"]), None)
                valid, error = validate_subresult(contract, matched) if matched else (None, "malformed output")
                status = "valid" if valid else "fallback"
                if valid is None and ledger.remaining() > 200:
                    try:
                        repaired, repair_cost = invoke(
                            caller,
                            ledger,
                            repair_prompt(contract, message, error or "malformed output"),
                            "format_repair",
                            {"index": task["index"], "query_id": contract["query_id"]},
                        )
                        repair_tokens += repair_cost
                        repaired_block = parse_fused(repaired)
                        candidate = next((block for block in repaired_block if block.get("query_id") == contract["query_id"]), repaired_block[0] if len(repaired_block) == 1 else None)
                        valid, second = validate_subresult(contract, candidate)
                        if valid:
                            status = "repaired"
                            error = None
                        else:
                            error = second or error
                    except BudgetExhausted:
                        valid = None
                subresults.append(
                    {
                        "query_id": contract["query_id"],
                        "status": status if valid else "fallback",
                        "error": error,
                        "fields": None if valid is None else valid["fields"],
                    }
                )
            commit(
                task["index"],
                {
                    "event": "task",
                    "index": task["index"],
                    "group_index": task["group_index"],
                    "doc": task["doc"],
                    "query_ids": task["query_ids"],
                    "mode": task["mode"],
                    "tokens": tokens,
                    "repair_tokens": repair_tokens,
                    "subresults": subresults,
                },
            )

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(run_task, task) for task in tasks]
            for future in as_completed(futures):
                future.result()
        append_jsonl(journal_path, {"event": "group_complete", "group_index": group["group_index"], "queries": group["queries"], "spent": ledger.spent})
        print(canonical({"group_complete": group["group_index"], "queries": group["queries"], "spent": ledger.spent}), flush=True)
    (OUT / "ledger.json").write_text(canonical(ledger.snapshot()))
    journal = _read_jsonl(journal_path)
    if file_sha(PLUMBING) != plumbing_hash:
        raise SystemExit("run invalid: plumbing database changed")
    prefixes = {}
    raw = journal_path.read_bytes()
    lines = raw.splitlines(keepends=True)
    for name, limit in THETA.items():
        count = checkpoint_groups(journal, limit)
        kept_end = 0
        seen_complete = -1
        for line in lines:
            payload = json.loads(line)
            kept_end += len(line)
            if payload.get("event") == "group_complete":
                seen_complete = int(payload["group_index"])
            if seen_complete == count - 1 and payload.get("event") == "group_complete":
                break
        prefix = raw[:kept_end] if count else b"".join(line for line in lines if json.loads(line).get("event") == "plan")
        if count and not raw.startswith(prefix):
            raise SystemExit(f"run invalid: {name} journal is not an exact prefix")
        folder = OUT / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "journal.jsonl").write_bytes(prefix)
        prefixes[name] = {"groups": count, "bytes": len(prefix), "journal_sha256": hashlib.sha256(prefix).hexdigest()}
        print(canonical({"checkpoint": name, **prefixes[name]}), flush=True)
    _freeze_checkpoints(plan, journal, predicates, prefixes, plumbing_hash)
    print(canonical({"status": "complete", "out": str(OUT)}), flush=True)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _freeze_checkpoints(plan: dict[str, Any], journal: list[dict[str, Any]], predicates, prefixes: dict[str, dict[str, Any]], plumbing_hash: str) -> None:
    contracts = plan["contracts"]
    queries = plan["queries"]
    plumbing_connection = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    identity = identity_checksum(plumbing_connection)
    plumbing_connection.close()
    checkpoints = []
    for name, limit in THETA.items():
        count = checkpoint_groups(journal, limit)
        folder = OUT / name
        extracted = rows_for(OFFICIAL_POLICY, contracts, [row for row in journal if row.get("event") != "task" or int(row["group_index"]) < count], count)
        bags = {}
        failures = []
        databases = {}
        for query in queries:
            target = folder / "databases" / f"{query['query_id'].replace(':', '_')}.db"
            target.parent.mkdir(parents=True, exist_ok=True)
            materialize_query(query, contracts[query["query_id"]], extracted.get(query["query_id"], {}), target)
            connection = sqlite3.connect(target)
            if identity_checksum(connection) != identity:
                raise SystemExit("run invalid: entity identity changed")
            connection.close()
            try:
                bags[query["query_id"]] = execute_query(target, query, predicates)
            except sqlite3.Error as exc:
                failures.append({"query_id": query["query_id"], "error": str(exc)})
                bags[query["query_id"]] = []
            databases[query["query_id"]] = file_sha(target)
        (folder / "bags.json").write_text(json.dumps(bags, ensure_ascii=False, sort_keys=True))
        selected = [row for row in journal if row.get("event") == "task" and int(row["group_index"]) < count]
        tokens = sum(int(row.get("tokens") or 0) + int(row.get("repair_tokens") or 0) for row in selected)
        if tokens > limit:
            raise SystemExit(f"run invalid: {name} ledger {tokens}")
        payload = {
            "checkpoint": name,
            "groups_completed": count,
            "queries_completed": sorted({query_id for group in plan["groups"][:count] for query_id in group}),
            "calls": len(selected),
            "prompt_tokens": sum(int(row.get("tokens") or 0) for row in selected),
            "repair_tokens": sum(int(row.get("repair_tokens") or 0) for row in selected),
            "tokens": tokens,
            "modes": dict(Counter(row.get("mode") for row in selected)),
            "statuses": dict(Counter(item.get("status") for row in selected for item in row.get("subresults") or [])),
            "errors": dict(Counter(item.get("error") for row in selected for item in row.get("subresults") or [] if item.get("error"))),
            "empty_bags": sum(1 for rows in bags.values() if len(rows) == 0),
            "execution_failures": failures,
            "bag_sha256": bag_hash(bags),
            "database_sha256": databases,
            "journal_sha256": prefixes[name]["journal_sha256"],
            "unused_budget": limit - tokens,
        }
        (folder / "checkpoint.json").write_text(canonical(payload))
        checkpoints.append(payload)
    (OUT / "checkpoints.json").write_text(canonical(checkpoints))
    theta75 = checkpoints[-1]
    if file_sha(PLUMBING) != plumbing_hash:
        raise SystemExit("run invalid: plumbing database changed")
    if len(theta75["execution_failures"]) and len(theta75["queries_completed"]) != 16:
        raise SystemExit("run invalid: official SQL failed")
    _FROZEN["ok"] = True
    official = score_policy(OFFICIAL_POLICY, contracts, queries, [row for row in journal if row.get("event") != "task" or int(row["group_index"]) < checkpoint_groups(journal, THETA["theta75"])], predicates, OUT / "ablation")
    direct = score_policy("fusion_direct", contracts, queries, [row for row in journal if row.get("event") != "task" or int(row["group_index"]) < checkpoint_groups(journal, THETA["theta75"])], predicates, OUT / "ablation")
    product = official["product"]
    if product > DOCETL_PRODUCT:
        decision = "fused query maps beat Legal DocETL"
    elif product > PLUMBING_PRODUCT:
        decision = "fused query maps improve Legal but remain below DocETL"
    else:
        decision = "fusion saves tokens but reduces semantic quality"
    report = {
        "decision": decision,
        "official": official,
        "fusion_direct": direct,
        "docetl_product": DOCETL_PRODUCT,
        "docetl_tokens": DOCETL_TOKENS,
        "wcci_product": WCCI_PRODUCT,
        "plumbing_product": PLUMBING_PRODUCT,
        "token_fraction_of_docetl": theta75["tokens"] / DOCETL_TOKENS,
        "checkpoints": checkpoints,
    }
    (OUT / "scores.json").write_text(canonical(report))
    (OUT / "REPORT.md").write_text(
        "\n".join(
            [
                "# Fused query maps",
                "",
                f"Decision: `{decision}`",
                "",
                f"θ75 product {product}",
                f"θ75 F2 {official['f2']}",
                f"θ75 cell F1@0.20 {official['f1']}",
                f"θ75 tokens {theta75['tokens']}",
                f"DocETL product {DOCETL_PRODUCT}",
                f"DocETL tokens {DOCETL_TOKENS}",
                f"WCCI product {WCCI_PRODUCT}",
                f"Plumbing product {PLUMBING_PRODUCT}",
                f"fusion_direct product {direct['product']}",
                f"fusion_same_attribute product {official['product']}",
                "",
            ]
        )
    )
    (OUT / "frozen.json").write_text(canonical({"gold_loaded": True, "decision": decision, "plan_sha256": file_sha(OUT / "plan.json")}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise

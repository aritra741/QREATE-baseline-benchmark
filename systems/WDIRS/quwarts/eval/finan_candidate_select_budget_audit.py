"""Zero-Qwen θ25 budget audit of the frozen Finan candidate-selection arm."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
DOCETL_SRC = ROOT / "systems" / "docetl-main"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DOCETL_SRC) not in sys.path:
    sys.path.insert(0, str(DOCETL_SRC))

from sqlglot import exp

from quwarts.core.candidate_select.candidates import Candidate
from quwarts.core.candidate_select.config import COMPLETION_RESERVATION
from quwarts.core.candidate_select.construct import construct_classification, construct_extractive
from quwarts.core.candidate_select.prompt import (
    CLASSIFY_SCHEMA,
    EXTRACTIVE_SCHEMA,
    assemble,
    document_metadata,
)
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog, specs_hash
from quwarts.core.docetl_exact_message.adapter import DOCETL_MODEL, DOCETL_SYSTEM, tools_for_schema
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.shared_bundle.inventory import _roles_for, compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates, resolve_attribute, select_aliases, table_aliases
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import _default_entity, parse_sql
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

FROZEN = ROOT / "results" / "quwarts_finan_candidate_select"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
SCHEMA_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
OUT = ROOT / "results" / "finan_candidate_select_budget_audit"
THETA_25 = 345_457
THETA_100 = 1_381_827
DOCETL_PRODUCT = 0.084
TARGET_PRODUCT = 0.084
BATCH_SIZES = (1, 2, 3, 4, 6, 8)
DEPEND_ROLES = {"WHERE", "JOIN", "CASE", "GROUP BY", "HAVING", "aggregate input"}
DEFAULT_PLACEHOLDERS = {"", "unknown", "unspecified", "none", "null"}
ABSENT_FIELDS = ("normalized", "end", "neighbors", "local_text", "in_c1", "score", "kind")


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _null(value: Any) -> bool:
    return value is None or value == "" or value == -1 or value == "-1"


def pctile(values: list[int | float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = min(len(ordered) - 1, max(0, int(math.ceil(p * len(ordered)) - 1)))
    return float(ordered[idx])


def summarize(values: list[int | float]) -> dict[str, float | int]:
    data = [float(v) for v in values]
    if not data:
        return {"n": 0, "mean": 0.0, "median": 0.0, "p90": 0.0, "total": 0.0}
    return {
        "n": len(data),
        "mean": sum(data) / len(data),
        "median": pctile(data, 0.5),
        "p90": pctile(data, 0.9),
        "total": sum(data),
    }


def mapping_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    mapping = {}
    for row in rows:
        stem = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        mapping[stem] = str(row.get("doc_id") or f"{stem}.txt")
    return mapping


def load_plumbing_rows() -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finance)")]
    rows = [dict(zip(cols, rec)) for rec in conn.execute("SELECT * FROM finance")]
    conn.close()
    return rows


def cand_from_dict(item: dict[str, Any]) -> Candidate:
    return Candidate(
        opaque_id=str(item.get("id") or item.get("opaque_id") or ""),
        raw_span=str(item.get("raw_span") or ""),
        normalized=item.get("normalized"),
        row_label=str(item.get("row_label") or ""),
        column_header=str(item.get("column_header") or ""),
        table_title=str(item.get("table_title") or ""),
        heading=str(item.get("heading") or ""),
        period=item.get("period"),
        unit=item.get("unit"),
        currency=item.get("currency"),
        start=int(item.get("start") or 0),
        end=int(item.get("end") or 0),
        neighbors=str(item.get("neighbors") or ""),
        local_text=str(item.get("local_text") or ""),
        in_c1=bool(item.get("in_c1")),
        score=float(item.get("score") or 0.0),
        kind=str(item.get("kind") or ""),
    )


def compact_title(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    title = str(item.get("table_title") or "").strip()
    heading = str(item.get("heading") or "").strip()
    extra: dict[str, Any] = {}
    if title and heading and title != heading:
        extra["heading_kept_in_title"] = heading
        return f"{heading}//{title}", extra
    if title:
        if heading and heading == title:
            extra["heading_redundant_with_title"] = True
        return title, extra
    return heading, extra


def compact_card(item: dict[str, Any]) -> dict[str, Any]:
    cid = str(item.get("id") or item.get("opaque_id") or "")
    raw = str(item.get("raw_span") or "").strip()
    row = str(item.get("row_label") or "").strip()
    header = str(item.get("column_header") or "").strip()
    title, title_extra = compact_title(item)
    period = str(item.get("period") or "").strip()
    unit = str(item.get("unit") or "").strip()
    currency = str(item.get("currency") or "").strip()
    offset = item.get("start")
    dropped: dict[str, Any] = {}
    retained = {
        "candidate_id": cid,
        "raw_candidate_value": raw,
        "row_label": row,
        "column_header": header,
        "table_section_title": title,
        "period": period,
        "unit_or_multiplier": unit,
        "currency": currency,
        "source_offset_id": offset,
    }

    def drop_default(field: str, value: str, key: str) -> str:
        if value.lower() in DEFAULT_PLACEHOLDERS:
            dropped[field] = {"value": value, "reason": "default_placeholder_equals_omission"}
            retained[key] = ""
            return ""
        return value

    row = drop_default("row_label", row, "row_label")
    header = drop_default("column_header", header, "column_header")
    title = drop_default("table_section_title", title, "table_section_title")
    period = drop_default("period", period, "period")
    unit = drop_default("unit_or_multiplier", unit, "unit_or_multiplier")
    currency = drop_default("currency", currency, "currency")

    if header and title and header == title:
        dropped["column_header"] = {"value": header, "reason": "equal_to_table_section_title"}
        retained["column_header"] = ""
        header = ""
    if row and title and row == title:
        dropped["row_label"] = {"value": row, "reason": "equal_to_table_section_title"}
        retained["row_label"] = ""
        row = ""
    if header and row and header == row:
        dropped["column_header"] = {"value": header, "reason": "equal_to_row_label"}
        retained["column_header"] = ""
        header = ""

    retained_blob = " ".join(
        str(part) for part in (raw, row, header, title, period, unit, currency, offset) if part not in (None, "")
    ).lower()
    neighbors = str(item.get("neighbors") or "").strip()
    residual = ""
    if not neighbors:
        dropped["neighbors"] = {"value": "", "reason": "absent"}
    elif neighbors.lower() in retained_blob:
        dropped["neighbors"] = {"value": neighbors, "reason": "substring_of_retained_fields"}
    else:
        residual = neighbors
        retained["residual_neighbor_text"] = residual

    end = item.get("end")
    if end in (None, "", 0):
        dropped["end"] = {"value": end, "reason": "absent"}
    elif raw and int(end) == int(offset or 0) + len(item.get("raw_span") or ""):
        dropped["end"] = {"value": end, "reason": "equal_to_start_plus_raw_span_length"}
    else:
        retained["residual_end"] = end

    if item.get("normalized") not in (None, "", raw):
        dropped["normalized"] = {"value": item.get("normalized"), "reason": "derived_from_raw_span_not_a_card_field"}
    else:
        dropped["normalized"] = {"value": item.get("normalized"), "reason": "equal_to_raw_or_absent"}
    dropped["in_c1"] = {"value": item.get("in_c1"), "reason": "ranking_metadata_not_candidate_content"}
    dropped["score"] = {"value": item.get("score"), "reason": "ranking_metadata_not_candidate_content"}
    dropped["kind"] = {"value": item.get("kind"), "reason": "ranking_metadata_not_candidate_content"}
    if not item.get("local_text"):
        dropped["local_text"] = {"value": "", "reason": "absent"}

    parts = [cid]
    if raw:
        parts.append(f"v={raw}")
    if retained["row_label"]:
        parts.append(f"r={retained['row_label']}")
    if retained["column_header"]:
        parts.append(f"h={retained['column_header']}")
    if retained["table_section_title"]:
        parts.append(f"t={retained['table_section_title']}")
    if retained["period"]:
        parts.append(f"p={retained['period']}")
    if retained["unit_or_multiplier"]:
        parts.append(f"u={retained['unit_or_multiplier']}")
    if retained["currency"]:
        parts.append(f"c={retained['currency']}")
    if offset not in (None, ""):
        parts.append(f"off={offset}")
    if residual:
        parts.append(f"nb={residual}")
    if retained.get("residual_end") not in (None, ""):
        parts.append(f"end={retained['residual_end']}")
    lossless = "residual_neighbor_text" not in retained and "residual_end" not in retained
    return {
        "line": "|".join(parts),
        "retained": retained,
        "dropped": dropped,
        "title_extra": title_extra,
        "lossless": lossless,
        "residual_neighbor_text": residual or None,
    }


def compact_card_lines(candidates: list[dict[str, Any]], task_id: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    reports = []
    lines = []
    for item in candidates:
        card = compact_card(item)
        cid = str(item.get("id") or "")
        if task_id:
            card["line"] = card["line"].replace(cid, f"{task_id}.{cid}", 1) if card["line"].startswith(cid) else f"{task_id}.{card['line']}"
        reports.append(card)
        lines.append(card["line"])
    return "\n".join(lines) if lines else "(no grounded candidates)", reports


def extract_metadata(user: str) -> str:
    marker = "Document metadata: "
    if marker not in user:
        return ""
    rest = user.split(marker, 1)[1]
    for stop in ("\n\nCandidates:\n", "\n\nEvidence cards:\n"):
        if stop in rest:
            return rest.split(stop, 1)[0]
    return rest


def parse_original_components(user: str, spec_name: str, description: str, candidates: list[dict[str, Any]]) -> dict[str, str]:
    metadata = extract_metadata(user)
    desc = description or ""
    if "Official description: " in user:
        after = user.split("Official description: ", 1)[1]
        desc = after.split("\n", 1)[0]
    instructions = user
    if metadata:
        instructions = instructions.replace(f"Document metadata: {metadata}", "Document metadata:")
    if desc:
        instructions = instructions.replace(f"Official description: {desc}", "Official description:")
    marker = "\n\nCandidates:\n" if "\n\nCandidates:\n" in user else "\n\nEvidence cards:\n"
    cards = user.split(marker, 1)[1] if marker in user else ""
    if marker in instructions:
        instructions = instructions.split(marker, 1)[0] + marker
    return {
        "instructions": instructions,
        "description": desc,
        "metadata": metadata,
        "cards": cards,
        "attribute": spec_name,
    }


def field_join(candidates: list[dict[str, Any]], *keys: str) -> str:
    parts = []
    for item in candidates:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                parts.append(str(value))
    return "\n".join(parts)


def batch_tools() -> list[dict[str, Any]]:
    parameters = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "candidate_ids": {"type": "array", "items": {"type": "string"}},
                        "operation": {"type": "string"},
                        "status": {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "required": ["task_id", "candidate_ids", "operation", "status"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    }
    return [
        {
            "type": "function",
            "additionalProperties": False,
            "strict": True,
            "function": {
                "name": "send_output",
                "description": "Send output back to the user",
                "parameters": parameters,
            },
        }
    ]


BATCH_INSTRUCTION = (
    "Select grounded candidate IDs for each task. Do not emit a value.\n"
    "Each task has a unique task_id, its own official description, and a namespaced candidate-ID set.\n"
    "Return one independent result per task_id with selected candidate IDs, operation, and status.\n"
    "Classification tasks may also return an official-domain label. Never emit a free-form extractive value.\n"
)


def task_id_for(entity_id: str, attribute: str) -> str:
    raw = f"{entity_id}:{attribute}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:10]
    return f"T{digest}"


def compact_one_cell_user(task: dict[str, Any], spec: Any, metadata: str) -> str:
    cards, _ = compact_card_lines(task["candidates"])
    if spec.task_class == "classification":
        labels = ", ".join(spec.schema_domain)
        return (
            "Classify one attribute using the official label space and grounded evidence cards.\n"
            "Do not invent a label outside the official domain. Do not emit a free-form extractive value.\n"
            f"Attribute: {spec.name}\n"
            f"Official description: {spec.official_description}\n"
            f"Official labels: {labels}\n"
            f"Document metadata: {metadata}\n\n"
            f"Evidence cards:\n{cards}"
        )
    ops = "identity, sum, none" if spec.allows_sum else "identity, none"
    return (
        "Select grounded candidate IDs for one attribute. Do not emit a value.\n"
        f"Attribute: {spec.name}\n"
        f"Official description: {spec.official_description}\n"
        f"Requested type: {spec.dtype} ({spec.sql_type})\n"
        f"Allowed operations: {ops}\n"
        "Return status selected with one or more candidate_ids, or status abstain with operation none.\n"
        "Use sum only if the official description requires aggregating segments.\n"
        f"Document metadata: {metadata}\n\n"
        f"Candidates:\n{cards}"
    )


def prompt_token_count(system: str, user: str, tools: list[dict[str, Any]]) -> int:
    return count_tokens(system + user) + count_tokens(json.dumps(tools, default=str))


def build_batch_prompt(tasks: list[dict[str, Any]], specs: dict[str, Any], metadata: str) -> dict[str, Any]:
    if not tasks:
        raise ValueError("empty batch")
    docs = {task["document_id"] for task in tasks}
    ents = {task["entity_id"] for task in tasks}
    if len(docs) != 1 or len(ents) != 1:
        raise ValueError("batch mixes entities or documents")
    seen_tid: set[str] = set()
    seen_cid: set[str] = set()
    blocks = []
    for task in tasks:
        spec = specs[task["attribute"]]
        tid = task["task_id"]
        if tid in seen_tid:
            raise ValueError(f"task id collision {tid}")
        seen_tid.add(tid)
        namespaced = []
        cards, _ = compact_card_lines(task["candidates"], task_id=tid)
        for item in task["candidates"]:
            cid = f"{tid}.{item['id']}"
            if cid in seen_cid:
                raise ValueError(f"candidate id collision {cid}")
            seen_cid.add(cid)
            namespaced.append(cid)
        if spec.task_class == "classification":
            labels = ", ".join(spec.schema_domain)
            head = (
                f"### Task {tid}\n"
                f"Attribute: {spec.name}\n"
                f"Official description: {spec.official_description}\n"
                f"Official labels: {labels}\n"
                f"Task class: classification\n"
                f"Namespaced candidate IDs: {', '.join(namespaced)}\n"
                f"Evidence cards:\n{cards}"
            )
        else:
            ops = "identity, sum, none" if spec.allows_sum else "identity, none"
            head = (
                f"### Task {tid}\n"
                f"Attribute: {spec.name}\n"
                f"Official description: {spec.official_description}\n"
                f"Requested type: {spec.dtype} ({spec.sql_type})\n"
                f"Allowed operations: {ops}\n"
                f"Task class: extractive\n"
                f"Namespaced candidate IDs: {', '.join(namespaced)}\n"
                f"Candidates:\n{cards}"
            )
        blocks.append(head)
    user = (
        BATCH_INSTRUCTION
        + f"Document metadata: {metadata}\n\n"
        + "\n\n".join(blocks)
    )
    tools = batch_tools()
    if "value" in json.dumps(tools).lower().split("send_output")[-1] and '"value"' in json.dumps(tools):
        raise ValueError("batch schema allows a value field")
    prompt_tokens = prompt_token_count(DOCETL_SYSTEM, user, tools)
    return {
        "entity_id": tasks[0]["entity_id"],
        "document_id": tasks[0]["document_id"],
        "task_ids": [task["task_id"] for task in tasks],
        "attributes": [task["attribute"] for task in tasks],
        "n_cells": len(tasks),
        "user": user,
        "tools": tools,
        "prompt_tokens": prompt_tokens,
        "namespaced_candidate_ids": sorted(seen_cid),
    }


def query_attr_roles(statements: dict[str, str]) -> dict[str, dict[str, set[str]]]:
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for query_id, sql in statements.items():
        tree = parse_sql(sql)
        aliases = table_aliases(tree)
        default = _default_entity(tree)
        skip = select_aliases(tree)
        for column in tree.find_all(exp.Column):
            resolved = resolve_attribute(column, aliases, default)
            if resolved is None:
                continue
            name = resolved[2]
            if name in skip or name == "rowid":
                continue
            for role, _expr in _roles_for(column):
                out[query_id][name].add(role)
    return out


def try_cpsat() -> bool:
    try:
        from ortools.sat.python import cp_model  # noqa: F401

        return True
    except Exception:
        return False


class WorkloadGraph:
    def __init__(
        self,
        tasks: list[dict[str, Any]],
        empty_cells: list[dict[str, Any]],
        plumbing_filled: dict[tuple[str, str], Any],
        roles: dict[str, dict[str, set[str]]],
        query_ids: list[str],
        entities: list[str],
    ) -> None:
        self.tasks = {task["key"]: task for task in tasks}
        self.empty = {(row["entity_id"], row["attribute"]) for row in empty_cells}
        self.plumbing_filled = plumbing_filled
        self.roles = roles
        self.query_ids = query_ids
        self.entities = entities
        self.required: dict[str, list[str]] = {}
        for qid in query_ids:
            attrs = sorted(
                name for name, role_set in roles.get(qid, {}).items() if role_set & DEPEND_ROLES
            )
            self.required[qid] = attrs
        self.witnesses: list[dict[str, Any]] = []
        self.by_witness: dict[tuple[str, str], dict[str, Any]] = {}
        self.n_candidate: dict[str, int] = {}
        self.by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for qid in query_ids:
            count = 0
            for entity in entities:
                needed = []
                unavailable = False
                free = []
                for attr in self.required[qid]:
                    key = (entity, attr)
                    if key in plumbing_filled:
                        free.append(attr)
                        continue
                    if key in self.empty:
                        unavailable = True
                        continue
                    task_key = f"{entity}::{attr}"
                    if task_key not in self.tasks:
                        unavailable = True
                        continue
                    needed.append(attr)
                feasible = not unavailable
                already = feasible and not needed
                if feasible:
                    count += 1
                rec = {
                    "query_id": qid,
                    "entity_id": entity,
                    "needed": needed,
                    "free": free,
                    "unavailable": unavailable,
                    "feasible": feasible,
                    "already_complete": already,
                }
                self.witnesses.append(rec)
                self.by_witness[(qid, entity)] = rec
                self.by_entity[entity].append(rec)
            self.n_candidate[qid] = count

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_tasks": len(self.tasks),
            "n_empty_unavailable": len(self.empty),
            "n_witnesses": len(self.witnesses),
            "n_feasible_witnesses": sum(1 for row in self.witnesses if row["feasible"]),
            "n_already_complete": sum(1 for row in self.witnesses if row["already_complete"]),
            "required_by_query": self.required,
            "candidate_witnesses_by_query": self.n_candidate,
            "empty_cells": sorted(list(self.empty)),
        }

    def completed(self, scheduled: set[str]) -> list[tuple[str, str]]:
        done = []
        for row in self.witnesses:
            if not row["feasible"]:
                continue
            if row["already_complete"] or all(f"{row['entity_id']}::{attr}" in scheduled for attr in row["needed"]):
                done.append((row["query_id"], row["entity_id"]))
        return done

    def objective(self, scheduled: set[str]) -> float:
        done = set(self.completed(scheduled))
        total = 0.0
        for qid in self.query_ids:
            n = self.n_candidate.get(qid) or 0
            if n <= 0:
                continue
            hits = sum(1 for entity in self.entities if (qid, entity) in done)
            total += hits / n
        return total


def reserved_for(prompt_tokens: int, n_cells: int, mean_completion: float) -> int:
    return int(prompt_tokens + max(COMPLETION_RESERVATION, int(round(n_cells * mean_completion))))


def pack_groups(tasks: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    by_ent: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        by_ent[(task["entity_id"], task["document_id"])].append(task)
    groups = []
    for key in sorted(by_ent):
        items = sorted(by_ent[key], key=lambda row: (row["attribute"], row["task_id"]))
        for idx in range(0, len(items), batch_size):
            groups.append(items[idx : idx + batch_size])
    return groups


def greedy_schedule(
    graph: WorkloadGraph,
    cost_of: Any,
    budget: int,
) -> dict[str, Any]:
    scheduled: set[str] = set()
    packages: list[dict[str, Any]] = []
    spent = 0
    while True:
        best = None
        for entity, rows in graph.by_entity.items():
            open_rows = []
            for row in rows:
                if not row["feasible"] or row["already_complete"]:
                    continue
                need = [attr for attr in row["needed"] if f"{entity}::{attr}" not in scheduled]
                if need:
                    open_rows.append((row, need))
            for row, need in open_rows:
                keys = [f"{entity}::{attr}" for attr in need]
                try:
                    extra = cost_of(scheduled, keys)
                except ValueError:
                    continue
                if extra <= 0 or spent + extra > budget:
                    continue
                added = set(keys)
                newly = []
                for other, remain in open_rows:
                    if all(f"{entity}::{attr}" in added or f"{entity}::{attr}" in scheduled for attr in remain):
                        if any(f"{entity}::{attr}" in added for attr in remain):
                            n = graph.n_candidate[other["query_id"]]
                            newly.append((other["query_id"], entity, 1.0 / n if n else 0.0))
                gain = sum(item[2] for item in newly)
                if gain <= 0:
                    continue
                cand = (
                    -gain / extra,
                    row["query_id"],
                    entity,
                    tuple(need),
                    extra,
                    newly,
                    keys,
                )
                if best is None or cand < best:
                    best = cand
        if best is None:
            break
        _eff, qid, entity, need, extra, newly, keys = best
        scheduled.update(keys)
        spent += extra
        packages.append(
            {
                "query_id": qid,
                "entity_id": entity,
                "attributes": list(need),
                "task_keys": keys,
                "reserved_delta": extra,
                "unlocked": [{"query_id": a, "entity_id": b} for a, b, _ in newly],
            }
        )
    leftover = []
    for key, task in sorted(graph.tasks.items()):
        if key in scheduled:
            continue
        try:
            extra = cost_of(scheduled, [key])
        except ValueError:
            continue
        if spent + extra <= budget:
            scheduled.add(key)
            spent += extra
            leftover.append(key)
    return {
        "solver": "deterministic_witness_package_greedy",
        "cpsat": False,
        "scheduled_keys": sorted(scheduled),
        "packages": packages,
        "leftover_fillers": leftover,
        "reserved": spent,
        "objective": graph.objective(scheduled),
        "completed_witnesses": [{"query_id": q, "entity_id": e} for q, e in graph.completed(scheduled)],
    }


def materialize(
    dest: Path,
    fills: dict[str, dict[str, Any]],
    mapping: dict[str, str],
    statements: dict[str, str],
    predicates,
    query_ids: list[str],
) -> dict[str, Any]:
    copy_plumbing(PLUMBING, dest)
    overlay = apply_overlay(dest, fills, mapping)
    bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    return {"overlay": overlay, "bags": bags, "bag_sha256": _hash(bags), "db_sha256": file_sha256(dest)}


def score_db(dest: Path, statements: dict[str, str], predicates, query_ids: list[str], gold) -> dict[str, Any]:
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    rewrites = {qid: {"sql": official_sql(statements[qid], dest, predicates, query_id=qid), "sqlite_path": str(dest)} for qid in query_ids}
    report = score_with_rewrites(score_rows, rewrites, dest, gold, "Finan")
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
    report15 = score_with_rewrites(count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, dest, gold, "Finan")
    return {
        "score_16": {
            "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
            "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
            "mean_per_query_product": mean_per_query_product(report),
            "per_query": [
                {
                    "query_id": row["query_id"],
                    "structure_f2": row.get("structure_f2"),
                    "cell_f1_20": row.get("cell_f1_20"),
                    "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
                }
                for row in report.get("per_query") or []
            ],
        },
        "score_15": {
            "mean_structure_f2": float(report15.get("mean_structure_f2") or 0.0),
            "mean_cell_f1_at_0.20": mean_cell_f1_20(report15),
            "mean_per_query_product": mean_per_query_product(report15),
        },
    }


def fills_from_keys(
    keys: list[str],
    tasks_by_key: dict[str, dict[str, Any]],
    journal_by_key: dict[str, dict[str, Any]],
    use_accepted: bool = True,
    gold_values: dict[tuple[str, str], Any] | None = None,
    gold_match_fn=None,
) -> dict[str, dict[str, Any]]:
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for key in keys:
        task = tasks_by_key[key]
        row = journal_by_key.get(key)
        value = None
        if gold_values is not None and gold_match_fn is not None:
            gold_v = gold_values.get((task["document_id"], task["attribute"]))
            chosen = None
            for item in task["candidates"]:
                if gold_match_fn(task["attribute"], item.get("normalized"), gold_v) or gold_match_fn(
                    task["attribute"], item.get("raw_span"), gold_v
                ):
                    chosen = item
                    break
            if chosen is not None:
                if task["task_class"] == "classification":
                    value = gold_v
                else:
                    built = construct_extractive(
                        spec=task["spec"],
                        candidates=task["candidate_objs"],
                        candidate_ids=[chosen["id"]],
                        operation="identity",
                        status="selected",
                    )
                    value = built.get("value")
        elif use_accepted and row is not None and not _null(row.get("accepted")):
            value = row.get("accepted")
        if not _null(value):
            fills[task["document_id"]][task["attribute"]] = value
    return dict(fills)


def write_report(path: Path, text: str) -> None:
    path.write_text(text)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frozen_arm = json.loads((FROZEN / "finan_candidate_select_arm.json").read_text())
    frozen_meta = json.loads((FROZEN / "frozen.json").read_text())
    journal = json.loads((FROZEN / "theta100_journal.json").read_text())
    journal25 = json.loads((FROZEN / "theta25_journal.json").read_text())
    fills100 = json.loads((FROZEN / "theta100_fills.json").read_text())
    fills25 = json.loads((FROZEN / "theta25_fills.json").read_text())
    bags100 = json.loads((FROZEN / "theta100_bags.json").read_text())
    bags25 = json.loads((FROZEN / "theta25_bags.json").read_text())
    frozen25 = json.loads((FROZEN / "theta25_frozen.json").read_text())
    frozen100 = json.loads((FROZEN / "theta100_frozen.json").read_text())
    inventory = json.loads((FROZEN / "candidate_inventory.json").read_text())
    schedules_frozen = json.loads((FROZEN / "schedules.json").read_text())
    prompts: list[dict[str, Any]] = []
    with (FROZEN / "rendered_prompts.jsonl").open() as handle:
        for line in handle:
            prompts.append(json.loads(line))

    mismatches: list[str] = []
    if file_sha256(FROZEN / "rendered_prompts.jsonl") != frozen_meta["hashes"]["rendered_prompts"]:
        mismatches.append("rendered_prompts hash")
    if file_sha256(PLUMBING) != frozen_meta["hashes"]["plumbing"]:
        mismatches.append("plumbing hash")
    if file_sha256(SCHEMA_PATH) != frozen_meta["hashes"]["official_schema"]:
        mismatches.append("official schema hash")
    if _hash(inventory) != frozen_meta["hashes"]["inventory"]:
        mismatches.append("inventory hash")
    if len(journal) != 1174:
        mismatches.append(f"journal calls {len(journal)}")
    if len(prompts) != 1174:
        mismatches.append(f"rendered prompts {len(prompts)}")
    if frozen_meta.get("calls") != 1174 or frozen_arm.get("cells_attempted") != 1174:
        mismatches.append("attempted cells")
    if frozen_meta.get("accepted") != 517 or frozen_arm.get("accepted_cells") != 517:
        mismatches.append("accepted cells")
    if sum(len(v) for v in fills100.values()) != 517:
        mismatches.append("theta100 fills")
    if frozen100["overlay"]["changed_cells"] != 517:
        mismatches.append("theta100 overlay")
    if int(frozen25["spent"]) != 344601:
        mismatches.append(f"theta25 spend {frozen25['spent']}")
    if int(frozen_meta["spent"]) != 1_303_552:
        mismatches.append(f"theta100 spend {frozen_meta['spent']}")
    if round(float(frozen_arm["score_25"]["score_16"]["mean_per_query_product"]), 4) != 0.0296:
        mismatches.append("theta25 product")
    if round(float(frozen_arm["score_100"]["score_16"]["mean_per_query_product"]), 4) != 0.1221:
        mismatches.append("theta100 product")

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    if len(query_ids) != 16:
        mismatches.append(f"manifest {len(query_ids)}")
    records = compile_attribute_inventory(statements)
    catalog = load_official_catalog(SCHEMA_PATH)
    specs = compile_specs(catalog, records)
    if specs_hash(specs) != frozen_meta["hashes"]["specs"]:
        mismatches.append("specs hash")
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}

    dest100 = OUT / "repro_theta100.db"
    dest25 = OUT / "repro_theta25.db"
    repro100 = materialize(dest100, fills100, mapping, statements, predicates, query_ids)
    repro25 = materialize(dest25, fills25, mapping, statements, predicates, query_ids)
    if repro100["bag_sha256"] != frozen100["bag_sha256"] or repro100["bag_sha256"] != _hash(bags100):
        mismatches.append("theta100 bags")
    if repro25["bag_sha256"] != frozen25["bag_sha256"] or repro25["bag_sha256"] != _hash(bags25):
        mismatches.append("theta25 bags")
    if repro100["overlay"]["changed_cells"] != 517:
        mismatches.append("repro overlay 100")
    if file_sha256(FROZEN / "theta100.db") != frozen100["overlay"]["db_sha256"]:
        mismatches.append("frozen theta100.db")
    if file_sha256(FROZEN / "theta25.db") != frozen25["overlay"]["db_sha256"]:
        mismatches.append("frozen theta25.db")
    if file_sha256(PLUMBING) != frozen_meta["hashes"]["plumbing"]:
        mismatches.append("plumbing mutated")

    reconcile = {
        "calls": len(journal),
        "attempted_cells": len(journal),
        "accepted_cells": frozen_meta["accepted"],
        "theta25_spend": frozen25["spent"],
        "theta25_product": frozen_arm["score_25"]["score_16"]["mean_per_query_product"],
        "theta100_spend": frozen_meta["spent"],
        "theta100_product": frozen_arm["score_100"]["score_16"]["mean_per_query_product"],
        "journal25_rows": len(journal25),
        "scheduled25_prefix": len(schedules_frozen["theta_25"]),
        "mismatches": mismatches,
    }
    (OUT / "reconcile.json").write_text(json.dumps(reconcile, indent=2))
    if mismatches:
        write_report(
            OUT / "REPORT.md",
            "# Finan candidate-select θ25 budget audit\n\n"
            f"**Decision: `audit invalid`**\n\nFrozen arm failed reconcile: {mismatches}\n",
        )
        print(json.dumps({"decision": "audit invalid", "mismatches": mismatches}, indent=2))
        return 2

    prompt_by_key = {(row["entity_id"], row["attribute"]): row for row in prompts}
    journal_by_key = {f"{row['entity_id']}::{row['attribute']}": row for row in journal}
    inventory_by_key = {(row["entity_id"], row["attribute"]): row for row in inventory}
    plumbing_filled: dict[tuple[str, str], Any] = {}
    entities = []
    for row in plumbing_rows:
        entity = str(row.get("__entity_id") or "")
        entities.append(entity)
        for name in specs:
            if not _null(row.get(name)):
                plumbing_filled[(entity, name)] = row.get(name)
    entities = sorted(dict.fromkeys(entities))

    tasks: list[dict[str, Any]] = []
    empty_cells = []
    for row in inventory:
        key = f"{row['entity_id']}::{row['attribute']}"
        if row.get("empty"):
            empty_cells.append(row)
            continue
        prompt = prompt_by_key.get((row["entity_id"], row["attribute"]))
        spec = specs[row["attribute"]]
        meta = extract_metadata(prompt["user"]) if prompt else document_metadata(texts.get(row["document_id"], ""))
        if prompt is None:
            rendered = assemble(spec, [cand_from_dict(item) for item in row["candidates"]], meta)
            prompt_tokens = prompt_token_count(
                DOCETL_SYSTEM,
                rendered["user"],
                rendered["tools"],
            )
            reserved = prompt_tokens + COMPLETION_RESERVATION
            user = rendered["user"]
            output_schema = rendered["output_schema"]
            original_prompt_tokens = prompt_tokens
            has_frozen_call = False
        else:
            user = prompt["user"]
            output_schema = prompt["output_schema"]
            original_prompt_tokens = int(prompt["prompt_tokens"])
            reserved = int(prompt["reserved"])
            has_frozen_call = True
        tasks.append(
            {
                "key": key,
                "task_id": task_id_for(row["entity_id"], row["attribute"]),
                "entity_id": row["entity_id"],
                "document_id": row["document_id"],
                "attribute": row["attribute"],
                "task_class": spec.task_class,
                "candidates": row["candidates"],
                "candidate_objs": [cand_from_dict(item) for item in row["candidates"]],
                "spec": spec,
                "metadata": meta,
                "user": user,
                "output_schema": output_schema,
                "original_prompt_tokens": original_prompt_tokens,
                "original_reserved": reserved,
                "has_frozen_call": has_frozen_call,
            }
        )
    tasks_by_key = {task["key"]: task for task in tasks}
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise SystemExit("task id collision across arm")

    completions = [int(row.get("api_completion_tokens") or 0) for row in journal]
    api_prompts = [int(row.get("api_prompt_tokens") or 0) for row in journal]
    mean_completion = sum(completions) / len(completions) if completions else 0.0
    median_completion = pctile(completions, 0.5)
    actual_charges = {
        f"{row['entity_id']}::{row['attribute']}": int(row.get("api_prompt_tokens") or 0) + int(row.get("api_completion_tokens") or 0)
        for row in journal
    }

    anatomy_rows = []
    component_values = defaultdict(list)
    for task in tasks:
        if not task["has_frozen_call"]:
            continue
        parsed = parse_original_components(task["user"], task["attribute"], task["spec"].official_description, task["candidates"])
        tools, _ = tools_for_schema(task["output_schema"], DOCETL_MODEL)
        tool_text = json.dumps(tools, default=str)
        cards = parsed["cards"]
        ids = "\n".join(str(item.get("id") or "") for item in task["candidates"])
        raws = field_join(task["candidates"], "raw_span")
        rows = field_join(task["candidates"], "row_label")
        headers = field_join(task["candidates"], "column_header")
        titles = field_join(task["candidates"], "table_title", "heading")
        puc = field_join(task["candidates"], "period", "unit", "currency")
        neighbors = field_join(task["candidates"], "neighbors", "local_text")
        journal_row = journal_by_key[task["key"]]
        parts = {
            "system_prompt": count_tokens(DOCETL_SYSTEM),
            "repeated_instructions": count_tokens(parsed["instructions"]),
            "output_schema_tool_definition": count_tokens(tool_text),
            "authoritative_attribute_description": count_tokens(parsed["description"]),
            "document_entity_metadata": count_tokens(parsed["metadata"]),
            "candidate_ids": count_tokens(ids),
            "candidate_raw_values": count_tokens(raws),
            "row_labels": count_tokens(rows),
            "column_headers": count_tokens(headers),
            "table_titles": count_tokens(titles),
            "period_unit_currency_metadata": count_tokens(puc),
            "neighboring_evidence_text": count_tokens(neighbors),
            "completion": int(journal_row.get("api_completion_tokens") or 0),
        }
        parts["fixed_overhead"] = (
            parts["system_prompt"]
            + parts["repeated_instructions"]
            + parts["output_schema_tool_definition"]
            + parts["authoritative_attribute_description"]
            + parts["document_entity_metadata"]
        )
        parts["candidate_dependent_payload"] = (
            parts["candidate_ids"]
            + parts["candidate_raw_values"]
            + parts["row_labels"]
            + parts["column_headers"]
            + parts["table_titles"]
            + parts["period_unit_currency_metadata"]
            + parts["neighboring_evidence_text"]
        )
        parts["tokenizer_prompt"] = task["original_prompt_tokens"]
        parts["api_prompt"] = int(journal_row.get("api_prompt_tokens") or 0)
        anatomy_rows.append({"key": task["key"], **parts})
        for name, value in parts.items():
            component_values[name].append(value)

    accepted_n = 517
    sql_visible = int(frozen_arm.get("sql_visible_fills") or 0)
    total_tokens = sum(int(row.get("api_prompt_tokens") or 0) + int(row.get("api_completion_tokens") or 0) for row in journal)
    shareable = ["system_prompt", "repeated_instructions", "output_schema_tool_definition", "document_entity_metadata"]
    shareable_total = sum(sum(component_values[name]) for name in shareable)
    candidate_total = sum(component_values["candidate_dependent_payload"])
    tokenizer_prompt_total = sum(component_values["tokenizer_prompt"])
    anatomy = {
        "components": {name: summarize(vals) for name, vals in component_values.items()},
        "tokens_per_attempted_cell": total_tokens / 1174,
        "tokens_per_accepted_cell": total_tokens / accepted_n,
        "tokens_per_sql_visible_fill": total_tokens / sql_visible if sql_visible else None,
        "fixed_overhead_per_call": summarize(component_values["fixed_overhead"]),
        "candidate_dependent_payload_per_call": summarize(component_values["candidate_dependent_payload"]),
        "proportion_removable_through_shared_batching": shareable_total / tokenizer_prompt_total if tokenizer_prompt_total else 0.0,
        "proportion_candidate_dependent": candidate_total / tokenizer_prompt_total if tokenizer_prompt_total else 0.0,
        "completion_distribution": {
            "mean": mean_completion,
            "median": median_completion,
            "p90": pctile(completions, 0.9),
            "total": sum(completions),
        },
        "api_prompt_distribution": summarize(api_prompts),
        "note": "Component totals can overlap because field strings are counted independently of the serialized card syntax.",
    }

    preservation = []
    compact_card_tokens = []
    original_card_tokens = []
    lossless_n = 0
    residual_n = 0
    dropped_reasons = Counter()
    for task in tasks:
        orig_cards = parse_original_components(task["user"], task["attribute"], task["spec"].official_description, task["candidates"])["cards"]
        compact_lines, reports = compact_card_lines(task["candidates"])
        original_card_tokens.append(count_tokens(orig_cards))
        compact_card_tokens.append(count_tokens(compact_lines))
        for item, report in zip(task["candidates"], reports):
            lossless_n += int(report["lossless"])
            residual_n += int(not report["lossless"])
            for field, info in report["dropped"].items():
                dropped_reasons[f"{field}:{info['reason']}"] += 1
            preservation.append(
                {
                    "entity_id": task["entity_id"],
                    "document_id": task["document_id"],
                    "attribute": task["attribute"],
                    "candidate_id": item.get("id"),
                    "original": item,
                    "compact": report["retained"],
                    "compact_line": report["line"],
                    "dropped": report["dropped"],
                    "lossless": report["lossless"],
                }
            )
    compression_frac = 1.0 - (sum(compact_card_tokens) / sum(original_card_tokens) if sum(original_card_tokens) else 1.0)
    anatomy["proportion_removable_through_deterministic_card_compression"] = (
        sum(original_card_tokens) - sum(compact_card_tokens)
    ) / tokenizer_prompt_total if tokenizer_prompt_total else 0.0
    anatomy["card_tokens"] = {"original": summarize(original_card_tokens), "compact": summarize(compact_card_tokens), "removed_fraction": compression_frac}

    with (OUT / "card_preservation.jsonl").open("w") as handle:
        for row in preservation:
            handle.write(json.dumps(row, default=str) + "\n")

    for task in tasks:
        spec = task["spec"]
        user = compact_one_cell_user(task, spec, task["metadata"])
        schema = CLASSIFY_SCHEMA if spec.task_class == "classification" else EXTRACTIVE_SCHEMA
        tools, _ = tools_for_schema(schema, DOCETL_MODEL)
        tokens = prompt_token_count(DOCETL_SYSTEM, user, tools)
        task["compact_user"] = user
        task["compact_prompt_tokens"] = tokens
        task["compact_reserved"] = reserved_for(tokens, 1, mean_completion)

    batch_cache: dict[tuple[int, tuple[str, ...]], dict[str, Any]] = {}
    sample_batches: dict[str, Any] = {}

    def batch_record(group: list[dict[str, Any]], batch_size: int) -> dict[str, Any]:
        key = (batch_size, tuple(item["key"] for item in group))
        if key in batch_cache:
            return batch_cache[key]
        if batch_size == 1 and len(group) == 1:
            task = group[0]
            rec = {
                "entity_id": task["entity_id"],
                "document_id": task["document_id"],
                "task_ids": [task["task_id"]],
                "attributes": [task["attribute"]],
                "n_cells": 1,
                "user": task["compact_user"],
                "prompt_tokens": task["compact_prompt_tokens"],
                "reserved": task["compact_reserved"],
                "namespaced_candidate_ids": [f"{task['task_id']}.{item['id']}" for item in task["candidates"]],
            }
            batch_cache[key] = rec
            return rec
        built = build_batch_prompt(group, specs, group[0]["metadata"])
        built["reserved"] = reserved_for(built["prompt_tokens"], built["n_cells"], mean_completion)
        batch_cache[key] = built
        return built

    complete_arm = {}
    frozen_tasks = [task for task in tasks if task["has_frozen_call"]]
    for k in BATCH_SIZES:
        groups = pack_groups(frozen_tasks, k)
        recs = [batch_record(group, k) for group in groups]
        complete_arm[str(k)] = {
            "batch_size": k,
            "projected_calls": len(recs),
            "prompt_tokens": sum(row["prompt_tokens"] for row in recs),
            "reserved_tokens": sum(row["reserved"] for row in recs),
            "reservation_style_tokens": sum(row["prompt_tokens"] + COMPLETION_RESERVATION for row in recs),
            "fits_theta25": sum(row["reserved"] for row in recs) <= THETA_25,
            "attempted_cells": len(frozen_tasks),
        }
        if k not in sample_batches:
            sample_batches[str(k)] = {
                "n_sample_batches": min(3, len(recs)),
                "samples": [
                    {key: rec[key] for key in rec if key != "tools"}
                    for rec in recs[:3]
                ],
            }
    (OUT / "microbatch_prompts_sample.json").write_text(json.dumps(sample_batches, indent=2, default=str))

    original_one_cell_all = {
        "batch_size": "original_1",
        "projected_calls": len(frozen_tasks),
        "prompt_tokens": sum(task["original_prompt_tokens"] for task in frozen_tasks),
        "reserved_tokens": sum(task["original_reserved"] for task in frozen_tasks),
        "fits_theta25": sum(task["original_reserved"] for task in frozen_tasks) <= THETA_25,
        "attempted_cells": len(frozen_tasks),
    }

    roles = query_attr_roles(statements)
    graph = WorkloadGraph(tasks, empty_cells, plumbing_filled, roles, query_ids, entities)
    graph_payload = graph.as_dict()
    graph_hash = _hash(graph_payload)
    (OUT / "workload_graph.json").write_text(json.dumps(graph_payload, indent=2, default=str))

    def cost_original(_scheduled: set[str], keys: list[str]) -> int:
        return sum(tasks_by_key[key]["original_reserved"] for key in keys)

    def make_batch_cost(batch_size: int):
        def cost(scheduled: set[str], keys: list[str]) -> int:
            affected = {tasks_by_key[key]["entity_id"] for key in keys}
            before = 0
            after = 0
            for entity in affected:
                current = [tasks_by_key[item] for item in scheduled if tasks_by_key[item]["entity_id"] == entity]
                added = current + [tasks_by_key[key] for key in keys if tasks_by_key[key]["entity_id"] == entity]
                before += sum(batch_record(group, batch_size)["reserved"] for group in pack_groups(current, batch_size))
                after += sum(batch_record(group, batch_size)["reserved"] for group in pack_groups(added, batch_size))
            return after - before

        return cost

    cpsat = try_cpsat()
    schedule_specs = [
        ("original_one_cell", 1, cost_original, False),
        ("compact_one_cell", 1, make_batch_cost(1), True),
        ("compact_batch_2", 2, make_batch_cost(2), True),
        ("compact_batch_3", 3, make_batch_cost(3), True),
        ("compact_batch_4", 4, make_batch_cost(4), True),
        ("compact_batch_6", 6, make_batch_cost(6), True),
        ("compact_batch_8", 8, make_batch_cost(8), True),
    ]
    schedules: dict[str, Any] = {}
    for name, k, cost_fn, compact in schedule_specs:
        print(json.dumps({"status": "scheduling", "name": name}, indent=2), flush=True)
        raw = greedy_schedule(graph, cost_fn, THETA_25)
        selected_tasks = [tasks_by_key[key] for key in raw["scheduled_keys"]]
        if compact:
            groups = pack_groups(selected_tasks, k)
            recs = [batch_record(group, k) for group in groups]
            reserved = sum(row["reserved"] for row in recs)
            calls = len(recs)
            prompt_tokens = sum(row["prompt_tokens"] for row in recs)
        else:
            reserved = sum(task["original_reserved"] for task in selected_tasks)
            calls = len(selected_tasks)
            prompt_tokens = sum(task["original_prompt_tokens"] for task in selected_tasks)
        completed = raw["completed_witnesses"]
        unlocked = [row for row in completed if not graph.by_witness[(row["query_id"], row["entity_id"])]["already_complete"]]
        queries_hit = sorted({row["query_id"] for row in unlocked})
        schedules[name] = {
            **raw,
            "format": name,
            "batch_size": k,
            "compact": compact,
            "cpsat_available": cpsat,
            "solver_used": "deterministic_witness_package_greedy",
            "n_scheduled_tasks": len(selected_tasks),
            "projected_calls": calls,
            "projected_prompt_tokens": prompt_tokens,
            "projected_reserved_tokens": reserved,
            "candidate_witnesses_completed": len(unlocked),
            "queries_receiving_complete_witnesses": queries_hit,
            "n_queries_receiving_complete_witnesses": len(queries_hit),
        }
        print(
            json.dumps(
                {
                    "scheduled": name,
                    "tasks": len(selected_tasks),
                    "reserved": reserved,
                    "objective": raw["objective"],
                    "unlocked": len(unlocked),
                },
                indent=2,
            ),
            flush=True,
        )

    schedule_hashes = {name: _hash({k: schedules[name][k] for k in ("scheduled_keys", "packages", "reserved", "objective")}) for name in schedules}
    (OUT / "schedules.json").write_text(json.dumps({"schedules": {k: {kk: vv for kk, vv in rec.items() if kk != "packages"} | {"n_packages": len(rec["packages"])} for k, rec in schedules.items()}, "hashes": schedule_hashes, "graph_sha256": graph_hash}, indent=2, default=str))
    (OUT / "schedule_packages.json").write_text(json.dumps({k: v["packages"] for k, v in schedules.items()}, indent=2, default=str))

    orig = schedules["original_one_cell"]
    replay_packages = list(orig["packages"])
    replay_keys: list[str] = []
    replay_spend = 0
    def package_actual(package: dict[str, Any]) -> int:
        total = 0
        for key in package["task_keys"]:
            total += actual_charges.get(key, tasks_by_key[key]["original_reserved"])
        return total

    kept_packages = []
    for package in replay_packages:
        extra = package_actual(package)
        if replay_spend + extra <= THETA_25:
            kept_packages.append(package)
            replay_keys.extend(package["task_keys"])
            replay_spend += extra
        else:
            break
    while replay_spend > THETA_25 and kept_packages:
        dropped = kept_packages.pop()
        replay_spend -= package_actual(dropped)
        replay_keys = [key for package in kept_packages for key in package["task_keys"]]
    leftover_actual = []
    for key in orig["leftover_fillers"]:
        extra = actual_charges.get(key, tasks_by_key[key]["original_reserved"])
        if replay_spend + extra <= THETA_25:
            leftover_actual.append(key)
            replay_keys.append(key)
            replay_spend += extra
    replay_keys = list(dict.fromkeys(replay_keys))
    replay_fills = fills_from_keys(replay_keys, tasks_by_key, journal_by_key)
    replay_mat = materialize(OUT / "replay_original_one_cell.db", replay_fills, mapping, statements, predicates, query_ids)
    replay_freeze = {
        "label": "replay_original_one_cell",
        "kind": "zero_token_scheduling_counterfactual",
        "n_tasks": len(replay_keys),
        "actual_spend": replay_spend,
        "budget": THETA_25,
        "fits": replay_spend <= THETA_25,
        "scheduled_keys": replay_keys,
        "packages_kept": len(kept_packages),
        "overlay": replay_mat["overlay"],
        "bag_sha256": replay_mat["bag_sha256"],
        "db_sha256": replay_mat["db_sha256"],
        "schedule_sha256": schedule_hashes["original_one_cell"],
        "graph_sha256": graph_hash,
    }
    (OUT / "replay_original_one_cell_frozen.json").write_text(json.dumps(replay_freeze, indent=2, default=str))
    (OUT / "replay_original_one_cell_fills.json").write_text(json.dumps(replay_fills, indent=2, default=str))
    (OUT / "replay_original_one_cell_bags.json").write_text(json.dumps(replay_mat["bags"], indent=2, default=str))

    projections = {}
    for name, rec in schedules.items():
        if name == "original_one_cell":
            continue
        keys = rec["scheduled_keys"]
        fills = fills_from_keys(keys, tasks_by_key, journal_by_key)
        dest = OUT / f"projection_{name}.db"
        mat = materialize(dest, fills, mapping, statements, predicates, query_ids)
        projections[name] = {
            "label": "decision_invariance_projection",
            "official_score": False,
            "format": name,
            "projected_calls": rec["projected_calls"],
            "projected_tokens": rec["projected_reserved_tokens"],
            "projected_prompt_tokens": rec["projected_prompt_tokens"],
            "attempted_cells": rec["n_scheduled_tasks"],
            "candidate_witnesses_completed": rec["candidate_witnesses_completed"],
            "queries_receiving_complete_witnesses": rec["queries_receiving_complete_witnesses"],
            "overlay": mat["overlay"],
            "bag_sha256": mat["bag_sha256"],
            "db_sha256": mat["db_sha256"],
            "schedule_sha256": schedule_hashes[name],
            "fills": fills,
        }
        (OUT / f"projection_{name}_frozen.json").write_text(json.dumps({k: v for k, v in projections[name].items() if k != "fills"}, indent=2, default=str))
        (OUT / f"projection_{name}_fills.json").write_text(json.dumps(fills, indent=2, default=str))
        (OUT / f"projection_{name}_bags.json").write_text(json.dumps(mat["bags"], indent=2, default=str))

    freeze_hashes = {
        "graph": graph_hash,
        "schedules": schedule_hashes,
        "replay": _hash(replay_freeze),
        "projections": {name: _hash({k: v for k, v in rec.items() if k != "fills"}) for name, rec in projections.items()},
        "anatomy": _hash({k: anatomy[k] for k in anatomy if k != "note"}),
        "complete_arm": _hash(complete_arm),
        "card_preservation": file_sha256(OUT / "card_preservation.jsonl"),
    }
    (OUT / "pre_gold_freeze.json").write_text(json.dumps(freeze_hashes, indent=2))
    print(json.dumps({"status": "hashed_before_gold", "hashes": freeze_hashes}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    gold_rows = gold.get("finance") or gold.get("Finance") or []
    gold_by: dict[str, dict[str, Any]] = {}
    for grow in gold_rows:
        for key in (str(grow.get("doc_id") or ""), Path(str(grow.get("doc_id") or "")).stem, str(grow.get("id") or "")):
            if key:
                gold_by[key] = grow

    def gold_value(doc_id: str, name: str) -> Any:
        grow = gold_by.get(doc_id) or gold_by.get(f"{doc_id}.txt") or {}
        raw = grow.get(name)
        if raw is None and name == "total_debt":
            raw = grow.get("total_Debt")
        return raw

    def gold_match(name: str, pred: Any, gold_v: Any) -> bool:
        spec = specs[name]
        gnorm, _, _ = normalize_value(gold_v, spec.dtype) if gold_v not in (None, "") else (None, None, None)
        pnorm, _, _ = normalize_value(pred, spec.dtype) if pred not in (None, "") else (None, None, None)
        if gnorm is None or pnorm is None:
            return False
        if gnorm == pnorm:
            return True
        if spec.dtype == "numeric" and isinstance(gnorm, (int, float)) and isinstance(pnorm, (int, float)) and gnorm != 0:
            return abs(float(pnorm) - float(gnorm)) / abs(float(gnorm)) <= 0.20
        if spec.dtype == "string":
            return str(gnorm).lower() in str(pnorm).lower() or str(pnorm).lower() in str(gnorm).lower()
        return False

    gold_map = {(task["document_id"], task["attribute"]): gold_value(task["document_id"], task["attribute"]) for task in tasks}

    confirm25 = score_db(FROZEN / "theta25.db", statements, predicates, query_ids, gold)
    confirm100 = score_db(FROZEN / "theta100.db", statements, predicates, query_ids, gold)
    if round(confirm25["score_16"]["mean_per_query_product"], 4) != 0.0296:
        raise SystemExit("post-freeze theta25 score drifted")
    if round(confirm100["score_16"]["mean_per_query_product"], 4) != 0.1221:
        raise SystemExit("post-freeze theta100 score drifted")

    replay_score = score_db(OUT / "replay_original_one_cell.db", statements, predicates, query_ids, gold)
    projection_scores = {}
    for name in projections:
        projection_scores[name] = score_db(OUT / f"projection_{name}.db", statements, predicates, query_ids, gold)
        projections[name]["projected_product_under_decision_invariance"] = projection_scores[name]["score_16"]["mean_per_query_product"]
        projections[name]["projected_score_16"] = {
            k: projection_scores[name]["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")
        }

    gold_match_keys = []
    for task in frozen_tasks:
        row = journal_by_key.get(task["key"])
        if row and gold_match(task["attribute"], row.get("accepted"), gold_map[(task["document_id"], task["attribute"])]):
            gold_match_keys.append(task["key"])

    def gold_cost(_scheduled: set[str], keys: list[str]) -> int:
        return sum(tasks_by_key[key]["original_reserved"] for key in keys)

    class GoldGraph(WorkloadGraph):
        pass

    useful = [tasks_by_key[key] for key in gold_match_keys]
    gold_graph = WorkloadGraph(useful, empty_cells, plumbing_filled, roles, query_ids, entities)
    oracle_sched = greedy_schedule(gold_graph, gold_cost, THETA_25)
    oracle_fills = fills_from_keys(oracle_sched["scheduled_keys"], tasks_by_key, journal_by_key)
    oracle_mat = materialize(OUT / "oracle_scheduling.db", oracle_fills, mapping, statements, predicates, query_ids)
    oracle_score = score_db(OUT / "oracle_scheduling.db", statements, predicates, query_ids, gold)

    label_keys = schedules["original_one_cell"]["scheduled_keys"]
    label_fills = fills_from_keys(label_keys, tasks_by_key, journal_by_key, use_accepted=False, gold_values=gold_map, gold_match_fn=gold_match)
    label_mat = materialize(OUT / "oracle_candidate_label.db", label_fills, mapping, statements, predicates, query_ids)
    label_score = score_db(OUT / "oracle_candidate_label.db", statements, predicates, query_ids, gold)

    full_theta100_compact = {k: complete_arm[k]["reserved_tokens"] for k in complete_arm}
    min_k_all = None
    for k in BATCH_SIZES:
        if complete_arm[str(k)]["fits_theta25"]:
            min_k_all = k
            break

    replay_product = replay_score["score_16"]["mean_per_query_product"]
    compact1_all_fit = complete_arm["1"]["fits_theta25"]
    compact1_proj = projections["compact_one_cell"]["projected_product_under_decision_invariance"]
    batch_proj_hit = any(
        projections[name]["projected_product_under_decision_invariance"] > TARGET_PRODUCT
        and projections[name]["projected_tokens"] <= THETA_25
        for name in projections
    )
    all_fit_any = any(complete_arm[str(k)]["fits_theta25"] for k in BATCH_SIZES)
    oracle_prod = oracle_score["score_16"]["mean_per_query_product"]
    label_prod = label_score["score_16"]["mean_per_query_product"]

    if replay_product > TARGET_PRODUCT and replay_spend <= THETA_25:
        decision = "workload-coherent scheduling beats DocETL at 25%"
    elif compact1_all_fit or (compact1_proj > TARGET_PRODUCT and schedules["compact_one_cell"]["projected_reserved_tokens"] <= THETA_25):
        decision = "compact single-cell selection can make the 25% target feasible"
    elif all_fit_any or batch_proj_hit:
        decision = "microbatching is required to make the 25% target feasible"
    elif oracle_prod <= TARGET_PRODUCT and label_prod <= TARGET_PRODUCT and not all_fit_any:
        decision = "even perfect scheduling and compression cannot meet the 25% target"
    else:
        decision = "even perfect scheduling and compression cannot meet the 25% target"

    frozen_deltas = {row["query_id"]: row.get("delta") or 0.0 for row in frozen_arm.get("per_query") or []}
    lift_queries = sorted(qid for qid, delta in frozen_deltas.items() if delta > 0)
    scheduled_queries = {
        name: rec["queries_receiving_complete_witnesses"] for name in schedules
    }
    overlap = {
        name: {
            "lift_queries": lift_queries,
            "scheduled_queries": rec,
            "intersection": sorted(set(lift_queries) & set(rec)),
            "lift_captured": (len(set(lift_queries) & set(rec)) / len(lift_queries)) if lift_queries else None,
        }
        for name, rec in scheduled_queries.items()
    }

    payload = {
        "decision": decision,
        "success_criterion": {"product": TARGET_PRODUCT, "tokens": THETA_25, "model": "Qwen 2.5 7B"},
        "reconcile": reconcile,
        "anatomy": anatomy,
        "compression": {
            "n_cards": len(preservation),
            "lossless_cards": lossless_n,
            "residual_cards": residual_n,
            "dropped_reasons": dict(dropped_reasons),
            "card_tokens": anatomy["card_tokens"],
            "removed_from_cards": [
                "repeated prose / card syntax (span=, row=, header=, title=, period=, unit=, currency=, offset= labels)",
                "default placeholders unknown/unspecified when equivalent to omission",
                "fields proven equal to another retained field (row/header/title)",
                "empty neighbors and empty local_text",
                "end when equal to start + raw_span length",
                "ranking metadata: in_c1, score, kind",
                "normalized when equal to raw or treated as derived",
            ],
            "retained_always": [
                "candidate ID",
                "raw candidate value",
                "row label if not redundant",
                "column header if not redundant",
                "table/section title",
                "period if not a default placeholder",
                "unit or multiplier if not a default placeholder",
                "currency if not a default placeholder",
                "source-offset ID",
            ],
        },
        "complete_arm_estimates": {"original_one_cell": original_one_cell_all, "compact_batched": complete_arm},
        "minimum_batch_size_all_1174_in_theta25": min_k_all,
        "full_theta100_decisions_at_compact_cost": full_theta100_compact,
        "graph": {"sha256": graph_hash, **{k: graph_payload[k] for k in graph_payload if k != "empty_cells"}},
        "scheduler": {
            "cpsat_available": cpsat,
            "solver_used": "deterministic_witness_package_greedy",
            "hashes": schedule_hashes,
        },
        "schedules": {
            name: {
                "n_scheduled_tasks": rec["n_scheduled_tasks"],
                "projected_calls": rec["projected_calls"],
                "projected_tokens": rec["projected_reserved_tokens"],
                "attempted_cells": rec["n_scheduled_tasks"],
                "candidate_witnesses_completed": rec["candidate_witnesses_completed"],
                "queries_receiving_complete_witnesses": rec["queries_receiving_complete_witnesses"],
                "objective": rec["objective"],
                "sha256": schedule_hashes[name],
            }
            for name, rec in schedules.items()
        },
        "official_replay": {
            "product": replay_product,
            "actual_spend": replay_spend,
            "n_tasks": len(replay_keys),
            "fits": replay_spend <= THETA_25,
            "score_16": {
                k: replay_score["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")
            },
            "bag_sha256": replay_mat["bag_sha256"],
            "db_sha256": replay_mat["db_sha256"],
            "official": True,
        },
        "decision_invariance_projections": {
            name: {
                "official_score": False,
                "projected_calls": rec["projected_calls"],
                "projected_tokens": rec["projected_tokens"],
                "attempted_cells": rec["attempted_cells"],
                "candidate_witnesses_completed": rec["candidate_witnesses_completed"],
                "queries_receiving_complete_witnesses": rec["queries_receiving_complete_witnesses"],
                "projected_product_under_decision_invariance": rec["projected_product_under_decision_invariance"],
                "projected_score_16": rec["projected_score_16"],
                "bag_sha256": rec["bag_sha256"],
            }
            for name, rec in projections.items()
        },
        "diagnostics": {
            "scheduling_oracle": {
                "label": "unattainable gold-aware scheduling ceiling",
                "product": oracle_prod,
                "n_tasks": len(oracle_sched["scheduled_keys"]),
                "reserved": oracle_sched["reserved"],
                "score_16": {
                    k: oracle_score["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")
                },
                "bag_sha256": oracle_mat["bag_sha256"],
            },
            "candidate_label_oracle": {
                "label": "gold-free schedule with correct candidate whenever present",
                "product": label_prod,
                "n_tasks": len(label_keys),
                "score_16": {
                    k: label_score["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")
                },
                "overlay": label_mat["overlay"],
                "bag_sha256": label_mat["bag_sha256"],
            },
            "full_theta100_decisions_minimum_compact_cost": full_theta100_compact,
        },
        "gold_free_scheduler_vs_score_lift": overlap,
        "hashes": freeze_hashes,
        "invariants": {
            "frozen_arm_unmodified": file_sha256(PLUMBING) == frozen_meta["hashes"]["plumbing"],
            "no_model_calls": True,
            "gold_loaded_after_schedule_hash": True,
            "qwen_generates_values": False,
            "cpsat": cpsat,
        },
    }
    (OUT / "finan_candidate_select_budget_audit.json").write_text(json.dumps(payload, indent=2, default=str))

    def fmt(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    lines = [
        "# Finan candidate-select θ25 budget audit",
        "",
        f"**Decision: `{decision}`**",
        "",
        "Zero-Qwen audit of the frozen schema-grounded candidate-selection arm. No compressed or microbatched model arm was launched.",
        "",
        "## Success criterion",
        "",
        "Finan product > 0.084, tokens ≤ 345,457, model = Qwen 2.5 7B.",
        "θ100 product 0.1221 is an opportunity result, not task completion.",
        "θ25 product 0.0296 is the official result against this target.",
        "",
        "## 1. Frozen-arm reconcile",
        "",
        f"- Calls: {reconcile['calls']}",
        f"- Attempted cells: {reconcile['attempted_cells']}",
        f"- Accepted cells: {reconcile['accepted_cells']}",
        f"- θ25 spend: {reconcile['theta25_spend']}",
        f"- θ25 product: {reconcile['theta25_product']:.4f}",
        f"- θ100 spend: {reconcile['theta100_spend']}",
        f"- θ100 product: {reconcile['theta100_product']:.4f}",
        f"- θ25 journal rows {reconcile['journal25_rows']} vs reserved prefix {reconcile['scheduled25_prefix']} (actual charges undershot reservation, so the snapshot kept 333 calls).",
        "- Journal, overlay, bags, and database hashes matched the frozen arm. Plumbing was not modified.",
        "",
        "## 2. Token-cost anatomy",
        "",
        "| Component | mean | median | p90 | total |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in (
        "system_prompt",
        "repeated_instructions",
        "output_schema_tool_definition",
        "authoritative_attribute_description",
        "document_entity_metadata",
        "candidate_ids",
        "candidate_raw_values",
        "row_labels",
        "column_headers",
        "table_titles",
        "period_unit_currency_metadata",
        "neighboring_evidence_text",
        "completion",
        "fixed_overhead",
        "candidate_dependent_payload",
        "tokenizer_prompt",
        "api_prompt",
    ):
        stats = anatomy["components"][name]
        lines.append(f"| {name} | {stats['mean']:.1f} | {stats['median']:.1f} | {stats['p90']:.1f} | {stats['total']:.0f} |")
    lines.extend(
        [
            "",
            f"- Tokens per attempted cell: {anatomy['tokens_per_attempted_cell']:.1f}",
            f"- Tokens per accepted cell: {anatomy['tokens_per_accepted_cell']:.1f}",
            f"- Tokens per SQL-visible fill: {anatomy['tokens_per_sql_visible_fill']:.1f}",
            f"- Fixed overhead per call: mean {anatomy['fixed_overhead_per_call']['mean']:.1f}",
            f"- Candidate-dependent payload per call: mean {anatomy['candidate_dependent_payload_per_call']['mean']:.1f}",
            f"- Proportion removable through shared batching: {anatomy['proportion_removable_through_shared_batching']:.3f}",
            f"- Proportion removable through deterministic card compression: {anatomy['proportion_removable_through_deterministic_card_compression']:.3f}",
            "- Neighboring evidence text is absent from every frozen inventory card.",
            "",
            "## 3. Compact candidate cards",
            "",
            f"- Cards: {len(preservation)}; lossless {lossless_n}; residual {residual_n}",
            f"- Original card tokens total {anatomy['card_tokens']['original']['total']:.0f}; compact {anatomy['card_tokens']['compact']['total']:.0f}; removed fraction {anatomy['card_tokens']['removed_fraction']:.3f}",
            "- Representation is corpus-agnostic: ID, raw value, row, header, title, period, unit, currency, source offset.",
            "- Removed only after a deterministic proof: default placeholder ≡ omission, equal fields, empty neighbors, `end = start + len(raw_span)`, ranking metadata.",
            "- Field-level report: `card_preservation.jsonl`.",
            "",
            "## 4. Microbatch request formats",
            "",
            "Prompts were generated, not executed. Batches stay inside one entity/document. Task IDs are unique; candidate IDs are namespaced as `task_id.C#`. The shared schema has no value field.",
            "",
            "| Format | calls | prompt tokens | reserved tokens | fits θ25 |",
            "| --- | ---: | ---: | ---: | ---: |",
            f"| original one-cell | {original_one_cell_all['projected_calls']} | {original_one_cell_all['prompt_tokens']} | {original_one_cell_all['reserved_tokens']} | {original_one_cell_all['fits_theta25']} |",
        ]
    )
    for k in BATCH_SIZES:
        rec = complete_arm[str(k)]
        lines.append(
            f"| compact batch-{k} | {rec['projected_calls']} | {rec['prompt_tokens']} | {rec['reserved_tokens']} | {rec['fits_theta25']} |"
        )
    lines.extend(
        [
            "",
            f"- Reserved cost uses Qwen tokenizer prompt tokens plus `max(192, k × mean frozen completion {mean_completion:.2f})`.",
            f"- Minimum batch size that places all 1,174 frozen tasks within 345,457: `{min_k_all}`.",
            "- Decision invariance is not assumed from field preservation.",
            "",
            "## 5–6. Workload graph and θ25 schedules",
            "",
            f"- CP-SAT available: {cpsat}. Solver used: `deterministic_witness_package_greedy`.",
            f"- Graph hash: `{graph_hash}`",
            f"- Feasible witnesses: {graph_payload['n_feasible_witnesses']}; already complete from plumbing: {graph_payload['n_already_complete']}; empty unavailable cells: {graph_payload['n_empty_unavailable']}",
            "",
            "| Schedule | tasks | calls | reserved | witnesses unlocked | queries | objective |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, rec in schedules.items():
        lines.append(
            f"| {name} | {rec['n_scheduled_tasks']} | {rec['projected_calls']} | {rec['projected_reserved_tokens']} | {rec['candidate_witnesses_completed']} | {rec['n_queries_receiving_complete_witnesses']} | {rec['objective']:.4f} |"
        )
    lines.extend(
        [
            "",
            "Schedules and projections were hashed before gold was loaded.",
            "",
            "## 7. Official zero-token scheduling replay",
            "",
            f"- Actual spend: {replay_spend} / {THETA_25}",
            f"- Tasks replayed: {len(replay_keys)}",
            f"- Official 16-query product: **{replay_product:.4f}**",
            f"- Structure F2 {replay_score['score_16']['mean_structure_f2']:.4f}; cell F1@0.20 {replay_score['score_16']['mean_cell_f1_at_0.20']:.4f}",
            f"- Bag hash: `{replay_mat['bag_sha256']}`",
            "- This is a valid zero-call counterfactual: frozen prompts and outputs were reused; only the predeclared schedule changed.",
            "",
            "## 8. Decision-invariance projections",
            "",
            "These are **not official model results**. They ask what the score would be if compact or batched presentation preserved each frozen per-cell decision.",
            "",
            "| Format | calls | tokens | cells | witnesses | queries | projected product |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, rec in projections.items():
        lines.append(
            f"| {name} | {rec['projected_calls']} | {rec['projected_tokens']} | {rec['attempted_cells']} | {rec['candidate_witnesses_completed']} | {len(rec['queries_receiving_complete_witnesses'])} | {rec['projected_product_under_decision_invariance']:.4f} |"
        )
    lines.extend(
        [
            "",
            f"- Full θ100 coverage inside θ25? compact-1 `{complete_arm['1']['fits_theta25']}`; first fitting batch size `{min_k_all}`.",
            "",
            "## 9. Post-freeze diagnostic ceilings",
            "",
            f"- Scheduling oracle (unattainable, gold-aware task subset, original costs): **{oracle_prod:.4f}** on {len(oracle_sched['scheduled_keys'])} tasks, reserved {oracle_sched['reserved']}.",
            f"- Candidate-label oracle (gold-free schedule, correct candidate when present): **{label_prod:.4f}**.",
            f"- Minimum compact/batched reserved tokens to carry all 1,174 frozen θ100 decisions: {full_theta100_compact}.",
            "",
            "## 10. Required conclusions",
            "",
            f"- Scheduling alone beats 0.084: **{replay_product > TARGET_PRODUCT}** (official replay {replay_product:.4f}).",
            f"- Compact single-cell prompts can fit enough coverage: **{compact1_all_fit or compact1_proj > TARGET_PRODUCT}** (all 1,174 fit={compact1_all_fit}; invariance product {compact1_proj:.4f}).",
            f"- Minimum batch size for all 1,174 tasks within 345,457: **{min_k_all}**.",
            "- Information removed by compression: default placeholders, proven-duplicate layout fields, empty neighbors, recoverable `end`, ranking metadata, and repeated card-field labels. Residual neighbor text never appeared.",
            f"- Gold-free scheduler vs score-lift queries: captured {overlap['original_one_cell']['intersection']} of {lift_queries} (fraction {overlap['original_one_cell']['lift_captured']}).",
            f"- θ25 scheduling ceiling: {oracle_prod:.4f}",
            f"- Candidate-label ceiling: {label_prod:.4f}",
            f"- Graph hash `{graph_hash}`; replay bag `{replay_mat['bag_sha256']}`; schedule hashes {schedule_hashes}.",
            "",
            f"**Primary decision:** `{decision}`",
            "",
        ]
    )
    write_report(OUT / "REPORT.md", "\n".join(lines) + "\n")
    print(json.dumps({"decision": decision, "replay_product": replay_product, "min_batch_all": min_k_all, "wrote": str(OUT / "REPORT.md")}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

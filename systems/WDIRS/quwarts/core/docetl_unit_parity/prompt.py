"""Locked generic map prompt compiled from the query AST."""

from __future__ import annotations

import hashlib
import json

from quwarts.core.docetl_unit_parity.config import MAP_INSTRUCTIONS
from quwarts.core.docetl_unit_parity.schema import QuerySchema


def schema_block(schema: QuerySchema) -> str:
    lines = []
    for item in schema.fields:
        lines.append(f"- {item.name} ({item.dtype}): {item.description}")
    return "\n".join(lines)


def literal_block(schema: QuerySchema) -> str:
    lines = []
    for item in schema.fields:
        if item.literals:
            lines.append(f"- {item.name}: " + ", ".join(item.literals[:12]))
        if item.semantic:
            lines.append(f"- {item.name}: inferred categorical value permitted")
    return "\n".join(lines) if lines else "- none"


def build_map_prompt(schema: QuerySchema, context: str) -> str:
    return (
        f"{MAP_INSTRUCTIONS}\n"
        f"requested_attributes: {schema.names}\n"
        f"{schema_block(schema)}\n"
        f"predicate_literals:\n{literal_block(schema)}\n\n"
        f"SOURCE:\n{context}\n"
    )


def build_repair_prompt(schema: QuerySchema, malformed: str) -> str:
    return (
        "Reformat into this shape, one entry per requested attribute:\n"
        '{"<attribute>":{"value":null,"status":"found|not_found|uncertain","evidence":""}}\n'
        f"requested_attributes: {schema.names}\n"
        f"{schema_block(schema)}\n"
        "Preserve any valid fields already present. Missing fields use value null and status not_found.\n"
        "Do not add facts that are not already in the malformed text.\n\n"
        f"MALFORMED:\n{malformed}\n"
    )


def compiled_prompts_hash(schemas: dict[str, QuerySchema]) -> str:
    payload = {
        qid: {
            "schema": schemas[qid].as_dict(),
            "instructions": MAP_INSTRUCTIONS,
            "schema_block": schema_block(schemas[qid]),
            "literal_block": literal_block(schemas[qid]),
        }
        for qid in sorted(schemas)
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

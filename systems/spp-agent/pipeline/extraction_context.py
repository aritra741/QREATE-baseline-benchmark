"""Workload-aware context for document extraction (no ground-truth schema in prompts)."""

from __future__ import annotations

import json
import re
from typing import Any

from agent.phases.demand_profile import (
    _VALID_AGG_FUNCS,
    _VALID_ROLES,
    _validate_demand_profile,
)
from pipeline.schema import Schema

_QUALIFIED_COL_RE = re.compile(r"\b([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\b")
_BARE_COL_IN_GROUP_RE = re.compile(r"\bgroup\s+by\s+(.+?)(?:\bhaving\b|\border\b|\blimit\b|$)", re.IGNORECASE | re.DOTALL)
_WHERE_CLAUSE_RE = re.compile(
    r"\bwhere\b(.+?)(?:\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_JOIN_ON_RE = re.compile(
    r"\bon\s+(.+?)(?:\bwhere\b|\bgroup\s+by\b|\bjoin\b|\border\b|\blimit\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_AGG_COL_RE = re.compile(
    r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(?:DISTINCT\s+)?(?:(\w+)\.)?(\w+)\s*\)",
    re.IGNORECASE,
)


def extract_demand_profile_sql_only(queries: list[dict]) -> dict[str, Any]:
    """Infer workload demand from SQL text only (no ground-truth schema)."""
    col_map: dict[str, dict[str, Any]] = {}
    has_join = False
    has_temporal = False

    def _touch(key: str, qid: str) -> dict[str, Any]:
        entry = col_map.setdefault(
            key,
            {
                "column": key,
                "roles": [],
                "aggregation_functions": [],
                "query_ids": [],
            },
        )
        if qid not in entry["query_ids"]:
            entry["query_ids"].append(qid)
        return entry

    def _add_role(entry: dict[str, Any], role: str) -> None:
        if role in _VALID_ROLES and role not in entry["roles"]:
            entry["roles"].append(role)

    for query in queries:
        qid = str(query.get("query_id", "unknown"))
        sql = query.get("sql_query", "")
        sql_lower = sql.lower()
        if re.search(r"\bjoin\b", sql_lower):
            has_join = True
        if re.search(r"\b(birth_date|draft_year|year|date|month|day|temporal)\b", sql_lower):
            has_temporal = True

        for table, col in _QUALIFIED_COL_RE.findall(sql):
            if col.lower() == "id":
                continue
            key = f"{table}.{col}"
            _touch(key, qid)

        group_match = _BARE_COL_IN_GROUP_RE.search(sql)
        if group_match:
            for token in re.split(r",", group_match.group(1)):
                token = token.strip()
                qm = _QUALIFIED_COL_RE.search(token)
                if qm:
                    key = f"{qm.group(1)}.{qm.group(2)}"
                    if qm.group(2).lower() != "id":
                        _add_role(_touch(key, qid), "group_key")
                elif re.match(r"^[a-zA-Z_][\w]*$", token):
                    key = token
                    _add_role(_touch(key, qid), "group_key")

        where_match = _WHERE_CLAUSE_RE.search(sql)
        if where_match:
            for table, col in _QUALIFIED_COL_RE.findall(where_match.group(1)):
                if col.lower() == "id":
                    continue
                _add_role(_touch(f"{table}.{col}", qid), "filter")

        join_match = _JOIN_ON_RE.search(sql)
        if join_match:
            for table, col in _QUALIFIED_COL_RE.findall(join_match.group(1)):
                if col.lower() != "id":
                    _add_role(_touch(f"{table}.{col}", qid), "join_key")

        for func, table, col in _AGG_COL_RE.findall(sql):
            key = f"{table}.{col}" if table else col
            if col.lower() == "id" and not table:
                continue
            entry = _touch(key, qid)
            _add_role(entry, "aggregate_input")
            fu = func.upper()
            if fu in _VALID_AGG_FUNCS and fu not in entry["aggregation_functions"]:
                entry["aggregation_functions"].append(fu)

    return _validate_demand_profile(
        {
            "columns": list(col_map.values()),
            "has_join": has_join,
            "has_temporal": has_temporal,
        }
    )


def resolve_demand_profile(
    queries: list[dict],
    *,
    demand_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build demand from workload queries only (SQL parse). No schema argument."""
    if demand_profile is not None:
        return _validate_demand_profile(demand_profile)
    if not queries:
        raise ValueError("queries are required to derive workload demand for extraction")
    return extract_demand_profile_sql_only(queries)


def compact_workload_summary(queries: list[dict], demand_profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "n_queries": len(queries),
        "has_join": bool(demand_profile.get("has_join")),
        "has_temporal": bool(demand_profile.get("has_temporal")),
        "n_demand_columns": len(demand_profile.get("columns", [])),
    }


def entity_hint_from_doc(doc: dict) -> str:
    """Schema table name for this document (prefer normalized table_hint)."""
    hint = doc.get("metadata", {}).get("table_hint")
    if hint:
        return str(hint).lower()
    doc_id = str(doc.get("doc_id", ""))
    if "/" in doc_id:
        folder = doc_id.split("/")[0].lower()
    elif "_" in doc_id:
        folder = doc_id.split("_")[0].lower()
    else:
        return ""
    from data.dataset_registry import MED_CORPUS_FOLDER_TO_TABLE

    return MED_CORPUS_FOLDER_TO_TABLE.get(folder, folder)


def demand_columns_for_entity(demand_profile: dict[str, Any], entity_hint: str) -> list[dict[str, Any]]:
    if not entity_hint:
        return list(demand_profile.get("columns", []))
    matched: list[dict[str, Any]] = []
    for col_spec in demand_profile.get("columns", []):
        column = str(col_spec.get("column", ""))
        if "." in column:
            table, attr = column.split(".", 1)
            if table.lower() != entity_hint:
                continue
            matched.append({**col_spec, "column": attr, "qualified_column": column})
        else:
            matched.append({**col_spec, "qualified_column": column})
    return matched


def attribute_names_for_entity(demand_profile: dict[str, Any], entity_hint: str) -> list[str]:
    attrs: list[str] = []
    for col_spec in demand_columns_for_entity(demand_profile, entity_hint):
        name = str(col_spec.get("column", "")).split(".")[-1]
        if name and name.lower() != "id" and name not in attrs:
            attrs.append(name)
    return attrs


def infer_output_tables(demand_profile: dict[str, Any], entity_hint: str) -> list[str]:
    tables: set[str] = set()
    if entity_hint:
        tables.add(entity_hint)
    for col_spec in demand_profile.get("columns", []):
        column = str(col_spec.get("column", ""))
        if "." in column:
            tables.add(column.split(".", 1)[0].lower())
    return sorted(tables) or ([entity_hint] if entity_hint else ["entity"])


def build_extraction_task_context(
    queries: list[dict],
    demand_profile: dict[str, Any],
) -> dict[str, Any]:
    """Compact workload context passed to the extractor (agent-visible shape)."""
    return {
        "task": "extract_structured_facts_for_query_workload",
        "workload_summary": compact_workload_summary(queries, demand_profile),
        "demand_profile": demand_profile,
    }


def build_workload_aware_extraction_prompt(
    doc: dict,
    *,
    task_context: dict[str, Any],
) -> str:
    demand_profile = task_context["demand_profile"]
    entity_hint = entity_hint_from_doc(doc)
    relevant_columns = demand_columns_for_entity(demand_profile, entity_hint)
    output_tables = [entity_hint] if entity_hint else infer_output_tables(demand_profile, entity_hint)

    table_specs = []
    for table in output_tables:
        attrs = attribute_names_for_entity(demand_profile, table)
        attr_desc = ", ".join(attrs) if attrs else "(workload-relevant attributes)"
        table_specs.append(f'  "{table}": [{attr_desc}]')

    context_json = json.dumps(
        {
            "workload_summary": task_context.get("workload_summary"),
            "demand_profile": {
                "columns": relevant_columns or demand_profile.get("columns", []),
                "has_join": demand_profile.get("has_join"),
                "has_temporal": demand_profile.get("has_temporal"),
            },
        },
        indent=2,
    )

    return (
        "Extract structured tuples from the document to support the query workload.\n"
        "You are NOT given the target database schema — only workload demand (columns, "
        "roles, aggregations inferred from SQL).\n"
        "Return ONLY valid JSON:\n"
        '{\n  "tables": {\n'
        + "\n".join(table_specs)
        + '\n  }\n}\n'
        "Each table value must be a list of objects with attribute names as keys.\n"
        "Extract values supported by the text for workload-relevant attributes.\n"
        "Do not invent facts. Use null for missing fields.\n\n"
        f"Workload task context:\n{context_json}\n\n"
        f"Document entity hint: {entity_hint or '(unknown)'}\n"
        f"Document ID: {doc['doc_id']}\n"
        f"Document:\n{doc['text']}\n"
    )


def gold_schema_leaks_in_prompt(prompt: str, schema: Schema) -> list[str]:
    """Return substrings from the evaluation schema that appear in an extractor prompt."""
    leaks: list[str] = []
    if schema.description and schema.description.strip():
        excerpt = schema.description.strip()[:120]
        if excerpt and excerpt in prompt:
            leaks.append("schema.description")
    for table, cols in schema.tables.items():
        for col in cols:
            col_type = schema.column_types.get(table, {}).get(col)
            if col_type and f"{col} ({col_type})" in prompt:
                leaks.append(f"typed_column:{table}.{col}")
        # Full table column list as emitted by legacy schema prompt
        col_types = schema.column_types.get(table, {})
        typed_list = ", ".join(
            f"{c} ({col_types.get(c, 'str')})" for c in cols if c.lower() != "id"
        )
        if typed_list and typed_list in prompt:
            leaks.append(f"typed_table_spec:{table}")
    banned_phrases = (
        "Schema description:",
        "according to the schema",
        "Schema tables:",
    )
    for phrase in banned_phrases:
        if phrase in prompt:
            leaks.append(f"phrase:{phrase}")
    return leaks


def align_tuples_to_schema(
    parsed: dict[str, list[dict]],
    schema: Schema,
) -> dict[str, list[dict]]:
    """Map free-form extractor output onto evaluation schema table buckets."""
    from data.dataset_registry import corpus_folder_to_table

    aligned: dict[str, list[dict]] = {table: [] for table in schema.tables}
    schema_tables = {t.lower(): t for t in schema.tables}
    dataset = getattr(schema, "dataset_name", "Player")

    for raw_table, rows in parsed.items():
        raw_lower = str(raw_table).lower()
        canonical = schema_tables.get(raw_lower)
        if canonical is None:
            mapped = corpus_folder_to_table(dataset, raw_lower)
            canonical = schema_tables.get(mapped)
        if canonical is None:
            continue
        allowed_cols = {c.lower() for c in schema.tables[canonical]}
        for row in rows:
            if not isinstance(row, dict):
                continue
            cleaned = {
                k: v
                for k, v in row.items()
                if str(k).lower() in allowed_cols
            }
            aligned[canonical].append(cleaned)
    return aligned

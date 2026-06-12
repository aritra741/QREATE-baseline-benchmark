"""Phase 0: workload demand extraction via a single LLM call."""

from __future__ import annotations

import json
import re
from typing import Any

from llm.client import chat_completion
from pipeline.schema import Schema
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.demand_profile")

_VALID_ROLES = {"group_key", "filter", "aggregate_input", "join_key"}
_VALID_AGG_FUNCS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}


def _build_prompt(queries: list[dict], schema: Schema) -> str:
    query_lines = []
    for q in queries:
        qid = q.get("query_id", "unknown")
        sql = q.get("sql_query", "")
        nl = q.get("nl_query") or ""
        query_lines.append(f"- query_id: {qid}\n  sql: {sql}\n  nl: {nl or '(none)'}")

    return (
        "Analyze the SQL workload below and return ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "demand_profile": {\n'
        '    "columns": [\n'
        "      {\n"
        '        "column": "<table.column or column name>",\n'
        '        "roles": ["group_key" | "filter" | "aggregate_input" | "join_key"],\n'
        '        "aggregation_functions": ["COUNT"|"SUM"|"AVG"|"MIN"|"MAX"],\n'
        '        "query_ids": ["<query_id>", ...]\n'
        "      }\n"
        "    ],\n"
        '    "has_join": <boolean>,\n'
        '    "has_temporal": <boolean>\n'
        "  }\n"
        "}\n\n"
        "Rules:\n"
        "- Valid roles: group_key, filter, aggregate_input, join_key.\n"
        "- Valid aggregation_functions: COUNT, SUM, AVG, MIN, MAX (empty list if none).\n"
        "- Infer columns from SQL (GROUP BY, WHERE, JOIN ON, aggregates).\n"
        "- has_join: true if any query uses JOIN.\n"
        "- has_temporal: true if any query uses date/year/temporal predicates or functions.\n"
        "- No preamble or markdown.\n\n"
        f"Schema tables: {json.dumps(schema.tables)}\n"
        f"Schema description excerpt: {schema.description[:2000]}\n\n"
        "Queries:\n"
        + "\n".join(query_lines)
    )


def _parse_json_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    payload = json.loads(text)
    if "demand_profile" not in payload:
        raise ValueError("Missing demand_profile key in LLM response.")
    return payload


def _validate_demand_profile(profile: dict[str, Any]) -> dict[str, Any]:
    columns = profile.get("columns", [])
    if not isinstance(columns, list):
        raise ValueError("demand_profile.columns must be a list.")
    cleaned: list[dict[str, Any]] = []
    for col in columns:
        roles = [r for r in col.get("roles", []) if r in _VALID_ROLES]
        aggs = [a.upper() for a in col.get("aggregation_functions", []) if a.upper() in _VALID_AGG_FUNCS]
        cleaned.append(
            {
                "column": str(col.get("column", "")),
                "roles": roles,
                "aggregation_functions": aggs,
                "query_ids": [str(q) for q in col.get("query_ids", [])],
            }
        )
    return {
        "columns": cleaned,
        "has_join": bool(profile.get("has_join", False)),
        "has_temporal": bool(profile.get("has_temporal", False)),
    }


def extract_demand_profile_heuristic(queries: list[dict], schema: Schema) -> dict[str, Any]:
    """SQL-only demand profile (no LLM). Used for offline runs."""
    import re

    col_map: dict[str, dict[str, Any]] = {}
    has_join = False
    has_temporal = False

    for q in queries:
        qid = str(q.get("query_id", "unknown"))
        sql = q.get("sql_query", "")
        sql_lower = sql.lower()
        if re.search(r"\bjoin\b", sql_lower):
            has_join = True
        if re.search(r"\b(birth_date|draft_year|year|date|month|day)\b", sql_lower):
            has_temporal = True

        for table, cols in schema.tables.items():
            for col in cols:
                if col.lower() == "id":
                    continue
                patterns = [
                    rf"\b{re.escape(table)}\.{re.escape(col)}\b",
                    rf"\b{re.escape(col)}\b",
                ]
                if not any(re.search(p, sql, re.IGNORECASE) for p in patterns):
                    continue
                key = f"{table}.{col}"
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
                if re.search(rf"group\s+by[^;]*\b{re.escape(col)}\b", sql, re.IGNORECASE):
                    if "group_key" not in entry["roles"]:
                        entry["roles"].append("group_key")
                if re.search(rf"\bwhere\b[^;]*\b{re.escape(col)}\b", sql, re.IGNORECASE):
                    if "filter" not in entry["roles"]:
                        entry["roles"].append("filter")
                for func in ("COUNT", "SUM", "AVG", "MIN", "MAX"):
                    if re.search(rf"\b{func}\s*\([^)]*\b{re.escape(col)}\b", sql, re.IGNORECASE):
                        if "aggregate_input" not in entry["roles"]:
                            entry["roles"].append("aggregate_input")
                        fu = func.upper()
                        if fu not in entry["aggregation_functions"]:
                            entry["aggregation_functions"].append(fu)
                if re.search(rf"\bjoin\b[^;]*\bon\b[^;]*\b{re.escape(col)}\b", sql, re.IGNORECASE):
                    if "join_key" not in entry["roles"]:
                        entry["roles"].append("join_key")

    return _validate_demand_profile(
        {
            "columns": list(col_map.values()),
            "has_join": has_join,
            "has_temporal": has_temporal,
        }
    )


def extract_demand_profile(
    queries: list[dict],
    schema: Schema,
    *,
    use_heuristic: bool = False,
) -> dict[str, Any]:
    """Single LLM call; returns fixed demand_profile for the run."""
    if use_heuristic:
        profile = extract_demand_profile_heuristic(queries, schema)
        logger.info(
            "Demand profile (heuristic): %d columns has_join=%s has_temporal=%s",
            len(profile["columns"]),
            profile["has_join"],
            profile["has_temporal"],
        )
        return profile
    cfg = load_config()
    llm_cfg = cfg["llm"]
    model = llm_cfg.get("agent_model") or llm_cfg.get("extraction_model")
    messages = [
        {
            "role": "system",
            "content": "You are a workload analyzer. Output strict JSON only.",
        },
        {"role": "user", "content": _build_prompt(queries, schema)},
    ]
    raw, _ = chat_completion(
        model,
        messages,
        base_url=llm_cfg.get("base_url", "http://localhost:8000/v1"),
        temperature=float(llm_cfg.get("temperature", 0.0)),
        llm_cfg=llm_cfg,
    )
    payload = _parse_json_payload(raw)
    profile = _validate_demand_profile(payload["demand_profile"])
    logger.info(
        "Demand profile: %d columns has_join=%s has_temporal=%s",
        len(profile["columns"]),
        profile["has_join"],
        profile["has_temporal"],
    )
    return profile

"""Phase 1: corpus supply profiling (no LLM, no extraction)."""

from __future__ import annotations

from typing import Any

from agent.phases.supply_profilers import (
    build_recommendations,
    index_column_mentions,
    infer_join_partner,
    profile_derivability,
    profile_expression_diversity,
    profile_join_key_ambiguity,
)
from pipeline.schema import Schema
from utils.logging import setup_logger

logger = setup_logger("spp.supply_profile")


def _column_match_keys(column: str) -> set[str]:
    bare = column.split(".")[-1].lower()
    return {column.lower(), bare}


def filter_supply_profile_for_query(
    supply_profile: dict[str, Any],
    demand_profile: dict[str, Any],
    query_id: str,
) -> dict[str, Any]:
    """Return supply signals only for columns referenced by this query."""
    referenced: set[str] = set()
    for col_spec in demand_profile.get("columns", []):
        if query_id not in col_spec.get("query_ids", []):
            continue
        referenced.update(_column_match_keys(col_spec.get("column", "")))

    filtered = [
        col
        for col in supply_profile.get("columns", [])
        if _column_match_keys(col.get("column", "")) & referenced
    ]
    return {"columns": filtered}


def build_supply_profile_by_query(
    supply_profile: dict[str, Any],
    demand_profile: dict[str, Any],
    query_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Map each query_id to its demand-filtered supply profile."""
    return {
        qid: filter_supply_profile_for_query(supply_profile, demand_profile, qid)
        for qid in query_ids
    }


ROLE_WEIGHTS: dict[str, int] = {
    "group_key": 3,
    "filter": 3,
    "join_key": 2,
    "aggregate_input": 1,
}


def column_roles_for_query(
    demand_profile: dict[str, Any],
    query_id: str,
    column: str,
) -> list[str]:
    keys = _column_match_keys(column)
    for col_spec in demand_profile.get("columns", []):
        if query_id not in col_spec.get("query_ids", []):
            continue
        if _column_match_keys(col_spec.get("column", "")) & keys:
            return list(col_spec.get("roles", []))
    return []


def role_weight(roles: list[str]) -> int:
    weights = [ROLE_WEIGHTS[r] for r in roles if r in ROLE_WEIGHTS]
    return max(weights) if weights else 0


def build_weighted_config_recommendation(
    demand_profile: dict[str, Any],
    supply_profile_by_query: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Role-weighted vote totals across per-query filtered supply columns."""
    norm_votes: dict[str, int] = {}
    coerce_votes: dict[str, int] = {}
    er_votes: dict[str, int] = {}
    feasibility_flag = False

    for query_id, profile in supply_profile_by_query.items():
        for col in profile.get("columns", []):
            if float(col.get("mention_rate", 0.0)) <= 0.0:
                continue
            weight = role_weight(
                column_roles_for_query(demand_profile, query_id, col.get("column", ""))
            )
            if weight <= 0:
                continue
            rec = col.get("recommendations") or {}
            norm = rec.get("norm_recommendation", "dictionary")
            coerce = rec.get("coerce_recommendation", "strict")
            er = rec.get("er_recommendation", "embedding")
            norm_votes[norm] = norm_votes.get(norm, 0) + weight
            coerce_votes[coerce] = coerce_votes.get(coerce, 0) + weight
            er_votes[er] = er_votes.get(er, 0) + weight
            if rec.get("feasibility_flag"):
                feasibility_flag = True

    def _winner(votes: dict[str, int], default: str) -> str:
        return max(votes, key=votes.get) if votes else default

    return {
        "norm_recommendation": _winner(norm_votes, "dictionary"),
        "coerce_recommendation": _winner(coerce_votes, "strict"),
        "er_recommendation": _winner(er_votes, "embedding"),
        "feasibility_flag": feasibility_flag,
        "vote_totals": {
            "norm": norm_votes,
            "coerce": coerce_votes,
            "er": er_votes,
        },
    }


def union_supply_columns(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate column entries across per-query supply profiles."""
    by_column: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        for col in profile.get("columns", []):
            key = col.get("column", "")
            if key and key not in by_column:
                by_column[key] = col
    return list(by_column.values())


def build_supply_profile(
    corpus: list[dict],
    demand_profile: dict[str, Any],
    schema: Schema,
) -> dict[str, Any]:
    """Analyze raw text for each column in the demand profile."""
    columns_out: list[dict[str, Any]] = []
    n_docs = len(corpus) or 1
    demand_columns = demand_profile.get("columns", [])

    for col_spec in demand_columns:
        column = col_spec.get("column", "")
        roles = col_spec.get("roles", [])
        idx = index_column_mentions(corpus, column, schema)
        mention_rate = len(idx.doc_ids_with_mentions) / n_docs

        expression_diversity = profile_expression_diversity(
            idx.mentions, column=column, schema=schema
        )
        derivability = profile_derivability(idx.mentions, column, schema)

        join_key_ambiguity = None
        if "join_key" in roles:
            partner = infer_join_partner(column, demand_columns, schema)
            join_key_ambiguity = profile_join_key_ambiguity(
                corpus, column, schema, join_partner=partner
            )

        recommendations = build_recommendations(
            expression_diversity=expression_diversity,
            derivability=derivability,
            join_key_ambiguity=join_key_ambiguity,
        )

        columns_out.append(
            {
                "column": column,
                "mention_rate": round(mention_rate, 4),
                "expression_diversity": expression_diversity,
                "derivability": derivability,
                "join_key_ambiguity": join_key_ambiguity,
                "recommendations": recommendations,
            }
        )

    profile = {"columns": columns_out}
    logger.info("Supply profile built for %d demand columns", len(columns_out))
    return profile


__all__ = [
    "build_supply_profile",
    "build_supply_profile_by_query",
    "build_weighted_config_recommendation",
    "filter_supply_profile_for_query",
    "union_supply_columns",
]

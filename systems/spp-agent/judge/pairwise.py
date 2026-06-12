from __future__ import annotations

import json
import random

import pandas as pd

from llm.client import chat_completion
from optimizer.config_space import PopulationConfig
from pipeline.schema import Schema
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.judge")


def _sample_db_rows(db: dict[str, pd.DataFrame], max_rows: int = 10) -> dict[str, list[dict]]:
    sampled: dict[str, list[dict]] = {}
    for table, df in db.items():
        if df.empty:
            sampled[table] = []
        else:
            n = min(max_rows, len(df))
            sampled[table] = df.head(n).to_dict(orient="records")
    return sampled


def _config_description(config: PopulationConfig) -> str:
    return (
        f"ER={config.er_strategy}, normalization={config.norm_strategy}, "
        f"units={config.unit_strategy}, missing={config.miss_strategy}"
    )


def _rows_for_required_tables(db: dict[str, pd.DataFrame], required_tables: set[str] | None) -> dict[str, int]:
    if not required_tables:
        return {t: len(df) for t, df in db.items()}
    return {t: len(db.get(t, pd.DataFrame())) for t in required_tables}


def _both_dbs_empty_for_required(
    db_a: dict[str, pd.DataFrame],
    db_b: dict[str, pd.DataFrame],
    required_tables: set[str] | None,
) -> bool:
    if not required_tables:
        return False
    rows_a = _rows_for_required_tables(db_a, required_tables)
    rows_b = _rows_for_required_tables(db_b, required_tables)
    return all(rows_a.get(t, 0) == 0 for t in required_tables) and all(
        rows_b.get(t, 0) == 0 for t in required_tables
    )


def judge_pairwise(
    db_a: dict[str, pd.DataFrame],
    db_b: dict[str, pd.DataFrame],
    schema: Schema,
    queries: list[dict],
    config_a: PopulationConfig,
    config_b: PopulationConfig,
    model_name: str,
    *,
    required_tables: set[str] | None = None,
    cluster_queries: list[dict] | None = None,
    cluster_type: str = "workload",
) -> dict:
    cfg = load_config()
    base_url = cfg["llm"]["base_url"]

    swap = random.random() < 0.5
    if swap:
        db_a, db_b = db_b, db_a
        config_a, config_b = config_b, config_a

    if _both_dbs_empty_for_required(db_a, db_b, required_tables):
        logger.info(
            "Pairwise judge auto-TIE: both DBs empty for required tables %s",
            sorted(required_tables or []),
        )
        return {
            "winner": "tie",
            "reasoning": "Both databases contain zero rows for workload-required tables.",
            "token_cost": 0.0,
        }

    required_note = ""
    if required_tables:
        required_note = (
            f"\nWorkload-required tables: {sorted(required_tables)}\n"
            "If both databases contain zero rows for the tables required by the query workload, "
            "output TIE. Do not speculate that patterns may extend to missing tables.\n"
        )

    query_sample = cluster_queries if cluster_queries is not None else queries[:8]
    query_summary = "\n".join(
        f"- {q['query_id']}: {q['sql_query'][:120]}" for q in query_sample
    )
    prompt = (
        f"Schema: {schema.description}\n\n"
        f"Query workload sample ({cluster_type} queries):\n{query_summary}\n\n"
        f"Configuration A: {_config_description(config_a)}\n"
        f"Configuration B: {_config_description(config_b)}\n\n"
        f"Database A sample rows:\n{json.dumps(_sample_db_rows(db_a), default=str)[:6000]}\n\n"
        f"Database B sample rows:\n{json.dumps(_sample_db_rows(db_b), default=str)[:6000]}\n\n"
        f"{required_note}"
        f"Which populated database is likely to answer the following {cluster_type} queries more accurately? "
        'Respond with JSON: {"winner": "a"|"b"|"tie", "reasoning": "..."}'
    )

    logger.info(
        "Pairwise judge model=%s configs=(%s vs %s) query_sample=%d",
        model_name,
        config_a.config_id,
        config_b.config_id,
        min(8, len(queries)),
    )

    raw, token_cost = chat_completion(
        model_name,
        [
            {"role": "system", "content": "You compare database quality for SQL workloads. Output JSON only."},
            {"role": "user", "content": prompt},
        ],
        base_url=base_url,
        temperature=0.0,
        llm_cfg=cfg["llm"],
    )

    winner = "tie"
    reasoning = raw
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            winner = str(parsed.get("winner", "tie")).lower()
            reasoning = str(parsed.get("reasoning", raw))
    except json.JSONDecodeError:
        lower = raw.lower()
        if "winner" in lower and '"a"' in lower:
            winner = "a"
        elif "winner" in lower and '"b"' in lower:
            winner = "b"

    if swap:
        if winner == "a":
            winner = "b"
        elif winner == "b":
            winner = "a"

    return {"winner": winner, "reasoning": reasoning, "token_cost": float(token_cost)}

from __future__ import annotations

import random
from dataclasses import dataclass, field

import pandas as pd

from data.query_alignment import assert_required_table_coverage, rows_by_table
from diagnostics.tier1 import compute_tier1
from judge.btl import fit_btl
from judge.btl_report import build_btl_report, log_btl_report
from judge.pair_selection import select_diverse_pairs
from judge.pairwise import judge_pairwise
from optimizer.config_space import PopulationConfig
from pipeline.extraction import ExtractionResult, extract_documents
from pipeline.population import apply_population
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.probing")


@dataclass
class ProbeData:
    config_ids: list[str]
    configs: dict[str, PopulationConfig]
    tier1_signals: dict[str, dict]
    glass_box_composites: dict[str, float]
    pairwise_comparisons: list[dict]
    btl_scores: dict[str, float]
    databases: dict[str, dict[str, pd.DataFrame]]
    total_cost: float
    true_errors: dict[str, float] = field(default_factory=dict)
    btl_report: dict = field(default_factory=dict)
    extraction: ExtractionResult | None = None


def _sample_corpus(corpus: list[dict], fraction: float, min_docs: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    n = max(min_docs, int(len(corpus) * fraction))
    n = min(n, len(corpus))
    indices = list(range(len(corpus)))
    rng.shuffle(indices)
    chosen = sorted(indices[:n])
    sampled = [corpus[i] for i in chosen]
    logger.info(
        "Sampled corpus size=%d (fraction=%.3f min_docs=%d total=%d seed=%d)",
        len(sampled),
        fraction,
        min_docs,
        len(corpus),
        seed,
    )
    for doc in sampled[:5]:
        logger.debug("Sample doc id=%s hint=%s", doc["doc_id"], doc.get("metadata", {}).get("table_hint"))
    if len(sampled) > 5:
        logger.debug("... and %d more sampled docs", len(sampled) - 5)
    return sampled


def run_probes(
    instance,
    schema,
    probe_configs: list[PopulationConfig],
    judge_pair_budget: int,
    *,
    seed: int | None = None,
    corpus_docs: list[dict] | None = None,
    corpus_sample_fraction: float | None = None,
    min_probe_docs: int | None = None,
    required_tables: set[str] | None = None,
    eval_queries: list[dict] | None = None,
) -> ProbeData:
    cfg = load_config()
    seed = seed if seed is not None else int(cfg["experiment"]["seed"])
    probing_cfg = cfg["probing"]
    llm_cfg = cfg["llm"]
    workload_queries = eval_queries if eval_queries is not None else instance.queries

    fraction = float(corpus_sample_fraction if corpus_sample_fraction is not None else probing_cfg["corpus_sample_fraction"])
    min_docs = int(min_probe_docs if min_probe_docs is not None else probing_cfg["min_probe_docs"])

    logger.info(
        "Running probes configs=%d judge_pairs=%d extraction_model=%s judge_model=%s eval_queries=%d",
        len(probe_configs),
        judge_pair_budget,
        llm_cfg.get("extraction_model"),
        llm_cfg.get("judge_model"),
        len(workload_queries),
    )

    if corpus_docs is not None:
        sampled_docs = corpus_docs
        logger.info("Using pre-selected corpus docs=%d", len(sampled_docs))
    else:
        sampled_docs = _sample_corpus(instance.corpus, fraction, min_docs, seed)

    logger.info("Starting extraction on %d docs", len(sampled_docs))
    extraction = extract_documents(sampled_docs, schema, llm_cfg["extraction_model"])
    total_cost = extraction.token_cost
    logger.info("Extraction finished token_cost=%.0f", total_cost)

    config_ids: list[str] = []
    configs: dict[str, PopulationConfig] = {}
    tier1_signals: dict[str, dict] = {}
    glass_box: dict[str, float] = {}
    databases: dict[str, dict[str, pd.DataFrame]] = {}

    for idx, config in enumerate(probe_configs, start=1):
        logger.info("Population %d/%d config=%s", idx, len(probe_configs), config.config_id)
        db, pop_diag = apply_population(extraction, config, schema)
        tier1 = compute_tier1(
            extraction,
            pop_diag,
            schema,
            db,
            queries=workload_queries,
            required_tables=required_tables,
        )
        row_counts = {t: len(df) for t, df in db.items()}
        logger.info(
            "Config %s glass_box=%.4f rows=%s numeric_type=%.4f required_rows=%s",
            config.config_id,
            tier1["glass_box_composite"],
            row_counts,
            tier1.get("numeric_type_success_rate", 1.0),
            tier1.get("required_table_row_count"),
        )
        if idx == 1 and required_tables:
            table_rows = rows_by_table(db)
            corpus_types = set(
                (instance.metadata or {}).get("corpus_entity_types", [])
            ) or None
            logger.info(
                "Required-table coverage check rows=%s required=%s corpus_types=%s",
                table_rows,
                sorted(required_tables),
                sorted(corpus_types) if corpus_types else None,
            )
            assert_required_table_coverage(
                table_rows,
                required_tables,
                corpus_supported_tables=corpus_types,
            )
        config_ids.append(config.config_id)
        configs[config.config_id] = config
        tier1_signals[config.config_id] = tier1
        glass_box[config.config_id] = tier1["glass_box_composite"]
        databases[config.config_id] = db

    pairs = select_diverse_pairs(config_ids, configs, judge_pair_budget, seed=seed)
    logger.info("Selected %d judge pairs: %s", len(pairs), pairs)
    comparisons: list[dict] = []
    for pair_idx, (a, b) in enumerate(pairs, start=1):
        logger.info("Judge pair %d/%d: %s vs %s", pair_idx, len(pairs), a, b)
        result = judge_pairwise(
            databases[a],
            databases[b],
            schema,
            workload_queries,
            configs[a],
            configs[b],
            llm_cfg["judge_model"],
            required_tables=required_tables,
        )
        total_cost += result["token_cost"]
        winner = result["winner"]
        logger.info(
            "Judge result winner=%s tokens=%.0f reasoning=%s",
            winner,
            result["token_cost"],
            str(result["reasoning"])[:200],
        )
        if winner == "a":
            comparisons.append({"winner": a, "loser": b, "reasoning": result["reasoning"]})
        elif winner == "b":
            comparisons.append({"winner": b, "loser": a, "reasoning": result["reasoning"]})
        else:
            logger.info("Judge tie skipped for BTL")

    btl_scores = fit_btl(comparisons, all_config_ids=config_ids)
    btl_report = build_btl_report(comparisons, config_ids, btl_scores)
    log_btl_report(btl_report, logger)
    logger.info("Probe run complete total_token_cost=%.0f", total_cost)

    return ProbeData(
        config_ids=config_ids,
        configs=configs,
        tier1_signals=tier1_signals,
        glass_box_composites=glass_box,
        pairwise_comparisons=comparisons,
        btl_scores=btl_scores,
        databases=databases,
        total_cost=total_cost,
        btl_report=btl_report,
        extraction=extraction,
    )

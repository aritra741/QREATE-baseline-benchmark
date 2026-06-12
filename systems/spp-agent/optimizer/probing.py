from __future__ import annotations

import copy
import dataclasses
import random
from dataclasses import dataclass, field

import pandas as pd

from data.query_alignment import assert_required_table_coverage, rows_by_table
from diagnostics.cluster_glass_box import compute_all_cluster_glass_boxes
from diagnostics.tier1 import compute_tier1
from judge.btl import fit_btl, fit_btl_with_uncertainty
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
    btl_report: dict = field(default_factory=dict)
    extraction: ExtractionResult | None = None
    cluster_glass_box_composites: dict[str, dict[int, float]] = field(default_factory=dict)
    cluster_btl_scores: dict[int, dict[str, float]] = field(default_factory=dict)
    cluster_btl_uncertainty: dict[int, dict[str, float]] = field(default_factory=dict)


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


def _record_comparison(comparisons: list[dict], winner: str, a: str, b: str, reasoning: str) -> None:
    if winner == "a":
        comparisons.append({"winner": a, "loser": b, "reasoning": reasoning})
    elif winner == "b":
        comparisons.append({"winner": b, "loser": a, "reasoning": reasoning})


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
    query_clusters=None,
    shared_extraction: ExtractionResult | None = None,
    skip_judge: bool = False,
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

    if shared_extraction is not None:
        extraction = shared_extraction
        total_cost = float(shared_extraction.token_cost)
        logger.info("Reusing shared extraction token_cost=%.0f", total_cost)
    else:
        logger.info("Starting extraction on %d docs", len(sampled_docs))
        extraction = extract_documents(
            sampled_docs,
            schema,
            llm_cfg["extraction_model"],
            queries=workload_queries,
        )
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

    comparisons: list[dict] = []
    cluster_btl_scores: dict[int, dict[str, float]] = {}
    cluster_btl_uncertainty: dict[int, dict[str, float]] = {}
    btl_scores: dict[str, float] = {}
    btl_report: dict = {}

    if skip_judge:
        logger.info("Skipping LLM judge pairs (structural/meta-controller mode)")
        btl_scores = {cid: 0.0 for cid in config_ids}
    elif query_clusters is not None and query_clusters.n_clusters > 0:
        pairs = select_diverse_pairs(config_ids, configs, judge_pair_budget, seed=seed)
        logger.info("Selected %d judge pairs: %s", len(pairs), pairs)
        for cluster_id, cluster_queries_list in query_clusters.cluster_to_queries.items():
            cluster_type = query_clusters.cluster_types.get(cluster_id, "mixed")
            cluster_comparisons: list[dict] = []
            for pair_idx, (a, b) in enumerate(pairs, start=1):
                logger.info(
                    "Cluster %d judge pair %d/%d: %s vs %s",
                    cluster_id,
                    pair_idx,
                    len(pairs),
                    a,
                    b,
                )
                result = judge_pairwise(
                    databases[a],
                    databases[b],
                    schema,
                    workload_queries,
                    configs[a],
                    configs[b],
                    llm_cfg["judge_model"],
                    required_tables=required_tables,
                    cluster_queries=cluster_queries_list,
                    cluster_type=cluster_type,
                )
                total_cost += result["token_cost"]
                winner = result["winner"]
                _record_comparison(cluster_comparisons, winner, a, b, result["reasoning"])
                _record_comparison(comparisons, winner, a, b, result["reasoning"])

            btl_result = fit_btl_with_uncertainty(
                cluster_comparisons,
                all_config_ids=config_ids,
                seed=seed,
            )
            cluster_btl_scores[cluster_id] = {
                cid: score for cid, (score, _) in btl_result.items()
            }
            cluster_btl_uncertainty[cluster_id] = {
                cid: std for cid, (_, std) in btl_result.items()
            }

        btl_scores = fit_btl(comparisons, all_config_ids=config_ids)
        btl_report = build_btl_report(comparisons, config_ids, btl_scores)
        log_btl_report(btl_report, logger)
    else:
        pairs = select_diverse_pairs(config_ids, configs, judge_pair_budget, seed=seed)
        logger.info("Selected %d judge pairs: %s", len(pairs), pairs)
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
            _record_comparison(comparisons, winner, a, b, result["reasoning"])

        btl_scores = fit_btl(comparisons, all_config_ids=config_ids)
        btl_report = build_btl_report(comparisons, config_ids, btl_scores)
        log_btl_report(btl_report, logger)

    logger.info("Probe run complete total_token_cost=%.0f", total_cost)

    cluster_glass_box_composites: dict[str, dict[int, float]] = {}
    if query_clusters is not None:
        cluster_glass_box_composites = compute_all_cluster_glass_boxes(
            tier1_signals,
            query_clusters.cluster_types,
        )

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
        cluster_glass_box_composites=cluster_glass_box_composites,
        cluster_btl_scores=cluster_btl_scores,
        cluster_btl_uncertainty=cluster_btl_uncertainty,
    )


def expand_structural_probes(
    probe_data: ProbeData,
    instance,
    schema,
    queries: list[dict],
    *,
    n_additional: int,
    seed: int,
    shared_extraction: ExtractionResult | None = None,
) -> tuple[ProbeData, int]:
    """Probe more configs without LLM judge (meta-controller path)."""
    import dataclasses
    import random

    from optimizer.config_space import generate_config_space

    existing_ids = set(probe_data.config_ids)
    remaining = [c for c in generate_config_space() if c.config_id not in existing_ids]
    if not remaining:
        return probe_data, 0

    rng = random.Random(seed)
    rng.shuffle(remaining)
    extra_configs = remaining[:n_additional]
    prior_cost = float(probe_data.total_cost)

    extra_probe = run_probes(
        instance,
        schema,
        extra_configs,
        judge_pair_budget=0,
        seed=seed,
        corpus_docs=list(instance.corpus),
        eval_queries=queries,
        shared_extraction=shared_extraction or probe_data.extraction,
        skip_judge=True,
    )

    merged = dataclasses.replace(
        probe_data,
        config_ids=list(probe_data.config_ids) + list(extra_probe.config_ids),
        configs={**probe_data.configs, **extra_probe.configs},
        tier1_signals={**probe_data.tier1_signals, **extra_probe.tier1_signals},
        glass_box_composites={**probe_data.glass_box_composites, **extra_probe.glass_box_composites},
        pairwise_comparisons=list(probe_data.pairwise_comparisons),
        btl_scores={**probe_data.btl_scores, **extra_probe.btl_scores},
        databases={**probe_data.databases, **extra_probe.databases},
        total_cost=probe_data.total_cost + extra_probe.total_cost,
        extraction=probe_data.extraction or extra_probe.extraction,
    )
    return merged, int(merged.total_cost - prior_cost)

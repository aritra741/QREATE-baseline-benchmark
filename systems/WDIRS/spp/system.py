"""Deployable offline SPP synthesis orchestrator.

This module deliberately has no dependency on ``spp.evaluation`` or
``spp.oracle_evaluation``. Ground truth cannot enter the synthesis call graph.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Sequence

from spp.budget_ledger import BudgetExhausted, GlobalBudgetLedger
from spp.evidence_store import EvidenceStore
from spp.optimizer import (
    PilotResult,
    ProgressiveSearchResult,
    progressive_pilot_search,
    select_budgeted_portfolio,
)
from spp.schema_design import generate_synthesis_configs
from spp.serving import compile_workload_sql, freeze_serving_bundle
from spp.spec import (
    FrozenPortfolio,
    QualityEstimate,
    QueryRequirement,
    SynthesisConfig,
    route_by_conservative_quality,
)
from spp.workload_intent import WorkloadIntent, analyze_workload


class SynthesisBackend(Protocol):
    """Data-plane contract implemented without access to ground truth."""

    def prepare(
        self,
        intent: WorkloadIntent,
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
    ) -> None: ...

    def completion_reserve(
        self,
        configs: Sequence[SynthesisConfig],
        requirements: Sequence[QueryRequirement],
    ) -> int: ...

    def estimate_full_cost(
        self,
        config: SynthesisConfig,
        requirements: Sequence[QueryRequirement],
    ) -> int: ...

    def pilot(
        self,
        config: SynthesisConfig,
        sample_fraction: float,
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
    ) -> PilotResult: ...

    def materialize(
        self,
        config: SynthesisConfig,
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
        output_path: Path,
    ) -> Path: ...

    def validate_materialization(
        self,
        config: SynthesisConfig,
        database_path: Path,
        requirements: Sequence[QueryRequirement],
        evidence_store: EvidenceStore,
        ledger: GlobalBudgetLedger,
    ) -> Mapping[str, QualityEstimate]: ...


SqlCompiler = Callable[
    [QueryRequirement, SynthesisConfig, Path, GlobalBudgetLedger], str
]
IntentAnalyzer = Callable[
    [Sequence[Mapping[str, Any] | str], GlobalBudgetLedger], WorkloadIntent
]


@dataclass(frozen=True)
class SynthesisRunResult:
    serving_manifest: Path
    portfolio: FrozenPortfolio
    progressive_search: ProgressiveSearchResult
    token_summary: dict
    candidate_count: int


class OfflineSynthesisSystem:
    def __init__(
        self,
        backend: SynthesisBackend,
        sql_compiler: SqlCompiler,
        *,
        intent_analyzer: Optional[IntentAnalyzer] = None,
        beta: float = 1.0,
        quality_floor: float = 0.0,
    ):
        self.backend = backend
        self.sql_compiler = sql_compiler
        self.intent_analyzer = intent_analyzer
        self.beta = beta
        self.quality_floor = quality_floor

    def synthesize(
        self,
        *,
        queries: Sequence[Mapping[str, Any] | str],
        token_budget: int,
        output_dir: Path,
        observed_document_lengths: Optional[Sequence[int]] = None,
        sample_fractions: Sequence[float] = (0.05, 0.15, 0.4),
    ) -> SynthesisRunResult:
        output_dir = Path(output_dir).expanduser().resolve()
        if output_dir.exists() and any(output_dir.iterdir()):
            raise FileExistsError(f"synthesis output is not empty: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        ledger = GlobalBudgetLedger(token_budget)

        if self.intent_analyzer is None:
            intent = analyze_workload(queries)
        else:
            intent = self.intent_analyzer(queries, ledger)
        configs = generate_synthesis_configs(
            intent,
            observed_document_lengths=observed_document_lengths,
            exhaustive=False,
        )
        if not configs:
            raise ValueError("workload pruning produced no valid configurations")

        evidence_path = output_dir / "evidence.sqlite"
        with EvidenceStore(evidence_path) as evidence_store:
            self.backend.prepare(intent, evidence_store, ledger)
            completion_reserve = int(
                self.backend.completion_reserve(configs, intent.requirements)
            )
            if not ledger.can_complete(completion_reserve):
                raise BudgetExhausted(
                    "budget cannot complete one valid full-workload configuration"
                )

            def evaluate(
                config: SynthesisConfig,
                fraction: float,
                active_ledger: GlobalBudgetLedger,
            ) -> PilotResult:
                return self.backend.pilot(
                    config, fraction, evidence_store, active_ledger
                )

            search = progressive_pilot_search(
                configs,
                intent.requirements,
                evaluate,
                ledger,
                sample_fractions=sample_fractions,
                completion_reserve=completion_reserve,
                beta=self.beta,
            )
            survivor_configs = [
                config for config in configs if config.config_id in search.survivors
            ]
            if not survivor_configs:
                raise BudgetExhausted("pilot search left no budget-feasible candidates")

            estimates = {
                (query_id, config_id): estimate
                for config_id, pilot in search.pilots.items()
                if config_id in search.survivors
                for query_id, estimate in pilot.estimates.items()
            }
            costs = {
                config.config_id: int(
                    self.backend.estimate_full_cost(config, intent.requirements)
                )
                for config in survivor_configs
            }
            preliminary = select_budgeted_portfolio(
                survivor_configs,
                intent.requirements,
                estimates,
                costs,
                token_budget=token_budget,
                tokens_already_spent=ledger.actual_spent,
                beta=self.beta,
                quality_floor=self.quality_floor,
            )

            db_work_dir = output_dir / "materialized_work"
            db_work_dir.mkdir()
            config_by_id = {config.config_id: config for config in configs}
            database_paths: Dict[str, Path] = {}
            for config_id in preliminary.selected_config_ids:
                config = config_by_id[config_id]
                filename = hashlib.sha256(config_id.encode()).hexdigest()[:16]
                path = db_work_dir / f"{filename}.sqlite"
                database_paths[config_id] = self.backend.materialize(
                    config, evidence_store, ledger, path
                )

            final_estimates: Dict[tuple[str, str], QualityEstimate] = {}
            for config_id, path in database_paths.items():
                measured = self.backend.validate_materialization(
                    config_by_id[config_id],
                    path,
                    intent.requirements,
                    evidence_store,
                    ledger,
                )
                for query_id, estimate in measured.items():
                    final_estimates[(query_id, config_id)] = estimate
            routing, scores = route_by_conservative_quality(
                intent.requirements,
                [config_by_id[cid] for cid in preliminary.selected_config_ids],
                final_estimates,
                beta=self.beta,
                quality_floor=self.quality_floor,
            )
            used = tuple(sorted(set(routing.values())))
            final_portfolio = FrozenPortfolio(
                selected_config_ids=used,
                query_to_config=routing,
                query_scores=scores,
                construction_tokens=ledger.actual_spent,
                objective_value=sum(scores.values()),
            )
            final_portfolio.validate(
                intent.requirements, config_by_id, token_budget
            )

            compiled = compile_workload_sql(
                intent.requirements,
                final_portfolio,
                config_by_id,
                database_paths,
                self.sql_compiler,
                ledger,
            )
            supported_values: Dict[str, set[str]] = {}
            for config_id in final_portfolio.selected_config_ids:
                values: set[str] = set()
                for provenance in evidence_store.supported_cells(
                    config_id=config_id
                ):
                    try:
                        value = json.loads(provenance.value_json)
                    except json.JSONDecodeError:
                        value = provenance.value_json
                    if value is not None:
                        values.add(str(value).strip().lower())
                supported_values[config_id] = values

            output_scores: Dict[str, float] = {}
            output_support_by_query: Dict[str, float] = {}
            requirements_by_id = {
                requirement.query_id: requirement
                for requirement in intent.requirements
            }
            for query in compiled:
                db_path = Path(database_paths[query.config_id]).resolve()
                uri = f"file:{db_path}?mode=ro"
                with sqlite3.connect(uri, uri=True) as connection:
                    rows = connection.execute(query.sql).fetchall()
                output_values = [
                    str(value).strip().lower()
                    for row in rows
                    for value in row
                    if value is not None
                ]
                if not output_values:
                    support = 0.0
                elif set(
                    requirements_by_id[query.query_id].operators
                ) & {"count", "sum", "avg", "min", "max"}:
                    # Aggregate outputs are derived and need not occur verbatim
                    # in provenance. Their source-cell support is already part
                    # of the base query-conditioned estimate.
                    support = 1.0
                else:
                    supported = supported_values.get(query.config_id, set())
                    support = sum(
                        value in supported for value in output_values
                    ) / len(output_values)
                base_score = final_portfolio.query_scores[query.query_id]
                output_support_by_query[query.query_id] = support
                output_scores[query.query_id] = base_score * support
            # SQL compilation and repair are part of construction cost.
            final_portfolio = replace(
                final_portfolio,
                query_scores=output_scores,
                construction_tokens=ledger.actual_spent,
                objective_value=sum(output_scores.values()),
            )
            final_portfolio.validate(
                intent.requirements, config_by_id, token_budget
            )
            evidence_manifest = evidence_store.manifest()

        os.chmod(evidence_path, 0o444)
        backend_manifest = (
            self.backend.reproducibility_manifest()
            if hasattr(self.backend, "reproducibility_manifest")
            else {"backend": type(self.backend).__name__}
        )
        candidate_space = {
            "count": len(configs),
            "schemas": {
                config.schema.schema_id: asdict(config.schema)
                for config in configs
            },
            "population_configs": {
                config.population.config_id: asdict(config.population)
                for config in configs
            },
            "preprocessing_policies": {
                config.preprocessing.policy_id: asdict(config.preprocessing)
                for config in configs
            },
            "configs": [
                {
                    "config_id": config.config_id,
                    "schema_id": config.schema.schema_id,
                    "population_config_id": config.population.config_id,
                    "preprocessing_policy_id": config.preprocessing.policy_id,
                }
                for config in configs
            ],
        }
        synthesis_manifest = {
            "workload_intent": asdict(intent),
            "candidate_space": candidate_space,
            "progressive_search": {
                "survivors": search.survivors,
                "eliminated": search.eliminated,
                "rounds_completed": search.rounds_completed,
                "tokens_spent": search.tokens_spent,
                "pilots": {
                    config_id: {
                        "sample_fraction": pilot.sample_fraction,
                        "output_signature": pilot.output_signature,
                        "full_cost_upper_bound": pilot.full_cost_upper_bound,
                        "metadata": pilot.metadata,
                        "estimates": {
                            query_id: {
                                "f_proxy": estimate.f_proxy,
                                "lcb": estimate.lower_confidence_bound(self.beta),
                                "uncertainty": estimate.uncertainty,
                                "sample_size": estimate.sample_size,
                            }
                            for query_id, estimate in pilot.estimates.items()
                        },
                    }
                    for config_id, pilot in search.pilots.items()
                },
                "survivor_estimate_details": {
                    config_id: {
                        query_id: asdict(estimate)
                        for query_id, estimate in search.pilots[
                            config_id
                        ].estimates.items()
                    }
                    for config_id in sorted(
                        set(search.survivors)
                        | set(final_portfolio.selected_config_ids)
                    )
                    if config_id in search.pilots
                },
            },
            "portfolio": asdict(final_portfolio),
            "compiled_queries": [asdict(query) for query in compiled],
            "compiled_output_support": output_support_by_query,
            "backend": backend_manifest,
        }
        synthesis_manifest_path = output_dir / "synthesis_manifest.json"
        synthesis_manifest_path.write_text(
            json.dumps(synthesis_manifest, indent=2, default=str)
        )
        synthesis_manifest_sha256 = hashlib.sha256(
            synthesis_manifest_path.read_bytes()
        ).hexdigest()
        os.chmod(synthesis_manifest_path, 0o444)
        bundle_dir = output_dir / "serving_bundle"
        manifest = freeze_serving_bundle(
            bundle_dir,
            final_portfolio,
            compiled,
            database_paths,
            ledger,
            evidence_manifest=evidence_manifest,
            synthesis_manifest_sha256=synthesis_manifest_sha256,
        )
        return SynthesisRunResult(
            serving_manifest=manifest,
            portfolio=final_portfolio,
            progressive_search=search,
            token_summary=ledger.summary(),
            candidate_count=len(configs),
        )
